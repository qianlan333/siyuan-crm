#!/usr/bin/env bash

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

pick_python() {
  local candidates=(
    "$ROOT/.venv311/bin/python"
    "$ROOT/.venv/bin/python"
    "python3.11"
    "python3"
  )

  local candidate=""
  for candidate in "${candidates[@]}"; do
    if [[ -x "$candidate" ]]; then
      if "$candidate" -m pytest --version >/dev/null 2>&1; then
        echo "$candidate"
        return 0
      fi
      continue
    fi

    if command -v "$candidate" >/dev/null 2>&1; then
      if "$candidate" -m pytest --version >/dev/null 2>&1; then
        echo "$candidate"
        return 0
      fi
    fi
  done

  return 1
}

PYTHON_BIN="$(pick_python || true)"
if [[ -z "$PYTHON_BIN" ]]; then
  echo "No usable Python + pytest runtime found." >&2
  echo "Expected one of: ./.venv311/bin/python, ./.venv/bin/python, python3.11, python3" >&2
  exit 2
fi

GUARDRAIL_TESTS=(
  "tests/test_refactor_guardrails.py"
)

WAVE1_SMOKE_TESTS=(
  "tests/test_customer_center_api.py"
  "tests/test_customer_timeline_api.py"
  "tests/test_mcp_business_tools.py"
  "tests/test_admin_customer_profile_console.py"
  "tests/test_service_layer_layout.py"
  "tests/test_http_registration_contract.py"
  "tests/contract/test_crm_contract.py"
)

run_suite() {
  local label="$1"
  shift

  echo
  echo "== $label =="
  echo "python: $PYTHON_BIN"
  echo "tests : $*"
  "$PYTHON_BIN" -m pytest -q "$@"
}

echo "Repository root: $ROOT"

guardrails_exit=0
smoke_exit=0

run_suite "Guardrails" "${GUARDRAIL_TESTS[@]}" || guardrails_exit=$?
run_suite "Wave 1 Smoke" "${WAVE1_SMOKE_TESTS[@]}" || smoke_exit=$?

echo
echo "== Summary =="
echo "Guardrails exit code : $guardrails_exit"
echo "Wave 1 smoke code   : $smoke_exit"

if [[ "$guardrails_exit" -eq 0 && "$smoke_exit" -eq 0 ]]; then
  echo "Wave 1 smoke result : PASS"
  exit 0
fi

echo "Wave 1 smoke result : FAIL"
exit 1
