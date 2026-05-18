"""Sync WeCom external contacts into the customer center tables.

Default mode is incremental: scan the WeCom follow-user list and import contacts
that are not yet in the local identity/contact tables. Use ``--full`` for a
periodic reconciliation pass.
"""
from __future__ import annotations

import argparse

from script_runtime import ensure_repo_root_on_path, print_json

ensure_repo_root_on_path()

from wecom_ability_service import create_app
from wecom_ability_service.http.sync_jobs import (
    run_contacts_sync,
    run_external_contact_identity_sync,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync WeCom external contacts into CRM.")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run a full reconciliation instead of only importing contacts that are not yet local.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    only_new = not bool(args.full)
    app = create_app()
    with app.app_context():
        contacts = run_contacts_sync(only_new=only_new)
        identities = run_external_contact_identity_sync(only_new=only_new)
    print_json(
        {
            "ok": True,
            "mode": "full" if args.full else "incremental",
            "contacts": contacts,
            "external_contact_identity": identities,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
