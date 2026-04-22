"""CRUD de BroadcastJob (Fase 5.1).

Não executa jobs ainda — só cria/lista/cancela. A execução real (envio ao
WhatsApp com intervalo anti-ban) será implementada na Fase 5.3 dentro do
scheduler.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.auth import CurrentUser, get_current_user
from app.deps import DbSession
from app.models import BroadcastJob, BroadcastLog, Channel, ChatbotFlow, MediaAsset

router = APIRouter(
    prefix="/api/broadcasts",
    tags=["Broadcast"],
    dependencies=[Depends(get_current_user)],
)


_VALID_AUDIENCE = {
    "all_groups",
    "selected_groups",
    "contacts_tag",
    "csv",
    "single_contact",
}


class MessagePayload(BaseModel):
    text: Optional[str] = None
    media_id: Optional[int] = None
    caption: Optional[str] = None


class BroadcastCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    channel_id: int
    audience_type: Literal[
        "all_groups", "selected_groups", "contacts_tag", "csv", "single_contact"
    ]
    audience_spec: dict[str, Any] = Field(default_factory=dict)
    message_payload: MessagePayload
    flow_id: Optional[int] = None
    interval_seconds: int = Field(default=5, ge=1, le=300)
    scheduled_at: Optional[datetime] = None


def _job_to_dict(j: BroadcastJob) -> dict:
    return {
        "id": j.id,
        "name": j.name,
        "flow_id": j.flow_id,
        "channel_id": j.channel_id,
        "audience_type": j.audience_type,
        "audience_spec": j.audience_spec,
        "message_payload": j.message_payload,
        "interval_seconds": j.interval_seconds,
        "scheduled_at": j.scheduled_at.isoformat() if j.scheduled_at else None,
        "recurrence": j.recurrence,
        "status": j.status,
        "total_targets": j.total_targets,
        "sent_count": j.sent_count,
        "error_count": j.error_count,
        "started_at": j.started_at.isoformat() if j.started_at else None,
        "completed_at": j.completed_at.isoformat() if j.completed_at else None,
        "created_at": j.created_at.isoformat() if j.created_at else None,
        "updated_at": j.updated_at.isoformat() if j.updated_at else None,
        "created_by": j.created_by,
        "error_message": j.error_message,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_broadcast(
    data: BroadcastCreate, db: DbSession, current_user: CurrentUser
):
    # Valida channel
    ch_res = await db.execute(
        select(Channel).where(Channel.id == data.channel_id)
    )
    channel = ch_res.scalar_one_or_none()
    if not channel:
        raise HTTPException(
            status_code=404, detail=f"Canal {data.channel_id} não encontrado"
        )

    # Valida flow se informado
    if data.flow_id is not None:
        flow_res = await db.execute(
            select(ChatbotFlow).where(ChatbotFlow.id == data.flow_id)
        )
        if flow_res.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=404, detail=f"Flow {data.flow_id} não encontrado"
            )

    # Valida scheduled_at futuro
    if data.scheduled_at is not None:
        now_utc = datetime.now(timezone.utc)
        if data.scheduled_at <= now_utc:
            raise HTTPException(
                status_code=400,
                detail="scheduled_at deve estar no futuro",
            )

    # Resolve media_id → media_url
    payload_dict = data.message_payload.model_dump(exclude_none=True)
    if data.message_payload.media_id is not None:
        media_res = await db.execute(
            select(MediaAsset).where(MediaAsset.id == data.message_payload.media_id)
        )
        asset = media_res.scalar_one_or_none()
        if not asset:
            raise HTTPException(
                status_code=404,
                detail=f"Mídia {data.message_payload.media_id} não encontrada",
            )
        payload_dict["media_url"] = f"/api/media/{asset.id}"
        payload_dict["media_type"] = asset.media_type
        payload_dict["media_mime"] = asset.mime_type

    if not payload_dict.get("text") and "media_id" not in payload_dict:
        raise HTTPException(
            status_code=400, detail="message_payload precisa de text ou media_id"
        )

    job = BroadcastJob(
        flow_id=data.flow_id,
        channel_id=data.channel_id,
        name=data.name,
        audience_type=data.audience_type,
        audience_spec=data.audience_spec,
        message_payload=payload_dict,
        interval_seconds=data.interval_seconds,
        scheduled_at=data.scheduled_at,
        status="pending",
        created_by=current_user.id,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return _job_to_dict(job)


@router.get("")
async def list_broadcasts(
    db: DbSession,
    status: Optional[str] = None,
    channel_id: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
):
    limit = max(1, min(limit, 200))
    offset = max(0, offset)

    q = select(BroadcastJob)
    if status:
        q = q.where(BroadcastJob.status == status)
    if channel_id:
        q = q.where(BroadcastJob.channel_id == channel_id)
    q = q.order_by(BroadcastJob.created_at.desc()).limit(limit).offset(offset)

    res = await db.execute(q)
    return [_job_to_dict(j) for j in res.scalars().all()]


@router.get("/{job_id}")
async def get_broadcast(job_id: int, db: DbSession):
    res = await db.execute(select(BroadcastJob).where(BroadcastJob.id == job_id))
    job = res.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Broadcast não encontrado")
    return _job_to_dict(job)


@router.get("/{job_id}/logs")
async def get_broadcast_logs(
    job_id: int, db: DbSession, limit: int = 100, offset: int = 0
):
    limit = max(1, min(limit, 500))
    offset = max(0, offset)

    job_res = await db.execute(select(BroadcastJob).where(BroadcastJob.id == job_id))
    if job_res.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Broadcast não encontrado")

    q = (
        select(BroadcastLog)
        .where(BroadcastLog.job_id == job_id)
        .order_by(BroadcastLog.sent_at.desc())
        .limit(limit)
        .offset(offset)
    )
    res = await db.execute(q)
    return [
        {
            "id": log.id,
            "job_id": log.job_id,
            "target_wa_id": log.target_wa_id,
            "target_name": log.target_name,
            "status": log.status,
            "error_detail": log.error_detail,
            "sent_at": log.sent_at.isoformat() if log.sent_at else None,
        }
        for log in res.scalars().all()
    ]


@router.post("/{job_id}/cancel")
async def cancel_broadcast(job_id: int, db: DbSession):
    res = await db.execute(select(BroadcastJob).where(BroadcastJob.id == job_id))
    job = res.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Broadcast não encontrado")
    if job.status not in ("pending", "running"):
        raise HTTPException(
            status_code=400,
            detail=f"Job em status '{job.status}' não pode ser cancelado",
        )
    job.status = "cancelled"
    job.completed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(job)
    return _job_to_dict(job)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_broadcast(job_id: int, db: DbSession, current_user: CurrentUser):
    res = await db.execute(select(BroadcastJob).where(BroadcastJob.id == job_id))
    job = res.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Broadcast não encontrado")
    if not current_user.is_admin and job.created_by != current_user.id:
        raise HTTPException(
            status_code=403, detail="Sem permissão para excluir este broadcast"
        )
    await db.delete(job)
    await db.commit()
