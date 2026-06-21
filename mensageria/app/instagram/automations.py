from __future__ import annotations

from typing import Any, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database import AsyncSessionLocal
from app.instagram import client as ig_client
from app.messaging.types import SendResult
from app.models import Channel, InstagramAutomation, InstagramAutomationExecution

# Eventos cujo gatilho casa por texto/keyword.
_TEXT_EVENTS = ("dm_received", "comment", "story_reply")


# ============================================================
# Extração de campos por tipo de evento
# ============================================================
def _text_of(event_kind: str, event: dict[str, Any]) -> str:
    if event_kind == "comment":
        return event.get("text") or ""
    if event_kind in ("dm_received", "story_reply"):
        return event.get("content") or ""
    return ""


def _user_igsid(event: dict[str, Any]) -> Optional[str]:
    return event.get("user_igsid")


def _contact_wa(event: dict[str, Any]) -> Optional[str]:
    igsid = _user_igsid(event)
    return f"ig:{igsid}" if igsid else None


def _trigger_ref(event_kind: str, event: dict[str, Any]) -> str:
    """Chave de dedup por (automação, trigger_ref)."""
    if event_kind == "comment":
        return event.get("comment_id") or "comment:unknown"
    if event_kind == "mention":
        return "mention:" + (event.get("comment_id") or event.get("media_id") or "unknown")
    igsid = _user_igsid(event)
    return f"ig:{igsid}" if igsid else f"{event_kind}:unknown"


# ============================================================
# Avaliação de condição (trigger_config × event)
# ============================================================
def _match_keywords(text: str, keywords: list[str], match: str) -> bool:
    if not keywords:
        return True
    t = (text or "").lower()
    kws = [str(k).lower() for k in keywords]
    if match == "all":
        return all(k in t for k in kws)
    if match == "exact":
        return t.strip() in kws
    # default: any
    return any(k in t for k in kws)


def _matches(snap: dict[str, Any], event_kind: str, event: dict[str, Any]) -> bool:
    cfg = snap.get("trigger_config") or {}

    if event_kind in _TEXT_EVENTS:
        # Restrição opcional a um post específico.
        cfg_media = cfg.get("media_id")
        if cfg_media and event.get("media_id") != cfg_media:
            return False
        return _match_keywords(
            _text_of(event_kind, event),
            cfg.get("keywords") or [],
            (cfg.get("match") or "any"),
        )

    if event_kind == "reaction":
        want = cfg.get("emoji")
        return (not want) or event.get("emoji") == want

    if event_kind == "postback":
        want = cfg.get("payload")
        return (not want) or event.get("payload") == want

    if event_kind == "mention":
        # Sem texto enriquecido nesta sprint — dispara sempre.
        return True

    return False


def _render_text(template: str, event: dict[str, Any]) -> str:
    username = event.get("username") or ""
    return (template or "").replace("{username}", username)


def _err_detail(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        ct = exc.response.headers.get("content-type", "")
        body = exc.response.json() if ct.startswith("application/json") else exc.response.text[:500]
        return f"HTTP {exc.response.status_code}: {body}"
    return f"{exc.__class__.__name__}: {exc}"[:1000]


# ============================================================
# Execução da ação
# ============================================================
async def _execute_action(
    snap: dict[str, Any],
    event_kind: str,
    event: dict[str, Any],
    channel: Channel,
    db,
) -> str:
    """Executa a ação e devolve um 'detail' curto. Pode levantar — o chamador loga error."""
    from app.messaging.persistence import persist_outbound_message
    from app.messaging.provider import get_provider

    text = _render_text((snap.get("action_config") or {}).get("text", ""), event)
    action = snap.get("action_type")

    if action == "send_dm":
        igsid = _user_igsid(event)
        if not igsid:
            raise ValueError("send_dm sem user_igsid no evento")
        provider = get_provider(channel)
        result = await provider.send_text(channel, igsid, text)
        await persist_outbound_message(
            db=db, channel=channel, to=f"ig:{igsid}",
            message_type="text", content=text, send_result=result, sent_by_ai=True,
        )
        return f"send_dm message_id={result.wa_message_id}"

    if action == "private_reply":
        comment_id = event.get("comment_id")
        if not comment_id:
            raise ValueError("private_reply exige comment_id (gatilho de comentário)")
        raw = await ig_client.send_private_reply(
            channel.instagram_id, channel.access_token, comment_id, text
        )
        msg_id = raw.get("message_id")
        # Se o comentário trouxe o IGSID, registra como DM outbound do contato.
        igsid = _user_igsid(event)
        if msg_id and igsid:
            await persist_outbound_message(
                db=db, channel=channel, to=f"ig:{igsid}",
                message_type="text", content=text,
                send_result=SendResult(wa_message_id=str(msg_id), raw_response=raw),
                sent_by_ai=True,
            )
        return f"private_reply message_id={msg_id}"

    if action == "public_comment_reply":
        comment_id = event.get("comment_id")
        if not comment_id:
            raise ValueError("public_comment_reply exige comment_id")
        raw = await ig_client.reply_to_comment(comment_id, channel.access_token, text)
        return f"public_comment_reply reply_id={raw.get('id')}"

    raise ValueError(f"action_type desconhecido: {action}")


async def _already_sent(db, automation_id: int, trigger_ref: str) -> bool:
    res = await db.execute(
        select(InstagramAutomationExecution.id).where(
            InstagramAutomationExecution.automation_id == automation_id,
            InstagramAutomationExecution.trigger_ref == trigger_ref,
            InstagramAutomationExecution.status == "sent",
        ).limit(1)
    )
    return res.scalar_one_or_none() is not None


def _log_execution(db, snap, channel_id, trigger_ref, contact_wa, status, detail):
    db.add(InstagramAutomationExecution(
        automation_id=snap["id"], channel_id=channel_id,
        trigger_ref=trigger_ref, contact_wa_id=contact_wa,
        status=status, detail=detail,
    ))


# ============================================================
# Motor — uma automação por sessão (isola rollback de erro)
# ============================================================
async def _run_one(snap, event_kind, event, channel_id, trigger_ref, contact_wa) -> None:
    """Roda UMA automação na sua própria sessão. snap é um dict puro (sem ORM vivo),
    pra um rollback de erro não expirar objetos usados por outras automações."""
    async with AsyncSessionLocal() as db:
        try:
            if not _matches(snap, event_kind, event):
                return

            if snap["once_per_contact"] and await _already_sent(db, snap["id"], trigger_ref):
                _log_execution(db, snap, channel_id, trigger_ref, contact_wa,
                               "skipped", "once_per_contact: já disparado")
                await db.commit()
                print(f"⏭️ IG automação [{snap['name']}] skip (dedup) {trigger_ref}", flush=True)
                return

            channel = await db.get(Channel, channel_id)
            if channel is None:
                return

            try:
                detail = await _execute_action(snap, event_kind, event, channel, db)
                status_val = "sent"
            except Exception as exc:
                await db.rollback()  # limpa qualquer persist parcial da ação que falhou
                status_val = "error"
                detail = _err_detail(exc)
                print(f"❌ IG automação [{snap['name']}] erro: {detail}", flush=True)

            _log_execution(db, snap, channel_id, trigger_ref, contact_wa, status_val, detail)
            try:
                await db.commit()
            except IntegrityError:
                # Corrida no índice parcial 'sent' — outra task já registrou o envio.
                await db.rollback()
                print(f"⏭️ IG automação [{snap['name']}] corrida de dedup {trigger_ref}", flush=True)
                return

            if status_val == "sent":
                print(f"🤖 IG automação [{snap['name']}] disparou pra {contact_wa or trigger_ref}", flush=True)
        except Exception as exc:
            await db.rollback()
            print(f"❌ IG automação [{snap.get('name')}] exceção inesperada: {exc.__class__.__name__}: {exc}", flush=True)


async def run_automations_for_event(
    event_kind: str,
    event: dict[str, Any],
    channel_id: int,
) -> None:
    """Ponto de entrada (via BackgroundTasks). Carrega as automações do canal/gatilho,
    serializa em snapshots puros e roda cada uma isoladamente."""
    try:
        async with AsyncSessionLocal() as db:
            channel = await db.get(Channel, channel_id)
            if channel is None or channel.provider != "instagram":
                return
            res = await db.execute(
                select(InstagramAutomation).where(
                    InstagramAutomation.channel_id == channel_id,
                    InstagramAutomation.trigger_type == event_kind,
                    InstagramAutomation.is_active.is_(True),
                ).order_by(InstagramAutomation.priority.asc(), InstagramAutomation.id.asc())
            )
            snaps = [
                {
                    "id": a.id,
                    "name": a.name,
                    "once_per_contact": a.once_per_contact,
                    "trigger_config": a.trigger_config or {},
                    "action_type": a.action_type,
                    "action_config": a.action_config or {},
                }
                for a in res.scalars().all()
            ]

        if not snaps:
            return

        trigger_ref = _trigger_ref(event_kind, event)
        contact_wa = _contact_wa(event)
        # Executa todas que casarem, na ordem de priority (once_per_contact segura ruído).
        for snap in snaps:
            await _run_one(snap, event_kind, event, channel_id, trigger_ref, contact_wa)
    except Exception as exc:
        # Nunca propaga — roda em BackgroundTask.
        print(f"❌ IG run_automations_for_event falhou: {exc.__class__.__name__}: {exc}", flush=True)
