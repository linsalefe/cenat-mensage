from __future__ import annotations

from typing import Optional

from sqlalchemy import select

from app.models import Channel, Pipeline


async def resolve_default_pipeline_id(channel: Optional[Channel], db) -> Optional[int]:
    """Pipeline em que um contato NOVO entra ao mandar a primeira mensagem.

    Prioriza o default do canal; cai pro pipeline marcado is_default. None se não houver.
    """
    if channel is not None and channel.default_pipeline_id:
        return channel.default_pipeline_id
    res = await db.execute(select(Pipeline.id).where(Pipeline.is_default.is_(True)).limit(1))
    return res.scalar_one_or_none()
