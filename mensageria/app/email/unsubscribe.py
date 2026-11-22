"""Token de descadastro: `<b64url(email)>.<b64url(HMAC-SHA256(secret, email))>`.

O e-mail vai dentro do token porque o GET/POST de descadastro só recebe o token.
Sem expiração, de propósito: um link de e-mail antigo tem que continuar
funcionando (LGPD). Trocar EMAIL_UNSUBSCRIBE_SECRET invalida todos os links já
enviados.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
from urllib.parse import quote

from app.config import get_settings


def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _secret() -> bytes:
    secret = get_settings().EMAIL_UNSUBSCRIBE_SECRET
    if not secret:
        raise ValueError("EMAIL_UNSUBSCRIBE_SECRET vazio")
    return secret.encode("utf-8")


def _sig(email_lower: str, secret: bytes) -> bytes:
    return hmac.new(secret, email_lower.encode("utf-8"), hashlib.sha256).digest()


def make_token(email: str) -> str:
    e = email.strip().lower()
    return f"{_b64e(e.encode('utf-8'))}.{_b64e(_sig(e, _secret()))}"


def verify_token(token: str | None) -> str | None:
    """E-mail (lowercase) se o token é válido; None em QUALQUER outro caso."""
    if not token or not isinstance(token, str) or token.count(".") != 1 or len(token) > 1024:
        return None
    try:
        secret = _secret()
        p_email, p_sig = token.split(".")
        email = _b64d(p_email).decode("utf-8")
        sig = _b64d(p_sig)
    except Exception:
        return None
    if not email or email != email.strip().lower() or "@" not in email:
        return None
    if not hmac.compare_digest(sig, _sig(email, secret)):
        return None
    return email


def unsubscribe_url(email: str) -> str:
    base = get_settings().EMAIL_PUBLIC_BASE_URL.rstrip("/")
    return f"{base}/api/email/unsubscribe?t={quote(make_token(email), safe='')}"
