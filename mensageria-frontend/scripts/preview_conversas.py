#!/usr/bin/env python3
"""preview_conversas.py — HTML estático do redesign de Conversas para revisão.

Existe porque o servidor de produção não tem browser headless, e instalar Chrome
só para tirar screenshot seria invasivo. Reproduz a tela com a MESMA paleta e a
mesma estrutura, populada com dados REAIS lidos do banco (somente leitura).

Os estados do agente de IA (badge 🤖 IA, nota [LEAD PÓS], banner de sandbox)
ainda não existem em produção — o agente nunca foi ligado. Eles aparecem numa
seção à parte, explicitamente marcada como SIMULADA, para não passar por dado
real.

Uso: /home/ubuntu/mensageria/.venv/bin/python scripts/preview_conversas.py
Saída: preview-conversas.html (não versionado)
"""
from __future__ import annotations

import html
import subprocess
import sys
from pathlib import Path

SAIDA = Path(__file__).resolve().parents[1] / "preview-conversas.html"

# Paleta — os mesmos valores de .wa-theme em globals.css.
C = {
    "bg": "#0b141a", "card": "#111b21", "sec": "#202c33", "pop": "#233138",
    "bd": "#2a3942", "muted": "#182229", "pri": "#005c4b", "acc": "#53bdeb",
    "fg": "#e9edef", "mfg": "#8696a0", "empty": "#222e35", "check": "#b3d1cb",
}
GRAD = ["#10b981,#047857", "#14b8a6,#0f766e", "#0ea5e9,#0369a1",
        "#8b5cf6,#6d28d9", "#d946ef,#a21caf", "#f59e0b,#b45309", "#f43f5e,#be123c"]


def sql(q: str) -> list[list[str]]:
    r = subprocess.run(
        ["docker", "exec", "postgres", "psql", "-U", "evolution", "-d", "evolution",
         "-tAF", "\x1f", "-c", q],
        capture_output=True, text=True, check=True,
    )
    return [ln.split("\x1f") for ln in r.stdout.strip().split("\n") if ln.strip()]


def grad(seed: str) -> str:
    h = 0
    for ch in seed:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return GRAD[h % len(GRAD)]


def iniciais(nome: str) -> str:
    p = [x for x in nome.split() if x]
    if not p:
        return "?"
    return (p[0][0] + p[-1][0]).upper() if len(p) > 1 else p[0][:2].upper()


def mask_tel(wa: str) -> str:
    d = "".join(c for c in wa if c.isdigit())
    if len(d) < 10:
        return wa
    return f"+{d[:2]} {d[2:4]} {d[4:-4]}-****"


def e(s) -> str:
    return html.escape(str(s or ""))


def avatar(nome: str, size: int) -> str:
    g = grad(nome)
    fs = int(size / 3.2)
    return (f'<div style="width:{size}px;height:{size}px;border-radius:50%;'
            f'background:linear-gradient(135deg,{g});display:flex;align-items:center;'
            f'justify-content:center;color:#fff;font-weight:600;font-size:{fs}px;'
            f'flex-shrink:0">{e(iniciais(nome))}</div>')


def main() -> int:
    contatos = sql("""
        select c.id, coalesce(nullif(c.name,''), c.wa_id), c.wa_id, c.lead_status,
               c.ai_active, coalesce(c.channel_id,0),
               coalesce((select string_agg(t.name||'~'||t.color, ',')
                         from mensageria.contact_tag_links l
                         join mensageria.contact_tags t on t.id=l.tag_id
                         where l.contact_id=c.id), ''),
               coalesce(to_char(c.last_inbound_at,'DD/MM HH24:MI'),'')
        from mensageria.contacts c
        where exists (select 1 from mensageria.messages m where m.contact_wa_id=c.wa_id)
        order by c.updated_at desc nulls last limit 9
    """)
    if not contatos:
        print("[X] sem contatos com mensagens", file=sys.stderr)
        return 1

    alvo = max(contatos, key=lambda r: int(sql(
        f"select count(*) from mensageria.messages where contact_wa_id='{r[2]}'")[0][0]))
    msgs = sql(f"""
        select direction, coalesce(content,''), to_char(timestamp,'HH24:MI'),
               status, message_type, sent_by_ai
        from mensageria.messages where contact_wa_id='{alvo[2]}'
        order by timestamp asc limit 12
    """)

    # ---------- coluna 1: lista ----------
    itens = []
    for cid, nome, wa, lead, ai, ch, tags, hora in contatos:
        chips = ""
        for t in [x for x in tags.split(",") if x]:
            n, _, cor = t.partition("~")
            chips += (f'<span style="background:{C["bd"]};color:{C["mfg"]};padding:2px 6px;'
                      f'border-radius:4px;font-size:10px;margin-right:4px">{e(n)}</span>')
        itens.append(f"""
        <div style="display:flex;gap:12px;padding:12px;border-bottom:1px solid {C['bd']}99;align-items:flex-start">
          {avatar(nome, 49)}
          <div style="min-width:0;flex:1">
            <div style="display:flex;justify-content:space-between;gap:8px">
              <span style="font-size:15px;color:{C['fg']};white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{e(nome)}</span>
              <span style="font-size:11px;color:{C['mfg']};flex-shrink:0">{e(hora)}</span>
            </div>
            <div style="font-size:13px;color:{C['mfg']};margin-top:2px">{e(mask_tel(wa))}</div>
            {'<div style="margin-top:4px">' + chips + '</div>' if chips else ''}
          </div>
        </div>""")

    # ---------- coluna 2: thread ----------
    balões = [f'<div style="display:flex;justify-content:center;padding:8px 0">'
              f'<span style="background:{C["muted"]};color:{C["mfg"]};padding:6px 12px;'
              f'border-radius:8px;font-size:12px">Hoje</span></div>']
    for direc, cont, hora, st, mtype, ai in msgs:
        out = direc == "outbound"
        if cont.startswith("local:") or mtype in ("image", "audio", "video", "document", "sticker"):
            corpo = (f'<div style="background:#00000033;padding:6px 8px;border-radius:6px;'
                     f'font-size:12px">📎 {e(mtype or "mídia")}</div>')
        else:
            corpo = e(cont[:220]) or f"[{e(mtype)}]"
        tick = ""
        if out:
            cor = C["acc"] if st == "read" else C["check"]
            tick = f'<span style="color:{cor};font-size:12px">✓✓</span>' if st in ("read", "delivered") else \
                   f'<span style="color:{C["check"]};font-size:12px">✓</span>'
        balões.append(f"""
        <div style="display:flex;justify-content:{'flex-end' if out else 'flex-start'};margin-bottom:6px">
          <div style="max-width:70%;padding:6px 10px;font-size:14.2px;line-height:19px;
               background:{C['pri'] if out else C['sec']};color:{C['fg']};
               border-radius:8px;border-top-{'right' if out else 'left'}-radius:0">
            {corpo}
            <div style="display:flex;justify-content:flex-end;gap:4px;margin-top:2px;
                 font-size:11px;color:{'#ffffff99' if out else C['mfg']}">{e(hora)}{tick}</div>
          </div>
        </div>""")

    nome_alvo = alvo[1]
    html_doc = f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<title>Preview — redesign de Conversas</title>
<style>
 body{{margin:0;background:#0f172a;color:{C['fg']};font-family:Inter,system-ui,sans-serif}}
 h2{{font-size:15px;margin:28px 16px 8px;color:#94a3b8;font-weight:600}}
 .shell{{display:flex;height:640px;margin:0 16px;border:1px solid {C['bd']};
        border-radius:10px;overflow:hidden}}
 .col1{{width:350px;background:{C['card']};border-right:1px solid {C['bd']};
        display:flex;flex-direction:column;flex-shrink:0}}
 .col2{{flex:1;background:{C['bg']};display:flex;flex-direction:column;min-width:0}}
 .col3{{width:300px;background:{C['card']};border-left:1px solid {C['bd']};
        flex-shrink:0;overflow:auto}}
 .hd{{background:{C['sec']};padding:12px;border-bottom:1px solid {C['bd']};
      display:flex;align-items:center;gap:12px}}
 .lbl{{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:{C['mfg']};
       font-weight:600;margin-bottom:8px}}
 .box{{background:{C['sec']};border:1px solid {C['bd']};border-radius:10px;padding:10px;font-size:13px}}
 .chip{{padding:5px 10px;border-radius:999px;font-size:11px;background:{C['muted']};color:{C['mfg']}}}
 .nota{{font-size:11px;color:#64748b;margin:6px 16px 0}}
</style></head><body>

<h2>1 · LISTA + THREAD + PAINEL — dados reais do banco (telefones mascarados)</h2>
<div class="shell">
  <div class="col1">
    <div style="padding:12px;border-bottom:1px solid {C['bd']}">
      <div style="background:{C['sec']};border-radius:8px;padding:8px 12px;color:{C['mfg']};font-size:13px">🔍 Pesquisar conversa…</div>
      <div style="display:flex;gap:6px;margin-top:10px">
        <span class="chip" style="background:{C['acc']};color:{C['card']}">Todos</span>
        <span class="chip">WhatsApp</span><span class="chip">Instagram</span>
      </div>
    </div>
    <div style="flex:1;overflow:auto">{''.join(itens)}</div>
  </div>

  <div class="col2">
    <div class="hd">
      {avatar(nome_alvo, 36)}
      <div style="flex:1;min-width:0">
        <div style="font-size:14px;font-weight:600">{e(nome_alvo)}</div>
        <div style="font-size:12px;color:{C['mfg']}">{e(mask_tel(alvo[2]))} · {e(alvo[3])}</div>
      </div>
    </div>
    <div style="flex:1;overflow:auto;padding:16px">{''.join(balões)}</div>
    <div style="background:#f59e0b1a;border-top:1px solid #f59e0b4d;color:#fcd34d;
         padding:8px 12px;font-size:11px">
      Sem resposta do contato há mais de 24h — fora da janela, a Meta pode rejeitar
      texto livre. Para reabrir, use um <u>template aprovado</u>.
    </div>
    <div style="background:{C['sec']};padding:12px;display:flex;gap:8px;align-items:center">
      <span style="color:{C['mfg']}">📎</span>
      <div style="flex:1;background:{C['bd']};border-radius:8px;padding:9px 12px;
           color:{C['mfg']};font-size:14px">Digite uma mensagem</div>
      <div style="width:42px;height:42px;border-radius:50%;background:{C['acc']};
           display:flex;align-items:center;justify-content:center">➤</div>
    </div>
  </div>

  <div class="col3">
    <div style="padding:12px;border-bottom:1px solid {C['bd']};font-size:14px;font-weight:600">Detalhes do contato</div>
    <div style="padding:16px">
      <div class="lbl">Etapa do funil</div><div class="box">{e(alvo[3] or 'novo')}</div>
      <div class="lbl" style="margin-top:18px">Atendente</div><div class="box">Sem atendente</div>
      <div class="lbl" style="margin-top:18px">Tags</div><div class="box">Sem tags</div>
      <div class="lbl" style="margin-top:18px">Notas</div>
      <div class="box" style="min-height:70px;color:{C['mfg']}">Anotações internas…</div>
    </div>
  </div>
</div>
<p class="nota">Banner de 24h aparece porque o último inbound deste contato passou de 24h — e só em canal oficial.</p>

<h2>2 · ESTADOS DO AGENTE DE IA — ⚠️ SIMULADO (não existe em produção ainda: 0 mensagens com sent_by_ai, 0 notas [LEAD PÓS], agent_enabled=false)</h2>
<div style="margin:0 16px">
  <div style="background:#f59e0b1a;border:1px solid #f59e0b4d;color:#fcd34d;
       padding:8px 16px;font-size:12px;border-radius:8px 8px 0 0">
    🧪 <b>Agente em modo sandbox</b> — a IA só responde 2 contatos de teste. Os demais
    não recebem resposta automática, mesmo com o canal habilitado.
  </div>
  <div class="shell" style="margin:0;border-radius:0 0 10px 10px;height:auto">
    <div class="col1" style="padding:12px">
      <div style="display:flex;gap:6px;margin-bottom:12px">
        <span class="chip" style="background:{C['acc']};color:{C['card']}">✨ Atendidas pela IA (3)</span>
      </div>
      <div style="display:flex;gap:12px;align-items:flex-start">
        {avatar('Maria Souza', 49)}
        <div style="flex:1">
          <div style="font-size:15px">Maria Souza</div>
          <div style="font-size:13px;color:{C['mfg']}">+55 11 9xxxx-****</div>
        </div>
      </div>
    </div>
    <div class="col2">
      <div class="hd">
        {avatar('Maria Souza', 36)}
        <div style="flex:1">
          <div style="font-size:14px;font-weight:600;display:flex;gap:8px;align-items:center">
            Maria Souza
            <span style="background:{C['acc']}26;color:{C['acc']};padding:2px 8px;
                  border-radius:999px;font-size:10px;font-weight:500">✨ IA ativa</span>
          </div>
          <div style="font-size:12px;color:{C['mfg']}">+55 11 9xxxx-**** · interessado</div>
        </div>
        <div style="background:{C['sec']};border:1px solid {C['bd']};padding:6px 12px;
             border-radius:8px;font-size:13px">👤 Assumir conversa</div>
      </div>
      <div style="padding:16px">
        <div style="display:flex;justify-content:flex-start;margin-bottom:6px">
          <div style="max-width:70%;padding:6px 10px;background:{C['sec']};border-radius:8px;
               border-top-left-radius:0;font-size:14.2px">Quanto custa a pós de TEA?
            <div style="text-align:right;font-size:11px;color:{C['mfg']};margin-top:2px">09:12</div></div>
        </div>
        <div style="display:flex;justify-content:flex-end">
          <div style="max-width:70%;padding:6px 10px;background:{C['pri']};border-radius:8px;
               border-top-right-radius:0;font-size:14.2px">
            A pós em TEA tem valor cheio de R$ 6.800,00 e promocional de R$ 5.100,00 à vista, ou 20x de R$ 255.
            <div style="display:flex;justify-content:space-between;gap:6px;margin-top:2px;font-size:11px;color:#ffffff99">
              <span style="background:#00000033;padding:1px 5px;border-radius:4px">🤖 IA</span>
              <span>09:12 <span style="color:{C['acc']}">✓✓</span></span>
            </div>
          </div>
        </div>
      </div>
    </div>
    <div class="col3" style="padding:16px">
      <div class="lbl">Notas</div>
      <div style="border:1px solid {C['acc']}66;background:{C['acc']}1a;color:{C['acc']};
           border-radius:6px;padding:6px 8px;font-size:11px;margin-bottom:4px">
        <b>🎓 Lead de pós</b> Psicologia Hospitalar: quer saber valor e início
      </div>
      <div style="border:1px solid #f59e0b66;background:#f59e0b1a;color:#fcd34d;
           border-radius:6px;padding:6px 8px;font-size:11px">
        <b>🤖→👤 Handoff</b> pedido explícito de atendimento humano
      </div>
      <div class="box" style="margin-top:8px;min-height:60px;color:{C['mfg']}">Anotações internas…</div>
    </div>
  </div>
</div>
<p class="nota">Tudo no bloco 2 é ilustrativo. Em produção, esses elementos só aparecem quando existirem
mensagens com <code>sent_by_ai</code>, notas <code>[LEAD PÓS]</code> e a allowlist de sandbox preenchida.</p>
<div style="height:32px"></div>
</body></html>"""

    SAIDA.write_text(html_doc)
    print(f"→ {SAIDA}  ({len(html_doc)//1024} KB)")
    print(f"  {len(contatos)} contatos reais · thread de '{nome_alvo}' com {len(msgs)} mensagens")
    return 0


if __name__ == "__main__":
    sys.exit(main())
