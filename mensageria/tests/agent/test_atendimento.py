#!/usr/bin/env python3
"""Testes do perfil ATENDIMENTO do agente (a "Nat") no canal Evolution.

Sem pytest, mesma convenção do `test_sandbox.py` e do `test_dois_turnos.py`: o
venv de produção não tem pytest, e instalar dependência num servidor que atende
cliente real por causa de teste não se paga.

O que cada parte toca:
- Partes 1 a 8: só memória e disco. Nada de banco, nada de OpenAI, nada de
  WhatsApp. O gating é síncrono, a KB é arquivo e o loop roda com uma sessão de
  banco dublê e um cliente OpenAI dublê.
- Parte 9: TOCA O BANCO de propósito. O escopo por canal é um filtro de query —
  só um round-trip real pelo Postgres prova que duas sessões do mesmo contato em
  canais diferentes não se misturam. Usa o wa_id dedicado `test:atendimento`,
  que não colide com contato real, e limpa as próprias linhas num `finally`.

Uso:
    .venv/bin/python tests/agent/test_atendimento.py
Exit 0 = tudo passou.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import inspect
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from sqlalchemy import delete, select  # noqa: E402

from app.agent import handler as H  # noqa: E402
from app.agent import kb as K  # noqa: E402
from app.agent import loop as L  # noqa: E402
from app.agent.profiles import (  # noqa: E402
    PERFIL_ATENDIMENTO, PERFIL_VENDAS, channel_profile,
)
from app.agent.prompt_atendimento import build_atendimento_prompt  # noqa: E402
from app.database import AsyncSessionLocal  # noqa: E402
from app.evolution.routes import _resolver_telefone  # noqa: E402
from app.models import (  # noqa: E402
    AgentSession, AgentTurnLog, Channel, Contact, Message,
)

SP_TZ = dt.timezone(dt.timedelta(hours=-3))
WA = "test:atendimento"

# Canal do atendimento usado nas checagens de gating em memória. Número
# arbitrário: o que importa é que `AGENT_ATENDIMENTO_CHANNEL_ID` aponte para ele.
CANAL_NAT = 12

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


def now_sp() -> dt.datetime:
    return dt.datetime.now(SP_TZ).replace(tzinfo=None)


# --------------------------------------------------------------------------- #
# fixtures e helpers
# --------------------------------------------------------------------------- #
def _canal_vendas(**kw) -> Channel:
    """O canal 6 real: Meta oficial, perfil vendas (default da coluna)."""
    base = dict(id=6, name="Cenat - disparos", provider="official",
                operation_mode="ai", agent_enabled=True)
    base.update(kw)
    return Channel(**base)


def _canal_nat(**kw) -> Channel:
    base = dict(id=CANAL_NAT, name="atendimento", provider="evolution",
                operation_mode="ai", agent_enabled=True,
                agent_profile=PERFIL_ATENDIMENTO)
    base.update(kw)
    return Channel(**base)


def _contato(wa_id="5583999999999", **kw) -> Contact:
    base = dict(wa_id=wa_id, name="Teste", ai_active=True, opted_out=False,
                is_group=False, channel_id=6, ai_memory={}, lead_status="novo")
    base.update(kw)
    return Contact(**base)


class _SettingsFake:
    """Sobrescreve só as chaves dadas, delegando o resto ao settings real."""

    def __init__(self, real, **ov):
        self._real = real
        self._ov = ov

    def __getattr__(self, nome):
        if nome in self._ov:
            return self._ov[nome]
        return getattr(self._real, nome)


class settings_de:
    """Context manager: roda o bloco com settings sobrescritos no módulo dado."""

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


# --------------------------------------------------------------------------- #
# 1. gating por perfil — a trava dupla de canal
# --------------------------------------------------------------------------- #
def test_gating_perfil() -> None:
    secao("gating: trava dupla de canal (provider + id)")

    with settings_de(H, AGENT_ATENDIMENTO_CHANNEL_ID=CANAL_NAT,
                     AGENT_TEST_WA_ALLOWLIST="",
                     AGENT_ATENDIMENTO_TEST_WA_ALLOWLIST=""):
        check(H.agent_should_handle(_canal_vendas(), _contato()),
              "canal 6 (vendas/official) → True, inalterado")
        check(H.agent_should_handle(_canal_nat(), _contato()),
              "canal do atendimento (evolution + id certo) → True")

        # O critério 1 do plano: nenhum OUTRO canal Evolution responde, mesmo
        # com agent_enabled=true. O canal 9 ("comunicados") é só disparo e tem
        # 4.4 mil contatos que nunca falaram — se a Nat atendesse por ali, ela
        # responderia a base inteira.
        check(not H.agent_should_handle(
                  _canal_nat(id=9), _contato()),
              "canal 9 marcado 'atendimento' mas id≠CHANNEL_ID → False")
        check(not H.agent_should_handle(
                  Channel(id=9, name="comunicados", provider="evolution",
                          operation_mode="ai", agent_enabled=True), _contato()),
              "canal 9 com perfil default (vendas) em provider evolution → False")
        check(not H.agent_should_handle(
                  _canal_nat(provider="official"), _contato()),
              "id certo mas provider 'official' → False")
        check(not H.agent_should_handle(
                  _canal_vendas(provider="evolution"), _contato()),
              "perfil 'vendas' em provider evolution → False")

        # Fail-closed: um typo na coluna cala o canal, não roda o perfil errado.
        check(not H.agent_should_handle(
                  _canal_nat(agent_profile="atendimentoo"), _contato()),
              "agent_profile desconhecido → False (fail-closed)")
        check(not H.agent_should_handle(
                  _canal_nat(agent_profile="vendas_2"), _contato()),
              "outro agent_profile inválido → False")

        # As 5 condições originais seguem valendo nos dois perfis.
        for rotulo, canal, contato in (
            ("agent_enabled=False", _canal_nat(agent_enabled=False), _contato()),
            ("operation_mode='chatbot'", _canal_nat(operation_mode="chatbot"), _contato()),
            ("ai_active=False", _canal_nat(), _contato(ai_active=False)),
            ("opted_out=True", _canal_nat(), _contato(opted_out=True)),
            ("is_group=True", _canal_nat(), _contato(is_group=True)),
        ):
            check(not H.agent_should_handle(canal, contato),
                  f"atendimento: {rotulo} continua bloqueando")

    # Nat desligada: sem CHANNEL_ID ela não atende em lugar nenhum, e vendas
    # segue intacto.
    with settings_de(H, AGENT_ATENDIMENTO_CHANNEL_ID=None,
                     AGENT_TEST_WA_ALLOWLIST="",
                     AGENT_ATENDIMENTO_TEST_WA_ALLOWLIST=""):
        check(not H.agent_should_handle(_canal_nat(), _contato()),
              "AGENT_ATENDIMENTO_CHANNEL_ID=None → Nat não atende")
        check(H.agent_should_handle(_canal_vendas(), _contato()),
              "...e vendas continua atendendo")


def test_channel_profile() -> None:
    secao("channel_profile: default e normalização")

    check(channel_profile(Channel(id=6)) == PERFIL_VENDAS,
          "agent_profile None (objeto não persistido) → 'vendas'")
    check(channel_profile(Channel(id=6, agent_profile="")) == PERFIL_VENDAS,
          "agent_profile vazio → 'vendas'")
    check(channel_profile(Channel(id=1, agent_profile=" ATENDIMENTO ")) == PERFIL_ATENDIMENTO,
          "normaliza caixa e espaço")
    check(channel_profile(None) == PERFIL_VENDAS, "canal None → 'vendas'")


# --------------------------------------------------------------------------- #
# 2. sandbox por perfil — os dois são independentes
# --------------------------------------------------------------------------- #
def test_sandbox_por_perfil() -> None:
    secao("sandbox: allowlists independentes por perfil")

    nat, v6 = _canal_nat(), _canal_vendas()

    # Sandbox SÓ do atendimento. Vendas não pode ser afetado: o canal 6 atende
    # cliente real, e colocá-lo em sandbox por tabela o calaria para todos.
    with settings_de(H, AGENT_ATENDIMENTO_CHANNEL_ID=CANAL_NAT,
                     AGENT_TEST_WA_ALLOWLIST="",
                     AGENT_ATENDIMENTO_TEST_WA_ALLOWLIST="5583111112222"):
        check(H.sandbox_active(PERFIL_ATENDIMENTO) is True,
              "sandbox_active('atendimento') True")
        check(H.sandbox_active(PERFIL_VENDAS) is False,
              "sandbox_active('vendas') False")
        check(H.agent_should_handle(nat, _contato("5583111112222")),
              "atendimento atende quem está na allowlist dele")
        check(not H.agent_should_handle(nat, _contato("5511999998888")),
              "atendimento barra quem está fora da allowlist dele")
        check(H.agent_should_handle(v6, _contato("5511999998888")),
              "sandbox do atendimento NÃO coloca vendas em sandbox")
        check(H.sandbox_allows("5583111112222", PERFIL_ATENDIMENTO),
              "sandbox_allows com perfil atendimento")
        check(not H.sandbox_allows("5583111112222", PERFIL_VENDAS),
              "o mesmo número NÃO está liberado como vendas")

    # Sandbox SÓ de vendas. O atendimento não pode ser afetado.
    with settings_de(H, AGENT_ATENDIMENTO_CHANNEL_ID=CANAL_NAT,
                     AGENT_TEST_WA_ALLOWLIST="5511777776666",
                     AGENT_ATENDIMENTO_TEST_WA_ALLOWLIST=""):
        check(H.agent_should_handle(v6, _contato("5511777776666")),
              "vendas atende quem está na allowlist dele")
        check(not H.agent_should_handle(v6, _contato("5583111112222")),
              "vendas barra quem está fora")
        check(H.agent_should_handle(nat, _contato("5583111112222")),
              "sandbox de vendas NÃO coloca o atendimento em sandbox")

    # Compatibilidade: `workers.py` chama sem o argumento de perfil.
    with settings_de(H, AGENT_TEST_WA_ALLOWLIST="5511777776666",
                     AGENT_ATENDIMENTO_TEST_WA_ALLOWLIST="5583111112222"):
        check(H.sandbox_allows("5511777776666") is True,
              "sandbox_allows() sem perfil = vendas (assinatura antiga)")
        check(H.sandbox_allows("5583111112222") is False,
              "...e NÃO consulta a allowlist do atendimento")
        check(H.sandbox_active() is True, "sandbox_active() sem perfil = vendas")

    # Variação do 9º dígito e Instagram continuam valendo no perfil novo.
    with settings_de(H, AGENT_ATENDIMENTO_CHANNEL_ID=CANAL_NAT,
                     AGENT_ATENDIMENTO_TEST_WA_ALLOWLIST="5583999999999"):
        check(H.agent_should_handle(nat, _contato("558399999999")),
              "atendimento tolera a forma sem o 9º dígito")
        check(not H.agent_should_handle(nat, _contato("ig:17841405925471370")),
              "wa_id de Instagram nunca casa com allowlist de telefone")


# --------------------------------------------------------------------------- #
# 3. KB: carga, _legado, placeholder, recarga
# --------------------------------------------------------------------------- #
def test_kb_carga() -> None:
    secao("KB: carga da base do atendimento")

    K._cache.clear()
    kb = K.load_kb("atendimento")
    arquivos = {c.arquivo for c in kb.chunks}

    check(kb.total_chars > 0 and bool(kb.chunks), "base carregou com conteúdo")
    check(all(a.endswith(".md") for a in arquivos), "só arquivos .md")
    check("README.md" not in arquivos,
          "_legado/ NÃO é carregado (README.md ausente)")
    check(not any(a.startswith("_") for a in arquivos),
          "nenhum arquivo com nome começando em '_'")
    check("{{" not in kb.full_text, "nenhum placeholder cru no texto final")

    # A regra de ouro: preço, data e link vivem em agent_products, não na KB.
    # Se um deles vazar para cá, o agente passa a citar valor que o guardrail
    # de saída não conhece — e o guardrail barra a própria resposta.
    check("R$" not in kb.full_text, "KB não contém 'R$'")
    check("http://" not in kb.full_text and "https://" not in kb.full_text,
          "KB não contém URL")
    check("CENSUPEG" not in kb.full_text and "São Marcos" not in kb.full_text,
          "KB não cita a certificadora (pendência 1 do CLAUDE.md)")


def test_kb_placeholder_e_recarga() -> None:
    secao("KB: placeholder descartado e recarga por mtime")

    pasta = K.KB_DIR / "atendimento"
    tmp = pasta / "99_teste_tmp.md"
    try:
        K._cache.clear()
        base = K.load_kb("atendimento")

        # Recarga: editar/criar .md vale no próximo turno, sem restart.
        tmp.write_text("# Horario de atendimento\n"
                       "Atendemos de segunda a sexta, das 9h as 18h.\n",
                       encoding="utf-8")
        nova = K.load_kb("atendimento")
        check(nova is not base, "assinatura mudou → recarregou")
        check("Horario de atendimento" in nova.full_text,
              "conteúdo do arquivo novo entrou na base")
        r = K.search_kb("atendimento", "qual o horario de atendimento de voces")
        check(bool(r) and r[0]["arquivo"] == tmp.name,
              "a busca encontra o arquivo novo")

        # Sem mudança de arquivo, não recarrega (índice BM25 é reaproveitado).
        check(K.load_kb("atendimento") is K.load_kb("atendimento"),
              "sem mudança → mesma instância do cache")

        # Placeholder não resolvido nunca chega ao modelo: sairia literal na
        # resposta ("seu certificado de {{curso}}") ou o modelo o preencheria
        # inventando.
        tmp.write_text("# Horario\nAtendemos de 9h as 18h.\n"
                       "Ola {{nome}}, seu curso e {{curso}}.\nFim do bloco.\n",
                       encoding="utf-8")
        comph = K.load_kb("atendimento")
        check("{{" not in comph.full_text, "nenhum '{{' sobrou")
        check("Ola" not in comph.full_text,
              "a linha com placeholder saiu INTEIRA (não só o '{{')")
        check("Fim do bloco" in comph.full_text,
              "linhas vizinhas são preservadas")
        check(comph.descartadas == 1, "contou exatamente 1 linha descartada")
    finally:
        tmp.unlink(missing_ok=True)
        K._cache.clear()
        K.load_kb("atendimento")


def test_kb_modo() -> None:
    secao("KB: modo inteira vs. busca pelo limite de chars")

    K._cache.clear()
    kb_real = K.load_kb("atendimento")
    slugs = ["genero-2026"]

    # Limite alto → base inteira no prompt, e buscar_base NÃO é oferecida:
    # oferecer a tool com a base já inline faz o modelo gastar um turno para
    # reler o que acabou de receber.
    with settings_de(K, AGENT_KB_INLINE_MAX_CHARS=1_000_000):
        K._cache.clear()
        kb = K.load_kb("atendimento")
        check(kb.mode == "inteira", "abaixo do limite → modo 'inteira'")
        nomes = [s["name"] for s in L._tools_do_perfil(slugs, PERFIL_ATENDIMENTO,
                                                       kb.modo_busca)]
        check("buscar_base" not in nomes, "modo inteira → sem buscar_base nas tools")
        sys_prompt = build_atendimento_prompt(kb.full_text, "- (cat)", "19/10/2026",
                                              modo=kb.mode)
        check("buscar_base" not in sys_prompt,
              "modo inteira → prompt não menciona buscar_base")
        check("Certificados" in sys_prompt, "modo inteira → conteúdo da KB no prompt")

    # Limite baixo → só o índice no prompt, e buscar_base aparece.
    with settings_de(K, AGENT_KB_INLINE_MAX_CHARS=500):
        K._cache.clear()
        kb = K.load_kb("atendimento")
        check(kb.mode == "busca", "acima do limite → modo 'busca'")
        check(len(kb.indice) < kb.total_chars, "índice é menor que a base inteira")
        check("02_certificados.md" in kb.indice, "índice lista o arquivo")
        check("Certificados" in kb.indice, "índice lista o título da seção")
        check("Nome errado" not in kb.indice,
              "índice NÃO carrega o conteúdo das seções")
        nomes = [s["name"] for s in L._tools_do_perfil(slugs, PERFIL_ATENDIMENTO,
                                                       kb.modo_busca)]
        check("buscar_base" in nomes, "modo busca → buscar_base presente")
        sys_prompt = build_atendimento_prompt(kb.indice, "- (cat)", "19/10/2026",
                                              modo=kb.mode)
        check("buscar_base" in sys_prompt, "modo busca → prompt manda chamar buscar_base")
        check("ÍNDICE" in sys_prompt,
              "modo busca → prompt avisa que o conteúdo não está ali")
        check(len(sys_prompt) < len(
                  build_atendimento_prompt(kb.full_text, "- (cat)", "19/10/2026")),
              "prompt do modo busca é menor que o da base inteira")

    K._cache.clear()
    K.load_kb("atendimento")
    check(K.load_kb("atendimento").mode == kb_real.mode,
          "modo volta ao real depois dos testes")


# --------------------------------------------------------------------------- #
# 4. busca BM25
# --------------------------------------------------------------------------- #
def test_busca() -> None:
    secao("busca léxica (BM25)")

    K._cache.clear()
    kb = K.load_kb("atendimento")

    def topo(consulta: str) -> str:
        r = K.search_kb("atendimento", consulta)
        return r[0]["arquivo"] if r else ""

    check(topo("meu nome saiu errado no certificado") == "02_certificados.md",
          "'nome errado no certificado' → 02_certificados")
    check(topo("quero estorno da compra") == "04_inscricoes_pagamento.md",
          "'estorno' → reembolso (sinônimo)")
    check(topo("como cancelo e peco devolucao") == "04_inscricoes_pagamento.md",
          "'cancelo/devolucao' → mesmo grupo de sinônimos")
    check(topo("esqueci minha senha nao consigo logar") == "05_comunidade.md",
          "'senha/logar' → Comunidade (sinônimo de acesso)")
    check(topo("o que esta incluso no intercambio") == "06_intercambios.md",
          "'intercambio' → 06_intercambios")
    check(topo("precisa ter faculdade completa para a pos") == "07_pos_graduacao.md",
          "requisito de graduação → 07_pos_graduacao")

    # Vazio NÃO é falha: é o sinal para a regra 4 (não invente, chame handoff).
    # Devolver o "menos pior" quando nada casa seria pior do que admitir.
    check(K.search_kb("atendimento", "receita de bolo de cenoura") == [],
          "consulta sem relação → lista vazia")
    check(K.search_kb("atendimento", "") == [], "consulta vazia → lista vazia")
    check(K.search_kb("atendimento", "de a o para") == [],
          "consulta só com stopwords → lista vazia")

    # Acento: quem digita no WhatsApp quase nunca acentua.
    com = {r["arquivo"] for r in K.search_kb("atendimento", "pós-graduação tem TCC")}
    sem = {r["arquivo"] for r in K.search_kb("atendimento", "pos graduacao tem tcc")}
    check(com == sem and "07_pos_graduacao.md" in com,
          "sem acento casa com acento")
    check({r["arquivo"] for r in K.search_kb("atendimento", "CERTIFICADO")}
          == {r["arquivo"] for r in K.search_kb("atendimento", "certificado")},
          "caixa alta não muda o resultado")

    # Forma dos resultados e limite.
    res = K.search_kb("atendimento", "certificado")
    check(all({"arquivo", "secao", "texto"} <= set(r) for r in res),
          "cada resultado traz arquivo, secao e texto")
    check(len(K.search_kb("atendimento", "certificado inscricao evento pos", k=5)) <= 5,
          "respeita o top-k")
    check(all(r.get("score", 0) > 0 for r in res),
          "só devolve chunk com score acima de zero")

    # Chunking: a linha é a unidade de sentido numa FAQ. Partir
    # "Nome errado no certificado: pedir o nome correto" produziria um trecho
    # que responde errado.
    linhas_kb = {l.strip() for l in kb.full_text.splitlines() if l.strip()}
    for c in kb.chunks:
        corpo = [l.strip() for l in c.texto.splitlines() if l.strip()]
        if not all(l in linhas_kb for l in corpo):
            check(False, f"chunk de {c.arquivo} cortou no meio de uma linha")
            break
    else:
        check(True, "nenhum chunk corta no meio de uma linha")
    check(all(c.secao in c.texto for c in kb.chunks if c.secao),
          "título da seção vai junto no texto do chunk")
    check(all(c.texto == c.texto.strip() for c in kb.chunks),
          "chunk não começa nem termina com espaço em branco")


def test_tool_buscar_base() -> None:
    secao("tool buscar_base")

    K._cache.clear()
    check(K.BUSCAR_BASE_SCHEMA["name"] == "buscar_base", "nome do schema")
    check("consulta" in K.BUSCAR_BASE_SCHEMA["parameters"]["properties"],
          "schema tem o parâmetro 'consulta'")

    vazio = K.executar_buscar_base({"consulta": "receita de lasanha"})
    check(vazio == {"resultados": [], "aviso": "nada na base"},
          "sem resultado → {'resultados': [], 'aviso': 'nada na base'}")

    cheio = K.executar_buscar_base({"consulta": "reembolso"})
    check(bool(cheio.get("resultados")), "com resultado → lista preenchida")
    check("aviso" not in cheio, "com resultado → sem aviso")
    check(K.executar_buscar_base({}) == {"resultados": [], "aviso": "nada na base"},
          "args sem 'consulta' não estoura")


# --------------------------------------------------------------------------- #
# 5. tools do perfil
# --------------------------------------------------------------------------- #
def test_tools_do_perfil() -> None:
    secao("tools: conjunto por perfil")

    slugs = ["genero-2026", "pos-tea"]
    vendas = [s["name"] for s in L._tools_do_perfil(slugs, PERFIL_VENDAS, False)]
    nat = [s["name"] for s in L._tools_do_perfil(slugs, PERFIL_ATENDIMENTO, False)]

    check(vendas == [s["name"] for s in L._default_tools(slugs)],
          "vendas = _default_tools, byte a byte (canal 6 inalterado)")

    # Fora do atendimento de propósito: follow-up é instrumento de venda e sai
    # por template da WABA do canal 6; e mexer no funil a partir de uma dúvida
    # de certificado corromperia o status do lead.
    check("schedule_followup" not in nat, "atendimento SEM schedule_followup")
    check("update_lead_status" not in nat, "atendimento SEM update_lead_status")
    check("schedule_followup" in vendas and "update_lead_status" in vendas,
          "...mas vendas continua com as duas")

    for t in ("handoff_to_human", "check_enrollment", "encaminhar_comercial_pos",
              "save_lead_memory"):
        check(t in nat, f"atendimento com {t}")
    for t in ("list_products", "get_product_info", "get_event_schedule",
              "get_faq_answer"):
        check(t in nat, f"atendimento com a tool de leitura {t}")

    check("buscar_base" not in vendas, "vendas nunca recebe buscar_base")
    check(len(set(nat)) == len(nat), "sem tool duplicada no atendimento")


def test_portao_de_execucao() -> None:
    """O modelo às vezes chuta um nome de tool que existe em OUTRO perfil.

    Sem o portão, `schedule_followup` chutado no atendimento cairia no executor
    de escrita e agendaria um follow-up de VENDAS de verdade — que sairia por
    template, pelo número errado, para alguém que só queria o certificado.

    Roda o `run_turn` real com sessão de banco dublê e cliente OpenAI dublê:
    sem Postgres, sem OpenAI, sem WhatsApp.
    """
    secao("tools: execução de tool fora do perfil é recusada")

    class _ResVazio:
        def scalars(self):
            return self

        def all(self):
            return []

        def first(self):
            return None

        def scalar_one_or_none(self):
            return None

    class _DbFake:
        def __init__(self):
            self.adicionados: list = []

        async def execute(self, *a, **k):
            return _ResVazio()

        def add(self, o):
            self.adicionados.append(o)

        async def flush(self):
            pass

        async def commit(self):
            pass

    class _Item:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    class _ClienteFake:
        """1ª resposta: chama a tool pedida. 2ª: devolve texto."""

        def __init__(self, tool_name: str):
            self.tool_name = tool_name
            self.n = 0
            self.oferecidas: list[str] = []
            self.responses = self

        async def create(self, **kw):
            self.n += 1
            self.oferecidas = [s["name"] for s in kw["tools"]]
            if self.n == 1:
                return _Item(
                    output=[_Item(type="function_call", name=self.tool_name,
                                  arguments="{}", call_id="c1")],
                    usage=_Item(input_tokens=1, output_tokens=1), output_text="")
            return _Item(
                output=[_Item(type="message", content=[
                    _Item(type="output_text",
                          text="Vou confirmar com a equipe e já te retorno 🙏")])],
                usage=_Item(input_tokens=1, output_tokens=1), output_text="")

    async def rodar(tool_name: str, profile: str):
        cli = _ClienteFake(tool_name)
        orig_cli, orig_guard = L.get_client, L.classify_input

        async def sem_guard(_texto):
            return {}

        L.get_client = lambda: cli
        L.classify_input = sem_guard
        try:
            db = _DbFake()
            sess = AgentSession(contact_wa_id=WA, channel_id=None, status="active",
                                history=[], turns_count=0)
            out = await L.run_turn(db, sess, _contato(WA),
                                   "meu certificado nao chegou", profile=profile)
            return cli, out, db
        finally:
            L.get_client, L.classify_input = orig_cli, orig_guard

    async def main_async():
        # Fora do perfil: nem é oferecida, e a execução é recusada com erro.
        for tool in ("schedule_followup", "update_lead_status"):
            cli, out, db = await rodar(tool, PERFIL_ATENDIMENTO)
            check(tool not in cli.oferecidas,
                  f"'{tool}' não é oferecida ao modelo no atendimento")
            check([t["name"] for t in out["tools"]] == [tool],
                  f"'{tool}' chutada é registrada no trace do turno")
            check(bool(out["reply"]),
                  f"o turno sobrevive à tool recusada ('{tool}')")

        # Dentro do perfil: é oferecida normalmente.
        cli, out, db = await rodar("list_products", PERFIL_ATENDIMENTO)
        check("list_products" in cli.oferecidas,
              "tool do perfil é oferecida e executada")

        # O log do turno registra o perfil e o modo da KB.
        logs = [o for o in db.adicionados if isinstance(o, AgentTurnLog)]
        saida = [o for o in logs if o.direction == "outbound"]
        check(bool(saida) and (saida[0].guardrail or {}).get("perfil") == PERFIL_ATENDIMENTO,
              "agent_turn_logs registra o perfil do turno")
        check(bool(saida) and (saida[0].guardrail or {}).get("kb_mode") in ("inteira", "busca"),
              "agent_turn_logs registra kb_mode")
        check(len(logs) == 2, "grava os 2 turnos (inbound + outbound) como em vendas")

        # Vendas: o JSON do guardrail NÃO ganha as chaves novas.
        cli, out, db = await rodar("list_products", PERFIL_VENDAS)
        saida = [o for o in db.adicionados
                 if isinstance(o, AgentTurnLog) and o.direction == "outbound"]
        check(bool(saida) and "perfil" not in (saida[0].guardrail or {}),
              "vendas: guardrail do log segue sem a chave 'perfil'")
        check(bool(saida) and "kb_mode" not in (saida[0].guardrail or {}),
              "vendas: guardrail do log segue sem a chave 'kb_mode'")

    asyncio.run(main_async())


def test_atendimento_nao_roteia() -> None:
    secao("atendimento: sem roteador de produto")

    src = inspect.getsource(L.run_turn)
    check("if not atendimento and not session.product_slug" in src,
          "roteamento condicionado a NÃO ser atendimento")
    check("_last_broadcast_text" in src,
          "_last_broadcast_text segue existindo (vendas usa)")
    # O bloco de categoria trocada é de vendas: no atendimento não há produto em
    # foco para trocar.
    check("if not atendimento and session.product_slug" in src,
          "bloco de produto em foco não roda no atendimento")


# --------------------------------------------------------------------------- #
# 6. anti-eco da IA
# --------------------------------------------------------------------------- #
def test_anti_eco() -> None:
    secao("anti-eco: o fromMe da própria IA não conta como humano")

    H._eco_ia.clear()
    wa = "5583999990000"
    texto = "Oi! Já te confirmo isso com a equipe 💙"

    check(not H.eh_eco_da_ia(wa, texto), "antes de registrar: não é eco")
    H.registrar_eco_ia(wa, texto)
    check(H.eh_eco_da_ia(wa, texto), "depois de registrar: é eco → não pausa")

    # NÃO consome no match: o Evolution pode reentregar o mesmo
    # MESSAGES_UPSERT, e um pop no primeiro match faria a reentrega virar
    # "humano" e pausar a IA sem ninguém ter digitado nada.
    check(H.eh_eco_da_ia(wa, texto), "segunda checagem ainda casa (não consome)")
    check(H.eh_eco_da_ia(wa, texto), "terceira checagem ainda casa")

    # Normalização: strip + colapso de espaços.
    check(H.eh_eco_da_ia(wa, f"  {texto}  "), "tolera espaço nas bordas")
    check(H.eh_eco_da_ia(wa, texto.replace(" ", "  ")),
          "tolera espaço duplicado no meio")
    check(H.eh_eco_da_ia(wa, texto.replace(" ", "\n")),
          "tolera quebra de linha onde havia espaço")

    # Texto diferente ou outro contato = humano → pausa.
    check(not H.eh_eco_da_ia(wa, "Bom dia, aqui é a Maria do CENAT"),
          "texto diferente → humano (pausa)")
    check(not H.eh_eco_da_ia(wa, texto[:-1]),
          "texto quase igual → humano (pausa)")
    check(not H.eh_eco_da_ia("5511888887777", texto),
          "mesmo texto para OUTRO contato → humano (pausa)")
    check(not H.eh_eco_da_ia(wa, ""), "texto vazio não casa")

    # TTL: entrada velha expira e deixa de ser eco.
    H._eco_ia.clear()
    H._eco_ia[(wa, H._norm_eco(texto))] = time.monotonic() - 1.0
    check(not H.eh_eco_da_ia(wa, texto), "entrada expirada não é mais eco")
    check((wa, H._norm_eco(texto)) not in H._eco_ia,
          "o GC removeu a entrada expirada")
    check(H.ECO_TTL >= 60, "TTL cobre com folga a latência de envio + webhook")

    # O registro acontece ANTES do envio: o webhook pode chegar enquanto o
    # `await send_text` ainda está em voo.
    src = inspect.getsource(H._send)
    check(src.index("registrar_eco_ia") < src.index("provider.send_text"),
          "registrar_eco_ia é chamado ANTES de provider.send_text")

    H._eco_ia.clear()


# --------------------------------------------------------------------------- #
# 7. @lid
# --------------------------------------------------------------------------- #
def test_lid() -> None:
    secao("@lid: resolução do telefone real")

    # Caminho normal, sem @lid.
    tel, falhou = _resolver_telefone({}, "5583999999999@s.whatsapp.net")
    check(tel == "5583999999999" and not falhou, "jid normal → telefone, sem flag")

    # @lid com remoteJidAlt.
    tel, falhou = _resolver_telefone(
        {"remoteJidAlt": "5583999999999@s.whatsapp.net"}, "123456789@lid")
    check(tel == "5583999999999" and not falhou, "@lid + remoteJidAlt → telefone")

    # @lid com senderPn.
    tel, falhou = _resolver_telefone(
        {"senderPn": "5511888887777@s.whatsapp.net"}, "987654321@lid")
    check(tel == "5511888887777" and not falhou, "@lid + senderPn → telefone")

    # remoteJidAlt tem precedência.
    tel, falhou = _resolver_telefone(
        {"remoteJidAlt": "5583111112222@s.whatsapp.net",
         "senderPn": "5511888887777@s.whatsapp.net"}, "1@lid")
    check(tel == "5583111112222", "remoteJidAlt tem precedência sobre senderPn")

    # @lid sem nenhum dos dois → flag ligada. A mensagem é persistida (não se
    # perde), mas o agente NÃO é acordado: responder a um identificador que não
    # é telefone criaria contato fantasma e a resposta não chegaria a ninguém.
    tel, falhou = _resolver_telefone({}, "123456789@lid")
    check(tel == "123456789" and falhou, "@lid sem alternativa → flag ligada")
    tel, falhou = _resolver_telefone(
        {"remoteJidAlt": "", "senderPn": None}, "123456789@lid")
    check(falhou, "@lid com campos vazios → flag ligada")

    # Campo que não é telefone (outro @lid) não serve.
    tel, falhou = _resolver_telefone({"remoteJidAlt": "55@lid"}, "123@lid")
    check(falhou, "@lid cujo alt também é @lid → flag ligada")

    # Grupo não passa por aqui, mas o dispatch do agente exige not is_group.
    src = inspect.getsource(__import__("app.evolution.routes",
                                       fromlist=["webhook"]).webhook)
    check("lid_sem_telefone" in src, "o webhook usa a flag de @lid")
    check("not lid_sem_telefone" in src,
          "o dispatch do agente exige @lid resolvido")


# --------------------------------------------------------------------------- #
# 8. regras do webhook Evolution (leitura do fonte)
# --------------------------------------------------------------------------- #
def test_webhook_regras() -> None:
    secao("webhook Evolution: regras da Nat")

    src = inspect.getsource(__import__("app.evolution.routes",
                                       fromlist=["webhook"]).webhook)

    check("canal_atendimento" in src, "o webhook calcula se o canal é da Nat")
    check("_PERFIL_ATENDIMENTO" in src,
          "a condição usa o perfil, não só agent_enabled")

    # `nunca_falou` tem que ser lido ANTES de last_inbound_at ser sobrescrito —
    # lido depois seria sempre falso e a ativação no 1º inbound nunca ocorreria.
    check(src.index("nunca_falou = contact.last_inbound_at is None")
          < src.index("contact.last_inbound_at = datetime.now(SP_TZ)"),
          "nunca_falou é lido ANTES de sobrescrever last_inbound_at")
    check("contact.ai_active = True" in src, "1º inbound ativa a IA")
    check("contact.channel_id = channel_id" in src,
          "canal da conversa = último canal de entrada")

    # Eco checado antes da dedup: no caminho da corrida a linha ainda não
    # existe, e é aí que importa não ler a IA como humano.
    check(src.index("eco_da_ia = bool(") < src.index("# Deduplicação por wa_message_id"),
          "eco é checado ANTES da dedup por wa_message_id")
    check("AGENT_ATENDIMENTO_PAUSE_ON_HUMAN" in src,
          "a pausa por humano é controlada pela setting")
    check("humano.ai_active = False" in src, "humano assumindo pausa a IA")
    check("sent_by_ai=eco_da_ia" in src,
          "eco é persistido com sent_by_ai (badge do inbox não mente)")

    # Dispatch depois do commit: o handler abre a própria sessão e precisa ver a
    # mensagem gravada (é o que o watermark lê).
    check(src.index("await db.commit()") < src.index("handle_inbound"),
          "dispatch do agente vem DEPOIS do commit")
    check("texto_do_agente" in src,
          "usa o texto capturado antes de a mídia sobrescrever text_content")

    # extendedTextMessage: texto com link ou em resposta a outra mensagem. Um
    # teste por msg_type contra ("text","conversation") deixaria a Nat muda.
    check('msg_type in ("text", "conversation")' not in src,
          "o filtro de texto NÃO depende do nome do msg_type")


def test_workers_retem_por_perfil() -> None:
    secao("workers: follow-up e boas-vindas só pelo canal de vendas")

    from app.agent import workers

    src = inspect.getsource(workers.process_followups_once)
    check("_channel_profile(channel) != PERFIL_VENDAS" in src,
          "retém quando o canal resolvido não é de vendas")
    check("follow-up retido" in src, "loga a retenção")
    check(src.index("_channel_profile(channel) != PERFIL_VENDAS")
          < src.index("within24"),
          "a retenção vem ANTES de escolher texto livre vs. template")

    # `welcome` é um AgentFollowup, então o mesmo portão cobre boas-vindas.
    check('kind="welcome"' in inspect.getsource(workers._convert),
          "boas-vindas é agendada como AgentFollowup (mesmo portão)")


def test_status_route() -> None:
    secao("/api/agent/status: campos do atendimento")

    src = inspect.getsource(__import__("app.agent.routes",
                                       fromlist=["agent_status"]).agent_status)
    check("atendimento_sandbox" in src, "expõe atendimento_sandbox")
    check("atendimento_sandbox_count" in src, "expõe atendimento_sandbox_count")
    check("AGENT_ATENDIMENTO_TEST_WA_ALLOWLIST" in src,
          "lê a allowlist do atendimento")
    # Nunca os números: são telefones de pessoas reais.
    check("entradas_atend)" in src and "parse_allowlist" in src,
          "devolve só o booleano e a contagem, nunca os números")


# --------------------------------------------------------------------------- #
# 9. escopo por canal — TOCA O BANCO
# --------------------------------------------------------------------------- #
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


_enviadas: list[tuple[int, str]] = []


async def _fake_run_turn(db, session, contact, user_text: str, **kw) -> dict:
    session.history = list(session.history or []) + [
        {"role": "user", "content": user_text},
        {"role": "assistant", "content": f"eco: {user_text}"},
    ]
    session.turns_count = (session.turns_count or 0) + 1
    session.last_outbound_at = now_sp()
    return {"reply": f"eco[{kw.get('profile')}]: {user_text}", "product_slug": None}


async def _fake_send(db, channel, wa_id: str, reply: str) -> None:
    _enviadas.append((channel.id, reply))


async def _semear_inbound(canal_id: int, texto: str, quando: dt.datetime) -> None:
    async with AsyncSessionLocal() as db:
        db.add(Message(
            wa_message_id=f"{WA}:{canal_id}:{quando.isoformat()}",
            contact_wa_id=WA, channel_id=canal_id, direction="inbound",
            message_type="text", content=texto, timestamp=quando,
            status="received", sent_by_ai=False,
        ))
        await db.commit()


async def _sessoes() -> list[AgentSession]:
    async with AsyncSessionLocal() as db:
        return list((await db.execute(
            select(AgentSession).where(AgentSession.contact_wa_id == WA)
            .order_by(AgentSession.id)
        )).scalars().all())


async def test_escopo_por_canal(c1: int, c2: int) -> None:
    """A mesma pessoa falando com vendas e com atendimento não pode misturar.

    Sem o filtro por canal, o segundo canal herdaria a sessão (e o histórico) do
    primeiro — a Nat responderia com o contexto de venda de congresso — e o
    watermark de um canal faria o outro achar que já respondeu, engolindo a
    resposta.
    """
    secao(f"escopo por canal (canais {c1} e {c2}) — BANCO")

    t1 = now_sp() - dt.timedelta(seconds=30)
    await _semear_inbound(c1, "Oi, quero saber do congresso", t1)
    await H._process(c1, WA)

    sess = await _sessoes()
    check(len(sess) == 1, "1º canal criou exatamente uma sessão")
    check(bool(sess) and sess[0].channel_id == c1, "a sessão é do canal 1")

    # Mesma pessoa, OUTRO canal: sessão nova, histórico limpo.
    t2 = now_sp() - dt.timedelta(seconds=10)
    await _semear_inbound(c2, "meu certificado nao chegou", t2)
    await H._process(c2, WA)

    sess = await _sessoes()
    check(len(sess) == 2, "o 2º canal criou uma sessão PRÓPRIA (não reusou)")
    por_canal = {s.channel_id: s for s in sess}
    check(set(por_canal) == {c1, c2}, "uma sessão por canal")

    s1, s2 = por_canal.get(c1), por_canal.get(c2)
    check(s2 is not None and len(s2.history or []) == 2,
          "sessão do canal 2 tem só o próprio turno")
    check(s2 is not None and all(
              "congresso" not in (m.get("content") or "")
              for m in (s2.history or [])),
          "o histórico do canal 1 NÃO vazou para o canal 2")
    check(s1 is not None and s2 is not None and s1.id != s2.id,
          "são sessões distintas")

    # Watermark por canal: o inbound do canal 2 não pode ter movido o do canal 1.
    check(s1 is not None and s1.last_inbound_at is not None
          and abs((s1.last_inbound_at - t1).total_seconds()) < 2,
          "watermark do canal 1 ficou no inbound DELE")
    check(s2 is not None and s2.last_inbound_at is not None
          and abs((s2.last_inbound_at - t2).total_seconds()) < 2,
          "watermark do canal 2 ficou no inbound DELE")

    # Cada resposta saiu pelo canal certo (critério 4).
    canais_resposta = [c for c, _ in _enviadas]
    check(canais_resposta == [c1, c2],
          "cada resposta saiu pelo canal em que a pessoa escreveu")

    # Reprocessar o canal 1 não responde de novo: o watermark dele já cobriu
    # aquele inbound, e o inbound do canal 2 não é dele.
    antes = len(_enviadas)
    await H._process(c1, WA)
    check(len(_enviadas) == antes,
          "reprocessar o canal 1 não gera resposta duplicada")


async def test_log_erro_por_canal(c1: int, c2: int) -> None:
    secao("_log_erro: erro do turno vai para a sessão do canal certo")

    sess = {s.channel_id: s.id for s in await _sessoes()}
    if c1 not in sess or c2 not in sess:
        check(False, "pré-condição: as duas sessões deveriam existir")
        return

    await H._log_erro(WA, RuntimeError("boom de teste"), c2)
    async with AsyncSessionLocal() as db:
        logs = list((await db.execute(
            select(AgentTurnLog).where(AgentTurnLog.session_id == sess[c2],
                                       AgentTurnLog.content.is_(None))
        )).scalars().all())
    check(bool(logs), "o erro foi gravado na sessão do canal informado")
    check(any("boom de teste" in ((lg.guardrail or {}).get("error") or "")
              for lg in logs), "o erro registra a exceção")

    async with AsyncSessionLocal() as db:
        outros = list((await db.execute(
            select(AgentTurnLog).where(AgentTurnLog.session_id == sess[c1],
                                       AgentTurnLog.content.is_(None))
        )).scalars().all())
    check(not outros, "a sessão do OUTRO canal não recebeu o erro")


# --------------------------------------------------------------------------- #
def main() -> int:
    # Parte sem banco.
    test_gating_perfil()
    test_channel_profile()
    test_sandbox_por_perfil()
    test_kb_carga()
    test_kb_placeholder_e_recarga()
    test_kb_modo()
    test_busca()
    test_tool_buscar_base()
    test_tools_do_perfil()
    test_portao_de_execucao()
    test_atendimento_nao_roteia()
    test_anti_eco()
    test_lid()
    test_webhook_regras()
    test_workers_retem_por_perfil()
    test_status_route()

    # Parte com banco: precisa de dois canais reais (FK em messages.channel_id
    # e agent_sessions.channel_id).
    async def parte_banco() -> None:
        L.run_turn = _fake_run_turn
        H._send = _fake_send
        H.agent_should_handle = lambda channel, contact: True

        async with AsyncSessionLocal() as db:
            canais = list((await db.execute(
                select(Channel.id).order_by(Channel.id)
            )).scalars().all())
        if len(canais) < 2:
            check(False, "o teste de escopo precisa de 2 canais no banco")
            return
        c1, c2 = canais[0], canais[1]

        await limpar()
        try:
            async with AsyncSessionLocal() as db:
                db.add(Contact(
                    wa_id=WA, name="Teste atendimento", channel_id=c1,
                    ai_active=True, is_group=False, opted_out=False,
                    ai_memory={}, lead_status="novo",
                ))
                await db.commit()
            await test_escopo_por_canal(c1, c2)
            await test_log_erro_por_canal(c1, c2)
        finally:
            await limpar()

    asyncio.run(parte_banco())

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
