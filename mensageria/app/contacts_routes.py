"""Rotas de contatos e mensagens (leitura + CRM do inbox)."""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.auth import get_current_user
from app.deps import DbSession
from app.models import Channel, Contact, ContactTag, Message, User, contact_tag_links

router = APIRouter(
    prefix="/api/contacts",
    tags=["Contacts"],
    dependencies=[Depends(get_current_user)],
)

# Message.timestamp é gravado naive em horário de São Paulo por todos os canais
# (meta/parser.py, evolution/routes.py, messaging/persistence.py). last_read_at
# segue a mesma convenção para que a comparação de não-lidas seja naive vs naive.
SP_TZ = timezone(timedelta(hours=-3))


def _now_sp_naive() -> datetime:
    return datetime.now(SP_TZ).replace(tzinfo=None)


def _contact_to_dict(
    c: Contact, channel_map: dict[int, str], unread: int = 0
) -> dict:
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
        "notes": c.notes,
        "ai_active": c.ai_active,
        "assigned_to": c.assigned_to,
        "tags": [
            {"id": t.id, "name": t.name, "color": t.color} for t in (c.tags or [])
        ],
        "unread": unread,
    }


def _unread_subquery():
    """Não lidas por contato: inbound mais recente que o marco de leitura.

    Uma única query agregada — nada de contar mensagem por contato no laço.
    """
    return (
        select(
            Message.contact_wa_id.label("wa_id"),
            func.count(Message.id).label("unread"),
        )
        .join(Contact, Contact.wa_id == Message.contact_wa_id)
        .where(
            Message.direction == "inbound",
            or_(
                Contact.last_read_at.is_(None),
                Message.timestamp > Contact.last_read_at,
            ),
        )
        .group_by(Message.contact_wa_id)
        .subquery()
    )


@router.get("")
async def list_contacts(
    db: DbSession,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    limit = max(1, min(limit, 200))
    offset = max(0, offset)

    unread_sq = _unread_subquery()
    q = select(Contact, func.coalesce(unread_sq.c.unread, 0).label("unread")).outerjoin(
        unread_sq, unread_sq.c.wa_id == Contact.wa_id
    )
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

    rows = (await db.execute(q)).all()

    channel_ids = {c.channel_id for c, _ in rows if c.channel_id}
    channel_map: dict[int, str] = {}
    if channel_ids:
        chres = await db.execute(select(Channel).where(Channel.id.in_(channel_ids)))
        channel_map = {ch.id: ch.name for ch in chres.scalars().all()}

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [_contact_to_dict(c, channel_map, unread) for c, unread in rows],
    }


class ContactCreate(BaseModel):
    wa_id: str = Field(..., min_length=4, max_length=100)
    name: Optional[str] = Field(default=None, max_length=255)
    channel_id: Optional[int] = None


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_contact(data: ContactCreate, db: DbSession):
    """Cria o contato ou devolve o existente (upsert por wa_id).

    Usado pelo "novo chat" do inbox: começar uma conversa com quem ainda não
    escreveu. Idempotente de propósito — abrir o mesmo número duas vezes não
    pode gerar contato duplicado (wa_id é unique e alvo da FK de messages).
    """
    wa_id = data.wa_id.strip()
    if not wa_id:
        raise HTTPException(422, "wa_id não pode ser vazio")

    existing = (
        await db.execute(select(Contact).where(Contact.wa_id == wa_id))
    ).scalar_one_or_none()
    if existing:
        channel_name = None
        if existing.channel_id:
            ch = await db.get(Channel, existing.channel_id)
            channel_name = ch.name if ch else None
        return _contact_to_dict(
            existing, {existing.channel_id: channel_name} if existing.channel_id else {}
        )

    if data.channel_id is not None and not await db.get(Channel, data.channel_id):
        raise HTTPException(404, "Canal não encontrado")

    contact = Contact(
        wa_id=wa_id,
        name=data.name or wa_id,
        channel_id=data.channel_id,
        lead_status="novo",
        ai_active=False,
        reengagement_count=0,
        is_group=False,
    )
    db.add(contact)
    await db.commit()
    await db.refresh(contact)

    channel_name = None
    if contact.channel_id:
        ch = await db.get(Channel, contact.channel_id)
        channel_name = ch.name if ch else None
    return _contact_to_dict(
        contact, {contact.channel_id: channel_name} if contact.channel_id else {}
    )


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

    return _contact_to_dict(
        contact, {contact.channel_id: channel_name} if contact.channel_id else {}
    )


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


class ContactPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    notes: Optional[str] = None
    ai_active: Optional[bool] = None
    assigned_to: Optional[int] = None  # null explícito desatribui o SDR


@router.patch("/{contact_id}")
async def patch_contact(contact_id: int, data: ContactPatch, db: DbSession):
    contact = await db.get(Contact, contact_id)
    if not contact:
        raise HTTPException(404, "Contato não encontrado")

    # exclude_unset distingue "não enviou o campo" de "enviou null": só o segundo
    # limpa notes/assigned_to.
    fields = data.model_dump(exclude_unset=True)

    if fields.get("assigned_to") is not None:
        user = await db.get(User, fields["assigned_to"])
        if not user:
            raise HTTPException(404, "Usuário responsável não encontrado")

    for key, value in fields.items():
        setattr(contact, key, value)

    await db.commit()
    await db.refresh(contact)

    channel_name = None
    if contact.channel_id:
        ch = await db.get(Channel, contact.channel_id)
        channel_name = ch.name if ch else None
    return _contact_to_dict(
        contact, {contact.channel_id: channel_name} if contact.channel_id else {}
    )


@router.post("/{contact_id}/mark-read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_read(contact_id: int, db: DbSession):
    contact = await db.get(Contact, contact_id)
    if not contact:
        raise HTTPException(404, "Contato não encontrado")
    contact.last_read_at = _now_sp_naive()
    await db.commit()


@router.post("/{contact_id}/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def add_tag(contact_id: int, tag_id: int, db: DbSession):
    contact = await db.get(Contact, contact_id)
    tag = await db.get(ContactTag, tag_id)
    if not contact or not tag:
        raise HTTPException(404, "Contato ou tag não encontrado")

    # Clicar duas vezes não deve estourar violação de PK.
    stmt = (
        pg_insert(contact_tag_links)
        .values(contact_id=contact_id, tag_id=tag_id)
        .on_conflict_do_nothing()
    )
    await db.execute(stmt)
    await db.commit()


@router.delete("/{contact_id}/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_tag(contact_id: int, tag_id: int, db: DbSession):
    await db.execute(
        delete(contact_tag_links).where(
            contact_tag_links.c.contact_id == contact_id,
            contact_tag_links.c.tag_id == tag_id,
        )
    )
    await db.commit()
