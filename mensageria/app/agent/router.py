"""Roteamento de produto: descobre qual congresso é o foco da conversa a partir
do anúncio (CTWA), do texto inicial (wa.me) e de palavras-chave (§3.5)."""
from __future__ import annotations

import json
import re
import unicodedata
from typing import Optional

from app.models import AgentProduct, Contact

_STOP = {
    "congresso", "online", "internacional", "nacional", "de", "do", "da", "e", "em",
    "boas", "praticas", "para", "com", "sobre", "cenat", "curso", "edicao",
    "i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "2025", "2026", "2027",
}


def _strip(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower()


def _keywords(p: AgentProduct) -> set[str]:
    kws: set[str] = set()
    for tok in re.split(r"[^a-z0-9]+", _strip(p.name)):
        if tok and tok not in _STOP and len(tok) >= 4:
            kws.add(tok)
    # radicais úteis (gênero -> gener; vozes -> voz)
    for extra in list(kws):
        if extra.endswith("s") and len(extra) > 4:
            kws.add(extra[:-1])
    return kws


def resolve_product_slug(
    contact: Optional[Contact], text: str, products: list[AgentProduct]
) -> Optional[str]:
    parts = [text or ""]
    if contact is not None:
        parts.append(contact.ad_headline or "")
        if contact.ad_payload:
            try:
                parts.append(json.dumps(contact.ad_payload, ensure_ascii=False))
            except Exception:
                pass
    hay = _strip(" ".join(parts))

    best_slug: Optional[str] = None
    best_score = 0
    tie = False
    for p in products:
        score = sum(1 for kw in _keywords(p) if kw in hay)
        if score > best_score:
            best_score, best_slug, tie = score, p.slug, False
        elif score == best_score and score > 0:
            tie = True
    if best_score == 0 or tie:
        return None  # ambíguo ou sem sinal → o agente pergunta
    return best_slug
