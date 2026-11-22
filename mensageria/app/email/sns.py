"""Verificação de assinatura de mensagens Amazon SNS (HTTP/S endpoint).

Referência: "Verifying the signatures of Amazon SNS messages" (docs da AWS).
- `SigningCertURL` tem que ser https em `sns.<AWS_REGION>.amazonaws.com` e
  terminar em `.pem` — senão qualquer um assinaria com o próprio certificado;
- SignatureVersion 1 = RSA PKCS#1 v1.5 + SHA1; 2 = idem + SHA256;
- string canônica = pares "Chave\\nValor\\n" em ordem fixa, por tipo.

Certificado em cache por processo (dict por URL). Rodamos com --workers 1, então
é um cache só.
"""
from __future__ import annotations

import base64
import logging
from urllib.parse import urlparse

import httpx
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding

from app.config import get_settings

logger = logging.getLogger(__name__)

_NOTIFICATION_KEYS = ("Message", "MessageId", "Subject", "Timestamp", "TopicArn", "Type")
_SUBSCRIPTION_KEYS = ("Message", "MessageId", "SubscribeURL", "Timestamp", "Token", "TopicArn", "Type")
_TYPES = {"Notification", "SubscriptionConfirmation", "UnsubscribeConfirmation"}

_cert_cache: dict[str, object] = {}


def _sns_host() -> str:
    return f"sns.{get_settings().AWS_REGION}.amazonaws.com"


def is_sns_url(url: str | None, *, pem: bool = False) -> bool:
    """URL https no host do SNS da nossa região (cert ou SubscribeURL)."""
    if not url or not isinstance(url, str):
        return False
    try:
        u = urlparse(url)
    except Exception:
        return False
    if u.scheme != "https" or u.hostname != _sns_host() or u.username or u.password:
        return False
    if u.port not in (None, 443):
        return False
    if pem and not u.path.endswith(".pem"):
        return False
    return True


def canonical_string(body: dict) -> str | None:
    t = body.get("Type")
    if t == "Notification":
        keys = _NOTIFICATION_KEYS
    elif t in ("SubscriptionConfirmation", "UnsubscribeConfirmation"):
        keys = _SUBSCRIPTION_KEYS
    else:
        return None
    parts: list[str] = []
    for k in keys:
        if k not in body or body[k] is None:
            if k == "Subject":  # único campo opcional
                continue
            return None
        parts.append(f"{k}\n{body[k]}\n")
    return "".join(parts)


async def _fetch_cert(url: str):
    cert = _cert_cache.get(url)
    if cert is not None:
        return cert
    async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
        r = await client.get(url)
        r.raise_for_status()
    cert = x509.load_pem_x509_certificate(r.content)
    _cert_cache[url] = cert
    return cert


def verify_with_cert(body: dict, cert) -> bool:
    """Parte pura da verificação (testável com certificado autoassinado)."""
    canon = canonical_string(body)
    if canon is None:
        return False
    version = str(body.get("SignatureVersion") or "")
    if version == "1":
        algo = hashes.SHA1()
    elif version == "2":
        algo = hashes.SHA256()
    else:
        return False
    try:
        sig = base64.b64decode(body.get("Signature") or "", validate=True)
    except Exception:
        return False
    if not sig:
        return False
    try:
        cert.public_key().verify(sig, canon.encode("utf-8"), padding.PKCS1v15(), algo)
        return True
    except InvalidSignature:
        return False
    except Exception:
        logger.exception("📧 SNS: erro inesperado ao verificar assinatura")
        return False


async def verify_sns_signature(body: dict) -> bool:
    if not isinstance(body, dict) or body.get("Type") not in _TYPES:
        return False
    cert_url = body.get("SigningCertURL")
    if not is_sns_url(cert_url, pem=True):
        logger.warning("📧 SNS: SigningCertURL fora do domínio do SNS: %r", (cert_url or "")[:200])
        return False
    try:
        cert = await _fetch_cert(cert_url)
    except Exception as e:
        logger.warning("📧 SNS: falha ao baixar certificado: %s", e.__class__.__name__)
        return False
    return verify_with_cert(body, cert)
