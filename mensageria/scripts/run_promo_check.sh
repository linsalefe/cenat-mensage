#!/usr/bin/env bash
# run_promo_check.sh — roda a auditoria do catálogo do agente e registra em log
# persistente, com o exit code.
#
# Usado por `mensageria-promo-check.service` (timer diário 00:20, TZ do host =
# America/Sao_Paulo). Também pode rodar à mão:
#
#   bash scripts/run_promo_check.sh                    # hoje
#   bash scripts/run_promo_check.sh --data 2026-08-01  # simula uma data
#
# Exit code é o do script Python (0 = consistente, 1 = achou problema) e é
# propagado para o systemd de propósito: um exit 1 marca a unit como failed, o
# que faz o problema aparecer em `systemctl list-units --failed`.
#
# NÃO usa `set -e`: precisamos capturar o exit 1 do Python em vez de abortar.
set -uo pipefail

REPO="/home/ubuntu/mensageria"
PY="$REPO/.venv/bin/python"
LOG_DIR="$REPO/logs"
LOG="$LOG_DIR/promo_check.log"
MAX_LINES="${MAX_LINES:-5000}"   # rotação simples, o log cresce ~40 linhas/dia

mkdir -p "$LOG_DIR"

STAMP="$(date '+%F %T %z')"

# `cd` no repo: app/config.py usa env_file=".env" (caminho relativo).
cd "$REPO" || { echo "[X] não consegui entrar em $REPO" >&2; exit 2; }

OUT="$("$PY" "$REPO/scripts/checar_promo_pos.py" "$@" 2>&1)"
RC=$?

{
    echo "===== $STAMP — checar_promo_pos.py $* ====="
    printf '%s\n' "$OUT"
    echo "----- exit=$RC -----"
    echo
} >> "$LOG"

# stdout também, para o journal do systemd e para execução manual.
printf '%s\n' "$OUT"
echo "exit=$RC (log: $LOG)"

if [ "$(wc -l < "$LOG")" -gt "$MAX_LINES" ]; then
    tail -n "$MAX_LINES" "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fi

exit "$RC"
