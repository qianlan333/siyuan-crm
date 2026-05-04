#!/usr/bin/env bash
set -euo pipefail

DB_PATH="/home/ubuntu/极简 crm/data.sqlite3"
BACKUP_DIR="/home/ubuntu/backups/openclaw"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_PATH="${BACKUP_DIR}/data-${TIMESTAMP}.sqlite3"

mkdir -p "${BACKUP_DIR}"

python3 - "${DB_PATH}" "${BACKUP_PATH}" <<'PY'
import sqlite3
import sys

source_path = sys.argv[1]
backup_path = sys.argv[2]

source = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
dest = sqlite3.connect(backup_path)
with dest:
    source.backup(dest)
source.close()
dest.close()
PY

find "${BACKUP_DIR}" -type f -name 'data-*.sqlite3' -mtime +7 -delete
echo "backup created: ${BACKUP_PATH}"
