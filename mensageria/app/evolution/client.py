"""
Client para Evolution API v2.x
Gerencia instâncias, QR code, status e envio de mensagens.
"""
import httpx
from app.evolution.config import EVOLUTION_API_URL, EVOLUTION_API_KEY, EDUFLOW_WEBHOOK_URL


HEADERS = {
    "apikey": EVOLUTION_API_KEY,
    "Content-Type": "application/json",
}


async def create_instance(instance_name: str) -> dict:
    """Cria uma instância no Evolution API e configura o webhook."""
    async with httpx.AsyncClient(timeout=30) as client:
        # Criar instância
        res = await client.post(
            f"{EVOLUTION_API_URL}/instance/create",
            headers=HEADERS,
            json={
                "instanceName": instance_name,
                "integration": "WHATSAPP-BAILEYS",
                "qrcode": True,
                "rejectCall": False,
                "groupsIgnore": True,
                "alwaysOnline": False,
                "readMessages": False,
                "readStatus": False,
                "syncFullHistory": False,
            },
        )
        data = res.json()

        # Configurar webhook
        await client.post(
            f"{EVOLUTION_API_URL}/webhook/set/{instance_name}",
            headers=HEADERS,
            json={
                "webhook": {
                    "enabled": True,
                    "url": f"{EDUFLOW_WEBHOOK_URL}/{instance_name}",
                    "webhookByEvents": False,
                    "webhookBase64": True,
                    "events": [
                        "MESSAGES_UPSERT",
                        "CONNECTION_UPDATE",
                        "QRCODE_UPDATED",
                        "MESSAGES_UPDATE",
                        "SEND_MESSAGE",
                    ],
                }
            },
        )

        return data


async def get_instance_status(instance_name: str) -> dict:
    """Verifica o status de conexão da instância."""
    async with httpx.AsyncClient(timeout=15) as client:
        res = await client.get(
            f"{EVOLUTION_API_URL}/instance/connectionState/{instance_name}",
            headers=HEADERS,
        )
        return res.json()


async def get_qrcode(instance_name: str) -> dict:
    """Busca o QR code da instância."""
    async with httpx.AsyncClient(timeout=15) as client:
        res = await client.get(
            f"{EVOLUTION_API_URL}/instance/connect/{instance_name}",
            headers=HEADERS,
        )
        return res.json()


async def delete_instance(instance_name: str) -> dict:
    """Deleta uma instância."""
    async with httpx.AsyncClient(timeout=15) as client:
        res = await client.delete(
            f"{EVOLUTION_API_URL}/instance/delete/{instance_name}",
            headers=HEADERS,
        )
        return res.json()


async def logout_instance(instance_name: str) -> dict:
    """Desconecta o WhatsApp da instância (sem deletar)."""
    async with httpx.AsyncClient(timeout=15) as client:
        res = await client.delete(
            f"{EVOLUTION_API_URL}/instance/logout/{instance_name}",
            headers=HEADERS,
        )
        return res.json()


async def send_text(instance_name: str, to: str, text: str) -> dict:
    """Envia mensagem de texto via WhatsApp."""
    # Formata número (remove +, adiciona @s.whatsapp.net)
    number = to.replace("+", "").replace("-", "").replace(" ", "")

    async with httpx.AsyncClient(timeout=15) as client:
        res = await client.post(
            f"{EVOLUTION_API_URL}/message/sendText/{instance_name}",
            headers=HEADERS,
            json={
                "number": number,
                "text": text,
            },
        )
        return res.json()


async def send_media(instance_name: str, to: str, media_type: str, base64_data: str, filename: str, mimetype: str, caption: str = "") -> dict:
    """Envia mídia (imagem, vídeo, documento) via Evolution API."""
    number = to.replace("+", "").replace("-", "").replace(" ", "")

    # Remover prefixo data:...;base64, se existir
    if ";base64," in base64_data:
        base64_data = base64_data.split(";base64,")[1]

    async with httpx.AsyncClient(timeout=60) as client:
        res = await client.post(
            f"{EVOLUTION_API_URL}/message/sendMedia/{instance_name}",
            headers=HEADERS,
            json={
                "number": number,
                "mediatype": media_type,
                "media": base64_data,
                "fileName": filename,
                "mimetype": mimetype,
                "caption": caption,
            },
        )
        return res.json()


async def send_audio(instance_name: str, to: str, base64_data: str) -> dict:
    """Envia áudio via Evolution API usando sendWhatsAppAudio."""
    number = to.replace("+", "").replace("-", "").replace(" ", "")

    # Remover prefixo data:...;base64, se existir
    if ";base64," in base64_data:
        base64_data = base64_data.split(";base64,")[1]

    async with httpx.AsyncClient(timeout=60) as client:
        res = await client.post(
            f"{EVOLUTION_API_URL}/message/sendWhatsAppAudio/{instance_name}",
            headers=HEADERS,
            json={
                "number": number,
                "audio": base64_data,
                "encoding": True,
            },
        )
        return res.json()


async def get_profile_picture(instance_name: str, number: str) -> str | None:
    """Busca a URL da foto de perfil de um contato via Evolution API."""
    number = number.replace("+", "").replace("-", "").replace(" ", "")

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.post(
                f"{EVOLUTION_API_URL}/chat/fetchProfilePictureUrl/{instance_name}",
                headers=HEADERS,
                json={"number": number},
            )
            data = res.json()
            if isinstance(data, dict):
                return data.get("profilePictureUrl") or data.get("profilePicUrl") or None
            return None
    except Exception:
        return None


async def list_instances() -> list:
    """Lista todas as instâncias criadas."""
    async with httpx.AsyncClient(timeout=15) as client:
        res = await client.get(
            f"{EVOLUTION_API_URL}/instance/fetchInstances",
            headers=HEADERS,
        )
        return res.json()


async def fetch_all_groups(instance_name: str, get_participants: bool = False) -> list:
    """Lista grupos de uma instância via Evolution API."""
    async with httpx.AsyncClient(timeout=30) as client:
        res = await client.get(
            f"{EVOLUTION_API_URL}/group/fetchAllGroups/{instance_name}",
            headers=HEADERS,
            params={"getParticipants": "true" if get_participants else "false"},
        )
        res.raise_for_status()
        data = res.json()
        return data if isinstance(data, list) else []