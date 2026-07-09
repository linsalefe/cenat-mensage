from __future__ import annotations

import asyncio
import logging
import os
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
# Tamanho do bloco de envio concorrente. Os avisos precisam sair praticamente
# ao mesmo tempo: cada bloco dispara N envios HTTP em paralelo para a API
# oficial (sem segurar conexão de banco durante a chamada). Ajustável por env.
BROADCAST_BATCH_SIZE = int(os.getenv("BROADCAST_BATCH_SIZE", "200"))


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
    from app.messaging.persistence import persist_outbound_message

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

        # Snapshots desacoplados da sessão principal: os envios rodam em
        # paralelo e leem canal/mídia como valores congelados (expunge evita
        # que um commit entre blocos expire esses objetos e dispare I/O
        # concorrente e inseguro na sessão `db`).
        db.expunge(channel)
        media_asset = None
        if payload.get("media_id"):
            media_asset = await db.get(MediaAsset, payload["media_id"])
            if media_asset is not None:
                db.expunge(media_asset)

        # Template é resolvido UMA vez (nome/idioma valem para todos os alvos).
        tpl_info = None
        if payload.get("template_id"):
            from app.models import MetaTemplate
            if (channel.provider or "").lower() not in ("official", "meta", "cloud"):
                await _fail_job(
                    job, db,
                    f"template_id em canal provider={channel.provider!r}: "
                    "template é suportado só em canal oficial (Meta)",
                )
                return
            tpl_res = await db.execute(
                select(MetaTemplate).where(
                    MetaTemplate.id == payload["template_id"],
                    MetaTemplate.channel_id == channel.id,
                )
            )
            tpl = tpl_res.scalar_one_or_none()
            if tpl is None:
                await _fail_job(
                    job, db,
                    f"Template {payload['template_id']} não encontrado no canal {channel.id}",
                )
                return
            tpl_info = {"name": tpl.name, "language": tpl.language}

        # Disparo em blocos concorrentes (default 200 por bloco): todos os
        # envios HTTP do bloco saem em paralelo para a API oficial e só depois
        # os resultados são persistidos numa única sessão — assim a janela de
        # envio cai de dezenas de minutos para poucos segundos sem estourar o
        # pool de conexões do banco.
        #
        # `interval_seconds` deixou de ser a pausa entre alvos (o bloco sai
        # junto) e passou a ser a pausa ENTRE blocos, dando à Meta uma janela de
        # respiro entre rajadas.
        interval_seconds = job.interval_seconds or 0
        for start in range(0, len(targets), BROADCAST_BATCH_SIZE):
            await db.refresh(job)
            if job.status == "cancelled":
                logger.info("Job %d cancelled mid-flight", job.id)
                job.completed_at = datetime.now(timezone.utc)
                await db.commit()
                await _relay_progress(job)
                return

            if start:
                await asyncio.sleep(interval_seconds)

            batch = targets[start:start + BROADCAST_BATCH_SIZE]
            # `_do_send` nunca levanta (converte qualquer erro em dict com
            # "error"), mas gather usa return_exceptions=True como rede: um
            # alvo malformado vira erro daquele alvo, nunca derruba o job.
            raw = await asyncio.gather(
                *(_do_send(t, channel, payload, media_asset, tpl_info) for t in batch),
                return_exceptions=True,
            )
            results = [
                r if isinstance(r, dict) else _error_result(t, r)
                for t, r in zip(batch, raw)
            ]

            sent = 0
            for r in results:
                wa_id = r["wa_id"]
                if r["error"] is None:
                    await persist_outbound_message(
                        db=db,
                        channel=channel,
                        to=wa_id,
                        message_type=r["message_type"],
                        content=r["content"],
                        send_result=r["send_result"],
                    )
                    db.add(BroadcastLog(
                        job_id=job.id,
                        target_wa_id=wa_id,
                        target_name=r["target_name"],
                        status="sent",
                    ))
                    sent += 1
                else:
                    # Registra a falha no chat (status=failed) para que o
                    # disparo apareça na conversa mesmo quando a Meta rejeita.
                    try:
                        await persist_outbound_message(
                            db=db,
                            channel=channel,
                            to=wa_id,
                            message_type=r["message_type"],
                            content=r["content"],
                            status="failed",
                        )
                    except Exception:
                        logger.exception(
                            "Falha ao persistir msg de disparo com erro (job=%d, wa_id=%s)",
                            job.id, wa_id,
                        )
                    db.add(BroadcastLog(
                        job_id=job.id,
                        target_wa_id=str(wa_id)[:100],
                        target_name=r["target_name"],
                        status="error",
                        error_detail=str(r["error"])[:2000],
                    ))

            job.sent_count = (job.sent_count or 0) + sent
            job.error_count = (job.error_count or 0) + (len(results) - sent)
            await db.commit()
            await _relay_progress(job)
            print(
                f"📤 Broadcast job={job.id} bloco {start}-{start + len(batch)}: "
                f"{sent} ok / {len(results) - sent} erro",
                flush=True,
            )

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


def _error_result(target, exc) -> dict:
    """Resultado de falha para um alvo que nem chegou a ser enviado."""
    wa_id = target.get("wa_id") if isinstance(target, dict) else None
    target_name = target.get("name") if isinstance(target, dict) else None
    return {
        "wa_id": str(wa_id or "?")[:100],
        "target_name": target_name,
        "message_type": "text",
        "content": None,
        "send_result": None,
        "error": f"{type(exc).__name__}: {exc}",
    }


async def _do_send(target, channel, payload, media_asset, tpl_info):
    """Executa APENAS o envio HTTP de um alvo (sem tocar no banco).

    Roda em paralelo dentro do bloco. Retorna um dict com o resultado para o
    chamador persistir depois numa única sessão:
    ``{wa_id, target_name, message_type, content, send_result, error}``.
    ``error`` é None em caso de sucesso; ``send_result`` é None em caso de falha.

    Nunca levanta: um alvo malformado (sem ``wa_id``, params de template
    inválidos) vira um resultado com ``error`` preenchido, para que o job siga
    com os demais alvos do bloco.
    """
    from app.messaging.provider import get_provider
    from app.messaging.types import OutboundMedia

    try:
        wa_id = target["wa_id"]
        target_name = target.get("name")
        text = _interpolate(payload.get("text", ""), target, wa_id)
        provider = get_provider(channel)

        is_template = tpl_info is not None
        template_components = None
        if is_template:
            rendered_values = _render_template_params(
                payload.get("template_params"), target, wa_id
            )
            if rendered_values:
                template_components = [{
                    "type": "body",
                    "parameters": [{"type": "text", "text": v} for v in rendered_values],
                }]
            message_type = "template"
            content_repr = f"[template:{tpl_info['name']}@{tpl_info['language']}]"
            if rendered_values:
                content_repr += f" params=[{', '.join(rendered_values)}]"
        elif media_asset is not None:
            message_type = media_asset.media_type
            content_repr = f"local:{media_asset.filename}|{media_asset.mime_type}|{text or ''}"
        else:
            message_type = "text"
            content_repr = text
    except Exception as e:
        logger.warning("Alvo inválido no disparo (%r): %s", target, e)
        return _error_result(target, e)

    last_error = None
    for attempt in range(len(RETRY_DELAYS) + 1):
        try:
            if is_template:
                result = await provider.send_template(
                    channel, wa_id, tpl_info["name"], tpl_info["language"], template_components,
                )
            elif media_asset is not None:
                media = OutboundMedia(
                    media_type=media_asset.media_type,
                    asset_path=media_asset.stored_path,
                    mime_type=media_asset.mime_type,
                    filename=media_asset.filename,
                    caption=text or None,
                )
                result = await provider.send_media(channel, wa_id, media)
            else:
                result = await provider.send_text(channel, wa_id, text)

            return {
                "wa_id": wa_id,
                "target_name": target_name,
                "message_type": message_type,
                "content": content_repr,
                "send_result": result,
                "error": None,
            }
        except Exception as e:
            last_error = e
            status_code = getattr(getattr(e, "response", None), "status_code", None)
            is_transient = status_code is None or status_code >= 500 or status_code == 429
            if is_transient and attempt < len(RETRY_DELAYS):
                await asyncio.sleep(RETRY_DELAYS[attempt])
                continue
            break

    return {
        "wa_id": wa_id,
        "target_name": target_name,
        "message_type": message_type,
        "content": content_repr,
        "send_result": None,
        "error": f"{type(last_error).__name__}: {last_error}",
    }


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
