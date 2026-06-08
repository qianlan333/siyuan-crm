#!/usr/bin/env bash
set -euo pipefail

DUMP_FILE="${DUMP_FILE:-}"
STAGING_DATABASE_URL="${STAGING_DATABASE_URL:-}"
CLEAN="${CLEAN:-true}"

pass() { printf 'PASS %s\n' "$*"; }
fail() { printf 'FAIL %s\n' "$*"; exit 1; }

[[ -n "${DUMP_FILE}" ]] || fail "DUMP_FILE is required"
[[ -f "${DUMP_FILE}" ]] || fail "DUMP_FILE not found: ${DUMP_FILE}"
[[ -n "${STAGING_DATABASE_URL}" ]] || fail "STAGING_DATABASE_URL is required and must be explicit"

if [[ "${CLEAN}" == "true" ]]; then
  pg_restore --clean --if-exists --no-owner --dbname="${STAGING_DATABASE_URL}" "${DUMP_FILE}"
else
  pg_restore --no-owner --dbname="${STAGING_DATABASE_URL}" "${DUMP_FILE}"
fi

pass "restored ${DUMP_FILE} to explicit staging database"
