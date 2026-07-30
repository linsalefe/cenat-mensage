#!/usr/bin/env bash
# turnos_agente.sh — acompanhamento dos turnos do agente de IA (somente leitura).
#
# Uso:
#   bash scripts/turnos_agente.sh              # últimos 20 turnos
#   bash scripts/turnos_agente.sh 50           # últimos 50
#   bash scripts/turnos_agente.sh 20 --erros   # só turnos que falharam
#   bash scripts/turnos_agente.sh --resumo     # agregado do dia (custo/latência/volume)
#   bash scripts/turnos_agente.sh --seguir     # acompanha ao vivo (poll 5s, Ctrl-C sai)
#
# ⚠️ agent_turn_logs.created_at é naive UTC; messages.timestamp é naive UTC-3.
#    As colunas "hora" abaixo já vêm convertidas para São Paulo.
set -uo pipefail
PSQL=(docker exec postgres psql -U evolution -d evolution)
N="${1:-20}"; [[ "$N" =~ ^[0-9]+$ ]] || N=20
MODO="${2:-${1:-}}"

case "$MODO" in
--resumo)
  "${PSQL[@]}" -c "
    select date_trunc('hour', l.created_at - interval '3 hours') as hora_sp,
           count(*) filter (where l.direction='inbound')  as recebidos,
           count(*) filter (where l.direction='outbound') as respondidos,
           count(*) filter (where l.guardrail->>'error' is not null) as erros,
           count(*) filter (where (l.guardrail->>'out_ok')::bool is false) as guardrail_barrou,
           sum(l.tokens_in) as tok_in, sum(l.tokens_out) as tok_out,
           round(avg(l.latency_ms) filter (where l.latency_ms is not null)) as lat_media_ms
    from mensageria.agent_turn_logs l
    where l.created_at > now() - interval '24 hours'
    group by 1 order by 1 desc;"
  exit 0;;
--erros)
  "${PSQL[@]}" -x -c "
    select l.id, to_char(l.created_at - interval '3 hours','DD/MM HH24:MI') as hora_sp,
           s.contact_wa_id, l.guardrail->>'error' as erro,
           left(l.guardrail->>'traceback', 600) as traceback
    from mensageria.agent_turn_logs l
    left join mensageria.agent_sessions s on s.id = l.session_id
    where l.guardrail->>'error' is not null
    order by l.id desc limit $N;"
  exit 0;;
esac

Q="
  select l.id,
         to_char(l.created_at - interval '3 hours','DD/MM HH24:MI:SS') as hora_sp,
         l.session_id as sess, s.contact_wa_id as contato, l.direction as dir,
         coalesce(l.tokens_in,0) as tk_in, coalesce(l.tokens_out,0) as tk_out,
         l.latency_ms as ms,
         case when l.guardrail->>'error' is not null then 'ERRO'
              when (l.guardrail->>'out_ok')::bool is false then 'BARRADO'
              when l.guardrail is null then '-' else 'ok' end as guard,
         coalesce((select string_agg(x->>'name',' > ')
                   from jsonb_array_elements(l.tool_calls) x
                   where jsonb_typeof(l.tool_calls)='array'),'-') as tools,
         left(replace(coalesce(l.content,''), chr(10), ' / '), 90) as texto
  from mensageria.agent_turn_logs l
  left join mensageria.agent_sessions s on s.id = l.session_id
  order by l.id desc limit $N;"

if [ "${MODO}" = "--seguir" ]; then
  while true; do clear; date '+%H:%M:%S'; "${PSQL[@]}" -c "$Q"; sleep 5; done
else
  "${PSQL[@]}" -c "$Q"
fi
