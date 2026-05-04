from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Callable

from ...db import get_db
from ...infra.constants import (
    USER_OPS_CLASS_TERM_TAG_GROUP_NAME,
    USER_OPS_CONFIRMED_CLASS_TERM_MAPPINGS,
)

owner_backfill_logger = logging.getLogger("owner_backfill")


@dataclass(frozen=True)
class ClassTermRuntime:
    """Internal-only dependency bag for user-ops class-term flows."""

    db_bool: Callable[[Any], bool | int]
    current_operator_resolver: Callable[[], str]
    contact_client_loader: Callable[[], Any]
    list_contact_tag_ids_for_user: Callable[[str, str], list[str]]
    save_tag_snapshot: Callable[[str, str, list[str], dict[str, str]], None]
    remove_tag_snapshot: Callable[[str, str, list[str]], None]
    get_owner_class_term_backfill_entry_source_override: Callable[[str], str]
    resolve_person_identity: Callable[..., dict[str, Any]]
    plan_lead_pool_member_upsert: Callable[..., dict[str, Any]]
    upsert_user_ops_lead_pool_member: Callable[..., dict[str, Any]]
    refresh_user_ops_contact_tags_for_owner: Callable[[str], dict[str, Any]]


def _normalize_user_ops_strategy_tag_groups(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_groups = (
        payload.get("strategy_tag_group")
        or payload.get("strategy_tag_list")
        or payload.get("strategy_tag")
        or payload.get("tag_group")
        or []
    )
    normalized_groups: list[dict[str, Any]] = []
    for group in raw_groups:
        group_name = str((group or {}).get("group_name") or (group or {}).get("name") or "").strip()
        group_id = str((group or {}).get("group_id") or (group or {}).get("id") or "").strip()
        strategy_id = str((group or {}).get("strategy_id") or "").strip()
        normalized_tags: list[dict[str, Any]] = []
        for tag in ((group or {}).get("tag") or (group or {}).get("tag_list") or (group or {}).get("tags") or []):
            tag_id = str((tag or {}).get("tag_id") or (tag or {}).get("id") or "").strip()
            tag_name = str((tag or {}).get("tag_name") or (tag or {}).get("name") or "").strip()
            if not tag_id or not tag_name:
                continue
            normalized_tags.append(
                {
                    "tag_id": tag_id,
                    "tag_name": tag_name,
                }
            )
        if not group_name:
            continue
        normalized_groups.append(
            {
                "strategy_id": strategy_id,
                "group_id": group_id,
                "group_name": group_name,
                "tags": normalized_tags,
            }
        )
    return normalized_groups


def _ensure_class_term_tag_mapping_seed(*, runtime: ClassTermRuntime) -> None:
    db = get_db()
    active_value = runtime.db_bool(True)
    existing_rows = db.execute(
        """
        SELECT id, strategy_id, group_id, tag_id, tag_group_name, tag_name, class_term_no, class_term_label, is_active
        FROM class_term_tag_mapping
        WHERE tag_group_name = ?
        ORDER BY id ASC
        """,
        (USER_OPS_CLASS_TERM_TAG_GROUP_NAME,),
    ).fetchall()
    by_tag_id = {
        str(row.get("tag_id") or "").strip(): dict(row)
        for row in existing_rows
        if str(row.get("tag_id") or "").strip()
    }
    by_group_name = {
        (str(row.get("tag_group_name") or "").strip(), str(row.get("tag_name") or "").strip()): dict(row)
        for row in existing_rows
    }
    for item in USER_OPS_CONFIRMED_CLASS_TERM_MAPPINGS:
        normalized_tag_id = str(item.get("tag_id") or "").strip()
        normalized_group_name = str(item.get("tag_group_name") or "").strip()
        normalized_tag_name = str(item.get("tag_name") or "").strip()
        existing = None
        if normalized_tag_id:
            existing = by_tag_id.get(normalized_tag_id)
        if existing is None:
            existing = by_group_name.get((normalized_group_name, normalized_tag_name))
        if existing is None:
            db.execute(
                """
                INSERT INTO class_term_tag_mapping (
                    strategy_id, group_id, tag_id, tag_group_name, tag_name, class_term_no, class_term_label, is_active, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (
                    str(item.get("strategy_id") or "").strip(),
                    str(item.get("group_id") or "").strip(),
                    normalized_tag_id,
                    normalized_group_name,
                    normalized_tag_name,
                    int(item["class_term_no"]),
                    item["class_term_label"],
                    active_value,
                ),
            )
            continue
        db.execute(
            """
            UPDATE class_term_tag_mapping
            SET strategy_id = ?,
                group_id = ?,
                tag_id = ?,
                tag_group_name = ?,
                tag_name = ?,
                class_term_no = ?,
                class_term_label = ?,
                is_active = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                str(existing.get("strategy_id") or "").strip() or str(item.get("strategy_id") or "").strip(),
                str(existing.get("group_id") or "").strip() or str(item.get("group_id") or "").strip(),
                str(existing.get("tag_id") or "").strip() or normalized_tag_id,
                normalized_group_name or str(existing.get("tag_group_name") or "").strip(),
                normalized_tag_name or str(existing.get("tag_name") or "").strip(),
                int(item["class_term_no"]),
                item["class_term_label"],
                active_value,
                int(existing["id"]),
            ),
        )
    db.commit()


def ensure_class_term_tag_mapping_seed(*, runtime: ClassTermRuntime) -> None:
    """Internal stable owner for class-term mapping seed sync."""

    _ensure_class_term_tag_mapping_seed(runtime=runtime)


def _confirmed_class_term_mappings_by_no() -> dict[int, dict[str, Any]]:
    return {
        int(item["class_term_no"]): {
            "strategy_id": str(item.get("strategy_id") or "").strip(),
            "group_id": str(item.get("group_id") or "").strip(),
            "tag_id": str(item.get("tag_id") or "").strip(),
            "tag_group_name": str(item.get("tag_group_name") or "").strip(),
            "tag_name": str(item.get("tag_name") or "").strip(),
            "class_term_no": int(item["class_term_no"]),
            "class_term_label": str(item.get("class_term_label") or "").strip(),
        }
        for item in USER_OPS_CONFIRMED_CLASS_TERM_MAPPINGS
    }


def _infer_user_ops_class_term_no_from_tag_name(tag_name: str) -> int | None:
    normalized_tag_name = str(tag_name or "").strip()
    if not normalized_tag_name:
        return None
    if "首期" in normalized_tag_name:
        return 1
    matched = re.search(r"第\s*(\d+)\s*期", normalized_tag_name)
    if matched:
        return int(matched.group(1))
    matched = re.fullmatch(r"(\d+)\s*期", normalized_tag_name)
    if matched:
        return int(matched.group(1))
    return None


def sync_user_ops_class_term_tag_definitions(*, runtime: ClassTermRuntime) -> dict[str, Any]:
    """Internal stable owner for class-term tag-definition refresh."""

    _ensure_class_term_tag_mapping_seed(runtime=runtime)
    client = runtime.contact_client_loader()
    payload = client.list_external_contact_tags()
    groups = _normalize_user_ops_strategy_tag_groups(payload)
    target_groups = [group for group in groups if group.get("group_name") == USER_OPS_CLASS_TERM_TAG_GROUP_NAME]
    rows = get_db().execute(
        """
        SELECT id, strategy_id, group_id, tag_id, tag_group_name, tag_name, class_term_no, class_term_label
        FROM class_term_tag_mapping
        WHERE tag_group_name = ?
        ORDER BY id ASC
        """,
        (USER_OPS_CLASS_TERM_TAG_GROUP_NAME,),
    ).fetchall()
    by_tag_id = {
        str(row.get("tag_id") or "").strip(): dict(row)
        for row in rows
        if str(row.get("tag_id") or "").strip()
    }
    by_tag_name = {
        str(row.get("tag_name") or "").strip(): dict(row)
        for row in rows
        if str(row.get("tag_name") or "").strip()
    }
    by_class_term_no = {
        int(row["class_term_no"]): dict(row)
        for row in rows
        if row.get("class_term_no") not in (None, "")
    }
    updated_count = 0
    discovered_count = 0
    skipped_count = 0
    synced_items: list[dict[str, Any]] = []
    db = get_db()
    for group in target_groups:
        group_id = str(group.get("group_id") or "").strip()
        strategy_id = str(group.get("strategy_id") or "").strip()
        for tag in group.get("tags") or []:
            tag_id = str(tag.get("tag_id") or "").strip()
            tag_name = str(tag.get("tag_name") or "").strip()
            existing = by_tag_id.get(tag_id) or by_tag_name.get(tag_name)
            if not existing:
                skipped_count += 1
                continue
            changed = any(
                [
                    str(existing.get("strategy_id") or "").strip() != strategy_id,
                    str(existing.get("group_id") or "").strip() != group_id,
                    str(existing.get("tag_id") or "").strip() != tag_id,
                    str(existing.get("tag_name") or "").strip() != tag_name,
                ]
            )
            db.execute(
                """
                UPDATE class_term_tag_mapping
                SET strategy_id = ?,
                    group_id = ?,
                    tag_id = ?,
                    tag_group_name = ?,
                    tag_name = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    strategy_id,
                    group_id,
                    tag_id,
                    USER_OPS_CLASS_TERM_TAG_GROUP_NAME,
                    tag_name,
                    int(existing["id"]),
                ),
            )
            if changed:
                updated_count += 1
            synced_items.append(
                {
                    "mapping_id": int(existing["id"]),
                    "strategy_id": strategy_id,
                    "group_id": group_id,
                    "tag_id": tag_id,
                    "tag_name": tag_name,
                    "class_term_no": int(existing["class_term_no"]),
                    "class_term_label": str(existing.get("class_term_label") or "").strip(),
                }
            )
            by_class_term_no[int(existing["class_term_no"])] = dict(existing)
        for tag in group.get("tags") or []:
            tag_id = str(tag.get("tag_id") or "").strip()
            tag_name = str(tag.get("tag_name") or "").strip()
            inferred_no = _infer_user_ops_class_term_no_from_tag_name(tag_name)
            if not tag_id or inferred_no is None:
                continue
            if tag_id in by_tag_id or tag_name in by_tag_name or inferred_no in by_class_term_no:
                continue
            db.execute(
                """
                INSERT INTO class_term_tag_mapping (
                    strategy_id, group_id, tag_id, tag_group_name, tag_name, class_term_no, class_term_label, is_active, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (
                    strategy_id,
                    group_id,
                    tag_id,
                    USER_OPS_CLASS_TERM_TAG_GROUP_NAME,
                    tag_name,
                    inferred_no,
                    f"{inferred_no}期",
                    runtime.db_bool(True),
                ),
            )
            inserted = db.execute(
                """
                SELECT id, strategy_id, group_id, tag_id, tag_name, class_term_no, class_term_label
                FROM class_term_tag_mapping
                WHERE tag_id = ?
                LIMIT 1
                """,
                (tag_id,),
            ).fetchone()
            inserted_payload = dict(inserted) if inserted else {}
            by_tag_id[tag_id] = inserted_payload
            by_tag_name[tag_name] = inserted_payload
            by_class_term_no[inferred_no] = inserted_payload
            discovered_count += 1
            synced_items.append(
                {
                    "mapping_id": int((inserted_payload or {}).get("id") or 0),
                    "strategy_id": strategy_id,
                    "group_id": group_id,
                    "tag_id": tag_id,
                    "tag_name": tag_name,
                    "class_term_no": inferred_no,
                    "class_term_label": f"{inferred_no}期",
                    "mapping_source": "live_discovered",
                }
            )
    db.commit()
    return {
        "ok": True,
        "group_count": len(target_groups),
        "synced_count": len(synced_items),
        "updated_count": updated_count,
        "discovered_count": discovered_count,
        "skipped_count": skipped_count,
        "items": synced_items,
    }


def list_user_ops_class_term_options(*, runtime: ClassTermRuntime) -> list[dict[str, Any]]:
    """Internal stable owner for sidebar/admin class-term option reads."""

    _ensure_class_term_tag_mapping_seed(runtime=runtime)
    rows = get_db().execute(
        """
        SELECT class_term_no, class_term_label
        FROM class_term_tag_mapping
        WHERE is_active = ?
        ORDER BY class_term_no ASC, id ASC
        """,
        (runtime.db_bool(True),),
    ).fetchall()
    return [
        {
            "class_term_no": int(row["class_term_no"]),
            "class_term_label": str(row.get("class_term_label") or "").strip(),
        }
        for row in rows
    ]


def list_active_class_term_mappings(*, runtime: ClassTermRuntime) -> list[dict[str, Any]]:
    """Internal stable owner for active class-term mapping reads."""

    _ensure_class_term_tag_mapping_seed(runtime=runtime)
    rows = get_db().execute(
        """
        SELECT id, strategy_id, group_id, tag_id, tag_group_name, tag_name, class_term_no, class_term_label
        FROM class_term_tag_mapping
        WHERE is_active = ? AND tag_group_name = ?
        ORDER BY class_term_no ASC, id ASC
        """,
        (runtime.db_bool(True), USER_OPS_CLASS_TERM_TAG_GROUP_NAME),
    ).fetchall()
    return [
        {
            "id": int(row["id"]),
            "strategy_id": str(row.get("strategy_id") or "").strip(),
            "group_id": str(row.get("group_id") or "").strip(),
            "tag_id": str(row.get("tag_id") or "").strip(),
            "tag_group_name": str(row.get("tag_group_name") or "").strip(),
            "tag_name": str(row.get("tag_name") or "").strip(),
            "class_term_no": int(row["class_term_no"]),
            "class_term_label": str(row.get("class_term_label") or "").strip(),
        }
        for row in rows
    ]


def get_active_class_term_mapping_by_no(
    class_term_no: int | None,
    *,
    runtime: ClassTermRuntime,
) -> dict[str, Any] | None:
    """Internal stable owner for class-term lookup by number."""

    if class_term_no in (None, ""):
        return None
    normalized_no = int(class_term_no)
    return next(
        (
            item
            for item in list_active_class_term_mappings(runtime=runtime)
            if int(item["class_term_no"]) == normalized_no
        ),
        None,
    )


def _list_live_user_ops_class_term_tags(tag_payload: dict[str, Any]) -> list[dict[str, Any]]:
    groups = _normalize_user_ops_strategy_tag_groups(tag_payload)
    items: list[dict[str, Any]] = []
    seen_tag_ids: set[str] = set()
    for group in groups:
        if str(group.get("group_name") or "").strip() != USER_OPS_CLASS_TERM_TAG_GROUP_NAME:
            continue
        for tag in group.get("tags") or []:
            tag_id = str(tag.get("tag_id") or "").strip()
            tag_name = str(tag.get("tag_name") or "").strip()
            if not tag_id or tag_id in seen_tag_ids:
                continue
            seen_tag_ids.add(tag_id)
            inferred_no = _infer_user_ops_class_term_no_from_tag_name(tag_name)
            items.append(
                {
                    "strategy_id": str(group.get("strategy_id") or "").strip(),
                    "group_id": str(group.get("group_id") or "").strip(),
                    "tag_group_name": USER_OPS_CLASS_TERM_TAG_GROUP_NAME,
                    "tag_id": tag_id,
                    "tag_name": tag_name,
                    "class_term_no": inferred_no,
                    "class_term_label": f"{inferred_no}期" if inferred_no is not None else "",
                }
            )
    return items


def _resolve_owner_backfill_class_term_mappings(
    *,
    class_term_min: int,
    class_term_max: int,
    tag_payload: dict[str, Any],
) -> dict[str, Any]:
    confirmed_by_no = _confirmed_class_term_mappings_by_no()
    live_tags = _list_live_user_ops_class_term_tags(tag_payload)
    live_by_tag_id = {
        str(item.get("tag_id") or "").strip(): item
        for item in live_tags
        if str(item.get("tag_id") or "").strip()
    }
    live_by_tag_name = {
        str(item.get("tag_name") or "").strip(): item
        for item in live_tags
        if str(item.get("tag_name") or "").strip()
    }
    live_by_term_no: dict[int, list[dict[str, Any]]] = {}
    for item in live_tags:
        class_term_no = item.get("class_term_no")
        if class_term_no in (None, ""):
            continue
        live_by_term_no.setdefault(int(class_term_no), []).append(item)

    effective_mappings: list[dict[str, Any]] = []
    warnings: list[str] = []
    for class_term_no in range(class_term_min, class_term_max + 1):
        confirmed = confirmed_by_no.get(class_term_no)
        resolved = None
        mapping_source = ""
        live_candidates = live_by_term_no.get(class_term_no, [])
        if confirmed:
            confirmed_tag_id = str(confirmed.get("tag_id") or "").strip()
            confirmed_tag_name = str(confirmed.get("tag_name") or "").strip()
            if confirmed_tag_id and confirmed_tag_id in live_by_tag_id:
                resolved = dict(live_by_tag_id[confirmed_tag_id])
                mapping_source = "confirmed_live_tag_id"
            elif confirmed_tag_name and confirmed_tag_name in live_by_tag_name:
                resolved = dict(live_by_tag_name[confirmed_tag_name])
                mapping_source = "confirmed_live_tag_name"
            elif len(live_candidates) == 1:
                resolved = dict(live_candidates[0])
                mapping_source = "confirmed_live_inferred"
            else:
                resolved = dict(confirmed)
                mapping_source = "confirmed_seed"
        elif len(live_candidates) == 1:
            resolved = dict(live_candidates[0])
            mapping_source = "live_discovered"
        elif len(live_candidates) > 1:
            warnings.append(f"{class_term_no}期 mapping ambiguous from real tags")
        else:
            warnings.append(f"{class_term_no}期 mapping missing")
        if resolved is None:
            continue
        resolved["class_term_no"] = class_term_no
        resolved["class_term_label"] = f"{class_term_no}期"
        resolved["mapping_source"] = mapping_source
        effective_mappings.append(resolved)

    effective_by_tag_id = {
        str(item.get("tag_id") or "").strip(): item
        for item in effective_mappings
        if str(item.get("tag_id") or "").strip()
    }
    effective_by_tag_name = {
        str(item.get("tag_name") or "").strip(): item
        for item in effective_mappings
        if str(item.get("tag_name") or "").strip()
    }
    term_two_mapping = next((item for item in effective_mappings if int(item["class_term_no"]) == 2), None)
    if term_two_mapping is None:
        warnings.extend(
            [
                "2期 mapping missing",
                "2期 skipped because no real tag mapping found",
            ]
        )

    return {
        "effective_mappings": effective_mappings,
        "effective_by_tag_id": effective_by_tag_id,
        "effective_by_tag_name": effective_by_tag_name,
        "live_tags": live_tags,
        "warnings": warnings,
        "term_2_mapping": {
            "exists": term_two_mapping is not None,
            "source": str((term_two_mapping or {}).get("mapping_source") or "missing"),
            "tag_id": str((term_two_mapping or {}).get("tag_id") or "").strip(),
            "tag_name": str((term_two_mapping or {}).get("tag_name") or "").strip(),
            "class_term_no": 2,
            "class_term_label": "2期" if term_two_mapping is not None else "",
        },
    }


def _list_owner_backfill_candidate_external_userids(owner_userid: str) -> list[dict[str, Any]]:
    normalized_owner_userid = str(owner_userid or "").strip()
    if not normalized_owner_userid:
        raise ValueError("owner_userid is required")
    rows = get_db().execute(
        """
        WITH candidates AS (
            SELECT external_userid, 1 AS from_follow_relation, 0 AS from_contact_owner
            FROM wecom_external_contact_follow_users
            WHERE user_id = ?
              AND relation_status = 'active'
              AND COALESCE(external_userid, '') <> ''
            UNION ALL
            SELECT external_userid, 0 AS from_follow_relation, 1 AS from_contact_owner
            FROM contacts
            WHERE owner_userid = ?
              AND COALESCE(external_userid, '') <> ''
        )
        SELECT
            external_userid,
            MAX(from_follow_relation) AS from_follow_relation,
            MAX(from_contact_owner) AS from_contact_owner
        FROM candidates
        GROUP BY external_userid
        ORDER BY external_userid ASC
        """,
        (normalized_owner_userid, normalized_owner_userid),
    ).fetchall()
    return [
        {
            "external_userid": str(row.get("external_userid") or "").strip(),
            "from_follow_relation": bool(row.get("from_follow_relation")),
            "from_contact_owner": bool(row.get("from_contact_owner")),
        }
        for row in rows
        if str(row.get("external_userid") or "").strip()
    ]


def _get_owner_scoped_live_contact_tags(
    *,
    external_userid: str,
    owner_userid: str,
    runtime: ClassTermRuntime,
) -> dict[str, Any]:
    normalized_external_userid = str(external_userid or "").strip()
    normalized_owner_userid = str(owner_userid or "").strip()
    if not normalized_external_userid:
        return {
            "detail": {},
            "owner_userid": normalized_owner_userid,
            "owner_found": False,
            "tags": [],
            "tag_ids": [],
            "tag_names": [],
            "external_contact_name": "",
        }
    detail = runtime.contact_client_loader().get_contact(normalized_external_userid)
    follow_users = detail.get("follow_user") or []
    owner_tags: list[dict[str, str]] = []
    owner_found = False
    for follow_user in follow_users:
        follow_user_userid = str((follow_user or {}).get("userid") or "").strip()
        if normalized_owner_userid and follow_user_userid != normalized_owner_userid:
            continue
        owner_found = True
        for tag in ((follow_user or {}).get("tags") or []):
            tag_id = str((tag or {}).get("tag_id") or (tag or {}).get("id") or "").strip()
            tag_name = str((tag or {}).get("tag_name") or (tag or {}).get("name") or "").strip()
            if not tag_id:
                continue
            owner_tags.append({"tag_id": tag_id, "tag_name": tag_name})
    deduped_tags: list[dict[str, str]] = []
    seen_tag_ids: set[str] = set()
    for tag in owner_tags:
        tag_id = str(tag.get("tag_id") or "").strip()
        if tag_id in seen_tag_ids:
            continue
        seen_tag_ids.add(tag_id)
        deduped_tags.append({"tag_id": tag_id, "tag_name": str(tag.get("tag_name") or "").strip()})
    return {
        "detail": detail,
        "owner_userid": normalized_owner_userid,
        "owner_found": owner_found,
        "tags": deduped_tags,
        "tag_ids": [str(item.get("tag_id") or "").strip() for item in deduped_tags],
        "tag_names": [
            str(item.get("tag_name") or "").strip()
            for item in deduped_tags
            if str(item.get("tag_name") or "").strip()
        ],
        "external_contact_name": str(((detail.get("external_contact") or {}).get("name") or "")).strip(),
    }


def _persist_owner_scoped_live_contact_tags(
    *,
    external_userid: str,
    owner_userid: str,
    tags: list[dict[str, str]],
    runtime: ClassTermRuntime,
) -> None:
    normalized_external_userid = str(external_userid or "").strip()
    normalized_owner_userid = str(owner_userid or "").strip()
    if not normalized_external_userid or not normalized_owner_userid:
        return
    tag_ids = sorted(
        {
            str(item.get("tag_id") or "").strip()
            for item in tags
            if str(item.get("tag_id") or "").strip()
        }
    )
    tag_name_map = {
        str(item.get("tag_id") or "").strip(): str(item.get("tag_name") or "").strip()
        for item in tags
        if str(item.get("tag_id") or "").strip()
    }
    runtime.save_tag_snapshot(normalized_owner_userid, normalized_external_userid, tag_ids, tag_name_map)
    existing_tag_ids = runtime.list_contact_tag_ids_for_user(
        normalized_external_userid,
        normalized_owner_userid,
    )
    removable_tag_ids = [tag_id for tag_id in existing_tag_ids if tag_id not in tag_ids]
    runtime.remove_tag_snapshot(normalized_owner_userid, normalized_external_userid, removable_tag_ids)


def _default_owner_class_term_backfill_entry_source(
    owner_userid: str,
    *,
    runtime: ClassTermRuntime,
) -> str:
    normalized_owner_userid = str(owner_userid or "").strip()
    override = runtime.get_owner_class_term_backfill_entry_source_override(normalized_owner_userid)
    if override:
        return override
    slug = re.sub(r"[^a-z0-9]+", "_", normalized_owner_userid.lower()).strip("_") or "owner"
    return f"{slug}_owner_backfill_20260329"


def _is_owner_backfill_invalid_test_candidate(external_userid: str) -> bool:
    normalized_external_userid = str(external_userid or "").strip().lower()
    return normalized_external_userid.startswith("wm_")


def backfill_owner_class_terms_into_lead_pool(
    *,
    owner_userid: str,
    class_term_min: int = 1,
    class_term_max: int = 5,
    dry_run: bool = True,
    operator: str = "",
    entry_source: str = "",
    sample_limit: int = 20,
    offset: int = 0,
    max_candidates: int | None = None,
    runtime: ClassTermRuntime,
) -> dict[str, Any]:
    """Internal stable owner for owner-level class-term backfill."""

    started_at = time.time()
    normalized_owner_userid = str(owner_userid or "").strip()
    if not normalized_owner_userid:
        raise ValueError("owner_userid is required")
    normalized_class_term_min = int(class_term_min)
    normalized_class_term_max = int(class_term_max)
    if normalized_class_term_min <= 0 or normalized_class_term_max <= 0:
        raise ValueError("class_term_min and class_term_max must be positive integers")
    if normalized_class_term_min > normalized_class_term_max:
        raise ValueError("class_term_min must be <= class_term_max")

    actor = str(operator or runtime.current_operator_resolver()).strip() or "owner_class_term_backfill"
    normalized_entry_source = str(entry_source or "").strip() or _default_owner_class_term_backfill_entry_source(
        normalized_owner_userid,
        runtime=runtime,
    )
    tag_payload = runtime.contact_client_loader().list_external_contact_tags()
    mapping_scope = _resolve_owner_backfill_class_term_mappings(
        class_term_min=normalized_class_term_min,
        class_term_max=normalized_class_term_max,
        tag_payload=tag_payload,
    )
    effective_by_tag_id = dict(mapping_scope["effective_by_tag_id"])
    effective_by_tag_name = dict(mapping_scope["effective_by_tag_name"])
    candidates = _list_owner_backfill_candidate_external_userids(normalized_owner_userid)
    candidate_total = len(candidates)
    normalized_offset = max(int(offset or 0), 0)
    normalized_max_candidates = int(max_candidates) if max_candidates is not None else None
    if normalized_max_candidates is not None and normalized_max_candidates <= 0:
        raise ValueError("max_candidates must be positive when provided")
    selected_candidates = list(candidates[normalized_offset:]) if normalized_offset else list(candidates)
    if normalized_max_candidates is not None:
        selected_candidates = selected_candidates[:normalized_max_candidates]

    items: list[dict[str, Any]] = []
    invalid_test_candidate_samples: list[dict[str, Any]] = []
    owner_mismatch_samples: list[dict[str, Any]] = []
    class_term_distribution = {
        str(class_term_no): 0
        for class_term_no in range(normalized_class_term_min, normalized_class_term_max + 1)
    }
    estimated_insert_total = 0
    estimated_update_total = 0
    estimated_mobile_bound_total = 0
    estimated_mobile_empty_total = 0
    single_match_total = 0
    conflict_total = 0
    skip_total = 0
    noop_total = 0
    error_total = 0
    invalid_test_candidate_total = 0
    owner_mismatch_total = 0
    processed_candidate_total = 0
    source_breakdown = {
        "follow_relation_only": 0,
        "contact_owner_only": 0,
        "both_sources": 0,
    }
    for candidate in selected_candidates:
        from_follow_relation = bool(candidate.get("from_follow_relation"))
        from_contact_owner = bool(candidate.get("from_contact_owner"))
        if from_follow_relation and from_contact_owner:
            source_breakdown["both_sources"] += 1
        elif from_follow_relation:
            source_breakdown["follow_relation_only"] += 1
        elif from_contact_owner:
            source_breakdown["contact_owner_only"] += 1

    if not dry_run:
        sync_user_ops_class_term_tag_definitions(runtime=runtime)

    for candidate in selected_candidates:
        processed_candidate_total += 1
        external_userid = str(candidate.get("external_userid") or "").strip()
        if not external_userid:
            continue
        target_owner_userid = normalized_owner_userid
        if processed_candidate_total % 100 == 0:
            owner_backfill_logger.info(
                "owner backfill progress owner_userid=%s processed=%s candidate_total=%s offset=%s max_candidates=%s",
                normalized_owner_userid,
                processed_candidate_total,
                candidate_total,
                normalized_offset,
                normalized_max_candidates if normalized_max_candidates is not None else "all",
            )
        if _is_owner_backfill_invalid_test_candidate(external_userid):
            invalid_test_candidate_total += 1
            invalid_item = {
                "external_userid": external_userid,
                "customer_name": "",
                "target_owner_userid": target_owner_userid,
                "resolved_owner_userid": target_owner_userid,
                "final_owner_userid": target_owner_userid,
                "owner_userid": target_owner_userid,
                "mobile": "",
                "is_mobile_bound": False,
                "matched_class_term_no": None,
                "matched_class_term_label": "",
                "decision": "skip",
                "decision_reason": "invalid_test_candidate",
            }
            items.append(invalid_item)
            if len(invalid_test_candidate_samples) < max(int(sample_limit or 20), 20):
                invalid_test_candidate_samples.append(dict(invalid_item))
            continue
        try:
            live_tag_payload = _get_owner_scoped_live_contact_tags(
                external_userid=external_userid,
                owner_userid=normalized_owner_userid,
                runtime=runtime,
            )
        except Exception as exc:
            error_total += 1
            items.append(
                {
                    "external_userid": external_userid,
                    "customer_name": "",
                    "target_owner_userid": target_owner_userid,
                    "resolved_owner_userid": target_owner_userid,
                    "final_owner_userid": target_owner_userid,
                    "owner_userid": target_owner_userid,
                    "mobile": "",
                    "is_mobile_bound": False,
                    "matched_class_term_no": None,
                    "matched_class_term_label": "",
                    "decision": "skip",
                    "decision_reason": f"tag_fetch_failed: {exc}",
                }
            )
            continue

        tags = list(live_tag_payload["tags"])
        matched_by_term_no: dict[int, dict[str, Any]] = {}
        for tag in tags:
            tag_id = str(tag.get("tag_id") or "").strip()
            tag_name = str(tag.get("tag_name") or "").strip()
            mapping = effective_by_tag_id.get(tag_id) or effective_by_tag_name.get(tag_name)
            if not mapping:
                continue
            matched_by_term_no[int(mapping["class_term_no"])] = {
                "class_term_no": int(mapping["class_term_no"]),
                "class_term_label": str(mapping.get("class_term_label") or "").strip(),
                "tag_id": tag_id,
                "tag_name": tag_name,
            }
        matched_terms = sorted(matched_by_term_no.values(), key=lambda item: int(item["class_term_no"]))
        identity = runtime.resolve_person_identity(external_userid=external_userid)
        customer_name = (
            str(identity.get("customer_name") or "").strip()
            or str(live_tag_payload.get("external_contact_name") or "").strip()
        )
        mobile = str(identity.get("mobile") or "").strip()
        is_mobile_bound = bool(identity.get("is_bound"))
        resolved_owner_userid = str(identity.get("owner_userid") or "").strip() or normalized_owner_userid
        final_owner_userid = target_owner_userid
        if resolved_owner_userid != target_owner_userid:
            owner_mismatch_total += 1
            mismatch_item = {
                "external_userid": external_userid,
                "customer_name": customer_name,
                "target_owner_userid": target_owner_userid,
                "resolved_owner_userid": resolved_owner_userid,
                "final_owner_userid": final_owner_userid,
                "mobile": mobile,
                "is_mobile_bound": is_mobile_bound,
            }
            if len(owner_mismatch_samples) < max(int(sample_limit or 20), 20):
                owner_mismatch_samples.append(dict(mismatch_item))

        if not matched_terms:
            skip_total += 1
            items.append(
                {
                    "external_userid": external_userid,
                    "customer_name": customer_name,
                    "target_owner_userid": target_owner_userid,
                    "resolved_owner_userid": resolved_owner_userid,
                    "final_owner_userid": final_owner_userid,
                    "owner_userid": final_owner_userid,
                    "mobile": mobile,
                    "is_mobile_bound": is_mobile_bound,
                    "matched_class_term_no": None,
                    "matched_class_term_label": "",
                    "decision": "skip",
                    "decision_reason": "no_match",
                    "tag_names": list(live_tag_payload["tag_names"]),
                }
            )
            continue

        if len(matched_terms) > 1:
            conflict_total += 1
            items.append(
                {
                    "external_userid": external_userid,
                    "customer_name": customer_name,
                    "target_owner_userid": target_owner_userid,
                    "resolved_owner_userid": resolved_owner_userid,
                    "final_owner_userid": final_owner_userid,
                    "owner_userid": final_owner_userid,
                    "mobile": mobile,
                    "is_mobile_bound": is_mobile_bound,
                    "matched_class_term_no": None,
                    "matched_class_term_label": "",
                    "decision": "conflict",
                    "decision_reason": "multiple_class_term_matches",
                    "matched_terms": matched_terms,
                    "tag_names": list(live_tag_payload["tag_names"]),
                }
            )
            continue

        single_match_total += 1
        matched = matched_terms[0]
        class_term_distribution[str(matched["class_term_no"])] += 1
        plan = runtime.plan_lead_pool_member_upsert(
            mobile=mobile,
            external_userid=str(identity.get("external_userid") or external_userid).strip(),
            customer_name=customer_name,
            owner_userid=final_owner_userid,
            is_wecom_added=True,
            is_mobile_bound=is_mobile_bound,
            class_term_no=int(matched["class_term_no"]),
            class_term_label=str(matched.get("class_term_label") or "").strip(),
            entry_source=normalized_entry_source,
        )
        decision = "insert"
        decision_reason = str(plan["action_type"])
        if plan["action_type"] == "lead_pool_insert":
            estimated_insert_total += 1
        elif plan["action_type"] == "lead_pool_noop":
            decision = "skip"
            decision_reason = "already_up_to_date"
            noop_total += 1
        else:
            decision = "update"
            estimated_update_total += 1
        if decision in {"insert", "update"}:
            if is_mobile_bound:
                estimated_mobile_bound_total += 1
            if not mobile:
                estimated_mobile_empty_total += 1
            if not dry_run:
                _persist_owner_scoped_live_contact_tags(
                    external_userid=external_userid,
                    owner_userid=normalized_owner_userid,
                    tags=tags,
                    runtime=runtime,
                )
                runtime.upsert_user_ops_lead_pool_member(
                    mobile=mobile,
                    external_userid=str(identity.get("external_userid") or external_userid).strip(),
                    customer_name=customer_name,
                    owner_userid=final_owner_userid,
                    is_wecom_added=True,
                    is_mobile_bound=is_mobile_bound,
                    class_term_no=int(matched["class_term_no"]),
                    class_term_label=str(matched.get("class_term_label") or "").strip(),
                    entry_source=normalized_entry_source,
                    operator=actor,
                    remark=f"owner class-term backfill external_userid={external_userid}",
                )
        items.append(
            {
                "external_userid": external_userid,
                "customer_name": customer_name,
                "target_owner_userid": target_owner_userid,
                "resolved_owner_userid": resolved_owner_userid,
                "final_owner_userid": final_owner_userid,
                "owner_userid": final_owner_userid,
                "mobile": mobile,
                "is_mobile_bound": is_mobile_bound,
                "matched_class_term_no": int(matched["class_term_no"]),
                "matched_class_term_label": str(matched.get("class_term_label") or "").strip(),
                "decision": decision,
                "decision_reason": decision_reason,
                "tag_names": list(live_tag_payload["tag_names"]),
            }
        )

    decision_order = {"conflict": 0, "update": 1, "insert": 2, "skip": 3}
    sample_items = sorted(
        items,
        key=lambda item: (
            decision_order.get(str(item.get("decision") or "").strip(), 9),
            str(item.get("matched_class_term_no") or ""),
            str(item.get("external_userid") or ""),
        ),
    )[: max(int(sample_limit or 20), 20)]

    return {
        "ok": True,
        "owner_userid": normalized_owner_userid,
        "class_term_min": normalized_class_term_min,
        "class_term_max": normalized_class_term_max,
        "dry_run": bool(dry_run),
        "entry_source": normalized_entry_source,
        "candidate_total": candidate_total,
        "processed_candidate_total": processed_candidate_total,
        "offset": normalized_offset,
        "max_candidates": normalized_max_candidates,
        "matched_candidate_total": single_match_total + conflict_total,
        "single_match_total": single_match_total,
        "class_term_distribution": class_term_distribution,
        "conflict_total": conflict_total,
        "skip_total": skip_total,
        "noop_total": noop_total,
        "error_total": error_total,
        "invalid_test_candidate_total": invalid_test_candidate_total,
        "invalid_test_candidate_samples": invalid_test_candidate_samples,
        "owner_mismatch_total": owner_mismatch_total,
        "owner_mismatch_samples": owner_mismatch_samples,
        "estimated_insert_total": estimated_insert_total,
        "estimated_update_total": estimated_update_total,
        "estimated_mobile_bound_total": estimated_mobile_bound_total,
        "estimated_mobile_empty_total": estimated_mobile_empty_total,
        "term_2_mapping": mapping_scope["term_2_mapping"],
        "warnings": list(dict.fromkeys(mapping_scope["warnings"])),
        "elapsed_seconds": round(time.time() - started_at, 3),
        "source_breakdown": source_breakdown,
        "samples": sample_items,
        "applied_total": 0 if dry_run else estimated_insert_total + estimated_update_total,
    }


def build_user_ops_backfill_preview(
    owner_userid: str,
    *,
    runtime: ClassTermRuntime,
) -> list[dict[str, Any]]:
    """Internal stable owner for owner-level class-term preview payloads."""

    normalized_owner_userid = str(owner_userid or "").strip()
    if not normalized_owner_userid:
        raise ValueError("owner_userid is required")
    _ensure_class_term_tag_mapping_seed(runtime=runtime)
    rows = get_db().execute(
        """
        SELECT
            current.id AS pool_id,
            current.mobile,
            current.external_userid,
            current.customer_name,
            current.owner_userid,
            current.class_term_no AS current_class_term_no,
            current.class_term_label AS current_class_term_label,
            COALESCE(tags.tag_id, '') AS tag_id,
            COALESCE(tags.tag_name, '') AS tag_name,
            COALESCE(mappings.tag_id, '') AS mapped_tag_id,
            mappings.class_term_no AS mapped_class_term_no,
            COALESCE(mappings.class_term_label, '') AS mapped_class_term_label
        FROM user_ops_pool_current current
        LEFT JOIN contact_tags tags
          ON tags.external_userid = current.external_userid
         AND tags.userid = current.owner_userid
        LEFT JOIN class_term_tag_mapping mappings
          ON mappings.tag_id = tags.tag_id
         AND mappings.tag_group_name = ?
         AND mappings.is_active = ?
         AND COALESCE(mappings.tag_id, '') <> ''
        WHERE current.owner_userid = ?
          AND COALESCE(current.external_userid, '') <> ''
        ORDER BY current.id ASC, mappings.class_term_no ASC, tags.tag_id ASC, tags.tag_name ASC
        """,
        (
            USER_OPS_CLASS_TERM_TAG_GROUP_NAME,
            runtime.db_bool(True),
            normalized_owner_userid,
        ),
    ).fetchall()
    preview_by_pool_id: dict[int, dict[str, Any]] = {}
    for row in rows:
        pool_id = int(row["pool_id"])
        preview = preview_by_pool_id.setdefault(
            pool_id,
            {
                "pool_id": pool_id,
                "mobile": str(row.get("mobile") or "").strip(),
                "external_userid": str(row.get("external_userid") or "").strip(),
                "customer_name": str(row.get("customer_name") or "").strip(),
                "owner_userid": str(row.get("owner_userid") or "").strip(),
                "current_class_term_no": int(row["current_class_term_no"])
                if row.get("current_class_term_no") not in (None, "")
                else None,
                "current_class_term_label": str(row.get("current_class_term_label") or "").strip(),
                "matched_terms": [],
                "matched_term_keys": set(),
                "tag_ids": [],
                "tag_names": [],
            },
        )
        tag_id = str(row.get("tag_id") or "").strip()
        tag_name = str(row.get("tag_name") or "").strip()
        if tag_id and tag_id not in preview["tag_ids"]:
            preview["tag_ids"].append(tag_id)
        if tag_name and tag_name not in preview["tag_names"]:
            preview["tag_names"].append(tag_name)
        mapped_no = row.get("mapped_class_term_no")
        mapped_label = str(row.get("mapped_class_term_label") or "").strip()
        if mapped_no in (None, ""):
            continue
        mapped_tag_id = str(row.get("mapped_tag_id") or "").strip()
        key = f"{int(mapped_no)}:{mapped_label}:{mapped_tag_id}"
        if key in preview["matched_term_keys"]:
            continue
        preview["matched_term_keys"].add(key)
        preview["matched_terms"].append(
            {
                "class_term_no": int(mapped_no),
                "class_term_label": mapped_label,
                "tag_id": mapped_tag_id,
                "tag_name": tag_name,
            }
        )
    preview_items: list[dict[str, Any]] = []
    for item in preview_by_pool_id.values():
        matched_terms = list(item["matched_terms"])
        current_no = item["current_class_term_no"]
        current_label = item["current_class_term_label"]
        if len(matched_terms) > 1:
            decision = "conflict"
        elif len(matched_terms) == 1:
            matched = matched_terms[0]
            if current_no == matched["class_term_no"] and current_label == matched["class_term_label"]:
                decision = "unchanged"
            else:
                decision = "update"
        else:
            decision = "no_match"
        preview_items.append(
            {
                "pool_id": item["pool_id"],
                "mobile": item["mobile"],
                "external_userid": item["external_userid"],
                "customer_name": item["customer_name"],
                "owner_userid": item["owner_userid"],
                "current_class_term_no": current_no,
                "current_class_term_label": current_label,
                "matched_terms": matched_terms,
                "tag_ids": list(item["tag_ids"]),
                "tag_names": list(item["tag_names"]),
                "decision": decision,
            }
        )
    return preview_items


def _build_backfill_class_term_summary(
    *,
    owner_userid: str,
    dry_run: bool,
    tag_definition_sync: dict[str, Any],
    tag_refresh: dict[str, Any],
    preview_items: list[dict[str, Any]],
    mappings: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "owner_userid": owner_userid,
        "dry_run": bool(dry_run),
        "mapping_count": len(mappings),
        "tag_definition_sync": tag_definition_sync,
        "tag_refresh": tag_refresh,
        "total_candidates": len(preview_items),
        "update_count": sum(1 for item in preview_items if item["decision"] == "update"),
        "unchanged_count": sum(1 for item in preview_items if item["decision"] == "unchanged"),
        "no_match_count": sum(1 for item in preview_items if item["decision"] == "no_match"),
        "conflict_count": sum(1 for item in preview_items if item["decision"] == "conflict"),
        "items": preview_items,
    }


def _log_backfill_class_term_conflict(db, item: dict[str, Any], *, actor: str, now: str) -> None:
    db.execute(
        """
        INSERT INTO user_ops_pool_history (
            pool_id, mobile, external_userid, action_type, old_payload_json, new_payload_json, operator, source_type, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            item["pool_id"],
            item["mobile"],
            item["external_userid"],
            "class_term_backfill_conflict",
            json.dumps(
                {
                    "class_term_no": item["current_class_term_no"],
                    "class_term_label": item["current_class_term_label"],
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "matched_terms": item["matched_terms"],
                    "tag_names": item["tag_names"],
                },
                ensure_ascii=False,
            ),
            actor,
            "class_term_backfill",
            now,
        ),
    )


def _apply_backfill_class_term_update(
    db,
    item: dict[str, Any],
    *,
    matched: dict[str, Any],
    actor: str,
    now: str,
) -> None:
    db.execute(
        """
        UPDATE user_ops_pool_current
        SET class_term_no = ?, class_term_label = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            matched["class_term_no"],
            matched["class_term_label"],
            now,
            item["pool_id"],
        ),
    )
    db.execute(
        """
        INSERT INTO user_ops_pool_history (
            pool_id, mobile, external_userid, action_type, old_payload_json, new_payload_json, operator, source_type, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            item["pool_id"],
            item["mobile"],
            item["external_userid"],
            "class_term_backfill_apply",
            json.dumps(
                {
                    "class_term_no": item["current_class_term_no"],
                    "class_term_label": item["current_class_term_label"],
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "class_term_no": matched["class_term_no"],
                    "class_term_label": matched["class_term_label"],
                    "matched_terms": item["matched_terms"],
                },
                ensure_ascii=False,
            ),
            actor,
            "class_term_backfill",
            now,
        ),
    )


def backfill_class_term_for_owner(
    *,
    owner_userid: str,
    dry_run: bool = True,
    operator: str = "",
    runtime: ClassTermRuntime,
) -> dict[str, Any]:
    """Internal stable owner for owner-level backfill preview/apply flow."""

    normalized_owner_userid = str(owner_userid or "").strip()
    if not normalized_owner_userid:
        raise ValueError("owner_userid is required")
    tag_definition_sync = sync_user_ops_class_term_tag_definitions(runtime=runtime)
    tag_refresh = runtime.refresh_user_ops_contact_tags_for_owner(normalized_owner_userid)
    preview_items = build_user_ops_backfill_preview(normalized_owner_userid, runtime=runtime)
    mappings = list_active_class_term_mappings(runtime=runtime)
    summary = _build_backfill_class_term_summary(
        owner_userid=normalized_owner_userid,
        dry_run=bool(dry_run),
        tag_definition_sync=tag_definition_sync,
        tag_refresh=tag_refresh,
        preview_items=preview_items,
        mappings=mappings,
    )
    if dry_run:
        return {"ok": True, **summary}

    db = get_db()
    actor = str(operator or runtime.current_operator_resolver()).strip() or "admin_user_ops"
    applied_count = 0
    conflict_logged = 0
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    for item in preview_items:
        if item["decision"] == "conflict":
            _log_backfill_class_term_conflict(db, item, actor=actor, now=now)
            conflict_logged += 1
            continue
        if item["decision"] != "update":
            continue
        matched = item["matched_terms"][0]
        _apply_backfill_class_term_update(db, item, matched=matched, actor=actor, now=now)
        applied_count += 1
    db.commit()
    return {
        "ok": True,
        **summary,
        "dry_run": False,
        "applied_count": applied_count,
        "conflict_logged_count": conflict_logged,
    }


def list_class_term_matches_for_external_contact(
    external_userid: str,
    owner_userid: str = "",
    *,
    runtime: ClassTermRuntime,
) -> dict[str, Any]:
    """Internal stable owner for class-term matching by external contact."""

    normalized_external_userid = str(external_userid or "").strip()
    normalized_owner_userid = str(owner_userid or "").strip()
    if not normalized_external_userid:
        return {"matched_terms": [], "tag_ids": [], "tag_names": []}
    rows = get_db().execute(
        """
        SELECT
            COALESCE(tags.tag_id, '') AS tag_id,
            COALESCE(tags.tag_name, '') AS tag_name,
            mappings.class_term_no,
            COALESCE(mappings.class_term_label, '') AS class_term_label
        FROM contact_tags tags
        LEFT JOIN class_term_tag_mapping mappings
          ON mappings.tag_id = tags.tag_id
         AND mappings.tag_group_name = ?
         AND mappings.is_active = ?
         AND COALESCE(mappings.tag_id, '') <> ''
        WHERE tags.external_userid = ?
          AND (? = '' OR tags.userid = ?)
        ORDER BY mappings.class_term_no ASC, tags.tag_id ASC, tags.tag_name ASC
        """,
        (
            USER_OPS_CLASS_TERM_TAG_GROUP_NAME,
            runtime.db_bool(True),
            normalized_external_userid,
            normalized_owner_userid,
            normalized_owner_userid,
        ),
    ).fetchall()
    tag_ids: list[str] = []
    tag_names: list[str] = []
    matched_terms: list[dict[str, Any]] = []
    seen_term_keys: set[str] = set()
    for row in rows:
        tag_id = str(row.get("tag_id") or "").strip()
        tag_name = str(row.get("tag_name") or "").strip()
        if tag_id and tag_id not in tag_ids:
            tag_ids.append(tag_id)
        if tag_name and tag_name not in tag_names:
            tag_names.append(tag_name)
        if row.get("class_term_no") in (None, ""):
            continue
        key = f"{int(row['class_term_no'])}:{str(row.get('class_term_label') or '').strip()}:{tag_id}"
        if key in seen_term_keys:
            continue
        seen_term_keys.add(key)
        matched_terms.append(
            {
                "class_term_no": int(row["class_term_no"]),
                "class_term_label": str(row.get("class_term_label") or "").strip(),
                "tag_id": tag_id,
                "tag_name": tag_name,
            }
        )
    return {"matched_terms": matched_terms, "tag_ids": tag_ids, "tag_names": tag_names}


__all__ = [
    "ClassTermRuntime",
    "backfill_class_term_for_owner",
    "backfill_owner_class_terms_into_lead_pool",
    "build_user_ops_backfill_preview",
    "ensure_class_term_tag_mapping_seed",
    "get_active_class_term_mapping_by_no",
    "list_active_class_term_mappings",
    "list_class_term_matches_for_external_contact",
    "list_user_ops_class_term_options",
    "sync_user_ops_class_term_tag_definitions",
]
