"""Endpoints da página de Documentos — conversão de formatos."""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from app.auth import get_current_user
from app.config import get_settings
from app.documents.converter import (
    MIME_BY_EXT,
    ConversionError,
    convert,
    family_of,
    targets_for,
)

router = APIRouter(
    prefix="/api/documents",
    tags=["Documents"],
    dependencies=[Depends(get_current_user)],
)

_settings = get_settings()

_SUPPORTED_IN = sorted(
    e for e in (
        "doc", "docx", "odt", "rtf", "txt", "html", "htm",
        "xls", "xlsx", "ods", "csv",
        "pdf",
    )
    if family_of(e)
)


def _safe_stem(filename: str | None) -> str:
    stem = Path(filename or "documento").stem
    stem = re.sub(r"[^\w.\- ]", "_", stem, flags=re.UNICODE).strip() or "documento"
    return stem[:80]


@router.get("/formats")
async def formats():
    """Matriz de conversão: para cada extensão de entrada, os alvos possíveis."""
    return {
        "max_bytes": _settings.DOC_MAX_BYTES,
        "conversions": {ext: targets_for(ext) for ext in _SUPPORTED_IN},
    }


@router.post("/convert")
async def convert_document(
    file: UploadFile = File(...),
    target: str = Form(...),
):
    src_ext = Path(file.filename or "").suffix.lower().lstrip(".")
    dst_ext = target.lower().strip().lstrip(".")

    if not family_of(src_ext):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Formato de entrada não suportado: .{src_ext or '?'}. "
            f"Aceitos: {', '.join('.' + e for e in _SUPPORTED_IN)}",
        )
    if dst_ext not in targets_for(src_ext):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Não é possível converter .{src_ext} para .{dst_ext}. "
            f"Alvos válidos: {', '.join('.' + t for t in targets_for(src_ext))}",
        )

    # Lê com um byte a mais que o limite — Content-Length é do cliente, não confiável.
    max_bytes = _settings.DOC_MAX_BYTES
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Arquivo excede o limite de {max_bytes // (1024 * 1024)} MB.",
        )
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Arquivo vazio."
        )

    try:
        produced, job_dir = await convert(content, src_ext, dst_ext)
    except ConversionError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    return FileResponse(
        produced,
        media_type=MIME_BY_EXT[dst_ext].split(";")[0],
        filename=f"{_safe_stem(file.filename)}.{dst_ext}",
        # O arquivo é efêmero: some assim que a resposta termina de ser enviada.
        background=BackgroundTask(shutil.rmtree, job_dir, ignore_errors=True),
    )
