from __future__ import annotations

from typing import Any

from ...db import get_db, get_db_backend


def _db_bool(value: bool) -> bool | int:
    return value if get_db_backend() == "postgres" else (1 if value else 0)


def list_signup_scope_external_userids(corp_id: str) -> list[str]:
    rows = get_db().execute(
        """
        SELECT external_userid
        FROM (
            SELECT external_userid FROM contacts
            UNION
            SELECT external_userid
            FROM wecom_external_contact_follow_users
            WHERE corp_id = ? AND relation_status = 'active'
            UNION
            SELECT external_userid
            FROM wecom_external_contact_identity_map
            WHERE corp_id = ? AND status = 'active'
        ) AS signup_scope
        WHERE external_userid IS NOT NULL AND external_userid <> ''
        ORDER BY external_userid ASC
        """,
        (corp_id, corp_id),
    ).fetchall()
    return [str(row.get("external_userid") or "").strip() for row in rows if str(row.get("external_userid") or "").strip()]


def list_class_user_live_base_rows(corp_id: str) -> list[dict[str, Any]]:
    rows = get_db().execute(
        """
        SELECT
            scope.external_userid,
            COALESCE(c.customer_name, '') AS customer_name,
            COALESCE(c.owner_userid, '') AS owner_userid,
            c.updated_at AS contact_updated_at,
            COALESCE(p.mobile, '') AS mobile,
            COALESCE(primary_fu.user_id, '') AS primary_follow_user_userid,
            COALESCE(owner_map.display_name, '') AS follow_user_display_name,
            COALESCE(identity_map.follow_user_userid, '') AS identity_follow_user_userid
        FROM (
            SELECT external_userid FROM contacts
            UNION
            SELECT external_userid
            FROM wecom_external_contact_follow_users
            WHERE corp_id = ? AND relation_status = 'active'
            UNION
            SELECT external_userid
            FROM wecom_external_contact_identity_map
            WHERE corp_id = ? AND status = 'active'
        ) AS scope
        LEFT JOIN contacts c
          ON c.external_userid = scope.external_userid
        LEFT JOIN external_contact_bindings bindings
          ON bindings.external_userid = scope.external_userid
        LEFT JOIN people p
          ON p.id = bindings.person_id
        LEFT JOIN wecom_external_contact_identity_map identity_map
          ON identity_map.corp_id = ? AND identity_map.external_userid = scope.external_userid
        LEFT JOIN wecom_external_contact_follow_users primary_fu
          ON primary_fu.corp_id = ?
         AND primary_fu.external_userid = scope.external_userid
         AND primary_fu.relation_status = 'active'
         AND primary_fu.is_primary = ?
        LEFT JOIN owner_role_map owner_map
          ON owner_map.userid = COALESCE(primary_fu.user_id, c.owner_userid, identity_map.follow_user_userid, '')
        ORDER BY scope.external_userid ASC
        """,
        (
            corp_id,
            corp_id,
            corp_id,
            corp_id,
            _db_bool(True),
        ),
    ).fetchall()
    return [dict(row) for row in rows]


def get_class_user_status_current(external_userid: str):
    return get_db().execute(
        """
        SELECT
            external_userid,
            signup_status,
            signup_label_name,
            customer_name_snapshot,
            owner_userid_snapshot,
            mobile_snapshot,
            set_by_userid,
            set_at,
            wecom_tag_sync_status,
            wecom_tag_sync_error,
            status_flags_json,
            created_at,
            updated_at
        FROM class_user_status_current
        WHERE external_userid = ?
        """,
        (external_userid,),
    ).fetchone()


def upsert_class_user_status_current(
    *,
    external_userid: str,
    signup_status: str,
    signup_label_name: str,
    customer_name_snapshot: str,
    owner_userid_snapshot: str,
    mobile_snapshot: str,
    set_by_userid: str,
    set_at: str | None = None,
    wecom_tag_sync_status: str = "pending",
    wecom_tag_sync_error: str = "",
    status_flags_json: str = "{}",
) -> None:
    normalized_set_at = str(set_at or "").strip()
    db = get_db()
    if normalized_set_at:
        db.execute(
            """
            INSERT INTO class_user_status_current (
                external_userid,
                signup_status,
                signup_label_name,
                customer_name_snapshot,
                owner_userid_snapshot,
                mobile_snapshot,
                set_by_userid,
                set_at,
                wecom_tag_sync_status,
                wecom_tag_sync_error,
                status_flags_json,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(external_userid) DO UPDATE SET
                signup_status = excluded.signup_status,
                signup_label_name = excluded.signup_label_name,
                customer_name_snapshot = excluded.customer_name_snapshot,
                owner_userid_snapshot = excluded.owner_userid_snapshot,
                mobile_snapshot = excluded.mobile_snapshot,
                set_by_userid = excluded.set_by_userid,
                set_at = excluded.set_at,
                wecom_tag_sync_status = excluded.wecom_tag_sync_status,
                wecom_tag_sync_error = excluded.wecom_tag_sync_error,
                status_flags_json = excluded.status_flags_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                external_userid,
                signup_status,
                signup_label_name,
                customer_name_snapshot,
                owner_userid_snapshot,
                mobile_snapshot,
                set_by_userid,
                normalized_set_at,
                wecom_tag_sync_status,
                wecom_tag_sync_error,
                status_flags_json,
            ),
        )
    else:
        db.execute(
            """
            INSERT INTO class_user_status_current (
                external_userid,
                signup_status,
                signup_label_name,
                customer_name_snapshot,
                owner_userid_snapshot,
                mobile_snapshot,
                set_by_userid,
                set_at,
                wecom_tag_sync_status,
                wecom_tag_sync_error,
                status_flags_json,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(external_userid) DO UPDATE SET
                signup_status = excluded.signup_status,
                signup_label_name = excluded.signup_label_name,
                customer_name_snapshot = excluded.customer_name_snapshot,
                owner_userid_snapshot = excluded.owner_userid_snapshot,
                mobile_snapshot = excluded.mobile_snapshot,
                set_by_userid = excluded.set_by_userid,
                set_at = excluded.set_at,
                wecom_tag_sync_status = excluded.wecom_tag_sync_status,
                wecom_tag_sync_error = excluded.wecom_tag_sync_error,
                status_flags_json = excluded.status_flags_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                external_userid,
                signup_status,
                signup_label_name,
                customer_name_snapshot,
                owner_userid_snapshot,
                mobile_snapshot,
                set_by_userid,
                wecom_tag_sync_status,
                wecom_tag_sync_error,
                status_flags_json,
            ),
        )
    db.commit()


def delete_class_user_status_current(external_userid: str) -> None:
    db = get_db()
    db.execute(
        """
        DELETE FROM class_user_status_current
        WHERE external_userid = ?
        """,
        (external_userid,),
    )
    db.commit()


def append_class_user_status_history(
    *,
    external_userid: str,
    old_signup_status: str,
    new_signup_status: str,
    old_label_name: str,
    new_label_name: str,
    customer_name_snapshot: str,
    owner_userid_snapshot: str,
    mobile_snapshot: str,
    set_by_userid: str,
    set_at: str | None = None,
    wecom_tag_sync_status: str = "pending",
    wecom_tag_sync_error: str = "",
    status_flags_json: str = "{}",
) -> None:
    normalized_set_at = str(set_at or "").strip()
    db = get_db()
    if normalized_set_at:
        db.execute(
            """
            INSERT INTO class_user_status_history (
                external_userid,
                old_signup_status,
                new_signup_status,
                old_label_name,
                new_label_name,
                customer_name_snapshot,
                owner_userid_snapshot,
                mobile_snapshot,
                set_by_userid,
                set_at,
                wecom_tag_sync_status,
                wecom_tag_sync_error,
                status_flags_json,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                external_userid,
                old_signup_status,
                new_signup_status,
                old_label_name,
                new_label_name,
                customer_name_snapshot,
                owner_userid_snapshot,
                mobile_snapshot,
                set_by_userid,
                normalized_set_at,
                wecom_tag_sync_status,
                wecom_tag_sync_error,
                status_flags_json,
            ),
        )
    else:
        db.execute(
            """
            INSERT INTO class_user_status_history (
                external_userid,
                old_signup_status,
                new_signup_status,
                old_label_name,
                new_label_name,
                customer_name_snapshot,
                owner_userid_snapshot,
                mobile_snapshot,
                set_by_userid,
                set_at,
                wecom_tag_sync_status,
                wecom_tag_sync_error,
                status_flags_json,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                external_userid,
                old_signup_status,
                new_signup_status,
                old_label_name,
                new_label_name,
                customer_name_snapshot,
                owner_userid_snapshot,
                mobile_snapshot,
                set_by_userid,
                wecom_tag_sync_status,
                wecom_tag_sync_error,
                status_flags_json,
            ),
        )
    db.commit()


def update_class_user_status_sync_result(
    external_userid: str,
    *,
    wecom_tag_sync_status: str,
    wecom_tag_sync_error: str = "",
) -> None:
    db = get_db()
    db.execute(
        """
        UPDATE class_user_status_current
        SET wecom_tag_sync_status = ?,
            wecom_tag_sync_error = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE external_userid = ?
        """,
        (wecom_tag_sync_status, wecom_tag_sync_error, external_userid),
    )
    db.execute(
        """
        UPDATE class_user_status_history
        SET wecom_tag_sync_status = ?,
            wecom_tag_sync_error = ?
        WHERE id = (
            SELECT id
            FROM class_user_status_history
            WHERE external_userid = ?
            ORDER BY id DESC
            LIMIT 1
        )
        """,
        (wecom_tag_sync_status, wecom_tag_sync_error, external_userid),
    )
    db.commit()


def list_class_user_management_rows():
    return get_db().execute(
        """
        SELECT
            current_status.external_userid,
            current_status.signup_status,
            current_status.signup_label_name,
            current_status.customer_name_snapshot,
            current_status.owner_userid_snapshot,
            current_status.mobile_snapshot,
            current_status.set_by_userid,
            current_status.set_at,
            current_status.wecom_tag_sync_status,
            current_status.wecom_tag_sync_error,
            current_status.updated_at AS current_updated_at,
            COALESCE(c.customer_name, '') AS contact_customer_name,
            COALESCE(c.owner_userid, '') AS contact_owner_userid,
            COALESCE(p.mobile, '') AS bound_mobile,
            COALESCE(owner_map.display_name, '') AS follow_user_display_name
        FROM class_user_status_current current_status
        LEFT JOIN contacts c
          ON c.external_userid = current_status.external_userid
        LEFT JOIN external_contact_bindings bindings
          ON bindings.external_userid = current_status.external_userid
        LEFT JOIN people p
          ON p.id = bindings.person_id
        LEFT JOIN owner_role_map owner_map
          ON owner_map.userid = COALESCE(current_status.owner_userid_snapshot, c.owner_userid, '')
        ORDER BY current_status.updated_at DESC, current_status.external_userid DESC
        """
    ).fetchall()


def list_class_user_status_history_rows(limit: int = 100):
    normalized_limit = max(1, min(int(limit or 100), 500))
    rows = get_db().execute(
        """
        SELECT
            id,
            external_userid,
            old_signup_status,
            new_signup_status,
            old_label_name,
            new_label_name,
            customer_name_snapshot,
            owner_userid_snapshot,
            mobile_snapshot,
            set_by_userid,
            set_at,
            wecom_tag_sync_status,
            wecom_tag_sync_error,
            created_at
        FROM class_user_status_history
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (normalized_limit,),
    ).fetchall()
    return rows, normalized_limit


def count_class_user_status_history() -> int:
    row = get_db().execute("SELECT COUNT(*) AS total FROM class_user_status_history").fetchone()
    return int((row or {}).get("total") or 0)


def list_contact_tag_signup_rows():
    return get_db().execute(
        """
        SELECT
            ct.external_userid,
            COALESCE(ct.userid, '') AS tag_userid,
            COALESCE(ct.tag_id, '') AS tag_id,
            COALESCE(ct.tag_name, '') AS tag_name,
            ct.created_at AS tag_created_at,
            COALESCE(c.customer_name, '') AS customer_name,
            COALESCE(c.owner_userid, '') AS owner_userid,
            COALESCE(p.mobile, '') AS mobile
        FROM contact_tags ct
        INNER JOIN signup_tag_rules signup_rules
          ON signup_rules.tag_id = ct.tag_id
         AND signup_rules.active = ?
        LEFT JOIN contacts c
          ON c.external_userid = ct.external_userid
        LEFT JOIN external_contact_bindings bindings
          ON bindings.external_userid = ct.external_userid
        LEFT JOIN people p
          ON p.id = bindings.person_id
        ORDER BY ct.created_at DESC, ct.id DESC
        """,
        (_db_bool(True),),
    ).fetchall()
