#!/usr/bin/env python3
"""
testar_doity.py - diagnostico API Doity (cobertura / backfill / range)
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timedelta

BASE_URL = os.getenv("DOITY_BASE_URL", "https://api.doity.com.br/public/v1").rstrip("/")
TOKEN = os.getenv("DOITY_TOKEN", "")


def _ids(raw): return [x.strip() for x in raw.split(",") if x.strip()]
EVENTO_IDS = _ids(os.getenv("DOITY_EVENTO_IDS", "") or os.getenv("DOITY_EVENTO_ID", ""))
LOOKBACK_DIAS = int(os.getenv("DOITY_LOOKBACK_DIAS", "120"))
DESDE = os.getenv("DOITY_DESDE", "").strip()
ATE = os.getenv("DOITY_ATE", "").strip()
MAX_PAGINAS = int(os.getenv("DOITY_MAX_PAGINAS", "120"))
LIMIT = int(os.getenv("DOITY_LIMIT", "50"))


def _request(path, params=None):
    qs = ("?" + urllib.parse.urlencode(params)) if params else ""
    req = urllib.request.Request(f"{BASE_URL}{path}{qs}", headers={
        "Accept": "application/json", "Authorization": f"Bearer {TOKEN}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8")), r.status


def get_strict(path, params=None):
    try:
        return _request(path, params)[0]
    except urllib.error.HTTPError as e:
        print(f"\n[X] HTTP {e.code}: {e.read().decode('utf-8','ignore')[:200]}"); sys.exit(1)
    except urllib.error.URLError as e:
        print(f"\n[X] Rede: {e.reason}"); sys.exit(1)


def try_get(path, params=None):
    try:
        return _request(path, params)
    except urllib.error.HTTPError as e:
        return None, e.code
    except urllib.error.URLError:
        return None, -1


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


def coletar(evento_id, filtro_valor):
    todos, seen, page, capou, dupes = [], set(), 1, False, 0
    primeira_pag = None
    while True:
        params = {"ativo": 1, "sort": "modified", "direction": "asc",
                  "page": page, "limit": LIMIT, "data_atualizacao": filtro_valor}
        path = f"/eventos/{evento_id}/participantes"
        data, code = try_get(path, params)
        if data is None and code == 500:
            params.pop("sort", None)
            data, code = try_get(path, params)
        if data is None:
            print(f"   [!] pag {page}: HTTP {code} - parando ({len(todos)} unicos ate aqui).")
            break
        pag = data.get("pagination", {}) or {}
        if primeira_pag is None:
            primeira_pag = pag
        for p in data.get("participantes", []) or []:
            pid = p.get("id")
            if pid in seen:
                dupes += 1; continue
            seen.add(pid); todos.append(p)
        page_count = pag.get("pageCount") or 1
        if page >= page_count: break
        if page >= MAX_PAGINAS: capou = True; break
        page += 1
        time.sleep(0.25)
    return todos, capou, dupes, primeira_pag


def linha(c="-"): print(c * 70)


def main():
    if not TOKEN:
        print("Defina DOITY_TOKEN."); sys.exit(1)

    if DESDE:
        filtro = f"{DESDE}|{ATE}" if ATE else DESDE
        modo = f"range '{filtro}'" if ATE else f"desde '{DESDE}'"
    else:
        filtro = (datetime.now() - timedelta(days=LOOKBACK_DIAS)).strftime("%Y-%m-%d %H:%M:%S")
        modo = f"janela relativa {LOOKBACK_DIAS}d (desde {filtro})"

    ids = EVENTO_IDS
    if not ids:
        print("Defina DOITY_EVENTO_IDS."); sys.exit(1)

    print("\n" + "=" * 70)
    print("  DIAGNOSTICO DOITY - cobertura")
    print(f"  filtro data_atualizacao: {modo}")
    print("=" * 70)

    por_cod = defaultdict(lambda: {"desc": "", "total": 0, "pago_t": 0, "pago_f": 0})
    nomes, preenchidos = Counter(), Counter()
    tem_tel = tem_email = tem_cpf = sem_compra = 0
    exemplos = []
    total = total_pago = 0

    for eid in ids:
        ev = get_strict(f"/eventos/{eid}").get("evento", {})
        print(f"\n>> Evento {eid} - {ev.get('nome','?')[:48]}")
        parts, capou, dupes, pag1 = coletar(eid, filtro)
        n = len(parts)
        pagos = sum(1 for p in parts if p.get("pago") is True)
        total += n; total_pago += pagos

        if pag1:
            pc = pag1.get("pageCount"); pp = pag1.get("perPage")
            est = (pc * pp) if (pc and pp) else "?"
            print(f"   API pagination -> pageCount={pc} perPage={pp}  (~ total na janela: {est})")
        print(f"   coletados unicos: {n} | pagos: {pagos} | duplicados ignorados: {dupes}"
              + ("  *CAPOU em MAX_PAGINAS" if capou else ""))

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
        time.sleep(0.2)

    print("\n" + "=" * 70)
    print(f"  TOTAL coletado (unicos): {total} | pagos: {total_pago}")
    print("  >>> COMPARE com o painel (Total Inscritos / Confirmados) <<<")
    print("=" * 70)
    if total == 0:
        print("\n[!] Zero. Recue DOITY_DESDE (evento mais antigo) ou cheque a data."); return

    print("\n  MAPA DE SITUACOES  ->  cruzado com `pago`")
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

    print("\n  COMPRADOR (chaves de match)")
    linha()
    print(f"   telefone {tem_tel}/{total} | email {tem_email}/{total} | CPF {tem_cpf}/{total}")
    for t, e, c in exemplos: print(f"     - {t} | {e} | {c}")
    linha()

    print("\n  RECOMENDACAO")
    linha()
    cand = sorted(cod for cod, b in por_cod.items() if b["pago_t"] > 0 and b["pago_f"] == 0)
    amb = sorted(cod for cod, b in por_cod.items() if b["pago_t"] > 0 and b["pago_f"] > 0)
    print(f"   situacoes_pagas: {cand or '(use pago=true)'}")
    if amb: print(f"   [!] ambiguos: {amb}")
    print("=" * 70 + "\n  Saida mascarada - pode me mandar.\n")


if __name__ == "__main__":
    main()
