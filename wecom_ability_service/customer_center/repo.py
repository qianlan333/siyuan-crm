from __future__ import annotations

from typing import Any

from ..db import cast_text, get_db, get_db_backend, is_postgres

_OWNER_ROLE_MAP_QUERY_BATCH_SIZE = 5000


def _fetchall_dict(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in get_db().execute(sql, params).fetchall()]


def list_scope_external_userids() -> list[str]:
    rows = _fetchall_dict(
        """
        SELECT external_userid
        FROM (
            SELECT external_userid FROM contacts
            UNION
            SELECT external_userid FROM external_contact_bindings
            UNION
            SELECT external_userid FROM wecom_external_contact_identity_map
            UNION
            SELECT external_userid FROM wecom_external_contact_follow_users
            UNION
            SELECT external_userid FROM contact_tags
            UNION
            SELECT external_userid FROM class_user_status_current
            UNION
            SELECT external_userid FROM archived_messages
        ) scope
        WHERE external_userid IS NOT NULL AND external_userid <> ''
        ORDER BY external_userid ASC
        """
    )
    return [str(row.get("external_userid") or "").strip() for row in rows if str(row.get("external_userid") or "").strip()]


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_bool_filter(value: Any) -> bool | None:
    normalized = _normalized_text(value).lower()
    if normalized in {"", "all"}:
        return None
    if normalized in {"1", "true", "yes"}:
        return True
    if normalized in {"0", "false", "no"}:
        return False
    raise ValueError("is_bound must be one of true/false/1/0")


def _customer_list_scope_sql() -> str:
    class_status_updated_at = cast_text("class_status.updated_at")
    contact_updated_at = cast_text("contact.updated_at")
    binding_updated_at = cast_text("binding.updated_at")

    return f"""
    WITH scope AS (
        SELECT external_userid FROM contacts
        UNION
        SELECT external_userid FROM external_contact_bindings
        UNION
        SELECT external_userid FROM wecom_external_contact_identity_map
        UNION
        SELECT external_userid FROM wecom_external_contact_follow_users
        UNION
        SELECT external_userid FROM contact_tags
        UNION
        SELECT external_userid FROM class_user_status_current
        UNION
        SELECT external_userid FROM archived_messages
    ),
    latest_messages AS (
        SELECT external_userid, MAX(send_time) AS last_message_at
        FROM archived_messages
        WHERE external_userid IS NOT NULL AND external_userid <> ''
        GROUP BY external_userid
    ),
    decorated AS (
        SELECT
            scope.external_userid,
            COALESCE(
                NULLIF(class_status.owner_userid_snapshot, ''),
                NULLIF(contact.owner_userid, ''),
                NULLIF(binding.last_owner_userid, ''),
                NULLIF(binding.first_owner_userid, ''),
                NULLIF((
                    SELECT identity.follow_user_userid
                    FROM wecom_external_contact_identity_map identity
                    WHERE identity.external_userid = scope.external_userid
                      AND identity.follow_user_userid IS NOT NULL
                      AND identity.follow_user_userid <> ''
                    ORDER BY identity.updated_at DESC, identity.id DESC
                    LIMIT 1
                ), ''),
                NULLIF((
                    SELECT follow_user.user_id
                    FROM wecom_external_contact_follow_users follow_user
                    WHERE follow_user.external_userid = scope.external_userid
                      AND follow_user.user_id IS NOT NULL
                      AND follow_user.user_id <> ''
                    ORDER BY follow_user.is_primary DESC, follow_user.updated_at DESC, follow_user.id DESC
                    LIMIT 1
                ), ''),
                ''
            ) AS owner_userid,
            COALESCE(
                NULLIF(class_status.customer_name_snapshot, ''),
                NULLIF(contact.customer_name, ''),
                NULLIF((
                    SELECT identity.name
                    FROM wecom_external_contact_identity_map identity
                    WHERE identity.external_userid = scope.external_userid
                      AND identity.name IS NOT NULL
                      AND identity.name <> ''
                    ORDER BY identity.updated_at DESC, identity.id DESC
                    LIMIT 1
                ), ''),
                scope.external_userid
            ) AS customer_name,
            COALESCE(NULLIF(people.mobile, ''), NULLIF(class_status.mobile_snapshot, ''), '') AS mobile,
            COALESCE(contact.remark, '') AS remark,
            COALESCE(contact.description, '') AS description,
            COALESCE(class_status.signup_status, '') AS signup_status,
            COALESCE(class_status.signup_label_name, '') AS signup_label_name,
            CASE WHEN binding.external_userid IS NULL THEN 0 ELSE 1 END AS is_bound,
            COALESCE(
                NULLIF({class_status_updated_at}, ''),
                NULLIF({contact_updated_at}, ''),
                NULLIF({binding_updated_at}, ''),
                NULLIF(latest_messages.last_message_at, ''),
                ''
            ) AS sort_updated_at
        FROM scope
        LEFT JOIN contacts contact
          ON contact.external_userid = scope.external_userid
        LEFT JOIN external_contact_bindings binding
          ON binding.external_userid = scope.external_userid
        LEFT JOIN people people
          ON people.id = binding.person_id
        LEFT JOIN class_user_status_current class_status
          ON class_status.external_userid = scope.external_userid
        LEFT JOIN latest_messages
          ON latest_messages.external_userid = scope.external_userid
        WHERE scope.external_userid IS NOT NULL
          AND scope.external_userid <> ''
    )
    """


def _customer_list_where(filters: dict[str, Any] | None) -> tuple[list[str], list[Any]]:
    normalized = {key: _normalized_text(value) for key, value in (filters or {}).items()}
    where: list[str] = []
    params: list[Any] = []

    owner_userid = normalized.get("owner_userid", "")
    if owner_userid:
        where.append(
            """
            (
                decorated.owner_userid = ?
                OR EXISTS (
                    SELECT 1
                    FROM owner_role_map owner_role
                    WHERE owner_role.userid = decorated.owner_userid
                      AND owner_role.display_name = ?
                )
            )
            """
        )
        params.extend([owner_userid, owner_userid])

    tag = normalized.get("tag", "")
    if tag:
        where.append(
            """
            (
                decorated.signup_label_name = ?
                OR EXISTS (
                    SELECT 1
                    FROM contact_tags tag
                    WHERE tag.external_userid = decorated.external_userid
                      AND (tag.tag_id = ? OR tag.tag_name = ?)
                )
            )
            """
        )
        params.extend([tag, tag, tag])

    status = normalized.get("status", "")
    if status:
        where.append("decorated.signup_status = ?")
        params.append(status)

    is_bound = _normalize_bool_filter(normalized.get("is_bound", ""))
    if is_bound is not None:
        where.append("decorated.is_bound = ?")
        params.append(1 if is_bound else 0)

    mobile = normalized.get("mobile", "")
    if mobile:
        where.append("decorated.mobile LIKE ?")
        params.append(f"%{mobile}%")

    keyword = normalized.get("keyword", "").lower()
    if keyword:
        like_keyword = f"%{keyword}%"
        where.append(
            """
            (
                LOWER(decorated.external_userid) LIKE ?
                OR LOWER(decorated.customer_name) LIKE ?
                OR LOWER(decorated.owner_userid) LIKE ?
                OR EXISTS (
                    SELECT 1
                    FROM owner_role_map owner_role
                    WHERE owner_role.userid = decorated.owner_userid
                      AND LOWER(owner_role.display_name) LIKE ?
                )
                OR LOWER(decorated.remark) LIKE ?
                OR LOWER(decorated.description) LIKE ?
                OR LOWER(decorated.mobile) LIKE ?
                OR LOWER(decorated.signup_status) LIKE ?
                OR LOWER(decorated.signup_label_name) LIKE ?
                OR EXISTS (
                    SELECT 1
                    FROM contact_tags tag
                    WHERE tag.external_userid = decorated.external_userid
                      AND (LOWER(tag.tag_id) LIKE ? OR LOWER(tag.tag_name) LIKE ?)
                )
            )
            """
        )
        params.extend([like_keyword] * 11)

    return where, params


def list_customer_scope_external_userids(
    filters: dict[str, Any] | None = None,
    *,
    limit: int,
    offset: int,
) -> list[str]:
    where, params = _customer_list_where(filters)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    rows = _fetchall_dict(
        f"""
        {_customer_list_scope_sql()}
        SELECT decorated.external_userid
        FROM decorated
        {where_sql}
        ORDER BY decorated.sort_updated_at DESC, decorated.external_userid DESC
        LIMIT ? OFFSET ?
        """,
        tuple(params + [max(1, int(limit)), max(0, int(offset))]),
    )
    return [_normalized_text(row.get("external_userid")) for row in rows if _normalized_text(row.get("external_userid"))]


def count_customer_scope_external_userids(filters: dict[str, Any] | None = None) -> int:
    where, params = _customer_list_where(filters)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    row = get_db().execute(
        f"""
        {_customer_list_scope_sql()}
        SELECT COUNT(*) AS total
        FROM decorated
        {where_sql}
        """,
        tuple(params),
    ).fetchone()
    return int(row["total"] or 0) if row else 0


def fetch_contact_map(external_userids: list[str]) -> dict[str, dict[str, Any]]:
    if not external_userids:
        return {}
    placeholders = ",".join(["?"] * len(external_userids))
    rows = _fetchall_dict(
        f"""
        SELECT external_userid, customer_name, owner_userid, remark, description, updated_at
        FROM contacts
        WHERE external_userid IN ({placeholders})
        """,
        tuple(external_userids),
    )
    return {str(row.get("external_userid") or "").strip(): row for row in rows}


def fetch_binding_map(external_userids: list[str]) -> dict[str, dict[str, Any]]:
    if not external_userids:
        return {}
    placeholders = ",".join(["?"] * len(external_userids))
    rows = _fetchall_dict(
        f"""
        SELECT
            b.external_userid,
            b.person_id,
            b.first_bound_by_userid,
            b.first_owner_userid,
            b.last_owner_userid,
            b.created_at,
            b.updated_at,
            p.mobile,
            p.third_party_user_id
        FROM external_contact_bindings b
        LEFT JOIN people p ON p.id = b.person_id
        WHERE b.external_userid IN ({placeholders})
        """,
        tuple(external_userids),
    )
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        external_userid = str(row.get("external_userid") or "").strip()
        if external_userid:
            payload = dict(row)
            payload["is_bound"] = True
            result[external_userid] = payload
    return result


def fetch_identity_map(external_userids: list[str]) -> dict[str, dict[str, Any]]:
    if not external_userids:
        return {}
    placeholders = ",".join(["?"] * len(external_userids))
    rows = _fetchall_dict(
        f"""
        SELECT
            external_userid,
            unionid,
            openid,
            follow_user_userid,
            name,
            status,
            created_at,
            updated_at
        FROM wecom_external_contact_identity_map
        WHERE external_userid IN ({placeholders})
        ORDER BY updated_at DESC, id DESC
        """,
        tuple(external_userids),
    )
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        external_userid = str(row.get("external_userid") or "").strip()
        if external_userid and external_userid not in result:
            result[external_userid] = row
    return result


def fetch_follow_users_map(external_userids: list[str]) -> dict[str, list[dict[str, Any]]]:
    if not external_userids:
        return {}
    placeholders = ",".join(["?"] * len(external_userids))
    rows = _fetchall_dict(
        f"""
        SELECT
            external_userid,
            user_id,
            relation_status,
            is_primary,
            remark,
            description,
            add_way,
            oper_userid,
            createtime,
            updated_at
        FROM wecom_external_contact_follow_users
        WHERE external_userid IN ({placeholders})
        ORDER BY external_userid ASC, is_primary DESC, updated_at DESC, id DESC
        """,
        tuple(external_userids),
    )
    result: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        external_userid = str(row.get("external_userid") or "").strip()
        if not external_userid:
            continue
        result.setdefault(external_userid, []).append(
            {
                "userid": str(row.get("user_id") or "").strip(),
                "relation_status": str(row.get("relation_status") or "").strip(),
                "is_primary": bool(row.get("is_primary")),
                "remark": str(row.get("remark") or "").strip(),
                "description": str(row.get("description") or "").strip(),
                "add_way": row.get("add_way"),
                "oper_userid": str(row.get("oper_userid") or "").strip(),
                "createtime": row.get("createtime"),
                "updated_at": str(row.get("updated_at") or "").strip(),
            }
        )
    return result


def fetch_tag_map(external_userids: list[str]) -> dict[str, list[dict[str, Any]]]:
    if not external_userids:
        return {}
    placeholders = ",".join(["?"] * len(external_userids))
    rows = _fetchall_dict(
        f"""
        SELECT external_userid, userid, tag_id, COALESCE(tag_name, '') AS tag_name, created_at
        FROM contact_tags
        WHERE external_userid IN ({placeholders})
        ORDER BY external_userid ASC, userid ASC, tag_name ASC, tag_id ASC
        """,
        tuple(external_userids),
    )
    result: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        external_userid = str(row.get("external_userid") or "").strip()
        if external_userid:
            result.setdefault(external_userid, []).append(row)
    return result


def fetch_class_status_map(external_userids: list[str]) -> dict[str, dict[str, Any]]:
    if not external_userids:
        return {}
    placeholders = ",".join(["?"] * len(external_userids))
    rows = _fetchall_dict(
        f"""
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
        WHERE external_userid IN ({placeholders})
        """,
        tuple(external_userids),
    )
    return {str(row.get("external_userid") or "").strip(): row for row in rows}


def fetch_last_message_map(external_userids: list[str]) -> dict[str, str]:
    if not external_userids:
        return {}
    placeholders = ",".join(["?"] * len(external_userids))
    rows = _fetchall_dict(
        f"""
        SELECT external_userid, MAX(send_time) AS last_message_at
        FROM archived_messages
        WHERE external_userid IN ({placeholders})
        GROUP BY external_userid
        """,
        tuple(external_userids),
    )
    return {
        str(row.get("external_userid") or "").strip(): str(row.get("last_message_at") or "").strip()
        for row in rows
        if str(row.get("external_userid") or "").strip()
    }


def list_customer_agent_output_rows(external_userid: str, *, limit: int = 10) -> list[dict[str, Any]]:
    normalized_external_userid = str(external_userid or "").strip()
    if not normalized_external_userid:
        return []
    return _fetchall_dict(
        """
        SELECT
            output.id,
            output.output_id,
            output.run_id,
            output.request_id,
            output.userid,
            output.external_contact_id,
            output.agent_code,
            output.output_type,
            output.raw_output_text,
            output.normalized_output_json,
            output.rendered_output_text,
            output.target_agent_code,
            output.target_pool,
            output.confidence,
            output.reason,
            output.need_human_review,
            output.applied_status,
            output.error_code,
            output.error_message,
            output.created_at,
            COALESCE(run.input_snapshot_json, '{}') AS input_snapshot_json,
            COALESCE(run.variables_snapshot_json, '{}') AS variables_snapshot_json,
            COALESCE(run.status, '') AS run_status,
            COALESCE(run.created_at::text, \'\') AS run_created_at
        FROM automation_agent_output output
        LEFT JOIN automation_agent_run run ON run.run_id = output.run_id
        WHERE output.external_contact_id = ?
          AND output.output_type IN ('next_action_suggestion', 'agent_reply_draft', 'agent_reply_final')
          AND COALESCE(output.error_code, '') = ''
          AND COALESCE(output.error_message, '') = ''
        ORDER BY output.created_at DESC, output.id DESC
        LIMIT ?
        """,
        (normalized_external_userid, max(1, min(int(limit or 10), 50))),
    )


def fetch_owner_role_map(userids: list[str]) -> dict[str, dict[str, Any]]:
    normalized: list[str] = []
    seen: set[str] = set()
    for userid in userids:
        normalized_userid = str(userid or "").strip()
        if not normalized_userid or normalized_userid in seen:
            continue
        seen.add(normalized_userid)
        normalized.append(normalized_userid)
    if not normalized:
        return {}
    rows: list[dict[str, Any]] = []
    for start in range(0, len(normalized), _OWNER_ROLE_MAP_QUERY_BATCH_SIZE):
        batch = normalized[start : start + _OWNER_ROLE_MAP_QUERY_BATCH_SIZE]
        placeholders = ",".join(["?"] * len(batch))
        rows.extend(
            _fetchall_dict(
                f"""
                SELECT userid, display_name, role, active, updated_at
                FROM owner_role_map
                WHERE userid IN ({placeholders})
                """,
                tuple(batch),
            )
        )
    return {str(row.get("userid") or "").strip(): row for row in rows}


def fetch_customer_marketing_state_current(external_userid: str) -> dict[str, Any] | None:
    normalized_external_userid = str(external_userid or "").strip()
    if not normalized_external_userid:
        return None
    row = get_db().execute(
        """
        SELECT
            external_userid,
            main_stage,
            sub_stage,
            eligible_for_conversion,
            last_activation_at,
            last_conversion_marked_at,
            state_payload_json,
            updated_at
        FROM customer_marketing_state_current
        WHERE external_userid = ?
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (normalized_external_userid,),
    ).fetchone()
    return dict(row) if row else None


def fetch_customer_marketing_state_current_map(external_userids: list[str]) -> dict[str, dict[str, Any]]:
    normalized = [str(item or "").strip() for item in external_userids if str(item or "").strip()]
    if not normalized:
        return {}
    placeholders = ",".join(["?"] * len(normalized))
    rows = _fetchall_dict(
        f"""
        SELECT
            external_userid,
            main_stage,
            sub_stage,
            eligible_for_conversion,
            last_activation_at,
            last_conversion_marked_at,
            state_payload_json,
            updated_at,
            id
        FROM customer_marketing_state_current
        WHERE external_userid IN ({placeholders})
        ORDER BY external_userid ASC, updated_at DESC, id DESC
        """,
        tuple(normalized),
    )
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        external_userid = str(row.get("external_userid") or "").strip()
        if external_userid and external_userid not in result:
            result[external_userid] = row
    return result


def fetch_customer_value_segment_current(external_userid: str) -> dict[str, Any] | None:
    normalized_external_userid = str(external_userid or "").strip()
    if not normalized_external_userid:
        return None
    row = get_db().execute(
        """
        SELECT
            external_userid,
            segment,
            score,
            updated_at
        FROM customer_value_segment_current
        WHERE external_userid = ?
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (normalized_external_userid,),
    ).fetchone()
    return dict(row) if row else None


def fetch_customer_value_segment_current_map(external_userids: list[str]) -> dict[str, dict[str, Any]]:
    normalized = [str(item or "").strip() for item in external_userids if str(item or "").strip()]
    if not normalized:
        return {}
    placeholders = ",".join(["?"] * len(normalized))
    rows = _fetchall_dict(
        f"""
        SELECT
            external_userid,
            segment,
            score,
            updated_at,
            id
        FROM customer_value_segment_current
        WHERE external_userid IN ({placeholders})
        ORDER BY external_userid ASC, updated_at DESC, id DESC
        """,
        tuple(normalized),
    )
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        external_userid = str(row.get("external_userid") or "").strip()
        if external_userid and external_userid not in result:
            result[external_userid] = row
    return result


def fetch_customer_last_dispatch_at(external_userid: str) -> str:
    normalized_external_userid = str(external_userid or "").strip()
    if not normalized_external_userid:
        return ""
    # SQLite stores dispatched_at as TEXT (may be ''); Postgres uses TIMESTAMPTZ
    # (where '' would be an invalid literal), so the empty-string guard is
    # only emitted in the SQLite branch.
    extra_filter = "" if is_postgres() else " AND dispatched_at <> ''"
    row = get_db().execute(
        f"""
        SELECT COALESCE({cast_text("MAX(dispatched_at)")}, '') AS last_dispatch_at
        FROM conversion_dispatch_log
        WHERE external_userid = ?
          AND dispatched_at IS NOT NULL{extra_filter}
        """,
        (normalized_external_userid,),
    ).fetchone()
    return str((row or {}).get("last_dispatch_at") or "").strip()


def fetch_customer_last_dispatch_at_map(external_userids: list[str]) -> dict[str, str]:
    """Batch variant of ``fetch_customer_last_dispatch_at`` to remove an N+1.

    Returns a mapping ``external_userid -> last_dispatch_at`` (empty string if
    no dispatch row exists for that customer).
    """
    normalized = [str(item or "").strip() for item in external_userids if str(item or "").strip()]
    if not normalized:
        return {}
    placeholders = ",".join(["?"] * len(normalized))
    extra_filter = "" if is_postgres() else " AND dispatched_at <> ''"
    rows = get_db().execute(
        f"""
        SELECT external_userid,
               COALESCE({cast_text("MAX(dispatched_at)")}, '') AS last_dispatch_at
        FROM conversion_dispatch_log
        WHERE external_userid IN ({placeholders})
          AND dispatched_at IS NOT NULL{extra_filter}
        GROUP BY external_userid
        """,
        tuple(normalized),
    ).fetchall()
    result: dict[str, str] = {}
    for row in rows:
        external_userid = str(row.get("external_userid") or "").strip()
        if external_userid:
            result[external_userid] = str(row.get("last_dispatch_at") or "").strip()
    return result
