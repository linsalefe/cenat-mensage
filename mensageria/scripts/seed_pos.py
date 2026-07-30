#!/usr/bin/env python3
"""seed_pos.py — popula/atualiza as pós-graduações em mensageria.agent_products.

Idempotente (upsert por `slug`). Lê **exclusivamente** o JSON produzido por
`scripts/extrair_pos.py` — nenhum preço, data ou carga horária é digitado aqui,
então rodar o extrator de novo e re-semear é a forma de atualizar a base.

Pós ≠ congresso (ver BASE_CONHECIMENTO_POS.md):
- sem `checkout_url` e sem `doity_event_id` → fora do sync e do polling de
  conversão da Doity;
- `tickets` fica `[]` de propósito: o caminho de preço do congresso não pode
  vazar para a pós (o preço da pós vive em `info.investimento`);
- `promo` com validade — a tool filtra vigência de forma determinística.

Decisões do dono do produto aplicadas neste seed (30/07/2026):
1. Certificadora NÃO é semeada (as 13 landings dizem Faculdade de São Marcos,
   mas o briefing mencionava CENSUPEG; pendente de confirmação). O agente não
   fala de certificação enquanto `certificacao_confirmada` for false.
2. `gestao-t5` e `psicologia-hospitalar` ficam SÓ com a parcela — a página não
   publica o total e não vamos multiplicar parcela por prazo.
3. Turma com início já vencido entra com `inicio_confirmado=false`; o prompt
   proíbe anunciar essa data e manda encaminhar ao comercial.
4. `pos-psicologia-raps` não recebe público-alvo (a landing traz o texto da
   Psicologia Escolar) — nem no `info`, nem via FAQ contaminada.

Uso:
    .venv/bin/python scripts/seed_pos.py            # aplica
    .venv/bin/python scripts/seed_pos.py --dry-run  # só mostra o diff
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import sys
from pathlib import Path

from sqlalchemy import select

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from app.database import AsyncSessionLocal  # noqa: E402
from app.models import AgentProduct  # noqa: E402

DADOS = REPO / "scripts" / "data" / "pos_extraido.json"

# Decisão 1: nenhuma certificadora semeada até confirmação.
SEMEAR_CERTIFICACAO = False

# Decisão 4: cursos cujo público-alvo extraído não é confiável.
PUBLICO_BLOQUEADO = {"pos-psicologia-raps"}

# Políticas comuns a todas as pós (BASE_CONHECIMENTO_POS.md).
POLITICAS_POS = {
    "processo_seletivo": (
        "A entrada é por processo seletivo: pré-aplicação no site → agendamento "
        "→ entrevista com a equipe. Não há compra direta."
    ),
    "requisito": (
        "Exigência do MEC: graduação concluída (bacharelado, licenciatura ou "
        "tecnólogo). Não é possível iniciar antes de concluir a graduação."
    ),
    "modalidade": "Online, aulas ao vivo e gravadas na plataforma para rever depois.",
    "tcc": "Sem TCC: a avaliação é por seminários avaliativos ao final de cada módulo.",
    "clube_carreira": (
        "Clube Carreira CENAT: plataforma de divulgação profissional e 50% de "
        "desconto em uma 2ª pós no CENAT."
    ),
    "garantia": (
        "Garantia de satisfação: ao concluir o 1º módulo, é possível cancelar a "
        "matrícula sem multa ou encargos."
    ),
    "imposto_renda": "O valor da pós é dedutível do Imposto de Renda.",
    "contato_comercial": (
        "Funil de pós: processoseletivo@cenatsaudemental.com | "
        "WhatsApp (11) 95213-7432 (https://wa.me/5511952137432)."
    ),
    "papel_do_agente": (
        "O agente INFORMA e DIRECIONA ao comercial. Não vende pós, não gera link "
        "de pagamento e não promete vaga nem condição."
    ),
}


def _parse_br(data: str | None) -> dt.date | None:
    try:
        d, m, a = (data or "").split("/")
        return dt.date(int(a), int(m), int(d))
    except (ValueError, AttributeError):
        return None


def _faq_limpa(curso: dict) -> list[dict]:
    """FAQ da landing, tirando itens contaminados nos cursos bloqueados."""
    faq = curso.get("faq") or []
    if curso["slug"] not in PUBLICO_BLOQUEADO:
        return faq
    sujo = ("escolar", "educacional", "psicopedag")
    return [
        f for f in faq
        if not any(s in (f.get("q", "") + " " + f.get("a", "")).lower() for s in sujo)
    ]


def montar_info(curso: dict) -> dict:
    """Monta o JSONB `info` a partir do registro extraído."""
    inicio = curso.get("inicio_aulas")
    d_inicio = _parse_br(inicio)
    # Decisão 3: início no passado = não confirmado (landing possivelmente velha).
    inicio_confirmado = bool(d_inicio and d_inicio >= dt.date.today())

    duracao = curso.get("duracao")
    duracao_confirmada = bool(duracao) and " ou " not in duracao

    inv = dict(curso.get("investimento") or {})
    inv.pop("texto_investimento", None)  # ruído de extração, não vai pro banco

    publico_ok = curso["slug"] not in PUBLICO_BLOQUEADO
    pub = curso.get("publico") or {}

    info = {
        "turma": curso.get("turma"),
        "inicio_aulas": inicio,
        "inicio_confirmado": inicio_confirmado,
        "carga_horaria": curso.get("carga_horaria"),
        "duracao": duracao,
        "duracao_confirmada": duracao_confirmada,
        "aulas": curso.get("aulas"),
        "certificacao": curso.get("certificacao") if SEMEAR_CERTIFICACAO else None,
        "certificacao_confirmada": SEMEAR_CERTIFICACAO,
        "investimento": inv,
        "publico": pub.get("resumo") if publico_ok else None,
        "perfis": pub.get("perfis") if publico_ok else [],
        "publico_confirmado": publico_ok,
        "modulos": curso.get("modulos") or [],
        "coordenacao": [c["nome"] for c in (curso.get("coordenacao") or [])],
        "docentes": [c["nome"] for c in (curso.get("docentes") or [])],
        "diferenciais": curso.get("diferenciais") or [],
        # Trilha de auditoria: por que um campo está vazio ou marcado como não
        # confirmado. O agente não lê isto; é para revisão humana.
        "avisos_extracao": curso.get("avisos") or [],
        "extraido_em": None,  # preenchido no main com a data do JSON
    }
    return info


def montar_promo(curso: dict) -> dict | None:
    p = curso.get("promo")
    if not p or not p.get("valido_ate"):
        return None
    return {
        "descricao": p.get("descricao"),
        "percentual": p.get("percentual"),
        "valido_de": p.get("valido_de"),      # nenhuma landing publica
        "valido_ate": p.get("valido_ate"),
        "cupom": p.get("cupom"),              # desconto aplicado na página
        "condicao": p.get("condicao"),
    }


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="mostra o que faria, sem gravar")
    ap.add_argument("--dados", type=Path, default=DADOS)
    args = ap.parse_args()

    if not args.dados.exists():
        print(f"[X] {args.dados} não existe — rode scripts/extrair_pos.py primeiro.",
              file=sys.stderr)
        return 1

    payload = json.loads(args.dados.read_text())
    cursos = payload.get("cursos") or []
    if not cursos:
        print("[X] JSON sem cursos.", file=sys.stderr)
        return 1

    print(f"fonte: {args.dados} (gerado em {payload.get('gerado_em')}) — "
          f"{len(cursos)} curso(s)\n")

    inseridos = atualizados = 0
    async with AsyncSessionLocal() as db:
        for curso in cursos:
            slug = curso["slug"]
            if not curso.get("nome"):
                print(f"  PULADO {slug}: sem nome extraído")
                continue

            info = montar_info(curso)
            info["extraido_em"] = payload.get("gerado_em")
            promo = montar_promo(curso)

            prod = (await db.execute(
                select(AgentProduct).where(AgentProduct.slug == slug)
            )).scalar_one_or_none()

            if prod is None:
                prod = AgentProduct(slug=slug)
                db.add(prod)
                acao = "INSERT"
                inseridos += 1
            else:
                if prod.kind == "congresso":
                    print(f"  [X] {slug} já existe como CONGRESSO — não vou "
                          f"sobrescrever. Renomeie o slug.")
                    continue
                acao = "UPDATE"
                atualizados += 1

            prod.name = curso["nome"]
            prod.kind = "pos"
            prod.doity_event_id = None      # pós fica fora do sync/conversão Doity
            prod.checkout_url = None        # entrada por processo seletivo
            prod.landing_url = curso["landing_url"]
            prod.submission_url = None
            prod.event_dates = None         # pós não é evento com data única
            prod.tickets = []               # preço da pós vive em info.investimento
            prod.faq = _faq_limpa(curso)
            prod.schedule = []
            prod.policies = dict(POLITICAS_POS)
            prod.info = info
            prod.promo = promo
            prod.is_active = True

            inv = info["investimento"]
            if inv.get("preco_cheio_cents"):
                preco = f"cheio R$ {inv['preco_cheio_cents']/100:.2f}"
            else:
                preco = f"⚠️ só parcela {inv.get('parcelas')}x R$ {(inv.get('parcela_cents') or 0)/100:.2f}"
            flags = []
            if not info["inicio_confirmado"]:
                flags.append("início NÃO confirmado")
            if not info["publico_confirmado"]:
                flags.append("público vazio")
            if not info["duracao_confirmada"]:
                flags.append("duração ambígua")
            print(f"  {acao} {slug:26} {preco:34} promo→{(promo or {}).get('valido_ate')}"
                  + (f"  [{'; '.join(flags)}]" if flags else ""))

        if args.dry_run:
            await db.rollback()
            print(f"\n--dry-run: nada gravado ({inseridos} insert, {atualizados} update).")
            return 0

        await db.commit()

    print(f"\nseed concluído: {inseridos} insert, {atualizados} update. "
          f"Certificação semeada: {SEMEAR_CERTIFICACAO}.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
