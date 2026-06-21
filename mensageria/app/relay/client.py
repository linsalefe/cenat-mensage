"""Relay Mensage -> Customer (Sprint S1 — Ponte do Mensage).

O Customer é a fonte da verdade do inbox. O Mensage continua persistindo o que
já persistia, mas **adicionalmente** relaya cada inbound/status oficial e o
progresso de broadcast para o Customer via HTTP.

Princípios:
- **Best-effort**: qualquer falha (timeout, Customer fora do ar, config ausente)
  é capturada, logada e engolida. NUNCA propaga exceção — o caller (webhook do
  Meta, worker de broadcast) jamais pode quebrar por causa do relay.
- Autenticação de origem via header ``X-Webhook-Secret: settings.WEBHOOK_SECRET``.
- Nunca logar o valor de secret.
- Se ``CUSTOMER_RELAY_URL`` estiver vazio, o relay é um no-op silencioso.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

_settings = get_settings()

_TIMEOUT = httpx.Timeout(5.0, connect=3.0)


async def _post(path: str, body: dict[str, Any]) -> None:
    """POST best-effort no Customer. Engole qualquer erro."""
    base = (_settings.CUSTOMER_RELAY_URL or "").rstrip("/")
    if not base:
        # Relay desligado (sem URL configurada) — no-op silencioso.
        return

    url = f"{base}{path}"
    headers = {"X-Webhook-Secret": _settings.WEBHOOK_SECRET or ""}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(url, json=body, headers=headers)
        if resp.status_code >= 400:
            logger.warning(
                "Relay %s respondeu %s (best-effort, seguindo)",
                path,
                resp.status_code,
            )
        else:
            logger.debug("Relay %s ok (%s)", path, resp.status_code)
    except Exception as exc:  # noqa: BLE001 — best-effort, nunca propaga
        logger.warning(
            "Relay %s falhou: %s: %s (best-effort, seguindo)",
            path,
            type(exc).__name__,
            exc,
        )


async def relay_inbound(payload: dict[str, Any]) -> None:
    """Mensagem inbound do canal oficial -> Customer.

    Espera body já normalizado:
        {wa_id, wa_message_id, message_type, content, timestamp (ISO),
         sender_name, channel: {id, provider:"official", name}}
    """
    await _post("/api/whatsapp/relay/inbound", payload)


async def relay_status(payload: dict[str, Any]) -> None:
    """Atualização de status de mensagem -> Customer.

    Espera body: {wa_message_id, status}
    """
    await _post("/api/whatsapp/relay/status", payload)


async def relay_broadcast_progress(payload: dict[str, Any]) -> None:
    """Progresso de um broadcast -> Customer.

    Espera body: {job_id, status, sent_count, error_count, total_targets}
    """
    await _post("/api/whatsapp/relay/broadcast-progress", payload)
