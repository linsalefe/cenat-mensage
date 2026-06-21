from __future__ import annotations

from datetime import datetime
from typing import Any, Iterator, Optional

# Reusa a TZ de São Paulo do parser do WhatsApp pra manter consistência de fuso.
from app.meta.parser import SP_TZ

# Tipos de attachment do Instagram → message_type interno.
_ATTACHMENT_TYPE_MAP = {
    "image": "image",
    "audio": "audio",
    "video": "video",
    "file": "file",
    "share": "file",
}


def parse_timestamp_ms(ts: Any) -> datetime:
    """Instagram manda ``messaging[].timestamp`` em **milissegundos** (diferente do
    WhatsApp, que manda em segundos). Convertemos pra datetime naive em SP_TZ."""
    if ts is None or ts == "":
        return datetime.now(SP_TZ).replace(tzinfo=None)
    try:
        return datetime.fromtimestamp(int(ts) / 1000, tz=SP_TZ).replace(tzinfo=None)
    except (ValueError, TypeError):
        return datetime.now(SP_TZ).replace(tzinfo=None)


def iter_messaging(payload: dict[str, Any]) -> Iterator[tuple[Optional[str], dict[str, Any]]]:
    """Itera ``(entry_ig_id, messaging_item)`` de cada ``entry[].messaging[]``.

    Webhook do IG tem ``object == "instagram"`` e estrutura ``entry[].messaging[]``
    (no WhatsApp é ``entry[].changes[].value.messages[]``).
    """
    for entry in payload.get("entry") or []:
        entry_ig_id = str(entry["id"]) if entry.get("id") is not None else None
        for item in entry.get("messaging") or []:
            yield entry_ig_id, item


def _classify(message: dict[str, Any]) -> str:
    # Resposta a um story tem prioridade — vem como reply_to.story.
    reply_to = message.get("reply_to") or {}
    if reply_to.get("story"):
        return "story_reply"

    attachments = message.get("attachments") or []
    if attachments:
        atype = (attachments[0] or {}).get("type", "")
        return _ATTACHMENT_TYPE_MAP.get(atype, "unsupported")

    if message.get("text") is not None:
        return "text"

    return "unsupported"


def _build_content(message: dict[str, Any], message_type: str) -> Optional[str]:
    if message.get("is_deleted"):
        return "[mensagem apagada]"

    if message_type == "text":
        return message.get("text") or ""

    if message_type == "story_reply":
        # Texto da resposta + referência ao story.
        story = (message.get("reply_to") or {}).get("story") or {}
        text = message.get("text") or ""
        story_url = story.get("url")
        marker = f"[story_reply] {text}".strip()
        return f"{marker} {story_url}".strip() if story_url else marker

    if message_type in ("image", "audio", "video", "file"):
        # Nesta sprint não baixamos o binário — só registramos o marcador e,
        # se vier, a URL pública do attachment (download fica pra Sprint 2/3).
        attachments = message.get("attachments") or []
        url = ((attachments[0] or {}).get("payload") or {}).get("url") if attachments else None
        marker = f"[{message_type}]"
        return f"{marker} {url}" if url else marker

    return f"[{message_type}]"


def parse_inbound_messages(
    payload: dict[str, Any],
    channel_ig_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Normaliza o webhook do IG numa lista de mensagens.

    ``channel_ig_id`` é o instagram_id da conta (quando já resolvido); usado pra
    derivar o IGSID do usuário. Se não vier, derivamos por ``is_echo``: em echo
    (enviada) o usuário é o ``recipient``; senão o usuário é o ``sender``.

    Só tratamos ``message`` aqui. reactions/postbacks/comments/mentions ficam pra
    Sprint 2 (automações por evento).
    """
    out: list[dict[str, Any]] = []

    for entry_ig_id, item in iter_messaging(payload):
        message = item.get("message")
        if not message:
            # read / delivery / postback / reaction etc. — tratados pelos parsers de evento
            # da Sprint 2 (parse_reactions/parse_postbacks/...), não aqui.
            continue

        ig_message_id = message.get("mid")
        if not ig_message_id:
            continue

        sender_id = str((item.get("sender") or {}).get("id") or "") or None
        recipient_id = str((item.get("recipient") or {}).get("id") or "") or None
        is_echo = bool(message.get("is_echo"))
        is_deleted = bool(message.get("is_deleted"))

        # O IGSID do usuário é sempre o ID que NÃO é a conta do canal.
        ref_ig_id = channel_ig_id or entry_ig_id
        if ref_ig_id and sender_id == ref_ig_id:
            user_igsid = recipient_id
        elif ref_ig_id and recipient_id == ref_ig_id:
            user_igsid = sender_id
        else:
            # Sem referência confiável: cai no comportamento por echo.
            user_igsid = recipient_id if is_echo else sender_id

        if not user_igsid:
            continue

        message_type = _classify(message)
        out.append(
            {
                "ig_message_id": ig_message_id,
                "user_igsid": user_igsid,
                "direction": "outbound" if is_echo else "inbound",
                "message_type": message_type,
                "content": _build_content(message, message_type),
                "timestamp": parse_timestamp_ms(item.get("timestamp")),
                "is_echo": is_echo,
                "is_deleted": is_deleted,
                "entry_ig_id": entry_ig_id,
            }
        )

    return out


# ============================================================
# Sprint 2 — parsers de evento (comments / reactions / postbacks / mentions)
# ============================================================
def _other_party_igsid(item: dict[str, Any], ref_ig_id: Optional[str]) -> Optional[str]:
    """Dado um messaging[] item, devolve o IGSID que NÃO é a conta do canal (ref_ig_id)."""
    sender_id = str((item.get("sender") or {}).get("id") or "") or None
    recipient_id = str((item.get("recipient") or {}).get("id") or "") or None
    if ref_ig_id and sender_id == ref_ig_id:
        return recipient_id
    if ref_ig_id and recipient_id == ref_ig_id:
        return sender_id
    # Sem referência: assume sender (eventos de evento não vêm em echo).
    return sender_id


def iter_changes(payload: dict[str, Any]):
    """Itera ``(entry_ig_id, field, value)`` cobrindo ``entry[].changes[]`` e o caso em
    que o ``field``/``value`` vêm direto no ``entry`` (variações do webhook do IG)."""
    for entry in payload.get("entry") or []:
        entry_ig_id = str(entry["id"]) if entry.get("id") is not None else None
        for change in entry.get("changes") or []:
            yield entry_ig_id, change.get("field"), change.get("value") or {}
        if entry.get("field") is not None:
            yield entry_ig_id, entry.get("field"), entry.get("value") or {}


def parse_comments(payload: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for entry_ig_id, field, value in iter_changes(payload):
        if field not in ("comments", "live_comments"):
            continue
        comment_id = value.get("id")
        frm = value.get("from") or {}
        user_igsid = str(frm.get("id")) if frm.get("id") is not None else None
        if not comment_id or not user_igsid:
            continue
        # Ignora comentários da própria conta (evita auto-disparo).
        if entry_ig_id and user_igsid == entry_ig_id:
            continue
        media = value.get("media") or {}
        out.append(
            {
                "comment_id": str(comment_id),
                "user_igsid": user_igsid,
                "username": frm.get("username"),
                "text": value.get("text") or "",
                "media_id": str(media.get("id")) if media.get("id") is not None else None,
                "media_product_type": media.get("media_product_type"),
                "entry_ig_id": entry_ig_id,
            }
        )
    return out


def parse_reactions(payload: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for entry_ig_id, item in iter_messaging(payload):
        reaction = item.get("reaction")
        if not reaction:
            continue
        if reaction.get("action") != "react":
            # unreact (ou outra ação) — não dispara.
            continue
        user_igsid = _other_party_igsid(item, entry_ig_id)
        if not user_igsid:
            continue
        out.append(
            {
                "mid": reaction.get("mid"),
                "user_igsid": user_igsid,
                "action": "react",
                "emoji": reaction.get("emoji"),
                "reaction": reaction.get("reaction"),
                "timestamp": parse_timestamp_ms(item.get("timestamp")),
                "entry_ig_id": entry_ig_id,
            }
        )
    return out


def parse_postbacks(payload: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for entry_ig_id, item in iter_messaging(payload):
        postback = item.get("postback")
        if not postback:
            continue
        user_igsid = _other_party_igsid(item, entry_ig_id)
        if not user_igsid:
            continue
        out.append(
            {
                "mid": postback.get("mid"),
                "user_igsid": user_igsid,
                "title": postback.get("title"),
                "payload": postback.get("payload"),
                "timestamp": parse_timestamp_ms(item.get("timestamp")),
                "entry_ig_id": entry_ig_id,
            }
        )
    return out


def parse_mentions(payload: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for entry_ig_id, field, value in iter_changes(payload):
        if field != "mentions":
            continue
        media_id = value.get("media_id")
        comment_id = value.get("comment_id")
        if media_id is None and comment_id is None:
            continue
        # TODO(Sprint futura): GET no mentioned_comment/mentions pra puxar o texto e
        # permitir keyword-match. Hoje a menção dispara sem ler o texto.
        out.append(
            {
                "media_id": str(media_id) if media_id is not None else None,
                "comment_id": str(comment_id) if comment_id is not None else None,
                "entry_ig_id": entry_ig_id,
            }
        )
    return out


def classify_entries(payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Separa o payload do webhook nos buckets de evento pro router consumir."""
    return {
        "messages": parse_inbound_messages(payload),
        "comments": parse_comments(payload),
        "reactions": parse_reactions(payload),
        "postbacks": parse_postbacks(payload),
        "mentions": parse_mentions(payload),
    }
