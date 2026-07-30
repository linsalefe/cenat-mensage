#!/usr/bin/env python3
"""checar_promo_pos.py — auditoria do catálogo do agente (pós + congressos).

Determinístico, sem chamar modelo. Responde:

PÓS (kind='pos')
1. quais ainda têm promoção VISÍVEL para o agente na data dada;
2. se, para as vencidas, o payload da tool passou a devolver só o valor sem
   desconto — e se o preço promocional saiu da allowlist do guardrail.

CONGRESSOS (kind='congresso')
3. se algum lote com `active=true` já passou do `lot_deadline`. Esse é o caso da
   virada de lote: a Doity devolve `termino=null`, então o prazo vem do seed e o
   `active` vem do sync — se a Doity não virar o lote (ou o sync falhar), o
   agente segue anunciando o preço de um lote vencido. Também alerta lote ativo
   SEM prazo, que é o mesmo risco sem forma de detectar.

Serve para a revisão mensal que o BASE_CONHECIMENTO_POS.md pede e roda diário
pelo timer `mensageria-promo-check.timer`.

Uso:
    .venv/bin/python scripts/checar_promo_pos.py                  # hoje
    .venv/bin/python scripts/checar_promo_pos.py --data 2026-08-01
    .venv/bin/python scripts/checar_promo_pos.py --esperar-zero   # falha se sobrar promo
    .venv/bin/python scripts/checar_promo_pos.py --so pos         # pos | congresso | tudo

Exit: 0 consistente · 1 achou problema (ou, com --esperar-zero, sobrou promo).
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import sys
from pathlib import Path

from sqlalchemy import select

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from app.database import AsyncSessionLocal  # noqa: E402
from app.models import AgentProduct  # noqa: E402
from app.agent.tools import (  # noqa: E402
    _pos_payload, _promo_vigente, allowed_prices_for,
)

# Lote que vence dentro desse prazo vira aviso (não é erro) — dá tempo de
# conferir a virada com a Doity antes de o preço ficar errado.
DIAS_ALERTA_PREVIO = 3


def _brl(cents: int) -> str:
    return f"R$ {cents // 100}"


# --------------------------------------------------------------------------- #
# PÓS
# --------------------------------------------------------------------------- #
def checar_pos(pos: list[AgentProduct], hoje: dt.date) -> tuple[int, list[str]]:
    """Devolve (promos_visiveis, problemas)."""
    allowed = allowed_prices_for(pos, hoje)
    problemas: list[str] = []
    visiveis = 0

    print(f"## PÓS ({len(pos)} cursos)")
    print(f"Preços de pós permitidos pelo guardrail nesta data: {sorted(allowed)}\n")
    print(f"{'slug':27} {'promo até':12} {'visível':8} {'sem desconto':13} promo p/ o modelo")
    print("-" * 96)

    for p in pos:
        gravada = (p.promo or {}).get("valido_ate") or "—"
        payload = _pos_payload(p, hoje)
        promo = payload.get("promo_vigente")
        inv = payload.get("investimento") or {}
        cheio = inv.get("valor_cheio") or inv.get("parcela_sem_desconto") or "⚠️ nenhum"
        if promo:
            visiveis += 1

        # A tool e o filtro puro têm que concordar.
        if bool(promo) != bool(_promo_vigente(p, hoje)):
            problemas.append(f"POS {p.slug}: tool e filtro de vigência discordam")

        if not promo:
            if inv.get("valor_promocional_a_vista"):
                problemas.append(
                    f"POS {p.slug}: promo vencida mas o investimento ainda traz valor à "
                    f"vista promocional ({inv['valor_promocional_a_vista']})"
                )
            if inv.get("parcelamento"):
                problemas.append(
                    f"POS {p.slug}: promo vencida mas o investimento ainda traz "
                    f"parcelamento promocional ({inv['parcelamento']})"
                )
            if not inv.get("aviso_promo_encerrada"):
                problemas.append(f"POS {p.slug}: promo vencida sem aviso de encerramento")
            if cheio == "⚠️ nenhum":
                problemas.append(
                    f"POS {p.slug}: promo vencida e nenhum valor sem desconto para informar"
                )
            promo_cents = ((p.info or {}).get("investimento") or {}).get("preco_promo_avista_cents")
            if promo_cents and (int(promo_cents) // 100) in allowed:
                problemas.append(
                    f"POS {p.slug}: preço promocional vencido ainda na allowlist do "
                    f"guardrail (R$ {int(promo_cents)//100})"
                )

        print(f"{p.slug:27} {gravada:12} {('SIM' if promo else 'não'):8} "
              f"{cheio:13} {(promo or {}).get('descricao') or '—'}")

    print(f"\nPromoções visíveis para o agente em {hoje.isoformat()}: {visiveis}/{len(pos)}")
    return visiveis, problemas


# --------------------------------------------------------------------------- #
# CONGRESSOS
# --------------------------------------------------------------------------- #
def checar_congressos(congs: list[AgentProduct], hoje: dt.date) -> list[str]:
    problemas: list[str] = []
    avisos: list[str] = []

    print(f"\n## CONGRESSOS ({len(congs)} eventos)")
    print(f"{'slug':17} {'lote':24} {'preço':9} {'prazo':12} {'ativo':6} situação")
    print("-" * 96)

    for p in congs:
        tickets = p.tickets or []
        if not tickets:
            avisos.append(f"CONGRESSO {p.slug}: sem nenhum lote na base")
        ativos = 0
        for t in tickets:
            ativo = bool(t.get("active", True))
            prazo_raw = t.get("lot_deadline")
            cents = t.get("price_cents")
            preco = _brl(int(cents)) if cents is not None else "—"
            lote = str(t.get("lot_name") or t.get("tier") or "?")[:24]

            prazo = None
            if prazo_raw:
                try:
                    prazo = dt.date.fromisoformat(str(prazo_raw))
                except ValueError:
                    problemas.append(
                        f"CONGRESSO {p.slug}: lote '{lote}' com prazo ilegível ({prazo_raw!r})"
                    )

            if ativo:
                ativos += 1

            situacao = "—"
            if ativo and prazo is not None:
                dias = (prazo - hoje).days
                if dias < 0:
                    situacao = f"❌ VENCIDO há {-dias}d, mas active=true"
                    problemas.append(
                        f"CONGRESSO {p.slug}: lote '{lote}' ({preco}) venceu em "
                        f"{prazo.isoformat()} (há {-dias} dia(s)) e segue active=true — "
                        f"o agente ainda anuncia esse preço. Conferir a virada de lote na "
                        f"Doity (lote_id={t.get('doity_lote_id')})."
                    )
                elif dias <= DIAS_ALERTA_PREVIO:
                    situacao = f"⚠️ vence em {dias}d"
                    avisos.append(
                        f"CONGRESSO {p.slug}: lote '{lote}' vence em {dias} dia(s) "
                        f"({prazo.isoformat()}) — acompanhar a virada."
                    )
                else:
                    situacao = f"ok, {dias}d"
            elif ativo and prazo is None:
                situacao = "❌ ativo SEM prazo"
                problemas.append(
                    f"CONGRESSO {p.slug}: lote '{lote}' ({preco}) está active=true sem "
                    f"lot_deadline — não há como saber se já virou. O sync da Doity não "
                    f"preenche prazo (termino=null); tem que vir do seed."
                )
            elif not ativo:
                situacao = "inativo (não ofertado)"

            print(f"{p.slug:17} {lote:24} {preco:9} "
                  f"{(prazo.isoformat() if prazo else '—'):12} "
                  f"{('sim' if ativo else 'não'):6} {situacao}")

        if tickets and ativos == 0:
            avisos.append(
                f"CONGRESSO {p.slug}: nenhum lote ativo — o agente não tem preço para "
                f"informar deste congresso."
            )
        if p.synced_from_doity_at:
            idade = (dt.datetime.now(dt.timezone.utc) - p.synced_from_doity_at).total_seconds() / 3600
            if idade > 6:
                avisos.append(
                    f"CONGRESSO {p.slug}: último sync com a Doity há {idade:.1f}h "
                    f"(worker roda a cada 30min) — sync possivelmente parado."
                )
        else:
            avisos.append(f"CONGRESSO {p.slug}: nunca sincronizou com a Doity.")

    if avisos:
        print(f"\nAvisos (não falham a checagem): {len(avisos)}")
        for a in avisos:
            print(f"  · {a}")

    return problemas


# --------------------------------------------------------------------------- #
async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", type=str, default=None,
                    help="data a simular (YYYY-MM-DD); default = hoje")
    ap.add_argument("--esperar-zero", action="store_true",
                    help="exit 1 se ainda houver promoção de pós visível")
    ap.add_argument("--so", choices=("pos", "congresso", "tudo"), default="tudo",
                    help="restringe a checagem")
    args = ap.parse_args()

    hoje = dt.date.fromisoformat(args.data) if args.data else dt.date.today()
    rotulo = hoje.isoformat() + (" (simulada)" if args.data else " (hoje)")

    async with AsyncSessionLocal() as db:
        prods = list((await db.execute(
            select(AgentProduct)
            .where(AgentProduct.is_active.is_(True))
            .order_by(AgentProduct.kind, AgentProduct.slug)
        )).scalars().all())

    pos = [p for p in prods if p.kind == "pos"]
    congs = [p for p in prods if p.kind != "pos"]

    print(f"Data de referência: {rotulo}")
    print(f"Catálogo ativo: {len(prods)} produtos ({len(pos)} pós, {len(congs)} congressos)\n")

    if not prods:
        print("[X] catálogo vazio em agent_products.", file=sys.stderr)
        return 1

    problemas: list[str] = []
    visiveis = 0

    if args.so in ("pos", "tudo"):
        if pos:
            visiveis, probs = checar_pos(pos, hoje)
            problemas += probs
        else:
            print("## PÓS — nenhuma pós ativa no catálogo")

    if args.so in ("congresso", "tudo"):
        if congs:
            problemas += checar_congressos(congs, hoje)
        else:
            print("\n## CONGRESSOS — nenhum congresso ativo no catálogo")

    print("\n" + "=" * 96)
    if problemas:
        print(f"❌ {len(problemas)} problema(s):")
        for pr in problemas:
            print(f"  - {pr}")
        return 1

    if args.esperar_zero and visiveis:
        print(f"❌ esperava 0 promoções de pós visíveis, achei {visiveis}.")
        return 1

    print("✅ Consistente: promoções de pós e prazos de lote coerentes com a base.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
