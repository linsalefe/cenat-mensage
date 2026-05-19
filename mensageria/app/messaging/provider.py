from __future__ import annotations

from typing import Protocol

from app.messaging.types import OutboundMedia, SendResult
from app.models import Channel


class MessagingProvider(Protocol):
    name: str

    async def send_text(
        self,
        channel: Channel,
        to: str,
        text: str,
    ) -> SendResult:
        ...

    async def send_media(
        self,
        channel: Channel,
        to: str,
        media: OutboundMedia,
    ) -> SendResult:
        ...

    async def send_template(
        self,
        channel: Channel,
        to: str,
        template_name: str,
        language_code: str = "pt_BR",
        components: list[dict] | None = None,
    ) -> SendResult:
        ...


def get_provider(channel: Channel) -> MessagingProvider:
    provider_name = (channel.provider or "").lower()
    if provider_name in ("official", "meta", "cloud"):
        from app.messaging.meta_provider import MetaProvider
        return MetaProvider()
    if provider_name == "evolution":
        from app.messaging.evolution_provider import EvolutionProvider
        return EvolutionProvider()
    raise ValueError(f"unknown provider: {channel.provider!r}")
