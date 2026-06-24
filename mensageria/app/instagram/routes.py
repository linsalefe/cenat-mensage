from __future__ import annotations

import hashlib
import hmac
import json
from typing import Optional

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import or_, select

from app.auth import get_current_user
from app.config import get_settings
from app.deps import DbSession
from app.instagram import client as ig_client
from app.instagram.automations import run_automations_for_event
from app.instagram.parser import classify_entries, parse_inbound_messages
from app.instagram.schemas import (
    ChannelCreateInstagram,
    ChannelOutInstagram,
    ChannelUpdateInstagram,
    InstagramAutomationCreate,
    InstagramAutomationExecutionOut,
    InstagramAutomationOut,
    InstagramAutomationUpdate,
    SendTextRequest,
)
from app.models import (
    Channel,
    Contact,
    InstagramAutomation,
    InstagramAutomationExecution,
    Message,
)

_settings = get_settings()


router = APIRouter(
    prefix="/api/instagram",
    tags=["Instagram API"],
    dependencies=[Depends(get_current_user)],
)
webhook_router = APIRouter(prefix="/api/instagram", tags=["Instagram Webhook"])


# ============================================================
# Webhook (sem auth) — verify + receive
# ============================================================
@webhook_router.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(..., alias="hub.mode"),
    hub_verify_token: str = Query(..., alias="hub.verify_token"),
    hub_challenge: str = Query(..., alias="hub.challenge"),
):
    if not _settings.IG_WEBHOOK_VERIFY_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Instagram webhook verify token not configured",
        )

    if hub_mode != "subscribe":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid hub.mode")

    if not hmac.compare_digest(hub_verify_token, _settings.IG_WEBHOOK_VERIFY_TOKEN):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid verify token")

    return PlainTextResponse(content=hub_challenge, status_code=200)


@webhook_router.post("/webhook")
async def receive_webhook(request: Request, db: DbSession, background_tasks: BackgroundTasks):
    if not _settings.IG_APP_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Instagram app secret not configured",
        )

    raw_body = await request.body()
    signature_header = request.headers.get("X-Hub-Signature-256", "")
    if not signature_header.startswith("sha256="):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="missing signature")

    received_sig = signature_header.removeprefix("sha256=")
    expected_sig = hmac.new(
        _settings.IG_APP_SECRET.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(received_sig, expected_sig):
        print("⚠️ IG webhook: assinatura inválida", flush=True)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid signature")

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        print(f"⚠️ IG webhook: JSON inválido: {raw_body[:200]!r}", flush=True)
        return {"status": "ok"}

    if payload.get("object") != "instagram":
        # Não é evento do IG — ignora sem erro.
        return {"status": "ok"}

    entry_ids = [str(e.get("id")) for e in (payload.get("entry") or [])]
    print(f"🔔 IG webhook: object=instagram entries={entry_ids}", flush=True)

    try:
        await _process_inbound(payload, db)
    except Exception as exc:
        print(f"❌ IG webhook: erro ao processar inbound: {exc.__class__.__name__}: {exc}", flush=True)

    # Agenda o processamento das automações em background (200 imediato pro Meta).
    try:
        await _schedule_automations(payload, db, background_tasks)
    except Exception as exc:
        print(f"❌ IG webhook: erro ao agendar automações: {exc.__class__.__name__}: {exc}", flush=True)

    return {"status": "ok"}


async def _schedule_automations(payload, db, background_tasks: BackgroundTasks):
    """Classifica os eventos e agenda run_automations_for_event por evento.

    Resolve o canal aqui (sessão do request) só pra obter o channel_id; cada task
    abre a própria sessão de DB (a do request fecha ao responder).
    """
    buckets = classify_entries(payload)
    if not any(buckets.values()):
        return

    channel_id_cache: dict[str, int | None] = {}

    async def channel_id_for(entry_ig_id) -> int | None:
        key = entry_ig_id or ""
        if key not in channel_id_cache:
            ch = await _resolve_channel(db, entry_ig_id)
            channel_id_cache[key] = ch.id if ch else None
        return channel_id_cache[key]

    def schedule(kind: str, event: dict, channel_id: int):
        background_tasks.add_task(run_automations_for_event, kind, event, channel_id)

    # Mensagens → dm_received (inbound texto) e story_reply. Echo não dispara.
    for m in buckets["messages"]:
        if m.get("direction") != "inbound":
            continue
        cid = await channel_id_for(m.get("entry_ig_id"))
        if cid is None:
            continue
        if m.get("message_type") == "story_reply":
            schedule("story_reply", m, cid)
        elif m.get("message_type") == "text":
            schedule("dm_received", m, cid)

    for kind, bucket in (("comment", "comments"), ("reaction", "reactions"),
                         ("postback", "postbacks"), ("mention", "mentions")):
        for ev in buckets[bucket]:
            cid = await channel_id_for(ev.get("entry_ig_id"))
            if cid is None:
                continue
            schedule(kind, ev, cid)


async def _resolve_channel(db, entry_ig_id) -> Channel | None:
    if not entry_ig_id:
        return None
    result = await db.execute(
        select(Channel).where(
            Channel.provider == "instagram",
            or_(Channel.instagram_id == entry_ig_id, Channel.page_id == entry_ig_id),
        )
    )
    return result.scalars().first()


async def _process_inbound(payload, db):
    messages = parse_inbound_messages(payload)
    if not messages:
        print("ℹ️ IG inbound: evento sem mensagem persistível (read/echo/postback/comment).", flush=True)
        return
    print(f"📨 IG inbound: {len(messages)} mensagem(ns) parseada(s).", flush=True)

    for parsed in messages:
        channel = await _resolve_channel(db, parsed.get("entry_ig_id"))
        if channel is None:
            print(
                f"⚠️ IG inbound: canal não encontrado para instagram_id={parsed.get('entry_ig_id')}",
                flush=True,
            )
            continue

        ig_message_id = parsed["ig_message_id"]
        wa_id = "ig:" + parsed["user_igsid"]
        msg_time = parsed["timestamp"]
        direction = parsed["direction"]

        existing = await db.execute(
            select(Message).where(Message.wa_message_id == ig_message_id)
        )
        if existing.scalar_one_or_none():
            # Dedup: echo de mensagem já persistida no envio, ou reentrega do webhook.
            continue

        contact_result = await db.execute(select(Contact).where(Contact.wa_id == wa_id))
        contact = contact_result.scalar_one_or_none()
        if contact is None:
            from app.crm.enroll import resolve_default_pipeline_id

            pipeline_id = await resolve_default_pipeline_id(channel, db)
            contact = Contact(
                wa_id=wa_id,
                name=parsed["user_igsid"],
                channel_id=channel.id,
                pipeline_id=pipeline_id,
                lead_status="novo",
                ai_active=False,
                last_inbound_at=msg_time if direction == "inbound" else None,
                reengagement_count=0,
                is_group=False,
            )
            db.add(contact)
            await db.flush()
            print(f"👤 IG novo contato: {wa_id}", flush=True)
        elif direction == "inbound":
            contact.last_inbound_at = msg_time
            contact.reengagement_count = 0

        new_msg = Message(
            wa_message_id=ig_message_id,
            contact_wa_id=wa_id,
            channel_id=channel.id,
            direction=direction,
            message_type=parsed["message_type"],
            content=parsed.get("content"),
            timestamp=msg_time,
            status="received" if direction == "inbound" else "sent",
        )
        db.add(new_msg)
        print(
            f"📥 IG [{channel.name}] {wa_id} ({direction}): {(parsed.get('content') or '')[:100]}",
            flush=True,
        )

    await db.commit()


# ============================================================
# CRUD de canal (com auth)
# ============================================================
@router.post("/channels", response_model=ChannelOutInstagram, status_code=201)
async def create_channel(payload: ChannelCreateInstagram, db: DbSession):
    existing = await db.execute(
        select(Channel).where(
            Channel.instagram_id == payload.instagram_id,
            Channel.provider == "instagram",
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Channel with instagram_id already exists")

    channel = Channel(
        name=payload.name or payload.username or payload.instagram_id,
        instagram_id=payload.instagram_id,
        page_id=payload.page_id,
        access_token=payload.access_token,
        provider="instagram",
        type="instagram",
        is_connected=True,
        is_active=True,
        operation_mode="none",
    )
    db.add(channel)
    await db.commit()
    await db.refresh(channel)
    return channel


@router.get("/channels", response_model=list[ChannelOutInstagram])
async def list_channels(db: DbSession):
    result = await db.execute(
        select(Channel).where(Channel.provider == "instagram").order_by(Channel.id.asc())
    )
    return list(result.scalars().all())


@router.get("/channels/{channel_id}", response_model=ChannelOutInstagram)
async def get_channel(channel_id: int, db: DbSession):
    ch = await db.get(Channel, channel_id)
    if ch is None or ch.provider != "instagram":
        raise HTTPException(status_code=404, detail="Instagram channel not found")
    return ch


@router.get("/channels/{channel_id}/health")
async def channel_health(channel_id: int, db: DbSession):
    ch = await db.get(Channel, channel_id)
    if ch is None or ch.provider != "instagram":
        raise HTTPException(status_code=404, detail="Instagram channel not found")
    if not ch.instagram_id or not ch.access_token:
        raise HTTPException(status_code=400, detail="Channel sem instagram_id ou access_token")

    try:
        data = await ig_client.get_profile(ch.instagram_id, ch.access_token)
    except httpx.HTTPStatusError as exc:
        content_type = exc.response.headers.get("content-type", "")
        return {
            "channel_id": ch.id,
            "ok": False,
            "status_code": exc.response.status_code,
            "error": exc.response.json() if content_type.startswith("application/json") else exc.response.text[:500],
        }
    except httpx.HTTPError as exc:
        return {"channel_id": ch.id, "ok": False, "error": str(exc)}

    return {
        "channel_id": ch.id,
        "ok": True,
        "username": data.get("username"),
        "name": data.get("name"),
        "profile_picture_url": data.get("profile_picture_url"),
    }


@router.get("/channels/{channel_id}/subscription")
async def channel_subscription(channel_id: int, db: DbSession):
    ch = await _get_ig_channel_or_404(db, channel_id)
    if not ch.page_id or not ch.access_token:
        raise HTTPException(status_code=400, detail="Channel sem page_id ou access_token")
    try:
        data = await ig_client.get_subscribed_apps(ch.page_id, ch.access_token)
    except httpx.HTTPStatusError as exc:
        ct = exc.response.headers.get("content-type", "")
        return {
            "channel_id": ch.id, "ok": False,
            "status_code": exc.response.status_code,
            "error": exc.response.json() if ct.startswith("application/json") else exc.response.text[:500],
        }
    return {"channel_id": ch.id, "ok": True, "subscribed_apps": data}


@router.post("/channels/{channel_id}/subscribe")
async def channel_subscribe(
    channel_id: int,
    db: DbSession,
    fields: str = Query(default="messages,comments,live_comments,mentions,message_reactions"),
):
    ch = await _get_ig_channel_or_404(db, channel_id)
    if not ch.page_id or not ch.access_token:
        raise HTTPException(status_code=400, detail="Channel sem page_id ou access_token")
    try:
        data = await ig_client.subscribe_page(ch.page_id, ch.access_token, fields)
    except httpx.HTTPStatusError as exc:
        ct = exc.response.headers.get("content-type", "")
        detail = exc.response.json() if ct.startswith("application/json") else exc.response.text[:500]
        # Erro de permissão aqui = token sem pages_manage_metadata (ver observações).
        raise HTTPException(status_code=502, detail={"meta_error": detail})
    return {"channel_id": ch.id, "ok": True, "result": data}


@router.patch("/channels/{channel_id}", response_model=ChannelOutInstagram)
async def update_channel(channel_id: int, payload: ChannelUpdateInstagram, db: DbSession):
    ch = await db.get(Channel, channel_id)
    if ch is None or ch.provider != "instagram":
        raise HTTPException(status_code=404, detail="Instagram channel not found")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(ch, field, value)
    await db.commit()
    await db.refresh(ch)
    return ch


@router.delete("/channels/{channel_id}", status_code=204)
async def delete_channel(channel_id: int, db: DbSession):
    ch = await db.get(Channel, channel_id)
    if ch is None or ch.provider != "instagram":
        raise HTTPException(status_code=404, detail="Instagram channel not found")
    await db.delete(ch)
    await db.commit()


@router.post("/channels/{channel_id}/send-text")
async def send_text_endpoint(channel_id: int, payload: SendTextRequest, db: DbSession):
    from app.messaging.persistence import persist_outbound_message
    from app.messaging.provider import get_provider

    ch = await db.get(Channel, channel_id)
    if ch is None or ch.provider != "instagram":
        raise HTTPException(status_code=404, detail="Instagram channel not found")
    if not ch.instagram_id or not ch.access_token:
        raise HTTPException(status_code=400, detail="Channel sem instagram_id ou access_token")

    # Aceita o IGSID com ou sem o prefixo interno "ig:".
    to_igsid = payload.to[3:] if payload.to.startswith("ig:") else payload.to

    provider = get_provider(ch)
    try:
        result = await provider.send_text(ch, to_igsid, payload.text)
    except httpx.HTTPStatusError as exc:
        # Propaga o erro da Meta de forma legível (ex.: fora da janela de 24h).
        content_type = exc.response.headers.get("content-type", "")
        detail = exc.response.json() if content_type.startswith("application/json") else exc.response.text[:500]
        raise HTTPException(status_code=502, detail={"meta_error": detail})

    await persist_outbound_message(
        db=db,
        channel=ch,
        to="ig:" + to_igsid,
        message_type="text",
        content=payload.text,
        send_result=result,
    )
    await db.commit()
    print(
        f"📤 IG [{ch.name}] → ig:{to_igsid} (message_id={result.wa_message_id})",
        flush=True,
    )
    return {
        "status": "sent",
        "message_id": result.wa_message_id,
        "graph_response": result.raw_response,
    }


# ============================================================
# CRUD de automações por evento (Sprint 2)
# ============================================================
async def _get_ig_channel_or_404(db, channel_id: int) -> Channel:
    ch = await db.get(Channel, channel_id)
    if ch is None or ch.provider != "instagram":
        raise HTTPException(status_code=404, detail="Instagram channel not found")
    return ch


async def _get_automation_or_404(db, automation_id: int) -> InstagramAutomation:
    a = await db.get(InstagramAutomation, automation_id)
    if a is None:
        raise HTTPException(status_code=404, detail="Automation not found")
    # Garante que pertence a um canal instagram (defensivo).
    ch = await db.get(Channel, a.channel_id)
    if ch is None or ch.provider != "instagram":
        raise HTTPException(status_code=404, detail="Automation not found")
    return a


@router.post("/channels/{channel_id}/automations", response_model=InstagramAutomationOut, status_code=201)
async def create_automation(channel_id: int, payload: InstagramAutomationCreate, db: DbSession):
    await _get_ig_channel_or_404(db, channel_id)
    automation = InstagramAutomation(
        channel_id=channel_id,
        name=payload.name,
        trigger_type=payload.trigger_type,
        trigger_config=payload.trigger_config,
        action_type=payload.action_type,
        action_config=payload.action_config,
        once_per_contact=payload.once_per_contact,
        is_active=payload.is_active,
        priority=payload.priority,
    )
    db.add(automation)
    await db.commit()
    await db.refresh(automation)
    return automation


@router.get("/channels/{channel_id}/automations", response_model=list[InstagramAutomationOut])
async def list_automations(
    channel_id: int,
    db: DbSession,
    trigger_type: Optional[str] = None,
    active: Optional[bool] = None,
):
    await _get_ig_channel_or_404(db, channel_id)
    q = select(InstagramAutomation).where(InstagramAutomation.channel_id == channel_id)
    if trigger_type:
        q = q.where(InstagramAutomation.trigger_type == trigger_type)
    if active is not None:
        q = q.where(InstagramAutomation.is_active.is_(active))
    q = q.order_by(InstagramAutomation.priority.asc(), InstagramAutomation.id.asc())
    res = await db.execute(q)
    return list(res.scalars().all())


@router.get("/automations/{automation_id}", response_model=InstagramAutomationOut)
async def get_automation(automation_id: int, db: DbSession):
    return await _get_automation_or_404(db, automation_id)


@router.patch("/automations/{automation_id}", response_model=InstagramAutomationOut)
async def update_automation(automation_id: int, payload: InstagramAutomationUpdate, db: DbSession):
    automation = await _get_automation_or_404(db, automation_id)
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(automation, field, value)
    await db.commit()
    await db.refresh(automation)
    return automation


@router.delete("/automations/{automation_id}", status_code=204)
async def delete_automation(automation_id: int, db: DbSession):
    automation = await _get_automation_or_404(db, automation_id)
    await db.delete(automation)
    await db.commit()


@router.get("/automations/{automation_id}/executions", response_model=list[InstagramAutomationExecutionOut])
async def list_executions(
    automation_id: int,
    db: DbSession,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    await _get_automation_or_404(db, automation_id)
    res = await db.execute(
        select(InstagramAutomationExecution)
        .where(InstagramAutomationExecution.automation_id == automation_id)
        .order_by(InstagramAutomationExecution.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(res.scalars().all())
