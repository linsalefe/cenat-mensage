from __future__ import annotations

import hashlib
import hmac
import json

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse

from app.config import get_settings

_settings = get_settings()

webhook_router = APIRouter(prefix="/api/meta", tags=["Meta Webhook"])


@webhook_router.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(..., alias="hub.mode"),
    hub_verify_token: str = Query(..., alias="hub.verify_token"),
    hub_challenge: str = Query(..., alias="hub.challenge"),
):
    if not _settings.META_WEBHOOK_VERIFY_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Meta webhook verify token not configured",
        )

    if hub_mode != "subscribe":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="invalid hub.mode",
        )

    if not hmac.compare_digest(hub_verify_token, _settings.META_WEBHOOK_VERIFY_TOKEN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="invalid verify token",
        )

    return PlainTextResponse(content=hub_challenge, status_code=200)


@webhook_router.post("/webhook")
async def receive_webhook(request: Request):
    if not _settings.META_APP_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Meta app secret not configured",
        )

    raw_body = await request.body()
    signature_header = request.headers.get("X-Hub-Signature-256", "")

    if not signature_header.startswith("sha256="):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="missing or malformed signature",
        )

    received_sig = signature_header.removeprefix("sha256=")
    expected_sig = hmac.new(
        _settings.META_APP_SECRET.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(received_sig, expected_sig):
        print(f"⚠️ Meta webhook: assinatura inválida (received_len={len(received_sig)})", flush=True)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="invalid signature",
        )

    try:
        payload = json.loads(raw_body)
        pretty = json.dumps(payload, indent=2, ensure_ascii=False)
        print(f"📩 Meta webhook OK:\n{pretty}", flush=True)
    except json.JSONDecodeError:
        print(f"📩 Meta webhook OK (não-JSON): {raw_body[:500]!r}", flush=True)

    return {"status": "ok"}
