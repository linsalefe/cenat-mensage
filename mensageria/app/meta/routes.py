from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
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
    MetaTemplateOut,
    SendMediaRequest,
    SendTemplateRequest,
    SendTextRequest,
)
from app.models import Channel, Contact, MediaAsset, Message, MetaTemplate
from app.relay import client as relay
from app.service_auth import get_user_or_service

_settings = get_settings()
SP_TZ = timezone(timedelta(hours=-3))

STATUS_ORDER = {"received": 0, "sent": 1, "delivered": 2, "read": 3, "failed": 99}


router = APIRouter(
    prefix="/api/meta",
    tags=["Meta API"],
    dependencies=[Depends(get_current_user)],
)
webhook_router = APIRouter(prefix="/api/meta", tags=["Meta Webhook"])

# Ponte (Sprint S1): endpoints que o Customer comanda. Aceitam JWT de usuário
# (frontend do Mensage) OU X-Service-Token (Customer). Não quebra o frontend.
bridge_router = APIRouter(
    prefix="/api/meta",
    tags=["Meta Bridge"],
    dependencies=[Depends(get_user_or_service)],
)


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

    # Payloads normalizados pra relayar ao Customer DEPOIS do commit (best-effort).
    relay_payloads: list[dict] = []
    # Inbounds elegíveis ao agente de IA — disparados DEPOIS do commit (não bloqueia).
    agent_jobs: list[tuple] = []

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

        # Atribuição CTWA — first-click-wins: nunca sobrescreve um clid já capturado.
        ref = parsed.get("referral")
        if ref and ref.get("ctwa_clid") and not contact.ctwa_clid:
            contact.source = "ctwa"
            contact.ctwa_clid = ref["ctwa_clid"]
            contact.ctwa_clid_at = msg_time
            contact.ad_id = ref.get("source_id")
            contact.ad_headline = (ref.get("headline") or "")[:255]
            contact.ad_payload = ref
            print(f"🎯 Meta CTWA: contato {wa_id} atribuído ao anúncio {ref.get('source_id')}", flush=True)

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

        # Pré-filtro barato do agente (o handler faz a checagem autoritativa de
        # gating com dados frescos). Só texto e só canal com agent_enabled.
        if (
            getattr(channel, "agent_enabled", False)
            and channel.operation_mode == "ai"
            and message_type == "text"
            and content
        ):
            agent_jobs.append((channel.id, wa_id, wa_message_id, content))

        relay_payloads.append({
            "wa_id": wa_id,
            "wa_message_id": wa_message_id,
            "message_type": message_type,
            "content": content,
            "timestamp": msg_time.isoformat() if hasattr(msg_time, "isoformat") else msg_time,
            "sender_name": parsed.get("contact_name"),
            "referral": parsed.get("referral"),   # ctwa_clid + headline/body/source_id do anúncio
            "channel": {
                "id": channel.id,
                "provider": "official",
                "name": channel.name,
            },
        })

        print(f"📥 Meta [{channel.name}] {wa_id}: {(content or '')[:100]}", flush=True)

    await db.commit()

    # Relay best-effort pro Customer (dono do inbox). Nunca derruba o webhook.
    for rp in relay_payloads:
        await relay.relay_inbound(rp)

    # Agente de IA: dispara em background (nunca bloqueia nem derruba o webhook).
    # Import isolado: se o módulo do agente falhar, o webhook segue intacto.
    if agent_jobs:
        try:
            import asyncio as _asyncio

            from app.agent import handler as _agent_handler

            for job in agent_jobs:
                _asyncio.create_task(_agent_handler.handle_inbound(*job))
        except Exception as _e:  # pragma: no cover
            print(f"🤖❌ falha ao agendar agente (webhook intacto): {_e!r}", flush=True)


async def _process_statuses(payload, db):
    statuses = parse_statuses(payload)
    if not statuses:
        return

    relay_payloads: list[dict] = []

    for st in statuses:
        wa_message_id = st["wa_message_id"]
        new_status = st["status"]
        # Relaya todo status recebido — o Customer é o dono do inbox e pode ter
        # a mensagem mesmo que o Mensage não a tenha persistido.
        relay_payloads.append({"wa_message_id": wa_message_id, "status": new_status})

        # Falha de entrega: loga o motivo da Meta (code/title/details) — antes era descartado
        if new_status == "failed" and st.get("errors"):
            for err in st["errors"]:
                ed = err.get("error_data") or {}
                print(
                    f"❌ Meta delivery FAILED {wa_message_id} → "
                    f"recipient={st.get('recipient_id')} "
                    f"code={err.get('code')} title={err.get('title')!r} "
                    f"details={ed.get('details')!r}",
                    flush=True,
                )
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

    # Relay best-effort pro Customer. Nunca derruba o webhook.
    for rp in relay_payloads:
        await relay.relay_status(rp)


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


@bridge_router.post("/channels/{channel_id}/send-text")
async def send_text_endpoint(channel_id: int, payload: SendTextRequest, db: DbSession):
    from app.messaging.persistence import persist_outbound_message
    from app.messaging.provider import get_provider

    ch = await db.get(Channel, channel_id)
    if ch is None or ch.provider != "official":
        raise HTTPException(status_code=404, detail="Meta channel not found")
    if not ch.phone_number_id or not ch.whatsapp_token:
        raise HTTPException(status_code=400, detail="Channel sem phone_number_id ou token")

    provider = get_provider(ch)
    try:
        result = await provider.send_text(ch, payload.to, payload.text)
    except Exception as e:
        # Registra a falha no chat para que a mensagem apareça (status=failed).
        await persist_outbound_message(
            db=db,
            channel=ch,
            to=payload.to,
            message_type="text",
            content=payload.text,
            status="failed",
        )
        await db.commit()
        raise HTTPException(status_code=502, detail=f"Falha ao enviar texto: {e}")
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


@bridge_router.post("/channels/{channel_id}/send-template")
async def send_template_endpoint(channel_id: int, payload: SendTemplateRequest, db: DbSession):
    from app.messaging.persistence import persist_outbound_message
    from app.messaging.provider import get_provider

    ch = await db.get(Channel, channel_id)
    if ch is None or ch.provider != "official":
        raise HTTPException(status_code=404, detail="Meta channel not found")
    if not ch.phone_number_id or not ch.whatsapp_token:
        raise HTTPException(status_code=400, detail="Channel sem phone_number_id ou token")

    provider = get_provider(ch)
    content_repr = f"[template:{payload.template_name}@{payload.language_code}]"
    try:
        result = await provider.send_template(
            ch,
            payload.to,
            payload.template_name,
            payload.language_code,
            payload.components,
        )
    except Exception as e:
        # Registra a falha no chat para que o template apareça (status=failed).
        await persist_outbound_message(
            db=db,
            channel=ch,
            to=payload.to,
            message_type="template",
            content=content_repr,
            status="failed",
        )
        await db.commit()
        print(
            f"❌ Falha ao enviar template {payload.template_name}@{payload.language_code} → {payload.to}: {e}",
            flush=True,
        )
        raise HTTPException(status_code=502, detail=f"Falha ao enviar template: {e}")

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


@bridge_router.post("/channels/{channel_id}/send-media")
async def send_media_endpoint(channel_id: int, payload: SendMediaRequest, db: DbSession):
    from app.messaging.persistence import persist_outbound_message
    from app.messaging.provider import get_provider
    from app.messaging.types import OutboundMedia

    ch = await db.get(Channel, channel_id)
    if ch is None or ch.provider != "official":
        raise HTTPException(status_code=404, detail="Meta channel not found")
    if not ch.phone_number_id or not ch.whatsapp_token:
        raise HTTPException(status_code=400, detail="Channel sem phone_number_id ou token")

    # Mídia via URL (caminho simples pro Graph), via MediaAsset local ou via base64.
    asset_path: Optional[str] = None
    if payload.media_id is not None:
        asset = await db.get(MediaAsset, payload.media_id)
        if not asset:
            raise HTTPException(status_code=404, detail="MediaAsset não encontrado")
        if not os.path.exists(asset.stored_path):
            raise HTTPException(status_code=404, detail="Arquivo da mídia ausente no disco")
        # O asset é reaproveitável: apontamos para ele, nunca copiamos nem apagamos.
        asset_path = asset.stored_path
        payload.mime_type = payload.mime_type or asset.mime_type
        payload.filename = payload.filename or asset.filename
    elif payload.media_base64:
        if not payload.mime_type:
            raise HTTPException(status_code=422, detail="media_base64 requer mime_type")
        try:
            raw_bytes = base64.b64decode(payload.media_base64, validate=True)
        except (binascii.Error, ValueError):
            raise HTTPException(status_code=422, detail="media_base64 inválido")
        os.makedirs(_settings.MEDIA_DIR, exist_ok=True)
        filename = payload.filename or f"{uuid.uuid4().hex}"
        asset_path = os.path.join(_settings.MEDIA_DIR, f"{uuid.uuid4().hex}_{filename}")
        with open(asset_path, "wb") as fh:
            fh.write(raw_bytes)

    media = OutboundMedia(
        media_type=payload.media_type,
        asset_path=asset_path,
        mime_type=payload.mime_type,
        filename=payload.filename,
        caption=payload.caption,
        media_link=payload.media_link if asset_path is None else None,
    )

    provider = get_provider(ch)
    if asset_path:
        content_repr = f"local:{payload.filename or os.path.basename(asset_path)}|{payload.mime_type}|{payload.caption or ''}"
    else:
        content_repr = f"link:{payload.media_link}|{payload.mime_type or ''}|{payload.caption or ''}"
    try:
        result = await provider.send_media(ch, payload.to, media)
    except Exception as e:
        # Registra a falha no chat para que a mídia apareça (status=failed).
        await persist_outbound_message(
            db=db,
            channel=ch,
            to=payload.to,
            message_type=payload.media_type,
            content=content_repr,
            status="failed",
        )
        await db.commit()
        raise HTTPException(status_code=502, detail=f"Falha ao enviar mídia: {e}")
    await persist_outbound_message(
        db=db,
        channel=ch,
        to=payload.to,
        message_type=payload.media_type,
        content=content_repr,
        send_result=result,
    )
    await db.commit()
    print(
        f"📤 Mídia enviada: {payload.media_type} → {payload.to} (wa_message_id={result.wa_message_id})",
        flush=True,
    )
    return {
        "status": "sent",
        "wa_message_id": result.wa_message_id,
        "graph_response": result.raw_response,
    }


@bridge_router.post("/channels/{channel_id}/templates/sync")
async def sync_templates(channel_id: int, db: DbSession):
    ch = await db.get(Channel, channel_id)
    if ch is None or ch.provider != "official":
        raise HTTPException(status_code=404, detail="Meta channel not found")
    if not ch.waba_id or not ch.whatsapp_token:
        raise HTTPException(status_code=400, detail="Channel sem waba_id ou token")

    try:
        templates = await meta_client.list_message_templates(
            waba_id=ch.waba_id,
            token=ch.whatsapp_token,
        )
    except httpx.HTTPStatusError as exc:
        content_type = exc.response.headers.get("content-type") or ""
        detail = exc.response.json() if "json" in content_type else exc.response.text[:500]
        raise HTTPException(status_code=502, detail={"meta_error": detail})

    inserted = 0
    updated = 0
    now_dt = datetime.now(timezone.utc)
    for t in templates:
        name = t.get("name")
        language = t.get("language") or "pt_BR"
        if not name:
            continue
        existing_res = await db.execute(
            select(MetaTemplate).where(
                MetaTemplate.channel_id == ch.id,
                MetaTemplate.name == name,
                MetaTemplate.language == language,
            )
        )
        existing = existing_res.scalar_one_or_none()
        if existing:
            existing.category = t.get("category")
            existing.status = t.get("status") or "UNKNOWN"
            existing.components = t.get("components")
            existing.meta_template_id = str(t.get("id")) if t.get("id") else None
            existing.last_synced_at = now_dt
            updated += 1
        else:
            db.add(MetaTemplate(
                channel_id=ch.id,
                name=name,
                language=language,
                category=t.get("category"),
                status=t.get("status") or "UNKNOWN",
                components=t.get("components"),
                meta_template_id=str(t.get("id")) if t.get("id") else None,
                last_synced_at=now_dt,
            ))
            inserted += 1
    await db.commit()
    print(
        f"📊 Templates sync canal {ch.id}: {inserted} novos, {updated} atualizados, total {len(templates)}",
        flush=True,
    )
    return {
        "channel_id": ch.id,
        "total_remote": len(templates),
        "inserted": inserted,
        "updated": updated,
    }


@bridge_router.get("/channels/{channel_id}/templates", response_model=list[MetaTemplateOut])
async def list_templates(
    channel_id: int,
    db: DbSession,
    status: Optional[str] = None,
):
    ch = await db.get(Channel, channel_id)
    if ch is None or ch.provider != "official":
        raise HTTPException(status_code=404, detail="Meta channel not found")
    q = select(MetaTemplate).where(MetaTemplate.channel_id == channel_id).order_by(MetaTemplate.name)
    if status:
        q = q.where(MetaTemplate.status == status.upper())
    res = await db.execute(q)
    rows = res.scalars().all()
    return [
        MetaTemplateOut(
            id=r.id,
            channel_id=r.channel_id,
            name=r.name,
            language=r.language,
            category=r.category,
            status=r.status,
            components=r.components,
            meta_template_id=r.meta_template_id,
            last_synced_at=r.last_synced_at.isoformat() if r.last_synced_at else None,
        )
        for r in rows
    ]
