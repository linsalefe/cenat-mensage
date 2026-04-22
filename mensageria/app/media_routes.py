"""Endpoints de upload/download/listagem de mídia (broadcast — Fase 5.1)."""
from __future__ import annotations

import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.auth import CurrentUser, get_current_user
from app.config import get_settings
from app.deps import DbSession
from app.models import MediaAsset

router = APIRouter(
    prefix="/api/media",
    tags=["Media"],
    dependencies=[Depends(get_current_user)],
)

_settings = get_settings()

# Mime types permitidos (WhatsApp Business)
_ALLOWED_MIME = {
    "image/jpeg": ("image", ".jpg"),
    "image/png": ("image", ".png"),
    "image/webp": ("image", ".webp"),
    "audio/ogg": ("audio", ".ogg"),
    "audio/mpeg": ("audio", ".mp3"),
    "video/mp4": ("video", ".mp4"),
    "application/pdf": ("document", ".pdf"),
}


def _asset_to_dict(a: MediaAsset) -> dict:
    return {
        "id": a.id,
        "url": f"/api/media/{a.id}",
        "filename": a.filename,
        "media_type": a.media_type,
        "mime_type": a.mime_type,
        "size_bytes": a.size_bytes,
        "uploaded_by": a.uploaded_by,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_media(
    db: DbSession,
    current_user: CurrentUser,
    file: UploadFile = File(...),
):
    mime = (file.content_type or "").lower().split(";")[0].strip()
    if mime not in _ALLOWED_MIME:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tipo de mídia não suportado: {mime!r}. "
            f"Aceitos: {sorted(_ALLOWED_MIME.keys())}",
        )

    # Lê respeitando limite (não confiar em Content-Length)
    max_bytes = _settings.MEDIA_MAX_BYTES
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Arquivo excede {max_bytes} bytes",
        )

    media_type, ext = _ALLOWED_MIME[mime]
    stored_name = f"{uuid.uuid4().hex}{ext}"
    root = Path(_settings.MEDIA_ROOT)
    root.mkdir(parents=True, exist_ok=True)
    stored_path = root / stored_name

    with open(stored_path, "wb") as f:
        f.write(content)

    asset = MediaAsset(
        filename=file.filename or stored_name,
        stored_path=str(stored_path),
        media_type=media_type,
        mime_type=mime,
        size_bytes=len(content),
        uploaded_by=current_user.id,
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)

    return _asset_to_dict(asset)


@router.get("")
async def list_media(db: DbSession, current_user: CurrentUser):
    q = select(MediaAsset).order_by(MediaAsset.created_at.desc()).limit(50)
    if not current_user.is_admin:
        q = q.where(MediaAsset.uploaded_by == current_user.id)
    res = await db.execute(q)
    return [_asset_to_dict(a) for a in res.scalars().all()]


@router.get("/{media_id}")
async def serve_media(media_id: int, db: DbSession):
    res = await db.execute(select(MediaAsset).where(MediaAsset.id == media_id))
    asset = res.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Mídia não encontrada")
    if not os.path.exists(asset.stored_path):
        raise HTTPException(status_code=404, detail="Arquivo ausente no disco")
    return FileResponse(
        asset.stored_path,
        media_type=asset.mime_type,
        filename=asset.filename,
    )


@router.delete("/{media_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_media(media_id: int, db: DbSession, current_user: CurrentUser):
    res = await db.execute(select(MediaAsset).where(MediaAsset.id == media_id))
    asset = res.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Mídia não encontrada")

    if not current_user.is_admin and asset.uploaded_by != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Sem permissão para remover esta mídia",
        )

    try:
        if os.path.exists(asset.stored_path):
            os.unlink(asset.stored_path)
    except Exception as exc:
        # log mas não bloqueia deleção do registro
        print(f"⚠️ Erro removendo {asset.stored_path}: {exc}")

    await db.delete(asset)
    await db.commit()
