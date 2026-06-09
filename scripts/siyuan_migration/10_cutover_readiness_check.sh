#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:5001}"
ENV_FILE="${ENV_FILE:-/home/ubuntu/.openclaw-wecom-pg.env}"
OLD_RELEASE_DIR="${OLD_RELEASE_DIR:-/home/ubuntu/极简 crm}"
NEW_RELEASE_DIR="${NEW_RELEASE_DIR:-$(pwd)}"
CHECK_ENV_FILE="${CHECK_ENV_FILE:-false}"
SAMPLE_SCENE_VALUE="${SAMPLE_SCENE_VALUE:-}"
SAMPLE_EXTERNAL_USERID="${SAMPLE_EXTERNAL_USERID:-}"

failures=0
warnings=0

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

pass() {
  printf 'PASS %s\n' "$*"
}

warn() {
  warnings=$((warnings + 1))
  printf 'WARN %s\n' "$*"
}

fail() {
  failures=$((failures + 1))
  printf 'FAIL %s\n' "$*"
}

check_command() {
  local name="$1"
  if command -v "$name" >/dev/null 2>&1; then
    pass "command_available ${name}"
  else
    fail "command_missing ${name}"
  fi
}

check_path() {
  local label="$1"
  local path="$2"
  if [[ -e "$path" ]]; then
    pass "${label} exists"
  else
    warn "${label} missing path=${path}"
  fi
}

check_script() {
  local path="$1"
  if [[ -f "$path" ]]; then
    pass "script_present ${path}"
  else
    fail "script_missing ${path}"
  fi
}

check_endpoint() {
  local label="$1"
  local path="$2"
  local display_path="${3:-$path}"
  local status
  status="$(curl -sS -o /tmp/siyuan_cutover_readiness_body.$$ -w '%{http_code}' "${BASE_URL}${path}" || true)"
  rm -f /tmp/siyuan_cutover_readiness_body.$$
  if [[ "$status" =~ ^5 ]]; then
    fail "endpoint ${label} ${display_path} status=${status}"
  elif [[ "$status" == "000" ]]; then
    warn "endpoint ${label} ${display_path} unavailable status=${status}"
  elif [[ "$status" =~ ^(302|401|403)$ ]]; then
    warn "endpoint ${label} ${display_path} auth_required_or_redirect status=${status}"
  else
    pass "endpoint ${label} ${display_path} status=${status}"
  fi
}

printf 'siyuan AI-CRM Next cutover readiness check\n'
printf 'BASE_URL=%s\n' "$BASE_URL"
printf 'NEW_RELEASE_DIR=%s\n' "$NEW_RELEASE_DIR"
printf 'OLD_RELEASE_DIR=%s\n' "$OLD_RELEASE_DIR"
printf 'This script is read-only and does not modify DB, systemd, or nginx.\n\n'

check_command git
check_command python3
check_command curl
check_command psql
check_command pg_dump
check_command pg_restore

check_path "env_file" "$ENV_FILE"
check_path "old_release_dir" "$OLD_RELEASE_DIR"
check_path "new_release_dir" "$NEW_RELEASE_DIR"

check_script scripts/siyuan_migration/00_preflight.sh
check_script scripts/siyuan_migration/01_backup_current_assets.sh
check_script scripts/siyuan_migration/02_restore_to_staging_db.sh
check_script scripts/siyuan_migration/03_channel_backfill.sql
check_script scripts/siyuan_migration/04_validate_migration.sql
check_script scripts/siyuan_migration/07_validate_next_blockers.sql
check_script scripts/siyuan_migration/08_validate_customer_projection.sql
check_script scripts/siyuan_migration/09_smoke_customer_projection.sh

if python3 app.py --help >/tmp/siyuan_cutover_app_help.$$ 2>&1; then
  for command_name in health run init-db init-next-schema-safe sync-customer-read-model; do
    if grep -q "$command_name" /tmp/siyuan_cutover_app_help.$$; then
      pass "app_command_present ${command_name}"
    else
      fail "app_command_missing ${command_name}"
    fi
  done
else
  fail "app_help_unavailable"
fi
rm -f /tmp/siyuan_cutover_app_help.$$

if [[ "$CHECK_ENV_FILE" == "true" ]]; then
  warn "CHECK_ENV_FILE is deprecated; this read-only script does not source env files"
fi

if [[ "${CHECK_CURRENT_ENV:-false}" == "true" ]]; then
  for key in \
    DATABASE_URL \
    SECRET_KEY \
    WECOM_CORP_ID \
    WECOM_AGENT_ID \
    WECOM_SECRET \
    WECOM_CONTACT_SECRET \
    WECOM_CALLBACK_TOKEN \
    WECOM_CALLBACK_AES_KEY \
    WECHAT_MP_APP_ID \
    WECHAT_MP_APPID \
    WECHAT_MP_APP_SECRET \
    ADMIN_LOGIN_REDIRECT_URI \
    CRM_API_TOKEN \
    MCP_BEARER_TOKEN \
    SIDEBAR_THIRD_PARTY_API_TOKEN
  do
    if [[ -n "${!key:-}" ]]; then
      pass "env ${key}: present"
    else
      warn "env ${key}: missing"
    fi
  done
else
  warn "current shell env presence check skipped; source env manually, then set CHECK_CURRENT_ENV=true to check present/missing without printing values"
fi

check_endpoint health /health
check_endpoint admin /admin
check_endpoint admin_channels /admin/channels
check_endpoint admin_customers /admin/customers
check_endpoint admin_config /admin/config
check_endpoint admin_api_docs /admin/api-docs
check_endpoint user_ops_overview /api/admin/user-ops/overview

if [[ -n "$SAMPLE_SCENE_VALUE" ]]; then
  encoded_scene="$(urlencode "$SAMPLE_SCENE_VALUE")"
  masked_scene="$(mask_identifier "$SAMPLE_SCENE_VALUE")"
  check_endpoint channel_runtime_diagnosis "/api/admin/channels/runtime-diagnosis?scene_value=${encoded_scene}" "/api/admin/channels/runtime-diagnosis?scene_value=${masked_scene}"
else
  warn "SAMPLE_SCENE_VALUE not set; channel runtime diagnosis skipped"
fi

if [[ -n "$SAMPLE_EXTERNAL_USERID" ]]; then
  encoded_external_userid="$(urlencode "$SAMPLE_EXTERNAL_USERID")"
  masked_external_userid="$(mask_identifier "$SAMPLE_EXTERNAL_USERID")"
  check_endpoint customer_detail "/api/customers/${encoded_external_userid}" "/api/customers/${masked_external_userid}"
  check_endpoint customer_timeline "/api/customers/${encoded_external_userid}/timeline" "/api/customers/${masked_external_userid}/timeline"
  check_endpoint sidebar_customer_context "/api/sidebar/customer-context?external_userid=${encoded_external_userid}" "/api/sidebar/customer-context?external_userid=${masked_external_userid}"
  check_endpoint sidebar_profile "/api/sidebar/profile?external_userid=${encoded_external_userid}" "/api/sidebar/profile?external_userid=${masked_external_userid}"
else
  warn "SAMPLE_EXTERNAL_USERID not set; customer/sidebar projected customer checks skipped"
fi

printf '\nsummary: failures=%s warnings=%s\n' "$failures" "$warnings"

if (( failures > 0 )); then
  exit 1
fi
