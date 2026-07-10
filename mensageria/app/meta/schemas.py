from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, model_validator


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


class SendMediaRequest(BaseModel):
    to: str = Field(..., min_length=4)
    media_type: str = Field(..., pattern="^(image|audio|video|document)$")
    media_link: Optional[str] = None
    media_base64: Optional[str] = None
    # MediaAsset já salvo via POST /api/media/upload. Caminho preferido do inbox:
    # payload pequeno e o arquivo fica reaproveitável.
    media_id: Optional[int] = None
    mime_type: Optional[str] = None
    filename: Optional[str] = None
    caption: Optional[str] = None

    @model_validator(mode="after")
    def _require_source(self) -> "SendMediaRequest":
        if not self.media_link and not self.media_base64 and self.media_id is None:
            raise ValueError("Informe media_link (URL), media_base64 ou media_id")
        return self


class MetaTemplateOut(BaseModel):
    id: int
    channel_id: int
    name: str
    language: str
    category: Optional[str]
    status: str
    components: Optional[list[dict]]
    meta_template_id: Optional[str]
    last_synced_at: Optional[str]

    class Config:
        from_attributes = True
