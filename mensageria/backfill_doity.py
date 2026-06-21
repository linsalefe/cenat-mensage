#!/usr/bin/env python3
"""
backfill_doity.py - coleta COMPLETA via cursor multi-rodada (metodo de producao)
"""

import json, os, sys, time, urllib.error, urllib.parse, urllib.request
from collections import Counter, defaultdict
from datetime import datetime

BASE_URL = os.getenv("DOITY_BASE_URL", "https://api.doity.com.br/public/v1").rstrip("/")
TOKEN = os.getenv("DOITY_TOKEN", "")
EVENTO_IDS = [x.strip() for x in (os.getenv("DOITY_EVENTO_IDS", "") or os.getenv("DOITY_EVENTO_ID", "")).split(",") if x.strip()]
DESDE = os.getenv("DOITY_DESDE", "2024-01-01 00:00:00").strip()
PAGES_PER_ROUND = int(os.getenv("DOITY_PAGES_PER_ROUND", "8"))
MAX_RODADAS = int(os.getenv("DOITY_MAX_RODADAS", "60"))
LIMIT = int(os.getenv("DOITY_LIMIT", "50"))


def _request(path, params=None):
    qs = ("?" + urllib.parse.urlencode(params)) if params else ""
    req = urllib.request.Request(f"{BASE_URL}{path}{qs}", headers={
        "Accept": "application/json", "Authorization": f"Bearer {TOKEN}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8")), r.status


def try_get(path, params=None):
    try:
        return _request(path, params)
    except urllib.error.HTTPError as e:
        return None, e.code
    except urllib.error.URLError:
        return None, -1


def get_strict(path, params=None):
    d, c = try_get(path, params)
    if d is None:
        print(f"\n[X] erro {c} em {path}"); sys.exit(1)
    return d


def m_tel(v):
    if not v: return None
    d = "".join(c for c in str(v) if c.isdigit())
    return f"{str(v)[:5]}...{d[-2:]} (len={len(d)})" if d else None
def m_email(v):
    if not v or "@" not in str(v): return None
    u, dom = str(v).split("@", 1); return f"{u[:1]}***@{dom}"
def m_cpf(v):
    if not v: return None
    d = "".join(c for c in str(v) if c.isdigit())
    return f"***{d[-2:]} (len={len(d)})" if d else None


def extrair_data_atualizacao(p):
    for k in ("data_atualizacao", "modified", "updated_at", "atualizado_em"):
        v = p.get(k)
        if v:
            return v
    return None


def iso_para_filtro(iso_str):
    try:
        return datetime.fromisoformat(iso_str).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def backfill(evento_id):
    cursor = DESDE
    seen, todos = set(), []
    rodada = 0
    print(f"   cursor inicial: {cursor}")
    while True:
        rodada += 1
        novos = 0
        max_iso = None
        page = 1
        page_count = None
        while page <= PAGES_PER_ROUND:
            params = {"ativo": 1, "sort": "modified", "direction": "asc",
                      "page": page, "limit": LIMIT, "data_atualizacao": cursor}
            data, code = try_get(f"/eventos/{evento_id}/participantes", params)
            if data is None:
                print(f"   [!] rodada {rodada} pag {page}: HTTP {code} (parando a rodada).")
                break
            pag = data.get("pagination", {}) or {}
            if rodada == 1 and page == 1:
                pc, pp = pag.get("pageCount"), pag.get("perPage")
                print(f"   API na 1a janela: pageCount={pc} perPage={pp} (~ {(pc*pp) if pc and pp else '?'} na janela)")
            page_count = pag.get("pageCount") or 1
            lote = data.get("participantes", []) or []
            if not lote:
                break
            for p in lote:
                iso = extrair_data_atualizacao(p)
                if iso and (max_iso is None or iso > max_iso):
                    max_iso = iso
                pid = p.get("id")
                if pid in seen:
                    continue
                seen.add(pid); todos.append(p); novos += 1
            if page >= page_count:
                break
            page += 1
            time.sleep(0.2)

        acumulado = len(todos)
        novo_cursor = iso_para_filtro(max_iso) if max_iso else None
        print(f"   rodada {rodada}: +{novos} novos | acumulado {acumulado} | proximo cursor: {novo_cursor}")

        if novos == 0:
            print("   [OK] novos=0 -> coleta exaustiva concluida.")
            break
        if not novo_cursor:
            print("   [!] nao consegui ler data_atualizacao dos registros (campo de cursor). Parando.")
            break
        if novo_cursor == cursor:
            print("   [!] cursor nao avancou com novos>0 (cluster no mesmo timestamp > capacidade da rodada). Parando.")
            break
        if rodada >= MAX_RODADAS:
            print(f"   [!] atingiu MAX_RODADAS={MAX_RODADAS}. Parando.")
            break
        cursor = novo_cursor
        time.sleep(0.2)

    return todos, rodada


def linha(c="-"): print(c * 70)


def main():
    if not TOKEN or not EVENTO_IDS:
        print("Defina DOITY_TOKEN e DOITY_EVENTO_IDS."); sys.exit(1)

    print("\n" + "=" * 70)
    print("  BACKFILL DOITY - cursor multi-rodada")
    print(f"  desde {DESDE} | {PAGES_PER_ROUND} pags/rodada | limit {LIMIT}")
    print("=" * 70)

    por_cod = defaultdict(lambda: {"desc": "", "total": 0, "pago_t": 0, "pago_f": 0})
    nomes, preenchidos = Counter(), Counter()
    tem_tel = tem_email = tem_cpf = sem_compra = 0
    exemplos, total, total_pago = [], 0, 0

    for eid in EVENTO_IDS:
        ev = get_strict(f"/eventos/{eid}").get("evento", {})
        print(f"\n>> Evento {eid} - {ev.get('nome','?')[:48]}")
        parts, rodadas = backfill(eid)
        n = len(parts); pagos = sum(1 for p in parts if p.get("pago") is True)
        total += n; total_pago += pagos
        print(f"   >>> {n} unicos em {rodadas} rodada(s) | {pagos} pagos")

        for p in parts:
            compra = p.get("compra") or {}; sit = compra.get("situacao") or {}
            cod = sit.get("codigo")
            if cod is None: sem_compra += 1
            else:
                b = por_cod[cod]; b["desc"] = sit.get("descricao", ""); b["total"] += 1
                b["pago_t" if p.get("pago") is True else "pago_f"] += 1
            for it in p.get("valores_campos_personalizados", []) or []:
                cn = ((it.get("campo_personalizado") or {}).get("nome") or "").strip()
                if cn:
                    nomes[cn] += 1
                    if (it.get("valor") or "").strip(): preenchidos[cn] += 1
            comp = compra.get("comprador") or {}
            tel, email = comp.get("telefone"), comp.get("email")
            cpf = (comp.get("identificacao") or {}).get("numero")
            tem_tel += bool(tel); tem_email += bool(email); tem_cpf += bool(cpf)
            if len(exemplos) < 6 and (tel or email or cpf):
                exemplos.append((m_tel(tel), m_email(email), m_cpf(cpf)))

    print("\n" + "=" * 70)
    print(f"  TOTAL unicos: {total} | pagos: {total_pago}   (compare com painel: 1348/1343)")
    print("=" * 70)
    if total == 0: return

    print("\n  MAPA DE SITUACOES (sobre a coleta completa)")
    linha()
    print(f"  {'cod':>4} | {'descricao':<28} | {'total':>5} | {'pago=T':>6} | {'pago=F':>6}")
    linha()
    for cod in sorted(por_cod):
        b = por_cod[cod]
        print(f"  {cod:>4} | {b['desc'][:28]:<28} | {b['total']:>5} | {b['pago_t']:>6} | {b['pago_f']:>6}")
    if sem_compra: print(f"   (+{sem_compra} sem `compra` - gratuitos)")
    linha()

    print("\n  CAMPOS PERSONALIZADOS")
    linha()
    for nome, qtd in nomes.most_common():
        flag = "  <- WhatsApp?" if any(k in nome.lower() for k in ("whats","celular","telefone")) else ""
        print(f"   - {nome[:60]:<60} aparece={qtd:>5} preenchido={preenchidos[nome]:>5}{flag}")
    if not nomes: print("   (nenhum)")
    linha()

    print("\n  COMPRADOR")
    linha()
    print(f"   telefone {tem_tel}/{total} | email {tem_email}/{total} | CPF {tem_cpf}/{total}")
    for t, e, c in exemplos: print(f"     - {t} | {e} | {c}")
    linha()

    cand = sorted(cod for cod, b in por_cod.items() if b["pago_t"] > 0 and b["pago_f"] == 0)
    amb = sorted(cod for cod, b in por_cod.items() if b["pago_t"] > 0 and b["pago_f"] > 0)
    print(f"\n  situacoes_pagas (sobre 100% dos dados): {cand or '(use pago=true)'}"
          + (f"   [!] ambiguos: {amb}" if amb else ""))
    print("=" * 70 + "\n  Saida mascarada - pode me mandar.\n")


if __name__ == "__main__":
    main()
