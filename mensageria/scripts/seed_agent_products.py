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

# Políticas PADRÃO. Cada produto pode sobrescrever qualquer chave via
# `policies_extra` — Curitiba é presencial, tem carga e horário próprios.
POLICIES = {
    "certificado": "Certificado de 30h, emitido pelo CENAT.",
    "pagamento": "Pix, boleto ou cartão de crédito em até 12x (com juros).",
    "reembolso": "Reembolso em até 7 dias úteis via atendimento@cenatcursos.com.br.",
    "horario": "8h20 às 18h30 (horário de Brasília).",
    "estudante": "O valor de estudante exige envio de comprovante de matrícula/vínculo com instituição de ensino.",
    # MODALIDADE é dado de primeira classe: muda o produto (quem é de fora
    # precisa viajar e se hospedar) e é a primeira coisa que o agente tem que
    # deixar clara. Valores: "online" | "presencial".
    "modalidade": "online",
}

# As 11 oficinas do dia 29/08 em Curitiba vêm dos lotes de valor 0 da Doity
# (evento 287503) — dado da fonte, não transcrito à mão.
OFICINAS_CURITIBA_IDS = (838974, 838978, 838980, 838982, 838983, 838984,
                         838986, 838987, 838988, 839029, 839030)

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
    {
        # ÚNICO PRESENCIAL da base. Difere dos outros dois em carga horária
        # (36h), horário (8h-18h20), local físico e submissão já encerrada.
        "slug": "curitiba-dh-2026",
        "name": ("VII Congresso Internacional: Saúde Mental e Direitos Humanos "
                 "das Populações Vulnerabilizadas — Curitiba/PR"),
        "doity_event_id": 287503,
        "event_dates": "27, 28 e 29/08/2026",
        "checkout_url": ("https://doity.com.br/vii-congresso-internacional-saude-mental-"
                         "e-direitos-humanos-das-populacoes-vulnerabilizadas-curitiba"),
        "landing_url": ("https://cenatsaudemental.com/"
                        "vii-congresso-saude-mental-direitos-humanos-curitiba"),
        "submission_url": None,
        "lot_deadline": "2026-07-31",   # 3º lote até 31/07/2026
        # Só o 3º lote está em vigor. A Doity devolve as 3 gerações como
        # `ativo=true` — sem esta lista, R$170 (1º lote) entraria na base e,
        # por tabela, na allowlist de preços do guardrail.
        "lotes_ativos": {859005, 859006, 838924},
        "combo_desc": (
            "Combo congresso + curso online 'Respondendo aos Sentimentos Suicidas' (20h), "
            "apostila e consultoria de carreira de 30 minutos."
        ),
        "submission_window": None,   # ENCERRADA — ver policies_extra
        "policies_extra": {
            "modalidade": "presencial",
            "local": ("Teatro da Reitoria - UFPR, Rua XV de Novembro 1299, "
                      "Centro, Curitiba/PR."),
            "horario": "8h às 18h20.",
            "certificado": "Certificado de 36h presencial, emitido pelo CENAT.",
            "submissao": (
                "ENCERRADA em 22/07/2026. NÃO há exceção nem prazo estendido — "
                "não prometa reabertura. A inscrição de PARTICIPANTE segue aberta."
            ),
            "oficinas": (
                "As oficinas acontecem no dia 29/08, têm vagas limitadas e são "
                "escolhidas no ato da inscrição. Se esgotarem, não reabrem."
            ),
            # A redação anterior ("Há tradução consecutiva para os palestrantes
            # internacionais") fez o agente responder "sim, há tradução" a uma
            # pergunta sobre LIBRAS e intérprete. São coisas distintas: idioma
            # estrangeiro não é acessibilidade para pessoa surda, e prometer
            # acessibilidade que não se confirmou é o pior tipo de promessa.
            "traducao": (
                "Há tradução consecutiva de IDIOMA para as falas dos palestrantes "
                "internacionais. Isto NÃO diz nada sobre Libras, intérprete de Libras, "
                "legendagem ou qualquer outro recurso de acessibilidade: sobre esses a "
                "base NÃO tem informação — não afirme que existem nem que não existem, "
                "diga que vai confirmar com a equipe."
            ),
            "coffee_break": "NÃO há coffee break. São servidos apenas água e café.",
            "empenho": ("Empenho para pessoa jurídica: solicite por "
                        "atendimento@cenatcursos.com.br."),
            "hospedagem": (
                "Hotel parceiro: Slim Curitiba Alto da XV (rede Slaviero). 20% de "
                "desconto com o código CENAT26, reservando pelo site oficial do hotel, "
                "válido de 26 a 30/08. Café da manhã incluso, ISS de 5%, "
                "estacionamento R$ 35/dia. ATENÇÃO: CENAT26 é desconto de HOTEL — "
                "NÃO é desconto na inscrição do congresso."
            ),
        },
        "faq": [
            {"q": "Qual é a data do congresso?",
             "a": "27, 28 e 29 de agosto de 2026, PRESENCIAL em Curitiba/PR, das 8h às 18h20."},
            {"q": "É online ou presencial?",
             "a": ("É PRESENCIAL, no Teatro da Reitoria da UFPR (Rua XV de Novembro 1299, "
                   "Centro, Curitiba/PR). Não há transmissão online deste congresso.")},
            {"q": "O certificado tem quantas horas?",
             "a": "36 horas presenciais, emitido pelo CENAT."},
            {"q": "Como funciona o valor de estudante?",
             "a": ("É necessário apresentar carteira de estudante na inscrição E também "
                   "no dia do evento.")},
            {"q": "Posso submeter trabalho?",
             "a": ("A submissão de trabalhos ENCERROU em 22/07/2026 e não haverá "
                   "prorrogação. A inscrição como participante continua aberta.")},
            {"q": "Onde posso me hospedar?",
             "a": ("O hotel parceiro é o Slim Curitiba Alto da XV (rede Slaviero), com 20% "
                   "de desconto pelo código CENAT26 reservando no site oficial do hotel, "
                   "válido de 26 a 30/08. Inclui café da manhã; ISS 5% e estacionamento "
                   "R$ 35/dia à parte. O CENAT26 vale só para a hospedagem.")},
            {"q": "Tem coffee break?",
             "a": "Não há coffee break. São servidos apenas água e café."},
            {"q": "As palestras internacionais têm tradução?",
             "a": "Sim, há tradução consecutiva para os palestrantes internacionais."},
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


def get_lotes(event_id: int) -> list[dict]:
    r = httpx.get(
        f"{DOITY_BASE}/eventos/{event_id}/lotes",
        headers={"Accept": "application/json", "Authorization": f"Bearer {DOITY_TOKEN}"},
        params={"limit": 50},
        timeout=40,
    )
    r.raise_for_status()
    return r.json().get("lotes", []) or []


def fetch_tickets(lotes: list[dict], lot_deadline: str,
                  lotes_ativos: set[int] | None) -> list[dict]:
    """Monta tickets a partir dos lotes da Doity.

    Descarta lote sem `valor` (cupom/promo) e lote de valor ZERO (oficina
    gratuita, lote privado de organizador) — como ticket, esses viram "tier
    outro por R$ 0,00" e o agente pode oferecê-los como se fossem ingresso.

    `lotes_ativos` decide o que está EM VIGOR. O campo `ativo` da Doity quer
    dizer "não desabilitado", não "à venda hoje": em Curitiba as três gerações
    de lote voltam `ativo=true` juntas, e confiar nisso colocaria R$ 170 (1º
    lote) na base — e portanto na allowlist de preços do guardrail. `None`
    mantém o comportamento antigo (todos ativos), que é correto para os
    congressos que só têm uma geração de lote.
    """
    tickets = []
    for lo in lotes:
        valor = lo.get("valor")
        if valor is None or float(valor) == 0:
            continue
        lid = lo.get("id")
        ativo = bool(lo.get("ativo")) if lotes_ativos is None else (lid in lotes_ativos)
        tickets.append({
            "tier": _tier_from_name(lo.get("nome")),
            "lot_name": lo.get("nome"),
            "price_cents": int(round(float(valor) * 100)),
            # prazo só faz sentido para o lote em vigor
            "lot_deadline": lot_deadline if ativo else None,
            "doity_lote_id": lid,
            "active": ativo,
        })
    return tickets


def fetch_oficinas(lotes: list[dict], ids: tuple[int, ...]) -> list[str]:
    """Nomes das oficinas, lidos dos lotes de valor 0 — fonte, não transcrição."""
    por_id = {lo.get("id"): lo for lo in lotes}
    return [str(por_id[i].get("nome")).strip() for i in ids if i in por_id]


async def main() -> None:
    if not DOITY_TOKEN:
        print("[X] DOITY_TOKEN ausente no .env — não dá pra puxar os lotes.")
        sys.exit(1)

    async with AsyncSessionLocal() as db:
        for p in PRODUCTS:
            lotes = get_lotes(p["doity_event_id"])
            tickets = fetch_tickets(lotes, p["lot_deadline"], p.get("lotes_ativos"))
            policies = dict(POLICIES)
            policies["combo"] = p["combo_desc"]
            if p.get("submission_window"):
                policies["submissao"] = p["submission_window"]
            # sobrescritas do produto por último: Curitiba muda modalidade,
            # horário, certificado e o texto de submissão.
            policies.update(p.get("policies_extra") or {})
            if p["slug"] == "curitiba-dh-2026":
                oficinas = fetch_oficinas(lotes, OFICINAS_CURITIBA_IDS)
                if oficinas:
                    policies["oficinas_disponiveis"] = oficinas

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

            ativos = [t for t in tickets if t["active"]]
            print(f"{action} {p['slug']} [{policies['modalidade']}]: "
                  f"{len(ativos)}/{len(tickets)} lote(s) em vigor — "
                  + ", ".join(f"{t['tier']}=R${t['price_cents']/100:.0f}" for t in ativos))
            inativos = [t for t in tickets if not t["active"]]
            if inativos:
                print("    fora de vigência (não citáveis): "
                      + ", ".join(f"{t['lot_name']}=R${t['price_cents']/100:.0f}"
                                  for t in inativos))

        await db.commit()
    print("seed concluído.")


if __name__ == "__main__":
    asyncio.run(main())
