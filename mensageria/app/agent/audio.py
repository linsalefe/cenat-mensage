"""Transcrição de áudio do inbound para o agente (voice note → texto).

Por que existe: num canal de ATENDIMENTO o voice note é comum, e sem isto a
pessoa manda um áudio e recebe silêncio — o agente nem é acordado, porque o
dispatch só criava job para texto.

Onde roda: chamado pelo `handler._display`, ou seja **depois** do debounce, em
background. De propósito não roda no webhook: o webhook tem que responder
rápido ao Evolution, e uma chamada de rede de alguns segundos ali atrasaria o
ACK (e, numa rajada, transcreveria áudio que o debounce ia descartar).

O que NÃO faz: não responde em áudio. Resposta de atendimento costuma levar
link, e-mail, data e valor — em locução a pessoa não copia o link nem relê o
número. Ouvir em áudio e responder em texto é o melhor atendimento, não o pior.
TTS existe no SDK (`audio.speech`) e o Evolution envia PTT
(`send_media(media_type="audio")`), então a porta está aberta se mudar a decisão.
"""
from __future__ import annotations

import os
from typing import Optional

from openai import AsyncOpenAI

from app.config import get_settings

settings = get_settings()

# Cliente próprio, não o do `loop`: `handler` importa este módulo no topo, e
# importar o `loop` aqui arrastaria tools/guardrails/prompt para o import do
# handler — anulando o import tardio que mantém o webhook independente do agente.
_client: Optional[AsyncOpenAI] = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


# Formatos que a API de transcrição aceita e que o WhatsApp de fato manda.
# `audio/ogg; codecs=opus` é o do voice note (PTT) e já chega como .ogg pelo
# EXT_MAP do webhook — sem conversão, sem depender da imagem audioconv.
EXTENSOES_OK = (".ogg", ".oga", ".mp3", ".m4a", ".wav", ".webm", ".mp4", ".mpeg", ".mpga", ".flac")


def parse_local(content: str) -> tuple[str, str, str]:
    """`local:<arquivo>|<mime>|<caption>` → (arquivo, mime, caption).

    É o formato que os dois webhooks gravam em `messages.content`. Caption pode
    conter `|`, então o split é limitado.
    """
    if not content.startswith("local:"):
        return "", "", ""
    resto = content[len("local:"):]
    partes = resto.split("|", 2)
    arquivo = partes[0] if partes else ""
    mime = partes[1] if len(partes) > 1 else ""
    caption = partes[2] if len(partes) > 2 else ""
    return arquivo, mime, caption


def eh_audio(content: str) -> bool:
    arquivo, mime, _ = parse_local(content)
    if not arquivo:
        return False
    if mime.split(";")[0].strip().startswith("audio/"):
        return True
    return arquivo.lower().endswith((".ogg", ".oga", ".mp3", ".m4a"))


async def transcrever(content: str) -> Optional[str]:
    """Transcreve o áudio referenciado por `content`. None em qualquer falha.

    Nunca levanta: um áudio que não dá para transcrever não pode derrubar o
    turno. Quem chama decide o texto de fallback.
    """
    arquivo, mime, _ = parse_local(content)
    if not arquivo:
        return None

    caminho = os.path.join(settings.MEDIA_DIR, arquivo)
    if not os.path.isfile(caminho):
        print(f"🎙️⚠️ áudio não encontrado em disco: {arquivo}", flush=True)
        return None

    ext = os.path.splitext(arquivo)[1].lower()
    if ext not in EXTENSOES_OK:
        print(f"🎙️⚠️ extensão não suportada para transcrição: {ext}", flush=True)
        return None

    tamanho = os.path.getsize(caminho)
    if tamanho <= 0:
        print(f"🎙️⚠️ áudio vazio: {arquivo}", flush=True)
        return None
    if tamanho > settings.AGENT_AUDIO_MAX_BYTES:
        # Corta por TAMANHO e não por duração: a duração só existe no payload do
        # webhook (`audioMessage.seconds`) e aqui só temos a linha do banco.
        # Tamanho é suficiente para barrar o caso que importa — áudio muito
        # longo, que custa caro e demora mais que a paciência de quem espera.
        print(f"🎙️⚠️ áudio grande demais ({tamanho} bytes > "
              f"{settings.AGENT_AUDIO_MAX_BYTES}): {arquivo}", flush=True)
        return None

    try:
        with open(caminho, "rb") as fh:
            resp = await get_client().audio.transcriptions.create(
                model=settings.OPENAI_MODEL_TRANSCRIBE,
                file=(arquivo, fh, mime.split(";")[0].strip() or "audio/ogg"),
                # pt fixo: o público é brasileiro. Sem isto o modelo às vezes
                # "detecta" espanhol num áudio curto e devolve tradução.
                language="pt",
            )
        texto = (getattr(resp, "text", "") or "").strip()
    except Exception as e:
        print(f"🎙️❌ falha ao transcrever {arquivo}: {e!r}", flush=True)
        return None

    if not texto:
        print(f"🎙️⚠️ transcrição vazia: {arquivo}", flush=True)
        return None

    print(f"🎙️ transcrito ({tamanho} bytes, {len(texto)} chars): "
          f"{texto[:80]}", flush=True)
    return texto
