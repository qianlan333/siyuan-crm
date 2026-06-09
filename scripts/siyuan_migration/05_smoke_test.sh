#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:5001}"
ADMIN_TOKEN="${ADMIN_TOKEN:-}"
SAMPLE_SCENE_VALUE="${SAMPLE_SCENE_VALUE:-}"
SAMPLE_EXTERNAL_USERID="${SAMPLE_EXTERNAL_USERID:-}"
FOLLOW_REDIRECTS="${FOLLOW_REDIRECTS:-false}"

failures=0

request() {
  local label="$1"
  local path="$2"
  local display_path="${3:-${path}}"
  local headers body status auth_args=() curl_args=(-sS)
  headers="$(mktemp)"
  body="$(mktemp)"
  if [[ "${FOLLOW_REDIRECTS}" == "true" ]]; then
    curl_args+=(-L)
  fi
  if [[ -n "${ADMIN_TOKEN}" ]]; then
    auth_args=(-H "Authorization: Bearer ${ADMIN_TOKEN}" -H "X-Admin-Action-Token: ${ADMIN_TOKEN}")
  fi
  status="$(curl "${curl_args[@]}" -D "${headers}" -o "${body}" -w '%{http_code}' "${auth_args[@]}" "${BASE_URL}${path}" || true)"
  printf '\n[%s] GET %s -> %s\n' "${label}" "${display_path}" "${status}"
  awk 'BEGIN{IGNORECASE=1} /^X-AICRM-Route-Owner:|^X-AICRM-App:|^X-AICRM-Release-SHA:/ {gsub(/\r/,""); print "HEADER " $0}' "${headers}" || true
  if [[ "${status}" =~ ^5 ]]; then
    printf 'FAIL %s returned %s\n' "${label}" "${status}"
    failures=$((failures + 1))
  elif [[ "${status}" =~ ^(401|403|302)$ ]]; then
    printf 'WARN %s auth_required_or_redirect status=%s\n' "${label}" "${status}"
  elif [[ "${status}" =~ ^(000)$ ]]; then
    printf 'FAIL %s could not connect\n' "${label}"
    failures=$((failures + 1))
  else
    printf 'PASS %s status=%s\n' "${label}" "${status}"
  fi
  rm -f "${headers}" "${body}"
}

request "health" "/health"
request "admin" "/admin"
request "admin_channels_page" "/admin/channels"
request "user_ops_overview" "/api/admin/user-ops/overview"

if [[ -n "${SAMPLE_SCENE_VALUE}" ]]; then
  encoded_scene="$(python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1]))' "${SAMPLE_SCENE_VALUE}")"
  request "channel_runtime_diagnosis" "/api/admin/channels/runtime-diagnosis?scene_value=${encoded_scene}" "/api/admin/channels/runtime-diagnosis?scene_value=[REDACTED]"
else
  printf '\nWARN SAMPLE_SCENE_VALUE not set; skipped channel runtime diagnosis\n'
fi

if [[ -n "${SAMPLE_EXTERNAL_USERID}" ]]; then
  encoded_external_userid="$(python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1]))' "${SAMPLE_EXTERNAL_USERID}")"
  request "customer_detail" "/api/customers/${encoded_external_userid}" "/api/customers/[REDACTED]"
  request "customer_timeline" "/api/customers/${encoded_external_userid}/timeline" "/api/customers/[REDACTED]/timeline"
  request "sidebar_customer_context" "/api/sidebar/customer-context?external_userid=${encoded_external_userid}" "/api/sidebar/customer-context?external_userid=[REDACTED]"
  request "sidebar_profile" "/api/sidebar/profile?external_userid=${encoded_external_userid}" "/api/sidebar/profile?external_userid=[REDACTED]"
else
  printf '\nWARN SAMPLE_EXTERNAL_USERID not set; skipped customer/sidebar read-model smoke checks\n'
fi

if (( failures > 0 )); then
  printf '\nFAIL smoke test completed with %s 5xx/connectivity failure(s)\n' "${failures}"
  exit 1
fi

printf '\nPASS smoke test completed without 5xx failures\n'
