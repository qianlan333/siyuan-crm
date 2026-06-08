#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DUPLICATE_DIR="$ROOT_DIR/experiments/ai_crm_next/src/aicrm_next"

if [ -e "$DUPLICATE_DIR" ]; then
  echo "FAIL: duplicate AI-CRM Next source is forbidden: experiments/ai_crm_next/src/aicrm_next" >&2
  echo "root aicrm_next/ is the only Next production source." >&2
  find "$DUPLICATE_DIR" -maxdepth 3 -print >&2
  exit 1
fi

if find "$ROOT_DIR/experiments/ai_crm_next" -path '*/src/aicrm_next*' -print -quit | grep -q .; then
  echo "FAIL: duplicate AI-CRM Next source path found under experiments/ai_crm_next/src." >&2
  find "$ROOT_DIR/experiments/ai_crm_next" -path '*/src/aicrm_next*' -print >&2
  exit 1
fi

echo "PASS: no duplicate AI-CRM Next source under experiments/ai_crm_next/src/aicrm_next"
