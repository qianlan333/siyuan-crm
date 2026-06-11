#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
from typing import Any

try:
    from scripts.script_runtime import ensure_repo_root_on_path, print_json
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from script_runtime import ensure_repo_root_on_path, print_json

ensure_repo_root_on_path()

from wecom_ability_service import create_app
from wecom_ability_service.domains.contacts.repo import count_contacts, list_contacts
from wecom_ability_service.domains.contacts.service import (
    contact_description_state,
    target_contact_description,
)
from wecom_ability_service.http.sync_support import _normalize_contact_descriptions, _sync_contacts


def _preview_contact_description_backfill() -> dict[str, Any]:
    contacts = [dict(row) for row in list_contacts(None)]
    states: Counter[str] = Counter()
    samples: list[dict[str, str]] = []
    for contact in contacts:
        external_userid = str(contact.get("external_userid") or "").strip()
        state = contact_description_state(contact.get("description"), external_userid)
        states[state] += 1
        if state in {"empty", "legacy"} and len(samples) < 20:
            samples.append(
                {
                    "external_userid": external_userid,
                    "owner_userid": str(contact.get("owner_userid") or "").strip(),
                    "current_description": str(contact.get("description") or ""),
                    "target_description": target_contact_description(external_userid),
                    "state": state,
                }
            )
    return {
        "scanned_count": len(contacts),
        "would_update_count": states["empty"] + states["legacy"],
        "untouched_count": states["target"],
        "skipped_count": states["custom"],
        "state_counts": dict(states),
        "contacts_total": count_contacts(),
        "samples": samples,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill historical WeCom contact descriptions to pure external_userid values."
    )
    parser.add_argument(
        "--include-sync",
        action="store_true",
        help="Before normalizing local historical contacts, run a full WeCom contact sync.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply writes to WeCom contact remarks and the local contact snapshot. Without this, only preview.",
    )
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        if not args.apply:
            payload = {
                "ok": True,
                "dry_run": True,
                "include_sync": bool(args.include_sync),
                **_preview_contact_description_backfill(),
            }
            if args.include_sync:
                payload["note"] = "--include-sync is ignored in dry-run mode; rerun with --apply to fetch live contacts."
            print_json(payload, indent=2)
            return 0

        sync_result: dict[str, Any] | None = None
        if args.include_sync:
            sync_result = _sync_contacts(only_new=False)
        normalize_result = _normalize_contact_descriptions()

    print_json(
        {
            "ok": True,
            "dry_run": False,
            "include_sync": bool(args.include_sync),
            "sync_result": sync_result,
            "normalize_result": normalize_result,
        },
        indent=2,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
