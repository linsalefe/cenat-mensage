"""Remux de áudio gravado no navegador para o formato que o WhatsApp aceita.

O MediaRecorder produz `audio/webm;codecs=opus`. O Cloud API rejeita webm
(testado contra a Graph: `code=100, Param file must be a file with one of the
following types...`) mas aceita `audio/ogg` com Opus. Como o codec é o mesmo,
trocamos só o contêiner — sem re-encode, sem perda.

Roda num container descartável, mesmas travas de docker/docconv: sem rede,
rootfs read-only, sem privilégios, com teto de memória.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import uuid
from pathlib import Path

from app.config import get_settings

_settings = get_settings()


class AudioConversionError(Exception):
    """Falha de remux já traduzida para mensagem de usuário."""


async def remux_webm_to_ogg(content: bytes) -> bytes:
    """Recebe os bytes de um .webm (Opus) e devolve os bytes de um .ogg (Opus)."""
    job_id = uuid.uuid4().hex
    job_dir = Path(_settings.AUDIO_CONVERT_DIR) / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    try:
        (job_dir / "in.webm").write_bytes(content)
        # Trilha 0: o MediaRecorder em modo áudio grava uma única trilha.
        argv = [
            "docker",
            "run",
            "--rm",
            "--name",
            f"audioconv-{job_id}",
            "--network=none",
            f"--memory={_settings.AUDIO_CONVERT_MEMORY}",
            f"--memory-swap={_settings.AUDIO_CONVERT_MEMORY}",
            "--cpus=1.0",
            "--pids-limit=128",
            "--security-opt=no-new-privileges",
            "--read-only",
            "--tmpfs=/tmp:rw,size=16m",
            "-u",
            f"{os.getuid()}:{os.getgid()}",
            "-v",
            f"{job_dir}:/work",
            _settings.AUDIO_CONVERT_IMAGE,
            "mkvextract",
            "tracks",
            "/work/in.webm",
            "0:/work/out.ogg",
        ]

        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            out, _ = await asyncio.wait_for(
                proc.communicate(), timeout=_settings.AUDIO_CONVERT_TIMEOUT
            )
        except asyncio.TimeoutError:
            kill = await asyncio.create_subprocess_exec(
                "docker", "rm", "-f", f"audioconv-{job_id}",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await kill.wait()
            raise AudioConversionError("A conversão do áudio demorou demais.")

        log = (out or b"").decode("utf-8", "replace").strip()
        produced = job_dir / "out.ogg"
        if proc.returncode != 0 or not produced.exists() or produced.stat().st_size == 0:
            print(f"⚠️ audioconv job={job_id} rc={proc.returncode}: {log[-400:]}", flush=True)
            raise AudioConversionError("Não foi possível converter o áudio gravado.")

        return produced.read_bytes()
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)
