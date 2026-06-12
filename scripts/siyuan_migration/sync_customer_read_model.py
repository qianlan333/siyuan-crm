#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aicrm_next.customer_read_model.backfill import CustomerReadModelBackfillService  # noqa: E402
from aicrm_next.customer_read_model.repo import (  # noqa: E402
    SqlAlchemyCustomerReadModelRepository,
    build_customer_live_source_repository,
)
from aicrm_next.shared.db_session import get_session_factory  # noqa: E402


class LiveSourceCustomerReadModelSource:
    source_name = "live_source"

    def __init__(self, repo: Any) -> None:
        self._repo = repo

    def list_customers(self, *, limit: int | None = None, external_userids: set[str] | None = None) -> list[dict[str, Any]]:
        if external_userids:
            return [
                customer
                for external_userid in sorted(external_userids)
                if (customer := self._repo.get_customer(external_userid)) is not None
            ][:limit]
        return self._repo.list_customers({}, limit=limit, offset=0)

    def get_customer_detail(self, external_userid: str) -> dict[str, Any] | None:
        return self._repo.get_customer(external_userid)

    def list_timeline(self, external_userid: str, *, limit: int | None = None) -> list[dict[str, Any]]:
        return self._repo.list_timeline(external_userid, limit=limit, offset=0)

    def list_recent_messages(self, external_userid: str, *, limit: int | None = None) -> list[dict[str, Any]]:
        return self._repo.list_recent_messages(external_userid, limit=limit)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sync live customer source rows into AI-CRM Next customer read-model projection tables."
    )
    parser.add_argument("--execute", action="store_true", help="Write projection tables. Defaults to dry-run.")
    parser.add_argument("--dry-run", action="store_true", help="Read source rows and report counts without writes.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum source customers to sync.")
    parser.add_argument("--external-userid", action="append", default=[], help="Sync a specific external_userid. May repeat.")
    parser.add_argument("--database-url", default="", help="Optional explicit database URL. Defaults to configured runtime DB.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.execute and args.dry_run:
        print(json.dumps({"ok": False, "error": "choose either --execute or --dry-run"}, ensure_ascii=False), file=sys.stderr)
        return 2

    dry_run = not bool(args.execute)
    session = get_session_factory(database_url=args.database_url or None)()
    try:
        source_repo = build_customer_live_source_repository(session=session)
        source = LiveSourceCustomerReadModelSource(source_repo)
        target_repo = SqlAlchemyCustomerReadModelRepository(session)
        result = CustomerReadModelBackfillService(source=source, target_repo=target_repo).run(
            dry_run=dry_run,
            limit=args.limit,
            external_userids=args.external_userid,
        )
        print(json.dumps({"ok": True, **result.to_dict()}, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    finally:
        try:
            session.rollback()
        finally:
            session.close()


if __name__ == "__main__":
    raise SystemExit(main())
