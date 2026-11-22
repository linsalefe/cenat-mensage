"""Rotas PÚBLICAS do e-mail (sem autenticação; expostas pelo nginx em /api/).

- POST /api/email/sns          eventos do SES via SNS (assinatura obrigatória)
- GET  /api/email/unsubscribe  link do rodapé → página HTML em português
- POST /api/email/unsubscribe  one-click (RFC 8058, List-Unsubscribe-Post)

Funcionam mesmo com EMAIL_ENABLED=false: são passivas (gravam supressão e
status, nunca enviam e-mail).
"""
from __future__ import annotations

import html as _html
import json
import logging
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from sqlalchemy import func, select, update

from app.config import get_settings
from app.deps import DbSession
from app.email.service import suppress
from app.email.sns import is_sns_url, verify_sns_signature
from app.email.unsubscribe import verify_token
from app.models import Contact, EmailMessage

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/email", tags=["E-mail (público)"])

# Precedência de status: evento atrasado nunca rebaixa um status mais grave
# (ex.: Delivery chegando depois de Complaint).
_RANK = {"queued": 0, "skipped": 0, "failed": 1, "sent": 1, "delivered": 2, "bounced": 3, "complained": 4}


def _parse_ts(v) -> datetime:
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except Exception:
        return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# SNS
# ---------------------------------------------------------------------------


@router.post("/sns")
async def sns_webhook(request: Request, db: DbSession):
    settings = get_settings()
    raw = await request.body()
    try:
        body = json.loads(raw or b"{}")
    except Exception:
        return JSONResponse({"detail": "corpo inválido"}, status_code=400)
    if not isinstance(body, dict):
        return JSONResponse({"detail": "corpo inválido"}, status_code=400)

    if not await verify_sns_signature(body):
        logger.warning("📧 SNS: assinatura inválida (Type=%r)", body.get("Type"))
        print(f"📧 SNS: assinatura inválida/ausente — 403 (Type={body.get('Type')!r})", flush=True)
        return JSONResponse({"detail": "assinatura inválida"}, status_code=403)

    topic = body.get("TopicArn")
    nosso = bool(settings.SES_SNS_TOPIC_ARN) and topic == settings.SES_SNS_TOPIC_ARN
    kind = body.get("Type")

    if kind == "SubscriptionConfirmation":
        if not nosso:
            print(f"📧 SNS: confirmação de tópico DESCONHECIDO ignorada ({topic})", flush=True)
            return {"status": "ignored"}
        url = body.get("SubscribeURL")
        if not is_sns_url(url):
            return JSONResponse({"detail": "SubscribeURL inválida"}, status_code=400)
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
                r = await client.get(url)
            print(f"📧 SNS: assinatura do tópico confirmada (HTTP {r.status_code})", flush=True)
        except Exception as e:
            print(f"📧 SNS: falha ao confirmar assinatura: {e.__class__.__name__}", flush=True)
            return JSONResponse({"detail": "falha ao confirmar"}, status_code=502)
        return {"status": "confirmed"}

    if kind == "UnsubscribeConfirmation":
        print(f"📧 SNS: UnsubscribeConfirmation recebido ({topic})", flush=True)
        return {"status": "ok"}

    # Notification
    if not nosso:
        print(f"📧 SNS: notificação de tópico desconhecido ignorada ({topic})", flush=True)
        return {"status": "ignored"}
    try:
        event = json.loads(body.get("Message") or "{}")
    except Exception:
        return {"status": "ignored", "reason": "Message não é JSON"}
    await _handle_ses_event(db, event)
    return {"status": "ok"}


async def _handle_ses_event(db, event: dict) -> None:
    """Processa UM evento do SES (event publishing ou notificação de identidade).
    Idempotente: supressão é ON CONFLICT DO NOTHING; status só sobe de rank."""
    etype = event.get("eventType") or event.get("notificationType") or ""
    mail = event.get("mail") or {}
    ses_id = mail.get("messageId")

    msg = None
    if ses_id:
        msg = (
            await db.execute(select(EmailMessage).where(EmailMessage.ses_message_id == ses_id))
        ).scalar_one_or_none()

    def _set_status(new: str, at, payload: dict, error: str | None = None) -> None:
        if msg is None:
            return
        if _RANK.get(new, 0) >= _RANK.get(msg.status, 0):
            msg.status = new
            msg.event_at = _parse_ts(at)
            msg.event_payload = payload
            if error:
                msg.error = error[:1000]

    if etype == "Bounce":
        b = event.get("bounce") or {}
        if b.get("bounceType") == "Permanent":
            for r in b.get("bouncedRecipients") or []:
                addr = (r.get("emailAddress") or "").strip().lower()
                if addr:
                    detail = f"{b.get('bounceSubType') or ''} {r.get('diagnosticCode') or ''}".strip()
                    await suppress(db, addr, reason="bounce", source="sns", detail=detail[:1000] or None)
            _set_status("bounced", b.get("timestamp"), event, f"bounce {b.get('bounceSubType')}")
            print(f"📧 bounce permanente → suprimido (ses_id={ses_id})", flush=True)
        elif msg is not None:
            # transitório: só registra; não suprime nem muda status
            msg.event_payload = event
            msg.error = f"bounce transitório {b.get('bounceSubType') or ''}".strip()
    elif etype == "Complaint":
        c = event.get("complaint") or {}
        for r in c.get("complainedRecipients") or []:
            addr = (r.get("emailAddress") or "").strip().lower()
            if addr:
                await suppress(db, addr, reason="complaint", source="sns",
                               detail=c.get("complaintFeedbackType"))
        _set_status("complained", c.get("timestamp"), event)
        print(f"📧 complaint → suprimido (ses_id={ses_id})", flush=True)
    elif etype == "Delivery":
        d = event.get("delivery") or {}
        _set_status("delivered", d.get("timestamp"), event)
    elif etype == "Reject":
        _set_status("failed", mail.get("timestamp"), event, "rejeitado pelo SES")
    # Send: já gravamos 'sent' no envio — nada a fazer.

    if msg is None and ses_id and etype not in ("Send",):
        logger.info("📧 SNS: evento %s para ses_id desconhecido", etype)
    await db.commit()


# ---------------------------------------------------------------------------
# Descadastro
# ---------------------------------------------------------------------------


def _page(titulo: str, corpo: str, status_code: int = 200) -> HTMLResponse:
    s = get_settings()
    marca = _html.escape(s.APP_NAME)
    html = f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>{_html.escape(titulo)} · CENAT</title>
<style>
 body{{margin:0;background:#f5f5f4;color:#1c1917;font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif}}
 main{{max-width:480px;margin:64px auto;padding:32px 24px;background:#fff;border-radius:12px;
      box-shadow:0 1px 3px rgba(0,0,0,.08)}}
 h1{{font-size:20px;margin:0 0 12px}} p{{line-height:1.55;margin:0 0 12px;color:#44403c}}
 small{{color:#78716c}}
</style></head>
<body><main><h1>{_html.escape(titulo)}</h1>{corpo}
<p><small>CENAT · {marca}</small></p></main></body></html>"""
    return HTMLResponse(html, status_code=status_code)


async def _unsubscribe(db, email: str, source: str = "link") -> None:
    await suppress(db, email, reason="unsubscribe", source=source)
    await db.execute(
        update(Contact)
        .where(func.lower(Contact.email) == email, Contact.email_opted_out.is_(False))
        .values(email_opted_out=True, email_opted_out_at=datetime.now(timezone.utc))
    )
    await db.commit()
    print("📧 descadastro registrado", flush=True)


@router.get("/unsubscribe")
async def unsubscribe_page(db: DbSession, t: str | None = None):
    email = verify_token(t)
    if not email:
        return _page(
            "Link inválido",
            "<p>Este link de descadastro não é válido. Se você copiou o endereço, "
            "confira se ele veio completo.</p>",
            status_code=400,
        )
    await _unsubscribe(db, email)
    return _page(
        "Pronto, descadastro feito",
        f"<p><strong>{_html.escape(email)}</strong> não vai mais receber nossos e-mails.</p>"
        "<p>Se foi engano, fale com a gente respondendo a qualquer e-mail do CENAT.</p>",
    )


@router.post("/unsubscribe")
async def unsubscribe_one_click(db: DbSession, t: str | None = None):
    email = verify_token(t)
    if not email:
        return PlainTextResponse("token inválido", status_code=400)
    await _unsubscribe(db, email)
    return PlainTextResponse("ok")
