from __future__ import annotations

from typing import Any

import httpx

from app.config import get_settings

_settings = get_settings()

# Mesmo host/versão do módulo meta/ (caminho Messenger Platform / Facebook Login).
# NÃO usar graph.instagram.com (Instagram Login) — decisão da sprint.
GRAPH_BASE = f"https://graph.facebook.com/{_settings.GRAPH_API_VERSION}"
DEFAULT_TIMEOUT = 30.0

# Tipos de attachment aceitos pela Send API do Instagram.
ATTACHMENT_TYPES = ("image", "audio", "video", "file")


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


async def send_text(
    ig_id: str,
    token: str,
    to_igsid: str,
    text: str,
) -> dict[str, Any]:
    """Envia uma DM de texto.

    ``to_igsid`` é o IGSID puro do destinatário (sem o prefixo interno ``ig:``);
    não é telefone, então não normalizamos. Texto: UTF-8, máx 1000 bytes (limite Meta).
    """
    url = f"{GRAPH_BASE}/{ig_id}/messages"
    payload = {
        "recipient": {"id": to_igsid},
        "message": {"text": text},
    }
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        resp = await client.post(url, json=payload, headers=_headers(token))
        resp.raise_for_status()
        return resp.json()


async def send_attachment(
    ig_id: str,
    token: str,
    to_igsid: str,
    media_type: str,
    url: str,
) -> dict[str, Any]:
    """Envia uma DM de mídia por URL pública (image | audio | video | file)."""
    if media_type not in ATTACHMENT_TYPES:
        raise ValueError(f"media_type inválido: {media_type}")

    endpoint = f"{GRAPH_BASE}/{ig_id}/messages"
    payload = {
        "recipient": {"id": to_igsid},
        "message": {
            "attachment": {
                "type": media_type,
                "payload": {"url": url, "is_reusable": True},
            }
        },
    }
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        resp = await client.post(endpoint, json=payload, headers=_headers(token))
        resp.raise_for_status()
        return resp.json()


async def send_private_reply(
    ig_id: str,
    token: str,
    comment_id: str,
    text: str,
) -> dict[str, Any]:
    """Manda o comentarista pro Direct (private reply a um comentário).

    Janela de 7 dias desde a criação do comentário; só UMA por comentário.
    Requer escopo instagram_manage_comments.
    """
    url = f"{GRAPH_BASE}/{ig_id}/messages"
    payload = {
        "recipient": {"comment_id": comment_id},
        "message": {"text": text},
    }
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        resp = await client.post(url, json=payload, headers=_headers(token))
        resp.raise_for_status()
        return resp.json()


async def reply_to_comment(comment_id: str, token: str, text: str) -> dict[str, Any]:
    """Responde publicamente no próprio comentário (POST /{comment_id}/replies)."""
    url = f"{GRAPH_BASE}/{comment_id}/replies"
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        resp = await client.post(
            url,
            params={"message": text},
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        return resp.json()


async def get_comment(
    comment_id: str,
    token: str,
    fields: str = "text,username,timestamp",
) -> dict[str, Any]:
    """Lê um comentário (texto/autor) — usado pra enriquecer menções/comentários."""
    url = f"{GRAPH_BASE}/{comment_id}"
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        resp = await client.get(
            url,
            params={"fields": fields},
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        return resp.json()


async def mark_seen(ig_id: str, token: str, to_igsid: str) -> dict[str, Any]:
    """Marca como lida a última mensagem do usuário (sender_action=mark_seen)."""
    url = f"{GRAPH_BASE}/{ig_id}/messages"
    payload = {
        "recipient": {"id": to_igsid},
        "sender_action": "mark_seen",
    }
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        resp = await client.post(url, json=payload, headers=_headers(token))
        resp.raise_for_status()
        return resp.json()


async def get_profile(ig_id: str, token: str) -> dict[str, Any]:
    """Lê o perfil da conta IG do canal — usado no health check."""
    url = f"{GRAPH_BASE}/{ig_id}"
    params = {"fields": "username,name,profile_picture_url"}
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            url, params=params, headers={"Authorization": f"Bearer {token}"}
        )
        resp.raise_for_status()
        return resp.json()


async def get_subscribed_apps(page_id: str, token: str) -> dict[str, Any]:
    """Lista apps inscritos na Página; `subscribed_fields` mostra o que está ativo.
    GET /{page_id}/subscribed_apps — exige pages_show_list (ou pages_manage_metadata)."""
    url = f"{GRAPH_BASE}/{page_id}/subscribed_apps"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, headers={"Authorization": f"Bearer {token}"})
        resp.raise_for_status()
        return resp.json()


async def subscribe_page(page_id: str, token: str, fields: str) -> dict[str, Any]:
    """Inscreve a Página no app pros campos informados (subscribed_fields, separados por vírgula).
    POST /{page_id}/subscribed_apps — exige pages_manage_metadata."""
    url = f"{GRAPH_BASE}/{page_id}/subscribed_apps"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            url,
            params={"subscribed_fields": fields},
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        return resp.json()
