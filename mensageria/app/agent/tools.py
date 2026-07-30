"""Tools do agente. Fase 1 = somente leitura sobre agent_products (fonte da
verdade de preços/lotes/links). Fase 2 adiciona tools de escrita (ver tools_write).

Formato de tool = Responses API "function" (flat): {type, name, description,
parameters, strict}. `execute_tool` despacha pelo nome e retorna dict serializável.

Congresso vs pós (`agent_products.kind`): a pós não tem lote nem checkout, e o
que o agente pode dizer dela sai de `info`/`promo`. Dois filtros aqui são
DETERMINÍSTICOS de propósito — o modelo nunca vê o dado, então não tem como
vazá-lo:
- promoção vencida (`promo.valido_ate` < hoje) não é devolvida;
- campo marcado como não confirmado (início de turma de landing velha,
  certificadora, público-alvo copiado da landing errada) não é devolvido.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentProduct

# Funil de pós (BASE_CONHECIMENTO_POS.md). O link exato do WhatsApp é a única
# exceção da allowlist de links do guardrail.
POS_WHATSAPP = "(11) 95213-7432"
POS_WHATSAPP_LINK = "https://wa.me/5511952137432"
POS_EMAIL = "processoseletivo@cenatsaudemental.com"


@dataclass
class ToolContext:
    db: AsyncSession
    contact_wa_id: str
    channel_id: Optional[int] = None
    session_id: Optional[int] = None


def _fmt_price(cents: int) -> str:
    """Formata em pt-BR. Acima de mil usa separador de milhar ("R$ 6.800,00"),
    senão fica curto como antes ("R$ 90", "R$ 255,00") — os valores de congresso
    são de 2–3 dígitos e ficavam estranhos com centavos à toa."""
    if cents >= 100_000:
        s = f"{cents / 100:,.2f}"          # 6,800.00
        return "R$ " + s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    if cents % 100 == 0:
        return f"R$ {cents // 100}"
    return f"R$ {cents / 100:.2f}".replace(".", ",")


def _active_tickets(prod: AgentProduct) -> list[dict]:
    out = []
    for t in (prod.tickets or []):
        if not t.get("active", True):
            continue
        cents = t.get("price_cents")
        if cents is None:
            continue  # lote sem preço (promo/cupom) não é ofertado
        out.append({
            "tier": t.get("tier"),
            "lote": t.get("lot_name"),
            "preco": _fmt_price(int(cents)),
            "preco_cents": int(cents),
            "prazo_lote": t.get("lot_deadline"),
        })
    return out


def _promo_vigente(prod: AgentProduct, hoje: Optional[dt.date] = None) -> Optional[dict]:
    """Promoção do produto SÓ se vigente hoje. Filtro determinístico: promo
    vencida (ou sem prazo) é invisível para o modelo.

    Sem `valido_ate` não há como afirmar vigência → tratamos como não vigente.
    """
    promo = prod.promo or None
    if not promo:
        return None
    hoje = hoje or dt.date.today()
    try:
        ate = dt.date.fromisoformat(str(promo.get("valido_ate")))
    except (TypeError, ValueError):
        return None
    if ate < hoje:
        return None
    de = promo.get("valido_de")
    if de:
        try:
            if dt.date.fromisoformat(str(de)) > hoje:
                return None  # promo futura, ainda não começou
        except (TypeError, ValueError):
            pass
    return {
        "descricao": promo.get("descricao"),
        "valido_ate": promo.get("valido_ate"),
        "cupom": promo.get("cupom"),
        "condicao": promo.get("condicao"),
    }


def _investimento_pos(info: dict, promo_vigente: bool) -> dict:
    """Formata o investimento da pós para o modelo, já em texto pronto.

    Dois cortes, ambos determinísticos:

    - Quando a landing só publica a parcela (`base == "por_parcela"`), NÃO existe
      valor total nem à vista — devolver isso vazio é o que impede o modelo de
      multiplicar parcela por prazo e inventar o total.
    - `preco_promo_avista_cents` e `parcela_cents` SÃO os valores com o desconto
      já aplicado (é assim que as landings anunciam). Se a promoção não está mais
      vigente, eles não podem sair daqui: senão a promo "desaparece" do bloco de
      promoção mas o preço promocional continua sendo informado — que é
      exatamente o vazamento que o filtro de vigência existe para impedir.
      `parcela_cheia_cents` (a parcela SEM desconto) segue valendo sempre.
    """
    inv = info.get("investimento") or {}
    out: dict[str, Any] = {"base": inv.get("base")}
    parcelas = inv.get("parcelas")
    if inv.get("preco_cheio_cents"):
        out["valor_cheio"] = _fmt_price(int(inv["preco_cheio_cents"]))
    if promo_vigente:
        if inv.get("preco_promo_avista_cents"):
            out["valor_promocional_a_vista"] = _fmt_price(int(inv["preco_promo_avista_cents"]))
        if parcelas and inv.get("parcela_cents"):
            out["parcelamento"] = f"{parcelas}x de {_fmt_price(int(inv['parcela_cents']))}"
    if inv.get("parcela_cheia_cents"):
        out["parcela_sem_desconto"] = _fmt_price(int(inv["parcela_cheia_cents"]))
    if not promo_vigente:
        out["aviso_promo_encerrada"] = (
            "A promoção anterior ENCERROU. Informe só o valor sem desconto e "
            "encaminhe ao comercial para as condições de pagamento e parcelamento "
            "atuais. NÃO cite valores promocionais nem parcelas antigas."
        )
    if inv.get("base") == "por_parcela":
        out["aviso"] = (
            "Esta página anuncia SÓ o valor por parcela. Não existe valor total "
            "nem à vista na base: não some nem multiplique parcelas. Se a pessoa "
            "quiser o total, encaminhe ao comercial."
        )
    return out


def _pos_payload(prod: AgentProduct, hoje: Optional[dt.date] = None) -> dict:
    """Dados de UMA pós, já filtrados pelo que pode ser afirmado.

    `hoje` existe para poder auditar a virada de vigência da promo numa data
    escolhida (ver `scripts/checar_promo_pos.py`); em produção fica None e vale
    a data real.
    """
    info = prod.info or {}
    promo = _promo_vigente(prod, hoje)
    out: dict[str, Any] = {
        "slug": prod.slug,
        "name": prod.name,
        "kind": "pos",
        "landing_url": prod.landing_url,
        "modalidade": "Online, aulas ao vivo e gravadas na plataforma.",
        "carga_horaria": info.get("carga_horaria"),
        "aulas": info.get("aulas"),
        "turma": info.get("turma"),
        "investimento": _investimento_pos(info, promo is not None),
        "promo_vigente": promo,
        "modulos": info.get("modulos") or [],
        "coordenacao": info.get("coordenacao") or [],
        "diferenciais": info.get("diferenciais") or [],
        "como_ingressar": (prod.policies or {}).get("processo_seletivo"),
        "requisito": (prod.policies or {}).get("requisito"),
        "contato_comercial": {
            "whatsapp": POS_WHATSAPP,
            "whatsapp_link": POS_WHATSAPP_LINK,
            "email": POS_EMAIL,
        },
        "politicas": prod.policies or {},
    }

    # Campos sob confirmação: ausentes + motivo, para o modelo não afirmar.
    if info.get("inicio_confirmado"):
        out["inicio_aulas"] = info.get("inicio_aulas")
    else:
        out["inicio_aulas"] = None
        out["inicio_aulas_indisponivel"] = (
            "A data de início desta turma está em confirmação. NÃO informe data "
            "de início — diga que confirma com a equipe e encaminhe ao comercial."
        )
    if info.get("duracao_confirmada"):
        out["duracao"] = info.get("duracao")
    else:
        out["duracao"] = None
        out["duracao_indisponivel"] = "Duração em confirmação — não afirme."
    if info.get("certificacao_confirmada"):
        out["certificacao"] = info.get("certificacao")
    else:
        out["certificacao"] = None
        out["certificacao_indisponivel"] = (
            "A instituição certificadora está em confirmação. Pode dizer que a "
            "pós é reconhecida pelo MEC e dá título de especialista (lato sensu), "
            "mas NÃO cite o nome da faculdade nem número de portaria."
        )
    if info.get("publico_confirmado"):
        out["publico"] = info.get("publico")
        out["perfis"] = info.get("perfis") or []
    else:
        out["publico"] = None
        out["publico_indisponivel"] = (
            "O público-alvo desta pós está em confirmação — não liste perfis; "
            "se perguntarem, encaminhe ao comercial."
        )
    return out


def allowed_prices_for(
    products: list[AgentProduct], hoje: Optional[dt.date] = None
) -> set[int]:
    """Conjunto de valores (em reais inteiros) que o agente pode citar.

    Congresso: preço de lote ativo. Pós: valor cheio e parcela sem desconto
    sempre; valor promocional à vista e parcela promocional SÓ enquanto a
    promoção estiver vigente — o guardrail tem que refletir o que é dizível
    agora, senão ele não pegaria o modelo repetindo um preço promocional vencido
    a partir do histórico da conversa.
    """
    allowed: set[int] = set()
    for p in products:
        for t in (p.tickets or []):
            if t.get("active") and t.get("price_cents") is not None:
                allowed.add(int(t["price_cents"]) // 100)
        inv = ((p.info or {}).get("investimento") or {})
        chaves = ["preco_cheio_cents", "parcela_cheia_cents"]
        if _promo_vigente(p, hoje) is not None:
            chaves += ["preco_promo_avista_cents", "parcela_cents"]
        for key in chaves:
            cents = inv.get(key)
            if cents:
                allowed.add(int(cents) // 100)
    return allowed


async def _load(db: AsyncSession, slug: str) -> Optional[AgentProduct]:
    res = await db.execute(
        select(AgentProduct).where(AgentProduct.slug == slug, AgentProduct.is_active.is_(True))
    )
    return res.scalar_one_or_none()


async def _load_all(db: AsyncSession) -> list[AgentProduct]:
    res = await db.execute(
        select(AgentProduct).where(AgentProduct.is_active.is_(True)).order_by(AgentProduct.slug)
    )
    return list(res.scalars().all())


def build_read_tool_schemas(slugs: list[str]) -> list[dict]:
    slug_schema = {"type": "string", "description": "slug do congresso ou da pós-graduação"}
    if slugs:
        slug_schema["enum"] = slugs
    return [
        {
            "type": "function",
            "name": "list_products",
            "description": "Lista o que o CENAT oferece: congressos (kind=congresso) e pós-graduações (kind=pos), com nome e slug. Use quando não souber o que a pessoa quer, ou para checar se um tema é congresso ou pós.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
            "strict": True,
        },
        {
            "type": "function",
            "name": "get_product_info",
            "description": (
                "Retorna os dados oficiais de UM produto. Chame SEMPRE antes de citar qualquer valor, data ou link. "
                "Congresso (kind=congresso): preços dos lotes ativos, prazo do lote, link de checkout e políticas. "
                "Pós (kind=pos): carga horária, dia/horário das aulas, início, investimento, promoção vigente, "
                "módulos, coordenação e como ingressar. Campos em confirmação voltam nulos com o motivo — "
                "nesse caso NÃO afirme o dado."
            ),
            "parameters": {
                "type": "object",
                "properties": {"product_slug": slug_schema},
                "required": ["product_slug"],
                "additionalProperties": False,
            },
            "strict": True,
        },
        {
            "type": "function",
            "name": "get_event_schedule",
            "description": "Retorna a programação do congresso (por dia, se informado).",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_slug": slug_schema,
                    "day": {"type": ["string", "null"], "description": "dia específico, opcional"},
                },
                "required": ["product_slug", "day"],
                "additionalProperties": False,
            },
            "strict": True,
        },
        {
            "type": "function",
            "name": "get_faq_answer",
            "description": "Busca uma resposta oficial na FAQ do congresso por tópico/palavra-chave (ex.: certificado, reembolso, estudante, submissão, pagamento).",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_slug": slug_schema,
                    "topic": {"type": "string", "description": "tópico ou palavra-chave da dúvida"},
                },
                "required": ["product_slug", "topic"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    ]


async def execute_tool(name: str, args: dict[str, Any], ctx: ToolContext) -> dict:
    if name == "list_products":
        prods = await _load_all(ctx.db)
        return {"produtos": [
            {
                "slug": p.slug,
                "name": p.name,
                "kind": p.kind,
                "datas": p.event_dates,
            }
            for p in prods
        ]}

    if name == "get_product_info":
        p = await _load(ctx.db, args.get("product_slug", ""))
        if p is None:
            return {"erro": "produto não encontrado", "slug": args.get("product_slug")}
        if p.kind == "pos":
            return _pos_payload(p)
        return {
            "slug": p.slug,
            "name": p.name,
            "kind": p.kind,
            "datas": p.event_dates,
            "checkout_url": p.checkout_url,
            "lotes_ativos": _active_tickets(p),
            "promo_vigente": _promo_vigente(p),
            "politicas": p.policies or {},
        }

    if name == "get_event_schedule":
        p = await _load(ctx.db, args.get("product_slug", ""))
        if p is None:
            return {"erro": "produto não encontrado"}
        sched = p.schedule or []
        if not sched:
            return {
                "slug": p.slug,
                "programacao": [],
                "aviso": "Programação detalhada ainda não disponível na base; oriente a pessoa a consultar a página oficial ou ofereça chamar a equipe.",
                "horario_geral": (p.policies or {}).get("horario"),
            }
        day = args.get("day")
        if day:
            sched = [s for s in sched if str(s.get("dia", "")).find(day) >= 0]
        return {"slug": p.slug, "programacao": sched}

    if name == "get_faq_answer":
        p = await _load(ctx.db, args.get("product_slug", ""))
        if p is None:
            return {"erro": "produto não encontrado"}
        topic = (args.get("topic") or "").lower()
        faq = p.faq or []
        hits = [f for f in faq if topic in (f.get("q", "") + " " + f.get("a", "")).lower()]
        # também expõe políticas relevantes como fallback
        pol = p.policies or {}
        pol_hits = {k: v for k, v in pol.items() if topic and topic in (k + " " + str(v)).lower()}
        return {
            "slug": p.slug,
            "faq": hits[:4] or faq[:4],
            "politicas_relacionadas": pol_hits,
        }

    return {"erro": f"tool desconhecida: {name}"}
