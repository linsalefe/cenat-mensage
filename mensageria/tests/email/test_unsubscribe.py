#!/usr/bin/env python3
"""Token de descadastro (HMAC). Não toca banco nem rede.

Uso: .venv/bin/python tests/email/test_unsubscribe.py   (exit 0 = ok)
"""
from __future__ import annotations

from _util import check, fim  # noqa: F401  (ajusta sys.path)

from app.config import get_settings  # noqa: E402
from app.email import unsubscribe as u  # noqa: E402

s = get_settings()
s.EMAIL_UNSUBSCRIBE_SECRET = "segredo-de-teste"
s.EMAIL_PUBLIC_BASE_URL = "https://exemplo.test/"

print("token")
t = u.make_token("Fulano@Exemplo.COM ")
check(u.verify_token(t) == "fulano@exemplo.com", "round-trip normaliza para lowercase")
check(u.make_token("fulano@exemplo.com") == t, "determinístico (sem expiração)")
check(u.verify_token(None) is None, "None → None")
check(u.verify_token("") is None, "vazio → None")
check(u.verify_token("xxx") is None, "lixo sem ponto → None")
check(u.verify_token("a.b.c") is None, "dois pontos → None")
check(u.verify_token(t + "A") is None, "assinatura adulterada → None")
outro = u.make_token("outra@exemplo.com")
check(u.verify_token(t.split(".")[0] + "." + outro.split(".")[1]) is None,
      "assinatura de outro e-mail → None")
check(u.verify_token("%%%." + t.split(".")[1]) is None, "base64 inválido → None (não levanta)")
check(u.verify_token("x" * 5000) is None, "token gigante → None")

print("segredo")
s.EMAIL_UNSUBSCRIBE_SECRET = "outro-segredo"
check(u.verify_token(t) is None, "trocar o segredo invalida links antigos")
s.EMAIL_UNSUBSCRIBE_SECRET = ""
check(u.verify_token(t) is None, "segredo vazio → None (nunca 500)")
try:
    u.make_token("a@b.com")
    check(False, "make_token sem segredo levanta")
except ValueError:
    check(True, "make_token sem segredo levanta")
s.EMAIL_UNSUBSCRIBE_SECRET = "segredo-de-teste"

print("url")
url = u.unsubscribe_url("a@b.com")
check(url.startswith("https://exemplo.test/api/email/unsubscribe?t="), "URL base sem barra dupla")
from urllib.parse import parse_qs, urlparse  # noqa: E402
tok = parse_qs(urlparse(url).query)["t"][0]
check(u.verify_token(tok) == "a@b.com", "token da URL é válido")

fim()
