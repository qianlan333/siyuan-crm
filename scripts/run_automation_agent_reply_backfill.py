#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from wecom_ability_service import create_app
from wecom_ability_service.domains.automation_conversion import backfill_missing_child_agent_replies


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill missing agent reply outputs from historical route decisions")
    parser.add_argument("--request-id", default="")
    parser.add_argument("--external-contact-id", default="")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--operator", default="history_reply_backfill_script")
    parser.add_argument("--dry-run", action="store_true", default=False)
    args = parser.parse_args()

    app = create_app()
    try:
        with app.app_context():
            payload = backfill_missing_child_agent_replies(
                operator_id=args.operator,
                request_id=args.request_id,
                external_contact_id=args.external_contact_id,
                limit=args.limit,
                dry_run=args.dry_run,
            )
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
