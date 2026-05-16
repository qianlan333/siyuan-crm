#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys

from script_runtime import ensure_repo_root_on_path, print_json

ensure_repo_root_on_path()

from wecom_ability_service import create_app
from wecom_ability_service.services import backfill_owner_class_terms_into_lead_pool


def main() -> int:
    parser = argparse.ArgumentParser(description="One-off owner lead-pool class-term backfill")
    parser.add_argument("--owner-userid", default="ZhaoYanFang")
    parser.add_argument("--class-term-min", type=int, default=1)
    parser.add_argument("--class-term-max", type=int, default=5)
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--apply", action="store_true", default=False)
    parser.add_argument("--operator", default="owner_class_term_backfill_script")
    parser.add_argument("--entry-source", default="")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--max-candidates", type=int, default=None)
    args = parser.parse_args()

    dry_run = False if args.apply else True
    app = create_app()
    try:
        with app.app_context():
            payload = backfill_owner_class_terms_into_lead_pool(
                owner_userid=args.owner_userid,
                class_term_min=args.class_term_min,
                class_term_max=args.class_term_max,
                dry_run=dry_run,
                operator=args.operator,
                entry_source=args.entry_source,
                offset=args.offset,
                max_candidates=args.max_candidates,
            )
    except Exception as exc:
        print_json({"ok": False, "error": str(exc)}, indent=2)
        return 1

    print_json(payload, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
