"""Agregados pro dashboard."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import and_, case, func, select, text

from app.auth import get_current_user
from app.deps import DbSession
from app.models import (
    BroadcastJob,
    Channel,
    ChatbotFlow,
    ChatbotSession,
    Contact,
    Message,
)

router = APIRouter(
    prefix="/api/dashboard",
    tags=["Dashboard"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/stats")
async def stats(db: DbSession):
    now = datetime.now(timezone.utc)
    h24 = now - timedelta(hours=24)
    d7 = now - timedelta(days=7)

    # ------------------ Channels ------------------
    ch_row = (
        await db.execute(
            select(
                func.count(Channel.id),
                func.sum(case((Channel.is_connected, 1), else_=0)),
                func.sum(case((Channel.operation_mode == "ai", 1), else_=0)),
                func.sum(case((Channel.operation_mode == "chatbot", 1), else_=0)),
                func.sum(case((Channel.operation_mode == "none", 1), else_=0)),
            )
        )
    ).one()
    channels_total, channels_connected, mode_ai, mode_chatbot, mode_none = ch_row

    # ------------------ Contacts ------------------
    # Contact.created_at é DateTime naive (UTC em prática)
    h24_naive = h24.replace(tzinfo=None)
    d7_naive = d7.replace(tzinfo=None)
    contacts_total = (await db.execute(select(func.count(Contact.id)))).scalar_one()
    contacts_24h = (
        await db.execute(
            select(func.count(Contact.id)).where(Contact.created_at >= h24_naive)
        )
    ).scalar_one()
    contacts_7d = (
        await db.execute(
            select(func.count(Contact.id)).where(Contact.created_at >= d7_naive)
        )
    ).scalar_one()

    # ------------------ Messages ------------------
    msg_total = (await db.execute(select(func.count(Message.id)))).scalar_one()

    msg_24h = (
        await db.execute(
            select(
                func.sum(case((Message.direction == "inbound", 1), else_=0)),
                func.sum(case((Message.direction == "outbound", 1), else_=0)),
            ).where(Message.timestamp >= h24.replace(tzinfo=None))
        )
    ).one()

    msg_7d = (
        await db.execute(
            select(
                func.sum(case((Message.direction == "inbound", 1), else_=0)),
                func.sum(case((Message.direction == "outbound", 1), else_=0)),
            ).where(Message.timestamp >= d7.replace(tzinfo=None))
        )
    ).one()

    # Série diária dos últimos 7 dias — SQL direto pra evitar problema de GROUP BY
    # com duas expressões "iguais" parametrizadas pelo asyncpg
    msg_series_rows = (
        await db.execute(
            text(
                "SELECT date_trunc('day', timestamp) AS day, "
                "SUM(CASE WHEN direction='inbound' THEN 1 ELSE 0 END) AS inbound, "
                "SUM(CASE WHEN direction='outbound' THEN 1 ELSE 0 END) AS outbound "
                "FROM mensageria.messages "
                "WHERE timestamp >= :since "
                "GROUP BY date_trunc('day', timestamp) "
                "ORDER BY date_trunc('day', timestamp)"
            ),
            {"since": d7.replace(tzinfo=None)},
        )
    ).all()
    msg_series = [
        {
            "day": r.day.date().isoformat() if r.day else None,
            "inbound": int(r.inbound or 0),
            "outbound": int(r.outbound or 0),
        }
        for r in msg_series_rows
    ]

    # ------------------ Chatbot ------------------
    flows_total = (await db.execute(select(func.count(ChatbotFlow.id)))).scalar_one()
    flows_published = (
        await db.execute(
            select(func.count(ChatbotFlow.id)).where(ChatbotFlow.is_published.is_(True))
        )
    ).scalar_one()
    sessions_active = (
        await db.execute(
            select(func.count(ChatbotSession.id)).where(ChatbotSession.status == "active")
        )
    ).scalar_one()
    sessions_completed_24h = (
        await db.execute(
            select(func.count(ChatbotSession.id)).where(
                and_(
                    ChatbotSession.status == "completed",
                    ChatbotSession.completed_at >= h24.replace(tzinfo=None),
                )
            )
        )
    ).scalar_one()

    # ------------------ Broadcasts ------------------
    bc_row = (
        await db.execute(
            select(
                func.count(BroadcastJob.id),
                func.sum(case((BroadcastJob.status == "pending", 1), else_=0)),
                func.sum(case((BroadcastJob.status == "running", 1), else_=0)),
                func.sum(
                    case(
                        (
                            and_(
                                BroadcastJob.status == "completed",
                                BroadcastJob.completed_at >= h24,
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ),
            )
        )
    ).one()
    bc_total, bc_pending, bc_running, bc_completed_24h = bc_row

    return {
        "generated_at": now.isoformat(),
        "channels": {
            "total": channels_total or 0,
            "connected": int(channels_connected or 0),
            "by_mode": {
                "ai": int(mode_ai or 0),
                "chatbot": int(mode_chatbot or 0),
                "none": int(mode_none or 0),
            },
        },
        "contacts": {
            "total": contacts_total or 0,
            "new_24h": contacts_24h or 0,
            "new_7d": contacts_7d or 0,
        },
        "messages": {
            "total": msg_total or 0,
            "last_24h": {
                "inbound": int(msg_24h[0] or 0),
                "outbound": int(msg_24h[1] or 0),
            },
            "last_7d": {
                "inbound": int(msg_7d[0] or 0),
                "outbound": int(msg_7d[1] or 0),
            },
            "series_7d": msg_series,
        },
        "chatbot": {
            "flows_total": flows_total or 0,
            "flows_published": flows_published or 0,
            "sessions_active": sessions_active or 0,
            "sessions_completed_24h": sessions_completed_24h or 0,
        },
        "broadcasts": {
            "total": bc_total or 0,
            "pending": int(bc_pending or 0),
            "running": int(bc_running or 0),
            "completed_24h": int(bc_completed_24h or 0),
        },
    }
