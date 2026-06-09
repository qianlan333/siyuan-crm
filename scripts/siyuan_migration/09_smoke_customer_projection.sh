#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:5001}"
SAMPLE_EXTERNAL_USERID="${SAMPLE_EXTERNAL_USERID:-}"
ADMIN_TOKEN="${ADMIN_TOKEN:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

mask_identifier() {
  local value="${1:-}"
  local length="${#value}"
  if [[ -z "$value" ]]; then
    printf ''
  elif (( length <= 4 )); then
    printf '***'
  else
    printf '%s***%s' "${value:0:2}" "${value: -2}"
  fi
}

urlencode() {
  python3 - "$1" <<'PY'
import sys
from urllib.parse import quote

print(quote(sys.argv[1], safe=""))
PY
}

projection_count_check() {
  local cli_url="${PG_CLI_DATABASE_URL:-}"
  if [[ -z "$cli_url" && -n "${DATABASE_URL:-}" ]]; then
    # shellcheck source=lib_db_url.sh
    source "$SCRIPT_DIR/lib_db_url.sh"
    cli_url="$(normalize_pg_cli_url "$DATABASE_URL")"
  fi
  if [[ -z "$cli_url" ]] || ! command -v psql >/dev/null 2>&1; then
    printf 'WARN projection_count skipped; PG_CLI_DATABASE_URL/DATABASE_URL or psql unavailable\n'
    return 0
  fi
  local count
  count="$(psql "$cli_url" -tAc "select count(*) from customer_detail_snapshot_next;" 2>/dev/null || true)"
  if [[ -z "$count" ]]; then
    printf 'WARN projection_count unavailable\n'
  elif [[ "$count" =~ ^[0-9]+$ && "$count" -gt 0 ]]; then
    printf 'PASS projection_count customer_detail_snapshot_next=%s\n' "$count"
  else
    printf 'WARN projection_count customer_detail_snapshot_next=%s\n' "$count"
  fi
}

request() {
  local label="$1"
  local path="$2"
  local display_path="$3"
  local expected_projected="${4:-false}"
  local header_args=()
  if [[ -n "$ADMIN_TOKEN" ]]; then
    header_args=(-H "Authorization: Bearer ${ADMIN_TOKEN}")
  fi
  local status
  status="$(curl -sS -o /tmp/siyuan_customer_projection_smoke_body.$$ -w '%{http_code}' "${header_args[@]}" "${BASE_URL}${path}" || true)"
  if [[ "$status" =~ ^5 ]]; then
    printf 'FAIL %s %s status=%s\n' "$label" "$display_path" "$status"
    rm -f /tmp/siyuan_customer_projection_smoke_body.$$
    return 1
  fi
  if [[ "$expected_projected" == "true" && "$status" =~ ^(400|404)$ ]]; then
    printf 'FAIL %s %s status=%s expected_projected_customer\n' "$label" "$display_path" "$status"
    rm -f /tmp/siyuan_customer_projection_smoke_body.$$
    return 1
  fi
  if [[ "$status" =~ ^(400|401|403|404)$ ]]; then
    printf 'WARN %s %s status=%s\n' "$label" "$display_path" "$status"
  else
    printf 'PASS %s %s status=%s\n' "$label" "$display_path" "$status"
  fi
  rm -f /tmp/siyuan_customer_projection_smoke_body.$$
}

projection_count_check

if [[ -z "$SAMPLE_EXTERNAL_USERID" ]]; then
  printf 'WARN SAMPLE_EXTERNAL_USERID not set; skipped customer/sidebar projected customer API sample\n'
  exit 0
fi

encoded_external_userid="$(urlencode "$SAMPLE_EXTERNAL_USERID")"
masked_external_userid="$(mask_identifier "$SAMPLE_EXTERNAL_USERID")"

request "customer_detail" "/api/customers/${encoded_external_userid}" "/api/customers/${masked_external_userid}" true
request "customer_timeline" "/api/customers/${encoded_external_userid}/timeline" "/api/customers/${masked_external_userid}/timeline" true
request "sidebar_customer_context" "/api/sidebar/customer-context?external_userid=${encoded_external_userid}" "/api/sidebar/customer-context?external_userid=${masked_external_userid}" true
request "sidebar_profile" "/api/sidebar/profile?external_userid=${encoded_external_userid}" "/api/sidebar/profile?external_userid=${masked_external_userid}" true
