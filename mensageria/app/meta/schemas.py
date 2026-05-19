from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ChannelCreateMeta(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    phone_number: str = Field(..., min_length=4, max_length=20)
    phone_number_id: str = Field(..., min_length=4, max_length=50)
    waba_id: str = Field(..., min_length=4, max_length=50)
    whatsapp_token: str = Field(..., min_length=10)
    operation_mode: str = Field(default="none")


class ChannelUpdateMeta(BaseModel):
    name: Optional[str] = None
    whatsapp_token: Optional[str] = None
    is_active: Optional[bool] = None
    operation_mode: Optional[str] = None


class ChannelOutMeta(BaseModel):
    id: int
    name: str
    phone_number: Optional[str]
    phone_number_id: Optional[str]
    waba_id: Optional[str]
    provider: str
    is_connected: bool
    is_active: bool
    operation_mode: str

    class Config:
        from_attributes = True


class SendTextRequest(BaseModel):
    to: str = Field(..., min_length=4)
    text: str = Field(..., min_length=1)


class SendTemplateRequest(BaseModel):
    to: str = Field(..., min_length=4)
    template_name: str = Field(..., min_length=1)
    language_code: str = Field(default="pt_BR")
    components: Optional[list[dict]] = None
