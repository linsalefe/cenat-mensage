"""Loop do agente: OpenAI Responses API + execução de tools + log de turnos.

`run_turn` é o cérebro puro: recebe o texto do usuário, conversa com o modelo
(chamando tools sobre agent_products) e devolve a resposta em texto. NÃO envia
WhatsApp — quem envia é o handler. Isso mantém o loop testável isoladamente.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import AgentProduct, AgentSession, AgentTurnLog, Contact, Message
from app.agent import tools as tools_mod
from app.agent import tools_write
from app.agent.guardrails import check_output, classify_input
from app.agent.prompt import build_system_prompt
from app.agent.router import resolve_route

settings = get_settings()
SP_TZ = timezone(timedelta(hours=-3))

_client: Optional[AsyncOpenAI] = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


def _today() -> str:
    return datetime.now(SP_TZ).strftime("%d/%m/%Y")


def _extract(resp) -> tuple[list, str]:
    """Retorna (function_calls, texto). Usa só itens type=message (ignora
    reasoning/outros), evitando vazar raciocínio na saída."""
    fcalls = [o for o in (resp.output or []) if getattr(o, "type", None) == "function_call"]
    parts = []
    for item in (resp.output or []):
        if getattr(item, "type", None) != "message":
            continue
        for cont in (getattr(item, "content", []) or []):
            if getattr(cont, "type", None) in ("output_text", "text"):
                parts.append(getattr(cont, "text", "") or "")
    text = "".join(parts).strip()
    if not text:  # fallback à conveniência do SDK
        text = (getattr(resp, "output_text", "") or "").strip()
    return fcalls, text


def _sanitize(text: str) -> str:
    """Rede de segurança: colapsa uma duplicação EXATA da mensagem inteira
    (modelo às vezes repete o texto). Conservador: só age se as duas metades
    forem idênticas."""
    t = (text or "").strip()
    n = len(t)
    if n > 40 and n % 2 == 0:
        a, b = t[: n // 2].strip(), t[n // 2:].strip()
        if a and a == b:
            return a
    return t


def _default_tools(slugs: list[str]) -> list[dict]:
    return tools_mod.build_read_tool_schemas(slugs) + tools_write.WRITE_TOOL_SCHEMAS


async def _default_execute(name, args, ctx):
    if name in tools_write.WRITE_NAMES:
        return await tools_write.execute_write_tool(name, args, ctx)
    return None  # cai no execute_tool (read)


def _memory_facts(contact: Contact) -> str:
    mem = contact.ai_memory or {}
    facts = "; ".join(f"{k}={v}" for k, v in mem.items() if v not in (None, "", [], {}))
    return facts


async def _maybe_compact(session: AgentSession) -> None:
    """Compacta o histórico quando fica longo: resume os turnos antigos com o
    modelo nano e mantém os últimos 20 itens (≈10 turnos)."""
    history = session.history or []
    if len(history) < 2 * settings.AGENT_MAX_TURNS_BEFORE_COMPACT:
        return
    keep = history[-20:]
    old = history[:-20]
    convo = "\n".join(f"{m.get('role')}: {m.get('content','')}" for m in old if m.get("role"))
    try:
        resp = await get_client().responses.create(
            model=settings.OPENAI_MODEL_GUARD,
            instructions="Resuma em português, em até 6 linhas, os fatos e decisões relevantes desta conversa de vendas para dar continuidade: interesse, congresso, perfil, objeções e próximos passos. Só o resumo.",
            input=convo, store=False, max_output_tokens=250,
        )
        summary = (getattr(resp, "output_text", "") or "").strip()
    except Exception as e:
        print(f"🤖⚠️ compactação falhou: {e!r}", flush=True)
        return
    prev = session.history_summary or ""
    session.history_summary = (prev + "\n" + summary).strip() if prev else summary
    session.history = keep


_SALESY = re.compile(r"R\$|lote|inscri|checkout|congresso|desconto|combo", re.I)


def _looks_salesy(text: str) -> bool:
    return bool(_SALESY.search(text or ""))


async def _last_broadcast_text(db: AsyncSession, contact: Contact) -> str:
    """Texto do último disparo enviado a este contato, para rotear quem responde
    a uma campanha.

    Quem recebe "promoção de 25% na pós de TEA" e responde só "quanto custa?" não
    dá sinal nenhum no próprio texto — o contexto está no que foi disparado.
    Olhamos apenas mensagens NÃO geradas pelo agente (`sent_by_ai` falso), para o
    roteamento não se realimentar das próprias respostas, e só nas últimas 72h.
    """
    try:
        limite = datetime.now(SP_TZ).replace(tzinfo=None) - timedelta(hours=72)
        res = await db.execute(
            select(Message.content)
            .where(
                Message.contact_wa_id == contact.wa_id,
                Message.direction == "outbound",
                Message.sent_by_ai.isnot(True),
                Message.timestamp >= limite,
            )
            .order_by(Message.timestamp.desc())
            .limit(1)
        )
        return (res.scalar_one_or_none() or "")[:1000]
    except Exception as e:  # roteamento é best-effort, nunca derruba o turno
        print(f"🤖⚠️ _last_broadcast_text falhou: {e!r}", flush=True)
        return ""


async def _force_handoff(db: AsyncSession, contact: Contact, session: AgentSession, motivo: str) -> None:
    session.status = "handed_off"
    contact.ai_active = False
    nota = f"[{datetime.now(SP_TZ):%d/%m %H:%M}] 🛡️→👤 Handoff automático (guardrail): {motivo}"
    contact.notes = (contact.notes + "\n" + nota) if contact.notes else nota
    print(f"🛡️→👤 HANDOFF automático {contact.wa_id}: {motivo}", flush=True)


async def run_turn(
    db: AsyncSession,
    session: AgentSession,
    contact: Contact,
    user_text: str,
    *,
    build_tools=None,
    extra_execute=None,
) -> dict:
    """Roda um turno. Retorna {reply, tokens_in, tokens_out, tools, product_slug}.

    Por padrão usa tools de leitura + escrita (Fase 2). `build_tools`/`extra_execute`
    permitem sobrescrever (ex.: evals).
    """
    build_tools = build_tools or _default_tools
    exec_fn = extra_execute or _default_execute
    res = await db.execute(
        select(AgentProduct).where(AgentProduct.is_active.is_(True)).order_by(AgentProduct.slug)
    )
    products = list(res.scalars().all())
    slugs = [p.slug for p in products]

    # roteamento: fixa o produto em foco se ainda não houver
    rota = None
    if not session.product_slug:
        campaign_text = await _last_broadcast_text(db, contact)
        rota = resolve_route(contact, user_text, products, campaign_text)
        slug = rota.slug
        if not slug:
            mem = contact.ai_memory or {}
            mem_slug = mem.get("pos_interesse") or mem.get("congresso_preferido")
            if mem_slug in slugs:
                slug = mem_slug
        if slug:
            session.product_slug = slug

    prod_dicts = [
        {"slug": p.slug, "name": p.name, "kind": p.kind, "event_dates": p.event_dates}
        for p in products
    ]
    system = build_system_prompt(prod_dicts, _today())
    if session.product_slug:
        kind_atual = next(
            (p.kind for p in products if p.slug == session.product_slug), "congresso"
        )
        rotulo = "pós-graduação" if kind_atual == "pos" else "congresso"
        system += (
            f'\n\n[Contexto: a conversa está focada na {rotulo} de slug '
            f'"{session.product_slug}". Priorize-a, mas atenda se a pessoa perguntar de outro.]'
        )
    if rota is not None and rota.mismatch:
        # Sobrepõe a regra 7 (responder preço na hora): dar o valor do produto
        # errado é pior do que gastar um turno alinhando o que a pessoa quer.
        system += (
            "\n\n[ATENÇÃO — CATEGORIA TROCADA. A pessoa se referiu a este produto usando a "
            "palavra da OUTRA categoria (chamou de 'congresso' algo que é pós-graduação, ou o "
            "contrário). NESTE TURNO, faça exatamente três coisas e nada além:\n"
            "1) diga com gentileza qual é a categoria real do que ela mencionou;\n"
            "2) explique a diferença de forma concreta — congresso é um evento curto, de dois "
            "dias, com certificado de participação; pós-graduação é uma formação longa, de mais "
            "de um ano, com processo seletivo e título de especialista;\n"
            "3) pergunte qual dos dois ela procura.\n"
            "NÃO informe preço, NÃO informe datas, NÃO mande links e NÃO chame "
            "encaminhar_comercial_pos neste turno — espere a resposta dela. Isto vale mesmo que "
            "ela tenha perguntado o valor: responder o preço do produto errado é o pior "
            "resultado possível aqui.]"
        )
    if session.history_summary:
        system += f"\n\n[Resumo da conversa até aqui: {session.history_summary}]"
    facts = _memory_facts(contact)
    if facts:
        system += f"\n\n[O que já sabemos sobre a pessoa (memória de conta): {facts}. Use com naturalidade, não repita tudo de volta nem recomece a apresentação.]"

    tool_schemas = build_tools(slugs)
    ctx = tools_mod.ToolContext(
        db=db, contact_wa_id=contact.wa_id, channel_id=session.channel_id, session_id=session.id
    )

    history = list(session.history or [])
    work = history + [{"role": "user", "content": user_text}]

    client = get_client()
    t0 = time.monotonic()
    tokens_in = tokens_out = 0
    tool_trace: list[dict] = []
    guard_note = None

    # Guardrail de ENTRADA em paralelo (nano) — não bloqueia a geração (§6.3).
    input_guard_task = asyncio.create_task(classify_input(user_text))

    async def _generate(work_items: list) -> str:
        nonlocal tokens_in, tokens_out
        for _ in range(settings.AGENT_MAX_TOOL_ITERS):
            resp = await client.responses.create(
                model=settings.OPENAI_MODEL_MAIN, instructions=system,
                input=work_items, tools=tool_schemas, tool_choice="auto",
                store=False, max_output_tokens=settings.AGENT_MAX_OUTPUT_TOKENS,
            )
            usage = getattr(resp, "usage", None)
            if usage:
                tokens_in += getattr(usage, "input_tokens", 0) or 0
                tokens_out += getattr(usage, "output_tokens", 0) or 0
            fcalls, text = _extract(resp)
            if not fcalls:
                return text
            for fc in fcalls:
                try:
                    args = json.loads(fc.arguments or "{}")
                except Exception:
                    args = {}
                result = await exec_fn(fc.name, args, ctx)
                if result is None:
                    result = await tools_mod.execute_tool(fc.name, args, ctx)
                tool_trace.append({"name": fc.name, "args": args})
                work_items.append({"type": "function_call", "call_id": fc.call_id,
                                   "name": fc.name, "arguments": fc.arguments})
                work_items.append({"type": "function_call_output", "call_id": fc.call_id,
                                   "output": json.dumps(result, ensure_ascii=False)})
        return ""  # esgotou iterações de tool

    reply = await _generate(work)
    if not reply:
        reply = "Deixa eu confirmar isso certinho com a equipe e já te retorno, tá? 🙏"
        guard_note = "tool_iters_exhausted"

    # Guardrail de SAÍDA (bloqueante, determinístico): preço/link vs. base.
    # Lote ativo (congresso) + investimento da pós (cheio, à vista, parcela).
    allowed_prices = tools_mod.allowed_prices_for(products)
    allowed_domains = [d.strip() for d in settings.AGENT_LINK_ALLOWLIST.split(",") if d.strip()]
    guard = check_output(reply, allowed_prices, allowed_domains)
    if not guard["ok"]:
        work.append({"role": "user", "content":
            "[sistema] Sua última resposta citou informação que NÃO confere com a base"
            f" (preços {guard['bad_prices']} / links {guard['bad_links']}"
            f" / cupons {guard.get('bad_cupons', [])}). Reescreva usando"
            " SOMENTE os dados retornados pelas tools; se não tiver certeza de um valor,"
            " link ou código promocional, não o cite e ofereça confirmar com a equipe."})
        reply2 = await _generate(work)
        guard2 = check_output(reply2, allowed_prices, allowed_domains) if reply2 else {"ok": False}
        if reply2 and guard2.get("ok"):
            reply, guard, guard_note = reply2, guard2, "output_guard_corrected"
        else:
            reply = "Deixa eu confirmar esses valores certinho com a equipe e já te confirmo, tá? 🙏"
            guard_note = "output_guard_fallback"
            print(f"🛡️ GUARDRAIL fallback (preço/link/cupom fora da base): "
                  f"{guard['bad_prices']} {guard['bad_links']} "
                  f"{guard.get('bad_cupons', [])}", flush=True)

    # Guardrail de ENTRADA: risco sensível → acolhe e força handoff.
    try:
        ig = await input_guard_task
    except Exception:
        ig = {}
    if ig.get("risco_sensivel"):
        if _looks_salesy(reply):
            reply = ("Sinto muito que você esteja passando por isso. Você não está sozinha(o) — "
                     "vou chamar uma pessoa da nossa equipe para te apoiar agora. Se houver risco "
                     "imediato, ligue 188 (CVV) ou 192.")
        await _force_handoff(db, contact, session, motivo="risco_sensivel (guardrail)")
        guard_note = f"{guard_note}+risco_sensivel" if guard_note else "risco_sensivel"

    if not reply:
        reply = "Deixa eu confirmar isso com a equipe e já te retorno 🙏"
        guard_note = guard_note or "empty_reply"

    reply = _sanitize(reply)
    latency_ms = int((time.monotonic() - t0) * 1000)

    # histórico limpo: só mensagens role/content (itens de tool são efêmeros do turno)
    session.history = history + [
        {"role": "user", "content": user_text},
        {"role": "assistant", "content": reply},
    ]
    session.turns_count = (session.turns_count or 0) + 1
    # naive UTC-3, a convenção do projeto — a coluna deixou de ser timestamptz
    # na migração d4a1e7b3c920, junto com last_inbound_at.
    session.last_outbound_at = datetime.now(SP_TZ).replace(tzinfo=None)

    db.add(AgentTurnLog(
        session_id=session.id, direction="inbound", content=user_text,
        model=settings.OPENAI_MODEL_MAIN,
    ))
    db.add(AgentTurnLog(
        session_id=session.id, direction="outbound", content=reply,
        tool_calls=tool_trace or None,
        guardrail={
            "note": guard_note,
            "out_ok": guard.get("ok"),
            "prices_seen": guard.get("prices_seen"),
            "bad": (guard.get("bad_prices") or []) + (guard.get("bad_links") or []),
            "in": ig,
        },
        model=settings.OPENAI_MODEL_MAIN,
        tokens_in=tokens_in, tokens_out=tokens_out, latency_ms=latency_ms,
    ))

    await _maybe_compact(session)

    return {
        "reply": reply,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "tools": tool_trace,
        "product_slug": session.product_slug,
    }
