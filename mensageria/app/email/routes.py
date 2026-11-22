"""Rotas AUTENTICADAS do e-mail: status, teste, disparos e supressões."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update

from app.auth import CurrentUser, get_current_user
from app.config import get_settings
from app.deps import DbSession
from app.email import ses
from app.email.audience import AUDIENCE_TYPES
from app.email.service import (
    EmailDisabled,
    QuotaExceeded,
    config_missing,
    find_contact_id,
    is_sandbox,
    normalize_email,
    send_one,
    sent_last_24h,
)
from app.models import Contact, EmailJob, EmailMessage, EmailSuppression

router = APIRouter(
    prefix="/api/email",
    tags=["E-mail"],
    dependencies=[Depends(get_current_user)],
)


def _iso(v) -> str | None:
    return v.isoformat() if v else None


def _require_enabled() -> None:
    if not get_settings().EMAIL_ENABLED:
        raise HTTPException(status_code=409, detail="e-mail desligado")


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


def _aws_status() -> dict:
    """Chamadas síncronas ao SES (rodam em thread). Nunca devolve segredo."""
    s = get_settings()
    acc = ses.get_account()
    quota = acc.get("SendQuota") or {}
    out: dict[str, Any] = {
        "production_access": bool(acc.get("ProductionAccessEnabled")),
        "sending_enabled": bool(acc.get("SendingEnabled")),
        "enforcement_status": acc.get("EnforcementStatus"),
        "max_24h_send": quota.get("Max24HourSend"),
        "max_send_rate": quota.get("MaxSendRate"),
        "sent_last_24h": quota.get("SentLast24Hours"),
        "identity": None,
    }
    if s.SES_FROM_EMAIL:
        from botocore.exceptions import ClientError

        ident = None
        tried = [s.SES_FROM_EMAIL, s.SES_FROM_EMAIL.rsplit("@", 1)[-1]]
        for name in tried:
            try:
                r = ses.get_identity(name)
                dkim = r.get("DkimAttributes") or {}
                ident = {
                    "name": name,
                    "type": r.get("IdentityType"),
                    "verified": bool(r.get("VerifiedForSendingStatus")),
                    "dkim_status": dkim.get("Status"),
                    "dkim_ok": dkim.get("Status") == "SUCCESS",
                }
                break
            except ClientError as e:
                if e.response.get("Error", {}).get("Code") != "NotFoundException":
                    raise
        out["identity"] = ident or {"name": s.SES_FROM_EMAIL, "verified": False,
                                    "dkim_ok": False, "missing": True}
    return out


@router.get("/status")
async def email_status(db: DbSession):
    s = get_settings()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    res = await db.execute(
        select(EmailMessage.status, func.count(EmailMessage.id))
        .where(EmailMessage.created_at >= cutoff)
        .group_by(EmailMessage.status)
    )
    by_status = {k: int(v) for k, v in res.all()}
    supp = int((await db.execute(select(func.count()).select_from(EmailSuppression))).scalar() or 0)
    local = {
        "sent_last_24h": await sent_last_24h(db),
        "by_status_24h": by_status,
        "suppressions": supp,
    }
    config = {
        "enabled": s.EMAIL_ENABLED,
        "sandbox": is_sandbox(),
        "allowlist": sorted(s.email_test_allowlist_set),
        "daily_limit": s.EMAIL_DAILY_LIMIT,
        "rate_per_second": s.EMAIL_RATE_PER_SECOND,
        "from_email": s.SES_FROM_EMAIL or None,
        "from_name": s.SES_FROM_NAME,
        "region": s.AWS_REGION,
        "configuration_set": s.SES_CONFIGURATION_SET or None,
        "sns_topic_configured": bool(s.SES_SNS_TOPIC_ARN),
        "missing": config_missing(),
    }
    try:
        aws = await asyncio.to_thread(_aws_status)
        return {"ok": True, "config": config, "local": local, "aws": aws}
    except Exception as e:
        return {
            "ok": False,
            "error": f"{e.__class__.__name__}: {str(e)[:300]}",
            "config": config,
            "local": local,
            "aws": None,
        }


# ---------------------------------------------------------------------------
# Teste unitário
# ---------------------------------------------------------------------------


class TestIn(BaseModel):
    to: str
    subject: Optional[str] = None
    html: Optional[str] = None


def _msg_dict(m: EmailMessage) -> dict:
    return {
        "id": m.id,
        "job_id": m.job_id,
        "contact_id": m.contact_id,
        "to_email": m.to_email,
        "to_name": m.to_name,
        "subject": m.subject,
        "ses_message_id": m.ses_message_id,
        "status": m.status,
        "error": m.error,
        "sent_at": _iso(m.sent_at),
        "event_at": _iso(m.event_at),
        "created_at": _iso(m.created_at),
    }


@router.post("/test")
async def send_test(data: TestIn, db: DbSession):
    _require_enabled()
    to = normalize_email(data.to)
    if not to:
        raise HTTPException(status_code=422, detail="e-mail inválido")
    marca = get_settings().APP_NAME
    subject = data.subject or f"Teste de envio — {marca}"
    html = data.html or (
        "<p>Olá!</p>"
        f"<p>Este é um e-mail de teste do <strong>{marca}</strong> (CENAT), enviado pelo Amazon SES.</p>"
        "<p>Se chegou, o envio está funcionando.</p>"
    )
    try:
        m = await send_one(
            db, to_email=to, to_name=None, subject=subject, html=html,
            contact_id=await find_contact_id(db, to),
        )
    except EmailDisabled:
        raise HTTPException(status_code=409, detail="e-mail desligado")
    except QuotaExceeded as e:
        raise HTTPException(status_code=429, detail=str(e))
    return _msg_dict(m)


# ---------------------------------------------------------------------------
# Disparos
# ---------------------------------------------------------------------------


class JobIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    audience_type: Literal["lists", "single", "contacts_filter"]
    audience_spec: dict = Field(default_factory=dict)
    subject: str = Field(..., min_length=1, max_length=998)
    html_body: str = Field(..., min_length=1)
    text_body: Optional[str] = None
    from_name: Optional[str] = Field(None, max_length=255)
    reply_to: Optional[str] = Field(None, max_length=255)
    scheduled_at: Optional[datetime] = None


def _job_dict(j: EmailJob) -> dict:
    return {
        "id": j.id,
        "name": j.name,
        "audience_type": j.audience_type,
        "audience_spec": j.audience_spec or {},
        "subject": j.subject,
        "html_body": j.html_body,
        "text_body": j.text_body,
        "from_name": j.from_name,
        "reply_to": j.reply_to,
        "scheduled_at": _iso(j.scheduled_at),
        "status": j.status,
        "total_targets": j.total_targets or 0,
        "sent_count": j.sent_count or 0,
        "skipped_count": j.skipped_count or 0,
        "error_count": j.error_count or 0,
        "started_at": _iso(j.started_at),
        "completed_at": _iso(j.completed_at),
        "created_by": j.created_by,
        "error_message": j.error_message,
        "created_at": _iso(j.created_at),
        "updated_at": _iso(j.updated_at),
    }


def _validate_spec(audience_type: str, spec: dict) -> dict:
    assert audience_type in AUDIENCE_TYPES
    if audience_type == "lists":
        ids = spec.get("list_ids")
        if not isinstance(ids, list) or not ids:
            raise HTTPException(status_code=422, detail="audience_spec.list_ids obrigatório")
        try:
            return {"list_ids": [int(x) for x in ids]}
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="list_ids deve ser lista de inteiros")
    if audience_type == "single":
        e = normalize_email(spec.get("email"))
        if not e:
            raise HTTPException(status_code=422, detail="audience_spec.email inválido")
        return {"email": e, "name": spec.get("name") or None}
    out: dict = {}
    if spec.get("tag_ids"):
        try:
            out["tag_ids"] = [int(x) for x in spec["tag_ids"]]
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="tag_ids deve ser lista de inteiros")
    if spec.get("lead_status"):
        out["lead_status"] = str(spec["lead_status"])
    return out


@router.get("/jobs")
async def list_jobs(db: DbSession, limit: int = 100):
    limit = max(1, min(limit, 500))
    res = await db.execute(select(EmailJob).order_by(EmailJob.created_at.desc()).limit(limit))
    return [_job_dict(j) for j in res.scalars().all()]


@router.post("/jobs", status_code=201)
async def create_job(data: JobIn, db: DbSession, current_user: CurrentUser):
    _require_enabled()
    reply_to = None
    if data.reply_to:
        reply_to = normalize_email(data.reply_to)
        if not reply_to:
            raise HTTPException(status_code=422, detail="reply_to inválido")
    sched = data.scheduled_at
    if sched is not None and sched.tzinfo is None:
        raise HTTPException(status_code=422, detail="scheduled_at precisa de fuso (ISO com offset)")
    job = EmailJob(
        name=data.name,
        audience_type=data.audience_type,
        audience_spec=_validate_spec(data.audience_type, data.audience_spec or {}),
        subject=data.subject.replace("\r", " ").replace("\n", " "),
        html_body=data.html_body,
        text_body=data.text_body or None,
        from_name=data.from_name or None,
        reply_to=reply_to,
        scheduled_at=sched,
        status="pending",
        created_by=current_user.id,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    print(f"📧 job #{job.id} criado por user {current_user.id} ({job.audience_type})", flush=True)
    return _job_dict(job)


@router.get("/jobs/{job_id}")
async def get_job(job_id: int, db: DbSession):
    j = await db.get(EmailJob, job_id)
    if not j:
        raise HTTPException(status_code=404, detail="Disparo não encontrado")
    return _job_dict(j)


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: int, db: DbSession):
    j = await db.get(EmailJob, job_id)
    if not j:
        raise HTTPException(status_code=404, detail="Disparo não encontrado")
    if j.status not in ("pending", "running", "paused_quota"):
        raise HTTPException(status_code=409, detail=f"Disparo já está '{j.status}'")
    j.status = "cancelled"
    if j.completed_at is None:
        j.completed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(j)
    return _job_dict(j)


@router.get("/jobs/{job_id}/messages")
async def list_job_messages(
    job_id: int, db: DbSession, status: Optional[str] = None, limit: int = 100, offset: int = 0
):
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    q = select(EmailMessage).where(EmailMessage.job_id == job_id)
    if status:
        q = q.where(EmailMessage.status == status)
    res = await db.execute(q.order_by(EmailMessage.id.desc()).limit(limit).offset(offset))
    return {"messages": [_msg_dict(m) for m in res.scalars().all()]}


# ---------------------------------------------------------------------------
# Supressões
# ---------------------------------------------------------------------------


class SuppressionIn(BaseModel):
    email: str
    detail: Optional[str] = None


def _supp_dict(s: EmailSuppression) -> dict:
    return {
        "email": s.email,
        "reason": s.reason,
        "source": s.source,
        "detail": s.detail,
        "created_at": _iso(s.created_at),
        "removable": s.reason in ("manual", "unsubscribe"),
    }


@router.get("/suppressions")
async def list_suppressions(db: DbSession, q: Optional[str] = None, limit: int = 100, offset: int = 0):
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    base = select(EmailSuppression)
    count_q = select(func.count()).select_from(EmailSuppression)
    if q:
        like = f"%{q.strip().lower()}%"
        base = base.where(EmailSuppression.email.like(like))
        count_q = count_q.where(EmailSuppression.email.like(like))
    total = int((await db.execute(count_q)).scalar() or 0)
    res = await db.execute(base.order_by(EmailSuppression.created_at.desc()).limit(limit).offset(offset))
    return {"total": total, "suppressions": [_supp_dict(s) for s in res.scalars().all()]}


@router.post("/suppressions", status_code=201)
async def add_suppression(data: SuppressionIn, db: DbSession):
    from app.email.service import suppress

    e = normalize_email(data.email)
    if not e:
        raise HTTPException(status_code=422, detail="e-mail inválido")
    await suppress(db, e, reason="manual", source="api", detail=data.detail)
    await db.commit()
    s = await db.get(EmailSuppression, e)
    return _supp_dict(s)


@router.delete("/suppressions/{email}", status_code=204)
async def remove_suppression(email: str, db: DbSession):
    e = (email or "").strip().lower()
    s = await db.get(EmailSuppression, e)
    if not s:
        raise HTTPException(status_code=404, detail="Supressão não encontrada")
    if s.reason not in ("manual", "unsubscribe"):
        raise HTTPException(
            status_code=409,
            detail=f"supressão por '{s.reason}' não pode ser removida pela UI (protege a reputação do remetente)",
        )
    await db.delete(s)
    if s.reason == "unsubscribe":
        # Reverte também o flag do contato, senão o filtro de contatos seguiria
        # excluindo a pessoa sem nenhum motivo visível.
        await db.execute(
            update(Contact)
            .where(func.lower(Contact.email) == e)
            .values(email_opted_out=False, email_opted_out_at=None)
        )
    await db.commit()
