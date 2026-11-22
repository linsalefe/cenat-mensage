"""Worker de disparos de e-mail (8ª task do lifespan). Estrutura de broadcast/worker.py.

- EMAIL_ENABLED=false → loga UMA vez e dorme em loop (não lê nem grava nada).
- Envio sequencial, `sleep(1/EMAIL_RATE_PER_SECOND)` entre envios.
- Cota (EMAIL_DAILY_LIMIT, janela móvel de 24h) atingida → job `paused_quota`;
  é repescado a cada PAUSE_RETRY e continua de onde parou.
- Idempotente em restart: destinatário que já tem linha em email_messages
  neste job (exceto `failed`) não é reenviado.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.email.audience import resolve_email_audience
from app.email.service import EmailDisabled, QuotaExceeded, send_one
from app.models import EmailJob, EmailMessage

logger = logging.getLogger(__name__)

POLL_INTERVAL = 10
DISABLED_SLEEP = 60
PAUSE_RETRY = timedelta(minutes=10)
# Falhas SEGUIDAS do SES (credencial, identidade, throttling persistente) antes
# de desistir do job — sem isto um problema de config marcaria a lista inteira
# como failed em poucos minutos.
MAX_CONSECUTIVE_FAILURES = 5

_worker_started = False


async def start_email_worker():
    global _worker_started
    if _worker_started:
        logger.warning("Email worker already started, skipping")
        return
    _worker_started = True

    settings = get_settings()
    if not settings.EMAIL_ENABLED:
        print("📧 E-mail desligado (EMAIL_ENABLED=false)", flush=True)
        while True:
            await asyncio.sleep(DISABLED_SLEEP)

    modo = (
        f"SANDBOX ({len(settings.email_test_allowlist_set)} endereço(s) na allowlist)"
        if settings.email_test_allowlist_set
        else "PRODUÇÃO (allowlist vazia)"
    )
    print(
        f"📧 Email worker started — {modo}, rate={settings.EMAIL_RATE_PER_SECOND}/s, "
        f"limite={settings.EMAIL_DAILY_LIMIT}/24h",
        flush=True,
    )
    try:
        await _startup_recovery()
    except Exception as e:
        logger.exception("📧 recovery falhou: %s", e)
    await _worker_loop()


async def _startup_recovery():
    async with AsyncSessionLocal() as db:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
        res = await db.execute(
            update(EmailJob)
            .where(EmailJob.status == "running", EmailJob.updated_at < cutoff)
            .values(status="pending")
            .returning(EmailJob.id)
        )
        ids = [r[0] for r in res.all()]
        await db.commit()
        if ids:
            print(f"📧 jobs travados recuperados: {ids}", flush=True)


async def _worker_loop():
    while True:
        try:
            async with AsyncSessionLocal() as db:
                job = await _pick_next_job(db)
                if job is None:
                    await asyncio.sleep(POLL_INTERVAL)
                    continue
                await _execute_job(job, db)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception("📧 worker loop error: %s", e)
            await asyncio.sleep(30)


async def _pick_next_job(db: AsyncSession):
    now = datetime.now(timezone.utc)
    stmt = (
        select(EmailJob)
        .where(
            or_(
                and_(
                    EmailJob.status == "pending",
                    (EmailJob.scheduled_at.is_(None)) | (EmailJob.scheduled_at <= now),
                ),
                and_(
                    EmailJob.status == "paused_quota",
                    EmailJob.updated_at <= now - PAUSE_RETRY,
                ),
            )
        )
        .order_by(EmailJob.created_at.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    job = (await db.execute(stmt)).scalar_one_or_none()
    if job is None:
        return None
    job.status = "running"
    if job.started_at is None:
        job.started_at = now
    job.updated_at = now
    await db.commit()
    await db.refresh(job)
    return job


async def _finish(job: EmailJob, db: AsyncSession, status: str, error: str | None = None):
    job.status = status
    if error:
        job.error_message = error
    if status in ("completed", "failed", "cancelled"):
        job.completed_at = datetime.now(timezone.utc)
    job.updated_at = datetime.now(timezone.utc)
    await db.commit()


async def _execute_job(job: EmailJob, db: AsyncSession):
    settings = get_settings()
    job_id = job.id
    print(f"📧 job #{job_id} '{job.name}' iniciando", flush=True)
    try:
        targets = await resolve_email_audience(job.audience_type, job.audience_spec or {}, db)
    except Exception as e:
        await _finish(job, db, "failed", f"audiência inválida: {e}")
        return

    job.total_targets = len(targets)
    await db.commit()
    if not targets:
        await _finish(job, db, "failed", "audiência vazia (nenhum e-mail elegível)")
        return

    res = await db.execute(
        select(EmailMessage.to_email).where(
            EmailMessage.job_id == job_id, EmailMessage.status != "failed"
        )
    )
    done = {r[0] for r in res.all()}

    interval = 1.0 / settings.EMAIL_RATE_PER_SECOND if settings.EMAIL_RATE_PER_SECOND > 0 else 1.0
    consecutive_failures = 0

    for i, t in enumerate(targets):
        if i % 20 == 0:
            await db.refresh(job)
            if job.status == "cancelled":
                print(f"📧 job #{job_id} cancelado", flush=True)
                job.completed_at = datetime.now(timezone.utc)
                await db.commit()
                return
        if t["email"] in done:
            continue
        try:
            msg = await send_one(
                db,
                to_email=t["email"], to_name=t.get("name"),
                subject=job.subject, html=job.html_body, text=job.text_body,
                job_id=job_id, contact_id=t.get("contact_id"),
                from_name=job.from_name, reply_to=job.reply_to,
            )
        except QuotaExceeded as e:
            print(f"📧 job #{job_id} pausado por cota: {e}", flush=True)
            await _finish(job, db, "paused_quota", str(e))
            return
        except EmailDisabled:
            await _finish(job, db, "paused_quota", "e-mail desligado")
            return

        if msg.status == "sent":
            job.sent_count = (job.sent_count or 0) + 1
            consecutive_failures = 0
        elif msg.status == "skipped":
            job.skipped_count = (job.skipped_count or 0) + 1
        else:
            job.error_count = (job.error_count or 0) + 1
            consecutive_failures += 1
        job.updated_at = datetime.now(timezone.utc)
        await db.commit()

        if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            await _finish(
                job, db, "failed",
                f"{MAX_CONSECUTIVE_FAILURES} falhas seguidas; última: {msg.error}",
            )
            print(f"📧 job #{job_id} abortado: falhas seguidas ({msg.error})", flush=True)
            return

        if msg.status == "sent":
            await asyncio.sleep(interval)

    await db.refresh(job)
    if job.status == "cancelled":
        return
    await _finish(job, db, "completed")
    print(
        f"📧 job #{job_id} concluído: {job.sent_count} enviados, "
        f"{job.skipped_count} pulados, {job.error_count} erros",
        flush=True,
    )
