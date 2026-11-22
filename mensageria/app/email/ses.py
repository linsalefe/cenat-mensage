"""Cliente Amazon SES v2 (boto3, SÍNCRONO).

Quem chama de código async usa `asyncio.to_thread(...)`. Nada aqui toca o banco.

Credenciais vêm SÓ do .env (AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY). Sem elas
o cliente não é criado — de propósito não caímos na cadeia padrão do boto3
(variáveis do sistema, ~/.aws, metadados da instância), para o Mensage nunca
enviar com uma credencial que ninguém configurou para ele.
"""
from __future__ import annotations

from email.headerregistry import Address
from email.message import EmailMessage as MIMEMessage
from email.policy import SMTP
from email.utils import make_msgid
from functools import lru_cache

from app.config import get_settings


class EmailNotConfigured(RuntimeError):
    """Falta configuração obrigatória (credencial, remetente, segredo...)."""


@lru_cache(maxsize=1)
def get_client():
    s = get_settings()
    if not s.AWS_ACCESS_KEY_ID or not s.AWS_SECRET_ACCESS_KEY:
        raise EmailNotConfigured("credenciais AWS ausentes (AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY)")
    import boto3
    from botocore.config import Config

    return boto3.client(
        "sesv2",
        region_name=s.AWS_REGION,
        aws_access_key_id=s.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=s.AWS_SECRET_ACCESS_KEY,
        config=Config(
            connect_timeout=5,
            read_timeout=20,
            retries={"max_attempts": 3, "mode": "standard"},
        ),
    )


def build_mime(
    *,
    from_email: str,
    from_name: str | None,
    to: str,
    to_name: str | None,
    subject: str,
    html: str,
    text: str,
    reply_to: str | None = None,
    headers: dict[str, str] | None = None,
) -> bytes:
    """Monta o MIME multipart/alternative (texto + HTML) com os cabeçalhos extras.

    Separado de `send` para ser testável sem rede.
    """
    msg = MIMEMessage()
    msg["From"] = Address(display_name=from_name or "", addr_spec=from_email)
    msg["To"] = Address(display_name=to_name or "", addr_spec=to)
    msg["Subject"] = subject
    if reply_to:
        msg["Reply-To"] = reply_to
    domain = from_email.rsplit("@", 1)[-1] if "@" in from_email else None
    msg["Message-ID"] = make_msgid(domain=domain)
    for k, v in (headers or {}).items():
        msg[k] = v
    msg.set_content(text or "", subtype="plain", charset="utf-8")
    msg.add_alternative(html or "", subtype="html", charset="utf-8")
    return msg.as_bytes(policy=SMTP)


def send(
    *,
    to: str,
    to_name: str | None,
    subject: str,
    html: str,
    text: str,
    headers: dict[str, str] | None = None,
    tags: dict[str, str] | None = None,
    from_name: str | None = None,
    reply_to: str | None = None,
) -> str:
    """Envia UM e-mail via SendEmail (Content.Raw). Devolve o MessageId do SES.

    Raw (e não Simple) porque só o Raw deixa pôr `List-Unsubscribe` e
    `List-Unsubscribe-Post` (RFC 8058).
    """
    s = get_settings()
    if not s.SES_FROM_EMAIL:
        raise EmailNotConfigured("SES_FROM_EMAIL vazio")
    raw = build_mime(
        from_email=s.SES_FROM_EMAIL,
        from_name=from_name or s.SES_FROM_NAME,
        to=to,
        to_name=to_name,
        subject=subject,
        html=html,
        text=text,
        reply_to=reply_to or s.SES_REPLY_TO or None,
        headers=headers,
    )
    kwargs: dict = {
        "FromEmailAddress": s.SES_FROM_EMAIL,
        "Destination": {"ToAddresses": [to]},
        "Content": {"Raw": {"Data": raw}},
    }
    if s.SES_CONFIGURATION_SET:
        kwargs["ConfigurationSetName"] = s.SES_CONFIGURATION_SET
    if tags:
        kwargs["EmailTags"] = [{"Name": k, "Value": v} for k, v in tags.items()]
    resp = get_client().send_email(**kwargs)
    return resp["MessageId"]


def get_account() -> dict:
    return get_client().get_account()


def get_identity(identity: str) -> dict:
    return get_client().get_email_identity(EmailIdentity=identity)
