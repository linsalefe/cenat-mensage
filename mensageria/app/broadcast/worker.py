import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.broadcast.audience_resolver import resolve_audience
from app.database import AsyncSessionLocal
from app.evolution.client import load_media_as_base64, send_media, send_text
from app.models import BroadcastJob, BroadcastLog, Channel, MediaAsset

logger = logging.getLogger(__name__)

POLL_INTERVAL = 10
RETRY_DELAYS = [5, 15]

_worker_started = False


async def start_broadcast_worker():
    global _worker_started
    if _worker_started:
        logger.warning("Broadcast worker already started, skipping")
        return
    _worker_started = True
    try:
        await _startup_recovery()
    except Exception as e:
        logger.exception("Crash recovery failed: %s", e)
    await _worker_loop()


async def _startup_recovery():
    async with AsyncSessionLocal() as db:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
        result = await db.execute(
            update(BroadcastJob)
            .where(
                BroadcastJob.status == "running",
                BroadcastJob.updated_at < cutoff,
            )
            .values(status="pending", started_at=None)
            .returning(BroadcastJob.id)
        )
        ids = [r[0] for r in result.all()]
        if ids:
            logger.warning("Recovered stuck jobs: %s", ids)
        await db.commit()


async def _worker_loop():
    print(f"📡 Broadcast worker started (poll={POLL_INTERVAL}s)", flush=True)
    logger.info("Broadcast worker started (poll=%ds)", POLL_INTERVAL)
    while True:
        try:
            async with AsyncSessionLocal() as db:
                job = await _pick_next_job(db)
                if job is None:
                    await asyncio.sleep(POLL_INTERVAL)
                    continue
                await _execute_job(job, db)
        except asyncio.CancelledError:
            logger.info("Broadcast worker cancelled")
            raise
        except Exception as e:
            logger.exception("Worker loop error: %s", e)
            await asyncio.sleep(30)


async def _pick_next_job(db: AsyncSession):
    now = datetime.now(timezone.utc)
    stmt = (
        select(BroadcastJob)
        .where(
            BroadcastJob.status == "pending",
            (BroadcastJob.scheduled_at.is_(None)) | (BroadcastJob.scheduled_at <= now),
        )
        .order_by(BroadcastJob.created_at.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    result = await db.execute(stmt)
    job = result.scalar_one_or_none()
    if job is None:
        return None
    job.status = "running"
    job.started_at = now
    await db.commit()
    await db.refresh(job)
    return job


async def _execute_job(job, db: AsyncSession):
    logger.info("Executing job %d: %s", job.id, job.name)
    try:
        channel = await db.get(Channel, job.channel_id)
        if channel is None:
            await _fail_job(job, db, "Canal não encontrado")
            return

        try:
            targets = await resolve_audience(
                job.audience_type, job.audience_spec or {}, channel, db
            )
        except NotImplementedError as e:
            await _fail_job(job, db, f"Tipo de audiência não implementado: {e}")
            return

        if not targets:
            await _fail_job(job, db, "Audiência vazia")
            return

        job.total_targets = len(targets)
        await db.commit()

        payload = job.message_payload or {}
        media_b64 = None
        media_asset = None
        if payload.get("media_id"):
            media_asset = await db.get(MediaAsset, payload["media_id"])
            if media_asset:
                media_b64 = await load_media_as_base64(media_asset)

        for target in targets:
            await db.refresh(job)
            if job.status == "cancelled":
                logger.info("Job %d cancelled mid-flight", job.id)
                job.completed_at = datetime.now(timezone.utc)
                await db.commit()
                return

            await _send_to_target(
                job, target, channel, payload, media_asset, media_b64, db
            )

            if target != targets[-1]:
                await asyncio.sleep(job.interval_seconds)

        await db.refresh(job)
        if job.status == "cancelled":
            return
        if job.sent_count == 0 and job.error_count > 0:
            job.status = "failed"
        else:
            job.status = "completed"
        job.completed_at = datetime.now(timezone.utc)
        await db.commit()
        logger.info(
            "Job %d finished: sent=%d errors=%d",
            job.id,
            job.sent_count,
            job.error_count,
        )

    except Exception as e:
        logger.exception("Unhandled error in job %d: %s", job.id, e)
        await _fail_job(job, db, f"Erro inesperado: {e.__class__.__name__}: {e}")


async def _send_to_target(job, target, channel, payload, media_asset, media_b64, db):
    wa_id = target["wa_id"]
    target_name = target.get("name")
    text = _interpolate(payload.get("text", ""), target, wa_id)

    last_error = None
    for attempt in range(len(RETRY_DELAYS) + 1):
        try:
            if media_b64 and media_asset:
                await send_media(
                    instance_name=channel.instance_name,
                    to=wa_id,
                    media_type=media_asset.media_type,
                    media_base64=media_b64,
                    caption=text or None,
                    filename=media_asset.filename,
                    mimetype=media_asset.mime_type,
                )
            else:
                await send_text(channel.instance_name, wa_id, text)

            db.add(BroadcastLog(
                job_id=job.id,
                target_wa_id=wa_id,
                target_name=target_name,
                status="sent",
            ))
            job.sent_count += 1
            await db.commit()
            return

        except Exception as e:
            last_error = e
            status_code = getattr(getattr(e, "response", None), "status_code", None)
            is_transient = status_code is None or status_code >= 500 or status_code == 429
            if is_transient and attempt < len(RETRY_DELAYS):
                await asyncio.sleep(RETRY_DELAYS[attempt])
                continue
            break

    db.add(BroadcastLog(
        job_id=job.id,
        target_wa_id=wa_id,
        target_name=target_name,
        status="error",
        error_detail=str(last_error)[:2000],
    ))
    job.error_count += 1
    await db.commit()


async def _fail_job(job, db, reason: str):
    job.status = "failed"
    job.error_message = reason
    job.completed_at = datetime.now(timezone.utc)
    await db.commit()
    logger.error("Job %d failed: %s", job.id, reason)


def _interpolate(template: str, target: dict, wa_id: str) -> str:
    if not template:
        return ""
    name = target.get("name") or ""
    return (
        template
        .replace("{nome}", name)
        .replace("{grupo_nome}", name)
        .replace("{wa_id}", wa_id)
    )
