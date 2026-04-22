"""Rotas de contatos e mensagens (leitura — usado pelo frontend)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_, select

from app.auth import get_current_user
from app.deps import DbSession
from app.models import Channel, Contact, Message

router = APIRouter(
    prefix="/api/contacts",
    tags=["Contacts"],
    dependencies=[Depends(get_current_user)],
)


def _contact_to_dict(c: Contact, channel_map: dict[int, str]) -> dict:
    return {
        "id": c.id,
        "wa_id": c.wa_id,
        "name": c.name,
        "lead_status": c.lead_status,
        "last_inbound_at": c.last_inbound_at.isoformat() if c.last_inbound_at else None,
        "channel_id": c.channel_id,
        "channel_name": channel_map.get(c.channel_id) if c.channel_id else None,
        "is_group": c.is_group,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


@router.get("")
async def list_contacts(
    db: DbSession,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    limit = max(1, min(limit, 200))
    offset = max(0, offset)

    q = select(Contact)
    if search:
        like = f"%{search}%"
        q = q.where(or_(Contact.wa_id.ilike(like), Contact.name.ilike(like)))
    q = q.order_by(
        Contact.last_inbound_at.desc().nullslast(),
        Contact.updated_at.desc().nullslast(),
    ).limit(limit).offset(offset)

    count_q = select(func.count(Contact.id))
    if search:
        like = f"%{search}%"
        count_q = count_q.where(or_(Contact.wa_id.ilike(like), Contact.name.ilike(like)))
    total = (await db.execute(count_q)).scalar_one()

    res = await db.execute(q)
    contacts = res.scalars().all()

    channel_ids = {c.channel_id for c in contacts if c.channel_id}
    channel_map: dict[int, str] = {}
    if channel_ids:
        chres = await db.execute(select(Channel).where(Channel.id.in_(channel_ids)))
        channel_map = {ch.id: ch.name for ch in chres.scalars().all()}

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [_contact_to_dict(c, channel_map) for c in contacts],
    }


@router.get("/{contact_id}")
async def get_contact(contact_id: int, db: DbSession):
    res = await db.execute(select(Contact).where(Contact.id == contact_id))
    contact = res.scalar_one_or_none()
    if not contact:
        raise HTTPException(404, "Contato não encontrado")

    channel_name = None
    if contact.channel_id:
        chres = await db.execute(select(Channel).where(Channel.id == contact.channel_id))
        ch = chres.scalar_one_or_none()
        channel_name = ch.name if ch else None

    return _contact_to_dict(contact, {contact.channel_id: channel_name} if contact.channel_id else {})


@router.get("/{contact_id}/messages")
async def get_contact_messages(contact_id: int, db: DbSession, limit: int = 50):
    limit = max(1, min(limit, 200))
    contact_res = await db.execute(select(Contact).where(Contact.id == contact_id))
    contact = contact_res.scalar_one_or_none()
    if not contact:
        raise HTTPException(404, "Contato não encontrado")

    q = (
        select(Message)
        .where(Message.contact_wa_id == contact.wa_id)
        .order_by(Message.timestamp.desc())
        .limit(limit)
    )
    res = await db.execute(q)
    messages = list(res.scalars().all())
    messages.reverse()  # retorno em ordem cronológica crescente

    return [
        {
            "id": m.id,
            "wa_message_id": m.wa_message_id,
            "contact_wa_id": m.contact_wa_id,
            "channel_id": m.channel_id,
            "direction": m.direction,
            "message_type": m.message_type,
            "content": m.content,
            "timestamp": m.timestamp.isoformat() if m.timestamp else None,
            "status": m.status,
            "sent_by_ai": m.sent_by_ai,
            "sender_name": m.sender_name,
        }
        for m in messages
    ]
