#!/usr/bin/env bash
# Daily SQLite backup. Run by cron as root.
# Per PRD §5.8.4.
set -euo pipefail

APP_DIR=/opt/bepors-bot
BACKUP_DIR=/var/backups/bepors
DB="${APP_DIR}/data/bepors.db"

mkdir -p "${BACKUP_DIR}"

if [ ! -f "${DB}" ]; then
  echo "[backup] db not found: ${DB}"
  exit 0
fi

STAMP=$(date -u +"%Y%m%d-%H%M%S")
OUT="${BACKUP_DIR}/bepors-${STAMP}.db"

# Use sqlite3 backup API (safe with WAL mode, no need to stop the service)
sqlite3 "${DB}" ".backup '${OUT}'"
gzip -f "${OUT}"

# Keep last 14 daily backups
ls -1t "${BACKUP_DIR}"/bepors-*.db.gz 2>/dev/null | tail -n +15 | xargs -r rm -f

echo "[backup] ok: ${OUT}.gz"
