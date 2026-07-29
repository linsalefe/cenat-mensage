#!/usr/bin/env bash
# backup_db.sh — dump do schema `mensageria` (Postgres no container docker `postgres`).
# Uso: bash scripts/backup_db.sh
# Cron sugerido (03h diário):
#   0 3 * * * /usr/bin/bash /home/ubuntu/mensageria/scripts/backup_db.sh >> /var/log/mensageria-backup.log 2>&1
set -euo pipefail

CONTAINER="${PG_CONTAINER:-postgres}"
DB_USER="${PG_USER:-evolution}"
DB_NAME="${PG_DB:-evolution}"
SCHEMA="${PG_SCHEMA:-mensageria}"
BACKUP_DIR="${BACKUP_DIR:-/home/ubuntu/backups/mensageria}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"

mkdir -p "$BACKUP_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$BACKUP_DIR/mensageria-${STAMP}.sql.gz"

# --schema restringe ao schema do projeto (NÃO inclui o schema `public` do Evolution).
docker exec "$CONTAINER" pg_dump -U "$DB_USER" -d "$DB_NAME" \
  --schema="$SCHEMA" --no-owner --no-privileges \
  | gzip -c > "$OUT"

SIZE="$(du -h "$OUT" | cut -f1)"
echo "[$(date '+%F %T')] backup ok: $OUT ($SIZE)"

# Retenção: remove dumps com mais de RETENTION_DAYS dias.
find "$BACKUP_DIR" -name 'mensageria-*.sql.gz' -mtime "+${RETENTION_DAYS}" -delete
echo "[$(date '+%F %T')] retenção aplicada (>${RETENTION_DAYS}d removidos)"
