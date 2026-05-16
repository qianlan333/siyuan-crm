from __future__ import annotations

from typing import Any

from ...db import get_db
from ...db.helpers import (
    fetch_inserted_id as _fetch_inserted_id,
    fetchall_dicts,
    fetchone_dict,
    placeholders as _placeholders,
)
from ...infra.helpers import db_bool as _db_bool


def count_admin_users() -> int:
    row = get_db().execute("SELECT COUNT(*) AS total FROM admin_users").fetchone()
    return int((row or {}).get("total") or 0)


def list_admin_users() -> list[dict[str, Any]]:
    return fetchall_dicts(
        get_db(),
        """
        SELECT
            id,
            wecom_userid,
            wecom_corpid,
            display_name,
            is_active,
            login_enabled,
            admin_level,
            auth_source,
            last_login_at,
            created_by,
            updated_by,
            created_at,
            updated_at
        FROM admin_users
        ORDER BY admin_level DESC, is_active DESC, login_enabled DESC, display_name ASC, wecom_userid ASC, id ASC
        """
    )


def list_admin_wecom_directory_members(*, wecom_corpid: str = "") -> list[dict[str, Any]]:
    normalized_corpid = str(wecom_corpid or "").strip()
    params: tuple[Any, ...] = ()
    where_sql = ""
    if normalized_corpid:
        where_sql = "WHERE wecom_corpid = ?"
        params = (normalized_corpid,)
    return fetchall_dicts(
        get_db(),
        f"""
        SELECT
            id,
            wecom_corpid,
            wecom_userid,
            display_name,
            department_ids_json,
            position,
            wecom_status,
            is_active,
            synced_at,
            raw_payload_json,
            created_at,
            updated_at
        FROM admin_wecom_directory_members
        {where_sql}
        ORDER BY is_active DESC, display_name ASC, wecom_userid ASC, id ASC
        """,
        params,
    )


def get_admin_wecom_directory_member(wecom_userid: str, *, wecom_corpid: str = "") -> dict[str, Any] | None:
    normalized_userid = str(wecom_userid or "").strip()
    normalized_corpid = str(wecom_corpid or "").strip()
    if not normalized_userid:
        return None
    if normalized_corpid:
        row = get_db().execute(
            """
            SELECT
                id,
                wecom_corpid,
                wecom_userid,
                display_name,
                department_ids_json,
                position,
                wecom_status,
                is_active,
                synced_at,
                raw_payload_json,
                created_at,
                updated_at
            FROM admin_wecom_directory_members
            WHERE wecom_corpid = ? AND wecom_userid = ?
            """,
            (normalized_corpid, normalized_userid),
        ).fetchone()
        if row:
            return dict(row)
    row = fetchone_dict(
        get_db(),
        """
        SELECT
            id,
            wecom_corpid,
            wecom_userid,
            display_name,
            department_ids_json,
            position,
            wecom_status,
            is_active,
            synced_at,
            raw_payload_json,
            created_at,
            updated_at
        FROM admin_wecom_directory_members
        WHERE wecom_userid = ?
        ORDER BY synced_at DESC, id DESC
        LIMIT 1
        """,
        (normalized_userid,),
    )
    return row


def _admin_user_with_roles_where(sql_where: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
    return fetchone_dict(
        get_db(),
        f"""
        SELECT
            id,
            wecom_userid,
            wecom_corpid,
            display_name,
            is_active,
            login_enabled,
            admin_level,
            auth_source,
            last_login_at,
            created_by,
            updated_by,
            created_at,
            updated_at
        FROM admin_users
        WHERE {sql_where}
        """,
        params,
    )


def get_admin_user_by_id(user_id: int) -> dict[str, Any] | None:
    return _admin_user_with_roles_where("id = ?", (int(user_id),))


def get_admin_user_by_wecom_userid(wecom_userid: str, *, wecom_corpid: str = "") -> dict[str, Any] | None:
    normalized_userid = str(wecom_userid or "").strip()
    normalized_corpid = str(wecom_corpid or "").strip()
    if not normalized_userid:
        return None
    if normalized_corpid:
        exact = _admin_user_with_roles_where(
            "wecom_userid = ? AND wecom_corpid = ?",
            (normalized_userid, normalized_corpid),
        )
        if exact:
            return exact
    return _admin_user_with_roles_where("wecom_userid = ?", (normalized_userid,))


def list_admin_user_roles(admin_user_ids: list[int] | None = None) -> list[dict[str, Any]]:
    params: list[Any] = []
    where_sql = ""
    if admin_user_ids:
        where_sql = f"WHERE admin_user_id IN ({_placeholders(admin_user_ids)})"
        params.extend(int(user_id) for user_id in admin_user_ids)
    return fetchall_dicts(
        get_db(),
        f"""
        SELECT
            id,
            admin_user_id,
            role_code,
            created_at
        FROM admin_user_roles
        {where_sql}
        ORDER BY admin_user_id ASC, role_code ASC, id ASC
        """,
        tuple(params),
    )


def list_active_super_admin_users(*, wecom_corpid: str = "") -> list[dict[str, Any]]:
    normalized_corpid = str(wecom_corpid or "").strip()
    params: list[Any] = []
    where_sql = "WHERE admin_level = 'super_admin' AND is_active = ? AND login_enabled = ?"
    params.extend([_db_bool(True), _db_bool(True)])
    if normalized_corpid:
        where_sql += " AND wecom_corpid = ?"
        params.append(normalized_corpid)
    return fetchall_dicts(
        get_db(),
        f"""
        SELECT
            id,
            wecom_userid,
            wecom_corpid,
            display_name,
            is_active,
            login_enabled,
            admin_level,
            auth_source,
            last_login_at,
            created_by,
            updated_by,
            created_at,
            updated_at
        FROM admin_users
        {where_sql}
        ORDER BY id ASC
        """,
        tuple(params),
    )


def upsert_admin_wecom_directory_members(
    *,
    wecom_corpid: str,
    members: list[dict[str, Any]],
    synced_at: str,
) -> int:
    normalized_corpid = str(wecom_corpid or "").strip()
    if not normalized_corpid or not members:
        return 0
    db = get_db()
    for member in members:
        db.execute(
            """
            INSERT INTO admin_wecom_directory_members (
                wecom_corpid,
                wecom_userid,
                display_name,
                department_ids_json,
                position,
                wecom_status,
                is_active,
                synced_at,
                raw_payload_json,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(wecom_corpid, wecom_userid) DO UPDATE SET
                display_name = excluded.display_name,
                department_ids_json = excluded.department_ids_json,
                position = excluded.position,
                wecom_status = excluded.wecom_status,
                is_active = excluded.is_active,
                synced_at = excluded.synced_at,
                raw_payload_json = excluded.raw_payload_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                normalized_corpid,
                str(member.get("wecom_userid") or "").strip(),
                str(member.get("display_name") or "").strip(),
                str(member.get("department_ids_json") or "[]").strip() or "[]",
                str(member.get("position") or "").strip(),
                member.get("wecom_status"),
                _db_bool(bool(member.get("is_active"))),
                str(synced_at or "").strip(),
                str(member.get("raw_payload_json") or "{}").strip() or "{}",
            ),
        )
    db.commit()
    return len(members)


def insert_admin_user(
    *,
    wecom_userid: str,
    wecom_corpid: str,
    display_name: str,
    is_active: bool,
    login_enabled: bool,
    admin_level: str,
    auth_source: str,
    created_by: str = "",
    updated_by: str = "",
) -> int:
    cursor = get_db().execute(
        """
        INSERT INTO admin_users (
            wecom_userid,
            wecom_corpid,
            display_name,
            is_active,
            login_enabled,
            admin_level,
            auth_source,
            created_by,
            updated_by,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING id
        """,
        (
            str(wecom_userid or "").strip(),
            str(wecom_corpid or "").strip(),
            str(display_name or "").strip(),
            _db_bool(is_active),
            _db_bool(login_enabled),
            str(admin_level or "").strip() or "admin",
            str(auth_source or "").strip() or "wecom_sso",
            str(created_by or "").strip(),
            str(updated_by or "").strip(),
        ),
    )
    get_db().commit()
    return _fetch_inserted_id(cursor)


def update_admin_user(
    *,
    user_id: int,
    wecom_userid: str,
    wecom_corpid: str,
    display_name: str,
    is_active: bool,
    login_enabled: bool,
    admin_level: str,
    auth_source: str,
    updated_by: str = "",
) -> None:
    get_db().execute(
        """
        UPDATE admin_users
        SET wecom_userid = ?,
            wecom_corpid = ?,
            display_name = ?,
            is_active = ?,
            login_enabled = ?,
            admin_level = ?,
            auth_source = ?,
            updated_by = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            str(wecom_userid or "").strip(),
            str(wecom_corpid or "").strip(),
            str(display_name or "").strip(),
            _db_bool(is_active),
            _db_bool(login_enabled),
            str(admin_level or "").strip() or "admin",
            str(auth_source or "").strip() or "wecom_sso",
            str(updated_by or "").strip(),
            int(user_id),
        ),
    )
    get_db().commit()


def replace_admin_user_roles(*, admin_user_id: int, role_codes: list[str]) -> None:
    db = get_db()
    db.execute("DELETE FROM admin_user_roles WHERE admin_user_id = ?", (int(admin_user_id),))
    for role_code in role_codes:
        db.execute(
            """
            INSERT INTO admin_user_roles (admin_user_id, role_code, created_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            """,
            (int(admin_user_id), str(role_code or "").strip()),
        )
    db.commit()


def update_admin_user_last_login(user_id: int) -> None:
    get_db().execute(
        """
        UPDATE admin_users
        SET last_login_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (int(user_id),),
    )
    get_db().commit()


def insert_admin_login_audit(
    *,
    admin_user_id: int | None,
    login_type: str,
    login_result: str,
    ip: str,
    user_agent: str,
) -> None:
    get_db().execute(
        """
        INSERT INTO admin_login_audit (
            admin_user_id,
            login_type,
            login_result,
            ip,
            user_agent,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (
            int(admin_user_id) if admin_user_id else None,
            str(login_type or "").strip(),
            str(login_result or "").strip(),
            str(ip or "").strip(),
            str(user_agent or "").strip(),
        ),
    )
    get_db().commit()


def list_admin_login_audit(*, limit: int = 20) -> list[dict[str, Any]]:
    return fetchall_dicts(
        get_db(),
        """
        SELECT
            a.id,
            a.admin_user_id,
            a.login_type,
            a.login_result,
            a.ip,
            a.user_agent,
            a.created_at,
            u.wecom_userid,
            u.display_name
        FROM admin_login_audit a
        LEFT JOIN admin_users u ON u.id = a.admin_user_id
        ORDER BY a.id DESC
        LIMIT ?
        """,
        (int(limit),),
    )


def create_admin_sso_state(*, state_token: str, login_kind: str, next_path: str, expires_at: str) -> None:
    get_db().execute(
        """
        INSERT INTO admin_sso_states (
            state_token,
            login_kind,
            next_path,
            expires_at,
            created_at
        )
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (
            str(state_token or "").strip(),
            str(login_kind or "").strip(),
            str(next_path or "").strip(),
            str(expires_at or "").strip(),
        ),
    )
    get_db().commit()


def get_admin_sso_state(state_token: str) -> dict[str, Any] | None:
    return fetchone_dict(
        get_db(),
        """
        SELECT
            state_token,
            login_kind,
            next_path,
            expires_at,
            created_at
        FROM admin_sso_states
        WHERE state_token = ?
        """,
        (str(state_token or "").strip(),),
    )


def delete_admin_sso_state(state_token: str) -> None:
    get_db().execute("DELETE FROM admin_sso_states WHERE state_token = ?", (str(state_token or "").strip(),))
    get_db().commit()


def purge_expired_admin_sso_states(now_value: str) -> None:
    get_db().execute(
        """
        DELETE FROM admin_sso_states
        WHERE expires_at <> ''
          AND expires_at <= ?
        """,
        (str(now_value or "").strip(),),
    )
    get_db().commit()
