"""Loop do agente: OpenAI Responses API + execução de tools + log de turnos.

`run_turn` é o cérebro puro: recebe o texto do usuário, conversa com o modelo
(chamando tools sobre agent_products) e devolve a resposta em texto. NÃO envia
WhatsApp — quem envia é o handler. Isso mantém o loop testável isoladamente.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import AgentProduct, AgentSession, AgentTurnLog, Contact
from app.agent import tools as tools_mod
from app.agent.prompt import build_system_prompt
from app.agent.router import resolve_product_slug

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


async def run_turn(
    db: AsyncSession,
    session: AgentSession,
    contact: Contact,
    user_text: str,
    *,
    build_tools=tools_mod.build_read_tool_schemas,
    extra_execute=None,
) -> dict:
    """Roda um turno. Retorna {reply, tokens_in, tokens_out, tools, product_slug}.

    `build_tools`/`extra_execute` permitem à Fase 2 injetar tools de escrita sem
    reescrever o loop.
    """
    res = await db.execute(
        select(AgentProduct).where(AgentProduct.is_active.is_(True)).order_by(AgentProduct.slug)
    )
    products = list(res.scalars().all())
    slugs = [p.slug for p in products]

    # roteamento: fixa o produto em foco se ainda não houver
    if not session.product_slug:
        slug = resolve_product_slug(contact, user_text, products)
        if slug:
            session.product_slug = slug

    prod_dicts = [{"slug": p.slug, "name": p.name, "event_dates": p.event_dates} for p in products]
    system = build_system_prompt(prod_dicts, _today())
    if session.product_slug:
        system += f'\n\n[Contexto: a conversa está focada no congresso de slug "{session.product_slug}". Priorize-o, mas atenda se a pessoa perguntar do outro.]'
    if session.history_summary:
        system += f"\n\n[Resumo da conversa até aqui: {session.history_summary}]"

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
    reply = ""
    guard_note = None

    for _ in range(settings.AGENT_MAX_TOOL_ITERS):
        resp = await client.responses.create(
            model=settings.OPENAI_MODEL_MAIN,
            instructions=system,
            input=work,
            tools=tool_schemas,
            tool_choice="auto",
            store=False,
            max_output_tokens=settings.AGENT_MAX_OUTPUT_TOKENS,
        )
        usage = getattr(resp, "usage", None)
        if usage:
            tokens_in += getattr(usage, "input_tokens", 0) or 0
            tokens_out += getattr(usage, "output_tokens", 0) or 0

        fcalls, text = _extract(resp)
        if not fcalls:
            reply = text
            break

        for fc in fcalls:
            try:
                args = json.loads(fc.arguments or "{}")
            except Exception:
                args = {}
            result = None
            if extra_execute is not None:
                result = await extra_execute(fc.name, args, ctx)
            if result is None:
                result = await tools_mod.execute_tool(fc.name, args, ctx)
            tool_trace.append({"name": fc.name, "args": args})
            work.append({"type": "function_call", "call_id": fc.call_id,
                         "name": fc.name, "arguments": fc.arguments})
            work.append({"type": "function_call_output", "call_id": fc.call_id,
                         "output": json.dumps(result, ensure_ascii=False)})
    else:
        # esgotou as iterações de tool sem uma resposta final
        reply = "Deixa eu confirmar isso certinho com a equipe e já te retorno, tá? 🙏"
        guard_note = "tool_iters_exhausted"

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
    session.last_outbound_at = datetime.now(SP_TZ)

    db.add(AgentTurnLog(
        session_id=session.id, direction="inbound", content=user_text,
        model=settings.OPENAI_MODEL_MAIN,
    ))
    db.add(AgentTurnLog(
        session_id=session.id, direction="outbound", content=reply,
        tool_calls=tool_trace or None,
        guardrail={"note": guard_note} if guard_note else None,
        model=settings.OPENAI_MODEL_MAIN,
        tokens_in=tokens_in, tokens_out=tokens_out, latency_ms=latency_ms,
    ))

    return {
        "reply": reply,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "tools": tool_trace,
        "product_slug": session.product_slug,
    }
