#!/usr/bin/env python3
"""Regressão: DOIS turnos seguidos na mesma sessão persistida.

Este é o cenário que quebrou em produção no primeiro teste real do agente e que
NENHUM eval pegava. O motivo da cegueira é estrutural: `eval_agent.py` chama
`run_turn` direto, e o watermark não mora no `run_turn` — mora no `_process`,
entre a leitura de `AgentSession.last_inbound_at` e o filtro sobre
`Message.timestamp`. Um teste que nunca passa pelo `_process` nunca vê o bug.

O defeito: `last_inbound_at` era `timestamptz` e `messages.timestamp` é naive
UTC-3. O 1º turno funcionava (sessão nova → `last_inbound_at IS NULL` → fallback
naive); do 2º em diante o watermark voltava AWARE do banco e o asyncpg estourava
`DataError: can't subtract offset-naive and offset-aware datetimes`, abortando o
turno antes de qualquer chamada. Sintoma: o agente responde a primeira mensagem
e emudece para sempre. Corrigido pela migração d4a1e7b3c920.

Sem pytest (mesma convenção do test_sandbox.py: o venv de produção não tem).

TOCA O BANCO — de propósito, porque o bug era de tipo de coluna e só aparece
num round-trip real pelo Postgres. `_process` dá commit, então rollback não
serve: o teste limpa as próprias linhas num `finally`. Usa um wa_id dedicado
(`test:dois-turnos`) que não colide com contato real.

NÃO chama OpenAI e NÃO envia WhatsApp: `run_turn` e `_send` são substituídos.

Uso:
    .venv/bin/python tests/agent/test_dois_turnos.py
Exit 0 = tudo passou.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from sqlalchemy import delete, select  # noqa: E402

from app.agent import handler as H  # noqa: E402
from app.agent import loop as L  # noqa: E402
from app.database import AsyncSessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    AgentSession, AgentTurnLog, Channel, Contact, Message,
)

SP_TZ = dt.timezone(dt.timedelta(hours=-3))
WA = "test:dois-turnos"

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


def now_sp() -> dt.datetime:
    return dt.datetime.now(SP_TZ).replace(tzinfo=None)


# --------------------------------------------------------------------------- #
# Dublês: o objeto do teste é o watermark, não a IA nem a Meta.
# --------------------------------------------------------------------------- #
_enviadas: list[str] = []


async def fake_run_turn(db, session, contact, user_text: str) -> dict:
    """Reproduz só os efeitos de `run_turn` que importam para o watermark."""
    session.history = list(session.history or []) + [
        {"role": "user", "content": user_text},
        {"role": "assistant", "content": f"eco: {user_text}"},
    ]
    session.turns_count = (session.turns_count or 0) + 1
    # naive, igual ao loop.py real depois da migração d4a1e7b3c920
    session.last_outbound_at = now_sp()
    return {"reply": f"eco: {user_text}", "product_slug": None}


async def fake_send(db, channel, wa_id: str, reply: str) -> None:
    _enviadas.append(reply)


async def limpar() -> None:
    """Remove tudo que o teste criou. Roda antes e depois (idempotente)."""
    async with AsyncSessionLocal() as db:
        ids = (await db.execute(
            select(AgentSession.id).where(AgentSession.contact_wa_id == WA)
        )).scalars().all()
        if ids:
            await db.execute(delete(AgentTurnLog).where(AgentTurnLog.session_id.in_(ids)))
        await db.execute(delete(AgentSession).where(AgentSession.contact_wa_id == WA))
        await db.execute(delete(Message).where(Message.contact_wa_id == WA))
        await db.execute(delete(Contact).where(Contact.wa_id == WA))
        await db.commit()


async def semear_inbound(canal_id: int | None, texto: str, quando: dt.datetime) -> None:
    async with AsyncSessionLocal() as db:
        db.add(Message(
            wa_message_id=f"test:dois-turnos:{quando.isoformat()}",
            contact_wa_id=WA, channel_id=canal_id, direction="inbound",
            message_type="text", content=texto, timestamp=quando,
            status="received", sent_by_ai=False,
        ))
        await db.commit()


async def processar(canal_id: int, rotulo: str) -> None:
    """Chama `_process` transformando exceção em falha legível.

    `_process` propaga (quem engole é o `handle_inbound`). Sem este wrapper, uma
    regressão do watermark devolve uma parede de traceback do asyncpg em vez de
    dizer qual checagem quebrou — e foi justamente a dificuldade de ler o sintoma
    que fez esse bug parecer "o agente ficou quieto".
    """
    try:
        await H._process(canal_id, WA)
    except Exception as e:
        check(False, f"{rotulo} estourou: {type(e).__name__}: {str(e)[:120]}")


async def ler_sessao() -> AgentSession | None:
    """Lê a sessão numa conexão NOVA — é o round-trip pelo Postgres que importa."""
    async with AsyncSessionLocal() as db:
        return (await db.execute(
            select(AgentSession).where(AgentSession.contact_wa_id == WA)
            .order_by(AgentSession.id.desc())
        )).scalars().first()


# --------------------------------------------------------------------------- #
async def test_dois_turnos(canal_id: int) -> None:
    print("\n[1] dois turnos seguidos na mesma sessão (o cenário que quebrou)")

    # Dentro da janela do fallback de sessão nova (`_now() - 2min`): mais velho
    # que isso e o 1º turno nem enxerga o inbound.
    t1 = now_sp() - dt.timedelta(seconds=60)
    await semear_inbound(canal_id, "Oi, quero saber do congresso", t1)
    await processar(canal_id, "1º turno")

    s1 = await ler_sessao()
    check(s1 is not None, "1º turno criou a sessão")
    check(len(_enviadas) == 1, f"1º turno respondeu (respostas={len(_enviadas)})")
    check(s1 is not None and s1.turns_count == 1, "turns_count = 1 após o 1º turno")
    check(s1 is not None and s1.last_inbound_at == t1,
          f"watermark = timestamp do 1º inbound ({s1.last_inbound_at if s1 else '?'})")

    # ── o passo que estourava ────────────────────────────────────────────────
    t2 = now_sp() - dt.timedelta(seconds=20)
    await semear_inbound(canal_id, "Me manda por favor", t2)
    await processar(canal_id, "2º turno")

    s2 = await ler_sessao()
    check(len(_enviadas) == 2,
          f"2º turno TAMBÉM respondeu (respostas={len(_enviadas)}) ← a regressão")
    check(s2 is not None and s2.turns_count == 2, "turns_count = 2 após o 2º turno")
    check(s2 is not None and s2.last_inbound_at == t2, "watermark avançou para o 2º inbound")
    check(_enviadas[-1] == "eco: Me manda por favor",
          "o 2º turno processou o texto NOVO, não o antigo")

    # Nenhum turno de erro gravado pelo _log_erro.
    async with AsyncSessionLocal() as db:
        erros = (await db.execute(
            select(AgentTurnLog).join(
                AgentSession, AgentSession.id == AgentTurnLog.session_id
            ).where(AgentSession.contact_wa_id == WA)
        )).scalars().all()
    check(all((t.guardrail or {}).get("error") is None for t in erros),
          "nenhum AgentTurnLog de erro foi gravado")


async def test_tipo_naive() -> None:
    print("\n[2] tipo que volta do banco")
    s = await ler_sessao()
    check(s is not None and s.last_inbound_at is not None
          and s.last_inbound_at.tzinfo is None,
          "last_inbound_at volta do Postgres NAIVE (a coluna não é mais timestamptz)")
    check(s is not None and s.last_outbound_at is not None
          and s.last_outbound_at.tzinfo is None,
          "last_outbound_at volta do Postgres NAIVE")


async def test_watermark_aware_nao_derruba(canal_id: int) -> None:
    """Defesa: mesmo que um AWARE apareça, o turno não pode morrer.

    Simula o estado antigo (coluna timestamptz) injetando um aware no objeto
    antes do `_process`. Sem `_sp_naive` isto estoura exatamente como estourava
    em produção.
    """
    print("\n[3] watermark AWARE não derruba o turno (normalização defensiva)")

    s = await ler_sessao()
    assert s is not None
    aware = s.last_inbound_at.replace(tzinfo=SP_TZ)
    check(H._sp_naive(aware) == s.last_inbound_at,
          "_sp_naive(aware) devolve o mesmo instante em naive SP")
    check(H._sp_naive(None) is None, "_sp_naive(None) = None")
    check(H._sp_naive(s.last_inbound_at) is s.last_inbound_at,
          "_sp_naive(naive) devolve o próprio objeto, sem conversão")

    # aware vindo de outro fuso deve cair na hora de parede de SP
    utc = dt.datetime(2026, 7, 30, 17, 28, 20, tzinfo=dt.timezone.utc)
    check(H._sp_naive(utc) == dt.datetime(2026, 7, 30, 14, 28, 20),
          "_sp_naive(17:28:20 UTC) = 14:28:20 naive (o caso real da sessão 191)")

    antes = len(_enviadas)
    t3 = now_sp()
    await semear_inbound(canal_id, "terceira mensagem", t3)  # noqa: F841 (t3 usado acima)
    async with AsyncSessionLocal() as db:
        sess = (await db.execute(
            select(AgentSession).where(AgentSession.contact_wa_id == WA)
        )).scalars().first()
        sess.last_inbound_at = None   # força o fallback e depois reescreve aware
        await db.commit()
    await processar(canal_id, "turno pós-aware")
    check(len(_enviadas) == antes + 1, "turno seguinte respondeu normalmente")


# --------------------------------------------------------------------------- #
async def main() -> int:
    # Dublês: nada de OpenAI, nada de WhatsApp, e o gating não é o objeto aqui
    # (quem cobre gating/sandbox é o test_sandbox.py).
    L.run_turn = fake_run_turn
    H._send = fake_send
    H.agent_should_handle = lambda channel, contact: True

    async with AsyncSessionLocal() as db:
        canal_id = (await db.execute(select(Channel.id).order_by(Channel.id))).scalars().first()
    if canal_id is None:
        print("❌ nenhum canal no banco — o teste precisa de um Channel para o _process.")
        return 1

    await limpar()
    try:
        async with AsyncSessionLocal() as db:
            db.add(Contact(
                wa_id=WA, name="Teste dois turnos", channel_id=canal_id,
                ai_active=True, is_group=False, opted_out=False,
                ai_memory={}, lead_status="novo",
            ))
            await db.commit()

        await test_dois_turnos(canal_id)
        await test_tipo_naive()
        await test_watermark_aware_nao_derruba(canal_id)
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
