from __future__ import annotations

import json
from typing import Any

from ...db import get_db
from ...db.helpers import fetchall_dicts


def get_contact_tag_snapshots(external_userid: str) -> list[dict[str, Any]]:
    rows = get_db().execute(
        """
        SELECT external_userid, userid, tag_id, COALESCE(tag_name, '') AS tag_name, created_at
        FROM contact_tags
        WHERE external_userid = ?
        ORDER BY userid ASC, tag_name ASC, tag_id ASC
        """,
        (external_userid,),
    ).fetchall()
    return [dict(row) for row in rows]


def list_signup_tag_rules(active_only: bool = False) -> list[dict[str, Any]]:
    sql = """
        SELECT tag_id, tag_name, signup_status, active, updated_at
        FROM signup_tag_rules
    """
    params: list[Any] = []
    if active_only:
        sql += " WHERE active = ?"
        params.append(True)
    sql += " ORDER BY active DESC, signup_status ASC, tag_name ASC, tag_id ASC"
    rows = get_db().execute(sql, tuple(params)).fetchall()
    return [dict(row) for row in rows]


def upsert_signup_tag_rule(tag_id: str, tag_name: str, signup_status: str, active: bool = True) -> None:
    normalized_tag_id = str(tag_id or "").strip()
    normalized_tag_name = str(tag_name or "").strip()
    normalized_status = str(signup_status or "").strip()
    if not normalized_tag_id or not normalized_tag_name or not normalized_status:
        return
    active_value = bool(active)
    get_db().execute(
        """
        INSERT INTO signup_tag_rules (tag_id, tag_name, signup_status, active, updated_at)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(tag_id) DO UPDATE SET
            tag_name = excluded.tag_name,
            signup_status = excluded.signup_status,
            active = excluded.active,
            updated_at = CURRENT_TIMESTAMP
        """,
        (normalized_tag_id, normalized_tag_name, normalized_status, active_value),
    )
    get_db().commit()


def save_tag_snapshot(
    userid: str,
    external_userid: str,
    add_tag_ids: list[str],
    tag_name_map: dict[str, str] | None = None,
) -> None:
    db = get_db()
    for tag_id in add_tag_ids:
        db.execute(
            """
            INSERT INTO contact_tags (external_userid, userid, tag_id, tag_name)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (external_userid, userid, tag_id) DO UPDATE SET
                tag_name = excluded.tag_name
            """,
            (external_userid, userid, tag_id, (tag_name_map or {}).get(tag_id)),
        )
    db.commit()


def remove_tag_snapshot(userid: str, external_userid: str, remove_tag_ids: list[str]) -> None:
    db = get_db()
    for tag_id in remove_tag_ids:
        db.execute(
            "DELETE FROM contact_tags WHERE external_userid = ? AND userid = ? AND tag_id = ?",
            (external_userid, userid, tag_id),
        )
    db.commit()


def remove_tag_snapshots_for_other_users(external_userid: str, keep_userids: list[str], scoped_tag_ids: list[str]) -> None:
    normalized_external_userid = str(external_userid or "").strip()
    normalized_keep_userids = [str(item or "").strip() for item in keep_userids if str(item or "").strip()]
    normalized_tag_ids = [str(item or "").strip() for item in scoped_tag_ids if str(item or "").strip()]
    if not normalized_external_userid or not normalized_tag_ids:
        return
    params: list[Any] = [normalized_external_userid, *normalized_tag_ids]
    sql = (
        "DELETE FROM contact_tags WHERE external_userid = ? AND tag_id IN ("
        + ",".join(["?"] * len(normalized_tag_ids))
        + ")"
    )
    if normalized_keep_userids:
        sql += " AND userid NOT IN (" + ",".join(["?"] * len(normalized_keep_userids)) + ")"
        params.extend(normalized_keep_userids)
    db = get_db()
    db.execute(sql, tuple(params))
    db.commit()


def list_contact_tag_ids_for_user(external_userid: str, userid: str) -> list[str]:
    rows = get_db().execute(
        """
        SELECT tag_id
        FROM contact_tags
        WHERE external_userid = ? AND userid = ?
        ORDER BY tag_id ASC
        """,
        (str(external_userid or "").strip(), str(userid or "").strip()),
    ).fetchall()
    return [str(row.get("tag_id") or "").strip() for row in rows if str(row.get("tag_id") or "").strip()]


def count_contact_tag_usage_by_tag_ids(tag_ids: list[str]) -> dict[str, int]:
    normalized_tag_ids = sorted({str(item or "").strip() for item in tag_ids if str(item or "").strip()})
    if not normalized_tag_ids:
        return {}
    placeholders = ",".join("?" for _ in normalized_tag_ids)
    rows = fetchall_dicts(
        get_db(),
        f"""
        SELECT tag_id, COUNT(*) AS usage_count
        FROM contact_tags
        WHERE tag_id IN ({placeholders})
        GROUP BY tag_id
        """,
        tuple(normalized_tag_ids),
    )
    return {str(row.get("tag_id") or "").strip(): int(row.get("usage_count") or 0) for row in rows}


def upsert_wecom_corp_tag_catalog(*, groups: list[dict[str, Any]], tags: list[dict[str, Any]], synced_at: str) -> dict[str, int]:
    db = get_db()
    upserted_groups = 0
    upserted_tags = 0
    for group in groups:
        group_id = str(group.get("group_id") or "").strip()
        if not group_id:
            continue
        db.execute(
            """
            INSERT INTO wecom_corp_tag_groups (
                group_id, group_name, group_key, tag_count, raw_payload, synced_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?::jsonb, ?::timestamptz, CURRENT_TIMESTAMP)
            ON CONFLICT (group_id) DO UPDATE SET
                group_name = EXCLUDED.group_name,
                group_key = EXCLUDED.group_key,
                tag_count = EXCLUDED.tag_count,
                raw_payload = EXCLUDED.raw_payload,
                synced_at = EXCLUDED.synced_at,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                group_id,
                str(group.get("group_name") or "").strip(),
                str(group.get("group_key") or "").strip() or group_id,
                int(group.get("tag_count") or 0),
                json.dumps(group.get("raw_payload") or {}, ensure_ascii=False),
                synced_at,
            ),
        )
        upserted_groups += 1

    for tag in tags:
        tag_id = str(tag.get("tag_id") or "").strip()
        if not tag_id:
            continue
        db.execute(
            """
            INSERT INTO wecom_corp_tags (
                tag_id, tag_name, group_id, group_name, order_index, deleted_at, raw_payload, synced_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, NULL, ?::jsonb, ?::timestamptz, CURRENT_TIMESTAMP)
            ON CONFLICT (tag_id) DO UPDATE SET
                tag_name = EXCLUDED.tag_name,
                group_id = EXCLUDED.group_id,
                group_name = EXCLUDED.group_name,
                order_index = EXCLUDED.order_index,
                deleted_at = NULL,
                raw_payload = EXCLUDED.raw_payload,
                synced_at = EXCLUDED.synced_at,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                tag_id,
                str(tag.get("tag_name") or "").strip(),
                str(tag.get("group_id") or "").strip(),
                str(tag.get("group_name") or "").strip(),
                int(tag.get("order_index") or 0),
                json.dumps(tag.get("raw_payload") or {}, ensure_ascii=False),
                synced_at,
            ),
        )
        upserted_tags += 1
    db.commit()
    return {"upserted_groups": upserted_groups, "upserted_tags": upserted_tags}


def mark_missing_wecom_corp_tags_deleted(*, seen_tag_ids: list[str], synced_at: str) -> int:
    normalized = sorted({str(item or "").strip() for item in seen_tag_ids if str(item or "").strip()})
    db = get_db()
    if normalized:
        placeholders = ",".join("?" for _ in normalized)
        cursor = db.execute(
            f"""
            UPDATE wecom_corp_tags
            SET deleted_at = COALESCE(deleted_at, ?::timestamptz),
                synced_at = ?::timestamptz,
                updated_at = CURRENT_TIMESTAMP
            WHERE deleted_at IS NULL
              AND tag_id NOT IN ({placeholders})
            """,
            (synced_at, synced_at, *normalized),
        )
    else:
        cursor = db.execute(
            """
            UPDATE wecom_corp_tags
            SET deleted_at = COALESCE(deleted_at, ?::timestamptz),
                synced_at = ?::timestamptz,
                updated_at = CURRENT_TIMESTAMP
            WHERE deleted_at IS NULL
            """,
            (synced_at, synced_at),
        )
    db.commit()
    return int(getattr(cursor, "rowcount", 0) or 0)


def list_wecom_corp_tag_cache(*, include_deleted: bool = False) -> dict[str, Any]:
    db = get_db()
    group_rows = fetchall_dicts(
        db,
        """
        SELECT group_id, group_name, group_key, tag_count, synced_at, updated_at
        FROM wecom_corp_tag_groups
        ORDER BY group_name ASC, group_id ASC
        """,
    )
    tag_sql = """
        SELECT tag_id, tag_name, group_id, group_name, order_index, synced_at, updated_at, deleted_at
        FROM wecom_corp_tags
    """
    params: tuple[Any, ...] = ()
    if not include_deleted:
        tag_sql += " WHERE deleted_at IS NULL"
    tag_sql += " ORDER BY group_name ASC, order_index ASC, tag_name ASC, tag_id ASC"
    tag_rows = fetchall_dicts(db, tag_sql, params)
    return {"groups": group_rows, "tags": tag_rows}


def create_wecom_tag_sync_run(*, status: str = "running", operator: str = "", raw_response: dict[str, Any] | None = None) -> int:
    row = get_db().execute(
        """
        INSERT INTO sync_runs (status, owner_userid, raw_response, created_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        RETURNING id
        """,
        (status, str(operator or "").strip(), json.dumps(raw_response or {}, ensure_ascii=False)),
    ).fetchone()
    get_db().commit()
    return int((row or {}).get("id") or 0)


def finish_wecom_tag_sync_run(
    run_id: int,
    *,
    status: str,
    fetched_count: int,
    inserted_count: int,
    raw_response: dict[str, Any] | None = None,
    error_message: str = "",
) -> None:
    if not run_id:
        return
    get_db().execute(
        """
        UPDATE sync_runs
        SET status = ?,
            fetched_count = ?,
            inserted_count = ?,
            raw_response = ?,
            error_message = ?,
            finished_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            status,
            int(fetched_count or 0),
            int(inserted_count or 0),
            json.dumps(raw_response or {}, ensure_ascii=False),
            str(error_message or "").strip(),
            int(run_id),
        ),
    )
    get_db().commit()


def remove_all_tag_snapshots_for_other_users(external_userid: str, keep_userids: list[str]) -> None:
    normalized_external_userid = str(external_userid or "").strip()
    normalized_keep_userids = [str(item or "").strip() for item in keep_userids if str(item or "").strip()]
    if not normalized_external_userid:
        return
    params: list[Any] = [normalized_external_userid]
    sql = "DELETE FROM contact_tags WHERE external_userid = ?"
    if normalized_keep_userids:
        sql += " AND userid NOT IN (" + ",".join(["?"] * len(normalized_keep_userids)) + ")"
        params.extend(normalized_keep_userids)
    db = get_db()
    db.execute(sql, tuple(params))
    db.commit()


def list_other_ownerids_with_scoped_tag_snapshots(
    *,
    external_userid: str,
    owner_userid: str,
    scoped_tag_ids: list[str],
) -> list[str]:
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
    return [str(row.get("userid") or "").strip() for row in rows if str(row.get("userid") or "").strip()]
