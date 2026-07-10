# Remux de áudio para o inbox (ver app/media_convert.py).
#
#   docker build -t audioconv:1 docker/audioconv
#
# O MediaRecorder do navegador grava Opus dentro de um contêiner WebM, e o
# WhatsApp Cloud API rejeita audio/webm (testado: code=100) mas aceita audio/ogg.
# Como os dois carregam o MESMO codec Opus, basta remuxar — nada de re-encode.
#
# mkvtoolnix são 12 pacotes / 220 MB. ffmpeg faria o mesmo com 145 pacotes.
FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends mkvtoolnix \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /work
