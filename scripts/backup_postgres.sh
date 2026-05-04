#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_URL is required"
  exit 1
fi

BACKUP_DIR="/home/ubuntu/backups/openclaw-postgres"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_PATH="${BACKUP_DIR}/openclaw-${TIMESTAMP}.dump"

mkdir -p "${BACKUP_DIR}"
pg_dump "${DATABASE_URL}" -Fc -f "${BACKUP_PATH}"
find "${BACKUP_DIR}" -type f -name 'openclaw-*.dump' -mtime +7 -delete
echo "backup created: ${BACKUP_PATH}"
