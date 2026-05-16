#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/_postgres_env.sh"
require_database_url

BACKUP_FILE="${1:-}"
if [[ -z "${BACKUP_FILE}" || ! -f "${BACKUP_FILE}" ]]; then
  echo "usage: DATABASE_URL=... $0 /path/to/backup.dump"
  exit 1
fi

pg_restore --clean --if-exists --no-owner --no-privileges -d "${DATABASE_URL}" "${BACKUP_FILE}"
echo "restore completed from: ${BACKUP_FILE}"
