"""Conversão de documentos num container descartável (docker/docconv/Dockerfile).

Cada conversão roda um container próprio, sem rede e com teto de memória. Só um
container por vez (semáforo): o backend divide ~620 MB livres com o Postgres e o
Next, e o uvicorn que sofreria o OOM é o mesmo que recebe os webhooks.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import uuid
from pathlib import Path

from app.config import get_settings

_settings = get_settings()

# Extensões de entrada por família. A família decide os alvos possíveis.
_TEXT_IN = {"doc", "docx", "odt", "rtf", "txt", "html", "htm"}
_SHEET_IN = {"xls", "xlsx", "ods", "csv"}
_PDF_IN = {"pdf"}

TARGETS: dict[str, list[str]] = {
    "text": ["pdf", "docx", "odt", "txt"],
    "sheet": ["pdf", "xlsx", "csv", "ods"],
    "pdf": ["docx", "txt"],
}

# Nome do filtro de exportação do soffice por extensão alvo.
_SOFFICE_FILTER = {
    "pdf": "pdf",
    "docx": "docx:MS Word 2007 XML",
    "odt": "odt",
    "txt": "txt:Text (encoded):UTF8",
    "xlsx": "xlsx:Calc MS Excel 2007 XML",
    "ods": "ods",
    "csv": "csv",
}

MIME_BY_EXT = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "odt": "application/vnd.oasis.opendocument.text",
    "txt": "text/plain; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "ods": "application/vnd.oasis.opendocument.spreadsheet",
    "csv": "text/csv; charset=utf-8",
}


class ConversionError(Exception):
    """Falha de conversão já traduzida para mensagem de usuário."""


def family_of(ext: str) -> str | None:
    if ext in _TEXT_IN:
        return "text"
    if ext in _SHEET_IN:
        return "sheet"
    if ext in _PDF_IN:
        return "pdf"
    return None


def targets_for(ext: str) -> list[str]:
    fam = family_of(ext)
    if not fam:
        return []
    # Converter para o próprio formato não faz sentido.
    return [t for t in TARGETS[fam] if t != ext]


# Um container por vez. Ver docstring do módulo.
_slot = asyncio.Semaphore(_settings.DOC_CONVERT_CONCURRENCY)


def _pdf2docx_script(out_name: str) -> str:
    return (
        "from pdf2docx import Converter;"
        "c=Converter('/work/in.pdf');"
        f"c.convert('/work/{out_name}');"
        "c.close()"
    )


def _pdf2txt_script(out_name: str) -> str:
    return (
        "import fitz;"
        "d=fitz.open('/work/in.pdf');"
        f"open('/work/{out_name}','w',encoding='utf-8')"
        ".write(chr(12).join(p.get_text() for p in d))"
    )


def _build_command(src_ext: str, dst_ext: str) -> tuple[list[str], str]:
    """Devolve (argv dentro do container, nome do arquivo de saída em /work)."""
    if src_ext == "pdf":
        out_name = f"out.{dst_ext}"
        script = _pdf2docx_script(out_name) if dst_ext == "docx" else _pdf2txt_script(out_name)
        return ["python3", "-c", script], out_name

    # soffice nomeia a saída como <stem-da-entrada>.<ext>; a entrada é sempre in.<ext>.
    out_name = f"in.{dst_ext}"
    argv = [
        "soffice",
        "--headless",
        # Sem um profile próprio e gravável o soffice aborta com rc=77.
        "-env:UserInstallation=file:///tmp/lo",
        # --outdir precisa vir logo após o --convert-to, nessa ordem.
        "--convert-to",
        _SOFFICE_FILTER[dst_ext],
        "--outdir",
        "/work",
        f"/work/in.{src_ext}",
    ]
    return argv, out_name


def _docker_argv(job_id: str, job_dir: Path, inner: list[str]) -> list[str]:
    mem = _settings.DOC_CONVERT_MEMORY
    return [
        "docker",
        "run",
        "--rm",
        "--name",
        f"docconv-{job_id}",
        # O conversor nunca precisa de rede; documento hostil não chama ninguém.
        "--network=none",
        f"--memory={mem}",
        # Sem isto o container usaria swap e o teto de memória viraria decorativo.
        f"--memory-swap={mem}",
        "--cpus=1.0",
        "--pids-limit=256",
        "--security-opt=no-new-privileges",
        "--read-only",
        "--tmpfs=/tmp:rw,size=64m,mode=1777",
        "-u",
        f"{os.getuid()}:{os.getgid()}",
        "-v",
        f"{job_dir}:/work",
        _settings.DOC_CONVERT_IMAGE,
        *inner,
    ]


async def _force_remove(job_id: str) -> None:
    proc = await asyncio.create_subprocess_exec(
        "docker", "rm", "-f", f"docconv-{job_id}",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.wait()


async def convert(content: bytes, src_ext: str, dst_ext: str) -> tuple[Path, Path]:
    """Converte `content` de src_ext para dst_ext.

    Devolve (arquivo_convertido, diretório_do_job). O chamador é responsável por
    apagar o diretório depois de servir o arquivo.
    """
    if dst_ext not in targets_for(src_ext):
        raise ConversionError(f"Conversão de .{src_ext} para .{dst_ext} não é suportada.")

    job_id = uuid.uuid4().hex
    job_dir = Path(_settings.DOC_CONVERT_DIR) / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    try:
        (job_dir / f"in.{src_ext}").write_bytes(content)
        inner, out_name = _build_command(src_ext, dst_ext)
        argv = _docker_argv(job_id, job_dir, inner)

        async with _slot:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            try:
                out, _ = await asyncio.wait_for(
                    proc.communicate(), timeout=_settings.DOC_CONVERT_TIMEOUT
                )
            except asyncio.TimeoutError:
                await _force_remove(job_id)
                raise ConversionError(
                    f"A conversão passou de {_settings.DOC_CONVERT_TIMEOUT}s e foi cancelada. "
                    "O arquivo pode ser grande ou complexo demais."
                )

        log = (out or b"").decode("utf-8", "replace").strip()

        if proc.returncode == 137:
            raise ConversionError(
                "O arquivo exigiu mais memória que o limite do conversor. "
                "Tente um arquivo menor."
            )
        if proc.returncode != 0:
            print(f"⚠️ docconv job={job_id} {src_ext}->{dst_ext} rc={proc.returncode}: {log[-500:]}")
            raise ConversionError("Não foi possível converter este arquivo.")

        produced = job_dir / out_name
        # rc=0 com saída ausente acontece: o soffice reporta sucesso quando o filtro
        # de exportação não existe para o módulo que abriu o arquivo.
        if not produced.exists() or produced.stat().st_size == 0:
            print(f"⚠️ docconv job={job_id} {src_ext}->{dst_ext} rc=0 sem saída: {log[-500:]}")
            raise ConversionError(
                f"O conversor não gerou um .{dst_ext} a partir deste arquivo."
            )

        return produced, job_dir
    except Exception:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise
