#!/usr/bin/env python3
"""Testes da transcrição de voice note no perfil ATENDIMENTO.

Sem pytest (mesma convenção do test_sandbox.py / test_atendimento.py).

NÃO chama a OpenAI e NÃO toca o banco: a função de transcrição é substituída por
dublê nos testes de `_display`, e os testes de `transcrever` exercitam só os
caminhos de recusa (arquivo ausente, vazio, grande demais, extensão errada), que
retornam antes de qualquer chamada de rede. Usa arquivos num diretório
temporário próprio.

Uso:
    .venv/bin/python tests/agent/test_audio.py
Exit 0 = tudo passou.
"""
from __future__ import annotations

import asyncio
import inspect
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.agent import audio as A  # noqa: E402
from app.agent import handler as H  # noqa: E402
from app.agent.profiles import PERFIL_ATENDIMENTO, PERFIL_VENDAS  # noqa: E402
from app.models import Message  # noqa: E402

_falhas: list[str] = []
_ok = 0


def check(cond: bool, rotulo: str) -> None:
    global _ok
    if cond:
        _ok += 1
        print(f"  ✔ {rotulo}")
    else:
        _falhas.append(rotulo)
        print(f"  ✘ {rotulo}")


def secao(t: str) -> None:
    print(f"\n## {t}")


class _SettingsFake:
    def __init__(self, real, **ov):
        self._real = real
        self._ov = ov

    def __getattr__(self, nome):
        if nome in self._ov:
            return self._ov[nome]
        return getattr(self._real, nome)


class settings_de:
    def __init__(self, modulo, **ov):
        self.modulo = modulo
        self.ov = ov

    def __enter__(self):
        self._orig = self.modulo.settings
        self.modulo.settings = _SettingsFake(self._orig, **self.ov)
        return self

    def __exit__(self, *exc):
        self.modulo.settings = self._orig
        return False


def _msg(content: str, transcript: str | None = None) -> Message:
    return Message(wa_message_id="x", contact_wa_id="55", direction="inbound",
                   message_type="audio", content=content, transcript=transcript)


# --------------------------------------------------------------------------- #
# 1. parse do formato local:
# --------------------------------------------------------------------------- #
def test_parse_local() -> None:
    secao("parse_local: formato que os dois webhooks gravam")

    check(A.parse_local("local:abc.ogg|audio/ogg|") == ("abc.ogg", "audio/ogg", ""),
          "arquivo + mime + caption vazia")
    check(A.parse_local("local:a.ogg|audio/ogg; codecs=opus|oi")
          == ("a.ogg", "audio/ogg; codecs=opus", "oi"),
          "mime com parâmetro e caption")
    # Caption pode conter '|' — o split é limitado para não perder texto.
    check(A.parse_local("local:a.ogg|audio/ogg|olha|isso")
          == ("a.ogg", "audio/ogg", "olha|isso"),
          "caption com '|' é preservada inteira")
    check(A.parse_local("local:a.ogg") == ("a.ogg", "", ""), "só arquivo")
    check(A.parse_local("oi, tudo bem?") == ("", "", ""), "texto normal → vazio")
    check(A.parse_local("") == ("", "", ""), "string vazia não estoura")


def test_eh_audio() -> None:
    secao("eh_audio: só áudio entra na transcrição")

    for c in ("local:a.ogg|audio/ogg|",
              "local:a.oga|audio/ogg; codecs=opus|",
              "local:a.mp3|audio/mpeg|",
              "local:a.ogg||"):           # sem mime, decide pela extensão
        check(A.eh_audio(c), f"áudio reconhecido: {c[:34]}")

    for c in ("local:a.jpg|image/jpeg|",
              "local:a.pdf|application/pdf|",
              "local:a.mp4|video/mp4|",
              "oi, meu certificado não chegou",
              ""):
        check(not A.eh_audio(c), f"NÃO é áudio: {c[:34] or '(vazio)'}")


# --------------------------------------------------------------------------- #
# 2. transcrever: caminhos de recusa (nenhum chega à rede)
# --------------------------------------------------------------------------- #
def test_transcrever_recusas() -> None:
    secao("transcrever: recusas antes de qualquer chamada de rede")

    async def corpo() -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with settings_de(A, MEDIA_DIR=tmp, AGENT_AUDIO_MAX_BYTES=1000):
                # Arquivo que não existe em disco.
                check(await A.transcrever("local:nao_existe.ogg|audio/ogg|") is None,
                      "arquivo ausente → None")

                # Content que não é mídia.
                check(await A.transcrever("oi") is None, "content sem 'local:' → None")

                # Extensão não suportada pela API.
                p = os.path.join(tmp, "a.bin")
                with open(p, "wb") as fh:
                    fh.write(b"\x00" * 10)
                check(await A.transcrever("local:a.bin|audio/ogg|") is None,
                      "extensão não suportada → None")

                # Arquivo vazio.
                vazio = os.path.join(tmp, "vazio.ogg")
                open(vazio, "wb").close()
                check(await A.transcrever("local:vazio.ogg|audio/ogg|") is None,
                      "áudio de 0 byte → None")

                # Acima do limite de tamanho.
                grande = os.path.join(tmp, "grande.ogg")
                with open(grande, "wb") as fh:
                    fh.write(b"\x00" * 2000)   # > AGENT_AUDIO_MAX_BYTES=1000
                check(await A.transcrever("local:grande.ogg|audio/ogg|") is None,
                      "áudio acima de AGENT_AUDIO_MAX_BYTES → None")

    asyncio.run(corpo())

    # O limite default tem que caber no da API (25 MB).
    check(A.settings.AGENT_AUDIO_MAX_BYTES <= 25 * 1024 * 1024,
          "AGENT_AUDIO_MAX_BYTES não passa do limite de 25 MB da API")
    check(".ogg" in A.EXTENSOES_OK,
          ".ogg (voice note do WhatsApp) está entre as extensões aceitas")

    # Nunca levanta: um áudio ruim não pode derrubar o turno.
    src = inspect.getsource(A.transcrever)
    check("except Exception" in src, "transcrever captura exceção da API")
    check("language=\"pt\"" in src,
          "fixa language='pt' (sem isso o modelo às vezes devolve tradução)")


# --------------------------------------------------------------------------- #
# 3. _display: o ponto de costura
# --------------------------------------------------------------------------- #
def test_display() -> None:
    secao("_display: mídia, áudio e cache da transcrição")

    chamadas: list[str] = []

    async def fake_ok(content: str):
        chamadas.append(content)
        return "oi, meu certificado não chegou"

    async def fake_falha(content: str):
        chamadas.append(content)
        return None

    async def corpo() -> None:
        orig = A.transcrever
        try:
            # Texto normal passa intacto, com ou sem transcrição ligada.
            A.transcrever = fake_ok
            check(await H._display(_msg("oi tudo bem"), True) == "oi tudo bem",
                  "texto normal passa intacto")
            check(not chamadas, "texto normal NÃO chama a transcrição")

            # Transcrição desligada: áudio vira o marcador de mídia de sempre.
            chamadas.clear()
            saida = await H._display(_msg("local:a.ogg|audio/ogg|"), False)
            check(saida == "[a pessoa enviou um arquivo de mídia]",
                  "transcrever=False → marcador de mídia (comportamento antigo)")
            check(not chamadas, "transcrever=False NÃO chama a API")

            # Mídia que não é áudio nunca é transcrita.
            chamadas.clear()
            saida = await H._display(_msg("local:a.pdf|application/pdf|"), True)
            check(saida == "[a pessoa enviou um arquivo de mídia]",
                  "PDF segue como marcador de mídia")
            check(not chamadas, "PDF NÃO chama a transcrição")

            # Caminho feliz: transcreve e GRAVA em m.transcript.
            chamadas.clear()
            m = _msg("local:a.ogg|audio/ogg|")
            saida = await H._display(m, True)
            check(saida == "oi, meu certificado não chegou", "áudio → texto transcrito")
            check(m.transcript == "oi, meu certificado não chegou",
                  "transcrição é gravada em m.transcript (sobe no commit do turno)")
            check(len(chamadas) == 1, "chamou a transcrição uma vez")

            # Já transcrito: reusa e NÃO paga de novo. É o ponto do cache.
            chamadas.clear()
            m2 = _msg("local:b.ogg|audio/ogg|", transcript="texto já salvo")
            check(await H._display(m2, True) == "texto já salvo",
                  "transcript existente é reaproveitado")
            check(not chamadas,
                  "NÃO chama a API quando já há transcrição (não cobra 2x)")

            # Falha: marcador explícito, nunca silêncio.
            A.transcrever = fake_falha
            chamadas.clear()
            m3 = _msg("local:c.ogg|audio/ogg|")
            saida = await H._display(m3, True)
            check(saida == H.AUDIO_NAO_ENTENDIDO,
                  "falha → marcador de áudio não transcrito")
            check(m3.transcript is None,
                  "falha NÃO grava transcript (permite nova tentativa)")
            check("não foi possível transcrever" in H.AUDIO_NAO_ENTENDIDO,
                  "o marcador diz ao modelo o que aconteceu")
        finally:
            A.transcrever = orig

    asyncio.run(corpo())


# --------------------------------------------------------------------------- #
# 4. gating: só atendimento transcreve
# --------------------------------------------------------------------------- #
def test_so_atendimento_transcreve() -> None:
    secao("gating: transcrição só no perfil atendimento")

    src = inspect.getsource(H._process)
    check("perfil == PERFIL_ATENDIMENTO and settings.AGENT_AUDIO_TRANSCRIBE" in src,
          "_process só transcreve no perfil atendimento e com a setting ligada")
    check("await _display(m, transcrever)" in src,
          "_display recebe a decisão, não a toma")
    # O canal 6 (vendas) tem que seguir ignorando mídia como sempre.
    check(PERFIL_VENDAS != PERFIL_ATENDIMENTO, "os perfis são distintos")
    check("profile=perfil" in src,
          "o perfil é calculado uma vez e reaproveitado no run_turn")


def test_webhook_acorda_com_audio() -> None:
    secao("webhook: voice note acorda o agente")

    src = inspect.getsource(__import__("app.evolution.routes",
                                       fromlist=["webhook"]).webhook)
    check("eh_audio_p_agente" in src, "o webhook calcula se o áudio deve acordar o agente")
    check('msg_type == "audio"' in src, "a condição olha msg_type == 'audio'")
    check("AGENT_AUDIO_TRANSCRIBE" in src, "respeita a setting de desligar")
    check("texto_do_agente or eh_audio_p_agente" in src,
          "dispatch aceita texto OU áudio")
    check('texto_do_agente or "[áudio]"' in src,
          "job de áudio leva marcador (o texto real vem da transcrição no handler)")
    # A transcrição NÃO pode rodar no webhook: ele tem que devolver rápido.
    check("transcrever" not in src.replace("AGENT_AUDIO_TRANSCRIBE", ""),
          "o webhook NÃO transcreve (isso é do handler, pós-debounce)")


def test_prompt_regra_audio() -> None:
    secao("prompt da Nat: regra 7 (áudio)")

    from app.agent.prompt_atendimento import build_atendimento_prompt

    p = build_atendimento_prompt("# Base\nlinha.", "- (cat)", "20/10/2026")
    check("7. Áudio:" in p, "regra 7 está no prompt")
    check("não chute o que ela disse" in p,
          "a regra proíbe adivinhar o conteúdo do áudio")
    check("entre colchetes é descrição do sistema" in p,
          "explica que o marcador não é fala da pessoa")

    # O prompt de VENDAS não pode ter ganhado regra de áudio.
    from app.agent.prompt import build_system_prompt
    v = build_system_prompt([{"slug": "x", "name": "X", "kind": "congresso"}], "20/10/2026")
    check("Áudio:" not in v, "prompt de vendas segue sem regra de áudio")


def test_opt_out_por_audio_e_limitacao_conhecida() -> None:
    """Documenta uma limitação real em forma de teste, para não ser surpresa.

    `_checar_opt_out` roda ANTES do debounce, com o texto que veio do webhook —
    que para áudio é o marcador "[áudio]". Logo, "SAIR" falado não descadastra.
    """
    secao("limitação conhecida: opt-out falado em áudio não descadastra")

    check(not H.eh_opt_out("[áudio]", ["sair", "parar"]),
          "o marcador de áudio não casa com palavra de opt-out")
    src = inspect.getsource(H.handle_inbound)
    check(src.index("_checar_opt_out") < src.index("AGENT_DEBOUNCE_SECONDS"),
          "opt-out é checado antes do debounce (e, portanto, antes da transcrição)")


def main() -> int:
    test_parse_local()
    test_eh_audio()
    test_transcrever_recusas()
    test_display()
    test_so_atendimento_transcreve()
    test_webhook_acorda_com_audio()
    test_prompt_regra_audio()
    test_opt_out_por_audio_e_limitacao_conhecida()

    print("\n" + "=" * 60)
    if _falhas:
        print(f"❌ {len(_falhas)} falha(s) de {_ok + len(_falhas)}:")
        for f in _falhas:
            print(f"  - {f}")
        return 1
    print(f"✅ {_ok}/{_ok} checagens passaram.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
