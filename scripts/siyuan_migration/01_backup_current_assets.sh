#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/home/ubuntu/backups/siyuan-aicrm-migration}"
ENV_FILE="${ENV_FILE:-/home/ubuntu/.openclaw-wecom-pg.env}"
APP_DIR="${APP_DIR:-$(pwd)}"
timestamp="$(date +%Y%m%d-%H%M%S)"

pass() { printf 'PASS %s\n' "$*"; }
fail() { printf 'FAIL %s\n' "$*"; exit 1; }

mkdir -p "${BACKUP_DIR}"
backup_abs="$(cd "${BACKUP_DIR}" && pwd)"
app_abs="$(cd "${APP_DIR}" && pwd)"
case "${backup_abs}/" in
  "${app_abs}/"*) fail "BACKUP_DIR must not be inside the repository: ${backup_abs}" ;;
esac
chmod 700 "${backup_abs}"

[[ -f "${ENV_FILE}" ]] || fail "ENV_FILE not found: ${ENV_FILE}"
set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a
[[ -n "${DATABASE_URL:-}" ]] || fail "DATABASE_URL is not set after sourcing ${ENV_FILE}"

dump_file="${backup_abs}/siyuan-current-${timestamp}.dump"
env_backup="${backup_abs}/$(basename "${ENV_FILE}").${timestamp}"
assets_archive="${backup_abs}/siyuan-assets-${timestamp}.tar.gz"

pg_dump "${DATABASE_URL}" --format=custom --file="${dump_file}"
chmod 600 "${dump_file}"
pass "database backup written to ${dump_file}"

cp "${ENV_FILE}" "${env_backup}"
chmod 600 "${env_backup}"
pass "env backup written to ${env_backup}"

(
  cd "${app_abs}"
  shopt -s nullglob
  assets=(WW_verify_*.txt MP_verify_*.txt uploads static/uploads instance *.pem *.key)
  if (( ${#assets[@]} > 0 )); then
    tar -czf "${assets_archive}" "${assets[@]}"
    chmod 600 "${assets_archive}"
    pass "file asset backup written to ${assets_archive}"
  else
    pass "no verification/upload/instance/private-key assets found under ${app_abs}"
  fi
)

pass "backup completed in ${backup_abs}"
