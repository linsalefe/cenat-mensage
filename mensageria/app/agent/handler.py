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

from sqlalchemy import select, update

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models import AgentFollowup, AgentSession, AgentTurnLog, Channel, Contact, Message
from app.agent import audio as audio_mod
from app.agent.phone import allowlist_variants, in_allowlist, mask, parse_allowlist
from app.agent.profiles import (
    PERFIL_ATENDIMENTO,
    PERFIL_VENDAS,
    PERFIS,
    channel_profile,
)

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


# --------------------------------------------------------------------------- #
# Registro anti-eco: o que a IA acabou de mandar, para o webhook do Evolution
# não confundir o eco da própria mensagem com um humano assumindo a conversa.
#
# Por que texto e não só o wa_message_id: existe uma CORRIDA real. O
# `_send` persiste a mensagem com `flush`, mas o commit só acontece no fim de
# `_process`; o Evolution, porém, pode entregar o webhook do `fromMe` antes
# disso. O webhook roda em outra sessão de banco e não vê a linha não-commitada
# — então o `wa_message_id` ainda não existe para ele. Sem este registro
# acontecem duas coisas, as duas ruins: a IA é lida como humano e se auto-pausa,
# e o INSERT do webhook viola a UNIQUE de `wa_message_id` quando o commit
# chega, derrubando o lote inteiro de mensagens daquele webhook.
#
# Em `--workers 1` o processo é único, então um dict em memória basta.
# --------------------------------------------------------------------------- #
ECO_TTL = 120.0
_eco_ia: dict[tuple[str, str], float] = {}


def _norm_eco(texto: str) -> str:
    """strip + colapsa espaços. O Evolution pode devolver o texto com quebra de
    linha normalizada diferente do que mandamos."""
    return " ".join((texto or "").split())


def _eco_gc(agora: float) -> None:
    for k in [k for k, exp in _eco_ia.items() if exp <= agora]:
        _eco_ia.pop(k, None)


def registrar_eco_ia(wa_id: str, texto: str) -> None:
    """Chamado ANTES do envio: a partir daqui, um `fromMe` com este texto é
    nosso, não de um humano."""
    agora = time.monotonic()
    _eco_gc(agora)
    _eco_ia[(wa_id or "", _norm_eco(texto))] = agora + ECO_TTL


def eh_eco_da_ia(wa_id: str, texto: str) -> bool:
    """O `fromMe` que chegou é eco de uma mensagem nossa?

    NÃO consome o registro: o Evolution entrega MESSAGES_UPSERT e pode reentregar
    o mesmo evento. Se o primeiro match apagasse a entrada, a reentrega seria
    lida como humano e pausaria a IA sem ninguém ter digitado nada. Quem limpa é
    o TTL.
    """
    agora = time.monotonic()
    _eco_gc(agora)
    return _eco_ia.get((wa_id or "", _norm_eco(texto)), 0.0) > agora


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


def _norm_opt_out(texto: str) -> str:
    """Minúscula, sem acento e sem pontuação de borda — 'SAIR.' vira 'sair'."""
    import unicodedata
    s = unicodedata.normalize("NFKD", texto or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.strip().strip(".,;:!?¡¿\"'()[]{}").strip().lower()


def eh_opt_out(texto: str, keywords: list | None) -> bool:
    """A mensagem é um pedido de descadastro?

    Exige que a mensagem INTEIRA seja a palavra-chave. É deliberadamente mais
    estrito que o chatbot (`app/chatbot/engine.py`), que aceita a palavra solta
    em qualquer lugar do texto: ali "vou sair de casa mais tarde" descadastraria
    a pessoa. Aqui não.

    O template `retomada_conversa` instrui "responda SAIR", então a resposta
    esperada é a palavra sozinha — que é exatamente o que isto casa. Pedido em
    frase ("quero parar de receber") NÃO casa aqui de propósito: cai no fluxo
    normal, e o agente tem `handoff_to_human` para o que for ambíguo. Errar para
    o lado de descadastrar quem não pediu também é um erro.
    """
    if not texto or not keywords:
        return False
    alvo = _norm_opt_out(texto)
    if not alvo:
        return False
    return any(_norm_opt_out(k) == alvo for k in keywords if isinstance(k, str))


async def _registrar_opt_out(channel: Channel, contact: Contact, db) -> None:
    """Marca o descadastro e cancela o que estava agendado.

    Sem isto o `retomada_conversa` prometia "responda SAIR" e nada acontecia: o
    tratamento de opt_out_keywords vive no motor do CHATBOT, que só roda com
    `operation_mode='chatbot'` — e o canal do agente está em 'ai'. A pessoa
    respondia SAIR, seguia recebendo, e só saía quando a própria Meta devolvia
    131050. Ou seja: depois do estrago, e pagando por cada mensagem até lá.
    """
    contact.opted_out = True
    contact.opted_out_at = datetime.now(SP_TZ)   # coluna é timestamptz → AWARE
    contact.ai_active = False
    canceladas = await db.execute(
        update(AgentFollowup)
        .where(AgentFollowup.contact_wa_id == contact.wa_id,
               AgentFollowup.status == "pending")
        .values(status="cancelled")
    )
    # Fecha a sessão DO CANAL onde o "SAIR" chegou. A sessão de outro canal (a
    # mesma pessoa pode ter conversa aberta com vendas e com atendimento) fica
    # aberta, mas inerte: `opted_out=True` e `ai_active=False` são do contato, e
    # `agent_should_handle` barra os dois canais. Cancelar o agendado continua
    # global, porque opt-out é global.
    sess = (await db.execute(
        select(AgentSession).where(
            AgentSession.contact_wa_id == contact.wa_id,
            AgentSession.channel_id == channel.id,
        ).order_by(AgentSession.id.desc())
    )).scalars().first()
    if sess and sess.status in ("active", "waiting"):
        sess.status = "closed"
    print(f"🤖🚪 opt-out {mask(contact.wa_id)}: descadastrado, "
          f"{canceladas.rowcount or 0} follow-up(s) cancelado(s)", flush=True)


AUDIO_NAO_ENTENDIDO = "[a pessoa enviou um áudio que não foi possível transcrever]"


async def _display(m: Message, transcrever_audio: bool = False) -> str:
    """Texto da mensagem como o modelo vai ver.

    Mídia vira um marcador — exceto áudio quando `transcrever_audio`, aí vira a
    transcrição. A transcrição é gravada em `m.transcript` e sobe junto do commit
    do turno, então o mesmo voice note nunca é transcrito (nem cobrado) duas
    vezes.
    """
    c = m.content or ""
    if not c.startswith("local:"):
        return c

    if transcrever_audio and audio_mod.eh_audio(c):
        if m.transcript:
            return m.transcript
        texto = await audio_mod.transcrever(c)
        if texto:
            m.transcript = texto
            return texto
        # Falhou: o marcador é explícito para o modelo pedir por escrito
        # (regra 7 do prompt do atendimento). Ficar mudo seria pior.
        return AUDIO_NAO_ENTENDIDO

    return "[a pessoa enviou um arquivo de mídia]"


def _allowlist_crua(profile: str) -> str:
    """Cada perfil tem a SUA allowlist de sandbox, e só a sua.

    Misturar as duas seria o pior dos mundos: ligar o sandbox do atendimento
    para testar a Nat colocaria o agente de vendas do canal 6 — que atende
    cliente real há meses — em sandbox, calando-o para todo mundo fora da lista.
    """
    if profile == PERFIL_ATENDIMENTO:
        return settings.AGENT_ATENDIMENTO_TEST_WA_ALLOWLIST
    return settings.AGENT_TEST_WA_ALLOWLIST


def sandbox_entries(profile: str = PERFIL_VENDAS) -> list[str]:
    """Allowlist de sandbox do perfil, lida do settings a cada chamada (permite
    mudar o .env + restart sem tocar em código)."""
    return parse_allowlist(_allowlist_crua(profile))


def sandbox_active(profile: str = PERFIL_VENDAS) -> bool:
    return bool(sandbox_entries(profile))


def sandbox_allows(wa_id: str, profile: str = PERFIL_VENDAS) -> bool:
    """True se o contato pode ser atendido considerando o modo sandbox do perfil.

    Allowlist vazia = produção, libera todo mundo. Allowlist preenchida = só os
    números dela. É a checagem que permite ligar `agent_enabled` no canal REAL
    sem nenhum cliente ver o agente.
    """
    entries = sandbox_entries(profile)
    if not entries:
        return True
    return in_allowlist(wa_id, allowlist_variants(entries))


def canal_bate_com_perfil(channel: Channel, profile: str) -> bool:
    """Trava DUPLA de canal: o perfil tem que casar com o provider e, no
    atendimento, com o id exato configurado.

    É o que garante o critério 1: nenhum outro canal Evolution responde como a
    Nat, **mesmo com `agent_enabled=true`**. Sem a trava de id bastaria alguém
    ligar o agent_enabled do canal 9 ("comunicados", que só faz disparo) para a
    Nat começar a responder numa base de 4.4 mil contatos que nunca falaram com
    a gente.

    Perfil desconhecido devolve False — fail-closed. Um typo em
    `agent_profile` cala o agente naquele canal em vez de rodar o perfil errado.
    """
    if profile == PERFIL_VENDAS:
        # É o que já acontece hoje: o único canal de vendas é o 6, official.
        if channel.provider != "official":
            print(f"🤖⛔ canal {channel.id} é perfil 'vendas' mas provider "
                  f"'{channel.provider}' (esperado 'official') — não atendo", flush=True)
            return False
        return True

    if profile == PERFIL_ATENDIMENTO:
        alvo = settings.AGENT_ATENDIMENTO_CHANNEL_ID
        if alvo is None:
            print(f"🤖⛔ canal {channel.id} é perfil 'atendimento' mas "
                  f"AGENT_ATENDIMENTO_CHANNEL_ID não está configurado — Nat desligada",
                  flush=True)
            return False
        if channel.provider != "evolution" or channel.id != alvo:
            print(f"🤖⛔ canal {channel.id} (provider '{channel.provider}') não é o "
                  f"canal do atendimento ({alvo}) — não atendo", flush=True)
            return False
        return True

    print(f"🤖⛔ canal {channel.id} com agent_profile desconhecido "
          f"{profile!r} — não atendo", flush=True)
    return False


def agent_should_handle(channel: Channel, contact: Contact) -> bool:
    """Gatilho de segurança §0.2 — TODAS as condições. agent_enabled default
    False garante que nenhum canal responde sem ativação explícita.

    O modo sandbox entra AQUI, e só aqui, para valer no fluxo inteiro: quem não
    está na allowlist tem comportamento idêntico a agente desligado — sem
    resposta, sem sessão criada e sem log de turno (esta função roda antes de
    tudo isso em `_process`). O mesmo vale para a trava de canal por perfil.
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
    profile = channel_profile(channel)
    if not canal_bate_com_perfil(channel, profile):
        return False
    if not sandbox_allows(contact.wa_id, profile):
        print(f"🧪 sandbox[{profile}]: ignorando {mask(contact.wa_id)} "
              f"(fora da allowlist)", flush=True)
        return False
    return True


async def handle_inbound(channel_id: int, wa_id: str, wa_message_id: str, text: str) -> None:
    """Debounce: coalesce rajadas de mensagens. Só o último inbound processa."""
    now = time.monotonic()
    _last_seen[wa_id] = now
    _gc(now)
    _seq[wa_id] += 1
    mine = _seq[wa_id]

    # OPT-OUT vem ANTES do debounce: quem pede para sair não espera 8 segundos,
    # e o pedido não pode ser engolido por uma mensagem posterior da rajada.
    try:
        if await _checar_opt_out(channel_id, wa_id, text):
            _seq[wa_id] += 1   # aborta qualquer turno em voo deste contato
            return
    except Exception as e:
        # Falhar aqui não pode calar o agente — mas registra, porque opt-out
        # silenciosamente não aplicado é problema de conformidade.
        print(f"🤖❌ falha ao checar opt-out ({wa_id}): {e!r}", flush=True)

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
            await _log_erro(wa_id, e, channel_id)


async def _checar_opt_out(channel_id: int, wa_id: str, text: str) -> bool:
    """True se a mensagem era um descadastro (e já foi tratada).

    Confirma para a pessoa: ela acabou de escrever, então estamos DENTRO da
    janela de 24h e o texto livre não custa template. Ficar mudo depois de
    "SAIR" deixa a dúvida de se funcionou — e a dúvida gera outro "SAIR".
    """
    async with AsyncSessionLocal() as db:
        channel = await db.get(Channel, channel_id)
        if not eh_opt_out(text, getattr(channel, "opt_out_keywords", None)):
            return False
        contact = (await db.execute(
            select(Contact).where(Contact.wa_id == wa_id)
        )).scalar_one_or_none()
        if contact is None:
            return False
        ja_estava = bool(contact.opted_out)
        if not ja_estava:
            await _registrar_opt_out(channel, contact, db)
        await db.commit()
        if not ja_estava:
            try:
                await _send(db, channel, wa_id,
                            "Pronto, você não vai mais receber mensagens nossas por aqui. "
                            "Se mudar de ideia, é só escrever de novo. 💙")
                await db.commit()
            except Exception as e:
                print(f"🤖❌ opt-out registrado mas confirmação não saiu ({wa_id}): {e!r}",
                      flush=True)
        return True


async def _log_erro(wa_id: str, exc: Exception, channel_id: int | None = None) -> None:
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
            q = select(AgentSession.id).where(AgentSession.contact_wa_id == wa_id)
            if channel_id is not None:
                # Mesmo motivo do filtro em `_process`: pendurar o erro do turno
                # do atendimento na sessão de vendas (ou o contrário) deixa o log
                # apontando para a conversa errada.
                q = q.where(AgentSession.channel_id == channel_id)
            sres = await db.execute(q.order_by(AgentSession.id.desc()))
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
        #
        # Filtrada por CANAL: a mesma pessoa pode falar com vendas (canal 6) e
        # com o atendimento (canal da Nat). Sem o filtro, o segundo canal
        # herdaria o histórico do primeiro — a Nat responderia com o contexto de
        # venda de congresso, e o watermark de um canal faria o outro achar que
        # já respondeu (resposta engolida ou duplicada).
        sres = await db.execute(
            select(AgentSession)
            .where(
                AgentSession.contact_wa_id == wa_id,
                AgentSession.channel_id == channel_id,
            )
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
                Message.channel_id == channel_id,
                Message.direction == "inbound",
                Message.timestamp > watermark,
            )
            .order_by(Message.timestamp.asc())
        )
        inbound = list(mres.scalars().all())
        if not inbound:
            return  # nada novo — evita resposta duplicada em retry do webhook

        # Transcrição de voice note só no ATENDIMENTO: é lá que o áudio é comum,
        # e manter o canal 6 de vendas ignorando mídia preserva o comportamento
        # que já está em produção desde julho.
        perfil = channel_profile(channel)
        transcrever = bool(
            perfil == PERFIL_ATENDIMENTO and settings.AGENT_AUDIO_TRANSCRIBE
        )
        partes = [await _display(m, transcrever) for m in inbound]
        user_text = "\n".join(partes).strip()
        session.last_inbound_at = _sp_naive(max(m.timestamp for m in inbound))
        if not user_text:
            await db.commit()
            return

        out = await run_turn(db, session, contact, user_text, profile=perfil)
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
    # ANTES do envio, não depois: o webhook do Evolution pode chegar enquanto o
    # `await send_text` ainda está em voo.
    registrar_eco_ia(wa_id, reply)
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
