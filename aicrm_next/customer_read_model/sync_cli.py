from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from aicrm_next.customer_read_model.backfill import (
    CustomerReadModelBackfillService,
    LiveSourceCustomerReadModelSource,
)
from aicrm_next.customer_read_model.repo import SqlAlchemyCustomerReadModelRepository
from aicrm_next.shared.db_session import get_session_factory
from aicrm_next.shared.runtime import production_data_ready


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sync live customer source rows into AI-CRM Next customer read-model projection tables."
    )
    parser.add_argument("--dry-run", action="store_true", help="Read source rows and report counts without writing projections.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum source customers to sync.")
    parser.add_argument("--replace", action="store_true", help="Explicitly rebuild only the Next customer projection tables.")
    parser.add_argument("--external-userid", action="append", default=[], help="Sync a specific external_userid. May repeat.")
    parser.add_argument("--source", choices=["live"], default="live", help="Source backend. Production sync supports live only.")
    return parser


def run_sync(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if production_data_ready() and args.source != "live":
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "production_customer_read_model_sync_requires_live_source",
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2

    session = get_session_factory()()
    source = LiveSourceCustomerReadModelSource(session)
    target_repo = SqlAlchemyCustomerReadModelRepository(session)
    result = CustomerReadModelBackfillService(source=source, target_repo=target_repo).run(
        dry_run=bool(args.dry_run),
        limit=args.limit,
        external_userids=args.external_userid,
        replace=bool(args.replace),
    )
    print(json.dumps({"ok": True, **result.to_dict()}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return run_sync(argv)


if __name__ == "__main__":
    raise SystemExit(main())
