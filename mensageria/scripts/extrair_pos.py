#!/usr/bin/env python3
"""extrair_pos.py — coleta as landing pages das pós-graduações CENAT (kind="pos").

Baixa as 13 landings de `pos*.cenatsaudemental.com`, extrai os campos do modelo
canônico (o da Turma 3 de Saúde Mental no Trabalho) e grava um JSON que serve de
fonte única para `scripts/seed_pos.py` — assim nenhum preço é digitado à mão.

As landings compartilham o mesmo template (seções com id `for-who`, `curriculum`,
`faculty`, `pricing`, `faq` e badges `hero-stat-val`/`hero-stat-label`), então a
extração é por âncora estrutural, não por posição.

**Nada é inventado.** Todo campo que não puder ser extraído com certeza sai como
`null` e ganha uma linha em `avisos` — que o relatório em Markdown marca com ⚠️.

Uso:
    .venv/bin/python scripts/extrair_pos.py                    # baixa e grava JSON+MD
    .venv/bin/python scripts/extrair_pos.py --cache-dir /tmp/x # reusa HTML baixado
    .venv/bin/python scripts/extrair_pos.py --only pos-tea     # um curso só

Saídas (default):
    scripts/data/pos_extraido.json   — dados estruturados (consumido pelo seed)
    scripts/data/pos_extraido.md     — relatório para revisão humana
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import sys
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "scripts" / "data"

# slug canônico -> landing. O slug é a chave de upsert em agent_products.
LANDINGS: dict[str, str] = {
    "pos-sm-trabalho-t3": "https://posmdotrabalhadort3.cenatsaudemental.com/",
    "pos-psicologia-raps": "https://pospsicologianaraps.cenatsaudemental.com/",
    "pos-psicologia-escolar": "https://pospsicologiaescolar.cenatsaudemental.com/",
    "pos-mulheridades": "https://posmulheridades.cenatsaudemental.com/",
    "pos-grupos-oficinas-t2": "https://posgruposeoficinast2.cenatsaudemental.com/",
    "pos-tea": "https://postea.cenatsaudemental.com/",
    "pos-gestao-t5": "https://posgestaot5.cenatsaudemental.com/",
    "pos-economia-solidaria": "https://poseconomiasolidaria.cenatsaudemental.com/",
    "pos-dialogo-aberto": "https://posdialogoaberto.cenatsaudemental.com/",
    "pos-suicidio-t3": "https://possuicidiot3.cenatsaudemental.com/",
    "pos-psicologia-clinica-t2": "https://pospsicologiaclinicat2.cenatsaudemental.com/",
    "pos-alcool-drogas-t4": "https://poscuidadousuariosadturma4.cenatsaudemental.com/",
    "pos-psicologia-hospitalar": "https://pospsicologiahospitalar.cenatsaudemental.com/",
}

UA = "Mozilla/5.0 (compatible; CENAT-extrair-pos/1.0)"

# ─────────────────────────── html → texto ───────────────────────────


def strip_tags(frag: str) -> str:
    """Colapsa um fragmento de HTML numa linha de texto."""
    frag = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", frag)
    frag = re.sub(r"(?s)<[^>]+>", " ", frag)
    return re.sub(r"[\s\xa0]+", " ", html.unescape(frag)).strip()


def flatten(page: str) -> list[str]:
    """Quebra o HTML em linhas de texto, uma por bloco visual."""
    t = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", page)
    t = re.sub(r"(?is)<br\s*/?>", "\n", t)
    t = re.sub(r"(?is)</(p|div|h[1-6]|li|tr|td|span|section)>", "\n", t)
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    t = html.unescape(t)
    lines = (re.sub(r"[ \t\xa0]+", " ", ln).strip() for ln in t.split("\n"))
    return [ln for ln in lines if ln]


def section(page: str, sec_id: str) -> str:
    """Devolve o HTML da <section id="..."> (ou '' se não existir)."""
    m = re.search(
        rf'(?is)<section[^>]*id="{re.escape(sec_id)}".*?</section>', page
    )
    return m.group(0) if m else ""


def hero(page: str) -> str:
    """HTML antes da primeira <section id=...> — o bloco hero."""
    m = re.search(r'(?is)<section[^>]*id="', page)
    return page[: m.start()] if m else page


# ─────────────────────────── parsers de campo ───────────────────────────

MONEY = r"R\$\s*([\d.]+(?:,\d{2})?)"


def to_cents(brl: str) -> int:
    """'6.800,00' / '6.800' / '255,00' -> centavos."""
    s = brl.strip().replace(".", "")
    if "," in s:
        inteiro, frac = s.split(",", 1)
        frac = (frac + "00")[:2]
    else:
        inteiro, frac = s, "00"
    return int(inteiro) * 100 + int(frac)


def parse_nome(page: str) -> str | None:
    for m in re.finditer(r"(?is)<h1[^>]*>(.*?)</h1>", page):
        txt = strip_tags(re.sub(r"(?is)<br\s*/?>", " ", m.group(1)))
        # A 2ª h1 de algumas páginas é o overlay "Obrigado(a) pelo seu interesse!".
        if txt and "obrigado" not in txt.lower():
            return txt
    return None


def parse_turma(page: str) -> str | None:
    # <div class="hero-badge"><span class="hero-badge-dot"></span> Turma 3</div>
    # (o `-dot` é só o pontinho decorativo; o texto é irmão dele)
    m = re.search(r'(?is)class="hero-badge"[^>]*>(.*?)</div>', page)
    if m:
        txt = strip_tags(m.group(1))
        if txt:
            return txt
    m = re.search(r"(?im)^\s*(Turma\s+[^\n]{0,60})$", "\n".join(flatten(hero(page))))
    return m.group(1).strip() if m else None


def parse_badges(page: str) -> dict[str, str]:
    """Badges do hero: {'início das aulas': '03/11/2026', 'carga horária': ...}."""
    h = hero(page)
    vals = re.findall(r'(?is)class="hero-stat-val"[^>]*>(.*?)</div>', h)
    labs = re.findall(r'(?is)class="hero-stat-label"[^>]*>(.*?)</div>', h)
    return {
        strip_tags(lab).lower(): strip_tags(val)
        for val, lab in zip(vals, labs)
        if strip_tags(lab)
    }


def parse_faq(page: str) -> list[dict[str, str]]:
    sec = section(page, "faq")
    qs = re.findall(r'(?is)class="faq-q"[^>]*>(.*?)</div>', sec)
    as_ = re.findall(r'(?is)class="faq-a"[^>]*>(.*?)</div>', sec)
    out = []
    for q, a in zip(qs, as_):
        q = re.sub(r"\s*\+\s*$", "", strip_tags(q))
        a = strip_tags(a)
        if q and a:
            out.append({"q": q, "a": a})
    return out


def parse_precos(page: str, avisos: list[str]) -> dict:
    """Extrai o bloco de investimento.

    Duas variantes no template:
      A) total: 'DE R$ 6.800,00 , POR R$ 5.100,00 à vista' + '20x de R$ 255,00'
      B) por parcela: 'DE R$ 340,00 , POR R$ 255,00 por parcela' (sem total!)
    Em (B) o total NÃO é publicado — não multiplicamos parcela por prazo.
    """
    linhas = flatten(section(page, "pricing"))
    blob = " \n ".join(linhas)
    out: dict = {
        "preco_cheio_cents": None,
        "preco_promo_avista_cents": None,
        "parcelas": None,
        "parcela_cents": None,
        "parcela_cheia_cents": None,
        "base": "por_total",
        "texto_investimento": [ln for ln in linhas[:14]],
    }

    m_de = re.search(rf"(?i)\bDE\s+{MONEY}", blob)
    m_avista = re.search(rf"(?i){MONEY}\s*à vista", blob)
    m_parc = re.search(rf"(?i)(\d+)\s*x\s+de\s+{MONEY}", blob)
    por_parcela = bool(re.search(r"(?i)por parcela|/parcela", blob))

    if m_parc:
        out["parcelas"] = int(m_parc.group(1))
        out["parcela_cents"] = to_cents(m_parc.group(2))
    else:
        avisos.append("não achei o parcelamento ('Nx de R$ ...') na seção de investimento")

    if m_avista:
        out["preco_promo_avista_cents"] = to_cents(m_avista.group(1))

    if m_de:
        de = to_cents(m_de.group(1))
        # Heurística: 'DE' abaixo de R$ 1.000 é valor de PARCELA, não total.
        if por_parcela or de < 100_000:
            out["base"] = "por_parcela"
            out["parcela_cheia_cents"] = de
            avisos.append(
                f"a página anuncia só o valor por parcela (de R$ {de/100:.2f} por parcela); "
                "o valor CHEIO total não é publicado — não foi calculado"
            )
        else:
            out["preco_cheio_cents"] = de
    else:
        avisos.append("não achei o valor cheio ('DE R$ ...') na seção de investimento")

    if out["base"] == "por_total" and not m_avista:
        avisos.append("não achei o valor promocional à vista ('R$ ... à vista')")

    return out


def parse_promo(page: str, ano: int, avisos: list[str]) -> dict | None:
    """Badge de promoção do hero + prazo. As páginas não publicam o ANO do prazo."""
    h = hero(page)
    m = re.search(r'(?is)class="hero-oferta-box-badge"[^>]*>(.*?)</div>', h)
    badge = strip_tags(m.group(1)) if m else None
    if not badge:
        for ln in flatten(h):
            if "%" in ln and ("off" in ln.lower() or "desconto" in ln.lower()):
                badge = ln
                break
    if not badge:
        return None

    badge = badge.lstrip("🔥 ").strip()
    corpo = " ".join(flatten(page))

    m_pct = re.search(r"(\d{1,2})\s*%", badge)
    m_dia = re.search(r"(?i)at[ée]\s+(\d{2})/(\d{2})", badge) or re.search(
        r"(?i)at[ée]\s+(\d{2})/(\d{2})", corpo
    )
    valido_ate = None
    if m_dia:
        valido_ate = f"{ano}-{m_dia.group(2)}-{m_dia.group(1)}"
        avisos.append(
            f"a página escreve o prazo da promo sem ano ('até {m_dia.group(1)}/"
            f"{m_dia.group(2)}'); assumi {valido_ate} (--ano={ano}) — confirmar"
        )
    else:
        avisos.append("promo sem prazo legível na página")

    # A condição de pagamento mora na seção de investimento ("no cartão por
    # recorrência"); o badge do hero repete o texto em caixa alta — ignoramos ele.
    condicao = None
    for ln in flatten(section(page, "pricing")) + flatten(page):
        if re.search(r"(?i)cart[ãa]o por recorr", ln) and "%" not in ln:
            condicao = ln
            break

    return {
        "descricao": badge,
        "percentual": int(m_pct.group(1)) if m_pct else None,
        "valido_de": None,          # as páginas não publicam início da promo
        "valido_ate": valido_ate,
        "cupom": None,              # desconto aplicado na página, sem cupom
        "condicao": condicao,
    }


def parse_certificacao(page: str, avisos: list[str]) -> str | None:
    for ln in flatten(page):
        m = re.search(
            r"(?i)Certifica[çc][ãa]o MEC\s+(Faculdade[^—–]*)[—–]\s*(Portaria[^\n]*)", ln
        )
        if m:
            return f"{m.group(1).strip()} — {m.group(2).strip()}"
    for ln in flatten(page):
        if re.search(r"(?i)parceria do CENAT com a (Faculdade|Universidade|Centro)", ln):
            return ln
    avisos.append("não achei a faculdade certificadora")
    return None


def parse_aulas(page: str, badges: dict, avisos: list[str]) -> str | None:
    if "horário das aulas" in badges:
        return badges["horário das aulas"]
    for ln in flatten(page):
        m = re.match(r"(?i)^Aulas\s+(.{3,60}?)\s*\|\s*Online e ao vivo", ln)
        if m:
            # "às Terças-feiras (19h–22h)" -> "Terças-feiras, 19h–22h"
            s = re.sub(r"(?i)^(às|aos|a[oò]s)\s+", "", m.group(1).strip())
            s = re.sub(r"\s*\(([^)]+)\)\s*$", r", \1", s)
            return s.strip()
    for ln in flatten(page):
        m = re.search(
            r"(?i)aulas ao vivo\s+(a[oò]s|às)\s+([a-zç\-]+(?:-feiras?)?)[^.]*?"
            r"(\d{1,2})h\s*(?:às|[–-])\s*(\d{1,2})h",
            ln,
        )
        if m:
            return f"{m.group(2)}, {m.group(3)}h–{m.group(4)}h"
    avisos.append("não achei o dia/horário das aulas")
    return None


def parse_carga(page: str, badges: dict, avisos: list[str]) -> str | None:
    if "carga horária" in badges:
        return badges["carga horária"]
    for ln in flatten(section(page, "pricing")) + flatten(section(page, "curriculum")):
        m = re.search(r"(\d{3})\s*h(?:oras)?\b", ln)
        if m:
            return f"{m.group(1)} horas"
    avisos.append("não achei a carga horária")
    return None


def parse_duracao(page: str, avisos: list[str]) -> str | None:
    """Duração do curso em meses.

    Casa só as formas em que o número é *a duração do curso* ('14 meses de
    duração', '360h · 15 meses ·', 'tem 362 horas e 16 meses'). Um `\\d+ meses`
    solto pega bônus do tipo '6 supervisões ao longo de 6 meses'.
    """
    corpo = " \n ".join(flatten(page))
    padroes = (
        r"(?i)\b(\d{1,2})\s*meses\s+de\s+dura[çc][ãa]o",
        r"(?i)dura[çc][ãa]o\s+(?:de\s+)?(?:aproximadamente\s+)?(\d{1,2})\s*meses",
        r"(?i)\d+\s*h(?:oras)?\s*(?:·|e)\s*(\d{1,2})\s*meses",
        r"(?i)(\d{1,2})\s*meses\b[^\n]{0,20}Certifica",
    )
    meses = {
        int(m.group(1)) for p in padroes for m in re.finditer(p, corpo)
    }
    if not meses:
        avisos.append("não achei a duração em meses")
        return None
    if len(meses) > 1:
        ordenado = sorted(meses)
        avisos.append(
            "a página cita durações divergentes em lugares diferentes: "
            + ", ".join(f"{m} meses" for m in ordenado)
        )
        return " ou ".join(f"{m} meses" for m in ordenado)
    return f"{meses.pop()} meses"


def parse_modulos(page: str, avisos: list[str]) -> list[dict]:
    out = []
    for ln in flatten(section(page, "curriculum")):
        if "Clique para ver as disciplinas" not in ln:
            continue
        horas = None
        m = re.search(r"(\d{2,3})\s*h\b", ln)
        if m:
            horas = int(m.group(1))
        titulo = re.sub(r"(?i)\s*·?\s*Clique para ver as disciplinas\s*·?\s*", " ", ln)
        titulo = re.sub(r"(\d{2,3})\s*h\b", " ", titulo)
        titulo = re.sub(r"^\s*[·•\-\s]+|[·•\-\s]+$", "", titulo).strip()
        if titulo:
            out.append({"titulo": titulo, "horas": horas})
    if not out:
        avisos.append("não achei os módulos/eixos do currículo")
    return out


def parse_equipe(page: str, avisos: list[str]) -> dict:
    linhas = flatten(section(page, "faculty"))
    papeis = {"coordenador", "coordenadora", "coordenadores", "coordenadoras",
              "docente", "docentes", "professor", "professora"}
    coord, docentes = [], []
    for i, ln in enumerate(linhas):
        if ln.strip().lower() not in papeis:
            continue
        nome = linhas[i + 1].strip() if i + 1 < len(linhas) else ""
        bio = linhas[i + 2].strip() if i + 2 < len(linhas) else ""
        if not nome or len(nome) > 70 or nome.lower() in papeis:
            continue
        alvo = coord if ln.strip().lower().startswith("coorden") else docentes
        alvo.append({"nome": nome, "bio": bio})
    if not coord:
        avisos.append("não achei a coordenação do curso")
    return {"coordenacao": coord, "docentes": docentes}


def parse_publico(page: str, faq: list[dict], avisos: list[str]) -> dict:
    linhas = flatten(section(page, "for-who"))
    perfis = []
    for ln in linhas:
        if 12 < len(ln) < 75 and not ln.endswith(".") and not ln.endswith("?"):
            if re.match(r"(?i)^(pra quem|você se reconhece|como funciona)", ln):
                continue
            if re.search(r"[A-Za-zÀ-ÿ]{3}", ln):
                perfis.append(ln)
    resumo = None
    for item in faq:
        if re.search(r"(?i)quem pode fazer", item["q"]):
            resumo = item["a"]
            break
    if resumo is None:
        # 1ª frase longa da seção for-who serve de resumo.
        longas = [ln for ln in linhas if len(ln) > 90]
        resumo = longas[0] if longas else None
    if resumo is None:
        avisos.append("não achei descrição do público-alvo")
    return {"resumo": resumo, "perfis": perfis}


def parse_diferenciais(page: str) -> list[str]:
    """Bullets do card de investimento (sem TCC, Clube Carreira, etc.)."""
    linhas = flatten(section(page, "pricing"))
    keys = (
        "sem tcc", "clube carreira", "carteira de estudante", "isenção",
        "dedutível", "garantia", "certificad",
    )
    # O parágrafo de venda ("Invista na formação que...") também casa com as
    # palavras-chave; ele não é um diferencial listado.
    ruido = ("invista na formação", "invista na especialização")
    out, seen = [], set()
    for ln in linhas:
        low = ln.lower()
        if any(r in low for r in ruido):
            continue
        if any(k in low for k in keys) and len(ln) < 160:
            norm = re.sub(r"\W+", "", low)
            if norm not in seen:
                seen.add(norm)
                out.append(ln)
    return out


def parse_bonus(page: str) -> list[str]:
    """Bônus/promoções extras que ficam fora do badge principal."""
    out = []
    for ln in flatten(section(page, "pricing")):
        if re.search(r"(?i)^\W*B[ÔO]NUS", ln) or re.search(r"(?i)ganhe\b", ln):
            out.append(ln)
    return out


def parse_contatos(page: str) -> dict:
    corpo = " ".join(flatten(page))
    email = re.search(r"[\w.+-]+@[\w.-]+\.\w+", corpo)
    zap = re.search(r"\(\d{2}\)\s*\d{4,5}-?\d{4}", corpo)
    return {"email": email.group(0) if email else None,
            "whatsapp": zap.group(0) if zap else None}


# ─────────────────────────── extração de uma página ───────────────────────────


def _normalizar_inicio(inicio: str, page: str, avisos: list[str]) -> str:
    """Normaliza a data de início e sinaliza ano de 2 dígitos / data no passado.

    Uma turma cujo início já passou é sinal de landing desatualizada — o agente
    não pode anunciar essa data como futura.
    """
    m = re.match(r"(\d{2})/(\d{2})/(\d{2,4})$", inicio.strip())
    if not m:
        return inicio
    dia, mes, ano = m.groups()
    if len(ano) == 2:
        ano = f"20{ano}"
        # A seção de investimento costuma repetir a data com o ano completo.
        outra = re.search(
            rf"(?i)in[íi]cio em {dia}/{mes}/(\d{{4}})", " ".join(flatten(page))
        )
        if outra and outra.group(1) != ano:
            avisos.append(
                f"o badge do hero traz o ano com 2 dígitos ({inicio}) e a página "
                f"repete como {dia}/{mes}/{outra.group(1)} — divergência de ano"
            )
        else:
            avisos.append(
                f"o badge do hero traz o ano com 2 dígitos ({inicio}); "
                f"normalizei para {dia}/{mes}/{ano}"
            )
    norm = f"{dia}/{mes}/{ano}"
    try:
        if dt.date(int(ano), int(mes), int(dia)) < dt.date.today():
            avisos.append(
                f"a data de início ({norm}) já passou — landing possivelmente "
                "desatualizada; confirmar com o comercial antes de anunciar"
            )
    except ValueError:
        avisos.append(f"data de início inválida: {norm}")
    return norm


def extrair(slug: str, url: str, page: str, ano: int) -> dict:
    avisos: list[str] = []
    badges = parse_badges(page)

    inicio = badges.get("início das aulas") or badges.get("inicio das aulas")
    if not inicio:
        m = re.search(r"(?i)in[íi]cio (?:em|das aulas)\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})",
                      " ".join(flatten(page)))
        inicio = m.group(1) if m else None
    if not inicio:
        avisos.append("não achei a data de início das aulas")
    else:
        inicio = _normalizar_inicio(inicio, page, avisos)

    faq = parse_faq(page)
    if not faq:
        avisos.append("não achei o FAQ")

    dados = {
        "slug": slug,
        "landing_url": url,
        "nome": parse_nome(page),
        "turma": parse_turma(page),
        "inicio_aulas": inicio,
        "carga_horaria": parse_carga(page, badges, avisos),
        "duracao": parse_duracao(page, avisos),
        "aulas": parse_aulas(page, badges, avisos),
        "certificacao": parse_certificacao(page, avisos),
        "investimento": parse_precos(page, avisos),
        "promo": parse_promo(page, ano, avisos),
        "publico": parse_publico(page, faq, avisos),
        "modulos": parse_modulos(page, avisos),
        "diferenciais": parse_diferenciais(page),
        "bonus": parse_bonus(page),
        "faq": faq,
        "contatos": parse_contatos(page),
        "avisos": avisos,
    }
    dados.update(parse_equipe(page, avisos))
    if not dados["nome"]:
        avisos.append("não achei o nome do curso (h1)")
    return dados


# ─────────────────────────── checagens entre páginas ───────────────────────────


def checar_contaminacao(cursos: list[dict]) -> None:
    """Sinaliza texto de público/perfil repetido entre landings diferentes.

    Parte do template é boilerplate legítimo, mas há landings com conteúdo
    copiado de OUTRO curso (a de Psicologia na RAPS descreve público e FAQ de
    Psicologia Escolar). Não há como decidir isso automaticamente, então cada
    repetição sai como aviso para revisão humana.
    """
    def norm(s: str | None) -> str:
        return re.sub(r"\W+", " ", (s or "").lower()).strip()

    grupos: dict[str, list[str]] = {}
    for c in cursos:
        chave = norm(c["publico"]["resumo"])
        if chave:
            grupos.setdefault(chave, []).append(c["slug"])

    for chave, slugs in grupos.items():
        if len(slugs) < 2:
            continue
        for c in cursos:
            if c["slug"] not in slugs:
                continue
            outros = [s for s in slugs if s != c["slug"]]
            c["avisos"].append(
                "o texto de público-alvo é idêntico ao de "
                + ", ".join(outros)
                + " — pode ser boilerplate do template ou conteúdo copiado da "
                "landing errada; revisar"
            )

    # Sinal mais forte: o texto do público fala de um tema ausente do nome do curso.
    temas = {
        "escolar": ("escolar", "educacional", "psicopedag"),
        "hospitalar": ("hospitalar", "enfermaria", "uti"),
        "trabalho": ("organizaç", "riscos psicossociais", "nr-1"),
    }
    for c in cursos:
        nome = norm(c["nome"])
        alvo = norm(c["publico"]["resumo"])
        for tema, marcas in temas.items():
            if tema in nome:
                continue
            if any(m in alvo for m in marcas):
                c["avisos"].append(
                    f"o público-alvo descrito menciona o tema '{tema}', que não "
                    f"aparece no nome do curso — provável conteúdo de outra "
                    f"landing; NÃO semear esse campo sem confirmação"
                )
                break


# ─────────────────────────── relatório markdown ───────────────────────────


def brl(cents: int | None) -> str:
    if cents is None:
        return "⚠️ não publicado"
    return f"R$ {cents/100:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def md_curso(i: int, d: dict) -> str:
    inv = d["investimento"]
    promo = d["promo"] or {}
    coord = "; ".join(c["nome"] for c in d["coordenacao"]) or "⚠️"
    docentes = "; ".join(c["nome"] for c in d["docentes"]) or "—"
    mods = " · ".join(
        f"{m['titulo']}" + (f" ({m['horas']}h)" if m["horas"] else " (⚠️ h?)")
        for m in d["modulos"]
    ) or "⚠️"

    if inv["base"] == "por_parcela":
        cheio = f"⚠️ total não publicado (página anuncia {brl(inv['parcela_cheia_cents'])}/parcela)"
        prom = f"{inv['parcelas']}x de {brl(inv['parcela_cents'])}" if inv["parcelas"] else "⚠️"
    else:
        cheio = brl(inv["preco_cheio_cents"])
        prom = (
            f"{brl(inv['preco_promo_avista_cents'])} à vista"
            + (f" OU {inv['parcelas']}x de {brl(inv['parcela_cents'])}" if inv["parcelas"] else "")
        )

    linhas = [
        f"## {i}. {d['nome'] or '⚠️ nome não extraído'}",
        "",
        "| campo | valor |",
        "|---|---|",
        f"| slug | `{d['slug']}` |",
        f"| landing | {d['landing_url']} |",
        f"| turma | {d['turma'] or '⚠️'} |",
        f"| inicio_aulas | {d['inicio_aulas'] or '⚠️'} |",
        f"| carga_horaria | {d['carga_horaria'] or '⚠️'} |",
        f"| duracao | {d['duracao'] or '⚠️'} |",
        f"| aulas | {d['aulas'] or '⚠️'} |",
        f"| certificacao | {d['certificacao'] or '⚠️'} |",
        f"| investimento_cheio | {cheio} |",
        f"| investimento_promo | {prom} |",
        f"| promo | {promo.get('descricao') or '⚠️ nenhuma'} · até {promo.get('valido_ate') or '⚠️'} |",
        f"| condicao_promo | {promo.get('condicao') or '⚠️'} |",
        f"| publico | {d['publico']['resumo'] or '⚠️'} |",
        f"| perfis | {'; '.join(d['publico']['perfis']) or '—'} |",
        f"| modulos | {mods} |",
        f"| coordenacao | {coord} |",
        f"| docentes | {docentes} |",
        f"| diferenciais | {'; '.join(d['diferenciais']) or '—'} |",
    ]
    if d["bonus"]:
        linhas.append(f"| bonus | {' / '.join(d['bonus'])} |")
    linhas.append(f"| faq | {len(d['faq'])} perguntas |")
    if d["avisos"]:
        linhas += ["", "**⚠️ Avisos de extração:**"] + [f"- {a}" for a in d["avisos"]]
    return "\n".join(linhas) + "\n"


def relatorio(cursos: list[dict], ano: int) -> str:
    com_promo = [c for c in cursos if c["promo"]]
    prazos = sorted({c["promo"]["valido_ate"] for c in com_promo if c["promo"]})
    certs = sorted({(c["certificacao"] or "⚠️") for c in cursos})
    hoje = dt.date.today().isoformat()

    head = [
        "# Extração das landings de pós-graduação — relatório",
        "",
        f"Gerado por `scripts/extrair_pos.py` em {hoje} (--ano={ano}).",
        f"{len(cursos)} de {len(LANDINGS)} landings processadas.",
        "",
        "## Consolidado",
        "",
        f"- **Promoção**: {len(com_promo)}/{len(cursos)} páginas anunciam promoção. "
        f"Prazos distintos encontrados: {', '.join(prazos) or '—'}.",
        "- **Certificadoras encontradas** (uma linha por variação de texto):",
    ]
    for c in certs:
        quem = [x["slug"] for x in cursos if (x["certificacao"] or "⚠️") == c]
        head.append(f"  - `{c}` → {len(quem)} curso(s): {', '.join(quem)}")
    total_avisos = sum(len(c["avisos"]) for c in cursos)
    head += [
        f"- **Campos incertos**: {total_avisos} aviso(s) no total "
        f"({sum(1 for c in cursos if c['avisos'])} curso(s) com pelo menos um).",
        "",
        "---",
        "",
    ]
    return "\n".join(head) + "\n---\n\n".join(md_curso(i, c) for i, c in enumerate(cursos, 1))


# ─────────────────────────── main ───────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--cache-dir", type=Path, default=None,
                    help="reusa/grava o HTML cru (evita rebaixar tudo a cada teste)")
    ap.add_argument("--only", action="append", default=None,
                    help="processa só estes slugs (repetível)")
    ap.add_argument("--ano", type=int, default=dt.date.today().year,
                    help="ano assumido para prazos escritos como 'até 31/07'")
    args = ap.parse_args()

    alvos = {s: u for s, u in LANDINGS.items() if not args.only or s in args.only}
    if not alvos:
        print(f"[X] nenhum slug casou com {args.only}", file=sys.stderr)
        return 1

    if args.cache_dir:
        args.cache_dir.mkdir(parents=True, exist_ok=True)

    cursos: list[dict] = []
    with httpx.Client(timeout=45, follow_redirects=True, headers={"User-Agent": UA}) as cli:
        for slug, url in alvos.items():
            cache = args.cache_dir / f"{slug}.html" if args.cache_dir else None
            if cache and cache.exists():
                page, origem = cache.read_text(), "cache"
            else:
                try:
                    r = cli.get(url)
                    r.raise_for_status()
                except Exception as exc:  # rede/HTTP — segue com os outros
                    print(f"[X] {slug}: {type(exc).__name__}: {exc}", file=sys.stderr)
                    continue
                page, origem = r.text, f"HTTP {r.status_code}"
                if cache:
                    cache.write_text(page)
            d = extrair(slug, url, page, args.ano)
            cursos.append(d)
            flag = f"⚠️ {len(d['avisos'])}" if d["avisos"] else "ok"
            print(f"{slug:28} {origem:9} {flag:6} {d['nome'] or '(sem nome)'}")

    checar_contaminacao(cursos)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.out_dir / "pos_extraido.json"
    md_path = args.out_dir / "pos_extraido.md"
    json_path.write_text(
        json.dumps(
            {"gerado_em": dt.date.today().isoformat(), "ano_assumido": args.ano,
             "cursos": cursos},
            ensure_ascii=False, indent=2,
        )
    )
    md_path.write_text(relatorio(cursos, args.ano))
    print(f"\n→ {json_path}\n→ {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
