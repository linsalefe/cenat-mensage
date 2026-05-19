from __future__ import annotations

from app.meta import client as meta_client
from app.messaging.types import OutboundMedia, SendResult
from app.models import Channel


class MetaProvider:
    name = "official"

    async def send_text(
        self,
        channel: Channel,
        to: str,
        text: str,
    ) -> SendResult:
        if not channel.phone_number_id or not channel.whatsapp_token:
            raise ValueError(f"Channel {channel.id} sem phone_number_id/whatsapp_token")

        raw = await meta_client.send_text(
            phone_number_id=channel.phone_number_id,
            token=channel.whatsapp_token,
            to=to,
            text=text,
        )
        wa_message_id = _extract_wa_id(raw)
        return SendResult(wa_message_id=wa_message_id, raw_response=raw)

    async def send_media(
        self,
        channel: Channel,
        to: str,
        media: OutboundMedia,
    ) -> SendResult:
        if not channel.phone_number_id or not channel.whatsapp_token:
            raise ValueError(f"Channel {channel.id} sem phone_number_id/whatsapp_token")

        media_id = None
        if media.asset_path and media.mime_type:
            upload = await meta_client.upload_media(
                phone_number_id=channel.phone_number_id,
                token=channel.whatsapp_token,
                file_path=media.asset_path,
                mime_type=media.mime_type,
            )
            media_id = upload.get("id")
            if not media_id:
                raise RuntimeError(f"Meta upload_media falhou: {upload}")

        raw = await meta_client.send_media(
            phone_number_id=channel.phone_number_id,
            token=channel.whatsapp_token,
            to=to,
            media_type=media.media_type,
            media_id=media_id,
            media_link=media.media_link if not media_id else None,
            caption=media.caption,
            filename=media.filename,
        )
        wa_message_id = _extract_wa_id(raw)
        return SendResult(wa_message_id=wa_message_id, raw_response=raw)


def _extract_wa_id(graph_response: dict) -> str:
    messages = graph_response.get("messages") or []
    if messages and isinstance(messages, list):
        first = messages[0]
        msg_id = first.get("id")
        if msg_id:
            return str(msg_id)
    raise RuntimeError(f"Meta response sem messages[0].id: {graph_response}")
