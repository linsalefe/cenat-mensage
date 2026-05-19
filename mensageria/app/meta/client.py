from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import httpx

from app.config import get_settings

_settings = get_settings()

GRAPH_BASE = f"https://graph.facebook.com/{_settings.GRAPH_API_VERSION}"
DEFAULT_TIMEOUT = 30.0


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _normalize_phone(to: str) -> str:
    return to.replace("+", "").replace("-", "").replace(" ", "").replace("(", "").replace(")", "")


async def send_text(
    phone_number_id: str,
    token: str,
    to: str,
    text: str,
    preview_url: bool = False,
) -> dict[str, Any]:
    url = f"{GRAPH_BASE}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": _normalize_phone(to),
        "type": "text",
        "text": {"body": text, "preview_url": preview_url},
    }
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        resp = await client.post(url, json=payload, headers=_headers(token))
        resp.raise_for_status()
        return resp.json()


async def send_template(
    phone_number_id: str,
    token: str,
    to: str,
    template_name: str,
    language_code: str = "pt_BR",
    components: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    url = f"{GRAPH_BASE}/{phone_number_id}/messages"
    template_body: dict[str, Any] = {
        "name": template_name,
        "language": {"code": language_code},
    }
    if components:
        template_body["components"] = components
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": _normalize_phone(to),
        "type": "template",
        "template": template_body,
    }
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        resp = await client.post(url, json=payload, headers=_headers(token))
        resp.raise_for_status()
        return resp.json()


async def send_media(
    phone_number_id: str,
    token: str,
    to: str,
    media_type: str,
    media_id: Optional[str] = None,
    media_link: Optional[str] = None,
    caption: Optional[str] = None,
    filename: Optional[str] = None,
) -> dict[str, Any]:
    if media_type not in ("image", "audio", "video", "document", "sticker"):
        raise ValueError(f"media_type inválido: {media_type}")
    if not media_id and not media_link:
        raise ValueError("informe media_id (upload prévio) ou media_link (URL pública)")

    media_obj: dict[str, Any] = {}
    if media_id:
        media_obj["id"] = media_id
    else:
        media_obj["link"] = media_link
    if caption and media_type in ("image", "video", "document"):
        media_obj["caption"] = caption
    if filename and media_type == "document":
        media_obj["filename"] = filename

    url = f"{GRAPH_BASE}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": _normalize_phone(to),
        "type": media_type,
        media_type: media_obj,
    }
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        resp = await client.post(url, json=payload, headers=_headers(token))
        resp.raise_for_status()
        return resp.json()


async def mark_as_read(
    phone_number_id: str,
    token: str,
    wa_message_id: str,
) -> dict[str, Any]:
    url = f"{GRAPH_BASE}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": wa_message_id,
    }
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        resp = await client.post(url, json=payload, headers=_headers(token))
        resp.raise_for_status()
        return resp.json()


async def get_media_url(media_id: str, token: str) -> dict[str, Any]:
    url = f"{GRAPH_BASE}/{media_id}"
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        resp = await client.get(
            url,
            params={"fields": "url,mime_type,sha256,file_size,messaging_product"},
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        return resp.json()


_MIME_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "audio/ogg": ".ogg",
    "audio/ogg; codecs=opus": ".ogg",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "video/mp4": ".mp4",
    "video/3gpp": ".3gp",
    "application/pdf": ".pdf",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
}


def _ext_for(mime: str) -> str:
    if not mime:
        return ".bin"
    base = mime.split(";")[0].strip().lower()
    return _MIME_EXT.get(base) or _MIME_EXT.get(mime, ".bin")


async def download_media(media_id: str, token: str, media_dir: str) -> Optional[dict[str, Any]]:
    try:
        meta = await get_media_url(media_id, token)
    except httpx.HTTPStatusError as exc:
        print(f"⚠️ Meta: falha ao obter URL de mídia {media_id}: {exc.response.status_code}", flush=True)
        return None

    media_url = meta.get("url")
    mime = meta.get("mime_type", "")
    if not media_url:
        print(f"⚠️ Meta: media_url vazio para {media_id}", flush=True)
        return None

    Path(media_dir).mkdir(parents=True, exist_ok=True)
    ext = _ext_for(mime)
    filename = f"meta_{media_id}{ext}"
    full_path = os.path.join(media_dir, filename)

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(media_url, headers={"Authorization": f"Bearer {token}"})
        resp.raise_for_status()
        with open(full_path, "wb") as fh:
            fh.write(resp.content)

    return {
        "filename": filename,
        "stored_path": full_path,
        "mime": mime,
        "size_bytes": len(resp.content),
    }


async def upload_media(
    phone_number_id: str,
    token: str,
    file_path: str,
    mime_type: str,
) -> dict[str, Any]:
    url = f"{GRAPH_BASE}/{phone_number_id}/media"
    filename = os.path.basename(file_path)
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=60.0) as client:
        with open(file_path, "rb") as fh:
            files = {
                "file": (filename, fh, mime_type),
                "type": (None, mime_type),
                "messaging_product": (None, "whatsapp"),
            }
            resp = await client.post(url, files=files, headers=headers)
            resp.raise_for_status()
            return resp.json()


async def list_message_templates(
    waba_id: str,
    token: str,
    limit: int = 100,
) -> list[dict[str, Any]]:
    url = f"{GRAPH_BASE}/{waba_id}/message_templates"
    params: Optional[dict[str, Any]] = {
        "fields": "id,name,language,status,category,components",
        "limit": limit,
    }
    headers = {"Authorization": f"Bearer {token}"}
    all_templates: list[dict[str, Any]] = []
    next_url: Optional[str] = url

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        while next_url:
            resp = await client.get(next_url, params=params, headers=headers)
            resp.raise_for_status()
            payload = resp.json()
            all_templates.extend(payload.get("data") or [])
            paging = payload.get("paging") or {}
            next_url = paging.get("next")
            params = None
            if len(all_templates) >= 500:
                break
    return all_templates
