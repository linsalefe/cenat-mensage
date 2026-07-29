"""Entrada do agente a partir do webhook. Debounce por contato, gating de
segurança de 5 condições, idempotência por watermark e envio da resposta.

Roda como background task (asyncio.create_task) disparada pelo webhook Meta —
NUNCA bloqueia o webhook. Em --workers 1, debounce/lock em memória bastam."""
from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models import AgentSession, Channel, Contact, Message

settings = get_settings()
SP_TZ = timezone(timedelta(hours=-3))

_seq: dict[str, int] = defaultdict(int)
_locks: dict[str, asyncio.Lock] = {}


def _lock(wa_id: str) -> asyncio.Lock:
    lk = _locks.get(wa_id)
    if lk is None:
        lk = _locks[wa_id] = asyncio.Lock()
    return lk


def _now() -> datetime:
    return datetime.now(SP_TZ).replace(tzinfo=None)


def _display(m: Message) -> str:
    c = m.content or ""
    if c.startswith("local:"):
        return "[a pessoa enviou um arquivo de mídia]"
    return c


def agent_should_handle(channel: Channel, contact: Contact) -> bool:
    """Gatilho de segurança §0.2 — TODAS as condições. agent_enabled default
    False garante que nenhum canal responde sem ativação explícita."""
    return bool(
        channel
        and channel.agent_enabled
        and channel.operation_mode == "ai"
        and contact
        and contact.ai_active
        and not contact.opted_out
        and not contact.is_group
    )


async def handle_inbound(channel_id: int, wa_id: str, wa_message_id: str, text: str) -> None:
    """Debounce: coalesce rajadas de mensagens. Só o último inbound processa."""
    _seq[wa_id] += 1
    mine = _seq[wa_id]
    try:
        await asyncio.sleep(settings.AGENT_DEBOUNCE_SECONDS)
    except asyncio.CancelledError:
        return
    if _seq.get(wa_id) != mine:
        return  # chegou mensagem mais nova; a task dela cuida do lote
    async with _lock(wa_id):
        try:
            await _process(channel_id, wa_id)
        except Exception as e:  # background task: nunca propaga
            print(f"🤖❌ agent handle_inbound erro ({wa_id}): {e!r}", flush=True)


async def _process(channel_id: int, wa_id: str) -> None:
    from app.agent.loop import run_turn

    async with AsyncSessionLocal() as db:
        channel = await db.get(Channel, channel_id)
        cres = await db.execute(select(Contact).where(Contact.wa_id == wa_id))
        contact = cres.scalar_one_or_none()
        if not agent_should_handle(channel, contact):
            return

        # sessão: reusa ativa/waiting; respeita handoff; recria se fechada/convertida
        sres = await db.execute(
            select(AgentSession)
            .where(AgentSession.contact_wa_id == wa_id)
            .order_by(AgentSession.id.desc())
        )
        session = sres.scalars().first()
        if session and session.status == "handed_off":
            return  # humano assumiu — agente fica em silêncio
        if session is None or session.status in ("converted", "closed"):
            session = AgentSession(contact_wa_id=wa_id, channel_id=channel_id, status="active")
            db.add(session)
            await db.flush()

        # lote: inbound novos desde o watermark (idempotência)
        watermark = session.last_inbound_at or (_now() - timedelta(minutes=2))
        mres = await db.execute(
            select(Message)
            .where(
                Message.contact_wa_id == wa_id,
                Message.direction == "inbound",
                Message.timestamp > watermark,
            )
            .order_by(Message.timestamp.asc())
        )
        inbound = list(mres.scalars().all())
        if not inbound:
            return  # nada novo — evita resposta duplicada em retry do webhook
        user_text = "\n".join(_display(m) for m in inbound).strip()
        session.last_inbound_at = max(m.timestamp for m in inbound)
        if not user_text:
            await db.commit()
            return

        out = await run_turn(db, session, contact, user_text)
        reply = out["reply"]

        await _send(db, channel, wa_id, reply)
        await db.commit()
        print(f"🤖 [{channel.name}] {wa_id}: {reply[:80]}", flush=True)


async def _send(db, channel: Channel, wa_id: str, reply: str) -> None:
    from app.messaging.persistence import persist_outbound_message
    from app.messaging.provider import get_provider

    if channel.provider == "official" and (not channel.phone_number_id or not channel.whatsapp_token):
        print(f"🤖⚠️ canal {channel.id} sem phone_number_id/token — resposta não enviada", flush=True)
        await persist_outbound_message(
            db=db, channel=channel, to=wa_id, message_type="text",
            content=reply, status="failed", sent_by_ai=True,
        )
        return
    provider = get_provider(channel)
    try:
        result = await provider.send_text(channel, wa_id, reply)
        await persist_outbound_message(
            db=db, channel=channel, to=wa_id, message_type="text",
            content=reply, send_result=result, sent_by_ai=True,
        )
    except Exception as e:
        print(f"🤖❌ falha ao enviar ({wa_id}): {e!r}", flush=True)
        await persist_outbound_message(
            db=db, channel=channel, to=wa_id, message_type="text",
            content=reply, status="failed", sent_by_ai=True,
        )
