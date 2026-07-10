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
from app.media_convert import AudioConversionError, remux_webm_to_ogg
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
    # MediaRecorder grava webm/opus no Chrome e Firefox, e mp4/aac no Safari.
    # O Cloud API aceita mp4 direto, mas rejeita webm — este é remuxado abaixo.
    "audio/webm": ("audio", ".webm"),
    "audio/mp4": ("audio", ".m4a"),
    "video/mp4": ("video", ".mp4"),
    "application/pdf": ("document", ".pdf"),
}

# Documentos do inbox: além do PDF, os formatos office mais comuns.
_ALLOWED_MIME.update(
    {
        "application/msword": ("document", ".doc"),
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (
            "document",
            ".docx",
        ),
        "application/vnd.ms-excel": ("document", ".xls"),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": (
            "document",
            ".xlsx",
        ),
        "text/plain": ("document", ".txt"),
        "text/csv": ("document", ".csv"),
    }
)


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

    # O WhatsApp rejeita audio/webm. Remuxamos aqui, no upload, para que o asset
    # já nasça enviável — o caminho de envio não precisa saber disso.
    if mime == "audio/webm":
        try:
            content = await remux_webm_to_ogg(content)
        except AudioConversionError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            )
        mime, ext = "audio/ogg", ".ogg"

    stored_name = f"{uuid.uuid4().hex}{ext}"
    root = Path(_settings.MEDIA_ROOT)
    root.mkdir(parents=True, exist_ok=True)
    stored_path = root / stored_name

    with open(stored_path, "wb") as f:
        f.write(content)

    # Se houve remux, o nome original ainda termina em .webm — corrige para não
    # mentir sobre o conteúdo do arquivo.
    original_name = file.filename or stored_name
    if mime == "audio/ogg" and original_name.lower().endswith(".webm"):
        original_name = original_name[: -len(".webm")] + ".ogg"

    asset = MediaAsset(
        filename=original_name,
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
