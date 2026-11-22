"""`send_one` é a ÚNICA porta de saída de e-mail do Mensage.

Ordem dos portões (nenhum caminho pula nenhum):
  0. EMAIL_ENABLED            → EmailDisabled (rota devolve 409; nada é gravado)
  1. supressão                → email_messages.status='skipped', error='suppressed'
  2. sandbox (allowlist)      → status='skipped', error='sandbox'
  3. cota diária              → QuotaExceeded (nada é gravado; o worker pausa o job)
  4. configuração/SES         → status='sent' (com ses_message_id) ou 'failed'

A E4b (sequências por gatilho) chama esta mesma função.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.email import ses
from app.email.render import render_message
from app.email.unsubscribe import unsubscribe_url
from app.models import Contact, EmailMessage, EmailSuppression

logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Status que já gastaram cota no SES. bounced/complained também saíram — o SES
# conta o envio, não a entrega.
_STATUS_ENVIADO = ("sent", "delivered", "bounced", "complained")


class EmailDisabled(RuntimeError):
    pass


class QuotaExceeded(RuntimeError):
    pass


def normalize_email(raw: str | None) -> str | None:
    v = (raw or "").strip().lower()
    if not v or len(v) > 255 or not EMAIL_RE.match(v):
        return None
    return v


def allowed_by_sandbox(email: str) -> bool:
    """True = pode enviar. Allowlist vazia = produção (todos)."""
    allow = get_settings().email_test_allowlist_set
    return not allow or email.lower() in allow


def is_sandbox() -> bool:
    return bool(get_settings().email_test_allowlist_set)


async def is_suppressed(db: AsyncSession, email: str) -> bool:
    res = await db.execute(
        select(EmailSuppression.email).where(EmailSuppression.email == email.lower())
    )
    return res.first() is not None


async def sent_last_24h(db: AsyncSession) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    res = await db.execute(
        select(func.count(EmailMessage.id)).where(
            EmailMessage.status.in_(_STATUS_ENVIADO),
            EmailMessage.sent_at >= cutoff,
        )
    )
    return int(res.scalar() or 0)


async def suppress(
    db: AsyncSession, email: str, *, reason: str, source: str, detail: str | None = None
) -> bool:
    """Grava supressão (idempotente: a primeira razão fica). True se inseriu."""
    stmt = (
        pg_insert(EmailSuppression)
        .values(email=email.strip().lower(), reason=reason, source=source, detail=detail)
        .on_conflict_do_nothing(index_elements=["email"])
    )
    res = await db.execute(stmt)
    return bool(res.rowcount)


def config_missing() -> list[str]:
    """Nomes das variáveis obrigatórias para enviar que estão vazias."""
    s = get_settings()
    faltando = []
    for nome in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "SES_FROM_EMAIL", "EMAIL_UNSUBSCRIBE_SECRET"):
        if not getattr(s, nome):
            faltando.append(nome)
    return faltando


async def send_one(
    db: AsyncSession,
    *,
    to_email: str,
    to_name: str | None,
    subject: str,
    html: str,
    text: str | None = None,
    job_id: int | None = None,
    contact_id: int | None = None,
    from_name: str | None = None,
    reply_to: str | None = None,
) -> EmailMessage:
    """Envia (ou registra por que não enviou) UM e-mail. Faz commit."""
    s = get_settings()
    if not s.EMAIL_ENABLED:
        raise EmailDisabled("e-mail desligado")

    email = normalize_email(to_email)
    row = EmailMessage(
        job_id=job_id,
        contact_id=contact_id,
        to_email=email or (to_email or "").strip().lower()[:255],
        to_name=to_name,
        subject=(subject or "")[:998],
        status="queued",
    )

    def _skip(motivo: str) -> None:
        row.status = "skipped"
        row.error = motivo

    if email is None:
        row.status = "failed"
        row.error = "e-mail inválido"
    elif await is_suppressed(db, email):
        _skip("suppressed")
    elif not allowed_by_sandbox(email):
        _skip("sandbox")
    else:
        if await sent_last_24h(db) >= s.EMAIL_DAILY_LIMIT:
            raise QuotaExceeded(f"cota diária de {s.EMAIL_DAILY_LIMIT} atingida")
        faltando = config_missing()
        if faltando:
            row.status = "failed"
            row.error = "configuração ausente: " + ", ".join(faltando)
        else:
            unsub = unsubscribe_url(email)
            f_subject, f_html, f_text = render_message(
                subject=subject, html=html, text=text, nome=to_name, email=email,
                unsubscribe_url=unsub,
            )
            row.subject = f_subject[:998]
            headers = {
                "List-Unsubscribe": f"<{unsub}>",
                "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
            }
            tags = {"job_id": str(job_id) if job_id is not None else "none"}
            try:
                msg_id = await asyncio.to_thread(
                    ses.send,
                    to=email, to_name=to_name, subject=f_subject, html=f_html, text=f_text,
                    headers=headers, tags=tags, from_name=from_name, reply_to=reply_to,
                )
                row.status = "sent"
                row.ses_message_id = msg_id
                row.sent_at = datetime.now(timezone.utc)
            except Exception as e:  # SES/rede/credencial — registra, não propaga
                row.status = "failed"
                row.error = f"{e.__class__.__name__}: {str(e)[:500]}"
                logger.warning("📧 envio falhou (job=%s): %s", job_id, row.error)

    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def find_contact_id(db: AsyncSession, email: str) -> int | None:
    res = await db.execute(
        select(Contact.id).where(func.lower(Contact.email) == email.lower()).limit(1)
    )
    r = res.first()
    return r[0] if r else None
