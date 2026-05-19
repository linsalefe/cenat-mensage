from __future__ import annotations

import hashlib
import hmac
import json
from datetime import timedelta, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import select, update

from app.auth import get_current_user
from app.config import get_settings
from app.deps import DbSession
from app.meta import client as meta_client
from app.meta.parser import parse_inbound_messages, parse_statuses
from app.meta.schemas import (
    ChannelCreateMeta,
    ChannelOutMeta,
    ChannelUpdateMeta,
    SendTemplateRequest,
    SendTextRequest,
)
from app.models import Channel, Contact, Message

_settings = get_settings()
SP_TZ = timezone(timedelta(hours=-3))

STATUS_ORDER = {"received": 0, "sent": 1, "delivered": 2, "read": 3, "failed": 99}


router = APIRouter(
    prefix="/api/meta",
    tags=["Meta API"],
    dependencies=[Depends(get_current_user)],
)
webhook_router = APIRouter(prefix="/api/meta", tags=["Meta Webhook"])


@webhook_router.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(..., alias="hub.mode"),
    hub_verify_token: str = Query(..., alias="hub.verify_token"),
    hub_challenge: str = Query(..., alias="hub.challenge"),
):
    if not _settings.META_WEBHOOK_VERIFY_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Meta webhook verify token not configured",
        )

    if hub_mode != "subscribe":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid hub.mode")

    if not hmac.compare_digest(hub_verify_token, _settings.META_WEBHOOK_VERIFY_TOKEN):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid verify token")

    return PlainTextResponse(content=hub_challenge, status_code=200)


@webhook_router.post("/webhook")
async def receive_webhook(request: Request, db: DbSession):
    if not _settings.META_APP_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Meta app secret not configured",
        )

    raw_body = await request.body()
    signature_header = request.headers.get("X-Hub-Signature-256", "")
    if not signature_header.startswith("sha256="):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="missing signature")

    received_sig = signature_header.removeprefix("sha256=")
    expected_sig = hmac.new(
        _settings.META_APP_SECRET.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(received_sig, expected_sig):
        print("⚠️ Meta webhook: assinatura inválida", flush=True)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid signature")

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        print(f"⚠️ Meta webhook: JSON inválido: {raw_body[:200]!r}", flush=True)
        return {"status": "ok"}

    try:
        await _process_inbound(payload, db)
    except Exception as exc:
        print(f"❌ Meta webhook: erro ao processar inbound: {exc.__class__.__name__}: {exc}", flush=True)

    try:
        await _process_statuses(payload, db)
    except Exception as exc:
        print(f"❌ Meta webhook: erro ao processar statuses: {exc.__class__.__name__}: {exc}", flush=True)

    return {"status": "ok"}


async def _resolve_channel(db, phone_number_id: Optional[str]) -> Optional[Channel]:
    if not phone_number_id:
        return None
    result = await db.execute(
        select(Channel).where(
            Channel.phone_number_id == phone_number_id,
            Channel.provider == "official",
        )
    )
    return result.scalar_one_or_none()


async def _process_inbound(payload, db):
    messages = parse_inbound_messages(payload)
    if not messages:
        return

    for parsed in messages:
        channel = await _resolve_channel(db, parsed.get("phone_number_id"))
        if channel is None:
            print(f"⚠️ Meta inbound: canal não encontrado para phone_number_id={parsed.get('phone_number_id')}", flush=True)
            continue

        wa_id = parsed["wa_id"]
        wa_message_id = parsed["wa_message_id"]
        msg_time = parsed["timestamp"]

        existing = await db.execute(
            select(Message).where(Message.wa_message_id == wa_message_id)
        )
        if existing.scalar_one_or_none():
            continue

        contact_result = await db.execute(select(Contact).where(Contact.wa_id == wa_id))
        contact = contact_result.scalar_one_or_none()
        if contact is None:
            contact = Contact(
                wa_id=wa_id,
                name=parsed.get("contact_name") or wa_id,
                channel_id=channel.id,
                lead_status="novo",
                ai_active=True,
                last_inbound_at=msg_time,
                reengagement_count=0,
                is_group=False,
            )
            db.add(contact)
            await db.flush()
            print(f"👤 Meta novo contato: {contact.name} ({wa_id})", flush=True)
        else:
            contact.last_inbound_at = msg_time
            contact.reengagement_count = 0

        message_type = parsed["message_type"]
        content = parsed.get("content")

        media = parsed.get("media")
        if media and parsed["raw_type"] in ("image", "audio", "video", "document", "sticker"):
            media_id = media.get("media_id")
            mime = media.get("mime_type", "")
            caption = media.get("caption", "")
            if media_id and channel.whatsapp_token:
                downloaded = await meta_client.download_media(
                    media_id, channel.whatsapp_token, _settings.MEDIA_DIR
                )
                if downloaded:
                    content = f"local:{downloaded['filename']}|{downloaded['mime']}|{caption}"
                else:
                    content = f"[{message_type}]"
            else:
                content = f"[{message_type}]"

        new_msg = Message(
            wa_message_id=wa_message_id,
            contact_wa_id=wa_id,
            channel_id=channel.id,
            direction="inbound",
            message_type=message_type,
            content=content,
            timestamp=msg_time,
            status="received",
            sender_name=parsed.get("contact_name"),
        )
        db.add(new_msg)

        print(f"📥 Meta [{channel.name}] {wa_id}: {(content or '')[:100]}", flush=True)

    await db.commit()


async def _process_statuses(payload, db):
    statuses = parse_statuses(payload)
    if not statuses:
        return

    for st in statuses:
        wa_message_id = st["wa_message_id"]
        new_status = st["status"]
        new_order = STATUS_ORDER.get(new_status, -1)
        if new_order < 0:
            print(f"⚠️ Meta status: status desconhecido '{new_status}' para {wa_message_id}", flush=True)
            continue

        current_result = await db.execute(
            select(Message.status).where(Message.wa_message_id == wa_message_id)
        )
        current_status = current_result.scalar_one_or_none()
        if current_status is None:
            print(f"📊 Meta status: {wa_message_id} → {new_status} (msg não persistida)", flush=True)
            continue

        current_order = STATUS_ORDER.get(current_status, 0)
        if new_order < current_order:
            print(f"⏭️ Meta status: {wa_message_id} ignorado ({current_status} → {new_status} regrediria)", flush=True)
            continue

        await db.execute(
            update(Message)
            .where(Message.wa_message_id == wa_message_id)
            .values(status=new_status)
        )
        print(f"📊 Meta status: {wa_message_id} {current_status} → {new_status}", flush=True)

    await db.commit()


@router.post("/channels", response_model=ChannelOutMeta, status_code=201)
async def create_channel(payload: ChannelCreateMeta, db: DbSession):
    existing = await db.execute(
        select(Channel).where(Channel.phone_number_id == payload.phone_number_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Channel with phone_number_id already exists")

    channel = Channel(
        name=payload.name,
        phone_number=payload.phone_number,
        phone_number_id=payload.phone_number_id,
        whatsapp_token=payload.whatsapp_token,
        waba_id=payload.waba_id,
        provider="official",
        type="whatsapp",
        is_connected=True,
        is_active=True,
        operation_mode=payload.operation_mode,
    )
    db.add(channel)
    await db.commit()
    await db.refresh(channel)
    return channel


@router.get("/channels", response_model=list[ChannelOutMeta])
async def list_channels(db: DbSession):
    result = await db.execute(
        select(Channel).where(Channel.provider == "official").order_by(Channel.id.asc())
    )
    return list(result.scalars().all())


@router.get("/channels/{channel_id}", response_model=ChannelOutMeta)
async def get_channel(channel_id: int, db: DbSession):
    ch = await db.get(Channel, channel_id)
    if ch is None or ch.provider != "official":
        raise HTTPException(status_code=404, detail="Meta channel not found")
    return ch


@router.get("/channels/{channel_id}/health")
async def channel_health(channel_id: int, db: DbSession):
    ch = await db.get(Channel, channel_id)
    if ch is None or ch.provider != "official":
        raise HTTPException(status_code=404, detail="Meta channel not found")
    if not ch.phone_number_id or not ch.whatsapp_token:
        raise HTTPException(status_code=400, detail="Channel sem phone_number_id ou token")

    url = f"https://graph.facebook.com/{_settings.GRAPH_API_VERSION}/{ch.phone_number_id}"
    params = {
        "fields": "verified_name,display_phone_number,quality_rating,code_verification_status,name_status,platform_type"
    }
    headers = {"Authorization": f"Bearer {ch.whatsapp_token}"}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params=params, headers=headers)
            if resp.status_code != 200:
                return {
                    "channel_id": ch.id,
                    "ok": False,
                    "status_code": resp.status_code,
                    "error": resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text[:500],
                }
            data = resp.json()
    except httpx.HTTPError as exc:
        return {"channel_id": ch.id, "ok": False, "error": str(exc)}

    return {
        "channel_id": ch.id,
        "ok": True,
        "verified_name": data.get("verified_name"),
        "display_phone_number": data.get("display_phone_number"),
        "quality_rating": data.get("quality_rating"),
        "code_verification_status": data.get("code_verification_status"),
        "name_status": data.get("name_status"),
        "platform_type": data.get("platform_type"),
    }


@router.patch("/channels/{channel_id}", response_model=ChannelOutMeta)
async def update_channel(channel_id: int, payload: ChannelUpdateMeta, db: DbSession):
    ch = await db.get(Channel, channel_id)
    if ch is None or ch.provider != "official":
        raise HTTPException(status_code=404, detail="Meta channel not found")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(ch, field, value)
    await db.commit()
    await db.refresh(ch)
    return ch


@router.delete("/channels/{channel_id}", status_code=204)
async def delete_channel(channel_id: int, db: DbSession):
    ch = await db.get(Channel, channel_id)
    if ch is None or ch.provider != "official":
        raise HTTPException(status_code=404, detail="Meta channel not found")
    await db.delete(ch)
    await db.commit()


@router.post("/channels/{channel_id}/send-text")
async def send_text_endpoint(channel_id: int, payload: SendTextRequest, db: DbSession):
    from app.messaging.persistence import persist_outbound_message
    from app.messaging.provider import get_provider

    ch = await db.get(Channel, channel_id)
    if ch is None or ch.provider != "official":
        raise HTTPException(status_code=404, detail="Meta channel not found")
    if not ch.phone_number_id or not ch.whatsapp_token:
        raise HTTPException(status_code=400, detail="Channel sem phone_number_id ou token")

    provider = get_provider(ch)
    result = await provider.send_text(ch, payload.to, payload.text)
    await persist_outbound_message(
        db=db,
        channel=ch,
        to=payload.to,
        message_type="text",
        content=payload.text,
        send_result=result,
    )
    await db.commit()
    return {
        "status": "sent",
        "wa_message_id": result.wa_message_id,
        "graph_response": result.raw_response,
    }


@router.post("/channels/{channel_id}/send-template")
async def send_template_endpoint(channel_id: int, payload: SendTemplateRequest, db: DbSession):
    from app.messaging.persistence import persist_outbound_message
    from app.messaging.provider import get_provider

    ch = await db.get(Channel, channel_id)
    if ch is None or ch.provider != "official":
        raise HTTPException(status_code=404, detail="Meta channel not found")
    if not ch.phone_number_id or not ch.whatsapp_token:
        raise HTTPException(status_code=400, detail="Channel sem phone_number_id ou token")

    provider = get_provider(ch)
    result = await provider.send_template(
        ch,
        payload.to,
        payload.template_name,
        payload.language_code,
        payload.components,
    )

    content_repr = f"[template:{payload.template_name}@{payload.language_code}]"
    await persist_outbound_message(
        db=db,
        channel=ch,
        to=payload.to,
        message_type="template",
        content=content_repr,
        send_result=result,
    )
    await db.commit()
    print(
        f"📤 Template enviado: {payload.template_name}@{payload.language_code} → {payload.to} (wa_message_id={result.wa_message_id})",
        flush=True,
    )
    return {
        "status": "sent",
        "wa_message_id": result.wa_message_id,
        "graph_response": result.raw_response,
    }
