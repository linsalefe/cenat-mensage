from __future__ import annotations

import logging
import re
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.config import get_settings
from app.deps import DbSession
from app.meta.conversions import fire_conversion
from app.models import Contact

logger = logging.getLogger(__name__)
_settings = get_settings()
router = APIRouter(prefix="/api/payments", tags=["Payments Webhook"])


def _digits(s: Optional[str]) -> str:
    return re.sub(r"\D", "", s or "")


async def _find_contact(db, phone: str) -> Optional[Contact]:
    """Casa wa_id por telefone (best-effort BR). Tenta variantes 55 + DDD + 8/9 digitos."""
    d = _digits(phone)
    cands = {d}
    if not d.startswith("55"):
        cands.add("55" + d)
    # variante com/sem 9o digito do celular
    if len(d) >= 12 and d.startswith("55"):
        cands.add(d[:4] + d[5:] if len(d) == 13 else d[:4] + "9" + d[4:])
    for wa in cands:
        c = (await db.execute(select(Contact).where(Contact.wa_id == wa))).scalar_one_or_none()
        if c:
            return c
    return None


@router.post("/webhook/hotmart")
async def hotmart_webhook(request: Request, db: DbSession):
    body = await request.json()
    # auth: hottok (confirmar no painel Hotmart o formato atual do webhook v2)
    hottok = request.headers.get("X-HOTMART-HOTTOK") or body.get("hottok")
    if not _settings.PAYMENT_WEBHOOK_TOKEN or hottok != _settings.PAYMENT_WEBHOOK_TOKEN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="token inválido")

    data = body.get("data") or {}
    purchase = data.get("purchase") or {}
    buyer = data.get("buyer") or {}
    # só conversão em compra aprovada
    if (purchase.get("status") or "").upper() not in ("APPROVED", "COMPLETE"):
        return {"status": "ignored", "reason": "status nao aprovado"}

    phone = buyer.get("phone") or (buyer.get("checkout_phone") or "")
    value = ((purchase.get("price") or {}).get("value")) or purchase.get("full_price") or None
    contact = await _find_contact(db, phone)
    if contact is None:
        logger.info("Hotmart: contato nao encontrado p/ telefone %s", _digits(phone)[-4:])
        return {"status": "no_match"}
    if not contact.ctwa_clid:
        return {"status": "no_attribution"}

    await fire_conversion(
        db, contact_wa_id=contact.wa_id, ctwa_clid=contact.ctwa_clid,
        channel_id=contact.channel_id, event_name="Purchase",
        value=float(value) if value is not None else None,
    )
    return {"status": "ok"}
