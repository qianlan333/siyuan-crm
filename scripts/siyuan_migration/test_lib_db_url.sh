#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib_db_url.sh"

assert_normalized() {
  local case_name="$1"
  local input_url="$2"
  local expected_url="$3"
  local actual_url
  actual_url="$(normalize_pg_cli_url "${input_url}")"
  if [[ "${actual_url}" != "${expected_url}" ]]; then
    printf 'FAIL normalize_pg_cli_url mismatch for %s\n' "${case_name}" >&2
    exit 1
  fi
}

assert_fails() {
  local case_name="$1"
  local input_url="${2:-}"
  if normalize_pg_cli_url "${input_url}" >/dev/null 2>&1; then
    printf 'FAIL normalize_pg_cli_url unexpectedly accepted %s\n' "${case_name}" >&2
    exit 1
  fi
}

assert_normalized 'psycopg' 'postgresql+psycopg://u:p@h:5432/db' 'postgresql://u:p@h:5432/db'
assert_normalized 'psycopg2' 'postgresql+psycopg2://u:p@h:5432/db' 'postgresql://u:p@h:5432/db'
assert_normalized 'postgresql' 'postgresql://u:p@h:5432/db' 'postgresql://u:p@h:5432/db'
assert_normalized 'postgres' 'postgres://u:p@h:5432/db' 'postgres://u:p@h:5432/db'
assert_fails 'empty input' ''
assert_fails 'unsupported scheme' 'mysql://u:p@h:3306/db'

printf 'PASS lib_db_url normalize_pg_cli_url tests\n'
