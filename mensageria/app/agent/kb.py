"""Base de conhecimento do agente em arquivos `.md`, com busca léxica BM25.

Por que arquivo e não banco: a equipe de atendimento precisa corrigir uma
resposta errada sem deploy e sem SQL. O loader relê por assinatura
(nome + mtime + tamanho) a cada turno, então salvar o `.md` vale no turno
seguinte — sem restart e sem task de watcher.

**Híbrida de propósito.** Enquanto a base é pequena, mandá-la INTEIRA no system
prompt é mais barato e mais preciso que qualquer busca: zero risco de o trecho
certo não ser recuperado. Quando ela cresce, isso vira desperdício de contexto a
cada turno — aí o modelo passa a receber só o índice e busca o que precisa. O
limite é `AGENT_KB_INLINE_MAX_CHARS`, e a troca é automática.

**A KB não tem preço, data, lote nem link de produto.** Isso vive em
`agent_products` (regra de ouro do PLANO_AGENTE §7.2) e só sai por tool, porque
é a tool que alimenta a allowlist do guardrail de saída. KB é para política,
procedimento e FAQ.

Busca: BM25 Okapi em Python puro. Sem dependência nova de propósito — a VPS tem
1,9 GiB de RAM compartilhados com Postgres e Next, e embeddings/pgvector para
sete arquivos pequenos seria custo sem retorno. Se a busca léxica começar a
errar com paráfrase, a medição está nos `agent_turn_logs` (consultas que
voltaram vazias).
"""
from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from app.config import get_settings

settings = get_settings()

KB_DIR = Path(__file__).resolve().parent / "kb"

# Alvo de tamanho do chunk. Não é um corte rígido: o chunk fecha ANTES de passar
# do alvo, e nunca no meio de uma linha — num .md de FAQ a linha é a unidade de
# sentido ("Nome errado no certificado: pedir o nome correto..."), e partir uma
# linha produziria um trecho que responde errado.
CHUNK_ALVO = 600

# Stopwords PT-BR básicas. Lista curta de propósito: numa base pequena, tirar
# palavra demais destrói sinal (ex.: "não" muda o sentido de uma política).
STOPWORDS = {
    "a", "ao", "aos", "as", "até", "com", "como", "da", "das", "de", "do", "dos",
    "e", "em", "entre", "era", "essa", "esse", "esta", "este", "eu", "foi", "for",
    "há", "isso", "já", "la", "lo", "mais", "mas", "me", "meu", "minha", "muito",
    "na", "nas", "no", "nos", "num", "numa", "o", "os", "ou", "para", "pela",
    "pelo", "por", "pra", "pro", "qual", "quando", "que", "se", "sem", "ser",
    "seu", "sua", "são", "também", "tem", "ter", "um", "uma", "vai", "você",
    "sobre", "quero", "gostaria", "saber", "queria", "tudo", "bem", "oi", "olá",
}

# Sinônimos curtos, fixos no código. Expandem os DOIS lados (documento e
# consulta), então "estorno" acha o parágrafo que fala de "reembolso" sem que
# ninguém precise escrever as duas palavras no .md.
SINONIMOS: list[set[str]] = [
    {"certificado", "certificacao", "certificar", "diploma", "declaracao"},
    {"pos", "posgraduacao", "especializacao", "lato"},
    {"reembolso", "estorno", "cancelamento", "cancelar", "devolucao", "desistir"},
    {"senha", "acesso", "login", "logar", "entrar", "plataforma"},
    {"valor", "preco", "custo", "investimento", "mensalidade"},
    {"inscricao", "matricula", "inscrever", "matricular"},
    {"gravacao", "gravado", "regravacao", "replay"},
    {"comunidade", "assinatura", "assinante"},
    {"intercambio", "viagem", "imersao"},
    {"nota", "recibo", "fiscal", "comprovante"},
]


def _sem_acento(s: str) -> str:
    n = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in n if not unicodedata.combining(c))


def _radical(t: str) -> str:
    """Plural PT-BR rudimentar. Não é stemmer: só encosta as formas que mais
    aparecem numa FAQ ("certificados" → "certificado", "inscrições" →
    "inscricao"), para a busca não falhar por causa de um "s"."""
    if len(t) > 4:
        if t.endswith("oes") or t.endswith("aes"):
            return t[:-3] + "ao"
        if t.endswith("eis"):
            return t[:-3] + "el"
        if t.endswith("s") and not t.endswith("ss"):
            return t[:-1]
    return t


# índice token -> conjunto completo do grupo, pré-computado uma vez
_GRUPOS: dict[str, frozenset[str]] = {}
for _g in SINONIMOS:
    _norm = frozenset(_radical(_sem_acento(w).lower()) for w in _g)
    for _w in _norm:
        _GRUPOS[_w] = _norm

_STOP_NORM = {_radical(_sem_acento(w).lower()) for w in STOPWORDS}


def tokenizar(texto: str) -> list[str]:
    """Minúsculas, sem acento, sem stopword, com plural encostado e sinônimos
    expandidos. Usada nos dois lados (documento e consulta) — é o que faz
    "estorno" casar com "reembolso" e "pos" com "pós"."""
    bruto = re.findall(r"[0-9a-zà-ÿ]+", (texto or "").lower())
    out: list[str] = []
    for t in bruto:
        t = _radical(_sem_acento(t))
        if not t or t in _STOP_NORM or len(t) == 1:
            continue
        grupo = _GRUPOS.get(t)
        if grupo:
            out.extend(sorted(grupo))
        else:
            out.append(t)
    return out


@dataclass
class Chunk:
    arquivo: str
    secao: str
    texto: str
    tokens: Counter = field(default_factory=Counter, repr=False)

    def como_dict(self, score: float | None = None) -> dict:
        d = {"arquivo": self.arquivo, "secao": self.secao, "texto": self.texto}
        if score is not None:
            d["score"] = round(score, 3)
        return d


@dataclass
class KB:
    nome: str
    mode: str                    # "inteira" | "busca"
    total_chars: int
    full_text: str
    chunks: list[Chunk]
    indice: str
    assinatura: tuple
    descartadas: int = 0
    # posting list do BM25, construído junto (barato nesta escala)
    _df: Counter = field(default_factory=Counter, repr=False)
    _avg_len: float = 0.0

    @property
    def modo_busca(self) -> bool:
        return self.mode == "busca"


def _chunk_arquivo(arquivo: str, texto: str) -> tuple[list[Chunk], int]:
    """Quebra um .md em chunks por seção e, dentro da seção, por parágrafo/linha.

    Devolve (chunks, nº de linhas descartadas por placeholder).
    """
    chunks: list[Chunk] = []
    secao = ""
    buf: list[str] = []
    descartadas = 0

    def tamanho() -> int:
        return sum(len(l) + 1 for l in buf)

    def flush() -> None:
        nonlocal buf
        corpo = "\n".join(buf).strip()
        if corpo:
            cabeca = f"{secao}\n" if secao else ""
            chunks.append(Chunk(arquivo=arquivo, secao=secao,
                                texto=(cabeca + corpo).strip()))
        buf = []

    for bruta in texto.splitlines():
        linha = bruta.rstrip()
        if "{{" in linha:
            # Placeholder não resolvido NUNCA chega ao modelo: ele sairia
            # literalmente na resposta ("seu certificado de {{curso}}") ou o
            # modelo tentaria preencher inventando.
            descartadas += 1
            continue
        titulo = re.match(r"^(#{1,6})\s+(.*)$", linha)
        if titulo:
            flush()
            secao = titulo.group(2).strip()
            continue
        if not linha.strip():
            # Linha vazia é fronteira natural de parágrafo: fecha o chunk se ele
            # já tem corpo suficiente, em vez de estourar o alvo.
            if tamanho() >= CHUNK_ALVO:
                flush()
            elif buf:
                buf.append("")
            continue
        if buf and tamanho() + len(linha) > CHUNK_ALVO:
            flush()
        buf.append(linha)

    flush()
    return chunks, descartadas


def _assinatura(pasta: Path) -> tuple:
    """(nome, mtime_ns, tamanho) de cada .md, ordenado. Mudou qualquer um →
    recarrega. Pega criação e remoção de arquivo, não só edição."""
    itens = []
    for p in sorted(pasta.glob("*.md")):
        if p.name.startswith("_"):
            continue
        st = p.stat()
        itens.append((p.name, st.st_mtime_ns, st.st_size))
    return tuple(itens)


def _montar_indice(chunks: list[Chunk]) -> str:
    """Índice para o modo busca: arquivos e títulos de seção, sem o conteúdo."""
    por_arquivo: dict[str, list[str]] = {}
    for c in chunks:
        secoes = por_arquivo.setdefault(c.arquivo, [])
        if c.secao and c.secao not in secoes:
            secoes.append(c.secao)
    linhas = []
    for arq in sorted(por_arquivo):
        secoes = por_arquivo[arq] or ["(sem seção)"]
        linhas.append(f"- {arq}: " + " · ".join(secoes))
    return "\n".join(linhas)


_cache: dict[str, KB] = {}
_modo_logado: dict[str, str] = {}


def load_kb(nome: str = "atendimento") -> KB:
    """Carrega (ou reusa do cache) a KB. Relê quando a assinatura muda.

    A subpasta `_legado/` não é carregada: `glob("*.md")` não é recursivo e
    arquivos com nome começando em `_` são pulados explicitamente.
    """
    pasta = KB_DIR / nome
    if not pasta.is_dir():
        vazia = KB(nome=nome, mode="inteira", total_chars=0, full_text="",
                   chunks=[], indice="", assinatura=())
        print(f"📚⚠️ KB {nome}: pasta {pasta} não existe — base vazia", flush=True)
        return vazia

    assinatura = _assinatura(pasta)
    em_cache = _cache.get(nome)
    if em_cache is not None and em_cache.assinatura == assinatura:
        return em_cache

    partes: list[str] = []
    chunks: list[Chunk] = []
    descartadas = 0
    for arq, _mtime, _tam in assinatura:
        p = pasta / arq
        try:
            texto = p.read_text(encoding="utf-8")
        except Exception as e:
            print(f"📚⚠️ KB {nome}: falha lendo {arq}: {e!r} — arquivo ignorado",
                  flush=True)
            continue
        cs, desc = _chunk_arquivo(arq, texto)
        descartadas += desc
        chunks.extend(cs)
        # O texto "inteiro" é remontado a partir dos chunks, não do arquivo cru:
        # assim o modo inteira também fica livre dos placeholders descartados.
        partes.extend(c.texto for c in cs)

    full_text = "\n\n".join(partes).strip()
    total = len(full_text)
    mode = "inteira" if total <= settings.AGENT_KB_INLINE_MAX_CHARS else "busca"

    kb = KB(nome=nome, mode=mode, total_chars=total, full_text=full_text,
            chunks=chunks, indice=_montar_indice(chunks), assinatura=assinatura,
            descartadas=descartadas)

    # BM25: df por token e comprimento médio. Reconstruído só aqui, ou seja, só
    # quando a assinatura muda.
    for c in chunks:
        c.tokens = Counter(tokenizar(c.texto))
        for t in c.tokens:
            kb._df[t] += 1
    if chunks:
        kb._avg_len = sum(sum(c.tokens.values()) for c in chunks) / len(chunks)

    _cache[nome] = kb

    if descartadas:
        print(f"📚⚠️ KB {nome}: {descartadas} linha(s) descartada(s) por "
              f"placeholder não resolvido ('{{{{')", flush=True)
    if _modo_logado.get(nome) != mode:
        if mode == "inteira":
            print(f"📚 KB {nome}: inteira ({total} chars)", flush=True)
        else:
            print(f"📚 KB {nome}: busca ({total} chars, {len(chunks)} chunks)",
                  flush=True)
        _modo_logado[nome] = mode
    return kb


# BM25 Okapi — parâmetros padrão da literatura.
_K1 = 1.5
_B = 0.75


def search_kb(nome: str, consulta: str, k: int = 5) -> list[dict]:
    """Top-k chunks para a consulta. Lista VAZIA se nada pontuar acima de zero.

    Vazio não é falha: é o sinal para a regra 4 do prompt (não invente, chame
    handoff_to_human). Devolver o "menos pior" quando nada casa seria pior do
    que admitir que a base não cobre.
    """
    kb = load_kb(nome)
    if not kb.chunks:
        return []
    termos = tokenizar(consulta)
    if not termos:
        return []
    n = len(kb.chunks)
    pontos: list[tuple[float, Chunk]] = []
    for c in kb.chunks:
        dl = sum(c.tokens.values()) or 1
        score = 0.0
        for t in set(termos):
            f = c.tokens.get(t, 0)
            if not f:
                continue
            df = kb._df.get(t, 0) or 1
            idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
            score += idf * (f * (_K1 + 1)) / (
                f + _K1 * (1 - _B + _B * dl / (kb._avg_len or dl))
            )
        if score > 0:
            pontos.append((score, c))
    pontos.sort(key=lambda x: (-x[0], x[1].arquivo, x[1].secao))
    return [c.como_dict(s) for s, c in pontos[:k]]


# ----------------------------------------------------------------------------
# Tool exposta ao modelo apenas no modo busca (ver loop.py::_tools_do_perfil)
# ----------------------------------------------------------------------------
BUSCAR_BASE_SCHEMA: dict = {
    "type": "function",
    "name": "buscar_base",
    "description": (
        "Busca na base de conhecimento do atendimento do CENAT (políticas, "
        "procedimentos e FAQ: certificados, acesso, pagamento, reembolso, "
        "Comunidade, intercâmbios, institucional). Use palavras da pergunta da "
        "pessoa. NÃO traz preço, data, lote nem link de congresso ou pós — isso "
        "vem das tools do catálogo."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "consulta": {
                "type": "string",
                "description": "Palavras-chave da dúvida da pessoa.",
            }
        },
        "required": ["consulta"],
        "additionalProperties": False,
    },
}


def executar_buscar_base(args: dict, nome: str = "atendimento") -> dict:
    consulta = (args or {}).get("consulta") or ""
    resultados = search_kb(nome, consulta)
    if not resultados:
        return {"resultados": [], "aviso": "nada na base"}
    return {"resultados": resultados}
