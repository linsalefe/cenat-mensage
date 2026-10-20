"""Rotas do módulo Evolution (mensageria mono-tenant).

Portado de backend/app/evolution/routes.py do EduFlow. Simplificações nesta fase:
- Removida auth (`get_current_user`, `get_tenant_id`) — endpoints abertos por ora.
- Removidos modelos não portados: Pipeline, Tenant, AIConfig, KnowledgeDocument,
  AIConversationSummary, CallLog, LandingPage, FormSubmission, Schedule.
- Bloco "Agente IA" do webhook removido (não há IA local — cérebro fica em
  portal.eduflowia.com se e quando webhooks das instâncias forem migrados).
- Módulos chatbot/automations serão portados na Fase 2.
"""
from __future__ import annotations

import base64 as b64module
import os
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select

from app.auth import get_current_user
from app.config import get_settings
from app.deps import DbSession
from app.evolution import client
from app.evolution.config import (
    EVOLUTION_API_KEY,
    EVOLUTION_API_URL,
    MEDIA_DIR,
)
from app.models import Channel, Contact, Message

_settings = get_settings()


def verify_webhook_secret(x_webhook_secret: str | None = Header(None)) -> None:
    """Se WEBHOOK_SECRET está setado no .env, exige header match. Vazio = aceita tudo."""
    if not _settings.WEBHOOK_SECRET:
        return
    if x_webhook_secret != _settings.WEBHOOK_SECRET:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Webhook secret inválido",
        )


# Perfis e máscara de log: módulos neutros (sem OpenAI, sem o loop do agente),
# então podem vir no import de topo.
from app.agent.phone import mask as _mask
from app.agent.profiles import (
    PERFIL_ATENDIMENTO as _PERFIL_ATENDIMENTO,
    channel_profile as _channel_profile,
)


def _eh_eco_da_ia(wa_id: str, texto: str) -> bool:
    """Wrapper com import tardio: mantém a propriedade de que o webhook não
    depende do módulo do agente para funcionar.

    Falha → False, isto é, "trata como humano e pausa". É o lado certo: se o
    módulo do agente está quebrado, o dispatch abaixo também falhou e a IA não
    respondeu nada — logo um `fromMe` é mesmo de um humano.
    """
    try:
        from app.agent.handler import eh_eco_da_ia

        return eh_eco_da_ia(wa_id, texto)
    except Exception as e:  # pragma: no cover
        print(f"⚠️ checagem de eco da IA falhou ({e!r}) — tratando como humano",
              flush=True)
        return False


def _resolver_telefone(key: dict, remote_jid: str) -> tuple[str, bool]:
    """Telefone do contato a partir do `key` do Evolution.

    Devolve `(identificador, lid_sem_telefone)`.

    O WhatsApp passou a entregar `remoteJid` no formato `<numero>@lid` (LID =
    identificador opaco do dispositivo) em vez do telefone. Quando isso
    acontece, o número real vem em `remoteJidAlt` ou `senderPn`. Se nenhum dos
    dois trouxer um `@s.whatsapp.net`, persistimos como antes — a mensagem não
    se perde e aparece no inbox — mas NÃO acordamos o agente: responder a um
    identificador que não é telefone criaria contato fantasma e a resposta não
    chegaria a ninguém.
    """
    if not remote_jid.endswith("@lid"):
        return remote_jid.replace("@s.whatsapp.net", ""), False

    for campo in ("remoteJidAlt", "senderPn"):
        alt = (key.get(campo) or "").strip()
        if alt.endswith("@s.whatsapp.net"):
            return alt.replace("@s.whatsapp.net", ""), False

    return remote_jid.replace("@lid", ""), True


router = APIRouter(
    prefix="/api/evolution",
    tags=["Evolution API"],
    dependencies=[Depends(get_current_user)],
)
webhook_router = APIRouter(prefix="/api/evolution", tags=["Evolution Webhook"])

SP_TZ = timezone(timedelta(hours=-3))

MEDIA_TYPE_MAP = {
    "imageMessage": "image",
    "audioMessage": "audio",
    "pttMessage": "audio",
    "videoMessage": "video",
    "documentMessage": "document",
    "documentWithCaptionMessage": "document",
    "stickerMessage": "sticker",
}

# Tipos já normalizados por MEDIA_TYPE_MAP que são mídia, não texto.
TIPOS_MIDIA = ("image", "audio", "video", "document", "sticker")

EXT_MAP = {
    "audio/ogg; codecs=opus": ".ogg",
    "audio/ogg": ".ogg",
    "audio/mpeg": ".mp3",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "video/mp4": ".mp4",
    "application/pdf": ".pdf",
}


class CreateInstanceRequest(BaseModel):
    name: str
    purpose: str = "commercial"


# ============================================================
# INSTÂNCIAS
# ============================================================

@router.get("/instances")
async def list_instances():
    """Lista todas as instâncias configuradas no Evolution API."""
    try:
        return await client.list_instances()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/instances")
async def create_instance(req: CreateInstanceRequest, db: DbSession):
    """Cria uma instância no Evolution API e persiste como canal local."""
    instance_name = req.name.lower().replace(" ", "_").replace("-", "_")

    try:
        await client.create_instance(instance_name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro ao criar instância: {exc}") from exc

    channel = Channel(
        name=req.name,
        type="whatsapp",
        provider="evolution",
        instance_name=instance_name,
        is_active=True,
        is_connected=False,
    )
    db.add(channel)
    await db.commit()
    await db.refresh(channel)

    qr = await client.get_qrcode(instance_name)

    return {
        "channel_id": channel.id,
        "instance_name": instance_name,
        "purpose": req.purpose,
        "qrcode": qr,
    }


@router.get("/instances/{instance_name}/qrcode")
async def get_qrcode(instance_name: str):
    try:
        return await client.get_qrcode(instance_name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/instances/{instance_name}/status")
async def get_status(instance_name: str, db: DbSession):
    try:
        status = await client.get_instance_status(instance_name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    state = status.get("instance", {}).get("state", "close")
    is_connected = state == "open"

    result = await db.execute(select(Channel).where(Channel.instance_name == instance_name))
    channel = result.scalar_one_or_none()
    if channel:
        channel.is_connected = is_connected
        await db.commit()

    return {"instance_name": instance_name, "state": state, "is_connected": is_connected}


@router.delete("/instances/{instance_name}")
async def delete_instance(instance_name: str, db: DbSession):
    """Deleta instância no Evolution e o canal correspondente. Preserva contatos e mensagens."""
    try:
        await client.delete_instance(instance_name)
    except Exception:
        pass

    result = await db.execute(select(Channel).where(Channel.instance_name == instance_name))
    channel = result.scalar_one_or_none()
    if channel:
        from sqlalchemy import text
        await db.execute(
            text("UPDATE mensageria.contacts SET channel_id = NULL WHERE channel_id = :ch_id"),
            {"ch_id": channel.id},
        )
        await db.delete(channel)
        await db.commit()

    return {"status": "deleted", "instance_name": instance_name}


@router.post("/instances/{instance_name}/logout")
async def logout_instance(instance_name: str, db: DbSession):
    try:
        await client.logout_instance(instance_name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    result = await db.execute(select(Channel).where(Channel.instance_name == instance_name))
    channel = result.scalar_one_or_none()
    if channel:
        channel.is_connected = False
        await db.commit()

    return {"status": "logged_out", "instance_name": instance_name}


# ============================================================
# WEBHOOK
# ============================================================

async def _download_media(
    instance_name: str, key: dict, mime: str
) -> str:
    """Baixa mídia via Evolution API e salva em disco. Retorna filename local ou string vazia."""
    os.makedirs(MEDIA_DIR, exist_ok=True)
    ext = EXT_MAP.get(mime.split(";")[0].strip(), ".bin")
    local_filename = f"{uuid.uuid4().hex}{ext}"

    try:
        async with httpx.AsyncClient(timeout=30) as http:
            resp = await http.post(
                f"{EVOLUTION_API_URL}/chat/getBase64FromMediaMessage/{instance_name}",
                json={"message": {"key": key}, "convertToMp4": False},
                headers={"apikey": EVOLUTION_API_KEY},
            )
            if resp.status_code not in (200, 201):
                print(f"⚠️ Erro ao baixar mídia: {resp.status_code}")
                return ""

            b64_data = resp.json().get("base64", "")
            if not b64_data:
                return ""

            file_bytes = b64module.b64decode(b64_data)
            filepath = os.path.join(MEDIA_DIR, local_filename)
            with open(filepath, "wb") as f:
                f.write(file_bytes)
            print(f"📎 Mídia salva: {filepath} ({len(file_bytes)} bytes)")
            return local_filename
    except Exception as exc:
        print(f"⚠️ Erro ao salvar mídia: {exc}")
        return ""


async def _fetch_group_name(instance_name: str, group_jid: str, fallback: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=5) as http_client:
            resp = await http_client.get(
                f"{EVOLUTION_API_URL}/group/findGroupInfos/{instance_name}",
                params={"groupJid": group_jid},
                headers={"apikey": EVOLUTION_API_KEY},
            )
            if resp.status_code == 200:
                return resp.json().get("subject", fallback)
    except Exception as exc:
        print(f"⚠️ Erro ao buscar nome do grupo: {exc}")
    return fallback


@webhook_router.post("/webhook/{instance_name}", dependencies=[Depends(verify_webhook_secret)])
async def webhook(instance_name: str, request: Request, db: DbSession):
    """Recebe eventos do Evolution API (CONNECTION_UPDATE, MESSAGES_UPSERT, ...).

    Nesta fase: apenas persiste mensagens e contatos. Não há processamento de IA,
    chatbot ou automações (esses módulos vêm na Fase 2).
    """
    try:
        payload = await request.json()
        event = payload.get("event", "").upper().replace(".", "_")

        print(f"📩 Evolution webhook [{instance_name}]: {event}")

        if event == "CONNECTION_UPDATE":
            state = payload.get("data", {}).get("state", "")
            is_connected = state == "open"

            result = await db.execute(
                select(Channel).where(Channel.instance_name == instance_name)
            )
            channel = result.scalar_one_or_none()
            if channel:
                channel.is_connected = is_connected
                if is_connected:
                    owner = payload.get("data", {}).get("instance", "")
                    if owner:
                        channel.phone_number = owner
                await db.commit()

            print(f"🔗 Conexão [{instance_name}]: {state}")

        elif event == "MESSAGES_UPSERT":
            data = payload.get("data", {})
            messages = data if isinstance(data, list) else [data]

            result = await db.execute(
                select(Channel).where(Channel.instance_name == instance_name)
            )
            channel = result.scalar_one_or_none()
            channel_id = channel.id if channel else None

            # O canal é da Nat? Só aí valem as regras de ativação no 1º inbound
            # e de pausa quando um humano responde. Canal de disparo (ex.: 9
            # "comunicados") segue com o comportamento de sempre.
            canal_atendimento = bool(
                channel
                and channel.agent_enabled
                and _channel_profile(channel) == _PERFIL_ATENDIMENTO
            )
            agent_jobs: list[tuple[int, str, str, str]] = []

            for msg in messages:
                key = msg.get("key", {})
                from_me = key.get("fromMe", False)
                remote_jid = key.get("remoteJid", "")
                msg_id = key.get("id", "")

                is_group = "@g.us" in remote_jid
                lid_sem_telefone = False

                if is_group:
                    phone = remote_jid
                    participant = key.get("participant", "") or msg.get("participant", "")
                    sender_name = msg.get("pushName", participant.replace("@s.whatsapp.net", ""))
                else:
                    phone, lid_sem_telefone = _resolver_telefone(key, remote_jid)
                    sender_name = msg.get("pushName", phone)

                message_content = msg.get("message", {})
                raw_msg_type = msg.get("messageType", "text")
                msg_type = MEDIA_TYPE_MAP.get(raw_msg_type, raw_msg_type)

                text_content = (
                    message_content.get("conversation", "")
                    or message_content.get("extendedTextMessage", {}).get("text", "")
                )

                if not text_content and msg_type not in TIPOS_MIDIA:
                    continue

                # Guardado AQUI, antes de a mídia sobrescrever `text_content`
                # com "local:...". Também não dá para decidir "é texto?" por
                # `msg_type`: texto com link ou em resposta a outra mensagem
                # chega como `extendedTextMessage`, e um teste contra
                # ("text", "conversation") deixaria a Nat muda nesses casos.
                texto_do_agente = (
                    text_content if (text_content and msg_type not in TIPOS_MIDIA) else ""
                )
                # Voice note também acorda o agente: o texto real só existe
                # depois da transcrição, que roda no handler (pós-debounce). O
                # que vai no job é um marcador — `_process` relê a mensagem do
                # banco e transcreve de lá.
                eh_audio_p_agente = bool(
                    msg_type == "audio" and _settings.AGENT_AUDIO_TRANSCRIBE
                )

                direction = "outbound" if from_me else "inbound"
                contact_phone = phone

                # Criar/atualizar contato só em mensagens recebidas
                if not from_me:
                    contact_result = await db.execute(
                        select(Contact).where(Contact.wa_id == contact_phone)
                    )
                    contact = contact_result.scalar_one_or_none()

                    if not contact:
                        display_name = sender_name
                        if is_group:
                            display_name = await _fetch_group_name(
                                instance_name, contact_phone, sender_name,
                            )

                        from app.crm.enroll import resolve_default_pipeline_id

                        ch_obj = await db.get(Channel, channel_id) if channel_id else None
                        pipeline_id = await resolve_default_pipeline_id(ch_obj, db)
                        contact = Contact(
                            wa_id=contact_phone,
                            name=display_name,
                            channel_id=channel_id,
                            pipeline_id=pipeline_id,
                            lead_status="novo",
                            ai_active=False if is_group else True,
                            last_inbound_at=datetime.now(SP_TZ).replace(tzinfo=None),
                            reengagement_count=0,
                            is_group=is_group,
                        )
                        db.add(contact)
                        await db.flush()
                        print(f"👤 Novo contato: {display_name} ({contact_phone})")
                    else:
                        # ANTES de sobrescrever: "nunca falou" é a condição da
                        # ativação no 1º inbound, e `last_inbound_at` é o único
                        # registro disso. Lido depois, seria sempre falso.
                        nunca_falou = contact.last_inbound_at is None
                        contact.last_inbound_at = datetime.now(SP_TZ).replace(tzinfo=None)
                        contact.reengagement_count = 0
                        # Canal da conversa = último canal de ENTRADA. Sem isto,
                        # quem foi criado por disparo responderia pelo canal do
                        # disparo, não pelo número em que escreveu.
                        if not is_group and channel_id:
                            contact.channel_id = channel_id
                        # 1º inbound ativa a IA. Contato criado por disparo nasce
                        # ai_active=False (campaign/persistence/contacts_routes);
                        # sem isto a Nat ficaria muda justamente para a base de
                        # quem só recebeu comunicado e agora resolveu responder.
                        # Quem JÁ falou e está False é decisão humana — respeita.
                        if canal_atendimento and nunca_falou and not is_group \
                                and not contact.ai_active:
                            contact.ai_active = True
                            print(f"🤖▶️ IA ativada no 1º inbound de "
                                  f"{_mask(contact_phone)}", flush=True)

                # Eco da IA? Checado ANTES da dedup: no caminho da corrida (o
                # webhook chega antes do commit do handler) a linha ainda não
                # existe, e é justamente aí que importa não ler a IA como humano.
                eco_da_ia = bool(
                    from_me and not is_group
                    and _eh_eco_da_ia(contact_phone, text_content)
                )

                # Deduplicação por wa_message_id
                existing = await db.execute(
                    select(Message).where(Message.wa_message_id == msg_id)
                )
                if existing.scalar_one_or_none():
                    continue

                # Humano assumiu: `fromMe` que não é eco da IA veio do painel ou
                # do celular do número. Pausa a IA só para esse contato; o botão
                # do inbox devolve. Controlado por AGENT_ATENDIMENTO_PAUSE_ON_HUMAN.
                if (
                    from_me and not is_group and not eco_da_ia
                    and canal_atendimento
                    and _settings.AGENT_ATENDIMENTO_PAUSE_ON_HUMAN
                ):
                    humano = (await db.execute(
                        select(Contact).where(Contact.wa_id == contact_phone)
                    )).scalar_one_or_none()
                    if humano is not None and humano.ai_active:
                        humano.ai_active = False
                        print(f"👤 humano assumiu {_mask(contact_phone)} — IA pausada",
                              flush=True)

                # Mídia: baixar e salvar em disco
                if msg_type in TIPOS_MIDIA:
                    media = message_content.get(raw_msg_type, {})
                    if raw_msg_type == "documentWithCaptionMessage":
                        media = media.get("message", {}).get("documentMessage", {})
                    mime = media.get("mimetype", "")
                    caption = media.get("caption", "")

                    local_filename = await _download_media(instance_name, key, mime)
                    text_content = (
                        f"local:{local_filename}|{mime}|{caption}"
                        if local_filename
                        else f"[{msg_type}]"
                    )

                ts = msg.get("messageTimestamp", 0)
                msg_time = (
                    datetime.fromtimestamp(int(ts), tz=SP_TZ).replace(tzinfo=None)
                    if ts
                    else datetime.now(SP_TZ).replace(tzinfo=None)
                )

                new_msg = Message(
                    wa_message_id=msg_id,
                    contact_wa_id=contact_phone,
                    channel_id=channel_id,
                    direction=direction,
                    message_type=msg_type if msg_type != "conversation" else "text",
                    content=text_content,
                    timestamp=msg_time,
                    status="received" if not from_me else "sent",
                    sender_name=sender_name if is_group and not from_me else None,
                    sent_by_ai=eco_da_ia,
                )
                db.add(new_msg)

                # Agente (Nat): pré-filtro barato. A checagem autoritativa de
                # gating é do handler, com dados frescos — aqui só evitamos
                # acordar task para o que nunca poderia ser atendido.
                if (
                    canal_atendimento
                    and not from_me
                    and not is_group
                    and not lid_sem_telefone
                    and channel.operation_mode == "ai"
                    and (texto_do_agente or eh_audio_p_agente)
                ):
                    agent_jobs.append((
                        channel_id, contact_phone, msg_id,
                        texto_do_agente or "[áudio]",
                    ))
                elif canal_atendimento and not from_me and lid_sem_telefone:
                    print(f"⚠️ lid sem telefone ({remote_jid}) — mensagem salva, "
                          f"agente NÃO acionado", flush=True)

                if not from_me:
                    contact_update = await db.execute(
                        select(Contact).where(Contact.wa_id == contact_phone)
                    )
                    ct = contact_update.scalar_one_or_none()
                    if ct:
                        ct.updated_at = msg_time

                print(
                    f"💬 {'📤' if from_me else '📥'} [{instance_name}] "
                    f"{sender_name} ({contact_phone}): {text_content[:100]}"
                )

            await db.commit()

            # Agente DEPOIS do commit: o handler abre a própria sessão de banco e
            # precisa ver a mensagem já gravada (é o que o watermark lê). Import
            # isolado em try/except — o webhook nunca quebra por causa do agente.
            if agent_jobs:
                try:
                    import asyncio as _asyncio

                    from app.agent import handler as _agent_handler

                    for job in agent_jobs:
                        _asyncio.create_task(_agent_handler.handle_inbound(*job))
                except Exception as _e:
                    print(f"🤖❌ falha ao agendar agente (webhook intacto): {_e!r}",
                          flush=True)

        return {"status": "ok"}

    except Exception as exc:
        print(f"❌ Erro webhook Evolution [{instance_name}]: {exc}")
        return {"status": "error", "detail": str(exc)}


# ============================================================
# ENVIAR MENSAGEM
# ============================================================

@router.post("/send")
async def send_message(instance_name: str, to: str, text: str):
    """Envia mensagem de texto via Evolution."""
    try:
        result = await client.send_text(instance_name, to, text)
        return {"status": "sent", "result": result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
