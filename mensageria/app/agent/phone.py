"""Normalização de número de WhatsApp e allowlist do modo sandbox.

A lógica de variantes vivia dentro de `workers._find_contact` (match de
participante da Doity com o contato) e agora é compartilhada com o gating de
sandbox — mesmo problema, dois lugares.

**Por que variantes e não uma forma canônica:** no Brasil não dá para decidir com
certeza se um número de 12 dígitos "deveria" ter o 9º dígito. `5583988887777` e
`558388887777` podem ser a mesma pessoa, e não há como saber pelo número. Então
comparamos conjuntos de variantes plausíveis dos DOIS lados, em vez de inventar
uma canonicalização que erraria em silêncio.
"""
from __future__ import annotations

import re

# wa_id de Instagram vem prefixado (`ig:<scoped_id>`) e não é telefone — nunca
# deve casar com uma allowlist de números.
IG_PREFIX = "ig:"


def digits(s: str | None) -> str:
    """Só os dígitos ('+55 (83) 99999-9999' -> '5583999999999')."""
    return re.sub(r"\D", "", s or "")


def wa_variants(phone: str | None) -> set[str]:
    """Variantes plausíveis de um número, para comparar com o banco.

    Mesma regra de sempre (extraída de `workers._find_contact`):
    - os dígitos como vieram;
    - com DDI 55 na frente, quando não tem;
    - alternando o 9º dígito BR (13 dígitos -> tira; 12 -> insere), o que cobre
      os dois formatos em que o mesmo celular aparece.
    """
    d = digits(phone)
    if not d:
        return set()

    cands = {d}
    if not d.startswith("55"):
        cands.add("55" + d)

    # Aplica a alternância do 9 em cada candidato que pareça número BR completo.
    for c in list(cands):
        if not c.startswith("55"):
            continue
        if len(c) == 13:
            cands.add(c[:4] + c[5:])          # 5583 9 99999999 -> 5583 99999999
        elif len(c) == 12:
            cands.add(c[:4] + "9" + c[4:])    # 5583 88887777  -> 5583 9 88887777
    return cands


def parse_allowlist(raw: str | None) -> list[str]:
    """'5583999999999, 5511888888888' -> ['5583999999999', '5511888888888'].

    Entradas vazias e não-numéricas caem fora. Devolve lista (não set) para o log
    de boot sair estável.
    """
    out: list[str] = []
    for parte in (raw or "").replace(";", ",").split(","):
        d = digits(parte)
        if d and d not in out:
            out.append(d)
    return out


def allowlist_variants(entries: list[str]) -> set[str]:
    """Une as variantes de todas as entradas — pré-computa uma vez, compara N vezes."""
    todas: set[str] = set()
    for e in entries:
        todas |= wa_variants(e)
    return todas


def in_allowlist(wa_id: str | None, variantes: set[str]) -> bool:
    """True se `wa_id` casar com alguma variante da allowlist.

    Compara variante-contra-variante: a allowlist pode ter o número com 9 e o
    banco sem (ou o contrário). Instagram (`ig:`) nunca casa.
    """
    if not variantes or not wa_id:
        return False
    if wa_id.startswith(IG_PREFIX):
        return False
    return bool(wa_variants(wa_id) & variantes)


def mask(wa_id: str | None) -> str:
    """wa_id truncado para log ('5583999999999' -> '5583*****9999')."""
    s = (wa_id or "").strip()
    if len(s) <= 8:
        return s or "?"
    return f"{s[:4]}{'*' * (len(s) - 8)}{s[-4:]}"
