from __future__ import annotations

from app.instagram import client as ig_client
from app.messaging.types import OutboundMedia, SendResult
from app.models import Channel

# Send API do IG usa "file" onde o WhatsApp usa "document".
_MEDIA_TYPE_MAP = {
    "image": "image",
    "audio": "audio",
    "video": "video",
    "document": "file",
    "file": "file",
}


def _strip_ig_prefix(igsid: str) -> str:
    """O prefixo ``ig:`` é interno do banco; a Graph API quer o IGSID puro."""
    return igsid[3:] if igsid.startswith("ig:") else igsid


class InstagramProvider:
    name = "instagram"

    async def send_text(
        self,
        channel: Channel,
        to: str,
        text: str,
    ) -> SendResult:
        if not channel.instagram_id or not channel.access_token:
            raise ValueError(f"Channel {channel.id} sem instagram_id/access_token")

        raw = await ig_client.send_text(
            ig_id=channel.instagram_id,
            token=channel.access_token,
            to_igsid=_strip_ig_prefix(to),
            text=text,
        )
        return SendResult(wa_message_id=_extract_message_id(raw), raw_response=raw)

    async def send_media(
        self,
        channel: Channel,
        to: str,
        media: OutboundMedia,
    ) -> SendResult:
        if not channel.instagram_id or not channel.access_token:
            raise ValueError(f"Channel {channel.id} sem instagram_id/access_token")

        if not media.media_link:
            # Upload de asset local pro IG fica pra depois (Sprint 2/3).
            raise NotImplementedError("upload local IG fica pra depois — use media_link (URL)")

        media_type = _MEDIA_TYPE_MAP.get(media.media_type)
        if media_type is None:
            raise ValueError(f"media_type não suportado no IG: {media.media_type}")

        raw = await ig_client.send_attachment(
            ig_id=channel.instagram_id,
            token=channel.access_token,
            to_igsid=_strip_ig_prefix(to),
            media_type=media_type,
            url=media.media_link,
        )
        return SendResult(wa_message_id=_extract_message_id(raw), raw_response=raw)

    async def send_template(
        self,
        channel: Channel,
        to: str,
        template_name: str,
        language_code: str = "pt_BR",
        components: list[dict] | None = None,
    ) -> SendResult:
        raise NotImplementedError("Instagram não usa templates como o WhatsApp")


def _extract_message_id(raw: dict) -> str:
    # Sucesso do IG: {"recipient_id": "...", "message_id": "<MID>"} —
    # campo é "message_id" (não messages[0].id como no WhatsApp).
    msg_id = raw.get("message_id")
    if msg_id:
        return str(msg_id)
    raise RuntimeError(f"Instagram response sem message_id: {raw}")
