from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.meta import capi
from app.models import Channel, ConversionEvent

logger = logging.getLogger(__name__)
_settings = get_settings()


async def fire_conversion(
    db,
    *,
    contact_wa_id: str,
    ctwa_clid: Optional[str],
    channel_id: Optional[int],
    event_name: str,                 # "Purchase" | "LeadSubmitted"
    value: Optional[float] = None,
    currency: str = "BRL",
) -> Optional[ConversionEvent]:
    """Registra e envia um evento de conversão pra Meta. Idempotente por (wa_id, event_name).
    Recebe primitivos (não ORM Contact) pra evitar expiry pós-commit."""
    if not ctwa_clid:
        logger.info("Conversao %s ignorada: %s sem ctwa_clid", event_name, contact_wa_id)
        return None
    if not _settings.META_DATASET_ID or not _settings.META_CAPI_TOKEN:
        logger.warning("Conversao %s ignorada: META_DATASET_ID/TOKEN ausentes", event_name)
        return None

    # dedup: ja enviado?
    already = (await db.execute(
        select(ConversionEvent).where(
            ConversionEvent.contact_wa_id == contact_wa_id,
            ConversionEvent.event_name == event_name,
            ConversionEvent.status == "sent",
        )
    )).scalar_one_or_none()
    if already:
        logger.info("Conversao %s ja enviada pro %s (dedup)", event_name, contact_wa_id)
        return None

    waba_id = None
    if channel_id:
        waba_id = (await db.execute(
            select(Channel.waba_id).where(Channel.id == channel_id)
        )).scalar_one_or_none()

    ev = ConversionEvent(
        contact_wa_id=contact_wa_id, event_name=event_name, value=value,
        currency=currency, ctwa_clid=ctwa_clid, status="pending",
        event_time=datetime.now(timezone.utc),
    )
    db.add(ev)
    await db.flush()

    try:
        resp = await capi.send_business_messaging_event(
            dataset_id=_settings.META_DATASET_ID, token=_settings.META_CAPI_TOKEN,
            waba_id=waba_id or "", ctwa_clid=ctwa_clid, event_name=event_name,
            value=value, currency=currency, event_time=int(ev.event_time.timestamp()),
        )
        ev.status, ev.meta_response = "sent", resp
        ev.sent_at = datetime.now(timezone.utc)
        logger.info("Conversao %s enviada pro %s: %s", event_name, contact_wa_id, resp)
    except httpx.HTTPStatusError as exc:
        ev.status = "failed"
        ev.meta_response = {"status_code": exc.response.status_code, "body": exc.response.text[:1000]}
        logger.warning("Conversao %s falhou (%s): %s", event_name, exc.response.status_code, exc.response.text[:300])
    except Exception as exc:  # noqa: BLE001
        ev.status = "failed"
        ev.meta_response = {"error": f"{type(exc).__name__}: {exc}"[:1000]}
        logger.warning("Conversao %s erro: %s", event_name, exc)

    try:
        await db.commit()
    except IntegrityError:
        # corrida: outra instancia ja gravou 'sent' — backstop do indice parcial
        await db.rollback()
        logger.info("Conversao %s: corrida resolvida pelo indice (skip) %s", event_name, contact_wa_id)
        return None
    return ev
