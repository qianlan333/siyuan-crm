#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/_postgres_env.sh"
require_database_url

BACKUP_DIR="/home/ubuntu/backups/openclaw-postgres"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_PATH="${BACKUP_DIR}/openclaw-${TIMESTAMP}.dump"

mkdir -p "${BACKUP_DIR}"
pg_dump "${DATABASE_URL}" -Fc -f "${BACKUP_PATH}"
find "${BACKUP_DIR}" -type f -name 'openclaw-*.dump' -mtime +7 -delete
echo "backup created: ${BACKUP_PATH}"
