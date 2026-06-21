from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, update

import re
import unicodedata

from app.auth import get_current_user
from app.config import get_settings
from app.crm.schemas import (
    DEFAULT_COLUMNS,
    CardUpdateRequest,
    ColumnsUpdate,
    KanbanCardOut,
    MoveCardRequest,
    PipelineCreate,
    PipelineOut,
    PipelineUpdate,
    QualifyRequest,
)
from app.deps import DbSession
from app.meta.conversions import fire_conversion
from app.models import Channel, Contact, Pipeline
from app.service_auth import get_user_or_service

router = APIRouter(
    prefix="/api/crm",
    tags=["CRM"],
    dependencies=[Depends(get_current_user)],
)


# ============================================================
# Pipelines
# ============================================================
@router.get("/pipelines", response_model=list[PipelineOut])
async def list_pipelines(db: DbSession):
    res = await db.execute(select(Pipeline).order_by(Pipeline.order.asc(), Pipeline.id.asc()))
    return list(res.scalars().all())


@router.post("/pipelines", response_model=PipelineOut, status_code=201)
async def create_pipeline(payload: PipelineCreate, db: DbSession):
    cols = (
        [c.model_dump() for c in payload.columns]
        if payload.columns
        else [dict(c) for c in DEFAULT_COLUMNS]
    )
    max_order = (await db.execute(select(func.coalesce(func.max(Pipeline.order), -1)))).scalar()
    pipeline = Pipeline(name=payload.name, columns=cols, is_default=False, order=(max_order or 0) + 1)
    db.add(pipeline)
    await db.commit()
    await db.refresh(pipeline)
    return pipeline


async def _get_pipeline_or_404(db, pipeline_id: int) -> Pipeline:
    p = await db.get(Pipeline, pipeline_id)
    if p is None:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    return p


@router.get("/pipelines/{pipeline_id}", response_model=PipelineOut)
async def get_pipeline(pipeline_id: int, db: DbSession):
    return await _get_pipeline_or_404(db, pipeline_id)


@router.patch("/pipelines/{pipeline_id}", response_model=PipelineOut)
async def update_pipeline(pipeline_id: int, payload: PipelineUpdate, db: DbSession):
    p = await _get_pipeline_or_404(db, pipeline_id)
    if payload.name is not None:
        p.name = payload.name
    if payload.columns is not None:
        p.columns = [c.model_dump() for c in payload.columns]
    await db.commit()
    await db.refresh(p)
    return p


def _slugify(label: str) -> str:
    s = unicodedata.normalize("NFD", label).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"\s+", "_", s.strip().lower())
    s = re.sub(r"[^a-z0-9_]", "", s)
    return s or "coluna"


@router.put("/pipelines/{pipeline_id}/columns", response_model=PipelineOut)
async def update_columns(pipeline_id: int, payload: ColumnsUpdate, db: DbSession):
    """Salva o array de colunas. key imutável; coluna nova vira slug; coluna removida
    realoca os contatos pra 1ª coluna (sem deixar lead_status órfão)."""
    p = await _get_pipeline_or_404(db, pipeline_id)
    existing_keys = {c.get("key") for c in (p.columns or []) if isinstance(c, dict)}

    new_cols: list[dict] = []
    used: set[str] = set()
    for idx, col in enumerate(payload.columns):
        if col.key and col.key in existing_keys:
            key = col.key  # key estável
        else:
            base = _slugify(col.label)
            key = base
            n = 2
            while key in used:
                key = f"{base}_{n}"
                n += 1
        used.add(key)
        new_cols.append({"key": key, "label": col.label, "color": col.color, "order": idx})

    first_key = new_cols[0]["key"]
    removed = existing_keys - {c["key"] for c in new_cols}
    if removed:
        await db.execute(
            update(Contact)
            .where(Contact.pipeline_id == pipeline_id, Contact.lead_status.in_(removed))
            .values(lead_status=first_key)
        )

    p.columns = new_cols
    await db.commit()
    await db.refresh(p)
    return p


@router.delete("/pipelines/{pipeline_id}", status_code=204)
async def delete_pipeline(pipeline_id: int, db: DbSession):
    p = await _get_pipeline_or_404(db, pipeline_id)
    if p.is_default:
        raise HTTPException(status_code=400, detail="Não é possível excluir o funil padrão")
    # Reatribui os contatos ao funil padrão (coluna "novo") antes de excluir.
    default_id = (
        await db.execute(select(Pipeline.id).where(Pipeline.is_default.is_(True)).limit(1))
    ).scalar_one_or_none()
    await db.execute(
        update(Contact)
        .where(Contact.pipeline_id == pipeline_id)
        .values(pipeline_id=default_id, lead_status="novo")
    )
    await db.execute(
        update(Channel)
        .where(Channel.default_pipeline_id == pipeline_id)
        .values(default_pipeline_id=default_id)
    )
    await db.delete(p)
    await db.commit()


# ============================================================
# Kanban (cards = Contacts)
# ============================================================
def _card(contact: Contact, provider: Optional[str]) -> KanbanCardOut:
    return KanbanCardOut(
        id=contact.id,
        wa_id=contact.wa_id,
        name=contact.name,
        lead_status=contact.lead_status,
        pipeline_id=contact.pipeline_id,
        channel_id=contact.channel_id,
        provider=provider,
        deal_value=float(contact.deal_value) if contact.deal_value is not None else None,
        notes=contact.notes,
        is_group=bool(contact.is_group),
        last_inbound_at=contact.last_inbound_at,
        updated_at=contact.updated_at,
    )


@router.get("/kanban/cards", response_model=list[KanbanCardOut])
async def list_cards(
    db: DbSession,
    pipeline_id: Optional[int] = None,
    channel_id: Optional[int] = None,
    provider: Optional[str] = None,
):
    q = (
        select(Contact, Channel.provider)
        .outerjoin(Channel, Contact.channel_id == Channel.id)
        .order_by(Contact.updated_at.desc().nullslast(), Contact.id.desc())
    )
    if pipeline_id is not None:
        q = q.where(Contact.pipeline_id == pipeline_id)
    if channel_id is not None:
        q = q.where(Contact.channel_id == channel_id)
    if provider:
        q = q.where(Channel.provider == provider)
    res = await db.execute(q)
    return [_card(contact, prov) for contact, prov in res.all()]


@router.get("/kanban/stats")
async def kanban_stats(db: DbSession, pipeline_id: Optional[int] = None):
    q = select(Contact.lead_status, func.count(Contact.id))
    if pipeline_id is not None:
        q = q.where(Contact.pipeline_id == pipeline_id)
    q = q.group_by(Contact.lead_status)
    rows = (await db.execute(q)).all()
    by_status = {(r[0] or "novo"): r[1] for r in rows}
    return {"total": sum(by_status.values()), "by_status": by_status}


async def _get_contact_or_404(db, contact_id: int) -> Contact:
    c = await db.get(Contact, contact_id)
    if c is None:
        raise HTTPException(status_code=404, detail="Card (contato) não encontrado")
    return c


def _valid_keys(pipeline: Optional[Pipeline]) -> set[str]:
    cols = (pipeline.columns if pipeline else None) or DEFAULT_COLUMNS
    return {c.get("key") for c in cols if isinstance(c, dict)}


def _won_stage_keys() -> set[str]:
    raw = get_settings().CRM_WON_STAGE_KEYS or ""
    return {k.strip() for k in raw.split(",") if k.strip()}


def _qualified_stage_keys() -> set[str]:
    raw = get_settings().CRM_QUALIFIED_STAGE_KEYS or ""
    return {k.strip() for k in raw.split(",") if k.strip()}


def _stage_event(lead_status: str) -> "tuple[str, bool] | None":
    """(event_name, usa_valor) se a etapa dispara conversao; senao None."""
    if lead_status in _won_stage_keys():
        return ("Purchase", True)
    if lead_status in _qualified_stage_keys():
        return ("LeadSubmitted", False)
    return None


@router.patch("/kanban/cards/{contact_id}/move")
async def move_card(contact_id: int, payload: MoveCardRequest, db: DbSession):
    contact = await _get_contact_or_404(db, contact_id)
    pipeline = await db.get(Pipeline, contact.pipeline_id) if contact.pipeline_id else None
    keys = _valid_keys(pipeline)
    if payload.lead_status not in keys:
        raise HTTPException(
            status_code=400,
            detail=f"Etapa inválida '{payload.lead_status}'. Válidas: {sorted(keys)}",
        )
    contact.lead_status = payload.lead_status
    # capturar ANTES do commit (evita expiry async)
    trigger = _stage_event(payload.lead_status)   # generaliza Purchase (S3) + LeadSubmitted (S4)
    clid = contact.ctwa_clid
    cid = contact.channel_id
    wa = contact.wa_id
    deal = float(contact.deal_value) if contact.deal_value is not None else None
    await db.commit()
    if trigger and clid:
        name, usa_valor = trigger
        await fire_conversion(
            db, contact_wa_id=wa, ctwa_clid=clid, channel_id=cid,
            event_name=name, value=(deal if usa_valor else None),
        )
    return {"status": "moved", "lead_status": payload.lead_status}


@router.patch("/kanban/cards/{contact_id}", response_model=KanbanCardOut)
async def update_card(contact_id: int, payload: CardUpdateRequest, db: DbSession):
    contact = await _get_contact_or_404(db, contact_id)
    if payload.name is not None:
        contact.name = payload.name
    if payload.notes is not None:
        contact.notes = payload.notes
    if payload.deal_value is not None:
        contact.deal_value = payload.deal_value
    trigger = None
    clid = cid = wa = deal = None
    if payload.lead_status is not None:
        pipeline = await db.get(Pipeline, contact.pipeline_id) if contact.pipeline_id else None
        if payload.lead_status not in _valid_keys(pipeline):
            raise HTTPException(status_code=400, detail="Etapa inválida")
        contact.lead_status = payload.lead_status
        # capturar ANTES do commit (evita expiry async)
        trigger = _stage_event(payload.lead_status)
        clid = contact.ctwa_clid
        cid = contact.channel_id
        wa = contact.wa_id
        deal = float(contact.deal_value) if contact.deal_value is not None else None
    await db.commit()
    if trigger and clid:
        name, usa_valor = trigger
        await fire_conversion(
            db, contact_wa_id=wa, ctwa_clid=clid, channel_id=cid,
            event_name=name, value=(deal if usa_valor else None),
        )
    await db.refresh(contact)
    provider = None
    if contact.channel_id:
        provider = (
            await db.execute(select(Channel.provider).where(Channel.id == contact.channel_id))
        ).scalar_one_or_none()
    return _card(contact, provider)


# ============================================================
# Bridge (JWT OU X-Service-Token) — Customer 360 chama
# ============================================================
bridge_router = APIRouter(
    prefix="/api/crm",
    tags=["CRM Bridge"],
    dependencies=[Depends(get_user_or_service)],
)


@bridge_router.post("/contacts/{wa_id}/qualify")
async def qualify_contact(wa_id: str, db: DbSession, payload: QualifyRequest | None = None):
    contact = (await db.execute(select(Contact).where(Contact.wa_id == wa_id))).scalar_one_or_none()
    if contact is None:
        raise HTTPException(status_code=404, detail="contato não encontrado")

    # move pra etapa qualificado (se valida no pipeline) — reflete no kanban
    target = (payload.lead_status if payload and payload.lead_status
              else next(iter(_qualified_stage_keys()), None))
    moved = False
    if target:
        pipeline = await db.get(Pipeline, contact.pipeline_id) if contact.pipeline_id else None
        if target in _valid_keys(pipeline):
            contact.lead_status = target
            moved = True

    clid, cid, wa = contact.ctwa_clid, contact.channel_id, contact.wa_id
    await db.commit()

    status_evento = "skip_sem_clid"
    if clid:
        ev = await fire_conversion(db, contact_wa_id=wa, ctwa_clid=clid, channel_id=cid,
                                   event_name="LeadSubmitted", value=None)
        status_evento = ev.status if ev else "dedup"
    return {"status": "qualified", "moved": moved, "evento": status_evento}
