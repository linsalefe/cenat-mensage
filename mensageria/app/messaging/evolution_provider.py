from __future__ import annotations

import base64
import uuid

from app.evolution import client as evo_client
from app.messaging.types import OutboundMedia, SendResult
from app.models import Channel


class EvolutionProvider:
    name = "evolution"

    async def send_text(
        self,
        channel: Channel,
        to: str,
        text: str,
    ) -> SendResult:
        if not channel.instance_name:
            raise ValueError(f"Channel {channel.id} sem instance_name (Evolution)")

        raw = await evo_client.send_text(channel.instance_name, to, text)
        wa_message_id = _extract_wa_id(raw)
        return SendResult(wa_message_id=wa_message_id, raw_response=raw)

    async def send_media(
        self,
        channel: Channel,
        to: str,
        media: OutboundMedia,
    ) -> SendResult:
        if not channel.instance_name:
            raise ValueError(f"Channel {channel.id} sem instance_name (Evolution)")
        if not media.asset_path:
            raise ValueError("Evolution requer asset local (base64)")

        with open(media.asset_path, "rb") as fh:
            media_b64 = base64.b64encode(fh.read()).decode("ascii")

        raw = await evo_client.send_media(
            instance_name=channel.instance_name,
            to=to,
            media_type=media.media_type,
            media_base64=media_b64,
            caption=media.caption,
            filename=media.filename,
            mimetype=media.mime_type,
        )
        wa_message_id = _extract_wa_id(raw)
        return SendResult(wa_message_id=wa_message_id, raw_response=raw)

    async def send_template(self, *args, **kwargs):
        raise NotImplementedError("Evolution não suporta templates")


def _extract_wa_id(evo_response: dict) -> str:
    key = evo_response.get("key") or {}
    msg_id = key.get("id")
    if msg_id:
        return str(msg_id)
    msg_id = evo_response.get("messageId") or evo_response.get("id")
    if msg_id:
        return str(msg_id)
    return f"evo_unknown_{uuid.uuid4().hex[:16]}"
