"""Resolve `email_jobs.audience_spec` em destinatários concretos.

  lists            {"list_ids": [1, 2]}       membros com e-mail, não opted_out
  single           {"email": "...", "name": "..."}
  contacts_filter  {"tag_ids": [..]?, "lead_status": "..."?}
                   contatos com e-mail e email_opted_out=false

Sempre deduplicado por e-mail lowercase (o primeiro nome encontrado fica).
Supressão NÃO é filtrada aqui: `send_one` registra o pulo como `skipped`, para o
disparo mostrar quantos foram barrados e por quê.
"""
from __future__ import annotations

from typing import TypedDict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.email.service import normalize_email
from app.models import Contact, ContactListMember, contact_tag_links

AUDIENCE_TYPES = ("lists", "single", "contacts_filter")


class EmailTarget(TypedDict):
    email: str
    name: str | None
    contact_id: int | None


def _int_list(v) -> list[int]:
    if not isinstance(v, list):
        return []
    out = []
    for x in v:
        try:
            out.append(int(x))
        except (TypeError, ValueError):
            continue
    return out


async def _opted_out_and_ids(db: AsyncSession, emails: set[str]) -> tuple[set[str], dict[str, int]]:
    """(e-mails cujo contato fez email_opt_out, mapa e-mail→contact_id)."""
    if not emails:
        return set(), {}
    res = await db.execute(
        select(func.lower(Contact.email), Contact.id, Contact.email_opted_out).where(
            func.lower(Contact.email).in_(list(emails))
        )
    )
    out_set: set[str] = set()
    ids: dict[str, int] = {}
    for em, cid, opted in res.all():
        if opted:
            out_set.add(em)
        ids.setdefault(em, cid)
    return out_set, ids


async def resolve_email_audience(
    audience_type: str, spec: dict, db: AsyncSession
) -> list[EmailTarget]:
    spec = spec or {}
    if audience_type == "single":
        email = normalize_email(spec.get("email"))
        if not email:
            return []
        opted, ids = await _opted_out_and_ids(db, {email})
        if email in opted:
            return []
        return [{"email": email, "name": spec.get("name") or None, "contact_id": ids.get(email)}]

    if audience_type == "lists":
        list_ids = _int_list(spec.get("list_ids"))
        if not list_ids:
            return []
        res = await db.execute(
            select(ContactListMember.email, ContactListMember.name)
            .where(
                ContactListMember.list_id.in_(list_ids),
                ContactListMember.email.is_not(None),
                ContactListMember.opted_out.is_(False),
            )
            .order_by(ContactListMember.id.asc())
        )
        seen: dict[str, str | None] = {}
        for em, name in res.all():
            e = normalize_email(em)
            if e and e not in seen:
                seen[e] = name
        opted, ids = await _opted_out_and_ids(db, set(seen))
        return [
            {"email": e, "name": n, "contact_id": ids.get(e)}
            for e, n in seen.items()
            if e not in opted
        ]

    if audience_type == "contacts_filter":
        q = select(Contact.id, Contact.email, Contact.name).where(
            Contact.email.is_not(None),
            Contact.email_opted_out.is_(False),
        )
        tag_ids = _int_list(spec.get("tag_ids"))
        if tag_ids:
            q = q.where(
                Contact.id.in_(
                    select(contact_tag_links.c.contact_id).where(
                        contact_tag_links.c.tag_id.in_(tag_ids)
                    )
                )
            )
        if spec.get("lead_status"):
            q = q.where(Contact.lead_status == str(spec["lead_status"]))
        res = await db.execute(q.order_by(Contact.id.asc()))
        seen_t: dict[str, EmailTarget] = {}
        for cid, em, name in res.all():
            e = normalize_email(em)
            if e and e not in seen_t:
                seen_t[e] = {"email": e, "name": name, "contact_id": cid}
        return list(seen_t.values())

    raise ValueError(f"audience_type desconhecido: {audience_type}")
