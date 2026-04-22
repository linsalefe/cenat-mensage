from typing import TypedDict

from sqlalchemy.ext.asyncio import AsyncSession

from app.evolution.client import fetch_all_groups
from app.models import Channel


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
        groups = await fetch_all_groups(channel.instance_name, get_participants=False)
        return [{"wa_id": g["id"], "name": g.get("subject")} for g in groups]

    if audience_type == "selected_groups":
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

    if audience_type in ("contacts_tag", "csv"):
        raise NotImplementedError(f"audience_type '{audience_type}' not supported yet")

    raise ValueError(f"audience_type desconhecido: {audience_type}")
