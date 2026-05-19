from typing import TypedDict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.evolution.client import fetch_all_groups
from app.models import Channel, Contact, ContactListMember


class Target(TypedDict):
    wa_id: str
    name: str | None


async def resolve_audience(
    audience_type: str,
    audience_spec: dict,
    channel: Channel,
    db: AsyncSession,
) -> list[Target]:
    """Converte audience_spec em lista concreta de targets."""
    if audience_type == "all_groups":
        if not channel.instance_name:
            raise ValueError("all_groups requer canal Evolution (instance_name)")
        groups = await fetch_all_groups(channel.instance_name, get_participants=False)
        return [{"wa_id": g["id"], "name": g.get("subject")} for g in groups]

    if audience_type == "selected_groups":
        if not channel.instance_name:
            raise ValueError("selected_groups requer canal Evolution (instance_name)")
        group_ids = audience_spec.get("group_ids") or []
        name_map: dict[str, str] = {}
        try:
            groups = await fetch_all_groups(channel.instance_name, get_participants=False)
            name_map = {g["id"]: g.get("subject", "") for g in groups}
        except Exception:
            pass
        return [{"wa_id": gid, "name": name_map.get(gid)} for gid in group_ids]

    if audience_type == "single_contact":
        return [{"wa_id": audience_spec["wa_id"], "name": audience_spec.get("name")}]

    if audience_type == "csv":
        list_id = audience_spec.get("list_id")
        if list_id is not None:
            res = await db.execute(
                select(ContactListMember)
                .outerjoin(Contact, Contact.wa_id == ContactListMember.wa_id)
                .where(
                    ContactListMember.list_id == int(list_id),
                    ContactListMember.opted_out.is_(False),
                    (Contact.opted_out.is_(False)) | (Contact.id.is_(None)),
                )
            )
            rows = res.scalars().all()
            return [{"wa_id": m.wa_id, "name": m.name} for m in rows]
        inline = audience_spec.get("contacts") or []
        out: list[Target] = []
        for c in inline:
            if not isinstance(c, dict):
                continue
            wa = c.get("wa_id")
            if not wa:
                continue
            out.append({"wa_id": str(wa), "name": c.get("name")})
        return out

    if audience_type == "contacts_tag":
        raise NotImplementedError("contacts_tag ainda não implementado — use audience_type='csv' com list_id")

    raise ValueError(f"audience_type desconhecido: {audience_type}")
