#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

MODE="full"
if [ "${1:-}" = "--mode" ]; then
  MODE="${2:-full}"
elif [[ "${1:-}" == --mode=* ]]; then
  MODE="${1#--mode=}"
elif [ -n "${1:-}" ]; then
  MODE="$1"
fi

if [ -x ".venv/bin/python" ]; then
  PYTHON=".venv/bin/python"
else
  PYTHON="python"
fi

run_fast() {
"$PYTHON" tools/check_route_ownership_manifest.py
"$PYTHON" tools/check_admin_route_auth.py
"$PYTHON" tools/check_repository_ownership.py
}

run_db() {
  "$PYTHON" tools/check_db_access_boundary.py
  "$PYTHON" tools/check_data_table_lifecycle.py
  "$PYTHON" tools/check_sql_static_guard.py
  "$PYTHON" -m pytest tests/test_alembic_revision_chain.py -q --tb=short
}

run_full_only() {
  "$PYTHON" tools/check_architecture_boundaries.py
  "$PYTHON" tools/check_external_effects_boundary.py
  "$PYTHON" tools/check_background_job_contract.py
  "$PYTHON" tools/check_schema_change_templates.py
}

case "$MODE" in
  fast)
    run_fast
    ;;
  db)
    run_fast
    run_db
    ;;
  full)
    run_fast
    run_db
    run_full_only
    ;;
  *)
    echo "Unknown architecture gate mode: $MODE" >&2
    exit 2
    ;;
esac
