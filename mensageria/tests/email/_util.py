"""Utilitário mínimo dos testes de e-mail (sem pytest, mesma convenção de tests/agent)."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

_falhas: list[str] = []
_total = 0


def check(cond: bool, nome: str) -> None:
    global _total
    _total += 1
    if cond:
        print(f"  ✔ {nome}")
    else:
        print(f"  ✘ {nome}")
        _falhas.append(nome)


def fim() -> None:
    print(f"\n{_total - len(_falhas)}/{_total} checagens passaram")
    if _falhas:
        for f in _falhas:
            print(f"   ✘ {f}")
        sys.exit(1)
    sys.exit(0)
