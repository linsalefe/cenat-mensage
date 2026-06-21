from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.broadcast.audience_resolver import resolve_audience
from app.database import AsyncSessionLocal
from app.models import BroadcastJob, BroadcastLog, Channel, MediaAsset
from app.relay import client as relay

logger = logging.getLogger(__name__)

POLL_INTERVAL = 10
RETRY_DELAYS = [5, 15]
# Relay de progresso pro Customer a cada N envios processados (Sprint S1).
PROGRESS_EVERY = 10


async def _relay_progress(job) -> None:
    """Relaya o progresso do job pro Customer (best-effort, nunca propaga)."""
    await relay.relay_broadcast_progress({
        "job_id": job.id,
        "status": job.status,
        "sent_count": job.sent_count or 0,
        "error_count": job.error_count or 0,
        "total_targets": job.total_targets or 0,
    })

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

        # Progresso inicial (job running, total conhecido).
        await _relay_progress(job)

        payload = job.message_payload or {}
        media_asset = None
        if payload.get("media_id"):
            media_asset = await db.get(MediaAsset, payload["media_id"])

        for idx, target in enumerate(targets):
            await db.refresh(job)
            if job.status == "cancelled":
                logger.info("Job %d cancelled mid-flight", job.id)
                job.completed_at = datetime.now(timezone.utc)
                await db.commit()
                await _relay_progress(job)
                return

            # Relay periódico de progresso (a cada N processados).
            if idx and idx % PROGRESS_EVERY == 0:
                await _relay_progress(job)

            try:
                await _send_to_target(
                    job, target, channel, payload, media_asset, None, db
                )
            except Exception as exc:
                try:
                    await db.rollback()
                except Exception:
                    pass

                target_wa_id = (
                    target.get("wa_id") if isinstance(target, dict)
                    else getattr(target, "wa_id", "?")
                )
                target_name = (
                    target.get("name") if isinstance(target, dict)
                    else getattr(target, "name", None)
                )

                try:
                    await db.refresh(job)
                    db.add(BroadcastLog(
                        job_id=job.id,
                        target_wa_id=str(target_wa_id)[:100],
                        target_name=target_name,
                        status="error",
                        error_detail=f"{type(exc).__name__}: {str(exc)[:1900]}",
                    ))
                    job.error_count = (job.error_count or 0) + 1
                    await db.commit()
                except Exception:
                    await db.rollback()

                logger.error(
                    "Broadcast job %d target %s falhou: %s: %s",
                    job.id, target_wa_id, type(exc).__name__, str(exc)[:200],
                )
                print(
                    f"❌ Broadcast job {job.id} target {target_wa_id}: "
                    f"{type(exc).__name__}: {str(exc)[:200]}",
                    flush=True,
                )

                await asyncio.sleep(0.5)
                continue

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
        await _relay_progress(job)
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
    from app.messaging.persistence import persist_outbound_message
    from app.messaging.provider import get_provider
    from app.messaging.types import OutboundMedia

    wa_id = target["wa_id"]
    target_name = target.get("name")
    text = _interpolate(payload.get("text", ""), target, wa_id)

    provider = get_provider(channel)

    is_template = bool(payload.get("template_id"))

    # Resolve template + componentes UMA vez, antes do loop de retry: erros
    # determinísticos (canal errado, template inexistente) devem falhar claro,
    # sem consumir retries nem cair silenciosamente no ramo de texto.
    tpl = None
    template_components = None
    rendered_values: list[str] = []
    if is_template:
        from app.models import MetaTemplate
        if (channel.provider or "").lower() not in ("official", "meta", "cloud"):
            raise RuntimeError(
                f"template_id em canal provider={channel.provider!r}: "
                "template é suportado só em canal oficial (Meta)"
            )
        tpl_res = await db.execute(
            select(MetaTemplate).where(
                MetaTemplate.id == payload["template_id"],
                MetaTemplate.channel_id == channel.id,
            )
        )
        tpl = tpl_res.scalar_one_or_none()
        if not tpl:
            raise RuntimeError(
                f"Template {payload['template_id']} não encontrado no canal {channel.id}"
            )
        rendered_values = _render_template_params(
            payload.get("template_params"), target, wa_id
        )
        if rendered_values:
            template_components = [{
                "type": "body",
                "parameters": [{"type": "text", "text": v} for v in rendered_values],
            }]

    last_error = None
    for attempt in range(len(RETRY_DELAYS) + 1):
        try:
            if is_template:
                result = await provider.send_template(
                    channel, wa_id, tpl.name, tpl.language, template_components,
                )
                content_repr = f"[template:{tpl.name}@{tpl.language}]"
                if rendered_values:
                    content_repr += f" params=[{', '.join(rendered_values)}]"
                message_type = "template"
            elif media_asset is not None:
                media = OutboundMedia(
                    media_type=media_asset.media_type,
                    asset_path=media_asset.stored_path,
                    mime_type=media_asset.mime_type,
                    filename=media_asset.filename,
                    caption=text or None,
                )
                result = await provider.send_media(channel, wa_id, media)
                content_repr = f"local:{media_asset.filename}|{media_asset.mime_type}|{text or ''}"
                message_type = media_asset.media_type
            else:
                result = await provider.send_text(channel, wa_id, text)
                content_repr = text
                message_type = "text"

            await persist_outbound_message(
                db=db,
                channel=channel,
                to=wa_id,
                message_type=message_type,
                content=content_repr,
                send_result=result,
            )

            db.add(BroadcastLog(
                job_id=job.id,
                target_wa_id=wa_id,
                target_name=target_name,
                status="sent",
            ))
            job.sent_count += 1
            await db.commit()
            print(f"📤 Broadcast job={job.id} → {wa_id} ({'template' if is_template else message_type}) ok", flush=True)
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
    await _relay_progress(job)
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


def _render_param(param: dict, target: dict, wa_id: str) -> str:
    p_type = param.get("type", "fixed_text")
    p_value = param.get("value", "") or ""
    if p_type == "contact_name":
        name = target.get("name") or ""
        first = name.split()[0] if name else ""
        return first or "Contato"
    if p_type == "contact_wa_id":
        return wa_id
    if p_type == "custom_var":
        custom = target.get("custom_vars") or {}
        return str(custom.get(p_value, ""))
    if p_type == "fixed_text":
        return p_value
    return p_value


def _render_template_params(params, target: dict, wa_id: str) -> list[str]:
    """Renderiza os parâmetros do corpo do template em valores por contato.

    Aceita dois formatos:
    - **dict posicional** (contrato da ponte/Customer):
      ``{"1": "Olá {nome}", "2": "Belém"}`` — ordenado por índice, cada valor
      string passa por ``_interpolate`` ({nome}/{wa_id}/...).
    - **lista** (frontend do Mensage):
      ``[{"type": "contact_name"}, {"type": "fixed_text", "value": "x"}]`` via
      ``_render_param``; strings soltas na lista também são interpoladas.

    Retorna [] quando não há params.
    """
    if not params:
        return []

    if isinstance(params, dict):
        def _key(k):
            try:
                return (0, int(k))
            except (TypeError, ValueError):
                return (1, str(k))
        ordered = sorted(params.items(), key=lambda kv: _key(kv[0]))
        return [_interpolate(str(v), target, wa_id) for _, v in ordered]

    if isinstance(params, list):
        out: list[str] = []
        for p in params:
            if isinstance(p, dict):
                out.append(_render_param(p, target, wa_id))
            else:
                out.append(_interpolate(str(p), target, wa_id))
        return out

    return []
