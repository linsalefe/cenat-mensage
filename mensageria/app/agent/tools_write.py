"""Tools de escrita do agente (Fase 2). Allowlist explícita — o agente NUNCA
deleta nada. Efeitos: memória de conta (Contact.ai_memory), status do lead,
follow-ups, handoff para humano e checagem de inscrição.

Re-consultam Contact/AgentSession pelo db (identity map garante o mesmo objeto
que o loop está usando), então mutações valem no commit do handler."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select

from app.config import get_settings
from app.models import AgentFollowup, AgentProduct, AgentSession, Contact
from app.agent.tools import ToolContext

settings = get_settings()
SP_TZ = timezone(timedelta(hours=-3))

WRITE_NAMES = {
    "save_lead_memory", "update_lead_status", "schedule_followup",
    "handoff_to_human", "check_enrollment",
}

_DELAYS = {
    "em_1_dia": timedelta(days=1),
    "em_2_dias": timedelta(days=2),
    "em_3_dias": timedelta(days=3),
    "em_1_semana": timedelta(days=7),
}

WRITE_TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "name": "save_lead_memory",
        "description": "Salva/atualiza o que você aprendeu sobre a pessoa (memória de conta, persiste entre conversas). Passe só os campos que descobriu.",
        "parameters": {
            "type": "object",
            "properties": {
                "perfil": {"type": ["string", "null"], "enum": ["estudante", "profissional", "outro", None]},
                "interesse": {"type": ["string", "null"], "description": "resumo do interesse/necessidade"},
                "objecoes": {"type": ["array", "null"], "items": {"type": "string"}, "description": "objeções levantadas (preço, tempo, etc.)"},
                "quer_submeter_trabalho": {"type": ["boolean", "null"]},
                "melhor_horario": {"type": ["string", "null"]},
                "congresso_preferido": {"type": ["string", "null"], "description": "slug do congresso preferido"},
            },
            "additionalProperties": False,
        },
        "strict": False,
    },
    {
        "type": "function",
        "name": "update_lead_status",
        "description": "Atualiza o estágio do lead no funil conforme a conversa evolui.",
        "parameters": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["em_conversa", "interessado", "proposta_enviada", "perdido", "descartado"]},
            },
            "required": ["status"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "schedule_followup",
        "description": "Agenda um lembrete/retomada para falar com a pessoa depois. Use quando ela pedir para ser lembrada (ex.: antes de virar o lote) ou ficar de pensar. Só agende com consentimento dela.",
        "parameters": {
            "type": "object",
            "properties": {
                "quando": {"type": "string", "enum": ["em_1_dia", "em_2_dias", "em_3_dias", "em_1_semana", "antes_do_prazo_do_lote"]},
                "motivo": {"type": "string", "description": "por que o follow-up (contexto p/ a mensagem futura)"},
            },
            "required": ["quando", "motivo"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "handoff_to_human",
        "description": "Transfere a conversa para uma pessoa da equipe e PARA de responder. Use em: pedido explícito de humano, sofrimento psíquico/crise, reembolso/pagamento/nota fiscal/troca de titularidade, irritação com o atendimento, ou dúvida sem resposta na base.",
        "parameters": {
            "type": "object",
            "properties": {
                "motivo": {"type": "string", "description": "motivo curto do handoff"},
                "resumo": {"type": "string", "description": "resumo do que a pessoa precisa, para o humano assumir"},
            },
            "required": ["motivo", "resumo"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "check_enrollment",
        "description": "Verifica se a pessoa já está inscrita/pagou (para não vender de novo a quem já comprou).",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        "strict": True,
    },
]


async def _contact(ctx: ToolContext) -> Contact | None:
    r = await ctx.db.execute(select(Contact).where(Contact.wa_id == ctx.contact_wa_id))
    return r.scalar_one_or_none()


async def _session(ctx: ToolContext) -> AgentSession | None:
    if ctx.session_id is None:
        return None
    return await ctx.db.get(AgentSession, ctx.session_id)


async def execute_write_tool(name: str, args: dict[str, Any], ctx: ToolContext) -> dict:
    if name == "save_lead_memory":
        contact = await _contact(ctx)
        if contact is None:
            return {"erro": "contato não encontrado"}
        mem = dict(contact.ai_memory or {})
        for k in ("perfil", "interesse", "objecoes", "quer_submeter_trabalho", "melhor_horario", "congresso_preferido"):
            v = args.get(k)
            if v is not None:
                mem[k] = v
        contact.ai_memory = mem
        contact.ai_memory_updated_at = datetime.now(SP_TZ)
        return {"ok": True, "memoria": mem}

    if name == "update_lead_status":
        contact = await _contact(ctx)
        if contact is None:
            return {"erro": "contato não encontrado"}
        contact.lead_status = args["status"]
        return {"ok": True, "lead_status": contact.lead_status}

    if name == "schedule_followup":
        # cadência: no máx. 3 follow-ups pendentes por contato
        cnt = await ctx.db.scalar(
            select(func.count()).select_from(AgentFollowup).where(
                AgentFollowup.contact_wa_id == ctx.contact_wa_id,
                AgentFollowup.status == "pending",
            )
        )
        if (cnt or 0) >= 3:
            return {"ok": False, "motivo": "já há 3 follow-ups pendentes"}
        quando = args.get("quando")
        now = datetime.now(SP_TZ)
        run_at = None
        kind = "custom"
        if quando == "antes_do_prazo_do_lote":
            kind = "lot_deadline"
            sess = await _session(ctx)
            slug = sess.product_slug if sess else None
            if slug:
                p = await ctx.db.scalar(select(AgentProduct).where(AgentProduct.slug == slug))
                deadline = _earliest_deadline(p) if p else None
                if deadline:
                    run_at = datetime.combine(deadline - timedelta(days=2), datetime.min.time()).replace(hour=10, tzinfo=SP_TZ)
            if run_at is None:
                run_at = now + timedelta(days=3)
        else:
            run_at = now + _DELAYS.get(quando, timedelta(days=2))
        if run_at <= now:
            run_at = now + timedelta(days=1)
        fu = AgentFollowup(
            session_id=ctx.session_id,
            contact_wa_id=ctx.contact_wa_id,
            run_at=run_at,
            kind=kind,
            payload={"motivo": args.get("motivo", ""), "product_slug": (await _session(ctx)).product_slug if await _session(ctx) else None},
            status="pending",
        )
        ctx.db.add(fu)
        return {"ok": True, "agendado_para": run_at.isoformat(), "kind": kind}

    if name == "handoff_to_human":
        contact = await _contact(ctx)
        sess = await _session(ctx)
        if sess is not None:
            sess.status = "handed_off"
        if contact is not None:
            contact.ai_active = False
            nota = f"[{datetime.now(SP_TZ):%d/%m %H:%M}] 🤖→👤 Handoff: {args.get('motivo','')}. {args.get('resumo','')}"
            contact.notes = (contact.notes + "\n" + nota) if contact.notes else nota
        print(f"🤖→👤 HANDOFF {ctx.contact_wa_id}: {args.get('motivo','')}", flush=True)
        return {"ok": True, "handed_off": True}

    if name == "check_enrollment":
        contact = await _contact(ctx)
        inscrito = bool(contact and contact.lead_status == "ganho")
        return {"inscrito": inscrito}

    return {"erro": f"tool de escrita desconhecida: {name}"}


def _earliest_deadline(prod: AgentProduct):
    if prod is None:
        return None
    best = None
    for t in (prod.tickets or []):
        d = t.get("lot_deadline")
        if not d:
            continue
        try:
            dt = datetime.strptime(d, "%Y-%m-%d").date()
        except Exception:
            continue
        if best is None or dt < best:
            best = dt
    return best
