"""Member / person / contact / stage / segment data-access (阶段 4.5).

Extracted from repo.py. Covers automation_member, person/external_contact
lookup, stage metrics, segment filtering, active automation membership.
External callers keep using ``automation_conversion.repo.X``.
"""

from __future__ import annotations

from typing import Any

from ...db import cast_text, get_db, is_postgres
from ._repo_helpers import (
    _db_bool,
    _fetchall_dicts,
    _fetchone_dict,
    _json_dumps,
    _json_loads,
    _normalized_text,
    _row_bool,
)


def lookup_person_id_by_external_contact_id(external_contact_id: str) -> int | None:
    row = _fetchone_dict(
        """
        SELECT person_id
        FROM external_contact_bindings
        WHERE external_userid = ?
        LIMIT 1
        """,
        (_normalized_text(external_contact_id),),
    )
    person_id = row.get("person_id") if row else None
    return int(person_id) if person_id not in (None, "") else None


def lookup_person_id_by_phone(phone: str) -> int | None:
    row = _fetchone_dict(
        """
        SELECT id
        FROM people
        WHERE mobile = ?
        LIMIT 1
        """,
        (_normalized_text(phone),),
    )
    person_id = row.get("id") if row else None
    return int(person_id) if person_id not in (None, "") else None


def list_external_contact_ids_by_person_id(person_id: int | None) -> list[str]:
    if person_id in (None, ""):
        return []
    rows = _fetchall_dicts(
        """
        SELECT external_userid
        FROM external_contact_bindings
        WHERE person_id = ?
        ORDER BY updated_at DESC, external_userid ASC
        """,
        (int(person_id),),
    )
    return [_normalized_text(row.get("external_userid")) for row in rows if _normalized_text(row.get("external_userid"))]


def find_latest_external_contact_id_by_phone(phone: str) -> str:
    normalized_phone = _normalized_text(phone)
    if not normalized_phone:
        return ""
    binding_ordering = f"COALESCE({cast_text('b.updated_at')}, {cast_text('b.created_at')}, '')"
    class_status_ordering = f"COALESCE({cast_text('updated_at')}, {cast_text('created_at')}, '')"
    submission_ordering = f"COALESCE({cast_text('submitted_at')}, '')"
    sql = f"""
    SELECT external_userid
    FROM (
        SELECT b.external_userid, {binding_ordering} AS ordering_value
        FROM external_contact_bindings b
        INNER JOIN people p ON p.id = b.person_id
        WHERE p.mobile = ?

        UNION ALL

        SELECT external_userid, {class_status_ordering} AS ordering_value
        FROM class_user_status_current
        WHERE mobile_snapshot = ?

        UNION ALL

        SELECT external_userid, {submission_ordering} AS ordering_value
        FROM questionnaire_submissions
        WHERE mobile_snapshot = ? AND external_userid IS NOT NULL AND external_userid <> ''
    ) candidates
    WHERE external_userid IS NOT NULL AND external_userid <> ''
    ORDER BY ordering_value DESC, external_userid ASC
    LIMIT 1
    """
    row = _fetchone_dict(sql, (normalized_phone, normalized_phone, normalized_phone))
    return _normalized_text((row or {}).get("external_userid"))


def get_member_by_id(member_id: int) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_member
        WHERE id = ?
        LIMIT 1
        """,
        (int(member_id),),
    )


def get_member_by_external_contact_id(external_contact_id: str) -> dict[str, Any] | None:
    normalized = _normalized_text(external_contact_id)
    if not normalized:
        return None
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_member
        WHERE external_contact_id = ?
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (normalized,),
    )


def get_member_by_phone(phone: str) -> dict[str, Any] | None:
    normalized = _normalized_text(phone)
    if not normalized:
        return None
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_member
        WHERE phone = ?
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (normalized,),
    )


def list_members_by_ids(member_ids: list[int]) -> list[dict[str, Any]]:
    normalized_ids = [int(item) for item in member_ids if str(item).strip()]
    if not normalized_ids:
        return []
    placeholders = ",".join("?" for _ in normalized_ids)
    return _fetchall_dicts(
        f"""
        SELECT *
        FROM automation_member
        WHERE id IN ({placeholders})
        ORDER BY id ASC
        """,
        tuple(normalized_ids),
    )


def insert_member(payload: dict[str, Any]) -> dict[str, Any]:
    db = get_db()
    params = (
        _normalized_text(payload.get("external_contact_id")),
        _normalized_text(payload.get("phone")),
        payload.get("master_customer_id"),
        _normalized_text(payload.get("owner_staff_id")),
        _db_bool(bool(payload.get("in_pool"))),
        _normalized_text(payload.get("current_pool")),
        _normalized_text(payload.get("follow_type")),
        _normalized_text(payload.get("questionnaire_status")),
        _normalized_text(payload.get("decision_source")),
        _normalized_text(payload.get("source_type")),
        payload.get("source_channel_id"),
        _normalized_text(payload.get("last_active_pool")),
        _normalized_text(payload.get("joined_at")),
        _normalized_text(payload.get("last_ai_push_at")),
        _normalized_text(payload.get("ai_cooldown_until")),
    )
    row = db.execute(
        """
        INSERT INTO automation_member (
            external_contact_id,
            phone,
            master_customer_id,
            owner_staff_id,
            in_pool,
            current_pool,
            follow_type,
            questionnaire_status,
            decision_source,
            source_type,
            source_channel_id,
            last_active_pool,
            joined_at,
            last_ai_push_at,
            ai_cooldown_until,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        params,
    ).fetchone()
    return dict(row) if row else {}


def update_member(member_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    db = get_db()
    params = (
        _normalized_text(payload.get("external_contact_id")),
        _normalized_text(payload.get("phone")),
        payload.get("master_customer_id"),
        _normalized_text(payload.get("owner_staff_id")),
        _db_bool(bool(payload.get("in_pool"))),
        _normalized_text(payload.get("current_pool")),
        _normalized_text(payload.get("follow_type")),
        _normalized_text(payload.get("questionnaire_status")),
        _normalized_text(payload.get("decision_source")),
        _normalized_text(payload.get("source_type")),
        payload.get("source_channel_id"),
        _normalized_text(payload.get("last_active_pool")),
        _normalized_text(payload.get("joined_at")),
        _normalized_text(payload.get("last_ai_push_at")),
        _normalized_text(payload.get("ai_cooldown_until")),
        int(member_id),
    )
    row = db.execute(
        """
        UPDATE automation_member
        SET external_contact_id = ?,
            phone = ?,
            master_customer_id = ?,
            owner_staff_id = ?,
            in_pool = ?,
            current_pool = ?,
            follow_type = ?,
            questionnaire_status = ?,
            decision_source = ?,
            source_type = ?,
            source_channel_id = ?,
            last_active_pool = ?,
            joined_at = ?,
            last_ai_push_at = ?,
            ai_cooldown_until = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        RETURNING *
        """,
        params,
    ).fetchone()
    return dict(row) if row else {}


def list_active_automation_external_contact_ids(external_contact_ids: list[str]) -> list[str]:
    normalized_ids = [_normalized_text(item) for item in external_contact_ids if _normalized_text(item)]
    if not normalized_ids:
        return []
    placeholders = ",".join("?" for _ in normalized_ids)
    rows = _fetchall_dicts(
        f"""
        SELECT external_contact_id
        FROM automation_member
        WHERE in_pool = ?
          AND external_contact_id IN ({placeholders})
        ORDER BY external_contact_id ASC
        """,
        (_db_bool(True), *normalized_ids),
    )
    return [_normalized_text(row.get("external_contact_id")) for row in rows if _normalized_text(row.get("external_contact_id"))]


def list_active_automation_members_by_external_contact_ids(external_contact_ids: list[str]) -> list[dict[str, Any]]:
    normalized_ids = [_normalized_text(item) for item in external_contact_ids if _normalized_text(item)]
    if not normalized_ids:
        return []
    placeholders = ",".join("?" for _ in normalized_ids)
    return _fetchall_dicts(
        f"""
        SELECT *
        FROM automation_member
        WHERE in_pool = ?
          AND external_contact_id IN ({placeholders})
        ORDER BY updated_at DESC, id DESC
        """,
        (_db_bool(True), *normalized_ids),
    )


def get_stage_counts() -> dict[str, int]:
    rows = _fetchall_dicts(
        """
        SELECT current_pool, COUNT(*) AS total
        FROM automation_member
        GROUP BY current_pool
        """
    )
    return {_normalized_text(row.get("current_pool")): int(row.get("total") or 0) for row in rows}


def get_stage_metrics() -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT
            current_audience_code AS current_pool,
            COUNT(*) AS total_count,
            COALESCE(SUM(CASE WHEN follow_type = 'focus' THEN 1 ELSE 0 END), 0) AS focus_count,
            COALESCE(SUM(CASE WHEN follow_type = 'normal' THEN 1 ELSE 0 END), 0) AS normal_count,
            COALESCE(SUM(CASE WHEN joined_at IS NOT NULL AND joined_at <> '' AND DATE(joined_at) = DATE(CURRENT_TIMESTAMP) THEN 1 ELSE 0 END), 0) AS today_new_count
        FROM automation_member
        WHERE current_audience_code IN ('pending_questionnaire', 'operating', 'converted')
        GROUP BY current_audience_code
        """
    )


def get_overview_counts() -> dict[str, int]:
    row = _fetchone_dict(
        """
        SELECT
            COALESCE(SUM(CASE WHEN in_pool THEN 1 ELSE 0 END), 0) AS in_pool_total,
            COALESCE(SUM(CASE WHEN joined_at IS NOT NULL AND joined_at <> '' AND DATE(joined_at) = DATE(CURRENT_TIMESTAMP) THEN 1 ELSE 0 END), 0) AS today_joined,
            COALESCE(SUM(CASE WHEN current_audience_code = 'pending_questionnaire' THEN 1 ELSE 0 END), 0) AS questionnaire_pending,
            COALESCE(SUM(CASE WHEN current_audience_code = 'operating' THEN 1 ELSE 0 END), 0) AS operating_total,
            COALESCE(SUM(CASE WHEN current_audience_code = 'converted' THEN 1 ELSE 0 END), 0) AS converted_total
        FROM automation_member
        """
    ) or {}
    return {key: int(row.get(key) or 0) for key in row}


def list_stage_members(*, current_pool: str, keyword: str = "", limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    normalized_keyword = _normalized_text(keyword)
    normalized_pool = _normalized_text(current_pool)
    params: list[Any] = [normalized_pool]
    if normalized_pool in {"pending_questionnaire", "operating", "converted"}:
        sql = """
        SELECT *
        FROM automation_member
        WHERE current_audience_code = ?
        """
    else:
        sql = """
        SELECT *
        FROM automation_member
        WHERE current_pool = ?
        """
    if normalized_keyword:
        sql += """
          AND (
            external_contact_id LIKE ?
            OR phone LIKE ?
          )
        """
        like_value = f"%{normalized_keyword}%"
        params.extend([like_value, like_value])
    sql += """
    ORDER BY updated_at DESC, id DESC
    LIMIT ?
    OFFSET ?
    """
    params.extend([int(limit), int(offset)])
    return _fetchall_dicts(sql, tuple(params))


def list_stage_members_for_manual_send(*, current_pool: str) -> list[dict[str, Any]]:
    normalized_pool = _normalized_text(current_pool)
    if normalized_pool not in {"pending_questionnaire", "operating", "converted"}:
        return []
    return _fetchall_dicts(
        """
        SELECT *
        FROM automation_member
        WHERE current_audience_code = ?
        ORDER BY updated_at DESC, id DESC
        """,
        (normalized_pool,),
    )


_VALID_AUDIENCE_CODES = ("pending_questionnaire", "operating", "converted")


def _normalize_segment_keys(values: list[str] | None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values or []:
        text = _normalized_text(value)
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def _build_segment_filter_sql(
    *,
    pool_keys: list[str],
    profile_keys: list[str],
    behavior_keys: list[str],
    keyword: str,
    select_clause: str,
    order_by: str = "",
    limit: int | None = None,
    offset: int | None = None,
) -> tuple[str, tuple[Any, ...]]:
    pools = [p for p in _normalize_segment_keys(pool_keys) if p in _VALID_AUDIENCE_CODES]
    profiles = _normalize_segment_keys(profile_keys)
    behaviors = _normalize_segment_keys(behavior_keys)
    normalized_keyword = _normalized_text(keyword)
    where_parts: list[str] = []
    params: list[Any] = []
    if pools:
        placeholders = ",".join(["?"] * len(pools))
        where_parts.append(f"m.current_audience_code IN ({placeholders})")
        params.extend(pools)
    else:
        placeholders = ",".join(["?"] * len(_VALID_AUDIENCE_CODES))
        where_parts.append(f"m.current_audience_code IN ({placeholders})")
        params.extend(_VALID_AUDIENCE_CODES)
    if profiles:
        placeholders = ",".join(["?"] * len(profiles))
        where_parts.append(f"m.profile_segment_key IN ({placeholders})")
        params.extend(profiles)
    if behaviors:
        placeholders = ",".join(["?"] * len(behaviors))
        where_parts.append(f"m.behavior_tier_key IN ({placeholders})")
        params.extend(behaviors)
    if normalized_keyword:
        like_value = f"%{normalized_keyword}%"
        where_parts.append(
            "(m.phone LIKE ? OR m.external_contact_id LIKE ? OR COALESCE(c.customer_name, '') LIKE ?)"
        )
        params.extend([like_value, like_value, like_value])
    where_sql = " AND ".join(where_parts)
    sql = f"""
        {select_clause}
        FROM automation_member m
        LEFT JOIN contacts c
          ON c.external_userid = m.external_contact_id
         AND m.external_contact_id <> ''
        WHERE {where_sql}
    """
    if order_by:
        sql += f" ORDER BY {order_by}"
    if limit is not None:
        sql += " LIMIT ?"
        params.append(int(limit))
    if offset is not None:
        sql += " OFFSET ?"
        params.append(int(offset))
    return sql, tuple(params)


def list_members_by_segment_filter(
    *,
    pool_keys: list[str] | None = None,
    profile_keys: list[str] | None = None,
    behavior_keys: list[str] | None = None,
    keyword: str = "",
    offset: int = 0,
    limit: int = 50,
) -> list[dict[str, Any]]:
    sql, params = _build_segment_filter_sql(
        pool_keys=list(pool_keys or []),
        profile_keys=list(profile_keys or []),
        behavior_keys=list(behavior_keys or []),
        keyword=keyword,
        select_clause="SELECT m.*, c.customer_name AS customer_name",
        order_by="m.updated_at DESC, m.id DESC",
        limit=limit,
        offset=offset,
    )
    return _fetchall_dicts(sql, params)


def count_members_by_segment_filter(
    *,
    pool_keys: list[str] | None = None,
    profile_keys: list[str] | None = None,
    behavior_keys: list[str] | None = None,
    keyword: str = "",
) -> int:
    sql, params = _build_segment_filter_sql(
        pool_keys=list(pool_keys or []),
        profile_keys=list(profile_keys or []),
        behavior_keys=list(behavior_keys or []),
        keyword=keyword,
        select_clause="SELECT COUNT(*) AS total",
    )
    row = _fetchone_dict(sql, params) or {}
    return int(row.get("total") or 0)


def aggregate_member_segment_dimensions() -> dict[str, list[dict[str, Any]]]:
    """Counts per pool / profile / behavior, used by the chip filter UI."""
    pool_rows = _fetchall_dicts(
        """
        SELECT current_audience_code AS key, COUNT(*) AS total
        FROM automation_member
        WHERE current_audience_code IN ('pending_questionnaire', 'operating', 'converted')
        GROUP BY current_audience_code
        """
    )
    profile_rows = _fetchall_dicts(
        """
        SELECT profile_segment_key AS key, COUNT(*) AS total
        FROM automation_member
        WHERE current_audience_code IN ('pending_questionnaire', 'operating', 'converted')
        GROUP BY profile_segment_key
        ORDER BY total DESC
        """
    )
    behavior_rows = _fetchall_dicts(
        """
        SELECT behavior_tier_key AS key, COUNT(*) AS total
        FROM automation_member
        WHERE current_audience_code IN ('pending_questionnaire', 'operating', 'converted')
        GROUP BY behavior_tier_key
        ORDER BY total DESC
        """
    )

    def _normalize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {"key": _normalized_text(row.get("key")), "total": int(row.get("total") or 0)}
            for row in rows
        ]

    return {
        "pools": _normalize(pool_rows),
        "profiles": _normalize(profile_rows),
        "behaviors": _normalize(behavior_rows),
    }


def count_stage_members(*, current_pool: str, keyword: str = "") -> int:
    normalized_keyword = _normalized_text(keyword)
    normalized_pool = _normalized_text(current_pool)
    params: list[Any] = [normalized_pool]
    if normalized_pool in {"pending_questionnaire", "operating", "converted"}:
        sql = """
        SELECT COUNT(*) AS total
        FROM automation_member
        WHERE current_audience_code = ?
        """
    else:
        sql = """
        SELECT COUNT(*) AS total
        FROM automation_member
        WHERE current_pool = ?
        """
    if normalized_keyword:
        like_value = f"%{normalized_keyword}%"
        sql += """
          AND (
            external_contact_id LIKE ?
            OR phone LIKE ?
          )
        """
        params.extend([like_value, like_value])
    row = _fetchone_dict(sql, tuple(params)) or {}
    return int(row.get("total") or 0)


def list_members_for_silent_refresh() -> list[dict[str, Any]]:
    return []


def list_members_for_message_activity_sync(*, current_pools: list[str]) -> list[dict[str, Any]]:
    normalized_pools = [_normalized_text(item) for item in current_pools if _normalized_text(item)]
    if not normalized_pools:
        return []
    placeholders = ",".join("?" for _ in normalized_pools)
    return _fetchall_dicts(
        f"""
        SELECT *
        FROM automation_member
        WHERE in_pool = ?
          AND current_pool IN ({placeholders})
        ORDER BY current_pool ASC, updated_at DESC, id ASC
        """,
        (_db_bool(True), *normalized_pools),
    )




__all__ = [
    "_build_segment_filter_sql",
    "_normalize_segment_keys",
    "aggregate_member_segment_dimensions",
    "count_members_by_segment_filter",
    "count_stage_members",
    "find_latest_external_contact_id_by_phone",
    "get_member_by_external_contact_id",
    "get_member_by_id",
    "get_member_by_phone",
    "get_overview_counts",
    "get_stage_counts",
    "get_stage_metrics",
    "insert_member",
    "list_active_automation_external_contact_ids",
    "list_active_automation_members_by_external_contact_ids",
    "list_external_contact_ids_by_person_id",
    "list_members_by_ids",
    "list_members_by_segment_filter",
    "list_members_for_message_activity_sync",
    "list_members_for_silent_refresh",
    "list_stage_members",
    "list_stage_members_for_manual_send",
    "lookup_person_id_by_external_contact_id",
    "lookup_person_id_by_phone",
    "update_member",
]
