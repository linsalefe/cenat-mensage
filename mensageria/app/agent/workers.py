"""Workers de background do agente (Fase 3), disparados pelo lifespan.

- sync (30min): atualiza agent_products.tickets a partir de /lotes da Doity.
  Roda SEMPRE (read-only + write interno; zero efeito externo).
- conversão (5min): casa participantes pagos da Doity com contatos → lead ganho,
  CAPI, cancela follow-ups, agenda boas-vindas. GATED por agent_enabled.
- follow-ups (60s): processa AgentFollowup vencidos (janela 24h / opt-out /
  cadência). GATED por agent_enabled — envia WhatsApp só com o agente ativo.

Gating: enquanto NENHUM canal tiver agent_enabled=True, conversão e follow-up
ficam dormentes (nenhum efeito externo). Ver PLANO_AGENTE.md §0.2 / rollout."""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, update

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models import (
    AgentFollowup, AgentProduct, AgentSession, Channel, Contact,
)
from app.agent.doity import DoityClient, DoityError

settings = get_settings()
SP_TZ = timezone(timedelta(hours=-3))

POLL_SYNC = 1800
POLL_CONV = 300
POLL_FU = 60


def _now_sp() -> datetime:
    return datetime.now(SP_TZ).replace(tzinfo=None)


# --------------------------------------------------------------------------- #
# helpers de match de telefone (mesma lógica best-effort BR do payments)
# --------------------------------------------------------------------------- #
def _digits(s: Optional[str]) -> str:
    return re.sub(r"\D", "", s or "")


async def _find_contact(db, phone: str) -> Optional[Contact]:
    d = _digits(phone)
    if not d:
        return None
    cands = {d}
    if not d.startswith("55"):
        cands.add("55" + d)
    if len(d) >= 12 and d.startswith("55"):
        cands.add(d[:4] + d[5:] if len(d) == 13 else d[:4] + "9" + d[4:])
    for wa in cands:
        c = (await db.execute(select(Contact).where(Contact.wa_id == wa))).scalar_one_or_none()
        if c:
            return c
    return None


async def _agent_enabled_anywhere(db) -> bool:
    return bool((await db.execute(
        select(Channel.id).where(Channel.agent_enabled.is_(True)).limit(1)
    )).first())


def _tier_from_name(nome: str) -> str:
    n = (nome or "").lower()
    if "estudante" in n:
        return "estudante"
    if "profissional" in n:
        return "profissional"
    if "combo" in n:
        return "combo"
    return "outro"


def _tickets_from_lotes(lotes: list[dict], old_tickets: list[dict]) -> list[dict]:
    old_by_id = {t.get("doity_lote_id"): t for t in (old_tickets or [])}
    out = []
    for lo in lotes:
        valor = lo.get("valor")
        if valor is None:
            continue  # lote sem preço (promo/cupom) não é ofertado
        lid = lo.get("id")
        out.append({
            "tier": _tier_from_name(lo.get("nome")),
            "lot_name": lo.get("nome"),
            "price_cents": int(round(float(valor) * 100)),
            # a API traz termino=null → preserva o prazo já semeado
            "lot_deadline": (old_by_id.get(lid) or {}).get("lot_deadline"),
            "doity_lote_id": lid,
            "active": bool(lo.get("ativo")),
        })
    return out


# --------------------------------------------------------------------------- #
# SYNC de produtos (sempre)
# --------------------------------------------------------------------------- #
async def sync_products_once() -> None:
    async with AsyncSessionLocal() as db:
        prods = (await db.execute(
            select(AgentProduct).where(
                AgentProduct.doity_event_id.isnot(None), AgentProduct.is_active.is_(True)
            )
        )).scalars().all()
        client = DoityClient()
        for p in prods:
            try:
                lotes = await client.get_lotes(p.doity_event_id)
            except DoityError as e:
                print(f"🤖🔄 sync {p.slug}: Doity {e.status} — pulando", flush=True)
                continue
            new_tickets = _tickets_from_lotes(lotes, p.tickets)
            if new_tickets and new_tickets != (p.tickets or []):
                p.tickets = new_tickets
                p.version = (p.version or 1) + 1
                print(f"🤖🔄 sync {p.slug}: tickets atualizados → v{p.version}", flush=True)
            p.synced_from_doity_at = datetime.now(SP_TZ)
        await db.commit()


async def start_agent_sync_worker() -> None:
    print(f"🤖🔄 Agent sync worker started (poll={POLL_SYNC}s)", flush=True)
    while True:
        try:
            await sync_products_once()
        except Exception as e:
            print(f"🤖🔄 sync loop erro: {e!r}", flush=True)
        await asyncio.sleep(POLL_SYNC)


# --------------------------------------------------------------------------- #
# CONVERSÃO por polling (gated)
# --------------------------------------------------------------------------- #
def _extract_phone(part: dict) -> Optional[str]:
    compra = part.get("compra") or {}
    comp = compra.get("comprador") or {}
    tel = comp.get("telefone")
    if tel:
        return tel
    for it in (part.get("valores_campos_personalizados") or []):
        campo = (it.get("campo_personalizado") or {}).get("nome", "").lower()
        if any(k in campo for k in ("whats", "telefone", "confirmação", "confirmacao")):
            v = (it.get("valor") or "").strip()
            if v:
                return v
    return None


async def poll_conversions_once() -> None:
    async with AsyncSessionLocal() as db:
        if not await _agent_enabled_anywhere(db):
            return
        prods = (await db.execute(
            select(AgentProduct).where(AgentProduct.doity_event_id.isnot(None))
        )).scalars().all()
        client = DoityClient()
        for p in prods:
            since = p.conv_synced_at or (datetime.now(SP_TZ) - timedelta(days=3))
            cursor = since.astimezone(SP_TZ).strftime("%Y-%m-%d %H:%M:%S")
            try:
                data = await client.get_participantes(p.doity_event_id, data_atualizacao=cursor)
            except DoityError as e:
                if e.status == 500:  # sort=modified às vezes 500 → tenta sem sort
                    try:
                        data = await client.get_participantes(
                            p.doity_event_id, data_atualizacao=cursor, sort="id"
                        )
                    except DoityError:
                        continue
                else:
                    continue
            for part in (data.get("participantes") or []):
                if part.get("pago") is not True:
                    continue
                phone = _extract_phone(part)
                if not phone:
                    continue
                contact = await _find_contact(db, phone)
                if contact is None or contact.lead_status == "ganho":
                    continue
                await _convert(db, contact, p, part)
            p.conv_synced_at = datetime.now(SP_TZ)
        await db.commit()


async def _convert(db, contact: Contact, product: AgentProduct, part: dict) -> None:
    from app.meta.conversions import fire_conversion

    # cancela follow-ups pendentes do contato
    await db.execute(
        update(AgentFollowup)
        .where(AgentFollowup.contact_wa_id == contact.wa_id, AgentFollowup.status == "pending")
        .values(status="cancelled")
    )
    contact.lead_status = "ganho"
    sess = (await db.execute(
        select(AgentSession).where(AgentSession.contact_wa_id == contact.wa_id)
        .order_by(AgentSession.id.desc())
    )).scalars().first()
    if sess and sess.status in ("active", "waiting"):
        sess.status = "converted"

    value = part.get("valor_pago")
    try:
        await fire_conversion(
            db, contact_wa_id=contact.wa_id, ctwa_clid=contact.ctwa_clid,
            channel_id=contact.channel_id, event_name="Purchase",
            value=float(value) if value is not None else None,
        )
    except Exception as e:
        print(f"🤖💰 fire_conversion falhou ({contact.wa_id}): {e!r}", flush=True)

    # boas-vindas (utility legítimo) — enviada pelo worker de follow-ups
    db.add(AgentFollowup(
        session_id=sess.id if sess else None,
        contact_wa_id=contact.wa_id,
        run_at=datetime.now(SP_TZ),
        kind="welcome",
        payload={"product_slug": product.slug, "product_name": product.name},
        status="pending",
    ))
    print(f"🤖💰 conversão: {contact.wa_id} → {product.slug} (ganho)", flush=True)


async def start_agent_conversion_worker() -> None:
    print(f"🤖💰 Agent conversion worker started (poll={POLL_CONV}s)", flush=True)
    while True:
        try:
            await poll_conversions_once()
        except Exception as e:
            print(f"🤖💰 conversion loop erro: {e!r}", flush=True)
        await asyncio.sleep(POLL_CONV)


# --------------------------------------------------------------------------- #
# FOLLOW-UPS (gated)
# --------------------------------------------------------------------------- #
async def _gen_followup_text(db, contact: Contact, product: Optional[AgentProduct], fu: AgentFollowup) -> str:
    """Gera 1–3 linhas de WhatsApp para o follow-up (dentro da janela 24h)."""
    from app.agent.loop import get_client

    ctx_lines = []
    if product:
        ctx_lines.append(f"Congresso: {product.name} ({product.event_dates}).")
        ctx_lines.append(f"Link de inscrição: {product.checkout_url}")
        for t in (product.tickets or []):
            if t.get("active") and t.get("price_cents") is not None:
                ctx_lines.append(f"- {t.get('tier')}: R$ {int(t['price_cents'])//100} (lote {t.get('lot_name')}, prazo {t.get('lot_deadline')})")
    motivo = (fu.payload or {}).get("motivo", "")
    kind = fu.kind
    if kind == "welcome":
        instr = "Escreva uma mensagem curta e calorosa CONFIRMANDO a inscrição da pessoa no congresso e dizendo que em breve chegam as orientações de acesso. Sem vender nada."
    elif kind == "lot_deadline":
        instr = "Escreva um lembrete curto e gentil de que o 1º lote (mais barato) está para encerrar, com o link. Sem pressão agressiva."
    else:
        instr = "Escreva uma retomada curta e gentil da conversa, se colocando à disposição, com o link se fizer sentido."
    try:
        resp = await get_client().responses.create(
            model=settings.OPENAI_MODEL_MAIN,
            instructions="Você é a assistente do CENAT no WhatsApp. pt-BR, 1 a 3 linhas, tom humano, sem markdown pesado. Use SOMENTE os dados fornecidos (não invente preço/data/link). " + instr,
            input="Contexto:\n" + "\n".join(ctx_lines) + (f"\nMotivo do follow-up: {motivo}" if motivo else ""),
            store=False, max_output_tokens=250,
        )
        return (getattr(resp, "output_text", "") or "").strip() or "Oi! Passando pra saber se posso te ajudar com a sua inscrição 😊"
    except Exception as e:
        print(f"🤖📩 gen followup falhou: {e!r}", flush=True)
        return "Oi! Passando pra saber se posso te ajudar com a sua inscrição no congresso 😊"


async def process_followups_once() -> None:
    from app.messaging.persistence import persist_outbound_message
    from app.messaging.provider import get_provider

    async with AsyncSessionLocal() as db:
        if not await _agent_enabled_anywhere(db):
            return
        now = _now_sp()
        due = (await db.execute(
            select(AgentFollowup)
            .where(AgentFollowup.status == "pending", AgentFollowup.run_at <= datetime.now(SP_TZ))
            .order_by(AgentFollowup.run_at.asc()).limit(20)
        )).scalars().all()
        if not due:
            return

        for fu in due:
            contact = (await db.execute(
                select(Contact).where(Contact.wa_id == fu.contact_wa_id)
            )).scalar_one_or_none()
            if contact is None or contact.opted_out:
                fu.status = "cancelled"
                continue
            sess = (await db.execute(
                select(AgentSession).where(AgentSession.contact_wa_id == fu.contact_wa_id)
                .order_by(AgentSession.id.desc())
            )).scalars().first()
            if sess and sess.status == "handed_off":
                fu.status = "cancelled"
                continue
            if contact.lead_status == "ganho" and fu.kind != "welcome":
                fu.status = "cancelled"
                continue

            channel = await db.get(Channel, contact.channel_id) if contact.channel_id else None
            if channel is None or not channel.agent_enabled:
                fu.status = "skipped"
                continue

            slug = (fu.payload or {}).get("product_slug") or (sess.product_slug if sess else None)
            product = None
            if slug:
                product = (await db.execute(
                    select(AgentProduct).where(AgentProduct.slug == slug)
                )).scalar_one_or_none()

            # janela 24h: dentro → texto livre (grátis); fora → template utility
            within24 = bool(contact.last_inbound_at and (now - contact.last_inbound_at) < timedelta(hours=24))
            if within24 or fu.kind == "welcome":
                text = await _gen_followup_text(db, contact, product, fu)
                ok = await _send_text(db, channel, contact.wa_id, text)
                fu.status = "sent" if ok else "skipped"
            else:
                ok = await _send_template_followup(db, channel, contact, product, fu)
                fu.status = "sent" if ok else "skipped"

        await db.commit()


async def _send_text(db, channel: Channel, wa_id: str, text: str) -> bool:
    from app.messaging.persistence import persist_outbound_message
    from app.messaging.provider import get_provider
    try:
        result = await get_provider(channel).send_text(channel, wa_id, text)
        await persist_outbound_message(db=db, channel=channel, to=wa_id,
                                       message_type="text", content=text,
                                       send_result=result, sent_by_ai=True)
        return True
    except Exception as e:
        print(f"🤖📩 envio follow-up falhou ({wa_id}): {e!r}", flush=True)
        await persist_outbound_message(db=db, channel=channel, to=wa_id,
                                       message_type="text", content=text,
                                       status="failed", sent_by_ai=True)
        return False


async def _send_template_followup(db, channel: Channel, contact: Contact,
                                  product: Optional[AgentProduct], fu: AgentFollowup) -> bool:
    """Fora da janela 24h → SÓ template utility aprovado. Os templates
    `lembrete_lote`/`retomada_conversa` precisam ser criados e aprovados no WABA
    (pendência externa — ver PLANO_AGENTE.md §5.3). Enquanto não existirem, este
    envio falha e o follow-up é marcado 'skipped' (erro 131049/131050 tratados)."""
    from app.messaging.persistence import persist_outbound_message
    from app.messaging.provider import get_provider

    template = "lembrete_lote" if fu.kind == "lot_deadline" else "retomada_conversa"
    pname = (product.name if product else "o congresso")
    deadline = ""
    if product:
        for t in (product.tickets or []):
            if t.get("lot_deadline"):
                deadline = t["lot_deadline"]
                break
    components = [{"type": "body", "parameters": [
        {"type": "text", "text": pname}, {"type": "text", "text": deadline or "em breve"},
    ]}]
    try:
        result = await get_provider(channel).send_template(
            channel, contact.wa_id, template, "pt_BR", components
        )
        await persist_outbound_message(db=db, channel=channel, to=contact.wa_id,
                                       message_type="text",
                                       content=f"[template:{template}]",
                                       send_result=result, sent_by_ai=True)
        return True
    except Exception as e:
        msg = str(e)
        if "131050" in msg:  # opt-out permanente
            contact.opted_out = True
            print(f"🤖📩 131050 opt-out ({contact.wa_id})", flush=True)
        elif "131049" in msg:  # saturação — reagenda +24h
            fu.status = "pending"
            fu.run_at = datetime.now(SP_TZ) + timedelta(hours=24)
            print(f"🤖📩 131049 saturação, reagenda +24h ({contact.wa_id})", flush=True)
            return False
        print(f"🤖📩 template follow-up indisponível ({template}): {e!r}", flush=True)
        return False


async def start_agent_followup_worker() -> None:
    print(f"🤖📩 Agent follow-up worker started (poll={POLL_FU}s)", flush=True)
    while True:
        try:
            await process_followups_once()
        except Exception as e:
            print(f"🤖📩 followup loop erro: {e!r}", flush=True)
        await asyncio.sleep(POLL_FU)
