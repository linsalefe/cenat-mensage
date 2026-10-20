"""Perfis do agente — identidade de qual persona atende um canal.

Módulo próprio e sem dependências pesadas de propósito: `handler` e `loop`
precisam dos mesmos nomes, e `loop` importar de `handler` (ou o contrário)
amarra dois módulos grandes por causa de duas constantes — além de só não dar
ciclo por acidente de ordem de import.

- `vendas`: o agente de congressos/pós do canal 6 (Meta oficial). É o default.
- `atendimento`: a "Nat", no canal Evolution do atendimento.
"""
from __future__ import annotations

PERFIL_VENDAS = "vendas"
PERFIL_ATENDIMENTO = "atendimento"
PERFIS = (PERFIL_VENDAS, PERFIL_ATENDIMENTO)


def channel_profile(channel) -> str:
    """Perfil efetivo do canal: "vendas" (congressos/pós) ou "atendimento" (Nat).

    `None`/vazio cai em "vendas" de propósito: a coluna `channels.agent_profile`
    tem server_default 'vendas', mas um `Channel` montado em memória e não
    persistido (testes, evals) vem com o atributo `None` — e o comportamento
    default tem que ser o que já existia.

    Valor desconhecido é devolvido como veio, normalizado. Quem decide o que
    fazer com ele é `handler.canal_bate_com_perfil`, que devolve False
    (fail-closed): um typo cala o agente naquele canal em vez de rodar o perfil
    errado.
    """
    return (getattr(channel, "agent_profile", None) or PERFIL_VENDAS).strip().lower()
