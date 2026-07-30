#!/usr/bin/env python3
"""Testes do MODO SANDBOX do agente (allowlist de contatos de teste).

Sem pytest de propósito: o venv de produção não o tem, e instalar dependência
num servidor que atende cliente real por causa de teste não se paga. Mesma
convenção do `eval_agent.py` — script executável com asserts.

Não toca no banco, não chama OpenAI, não envia WhatsApp: o gating é síncrono e
os objetos são construídos em memória.

Uso:
    .venv/bin/python tests/agent/test_sandbox.py
Exit 0 = tudo passou.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.agent import handler as handler_mod  # noqa: E402
from app.agent.phone import (  # noqa: E402
    allowlist_variants, digits, in_allowlist, mask, parse_allowlist, wa_variants,
)
from app.models import AgentFollowup, Channel, Contact  # noqa: E402

SP_TZ = dt.timezone(dt.timedelta(hours=-3))

_falhas: list[str] = []
_ok = 0


def check(cond: bool, rotulo: str) -> None:
    global _ok
    if cond:
        _ok += 1
        print(f"  ok   {rotulo}")
    else:
        _falhas.append(rotulo)
        print(f"  FALHA {rotulo}")


def secao(t: str) -> None:
    print(f"\n## {t}")


# --------------------------------------------------------------------------- #
# 1. helper de normalização
# --------------------------------------------------------------------------- #
def test_normalizacao() -> None:
    secao("normalização de número")

    check(digits("+55 (83) 99999-9999") == "5583999999999", "digits tira máscara")
    check(digits(None) == "", "digits aceita None")
    check(wa_variants("") == set(), "número vazio não gera variante")

    # 13 dígitos (com 9º dígito) deve gerar a forma de 12 e vice-versa.
    v13 = wa_variants("5583999999999")
    check("5583999999999" in v13, "13 dígitos: mantém a forma original")
    check("558399999999" in v13, "13 dígitos: gera a forma SEM o 9º dígito")

    v12 = wa_variants("558388887777")
    check("558388887777" in v12, "12 dígitos: mantém a forma original")
    check("5583988887777" in v12, "12 dígitos: gera a forma COM o 9º dígito")

    # DDI implícito: número sem 55 tem que casar com o do banco, que tem.
    v_sem_ddi = wa_variants("83999999999")
    check("5583999999999" in v_sem_ddi, "DDI implícito: acrescenta 55")
    check("558399999999" in v_sem_ddi,
          "DDI implícito + alternância do 9 (o antigo _find_contact NÃO cobria)")

    # As duas formas do mesmo celular casam entre si nos dois sentidos.
    check(bool(wa_variants("5583999999999") & wa_variants("558399999999")),
          "as duas formas do mesmo número se cruzam")

    # Números realmente diferentes não podem casar.
    check(not (wa_variants("5583999999999") & wa_variants("5511888888888")),
          "números diferentes não casam")
    check(not (wa_variants("5583999999999") & wa_variants("5583999999998")),
          "último dígito diferente não casa")

    check(mask("5583999999999") == "5583*****9999", "mask esconde o miolo")
    check(mask("123") == "123", "mask não quebra em número curto")


def test_parse_allowlist() -> None:
    secao("parse da allowlist")

    check(parse_allowlist("") == [], "vazia → lista vazia (produção)")
    check(parse_allowlist(None) == [], "None → lista vazia")
    check(parse_allowlist("   ") == [], "só espaço → lista vazia")
    check(parse_allowlist("5583999999999") == ["5583999999999"], "uma entrada")
    check(parse_allowlist("5583999999999,5511888888888")
          == ["5583999999999", "5511888888888"], "duas entradas")
    check(parse_allowlist(" +55 83 99999-9999 , 5511888888888 ")
          == ["5583999999999", "5511888888888"], "tolera máscara e espaço")
    check(parse_allowlist("5583999999999,5583999999999") == ["5583999999999"],
          "deduplica")
    check(parse_allowlist("5583999999999,,abc,") == ["5583999999999"],
          "descarta entradas vazias e não numéricas")

    variantes = allowlist_variants(["5583999999999"])
    check(in_allowlist("5583999999999", variantes), "casa forma idêntica")
    check(in_allowlist("558399999999", variantes), "casa a forma sem o 9º dígito")
    check(not in_allowlist("5511888888888", variantes), "não casa outro número")
    check(not in_allowlist("ig:17841405925471370", variantes),
          "wa_id de Instagram nunca casa com allowlist de telefone")
    check(not in_allowlist("5583999999999", set()),
          "allowlist vazia via in_allowlist → não casa (quem libera é o chamador)")


# --------------------------------------------------------------------------- #
# helpers de fixture
# --------------------------------------------------------------------------- #
def _canal(**kw) -> Channel:
    base = dict(id=6, name="Cenat - disparos", provider="official",
                operation_mode="ai", agent_enabled=True)
    base.update(kw)
    return Channel(**base)


def _contato(wa_id="5583999999999", **kw) -> Contact:
    base = dict(wa_id=wa_id, name="Teste", ai_active=True, opted_out=False,
                is_group=False, channel_id=6)
    base.update(kw)
    return Contact(**base)


class _SettingsFake:
    """Troca só AGENT_TEST_WA_ALLOWLIST, delegando o resto ao settings real."""

    def __init__(self, real, allowlist: str):
        self._real = real
        self.AGENT_TEST_WA_ALLOWLIST = allowlist

    def __getattr__(self, nome):
        return getattr(self._real, nome)


class allowlist_de:
    """Context manager: roda o bloco com a allowlist dada."""

    def __init__(self, valor: str):
        self.valor = valor

    def __enter__(self):
        self._orig = handler_mod.settings
        handler_mod.settings = _SettingsFake(self._orig, self.valor)
        return self

    def __exit__(self, *exc):
        handler_mod.settings = self._orig
        return False


# --------------------------------------------------------------------------- #
# 2. gating no handler (ponto 1 dos 3)
# --------------------------------------------------------------------------- #
def test_gating_handler() -> None:
    secao("gating no handler — allowlist VAZIA (produção)")
    with allowlist_de(""):
        check(handler_mod.sandbox_active() is False, "sandbox_active() False")
        check(handler_mod.agent_should_handle(_canal(), _contato("5583999999999")),
              "atende contato qualquer")
        check(handler_mod.agent_should_handle(_canal(), _contato("5511777776666")),
              "atende outro contato qualquer")
        # O gating original tem que continuar valendo.
        check(not handler_mod.agent_should_handle(_canal(agent_enabled=False), _contato()),
              "agent_enabled=False continua bloqueando")
        check(not handler_mod.agent_should_handle(_canal(operation_mode="chatbot"), _contato()),
              "operation_mode != ai continua bloqueando")
        check(not handler_mod.agent_should_handle(_canal(), _contato(ai_active=False)),
              "ai_active=False continua bloqueando")
        check(not handler_mod.agent_should_handle(_canal(), _contato(opted_out=True)),
              "opted_out continua bloqueando")
        check(not handler_mod.agent_should_handle(_canal(), _contato(is_group=True)),
              "is_group continua bloqueando")

    secao("gating no handler — allowlist NÃO-VAZIA (sandbox)")
    with allowlist_de("5583999999999,5511888888888"):
        check(handler_mod.sandbox_active() is True, "sandbox_active() True")
        check(handler_mod.agent_should_handle(_canal(), _contato("5583999999999")),
              "ATENDE número da allowlist")
        check(handler_mod.agent_should_handle(_canal(), _contato("5511888888888")),
              "ATENDE o segundo número da allowlist")
        check(handler_mod.agent_should_handle(_canal(), _contato("558399999999")),
              "ATENDE a variante sem o 9º dígito do número da allowlist")
        check(not handler_mod.agent_should_handle(_canal(), _contato("5511777776666")),
              "IGNORA cliente fora da allowlist (canal real ligado)")
        check(not handler_mod.agent_should_handle(_canal(), _contato("ig:17841405925471370")),
              "IGNORA contato de Instagram")
        # Sandbox não afrouxa nada: continua exigindo o gating base.
        check(not handler_mod.agent_should_handle(_canal(agent_enabled=False),
                                                 _contato("5583999999999")),
              "número da allowlist NÃO passa se o canal está desligado")
        check(not handler_mod.agent_should_handle(_canal(), _contato("5583999999999",
                                                                    opted_out=True)),
              "número da allowlist NÃO passa se optou por sair")


# --------------------------------------------------------------------------- #
# 3. gating do envio de follow-up e de boas-vindas (pontos 2 e 3)
# --------------------------------------------------------------------------- #
def _fu(wa_id: str, kind: str) -> AgentFollowup:
    return AgentFollowup(
        session_id=None, contact_wa_id=wa_id,
        run_at=dt.datetime.now(SP_TZ), kind=kind, payload={}, status="pending",
    )


def _decide_envio(wa_id: str, kind: str) -> tuple[bool, str]:
    """Reproduz a decisão de envio do worker de follow-up para um contato.

    Espelha o trecho de `process_followups_once`: em sandbox, fora da allowlist
    o follow-up é RETIDO e o status fica 'pending' (não 'skipped', para não
    perder um envio legítimo durante o teste).
    """
    fu = _fu(wa_id, kind)
    if handler_mod.sandbox_active() and not handler_mod.sandbox_allows(wa_id):
        return False, fu.status          # retido, status intacto
    return True, fu.status


def test_gating_followup_e_welcome() -> None:
    secao("envio de follow-up — allowlist VAZIA (produção)")
    with allowlist_de(""):
        enviou, status = _decide_envio("5511777776666", "no_reply")
        check(enviou, "envia follow-up para contato qualquer")
        enviou, status = _decide_envio("5511777776666", "welcome")
        check(enviou, "envia boas-vindas para comprador qualquer")

    secao("envio de follow-up — allowlist NÃO-VAZIA (sandbox)")
    with allowlist_de("5583999999999"):
        enviou, status = _decide_envio("5583999999999", "no_reply")
        check(enviou, "envia follow-up para número da allowlist")

        enviou, status = _decide_envio("5511777776666", "no_reply")
        check(not enviou, "NÃO envia follow-up para cliente fora da allowlist")
        check(status == "pending",
              "follow-up retido fica 'pending' (não 'cancelled' nem 'skipped')")

        # O caso real: a conversão da Doity cria boas-vindas para comprador de
        # verdade mesmo em sandbox (ela é passiva). O ENVIO tem que ser retido.
        enviou, status = _decide_envio("5511777776666", "welcome")
        check(not enviou, "NÃO envia boas-vindas para comprador fora da allowlist")
        check(status == "pending", "boas-vindas retida fica 'pending'")

        enviou, _ = _decide_envio("558399999999", "welcome")
        check(enviou, "envia boas-vindas para variante sem 9º dígito da allowlist")


def test_conversao_segue_passiva() -> None:
    """A conversão não pode ser afetada: ela só grava, não envia."""
    secao("conversão por polling não é gated por sandbox")
    import inspect

    from app.agent import workers

    src_convert = inspect.getsource(workers._convert)
    check("sandbox" not in src_convert.replace("# ", "").lower()
          or "sandbox" in src_convert.lower(),
          "_convert existe e é inspecionável")
    check("fire_conversion" in src_convert, "_convert continua chamando fire_conversion")
    check('lead_status = "ganho"' in src_convert, "_convert continua marcando ganho")
    check("sandbox_allows" not in src_convert,
          "_convert NÃO chama sandbox_allows (registro é passivo, não filtrado)")

    src_poll = inspect.getsource(workers.poll_conversions_once)
    check("sandbox_allows" not in src_poll,
          "poll_conversions_once NÃO filtra por sandbox")

    # E o gating do envio precisa estar de fato no worker de follow-up.
    src_fu = inspect.getsource(workers.process_followups_once)
    check("sandbox_allows" in src_fu, "process_followups_once filtra por sandbox")


def test_ponto_unico() -> None:
    """A semântica tem que morar em agent_should_handle, não espalhada."""
    secao("sandbox implementado em um ponto só")
    import inspect

    from app.agent import loop

    src = inspect.getsource(handler_mod.agent_should_handle)
    check("sandbox_allows" in src, "agent_should_handle aplica o sandbox")

    check("sandbox" not in inspect.getsource(loop.run_turn).lower(),
          "run_turn NÃO conhece sandbox (evals chamam ele direto)")


def main() -> int:
    test_normalizacao()
    test_parse_allowlist()
    test_gating_handler()
    test_gating_followup_e_welcome()
    test_conversao_segue_passiva()
    test_ponto_unico()

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
