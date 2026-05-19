from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class SendResult:
    wa_message_id: str
    raw_response: dict[str, Any] = field(default_factory=dict)


@dataclass
class OutboundMedia:
    media_type: str
    asset_path: Optional[str] = None
    mime_type: Optional[str] = None
    filename: Optional[str] = None
    caption: Optional[str] = None
    media_link: Optional[str] = None
