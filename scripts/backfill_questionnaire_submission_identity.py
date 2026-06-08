#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys

try:
    from scripts.script_runtime import ensure_repo_root_on_path, print_json
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from script_runtime import ensure_repo_root_on_path, print_json

ensure_repo_root_on_path()

from wecom_ability_service import create_app
from wecom_ability_service.db import init_db
from wecom_ability_service.domains.questionnaire import backfill_questionnaire_submission_identities


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dry-run or apply mobile-based identity backfill for orphan questionnaire submissions.",
    )
    parser.add_argument("--questionnaire-id", type=int, required=True)
    parser.add_argument("--since", default="", help="Only include submissions submitted at or after this timestamp.")
    parser.add_argument("--until", default="", help="Only include submissions submitted at or before this timestamp.")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--apply", action="store_true", default=False)
    args = parser.parse_args(argv)
    if args.limit <= 0:
        parser.error("--limit must be >= 1")
    return args


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    app = create_app()
    try:
        with app.app_context():
            init_db()
            payload = backfill_questionnaire_submission_identities(
                questionnaire_id=args.questionnaire_id,
                since=args.since,
                until=args.until,
                limit=args.limit,
                apply=bool(args.apply),
            )
        print_json(payload, indent=2)
        return 0 if payload.get("ok") else 1
    except Exception as exc:
        print_json(
            {
                "ok": False,
                "mode": "questionnaire_submission_identity_backfill",
                "error": str(exc),
            },
            indent=2,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
