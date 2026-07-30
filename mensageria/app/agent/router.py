"""Roteamento de produto: descobre qual congresso ou pós é o foco da conversa a
partir do anúncio (CTWA), do texto inicial (wa.me), do disparo que a pessoa está
respondendo e de palavras-chave (§3.5).

Congresso e pós convivem no mesmo catálogo, o que traz dois problemas novos:

1. **Termos genéricos.** "pós", "graduação", "saúde", "mental" aparecem em quase
   todos os 13 cursos e não distinguem nada. Em vez de manter uma lista fixa de
   stopwords, os tokens comuns são descobertos por frequência DENTRO de cada
   kind — a régua se ajusta sozinha quando cursos entram ou saem.

2. **Confusão de categoria.** "quero o congresso de TEA" — TEA é pós, não
   congresso. Nesse caso o roteador ainda aponta o produto certo, mas devolve
   `mismatch=True` para o agente esclarecer a diferença antes de seguir, em vez
   de tratar a pessoa como se ela já soubesse.
"""
from __future__ import annotations

import json
import re
import unicodedata
from typing import NamedTuple, Optional

from app.models import AgentProduct, Contact

# Ruído comum aos dois kinds (numerais romanos de edição, ano, conectivos).
_STOP = {
    "congresso", "online", "internacional", "nacional", "de", "do", "da", "e", "em",
    "boas", "praticas", "para", "com", "sobre", "cenat", "curso", "edicao",
    "pos", "posgraduacao", "graduacao", "especializacao", "turma",
    "i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x",
    "2025", "2026", "2027",
}

# Token presente em mais de 40% dos produtos do mesmo kind não distingue nada.
_LIMITE_COMUM = 0.40

# Como a pessoa sinaliza que fala de pós vs. de congresso.
_RE_POS = re.compile(
    r"\b(pos|pos\s*graduacao|posgraduacao|especializacao|especialista|"
    r"lato\s*sensu|mestrado|doutorado|matricula|matricular|"
    r"processo\s*seletivo|pre\s*aplicacao)\b"
)
_RE_CONGRESSO = re.compile(
    r"\b(congresso|evento|simposio|seminario|palestra|inscricao\s*no\s*congresso)\b"
)


class Rota(NamedTuple):
    slug: Optional[str]
    kind_hint: Optional[str]   # "pos" | "congresso" | None (sem sinal)
    mismatch: bool             # a pessoa chamou de um kind, mas o produto é do outro


def _strip(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower()


def _acronimos(nome: str) -> set[str]:
    """Siglas do nome original (TEA, RAPS, CAPS, CNV) — curtas mas decisivas,
    logo escapam do corte de tamanho mínimo aplicado aos tokens comuns."""
    return {a.lower() for a in re.findall(r"\b([A-Z]{3,5})\b", nome or "")}


def _tokens(nome: str) -> set[str]:
    kws: set[str] = set()
    for tok in re.split(r"[^a-z0-9]+", _strip(nome)):
        if tok and tok not in _STOP and len(tok) >= 4:
            kws.add(tok)
    for extra in list(kws):  # radicais úteis (vozes -> voz, grupos -> grupo)
        if extra.endswith("s") and len(extra) > 4:
            kws.add(extra[:-1])
    return kws


def _comuns_por_kind(products: list[AgentProduct]) -> dict[str, set[str]]:
    """Tokens frequentes demais dentro de cada kind para servir de sinal."""
    por_kind: dict[str, list[set[str]]] = {}
    for p in products:
        por_kind.setdefault(p.kind or "congresso", []).append(_tokens(p.name))
    comuns: dict[str, set[str]] = {}
    for kind, listas in por_kind.items():
        if len(listas) < 3:   # com 2 produtos não há "frequente demais"
            comuns[kind] = set()
            continue
        contagem: dict[str, int] = {}
        for toks in listas:
            for t in toks:
                contagem[t] = contagem.get(t, 0) + 1
        limite = max(2, int(len(listas) * _LIMITE_COMUM))
        comuns[kind] = {t for t, n in contagem.items() if n >= limite}
    return comuns


def _keywords(p: AgentProduct, comuns: dict[str, set[str]]) -> set[str]:
    kind = p.kind or "congresso"
    return (_tokens(p.name) - comuns.get(kind, set())) | _acronimos(p.name)


def detect_kind_hint(text: str) -> Optional[str]:
    """"pós"/"especialização" → 'pos'; "congresso"/"evento" → 'congresso'.

    Se a pessoa usa as duas palavras (o caso clássico de confusão), não há
    preferência — quem decide é o esclarecimento na conversa.
    """
    hay = _strip(text)
    tem_pos = bool(_RE_POS.search(hay))
    tem_con = bool(_RE_CONGRESSO.search(hay))
    if tem_pos and not tem_con:
        return "pos"
    if tem_con and not tem_pos:
        return "congresso"
    return None


def resolve_route(
    contact: Optional[Contact],
    text: str,
    products: list[AgentProduct],
    campaign_text: str = "",
) -> Rota:
    """Resolve produto + categoria. `campaign_text` é o último disparo enviado
    ao contato: quem responde "quero saber o valor" a uma campanha de promoção
    de pós não tem sinal nenhum no próprio texto, só no que foi disparado."""
    proprio = [text or ""]
    if contact is not None:
        proprio.append(contact.ad_headline or "")
        if contact.ad_payload:
            try:
                proprio.append(json.dumps(contact.ad_payload, ensure_ascii=False))
            except (TypeError, ValueError):
                pass

    hay_proprio = _strip(" ".join(proprio))
    hay_campanha = _strip(campaign_text)
    # O texto do disparo entra na busca do produto, mas com peso menor que o que
    # a pessoa escreveu — ela pode responder a um disparo perguntando de outro curso.
    comuns = _comuns_por_kind(products)

    melhor: Optional[AgentProduct] = None
    melhor_score = 0.0
    empate = False
    for p in products:
        kws = _keywords(p, comuns)
        if not kws:
            continue
        score = sum(1.0 for kw in kws if kw in hay_proprio)
        score += sum(0.5 for kw in kws if kw in hay_campanha)
        if score > melhor_score + 1e-9:
            melhor, melhor_score, empate = p, score, False
        elif abs(score - melhor_score) < 1e-9 and score > 0:
            empate = True

    # O sinal de categoria também vale do disparo: responder a uma campanha de
    # pós entra no contexto de pós mesmo sem a palavra "pós" na resposta.
    hint = detect_kind_hint(text or "")
    if hint is None and contact is not None:
        hint = detect_kind_hint(contact.ad_headline or "")
    if hint is None and campaign_text:
        hint = detect_kind_hint(campaign_text)

    if melhor_score <= 0 or empate:
        # Sem produto definido. Se ao menos a categoria ficou clara e existe um
        # único produto dela, é resposta suficiente (ex.: só há 1 congresso ativo).
        if hint and not empate:
            do_kind = [p for p in products if (p.kind or "congresso") == hint]
            if len(do_kind) == 1:
                return Rota(do_kind[0].slug, hint, False)
        return Rota(None, hint, False)

    kind_prod = melhor.kind or "congresso"
    mismatch = bool(hint and hint != kind_prod)
    return Rota(melhor.slug, hint, mismatch)


def resolve_product_slug(
    contact: Optional[Contact],
    text: str,
    products: list[AgentProduct],
    campaign_text: str = "",
) -> Optional[str]:
    """Compat: só o slug. Prefira `resolve_route`, que traz o sinal de categoria."""
    return resolve_route(contact, text, products, campaign_text).slug
