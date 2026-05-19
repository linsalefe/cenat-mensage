from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func as sql_func
from sqlalchemy import select

from app.auth import CurrentUser, get_current_user
from app.deps import DbSession
from app.models import CampaignRun, ChatbotFlow, ContactList

router = APIRouter(
    prefix="/api/campaigns",
    tags=["Campaign"],
    dependencies=[Depends(get_current_user)],
)


class CampaignStart(BaseModel):
    flow_id: int
    channel_id: int
    list_id: int
    batch_interval_seconds: int = 2
    daily_limit: Optional[int] = None


def _run_to_dict(r: CampaignRun) -> dict:
    return {
        "id": r.id,
        "flow_id": r.flow_id,
        "channel_id": r.channel_id,
        "list_id": r.list_id,
        "status": r.status,
        "total_targets": r.total_targets,
        "sessions_created": r.sessions_created,
        "sessions_completed": r.sessions_completed,
        "sessions_failed": r.sessions_failed,
        "batch_interval_seconds": r.batch_interval_seconds,
        "daily_limit": r.daily_limit,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "created_by": r.created_by,
        "error_message": r.error_message,
    }


@router.post("/start", status_code=201)
async def start_campaign(data: CampaignStart, db: DbSession, current_user: CurrentUser):
    flow = await db.get(ChatbotFlow, data.flow_id)
    if not flow:
        raise HTTPException(404, "Fluxo não encontrado")
    if not flow.is_published:
        raise HTTPException(400, "Fluxo precisa estar publicado")
    lst = await db.get(ContactList, data.list_id)
    if not lst:
        raise HTTPException(404, "Lista não encontrada")

    run = CampaignRun(
        flow_id=data.flow_id,
        channel_id=data.channel_id,
        list_id=data.list_id,
        batch_interval_seconds=data.batch_interval_seconds,
        daily_limit=data.daily_limit,
        status="pending",
        created_by=current_user.id,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return _run_to_dict(run)


@router.get("")
async def list_runs(
    db: DbSession,
    flow_id: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = 50,
):
    q = select(CampaignRun)
    if flow_id is not None:
        q = q.where(CampaignRun.flow_id == flow_id)
    if status:
        q = q.where(CampaignRun.status == status)
    q = q.order_by(CampaignRun.created_at.desc()).limit(limit)
    res = await db.execute(q)
    return [_run_to_dict(r) for r in res.scalars().all()]


@router.get("/{run_id}")
async def get_run(run_id: int, db: DbSession):
    r = await db.get(CampaignRun, run_id)
    if not r:
        raise HTTPException(404, "Campaign run não encontrado")
    return _run_to_dict(r)


@router.post("/{run_id}/cancel")
async def cancel_run(run_id: int, db: DbSession):
    r = await db.get(CampaignRun, run_id)
    if not r:
        raise HTTPException(404, "Campaign run não encontrado")
    if r.status not in ("pending", "running"):
        raise HTTPException(400, f"Status atual '{r.status}' não pode ser cancelado")
    r.status = "cancelled"
    await db.commit()
    return _run_to_dict(r)


@router.get("/{run_id}/metrics")
async def metrics(run_id: int, db: DbSession):
    from app.models import ChatbotSession, Message

    r = await db.get(CampaignRun, run_id)
    if not r:
        raise HTTPException(404, "Campaign run não encontrado")

    sess_res = await db.execute(
        select(ChatbotSession.status, sql_func.count(ChatbotSession.id))
        .where(ChatbotSession.campaign_run_id == run_id)
        .group_by(ChatbotSession.status)
    )
    by_status = dict(sess_res.all())

    msg_res = await db.execute(
        select(Message.status, sql_func.count(Message.id))
        .join(ChatbotSession, ChatbotSession.contact_wa_id == Message.contact_wa_id)
        .where(
            ChatbotSession.campaign_run_id == run_id,
            Message.direction == "outbound",
        )
        .group_by(Message.status)
    )
    msg_status = dict(msg_res.all())

    return {
        "run_id": run_id,
        "sessions_by_status": by_status,
        "messages_by_status": msg_status,
        "total_sessions": sum(by_status.values()),
        "delivered": msg_status.get("delivered", 0) + msg_status.get("read", 0),
        "read": msg_status.get("read", 0),
        "failed": msg_status.get("failed", 0),
    }


@router.get("/{run_id}/sessions")
async def list_run_sessions(run_id: int, db: DbSession, limit: int = 100, offset: int = 0):
    from app.models import ChatbotSession

    q = (
        select(ChatbotSession)
        .where(ChatbotSession.campaign_run_id == run_id)
        .order_by(ChatbotSession.started_at.desc())
        .limit(limit)
        .offset(offset)
    )
    res = await db.execute(q)
    return [
        {
            "id": s.id,
            "contact_wa_id": s.contact_wa_id,
            "current_node_id": s.current_node_id,
            "status": s.status,
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "last_interaction_at": s.last_interaction_at.isoformat() if s.last_interaction_at else None,
            "completed_at": s.completed_at.isoformat() if s.completed_at else None,
            "variables": s.variables or {},
        }
        for s in res.scalars().all()
    ]
