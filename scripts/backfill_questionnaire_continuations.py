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
from aicrm_next.questionnaire.continuation import (
    QuestionnaireContinuationService,
    configure_questionnaire_continuation_audience_repository,
)

configure_questionnaire_continuation_audience_repository(build_audience_repository)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill up to seven days of server-verified UnionID questionnaire continuations."
    )
    parser.add_argument("--apply", action="store_true", help="Create and dispatch jobs. Default only previews candidates.")
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()
    payload = QuestionnaireContinuationService().backfill_recent_verified_submissions(
        apply=args.apply,
        limit=args.limit,
    )
    print_json(payload, indent=2)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
