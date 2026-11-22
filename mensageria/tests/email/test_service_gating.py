#!/usr/bin/env python3
"""Portões do send_one: desligado, supressão, sandbox, cota, config, SES. Com fakes.

Não toca banco nem rede: is_suppressed / sent_last_24h / ses.send são
substituídos por dublês e a sessão é um objeto que só guarda o que recebeu.

Uso: .venv/bin/python tests/email/test_service_gating.py   (exit 0 = ok)
"""
from __future__ import annotations

import asyncio

from _util import check, fim

from app.config import get_settings  # noqa: E402
from app.email import service  # noqa: E402

s = get_settings()


class FakeDB:
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        pass

    async def refresh(self, obj):
        pass


estado = {"suprimidos": set(), "enviados_24h": 0, "chamadas_ses": [], "ses_erro": None}


async def fake_is_suppressed(db, email):
    return email in estado["suprimidos"]


async def fake_sent_last_24h(db):
    return estado["enviados_24h"]


def fake_send(**kw):
    estado["chamadas_ses"].append(kw)
    if estado["ses_erro"]:
        raise estado["ses_erro"]
    return f"ses-{len(estado['chamadas_ses'])}"


service.is_suppressed = fake_is_suppressed
service.sent_last_24h = fake_sent_last_24h
service.ses.send = fake_send


def configurar(**kw):
    base = dict(
        EMAIL_ENABLED=True, EMAIL_TEST_ALLOWLIST="", EMAIL_DAILY_LIMIT=200,
        AWS_ACCESS_KEY_ID="AKIA-teste", AWS_SECRET_ACCESS_KEY="x", SES_FROM_EMAIL="envio@x.com",
        EMAIL_UNSUBSCRIBE_SECRET="segredo", EMAIL_PUBLIC_BASE_URL="https://u.test",
    )
    base.update(kw)
    for k, v in base.items():
        setattr(s, k, v)
    estado.update(suprimidos=set(), enviados_24h=0, chamadas_ses=[], ses_erro=None)


def enviar(to="ana@x.com", **kw):
    db = FakeDB()
    m = asyncio.run(service.send_one(db, to_email=to, to_name="Ana", subject="Oi {nome}",
                                     html="<p>Oi {nome}</p>", **kw))
    return m, db


print("desligado")
configurar(EMAIL_ENABLED=False)
try:
    enviar(); check(False, "EMAIL_ENABLED=false levanta EmailDisabled")
except service.EmailDisabled:
    check(True, "EMAIL_ENABLED=false levanta EmailDisabled")
check(not estado["chamadas_ses"], "…e não chama o SES")

print("supressão")
configurar(); estado["suprimidos"] = {"ana@x.com"}
m, db = enviar("ANA@x.com")
check(m.status == "skipped" and m.error == "suppressed", "suprimido → skipped/suppressed")
check(not estado["chamadas_ses"], "…sem chamar o SES")
check(db.added == [m], "…e registra a linha")

print("sandbox")
configurar(EMAIL_TEST_ALLOWLIST="teste@x.com, Outro@X.com")
m, _ = enviar("ana@x.com")
check(m.status == "skipped" and m.error == "sandbox", "fora da allowlist → skipped/sandbox")
m, _ = enviar("outro@x.com")
check(m.status == "sent", "na allowlist (case-insensitive) → sent")
configurar(EMAIL_TEST_ALLOWLIST="teste@x.com"); estado["suprimidos"] = {"teste@x.com"}
m, _ = enviar("teste@x.com")
check(m.error == "suppressed", "supressão vence a allowlist")

print("cota")
configurar(EMAIL_DAILY_LIMIT=10); estado["enviados_24h"] = 10
try:
    enviar(); check(False, "cota cheia levanta QuotaExceeded")
except service.QuotaExceeded:
    check(True, "cota cheia levanta QuotaExceeded")
check(not estado["chamadas_ses"], "…sem chamar o SES")
configurar(EMAIL_DAILY_LIMIT=10, EMAIL_TEST_ALLOWLIST="z@x.com"); estado["enviados_24h"] = 10
m, _ = enviar("ana@x.com")
check(m.error == "sandbox", "pulo por sandbox não gasta nem checa cota")

print("configuração")
configurar(EMAIL_UNSUBSCRIBE_SECRET="")
m, _ = enviar()
check(m.status == "failed" and "EMAIL_UNSUBSCRIBE_SECRET" in (m.error or ""),
      "sem segredo de descadastro → failed (nunca envia sem link de saída)")
check(not estado["chamadas_ses"], "…sem chamar o SES")

print("envio")
configurar()
m, _ = enviar(job_id=7)
check(m.status == "sent" and m.ses_message_id == "ses-1" and m.sent_at is not None, "sent com id do SES")
kw = estado["chamadas_ses"][0]
check(kw["headers"]["List-Unsubscribe"].startswith("<https://u.test/api/email/unsubscribe?t="),
      "List-Unsubscribe aponta para a rota pública")
check(kw["headers"]["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click", "One-Click")
check(kw["tags"] == {"job_id": "7"}, "tag job_id")
check("https://u.test/api/email/unsubscribe" in kw["html"], "rodapé injetado no HTML")
check(kw["subject"] == "Oi Ana", "assunto interpolado")

configurar(); estado["ses_erro"] = RuntimeError("MessageRejected: Email address is not verified")
m, _ = enviar()
check(m.status == "failed" and "MessageRejected" in m.error, "erro do SES → failed (não propaga)")

m, _ = enviar("nao-é-email")
check(m.status == "failed" and m.error == "e-mail inválido", "e-mail inválido → failed")

fim()
