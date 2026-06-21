from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

DEFAULT_COLUMNS: list[dict[str, Any]] = [
    {"key": "novo", "label": "Novos Contatos", "color": "#10b981", "order": 0},
    {"key": "em_contato", "label": "Em Contato", "color": "#f59e0b", "order": 1},
    {"key": "qualificado", "label": "Qualificados", "color": "#8b5cf6", "order": 2},
    {"key": "negociando", "label": "Negociando", "color": "#06b6d4", "order": 3},
    {"key": "convertido", "label": "Convertido", "color": "#22c55e", "order": 4},
    {"key": "perdido", "label": "Perdido", "color": "#ef4444", "order": 5},
]


class PipelineColumn(BaseModel):
    key: str
    label: str
    color: str = "#10b981"
    order: int = 0


class PipelineCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    columns: Optional[list[PipelineColumn]] = None


class PipelineUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    columns: Optional[list[PipelineColumn]] = None


class ColumnInput(BaseModel):
    # key ausente/None numa coluna => coluna nova (gera slug do label no servidor).
    key: Optional[str] = None
    label: str = Field(..., min_length=1, max_length=60)
    color: str = "#10b981"
    order: int = 0


class ColumnsUpdate(BaseModel):
    columns: list[ColumnInput] = Field(..., min_length=1)


class PipelineOut(BaseModel):
    id: int
    name: str
    columns: list[dict[str, Any]]
    is_default: bool
    order: int
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class KanbanCardOut(BaseModel):
    id: int
    wa_id: str
    name: Optional[str]
    lead_status: Optional[str]
    pipeline_id: Optional[int]
    channel_id: Optional[int]
    provider: Optional[str]
    deal_value: Optional[float]
    notes: Optional[str]
    is_group: bool
    last_inbound_at: Optional[datetime]
    updated_at: Optional[datetime]


class MoveCardRequest(BaseModel):
    lead_status: str = Field(..., min_length=1)


class CardUpdateRequest(BaseModel):
    name: Optional[str] = None
    notes: Optional[str] = None
    deal_value: Optional[float] = None
    lead_status: Optional[str] = None


class QualifyRequest(BaseModel):
    lead_status: Optional[str] = None   # etapa-alvo; default = 1ª de CRM_QUALIFIED_STAGE_KEYS
