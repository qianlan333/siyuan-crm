from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ...db import get_db


@dataclass(frozen=True)
class TagRefreshRuntime:
    """Internal-only dependency bag for user-ops tag-refresh flows."""

    contact_client_loader: Callable[[], Any]
    list_active_class_term_mappings: Callable[[], list[dict[str, Any]]]
    list_contact_tag_ids_for_user: Callable[[str, str], list[str]]
    save_tag_snapshot: Callable[[str, str, list[str], dict[str, str]], None]
    remove_tag_snapshot: Callable[[str, str, list[str]], None]
    remove_all_tag_snapshots_for_other_users: Callable[[str, list[str]], None]


def list_user_ops_pool_external_userids_for_owner(owner_userid: str) -> list[str]:
    """Internal stable helper for owner-scope external_userid enumeration."""

    rows = get_db().execute(
        """
        SELECT external_userid
        FROM user_ops_lead_pool_current
        WHERE owner_userid = ?
          AND COALESCE(external_userid, '') <> ''
        ORDER BY external_userid ASC
        """,
        (str(owner_userid or "").strip(),),
    ).fetchall()
    return [
        str(row.get("external_userid") or "").strip()
        for row in rows
        if str(row.get("external_userid") or "").strip()
    ]


def list_other_ownerids_with_scoped_tag_snapshots(
    *,
    external_userid: str,
    owner_userid: str,
    scoped_tag_ids: list[str],
) -> list[str]:
    """Internal stable helper for cross-owner scoped snapshot cleanup."""

    if not scoped_tag_ids:
        return []
    placeholders = ", ".join("?" for _ in scoped_tag_ids)
    rows = get_db().execute(
        f"""
        SELECT DISTINCT userid
        FROM contact_tags
        WHERE external_userid = ?
          AND userid <> ?
          AND tag_id IN ({placeholders})
        ORDER BY userid ASC
        """,
        (external_userid, owner_userid, *scoped_tag_ids),
    ).fetchall()
    return [
        str(row.get("userid") or "").strip()
        for row in rows
        if str(row.get("userid") or "").strip()
    ]


def refresh_contact_tags_for_external_userid(
    *,
    external_userid: str,
    owner_userid: str = "",
    scoped_tag_ids: list[str] | None = None,
    runtime: TagRefreshRuntime,
) -> dict[str, Any]:
    """Internal stable owner for full/scoped contact-tag refresh; service facade may call this."""

    normalized_external_userid = str(external_userid or "").strip()
    normalized_owner_userid = str(owner_userid or "").strip()
    if not normalized_external_userid:
        return {"ok": True, "refreshed": False, "reason": "missing_external_userid"}

    normalized_scoped_tag_ids = sorted(
        {
            str(item or "").strip()
            for item in (scoped_tag_ids or [])
            if str(item or "").strip()
        }
    )
    scoped_all_tags = not normalized_scoped_tag_ids
    tag_name_map: dict[str, str] = {}

    if not scoped_all_tags:
        for item in runtime.list_active_class_term_mappings():
            tag_id = str(item.get("tag_id") or "").strip()
            tag_name = str(item.get("tag_name") or "").strip()
            if tag_id and tag_name and tag_id in normalized_scoped_tag_ids:
                tag_name_map[tag_id] = tag_name

    detail = runtime.contact_client_loader().get_contact(normalized_external_userid)
    follow_users = detail.get("follow_user") or []
    refreshed_userids: list[str] = []
    snapshot_count = 0

    for follow_user in follow_users:
        follow_user_userid = str((follow_user or {}).get("userid") or "").strip()
        if not follow_user_userid:
            continue
        if normalized_owner_userid and follow_user_userid != normalized_owner_userid:
            continue
        refreshed_userids.append(follow_user_userid)
        current_tag_ids: list[str] = []
        for tag in ((follow_user or {}).get("tags") or []):
            current_tag_id = str((tag or {}).get("tag_id") or (tag or {}).get("id") or "").strip()
            current_tag_name = str((tag or {}).get("tag_name") or (tag or {}).get("name") or "").strip()
            if not current_tag_id:
                continue
            if not scoped_all_tags and current_tag_id not in normalized_scoped_tag_ids:
                continue
            current_tag_ids.append(current_tag_id)
            if current_tag_name:
                tag_name_map[current_tag_id] = current_tag_name
        current_tag_ids = sorted(set(current_tag_ids))
        runtime.save_tag_snapshot(
            follow_user_userid,
            normalized_external_userid,
            current_tag_ids,
            tag_name_map,
        )
        existing_tag_ids = runtime.list_contact_tag_ids_for_user(
            normalized_external_userid,
            follow_user_userid,
        )
        removable_tag_ids = [
            tag_id
            for tag_id in existing_tag_ids
            if (scoped_all_tags or tag_id in normalized_scoped_tag_ids) and tag_id not in current_tag_ids
        ]
        runtime.remove_tag_snapshot(
            follow_user_userid,
            normalized_external_userid,
            removable_tag_ids,
        )
        snapshot_count += len(current_tag_ids)

    if normalized_owner_userid and normalized_owner_userid not in refreshed_userids:
        missing_owner_existing = runtime.list_contact_tag_ids_for_user(
            normalized_external_userid,
            normalized_owner_userid,
        )
        removable_missing_owner = [
            tag_id
            for tag_id in missing_owner_existing
            if scoped_all_tags or tag_id in normalized_scoped_tag_ids
        ]
        runtime.remove_tag_snapshot(
            normalized_owner_userid,
            normalized_external_userid,
            removable_missing_owner,
        )
    if scoped_all_tags:
        runtime.remove_all_tag_snapshots_for_other_users(
            normalized_external_userid,
            refreshed_userids,
        )

    return {
        "ok": True,
        "refreshed": True,
        "external_userid": normalized_external_userid,
        "owner_userid": normalized_owner_userid,
        "follow_user_count": len(follow_users),
        "refreshed_userids": refreshed_userids,
        "scoped_tag_count": len(normalized_scoped_tag_ids),
        "scoped_all_tags": scoped_all_tags,
        "snapshot_count": snapshot_count,
    }


def refresh_user_ops_contact_tags_for_external_userid(
    *,
    external_userid: str,
    owner_userid: str = "",
    runtime: TagRefreshRuntime,
) -> dict[str, Any]:
    """Internal stable owner for single external-userid user-ops tag refresh."""

    scoped_tag_ids = sorted(
        {
            str(item.get("tag_id") or "").strip()
            for item in runtime.list_active_class_term_mappings()
            if str(item.get("tag_id") or "").strip()
        }
    )
    if not scoped_tag_ids:
        return {"ok": True, "refreshed": False, "reason": "no_active_class_term_tag_ids"}
    return refresh_contact_tags_for_external_userid(
        external_userid=external_userid,
        owner_userid=owner_userid,
        scoped_tag_ids=scoped_tag_ids,
        runtime=runtime,
    )


def refresh_user_ops_contact_tags_for_owner(
    owner_userid: str,
    *,
    runtime: TagRefreshRuntime,
) -> dict[str, Any]:
    """Internal stable owner for owner-sweep user-ops tag refresh."""

    normalized_owner_userid = str(owner_userid or "").strip()
    if not normalized_owner_userid:
        raise ValueError("owner_userid is required")
    external_userids = list_user_ops_pool_external_userids_for_owner(normalized_owner_userid)
    items: list[dict[str, Any]] = []
    refreshed_count = 0
    for external_userid in external_userids:
        result = refresh_user_ops_contact_tags_for_external_userid(
            external_userid=external_userid,
            owner_userid=normalized_owner_userid,
            runtime=runtime,
        )
        items.append(result)
        if result.get("refreshed"):
            refreshed_count += 1
    return {
        "ok": True,
        "owner_userid": normalized_owner_userid,
        "external_user_count": len(external_userids),
        "refreshed_count": refreshed_count,
        "items": items,
    }
