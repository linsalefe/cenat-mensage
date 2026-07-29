#!/usr/bin/env python3
"""seed_agent_products.py — popula/atualiza mensageria.agent_products (Fase 0).

Idempotente (upsert por slug). Os TICKETS são puxados AO VIVO da Doity
(`/eventos/{id}/lotes`), filtrando lotes sem `valor` (ex.: CENATPROMO). Datas do
evento, prazos de lote, políticas e FAQ vêm dos fatos do PLANO_AGENTE.md — a API
de detalhe `/eventos/{id}` não responde para este token e os lotes vêm com
`termino.data=null`, então o prazo do 1º lote precisa ser informado aqui.

Uso:
    /home/ubuntu/mensageria/.venv/bin/python scripts/seed_agent_products.py
Requer DOITY_TOKEN/DOITY_BASE_URL no .env do repo (a app ignora essas chaves,
então lemos o .env diretamente aqui).
"""
import asyncio
import os
import sys
from pathlib import Path

import httpx
from sqlalchemy import select

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from app.database import AsyncSessionLocal  # noqa: E402
from app.models import AgentProduct  # noqa: E402


def _load_env(path: Path) -> dict:
    out = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k] = v
    return out


ENV = _load_env(REPO / ".env")
DOITY_TOKEN = os.getenv("DOITY_TOKEN") or ENV.get("DOITY_TOKEN", "")
DOITY_BASE = (os.getenv("DOITY_BASE_URL") or ENV.get("DOITY_BASE_URL")
              or "https://api.doity.com.br/public/v1").rstrip("/")

# Políticas compartilhadas pelos dois congressos (PLANO_AGENTE.md §0).
POLICIES = {
    "certificado": "Certificado de 30h, emitido pelo CENAT.",
    "pagamento": "Pix, boleto ou cartão de crédito em até 12x (com juros).",
    "reembolso": "Reembolso em até 7 dias úteis via atendimento@cenatcursos.com.br.",
    "horario": "8h20 às 18h30 (horário de Brasília).",
    "estudante": "O valor de estudante exige envio de comprovante de matrícula/vínculo com instituição de ensino.",
}

# Definição dos produtos. `tickets` é preenchido ao vivo da Doity; os demais
# campos são os fatos oficiais do plano/landing.
PRODUCTS = [
    {
        "slug": "genero-2026",
        "name": "I Congresso Online Internacional: Boas Práticas em Gêneros e Sexualidades",
        "doity_event_id": 296038,
        "event_dates": "13 e 14/11/2026",
        "checkout_url": "https://doity.com.br/i-congresso-online-internacional-boas-praticas-em-generos-e-sexualidades",
        "landing_url": "https://doity.com.br/i-congresso-online-internacional-boas-praticas-em-generos-e-sexualidades",
        "submission_url": None,
        "lot_deadline": "2026-07-31",   # 1º lote até 31/07/2026
        "combo_desc": "Combo congresso + curso de 12h de Gênero e Sexualidades.",
        "submission_window": "01/07 a 30/09/2026",
        "faq": [
            {"q": "Qual é a data do congresso?", "a": "13 e 14 de novembro de 2026, online, das 8h20 às 18h30 (horário de Brasília)."},
            {"q": "O certificado tem quantas horas?", "a": "30 horas, emitido pelo CENAT."},
            {"q": "Como funciona o valor de estudante?", "a": "É necessário enviar comprovante de matrícula/vínculo com instituição de ensino."},
            {"q": "Posso submeter trabalho?", "a": "Sim, a submissão vai de 01/07 a 30/09/2026."},
        ],
    },
    {
        "slug": "ouvidores-2026",
        "name": "VI Congresso Online Internacional: Ouvidores de Vozes",
        "doity_event_id": 296665,
        "event_dates": "04 e 05/12/2026",
        "checkout_url": "https://doity.com.br/vi-congresso-online-internacional-ouvidores-de-vozes-2026",
        "landing_url": "https://doity.com.br/vi-congresso-online-internacional-ouvidores-de-vozes-2026",
        "submission_url": None,
        "lot_deadline": "2026-08-31",   # 1º lote até 31/08/2026
        "combo_desc": "Combo congresso + curso de 30h Trabalhando com Pessoas que Ouvem Vozes.",
        "submission_window": "16/07 a 30/09/2026",
        "faq": [
            {"q": "Qual é a data do congresso?", "a": "04 e 05 de dezembro de 2026, online, das 8h20 às 18h30 (horário de Brasília)."},
            {"q": "O certificado tem quantas horas?", "a": "30 horas, emitido pelo CENAT."},
            {"q": "Como funciona o valor de estudante?", "a": "É necessário enviar comprovante de matrícula/vínculo com instituição de ensino."},
            {"q": "Posso submeter trabalho?", "a": "Sim, a submissão vai de 16/07 a 30/09/2026."},
        ],
    },
]


def _tier_from_name(nome: str) -> str:
    n = (nome or "").lower()
    if "estudante" in n:
        return "estudante"
    if "profissional" in n:
        return "profissional"
    if "combo" in n:
        return "combo"
    return "outro"


def fetch_tickets(event_id: int, lot_deadline: str) -> list[dict]:
    """Puxa lotes da Doity e monta tickets. Filtra lotes sem `valor` (promo/cupom)."""
    url = f"{DOITY_BASE}/eventos/{event_id}/lotes"
    r = httpx.get(
        url,
        headers={"Accept": "application/json", "Authorization": f"Bearer {DOITY_TOKEN}"},
        params={"limit": 50},
        timeout=40,
    )
    r.raise_for_status()
    lotes = r.json().get("lotes", []) or []
    tickets = []
    for lo in lotes:
        valor = lo.get("valor")
        if valor is None:
            continue  # CENATPROMO etc. — sem preço listável
        tickets.append({
            "tier": _tier_from_name(lo.get("nome")),
            "lot_name": lo.get("nome"),
            "price_cents": int(round(float(valor) * 100)),
            "lot_deadline": lot_deadline,   # a API traz termino=null → vem do plano
            "doity_lote_id": lo.get("id"),
            "active": bool(lo.get("ativo")),
        })
    return tickets


async def main() -> None:
    if not DOITY_TOKEN:
        print("[X] DOITY_TOKEN ausente no .env — não dá pra puxar os lotes.")
        sys.exit(1)

    async with AsyncSessionLocal() as db:
        for p in PRODUCTS:
            tickets = fetch_tickets(p["doity_event_id"], p["lot_deadline"])
            policies = dict(POLICIES)
            policies["combo"] = p["combo_desc"]
            policies["submissao"] = p["submission_window"]

            res = await db.execute(
                select(AgentProduct).where(AgentProduct.slug == p["slug"])
            )
            prod = res.scalar_one_or_none()
            if prod is None:
                prod = AgentProduct(slug=p["slug"])
                db.add(prod)
                action = "INSERT"
            else:
                action = "UPDATE"

            prod.name = p["name"]
            prod.doity_event_id = p["doity_event_id"]
            prod.event_dates = p["event_dates"]
            prod.checkout_url = p["checkout_url"]
            prod.landing_url = p["landing_url"]
            prod.submission_url = p["submission_url"]
            prod.faq = p["faq"]
            prod.tickets = tickets
            prod.policies = policies
            prod.is_active = True
            # schedule fica [] por ora — programação detalhada entra depois.

            print(f"{action} {p['slug']}: {len(tickets)} tickets "
                  + ", ".join(f"{t['tier']}=R${t['price_cents']/100:.0f}" for t in tickets))

        await db.commit()
    print("seed concluído.")


if __name__ == "__main__":
    asyncio.run(main())
