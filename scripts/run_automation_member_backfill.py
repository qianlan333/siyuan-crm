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
from wecom_ability_service.domains.automation_conversion import automation_member_backfill_service


def _text(value: object) -> str:
    return str(value or "").strip()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Register sidebar-bound external contacts as Campaign-ready automation members. "
            "Hourly cron example: 0 * * * * cd /opt/crm && "
            "python3 scripts/run_automation_member_backfill.py --limit 5000"
        )
    )
    parser.add_argument("--external-userid", default="")
    parser.add_argument("--limit", type=int, default=5000)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true", default=False)
    args = parser.parse_args(argv)
    if args.limit <= 0:
        parser.error("--limit must be >= 1")
    if args.offset < 0:
        parser.error("--offset must be >= 0")
    return args


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    app = create_app()
    try:
        with app.app_context():
            init_db()
            external_userid = _text(args.external_userid)
            if external_userid:
                output = automation_member_backfill_service.ensure_campaign_member_from_sidebar_binding(
                    external_userid,
                    dry_run=bool(args.dry_run),
                    commit=True,
                )
            else:
                output = automation_member_backfill_service.refresh_campaign_members_from_sidebar_bindings(
                    limit=int(args.limit),
                    offset=int(args.offset),
                    dry_run=bool(args.dry_run),
                    commit=True,
                )
            print_json(output)
            return 0 if output.get("ok") else 1
    except Exception as exc:  # pragma: no cover - operator entrypoint
        print_json({"ok": False, "error": str(exc)})
        return 1


if __name__ == "__main__":
    sys.exit(main())
