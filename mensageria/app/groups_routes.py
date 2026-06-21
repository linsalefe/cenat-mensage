"""Proxy de grupos WhatsApp via Evolution API (server-side).

Mantém a apikey no servidor — nunca é exposta ao frontend. O cache fica
em evo_client.fetch_all_groups (TTL configurável); use force_refresh para
ignorá-lo.
"""
from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.auth import get_current_user
from app.deps import DbSession
from app.evolution import client as evo_client
from app.models import Channel

router = APIRouter(
    prefix="/api/evolution/instances",
    tags=["Evolution Groups"],
    dependencies=[Depends(get_current_user)],
)


def _normalize_group(g: dict[str, Any]) -> dict:
    """Normaliza a resposta crua da Evolution pra um shape estável pro frontend."""
    return {
        "id": g.get("id") or g.get("remoteJid") or "",
        "subject": g.get("subject") or g.get("subjectOwner") or "",
        "picture_url": g.get("pictureUrl") or g.get("profilePictureUrl"),
        "size": g.get("size") or g.get("participantsCount"),
        "owner": g.get("owner") or g.get("subjectOwner"),
        "desc": g.get("desc") or g.get("description"),
        "created_at": g.get("creation") or g.get("createdAt"),
    }


@router.get("/{instance_name}/groups")
async def list_groups(
    instance_name: str,
    db: DbSession,
    get_participants: bool = False,
    force_refresh: bool = False,
):
    res = await db.execute(
        select(Channel).where(Channel.instance_name == instance_name)
    )
    if res.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=404,
            detail=f"Instância {instance_name!r} não encontrada em channels",
        )

    try:
        raw = await evo_client.fetch_all_groups(
            instance_name, get_participants, force_refresh=force_refresh
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Evolution API respondeu {exc.response.status_code}",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Falha ao contactar Evolution API: {exc.__class__.__name__}",
        ) from exc

    return [_normalize_group(g) for g in raw]
