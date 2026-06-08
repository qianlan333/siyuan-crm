#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${AICRM_CODEX_AUTOPILOT_LOG_DIR:-$ROOT_DIR/logs/codex-autopilot}"
PROMPT_PATH="${AICRM_CODEX_AUTOPILOT_PROMPT:-/tmp/aicrm_codex_next_prompt.md}"
REPORT_JSON="$LOG_DIR/tick-report.json"
REPORT_MD="$LOG_DIR/tick-report.md"
CODEX_COMMAND="${AICRM_CODEX_COMMAND:-codex}"

mkdir -p "$LOG_DIR"

{
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] codex autopilot tick starting"
  cd "$ROOT_DIR"
  git fetch origin main --prune
  python3 tools/run_codex_autopilot_tick.py \
    --prompt-output "$PROMPT_PATH" \
    --output-json "$REPORT_JSON" \
    --output-md "$REPORT_MD"

  if python3 - "$REPORT_JSON" <<'PY'
import json
import sys
report = json.load(open(sys.argv[1], encoding="utf-8"))
raise SystemExit(0 if report.get("prompt_generated") else 1)
PY
  then
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] prompt generated at $PROMPT_PATH"
    "$CODEX_COMMAND" < "$PROMPT_PATH"
  else
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] no prompt generated; see $REPORT_JSON"
  fi
} >> "$LOG_DIR/tick.log" 2>&1
