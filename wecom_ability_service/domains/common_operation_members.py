from __future__ import annotations

from typing import Any

from aicrm_next.shared.operation_members import (
    bool_from_query,
    clamp_page,
    clamp_page_size,
    clean_text,
    normalize_scope,
    operation_members_payload,
)

from ..db import get_db


def _fetch(sql: str, *, source: str, priority: int) -> list[dict[str, Any]]:
    try:
        rows = [dict(row) for row in get_db().execute(sql).fetchall() or []]
    except Exception:
        return []
    for row in rows:
        row.setdefault("source", source)
        row.setdefault("priority", priority)
    return rows


def list_operation_member_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    rows.extend(
        _fetch(
            """
            SELECT
                wecom_userid AS user_id,
                display_name,
                position,
                wecom_status,
                is_active,
                raw_payload_json,
                '' AS avatar_url,
                '' AS department_name
            FROM admin_wecom_directory_members
            WHERE COALESCE(wecom_userid, '') <> ''
            """,
            source="wecom_directory",
            priority=10,
        )
    )
    rows.extend(
        _fetch(
            """
            SELECT
                wecom_userid AS user_id,
                display_name,
                is_active,
                '' AS avatar_url,
                '' AS department_name
            FROM admin_users
            WHERE COALESCE(wecom_userid, '') <> ''
            """,
            source="admin_user",
            priority=20,
        )
    )
    rows.extend(
        _fetch(
            """
            SELECT
                userid AS user_id,
                display_name,
                role,
                active AS is_active,
                '' AS avatar_url,
                '' AS department_name
            FROM owner_role_map
            WHERE COALESCE(userid, '') <> ''
            """,
            source="owner_role_map",
            priority=30,
        )
    )
    for sql, source in [
        ("SELECT DISTINCT owner_userid AS user_id FROM group_chats WHERE COALESCE(owner_userid, '') <> ''", "group_chats"),
        (
            "SELECT DISTINCT owner_userid AS user_id FROM automation_group_ops_plans WHERE COALESCE(owner_userid, '') <> ''",
            "group_ops_plan_owner",
        ),
        (
            "SELECT DISTINCT owner_staff_id AS user_id FROM automation_channel WHERE COALESCE(owner_staff_id, '') <> ''",
            "channel_owner_field",
        ),
        (
            "SELECT DISTINCT owner_staff_id AS user_id FROM automation_member WHERE COALESCE(owner_staff_id, '') <> ''",
            "automation_member_owner_field",
        ),
        (
            "SELECT DISTINCT follow_user_userid AS user_id FROM wecom_external_contact_identity_map WHERE COALESCE(follow_user_userid, '') <> ''",
            "external_contact_follow_user",
        ),
        (
            "SELECT DISTINCT user_id AS user_id FROM wecom_external_contact_follow_users WHERE COALESCE(user_id, '') <> ''",
            "external_contact_follow_user",
        ),
    ]:
        rows.extend(_fetch(sql, source=source, priority=80))
    return rows


def search_operation_members(
    *,
    q: str = "",
    scope: str = "common",
    page: int = 1,
    page_size: int = 30,
    include_inactive: bool = False,
) -> dict[str, Any]:
    return operation_members_payload(
        list_operation_member_rows(),
        q=clean_text(q),
        scope=normalize_scope(scope),
        page=clamp_page(page),
        page_size=clamp_page_size(page_size),
        include_inactive=include_inactive,
    )


def search_operation_members_from_request_args(args: Any) -> dict[str, Any]:
    return search_operation_members(
        q=clean_text(args.get("q")),
        scope=clean_text(args.get("scope")),
        page=clamp_page(args.get("page")),
        page_size=clamp_page_size(args.get("page_size")),
        include_inactive=bool_from_query(args.get("include_inactive")),
    )
