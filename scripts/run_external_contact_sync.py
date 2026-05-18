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
from wecom_ability_service.domains.contacts.repo import (
    count_contacts,
    list_contacts,
    upsert_contacts,
)
from wecom_ability_service.domains.contacts.service import normalize_contact_record
from wecom_ability_service.domains.identity.service import (
    count_external_contact_identity_maps,
    list_identity_external_userids_for_corp,
    normalize_external_contact_identity,
    refresh_external_contact_identity_owner,
    replace_external_contact_follow_users,
    upsert_external_contact_identity,
)
from wecom_ability_service.http.sync_support import _collect_owner_userids
from wecom_ability_service.infra.wecom_runtime import get_contact_runtime_client
from wecom_ability_service.wecom_client import WeComClientError


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync WeCom external contacts into CRM.")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run a full reconciliation instead of only importing contacts that are not yet local.",
    )
    return parser.parse_args()


def run_sync(*, only_new: bool, batch_size: int = 25) -> dict[str, object]:
    client = get_contact_runtime_client()
    from flask import current_app

    corp_id = str(current_app.config.get("WECOM_CORP_ID") or "").strip()
    owner_userids = _collect_owner_userids(client)
    existing_contacts = {str(row.get("external_userid") or "").strip() for row in list_contacts(None)}
    existing_identities = set(list_identity_external_userids_for_corp(corp_id)) if only_new else set()
    seen_external_userids: set[str] = set()
    contact_batch: list[dict[str, object]] = []
    fetched_count = 0
    inserted_count = 0
    updated_count = 0
    identity_inserted_count = 0
    identity_updated_count = 0
    skipped_owner_count = 0
    skipped_contact_count = 0
    skipped_existing_count = 0
    owner_results: list[dict[str, object]] = []

    def flush_contacts() -> None:
        nonlocal inserted_count, updated_count
        if not contact_batch:
            return
        batch_inserted, batch_updated = upsert_contacts(list(contact_batch))
        inserted_count += batch_inserted
        updated_count += batch_updated
        contact_batch.clear()

    for owner_userid in owner_userids:
        try:
            result = client.list_contacts(owner_userid)
        except WeComClientError as exc:
            skipped_owner_count += 1
            owner_results.append(
                {
                    "owner_userid": owner_userid,
                    "ok": False,
                    "errcode": (exc.payload or {}).get("errcode"),
                    "errmsg": (exc.payload or {}).get("errmsg") or str(exc),
                }
            )
            continue

        external_userids = [value for value in (result.get("external_userid") or []) if value]
        owner_fetched = 0
        for external_userid in external_userids:
            if external_userid in seen_external_userids:
                continue
            if only_new and external_userid in existing_contacts and external_userid in existing_identities:
                skipped_existing_count += 1
                continue
            try:
                detail = client.get_contact(external_userid)
            except WeComClientError:
                skipped_contact_count += 1
                continue

            seen_external_userids.add(external_userid)
            contact_batch.append(normalize_contact_record(detail, owner_userid=owner_userid))
            identity_exists = external_userid in existing_identities
            identity = normalize_external_contact_identity(
                corp_id,
                detail,
                follow_user_userid=owner_userid,
                status="active",
            )
            upsert_external_contact_identity(identity)
            replace_external_contact_follow_users(
                corp_id,
                external_userid,
                detail.get("follow_user") or [],
                preferred_userid=owner_userid,
            )
            refresh_external_contact_identity_owner(corp_id, external_userid)
            if identity_exists:
                identity_updated_count += 1
            else:
                identity_inserted_count += 1
                existing_identities.add(external_userid)
            fetched_count += 1
            owner_fetched += 1
            if len(contact_batch) >= batch_size:
                flush_contacts()

        owner_results.append(
            {
                "owner_userid": owner_userid,
                "ok": True,
                "external_count": len(external_userids),
                "fetched_count": owner_fetched,
            }
        )

    flush_contacts()
    return {
        "fetched_count": fetched_count,
        "inserted_count": inserted_count,
        "updated_count": updated_count,
        "identity_inserted_count": identity_inserted_count,
        "identity_updated_count": identity_updated_count,
        "skipped_owner_count": skipped_owner_count,
        "skipped_contact_count": skipped_contact_count,
        "skipped_existing_count": skipped_existing_count,
        "contacts_total": count_contacts(),
        "identity_map_total": count_external_contact_identity_maps(),
        "owners": owner_results,
    }


def main() -> int:
    args = parse_args()
    only_new = not bool(args.full)
    app = create_app()
    with app.app_context():
        result = run_sync(only_new=only_new)
    print_json(
        {
            "ok": True,
            "mode": "full" if args.full else "incremental",
            **result,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
