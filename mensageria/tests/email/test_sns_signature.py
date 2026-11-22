#!/usr/bin/env python3
"""Assinatura SNS com certificado AUTOASSINADO gerado aqui. Sem rede.

Cobre: string canônica (Notification com/sem Subject, SubscriptionConfirmation),
SignatureVersion 1 (SHA1) e 2 (SHA256), adulteração, versão desconhecida,
validação do SigningCertURL e o caminho async com o cache de certificado
pré-populado (não baixa nada).

Uso: .venv/bin/python tests/email/test_sns_signature.py   (exit 0 = ok)
"""
from __future__ import annotations

import asyncio
import base64
from datetime import datetime, timedelta, timezone

from _util import check, fim

from cryptography import x509  # noqa: E402
from cryptography.hazmat.primitives import hashes  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import padding, rsa  # noqa: E402
from cryptography.x509.oid import NameOID  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.email import sns  # noqa: E402

get_settings().AWS_REGION = "us-east-1"

key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "sns.amazonaws.com")])
now = datetime.now(timezone.utc)
cert = (
    x509.CertificateBuilder()
    .subject_name(name).issuer_name(name).public_key(key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=1))
    .sign(key, hashes.SHA256())
)
CERT_URL = "https://sns.us-east-1.amazonaws.com/SimpleNotificationService-teste.pem"


def assinar(body: dict, version: str) -> dict:
    b = dict(body, SignatureVersion=version, SigningCertURL=CERT_URL)
    canon = sns.canonical_string(b)
    algo = hashes.SHA1() if version == "1" else hashes.SHA256()
    b["Signature"] = base64.b64encode(key.sign(canon.encode(), padding.PKCS1v15(), algo)).decode()
    return b


NOTIF = {
    "Type": "Notification",
    "MessageId": "m-1",
    "TopicArn": "arn:aws:sns:us-east-1:123:mensage-ses-events",
    "Subject": "Amazon SES Email Event Notification",
    "Message": '{"eventType":"Delivery","mail":{"messageId":"abc"}}',
    "Timestamp": "2026-11-22T12:00:00.000Z",
}
SUB = {
    "Type": "SubscriptionConfirmation",
    "MessageId": "m-2",
    "Token": "tok",
    "TopicArn": NOTIF["TopicArn"],
    "Message": "You have chosen to subscribe...",
    "SubscribeURL": "https://sns.us-east-1.amazonaws.com/?Action=ConfirmSubscription&Token=tok",
    "Timestamp": "2026-11-22T12:00:00.000Z",
}

print("string canônica")
c = sns.canonical_string(NOTIF)
check(c.startswith("Message\n") and "Subject\n" in c and c.endswith("Type\nNotification\n"),
      "Notification: ordem e formato")
sem_subj = {k: v for k, v in NOTIF.items() if k != "Subject"}
check("Subject" not in sns.canonical_string(sem_subj), "Subject é opcional")
check("SubscribeURL\n" in sns.canonical_string(SUB) and "Token\n" in sns.canonical_string(SUB),
      "SubscriptionConfirmation inclui SubscribeURL e Token")
check(sns.canonical_string({"Type": "Outro"}) is None, "tipo desconhecido → None")
check(sns.canonical_string({k: v for k, v in NOTIF.items() if k != "MessageId"}) is None,
      "campo obrigatório ausente → None")

print("verify_with_cert")
for v in ("1", "2"):
    check(sns.verify_with_cert(assinar(NOTIF, v), cert), f"Notification v{v} válida")
    check(sns.verify_with_cert(assinar(SUB, v), cert), f"SubscriptionConfirmation v{v} válida")
adult = assinar(NOTIF, "2"); adult["Message"] = '{"eventType":"Complaint"}'
check(not sns.verify_with_cert(adult, cert), "Message adulterada → inválida")
troca = assinar(NOTIF, "1"); troca["SignatureVersion"] = "2"
check(not sns.verify_with_cert(troca, cert), "versão trocada → inválida")
v3 = assinar(NOTIF, "2"); v3["SignatureVersion"] = "3"
check(not sns.verify_with_cert(v3, cert), "versão desconhecida → inválida")
lixo = assinar(NOTIF, "2"); lixo["Signature"] = "não-é-base64!!"
check(not sns.verify_with_cert(lixo, cert), "assinatura não-base64 → inválida (não levanta)")

print("SigningCertURL")
check(sns.is_sns_url(CERT_URL, pem=True), "URL oficial aceita")
for ruim in [
    "http://sns.us-east-1.amazonaws.com/x.pem",
    "https://sns.us-east-1.amazonaws.com.evil.com/x.pem",
    "https://evil.com/sns.us-east-1.amazonaws.com/x.pem",
    "https://sns.us-west-2.amazonaws.com/x.pem",
    "https://user@sns.us-east-1.amazonaws.com/x.pem",
    "https://sns.us-east-1.amazonaws.com/x.txt",
    "https://sns.us-east-1.amazonaws.com:8443/x.pem",
    None,
]:
    check(not sns.is_sns_url(ruim, pem=True), f"rejeita {ruim!r}")

print("verify_sns_signature (async, cache pré-populado — sem rede)")
sns._cert_cache[CERT_URL] = cert
check(asyncio.run(sns.verify_sns_signature(assinar(NOTIF, "2"))), "válida")
check(not asyncio.run(sns.verify_sns_signature({})), "{} → False (a rota devolve 403)")
fora = assinar(NOTIF, "2"); fora["SigningCertURL"] = "https://evil.com/x.pem"
check(not asyncio.run(sns.verify_sns_signature(fora)), "cert fora do SNS → False")

fim()
