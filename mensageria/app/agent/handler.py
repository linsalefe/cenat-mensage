"""Entrada do agente a partir do webhook. Debounce por contato, gating de
segurança de 5 condições, idempotência por watermark e envio da resposta.

Roda como background task (asyncio.create_task) disparada pelo webhook Meta —
NUNCA bloqueia o webhook. Em --workers 1, debounce/lock em memória bastam."""
from __future__ import annotations

import asyncio
import time
import traceback
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models import AgentSession, AgentTurnLog, Channel, Contact, Message
from app.agent.phone import allowlist_variants, in_allowlist, mask, parse_allowlist

settings = get_settings()
SP_TZ = timezone(timedelta(hours=-3))

_seq: dict[str, int] = defaultdict(int)
_locks: dict[str, asyncio.Lock] = {}
_last_seen: dict[str, float] = {}   # wa_id -> time.monotonic() do último inbound

# GC do estado em memória: sem isto, _seq/_locks crescem para sempre (uma entrada
# por wa_id que já falou com o agente) e nunca são liberados enquanto o processo
# viver. Como só há 1 worker uvicorn, esse estado é do processo inteiro.
_GC_INTERVAL = 600.0   # varre no máximo a cada 10 min
_GC_IDLE_TTL = 3600.0  # descarta wa_id parado há mais de 1h
_last_gc: float = 0.0


def _lock(wa_id: str) -> asyncio.Lock:
    lk = _locks.get(wa_id)
    if lk is None:
        lk = _locks[wa_id] = asyncio.Lock()
    return lk


def _gc(now: float) -> None:
    """Remove o estado de contatos inativos. Chamado no caminho do inbound (não
    precisa de task própria). Nunca mexe em wa_id com lock tomado (turno em voo);
    o TTL de 1h é ordens de grandeza maior que o debounce de 8s, então não existe
    task de debounce dormindo sobre uma entrada elegível."""
    global _last_gc
    if now - _last_gc < _GC_INTERVAL:
        return
    _last_gc = now
    stale = [w for w, ts in _last_seen.items() if now - ts > _GC_IDLE_TTL]
    removed = 0
    for w in stale:
        lk = _locks.get(w)
        if lk is not None and lk.locked():
            continue  # turno em andamento — deixa para a próxima varredura
        _last_seen.pop(w, None)
        _seq.pop(w, None)
        _locks.pop(w, None)
        removed += 1
    if removed:
        print(f"🤖🧹 GC: {removed} contatos inativos liberados "
              f"({len(_last_seen)} ativos)", flush=True)


def _now() -> datetime:
    return datetime.now(SP_TZ).replace(tzinfo=None)


def _sp_naive(dt: datetime | None) -> datetime | None:
    """Normaliza para naive na hora de parede de São Paulo.

    A convenção do projeto é datetime naive em UTC-3 — é o que
    `messages.timestamp` guarda. Se um valor AWARE chegar aqui (coluna que
    voltou a ser timestamptz, valor vindo de outra camada), converter é sempre
    melhor do que deixar passar: um aware usado para filtrar coluna naive não
    dá resultado errado, ele **derruba o turno inteiro** no encoder do asyncpg
    (`can't subtract offset-naive and offset-aware datetimes`). Foi exatamente
    o bug corrigido pela migração d4a1e7b3c920, e o sintoma era o agente
    responder à primeira mensagem e emudecer para sempre.
    """
    if dt is None or dt.tzinfo is None:
        return dt
    return dt.astimezone(SP_TZ).replace(tzinfo=None)


def _display(m: Message) -> str:
    c = m.content or ""
    if c.startswith("local:"):
        return "[a pessoa enviou um arquivo de mídia]"
    return c


def sandbox_entries() -> list[str]:
    """Allowlist de sandbox, lida do settings a cada chamada (permite mudar o
    .env + restart sem tocar em código)."""
    return parse_allowlist(settings.AGENT_TEST_WA_ALLOWLIST)


def sandbox_active() -> bool:
    return bool(sandbox_entries())


def sandbox_allows(wa_id: str) -> bool:
    """True se o contato pode ser atendido considerando o modo sandbox.

    Allowlist vazia = produção, libera todo mundo. Allowlist preenchida = só os
    números dela. É a checagem que permite ligar `agent_enabled` no canal REAL
    sem nenhum cliente ver o agente.
    """
    entries = sandbox_entries()
    if not entries:
        return True
    return in_allowlist(wa_id, allowlist_variants(entries))


def agent_should_handle(channel: Channel, contact: Contact) -> bool:
    """Gatilho de segurança §0.2 — TODAS as condições. agent_enabled default
    False garante que nenhum canal responde sem ativação explícita.

    O modo sandbox entra AQUI, e só aqui, para valer no fluxo inteiro: quem não
    está na allowlist tem comportamento idêntico a agente desligado — sem
    resposta, sem sessão criada e sem log de turno (esta função roda antes de
    tudo isso em `_process`).
    """
    base = bool(
        channel
        and channel.agent_enabled
        and channel.operation_mode == "ai"
        and contact
        and contact.ai_active
        and not contact.opted_out
        and not contact.is_group
    )
    if not base:
        return False
    if not sandbox_allows(contact.wa_id):
        print(f"🧪 sandbox: ignorando {mask(contact.wa_id)} (fora da allowlist)", flush=True)
        return False
    return True


async def handle_inbound(channel_id: int, wa_id: str, wa_message_id: str, text: str) -> None:
    """Debounce: coalesce rajadas de mensagens. Só o último inbound processa."""
    now = time.monotonic()
    _last_seen[wa_id] = now
    _gc(now)
    _seq[wa_id] += 1
    mine = _seq[wa_id]
    try:
        await asyncio.sleep(settings.AGENT_DEBOUNCE_SECONDS)
    except asyncio.CancelledError:
        return
    if _seq.get(wa_id) != mine:
        return  # chegou mensagem mais nova; a task dela cuida do lote
    async with _lock(wa_id):
        try:
            await _process(channel_id, wa_id)
        except Exception as e:  # background task: nunca propaga
            # Traceback completo: só o repr da exceção não diz em QUE linha o
            # turno morreu, e foi isso que fez o bug do watermark parecer
            # "o agente ficou quieto" em vez de "o agente quebrou".
            print(f"🤖❌ agent handle_inbound erro ({wa_id}): {e!r}\n"
                  f"{traceback.format_exc()}", flush=True)
            await _log_erro(wa_id, e)


async def _log_erro(wa_id: str, exc: Exception) -> None:
    """Grava um AgentTurnLog de falha para o turno que morreu.

    Sem isto, um turno que estoura não deixa NENHUMA linha em agent_turn_logs, e
    silêncio do agente fica indistinguível de falha do agente — quem olha o
    painel vê a conversa parada e não tem como saber se a IA decidiu não
    responder ou se explodiu.

    Usa conexão própria de propósito: a sessão do turno que falhou já está em
    estado inconsistente (o `async with` de `_process` fez rollback). E nunca
    propaga: falhar ao registrar a falha não pode derrubar o webhook.
    """
    try:
        async with AsyncSessionLocal() as db:
            sres = await db.execute(
                select(AgentSession.id)
                .where(AgentSession.contact_wa_id == wa_id)
                .order_by(AgentSession.id.desc())
            )
            db.add(AgentTurnLog(
                session_id=sres.scalars().first(),  # None se nem sessão houver
                direction="inbound",
                content=None,
                guardrail={
                    "error": f"{type(exc).__name__}: {exc}"[:2000],
                    "traceback": traceback.format_exc()[-4000:],
                },
            ))
            await db.commit()
    except Exception as e2:
        print(f"🤖❌ falha ao registrar o erro do turno ({wa_id}): {e2!r}", flush=True)


async def _process(channel_id: int, wa_id: str) -> None:
    from app.agent.loop import run_turn

    async with AsyncSessionLocal() as db:
        channel = await db.get(Channel, channel_id)
        cres = await db.execute(select(Contact).where(Contact.wa_id == wa_id))
        contact = cres.scalar_one_or_none()
        if not agent_should_handle(channel, contact):
            return

        # sessão: reusa ativa/waiting; respeita handoff; recria se fechada/convertida
        sres = await db.execute(
            select(AgentSession)
            .where(AgentSession.contact_wa_id == wa_id)
            .order_by(AgentSession.id.desc())
        )
        session = sres.scalars().first()
        if session and session.status == "handed_off":
            return  # humano assumiu — agente fica em silêncio
        if session is None or session.status in ("converted", "closed"):
            session = AgentSession(contact_wa_id=wa_id, channel_id=channel_id, status="active")
            db.add(session)
            await db.flush()

        # lote: inbound novos desde o watermark (idempotência)
        # _sp_naive: o watermark filtra `Message.timestamp`, coluna NAIVE. Um
        # aware aqui estoura o encoder do asyncpg e mata o turno (ver docstring).
        watermark = _sp_naive(session.last_inbound_at) or (_now() - timedelta(minutes=2))
        mres = await db.execute(
            select(Message)
            .where(
                Message.contact_wa_id == wa_id,
                Message.direction == "inbound",
                Message.timestamp > watermark,
            )
            .order_by(Message.timestamp.asc())
        )
        inbound = list(mres.scalars().all())
        if not inbound:
            return  # nada novo — evita resposta duplicada em retry do webhook
        user_text = "\n".join(_display(m) for m in inbound).strip()
        session.last_inbound_at = _sp_naive(max(m.timestamp for m in inbound))
        if not user_text:
            await db.commit()
            return

        out = await run_turn(db, session, contact, user_text)
        reply = out["reply"]

        await _send(db, channel, wa_id, reply)
        await db.commit()
        print(f"🤖 [{channel.name}] {wa_id}: {reply[:80]}", flush=True)


async def _send(db, channel: Channel, wa_id: str, reply: str) -> None:
    from app.messaging.persistence import persist_outbound_message
    from app.messaging.provider import get_provider

    if channel.provider == "official" and (not channel.phone_number_id or not channel.whatsapp_token):
        print(f"🤖⚠️ canal {channel.id} sem phone_number_id/token — resposta não enviada", flush=True)
        await persist_outbound_message(
            db=db, channel=channel, to=wa_id, message_type="text",
            content=reply, status="failed", sent_by_ai=True,
        )
        return
    provider = get_provider(channel)
    try:
        result = await provider.send_text(channel, wa_id, reply)
        await persist_outbound_message(
            db=db, channel=channel, to=wa_id, message_type="text",
            content=reply, send_result=result, sent_by_ai=True,
        )
    except Exception as e:
        print(f"🤖❌ falha ao enviar ({wa_id}): {e!r}", flush=True)
        await persist_outbound_message(
            db=db, channel=channel, to=wa_id, message_type="text",
            content=reply, status="failed", sent_by_ai=True,
        )
