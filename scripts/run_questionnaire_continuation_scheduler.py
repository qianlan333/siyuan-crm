#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys

try:
    from scripts.script_runtime import ensure_repo_root_on_path, print_json
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from script_runtime import ensure_repo_root_on_path, print_json

ensure_repo_root_on_path()

from aicrm_next.ai_audience_ops.repository import build_audience_repository
from aicrm_next.questionnaire.continuation import configure_questionnaire_continuation_audience_repository
from aicrm_next.questionnaire.scheduler import run_questionnaire_continuation_reconciliation

configure_questionnaire_continuation_audience_repository(build_audience_repository)


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile due questionnaire identity continuation jobs.")
    parser.add_argument("--execute", action="store_true", help="Claim and dispatch eligible jobs; default is no-write dry-run.")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    payload = run_questionnaire_continuation_reconciliation(execute=args.execute, limit=args.limit)
    print_json(payload, indent=2)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
