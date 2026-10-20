#!/usr/bin/env python3
"""Opt-out no caminho do AGENTE (palavra do canal → descadastro).

Existe porque o template `retomada_conversa`, aprovado na Meta, promete "responda
SAIR" — e nada tratava isso no caminho do agente. O tratamento de
`opt_out_keywords` vive em `app/chatbot/engine.py`, que só roda com
`operation_mode='chatbot'`; o canal do agente está em 'ai'. A pessoa respondia
SAIR, seguia recebendo, e só saía quando a Meta devolvia 131050 — depois do
estrago e pagando por cada mensagem até lá.

Sem pytest (mesma convenção do test_sandbox.py).

Parte 1 não toca o banco (só o casamento da palavra). Parte 2 toca, com wa_id
dedicado, e limpa no `finally`. Não chama OpenAI e não envia WhatsApp.

Uso:
    .venv/bin/python tests/agent/test_opt_out.py
Exit 0 = tudo passou.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from sqlalchemy import delete, select  # noqa: E402

from app.agent import handler as H  # noqa: E402
from app.database import AsyncSessionLocal  # noqa: E402
from app.models import AgentFollowup, AgentSession, Channel, Contact  # noqa: E402

WA = "test:opt-out"
KEYWORDS = ["sair", "parar", "cancelar", "remover", "stop", "unsubscribe"]

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


# --------------------------------------------------------------------------- #
def test_casamento() -> None:
    print("\n[1] casamento da palavra (sem banco)")
    deve_casar = ["sair", "SAIR", " Sair ", "sair.", "SAIR!", "parar", "Cancelar",
                  "stop", "UNSUBSCRIBE", "remover"]
    for t in deve_casar:
        check(H.eh_opt_out(t, KEYWORDS), f"{t!r} é opt-out")

    # O ponto do desenho: mensagem que CONTÉM a palavra não descadastra.
    # O chatbot engine casaria "vou sair de casa" — aqui não, de propósito.
    nao_deve = [
        "vou sair de casa mais tarde",
        "quero parar de pensar nisso",
        "posso cancelar minha inscrição depois?",
        "sairei do trabalho às 18h",
        "não quero sair",
        "stop motion é meu tema de pesquisa",
        "",
        "oi, quanto custa?",
    ]
    for t in nao_deve:
        check(not H.eh_opt_out(t, KEYWORDS), f"{t[:38]!r} NÃO é opt-out")

    check(not H.eh_opt_out("sair", []), "sem keywords no canal, nada casa")
    check(not H.eh_opt_out("sair", None), "opt_out_keywords None não quebra")


async def limpar() -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(delete(AgentFollowup).where(AgentFollowup.contact_wa_id == WA))
        await db.execute(delete(AgentSession).where(AgentSession.contact_wa_id == WA))
        await db.execute(delete(Contact).where(Contact.wa_id == WA))
        await db.commit()


async def test_efeito(canal_id: int) -> None:
    print("\n[2] efeito no banco")
    async with AsyncSessionLocal() as db:
        db.add(Contact(wa_id=WA, name="Teste opt-out", channel_id=canal_id,
                       ai_active=True, is_group=False, opted_out=False,
                       ai_memory={}, lead_status="novo"))
        db.add(AgentSession(contact_wa_id=WA, channel_id=canal_id,
                            status="active", history=[], turns_count=0))
        await db.flush()
        db.add(AgentFollowup(contact_wa_id=WA, run_at=H._now(), kind="custom",
                             payload={}, status="pending"))
        db.add(AgentFollowup(contact_wa_id=WA, run_at=H._now(), kind="lot_deadline",
                             payload={}, status="pending"))
        await db.commit()

    enviadas: list[str] = []

    async def fake_send(db, channel, wa_id, reply):
        enviadas.append(reply)

    original, H._send = H._send, fake_send
    try:
        tratou = await H._checar_opt_out(canal_id, WA, "SAIR")
    finally:
        H._send = original

    check(tratou is True, "_checar_opt_out devolveu True para 'SAIR'")
    check(len(enviadas) == 1, f"confirmou para a pessoa (mensagens={len(enviadas)})")

    async with AsyncSessionLocal() as db:
        c = (await db.execute(select(Contact).where(Contact.wa_id == WA))).scalars().first()
        check(c is not None and c.opted_out is True, "contato marcado opted_out")
        check(c is not None and c.opted_out_at is not None, "opted_out_at gravado")
        check(c is not None and c.ai_active is False, "ai_active desligado")
        fus = (await db.execute(
            select(AgentFollowup).where(AgentFollowup.contact_wa_id == WA))).scalars().all()
        check(all(f.status == "cancelled" for f in fus),
              f"os {len(fus)} follow-ups pendentes viraram 'cancelled' "
              f"({[f.status for f in fus]})")
        s = (await db.execute(
            select(AgentSession).where(AgentSession.contact_wa_id == WA))).scalars().first()
        check(s is not None and s.status == "closed", "sessão fechada")

    # Segunda vez: não reconfirma (senão "SAIR" repetido vira ping-pong).
    enviadas.clear()
    original, H._send = H._send, fake_send
    try:
        tratou2 = await H._checar_opt_out(canal_id, WA, "sair")
    finally:
        H._send = original
    check(tratou2 is True, "2ª vez ainda é reconhecida como opt-out")
    check(len(enviadas) == 0, "2ª vez NÃO reenvia confirmação")

    # Mensagem normal de contato já descadastrado não é opt-out.
    check(await H._checar_opt_out(canal_id, WA, "quanto custa?") is False,
          "mensagem comum não é tratada como opt-out")


async def main() -> int:
    test_casamento()
    async with AsyncSessionLocal() as db:
        canal = (await db.execute(
            select(Channel).where(Channel.operation_mode == "ai").order_by(Channel.id)
        )).scalars().first()
    if canal is None:
        print("❌ nenhum canal com operation_mode='ai' — o teste precisa de um.")
        return 1
    if not (canal.opt_out_keywords or []):
        print(f"⚠️  canal {canal.id} sem opt_out_keywords configuradas — "
              f"a parte 2 não valida nada. Configure antes.")
        return 1

    await limpar()
    try:
        await test_efeito(canal.id)
    finally:
        await limpar()

    print("\n" + "=" * 60)
    if _falhas:
        print(f"❌ {len(_falhas)} falha(s) de {_ok + len(_falhas)}:")
        for f in _falhas:
            print(f"  - {f}")
        return 1
    print(f"✅ {_ok}/{_ok} checagens passaram.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
