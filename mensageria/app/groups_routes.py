"""Proxy de grupos WhatsApp via Evolution API (server-side).

Mantém a apikey no servidor — nunca é exposta ao frontend. Cache simples
de 60s em memória por (instância, get_participants) para evitar hammering.
"""
from __future__ import annotations

import asyncio
import time
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

_CACHE_TTL = 60.0
_cache: dict[tuple[str, bool], tuple[float, list[dict]]] = {}
_cache_lock = asyncio.Lock()


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
):
    # Valida que a instância é um canal conhecido
    res = await db.execute(
        select(Channel).where(Channel.instance_name == instance_name)
    )
    if res.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=404,
            detail=f"Instância {instance_name!r} não encontrada em channels",
        )

    cache_key = (instance_name, get_participants)
    now = time.monotonic()
    async with _cache_lock:
        cached = _cache.get(cache_key)
        if cached and (now - cached[0]) < _CACHE_TTL:
            print(f"📦 groups cache hit: {instance_name}")
            return cached[1]

    try:
        raw = await evo_client.fetch_all_groups(instance_name, get_participants)
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

    groups = [_normalize_group(g) for g in raw]

    async with _cache_lock:
        _cache[cache_key] = (time.monotonic(), groups)

    return groups
