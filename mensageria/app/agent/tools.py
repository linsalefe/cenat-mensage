"""Tools do agente. Fase 1 = somente leitura sobre agent_products (fonte da
verdade de preços/lotes/links). Fase 2 adiciona tools de escrita (ver tools_write).

Formato de tool = Responses API "function" (flat): {type, name, description,
parameters, strict}. `execute_tool` despacha pelo nome e retorna dict serializável.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentProduct


@dataclass
class ToolContext:
    db: AsyncSession
    contact_wa_id: str
    channel_id: Optional[int] = None
    session_id: Optional[int] = None


def _fmt_price(cents: int) -> str:
    reais = cents / 100
    if cents % 100 == 0:
        return f"R$ {int(reais)}"
    return f"R$ {reais:.2f}".replace(".", ",")


def _active_tickets(prod: AgentProduct) -> list[dict]:
    out = []
    for t in (prod.tickets or []):
        if not t.get("active", True):
            continue
        cents = t.get("price_cents")
        if cents is None:
            continue  # lote sem preço (promo/cupom) não é ofertado
        out.append({
            "tier": t.get("tier"),
            "lote": t.get("lot_name"),
            "preco": _fmt_price(int(cents)),
            "preco_cents": int(cents),
            "prazo_lote": t.get("lot_deadline"),
        })
    return out


async def _load(db: AsyncSession, slug: str) -> Optional[AgentProduct]:
    res = await db.execute(
        select(AgentProduct).where(AgentProduct.slug == slug, AgentProduct.is_active.is_(True))
    )
    return res.scalar_one_or_none()


async def _load_all(db: AsyncSession) -> list[AgentProduct]:
    res = await db.execute(
        select(AgentProduct).where(AgentProduct.is_active.is_(True)).order_by(AgentProduct.slug)
    )
    return list(res.scalars().all())


def build_read_tool_schemas(slugs: list[str]) -> list[dict]:
    slug_schema = {"type": "string", "description": "slug do congresso"}
    if slugs:
        slug_schema["enum"] = slugs
    return [
        {
            "type": "function",
            "name": "list_products",
            "description": "Lista os congressos disponíveis (nome, slug e datas). Use quando não souber qual congresso a pessoa quer.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
            "strict": True,
        },
        {
            "type": "function",
            "name": "get_product_info",
            "description": "Retorna preços dos lotes ativos, prazo do lote, link de checkout e políticas (certificado, pagamento, reembolso, estudante) de UM congresso. Chame SEMPRE antes de citar qualquer valor, data ou link.",
            "parameters": {
                "type": "object",
                "properties": {"product_slug": slug_schema},
                "required": ["product_slug"],
                "additionalProperties": False,
            },
            "strict": True,
        },
        {
            "type": "function",
            "name": "get_event_schedule",
            "description": "Retorna a programação do congresso (por dia, se informado).",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_slug": slug_schema,
                    "day": {"type": ["string", "null"], "description": "dia específico, opcional"},
                },
                "required": ["product_slug", "day"],
                "additionalProperties": False,
            },
            "strict": True,
        },
        {
            "type": "function",
            "name": "get_faq_answer",
            "description": "Busca uma resposta oficial na FAQ do congresso por tópico/palavra-chave (ex.: certificado, reembolso, estudante, submissão, pagamento).",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_slug": slug_schema,
                    "topic": {"type": "string", "description": "tópico ou palavra-chave da dúvida"},
                },
                "required": ["product_slug", "topic"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    ]


async def execute_tool(name: str, args: dict[str, Any], ctx: ToolContext) -> dict:
    if name == "list_products":
        prods = await _load_all(ctx.db)
        return {"produtos": [
            {"slug": p.slug, "name": p.name, "datas": p.event_dates} for p in prods
        ]}

    if name == "get_product_info":
        p = await _load(ctx.db, args.get("product_slug", ""))
        if p is None:
            return {"erro": "produto não encontrado", "slug": args.get("product_slug")}
        return {
            "slug": p.slug,
            "name": p.name,
            "datas": p.event_dates,
            "checkout_url": p.checkout_url,
            "lotes_ativos": _active_tickets(p),
            "politicas": p.policies or {},
        }

    if name == "get_event_schedule":
        p = await _load(ctx.db, args.get("product_slug", ""))
        if p is None:
            return {"erro": "produto não encontrado"}
        sched = p.schedule or []
        if not sched:
            return {
                "slug": p.slug,
                "programacao": [],
                "aviso": "Programação detalhada ainda não disponível na base; oriente a pessoa a consultar a página oficial ou ofereça chamar a equipe.",
                "horario_geral": (p.policies or {}).get("horario"),
            }
        day = args.get("day")
        if day:
            sched = [s for s in sched if str(s.get("dia", "")).find(day) >= 0]
        return {"slug": p.slug, "programacao": sched}

    if name == "get_faq_answer":
        p = await _load(ctx.db, args.get("product_slug", ""))
        if p is None:
            return {"erro": "produto não encontrado"}
        topic = (args.get("topic") or "").lower()
        faq = p.faq or []
        hits = [f for f in faq if topic in (f.get("q", "") + " " + f.get("a", "")).lower()]
        # também expõe políticas relevantes como fallback
        pol = p.policies or {}
        pol_hits = {k: v for k, v in pol.items() if topic and topic in (k + " " + str(v)).lower()}
        return {
            "slug": p.slug,
            "faq": hits[:4] or faq[:4],
            "politicas_relacionadas": pol_hits,
        }

    return {"erro": f"tool desconhecida: {name}"}
