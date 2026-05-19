from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

SP_TZ = timezone(timedelta(hours=-3))


def parse_timestamp(ts: Any) -> datetime:
    if ts is None or ts == "":
        return datetime.now(SP_TZ).replace(tzinfo=None)
    try:
        return datetime.fromtimestamp(int(ts), tz=SP_TZ).replace(tzinfo=None)
    except (ValueError, TypeError):
        return datetime.now(SP_TZ).replace(tzinfo=None)


def iter_value_objects(payload: dict[str, Any]):
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            if change.get("field") != "messages":
                continue
            value = change.get("value") or {}
            yield value


def extract_phone_number_id(value: dict[str, Any]) -> Optional[str]:
    metadata = value.get("metadata") or {}
    pnid = metadata.get("phone_number_id")
    return str(pnid) if pnid else None


def extract_contact_name(value: dict[str, Any], wa_id: str) -> Optional[str]:
    for contact in value.get("contacts") or []:
        if contact.get("wa_id") == wa_id:
            profile = contact.get("profile") or {}
            return profile.get("name")
    return None


def parse_inbound_message(msg: dict[str, Any], value: dict[str, Any]) -> Optional[dict[str, Any]]:
    wa_message_id = msg.get("id")
    wa_id = msg.get("from")
    msg_type = msg.get("type", "")
    timestamp = parse_timestamp(msg.get("timestamp"))

    if not wa_message_id or not wa_id:
        return None

    contact_name = extract_contact_name(value, wa_id)

    base = {
        "wa_message_id": wa_message_id,
        "wa_id": wa_id,
        "contact_name": contact_name,
        "timestamp": timestamp,
        "raw_type": msg_type,
    }

    if msg_type == "text":
        text_body = (msg.get("text") or {}).get("body", "")
        base["message_type"] = "text"
        base["content"] = text_body
        base["media"] = None
        return base

    if msg_type in ("image", "audio", "video", "document", "sticker"):
        media_obj = msg.get(msg_type) or {}
        base["message_type"] = msg_type
        base["content"] = None
        base["media"] = {
            "media_id": media_obj.get("id"),
            "mime_type": media_obj.get("mime_type", ""),
            "caption": media_obj.get("caption", "") or "",
            "filename": media_obj.get("filename"),
            "sha256": media_obj.get("sha256"),
        }
        return base

    if msg_type == "interactive":
        interactive = msg.get("interactive") or {}
        sub = interactive.get("type", "")
        if sub == "button_reply":
            reply = interactive.get("button_reply") or {}
            content = f"[interactive] {reply.get('id', '')}: {reply.get('title', '')}"
        elif sub == "list_reply":
            reply = interactive.get("list_reply") or {}
            content = f"[interactive] {reply.get('id', '')}: {reply.get('title', '')}"
        else:
            content = f"[interactive] {sub}"
        base["message_type"] = "text"
        base["content"] = content
        base["media"] = None
        return base

    if msg_type == "button":
        btn = msg.get("button") or {}
        base["message_type"] = "text"
        base["content"] = f"[button] {btn.get('payload', '')}: {btn.get('text', '')}"
        base["media"] = None
        return base

    if msg_type == "reaction":
        reaction = msg.get("reaction") or {}
        base["message_type"] = "text"
        base["content"] = f"[reaction] {reaction.get('emoji', '')} em {reaction.get('message_id', '')}"
        base["media"] = None
        return base

    base["message_type"] = "text"
    base["content"] = f"[{msg_type}] (tipo não tratado)"
    base["media"] = None
    return base


def parse_inbound_messages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for value in iter_value_objects(payload):
        pnid = extract_phone_number_id(value)
        for raw_msg in value.get("messages") or []:
            parsed = parse_inbound_message(raw_msg, value)
            if parsed is None:
                continue
            parsed["phone_number_id"] = pnid
            out.append(parsed)
    return out


def parse_statuses(payload: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for value in iter_value_objects(payload):
        pnid = extract_phone_number_id(value)
        for st in value.get("statuses") or []:
            wa_message_id = st.get("id")
            new_status = st.get("status")
            if not wa_message_id or not new_status:
                continue
            out.append({
                "wa_message_id": wa_message_id,
                "status": new_status,
                "timestamp": parse_timestamp(st.get("timestamp")),
                "recipient_id": st.get("recipient_id"),
                "phone_number_id": pnid,
                "errors": st.get("errors"),
            })
    return out
