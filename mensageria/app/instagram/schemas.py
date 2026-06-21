from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

TriggerType = Literal["dm_received", "comment", "reaction", "postback", "mention", "story_reply"]
ActionType = Literal["send_dm", "private_reply", "public_comment_reply"]


class ChannelCreateInstagram(BaseModel):
    name: Optional[str] = Field(default=None, max_length=100)
    instagram_id: str = Field(..., min_length=2, max_length=50)
    page_id: Optional[str] = Field(default=None, max_length=50)
    access_token: str = Field(..., min_length=10)
    username: Optional[str] = Field(default=None, max_length=100)


class ChannelUpdateInstagram(BaseModel):
    name: Optional[str] = None
    access_token: Optional[str] = None
    is_active: Optional[bool] = None


class ChannelOutInstagram(BaseModel):
    id: int
    name: str
    instagram_id: Optional[str]
    page_id: Optional[str]
    provider: str
    type: str
    is_connected: bool
    is_active: bool
    operation_mode: str

    class Config:
        from_attributes = True


class SendTextRequest(BaseModel):
    # IGSID do destinatário — com ou sem o prefixo interno "ig:" (removido no router).
    to: str = Field(..., min_length=2)
    text: str = Field(..., min_length=1)


# ============================================================
# Automações por evento (Sprint 2)
# ============================================================
class InstagramAutomationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    trigger_type: TriggerType
    trigger_config: dict[str, Any] = Field(default_factory=dict)
    action_type: ActionType
    action_config: dict[str, Any] = Field(default_factory=dict)
    once_per_contact: bool = True
    is_active: bool = True
    priority: int = 100


class InstagramAutomationUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    trigger_type: Optional[TriggerType] = None
    trigger_config: Optional[dict[str, Any]] = None
    action_type: Optional[ActionType] = None
    action_config: Optional[dict[str, Any]] = None
    once_per_contact: Optional[bool] = None
    is_active: Optional[bool] = None
    priority: Optional[int] = None


class InstagramAutomationOut(BaseModel):
    id: int
    channel_id: int
    name: str
    trigger_type: str
    trigger_config: dict[str, Any]
    action_type: str
    action_config: dict[str, Any]
    once_per_contact: bool
    is_active: bool
    priority: int
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class InstagramAutomationExecutionOut(BaseModel):
    id: int
    automation_id: int
    channel_id: Optional[int]
    trigger_ref: str
    contact_wa_id: Optional[str]
    status: str
    detail: Optional[str]
    created_at: Optional[datetime]

    class Config:
        from_attributes = True
