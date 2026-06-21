from __future__ import annotations

import time
from typing import Any, Optional

import httpx

from app.config import get_settings

_settings = get_settings()
GRAPH_BASE = f"https://graph.facebook.com/{_settings.GRAPH_API_VERSION}"
DEFAULT_TIMEOUT = 30.0


async def send_business_messaging_event(
    *,
    dataset_id: str,
    token: str,
    waba_id: str,
    ctwa_clid: str,
    event_name: str,                 # "Purchase" | "LeadSubmitted"
    value: Optional[float] = None,
    currency: str = "BRL",
    event_time: Optional[int] = None,
    test_event_code: Optional[str] = None,
) -> dict[str, Any]:
    url = f"{GRAPH_BASE}/{dataset_id}/events"
    event: dict[str, Any] = {
        "event_name": event_name,
        "event_time": event_time or int(time.time()),
        "action_source": "business_messaging",   # OBRIGATÓRIO
        "messaging_channel": "whatsapp",          # OBRIGATÓRIO
        "user_data": {
            "whatsapp_business_account_id": waba_id,  # ⚠️ ver nota A3
            "ctwa_clid": ctwa_clid,
        },
    }
    if value is not None:
        event["custom_data"] = {"currency": currency, "value": value}
    payload: dict[str, Any] = {"data": [event], "partner_agent": "whatsflow"}
    if test_event_code:
        payload["test_event_code"] = test_event_code

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        resp = await client.post(url, params={"access_token": token}, json=payload)
        resp.raise_for_status()
        return resp.json()
