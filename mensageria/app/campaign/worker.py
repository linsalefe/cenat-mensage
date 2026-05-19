from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.chatbot.engine import _advance_from, find_next_node
from app.database import AsyncSessionLocal
from app.models import (
    CampaignRun,
    Channel,
    ChatbotFlow,
    ChatbotSession,
    Contact,
    ContactListMember,
)

logger = logging.getLogger(__name__)

POLL_INTERVAL = 5
_worker_started = False


async def start_campaign_worker():
    global _worker_started
    if _worker_started:
        return
    _worker_started = True
    print(f"📡 Campaign worker started (poll={POLL_INTERVAL}s)", flush=True)
    while True:
        try:
            async with AsyncSessionLocal() as db:
                run = await _pick_next(db)
                if run is None:
                    await asyncio.sleep(POLL_INTERVAL)
                    continue
                await _execute(run, db)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Campaign worker erro: %s", exc)
            await asyncio.sleep(30)


async def _pick_next(db):
    stmt = (
        select(CampaignRun)
        .where(CampaignRun.status == "pending")
        .order_by(CampaignRun.created_at.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    res = await db.execute(stmt)
    run = res.scalar_one_or_none()
    if run is None:
        return None
    run.status = "running"
    run.started_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(run)
    return run


async def _execute(run: CampaignRun, db):
    print(f"📡 Iniciando campaign run #{run.id} (flow={run.flow_id}, list={run.list_id})", flush=True)

    flow = await db.get(ChatbotFlow, run.flow_id)
    if not flow or not flow.is_published or not flow.published_graph:
        await _fail(run, db, "Fluxo não publicado")
        return
    channel = await db.get(Channel, run.channel_id)
    if not channel:
        await _fail(run, db, "Canal não encontrado")
        return

    graph = flow.published_graph
    trigger_node = next(
        (
            n
            for n in (graph.get("nodes") or [])
            if (n.get("type") or (n.get("data") or {}).get("kind")) == "audience_trigger"
        ),
        None,
    )
    if not trigger_node:
        await _fail(run, db, "Fluxo campaign sem audience_trigger")
        return

    first_node = find_next_node(graph, trigger_node["id"])
    if not first_node:
        await _fail(run, db, "audience_trigger sem nó seguinte")
        return

    if not run.list_id:
        await _fail(run, db, "Campaign sem list_id")
        return

    members_res = await db.execute(
        select(ContactListMember).where(
            ContactListMember.list_id == run.list_id,
            ContactListMember.opted_out.is_(False),
        )
    )
    members = members_res.scalars().all()

    if not members:
        await _fail(run, db, "Lista vazia ou todos opted-out")
        return

    run.total_targets = len(members)
    await db.commit()

    daily_count = 0
    for m in members:
        await db.refresh(run)
        if run.status == "cancelled":
            print(f"📡 Campaign run #{run.id} cancelada", flush=True)
            run.completed_at = datetime.now(timezone.utc)
            await db.commit()
            return
        if run.daily_limit and daily_count >= run.daily_limit:
            print(f"📡 Campaign run #{run.id} atingiu daily_limit {run.daily_limit}", flush=True)
            break

        cres = await db.execute(select(Contact).where(Contact.wa_id == m.wa_id))
        contact = cres.scalar_one_or_none()
        if not contact:
            contact = Contact(
                wa_id=m.wa_id,
                name=m.name or m.wa_id,
                channel_id=channel.id,
                lead_status="novo",
                ai_active=False,
                reengagement_count=0,
                is_group=False,
            )
            db.add(contact)
            await db.flush()

        custom_vars = dict(m.custom_vars or {})
        if m.name:
            custom_vars = {"nome": m.name, **custom_vars}

        session = ChatbotSession(
            flow_id=flow.id,
            channel_id=channel.id,
            contact_wa_id=m.wa_id,
            current_node_id=str(trigger_node["id"]),
            variables=custom_vars,
            status="active",
            campaign_run_id=run.id,
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)

        try:
            await _advance_from(session, first_node, graph, channel, contact, db)
            run.sessions_created += 1
            daily_count += 1
        except Exception as exc:
            print(f"❌ Campaign run #{run.id} falhou pra {m.wa_id}: {exc}", flush=True)
            run.sessions_failed += 1
        await db.commit()

        if m is not members[-1]:
            await asyncio.sleep(run.batch_interval_seconds)

    await db.refresh(run)
    if run.status != "cancelled":
        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
        await db.commit()
        print(
            f"📡 Campaign run #{run.id} concluída: {run.sessions_created} criadas, {run.sessions_failed} falhas",
            flush=True,
        )


async def _fail(run, db, reason: str):
    run.status = "failed"
    run.error_message = reason
    run.completed_at = datetime.now(timezone.utc)
    await db.commit()
    print(f"❌ Campaign run #{run.id} falhou: {reason}", flush=True)
