from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.messaging.types import SendResult
from app.models import Channel, Contact, Message

SP_TZ = timezone(timedelta(hours=-3))


def _normalize_wa_id(to: str) -> str:
    return to.replace("+", "").replace("-", "").replace(" ", "").replace("(", "").replace(")", "")


async def persist_outbound_message(
    db: AsyncSession,
    channel: Channel,
    to: str,
    message_type: str,
    content: Optional[str],
    send_result: Optional[SendResult] = None,
    sent_by_ai: bool = False,
    status: str = "sent",
) -> Message:
    """Persiste uma mensagem de saída no chat.

    Use com ``send_result`` quando a Meta aceitou o envio (``status='sent'``).
    Para registrar uma falha de envio (ex.: Meta rejeitou o template/disparo),
    chame com ``status='failed'`` e ``send_result=None`` — assim a mensagem ainda
    aparece na conversa, com o wa_message_id sintético ``failed_<uuid>``.
    """
    wa_id = _normalize_wa_id(to)
    now = datetime.now(SP_TZ).replace(tzinfo=None)

    contact_result = await db.execute(select(Contact).where(Contact.wa_id == wa_id))
    contact = contact_result.scalar_one_or_none()
    if contact is None:
        contact = Contact(
            wa_id=wa_id,
            name=wa_id,
            channel_id=channel.id,
            lead_status="novo",
            ai_active=False,
            reengagement_count=0,
            is_group=False,
        )
        db.add(contact)
        await db.flush()
    else:
        # Traz a conversa para o topo da lista (ordenada por updated_at) mesmo
        # quando o contato só recebe mensagens de saída (disparo/template).
        contact.updated_at = now

    wa_message_id = (
        send_result.wa_message_id if send_result and send_result.wa_message_id
        else f"failed_{uuid.uuid4().hex}"
    )

    existing = await db.execute(
        select(Message).where(Message.wa_message_id == wa_message_id)
    )
    msg = existing.scalar_one_or_none()
    if msg is not None:
        return msg

    msg = Message(
        wa_message_id=wa_message_id,
        contact_wa_id=wa_id,
        channel_id=channel.id,
        direction="outbound",
        message_type=message_type,
        content=content,
        timestamp=now,
        status=status,
        sent_by_ai=sent_by_ai,
    )
    db.add(msg)
    await db.flush()
    return msg
