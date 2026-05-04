from __future__ import annotations

import json
from typing import Any

from ...db import get_db, get_db_backend


def _db_bool(value: bool) -> bool | int:
    return value if get_db_backend() == "postgres" else (1 if value else 0)


def _fetch_inserted_id(cursor) -> int:
    if get_db_backend() == "postgres":
        row = cursor.fetchone() or {}
        return int((row or {}).get("id") or 0)
    return int(cursor.lastrowid)


def _json_loads(value: Any, *, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if value in (None, ""):
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def list_class_term_tag_mappings(active_only: bool = False) -> list[dict[str, Any]]:
    sql = """
        SELECT
            id,
            strategy_id,
            group_id,
            tag_id,
            tag_group_name,
            tag_name,
            class_term_no,
            class_term_label,
            is_active,
            created_at,
            updated_at
        FROM class_term_tag_mapping
    """
    params: list[Any] = []
    if active_only:
        sql += " WHERE is_active = ?"
        params.append(_db_bool(True))
    sql += " ORDER BY is_active DESC, class_term_no ASC, id ASC"
    rows = get_db().execute(sql, tuple(params)).fetchall()
    return [dict(row) for row in rows]


def get_class_term_tag_mapping(mapping_id: int) -> dict[str, Any] | None:
    row = get_db().execute(
        """
        SELECT
            id,
            strategy_id,
            group_id,
            tag_id,
            tag_group_name,
            tag_name,
            class_term_no,
            class_term_label,
            is_active,
            created_at,
            updated_at
        FROM class_term_tag_mapping
        WHERE id = ?
        """,
        (int(mapping_id),),
    ).fetchone()
    return dict(row) if row else None


def upsert_class_term_tag_mapping(
    *,
    mapping_id: int | None,
    strategy_id: str,
    group_id: str,
    tag_id: str,
    tag_group_name: str,
    tag_name: str,
    class_term_no: int,
    class_term_label: str,
    is_active: bool,
) -> int:
    db = get_db()
    if mapping_id:
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
                strategy_id,
                group_id,
                tag_id,
                tag_group_name,
                tag_name,
                int(class_term_no),
                class_term_label,
                _db_bool(is_active),
                int(mapping_id),
            ),
        )
        db.commit()
        return int(mapping_id)

    if tag_id:
        existing = db.execute(
            "SELECT id FROM class_term_tag_mapping WHERE tag_id = ?",
            (tag_id,),
        ).fetchone()
        if existing:
            mapping_id = int(existing["id"])
            return upsert_class_term_tag_mapping(
                mapping_id=mapping_id,
                strategy_id=strategy_id,
                group_id=group_id,
                tag_id=tag_id,
                tag_group_name=tag_group_name,
                tag_name=tag_name,
                class_term_no=class_term_no,
                class_term_label=class_term_label,
                is_active=is_active,
            )

    existing = db.execute(
        """
        SELECT id
        FROM class_term_tag_mapping
        WHERE tag_group_name = ? AND tag_name = ?
        LIMIT 1
        """,
        (tag_group_name, tag_name),
    ).fetchone()
    if existing:
        mapping_id = int(existing["id"])
        return upsert_class_term_tag_mapping(
            mapping_id=mapping_id,
            strategy_id=strategy_id,
            group_id=group_id,
            tag_id=tag_id,
            tag_group_name=tag_group_name,
            tag_name=tag_name,
            class_term_no=class_term_no,
            class_term_label=class_term_label,
            is_active=is_active,
        )

    inserted = db.execute(
        """
        INSERT INTO class_term_tag_mapping (
            strategy_id,
            group_id,
            tag_id,
            tag_group_name,
            tag_name,
            class_term_no,
            class_term_label,
            is_active,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """ + (" RETURNING id" if get_db_backend() == "postgres" else "") + """
        """,
        (
            strategy_id,
            group_id,
            tag_id,
            tag_group_name,
            tag_name,
            int(class_term_no),
            class_term_label,
            _db_bool(is_active),
        ),
    )
    db.commit()
    return _fetch_inserted_id(inserted)


def list_app_setting_rows() -> list[dict[str, Any]]:
    rows = get_db().execute(
        """
        SELECT key, value, updated_at
        FROM app_settings
        ORDER BY key ASC
        """
    ).fetchall()
    return [dict(row) for row in rows]


def get_app_setting_row(key: str) -> dict[str, Any] | None:
    row = get_db().execute(
        """
        SELECT key, value, updated_at
        FROM app_settings
        WHERE key = ?
        """,
        (str(key or "").strip(),),
    ).fetchone()
    return dict(row) if row else None


def upsert_app_setting(*, key: str, value: str) -> None:
    get_db().execute(
        """
        INSERT INTO app_settings (key, value, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = CURRENT_TIMESTAMP
        """,
        (str(key or "").strip(), str(value)),
    )
    get_db().commit()


def list_mcp_tool_settings() -> list[dict[str, Any]]:
    rows = get_db().execute(
        """
        SELECT
            tool_name,
            tool_group,
            display_name,
            description_override,
            enabled,
            visible_in_console,
            show_sample_args,
            show_sample_output,
            sort_order,
            updated_at
        FROM mcp_tool_settings
        ORDER BY sort_order ASC, tool_name ASC
        """
    ).fetchall()
    return [dict(row) for row in rows]


def get_mcp_tool_setting(tool_name: str) -> dict[str, Any] | None:
    row = get_db().execute(
        """
        SELECT
            tool_name,
            tool_group,
            display_name,
            description_override,
            enabled,
            visible_in_console,
            show_sample_args,
            show_sample_output,
            sort_order,
            updated_at
        FROM mcp_tool_settings
        WHERE tool_name = ?
        """,
        (str(tool_name or "").strip(),),
    ).fetchone()
    return dict(row) if row else None


def upsert_mcp_tool_setting(
    *,
    tool_name: str,
    tool_group: str,
    display_name: str,
    description_override: str,
    enabled: bool,
    visible_in_console: bool,
    show_sample_args: bool,
    show_sample_output: bool,
    sort_order: int,
) -> None:
    get_db().execute(
        """
        INSERT INTO mcp_tool_settings (
            tool_name,
            tool_group,
            display_name,
            description_override,
            enabled,
            visible_in_console,
            show_sample_args,
            show_sample_output,
            sort_order,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(tool_name) DO UPDATE SET
            tool_group = excluded.tool_group,
            display_name = excluded.display_name,
            description_override = excluded.description_override,
            enabled = excluded.enabled,
            visible_in_console = excluded.visible_in_console,
            show_sample_args = excluded.show_sample_args,
            show_sample_output = excluded.show_sample_output,
            sort_order = excluded.sort_order,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            str(tool_name or "").strip(),
            str(tool_group or "").strip(),
            str(display_name or "").strip(),
            str(description_override or "").strip(),
            _db_bool(enabled),
            _db_bool(visible_in_console),
            _db_bool(show_sample_args),
            _db_bool(show_sample_output),
            int(sort_order),
        ),
    )
    get_db().commit()


def insert_admin_operation_log(
    *,
    operator: str,
    action_type: str,
    target_type: str,
    target_id: str,
    before_json: dict[str, Any],
    after_json: dict[str, Any],
) -> int:
    cursor = get_db().execute(
        """
        INSERT INTO admin_operation_logs (
            operator,
            action_type,
            target_type,
            target_id,
            before_json,
            after_json,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """ + (" RETURNING id" if get_db_backend() == "postgres" else "") + """
        """,
        (
            str(operator or "").strip(),
            str(action_type or "").strip(),
            str(target_type or "").strip(),
            str(target_id or "").strip(),
            json.dumps(before_json or {}, ensure_ascii=False, sort_keys=True),
            json.dumps(after_json or {}, ensure_ascii=False, sort_keys=True),
        ),
    )
    get_db().commit()
    return _fetch_inserted_id(cursor)


def list_admin_operation_logs(*, target_type: str = "", limit: int = 20) -> list[dict[str, Any]]:
    sql = """
        SELECT id, operator, action_type, target_type, target_id, before_json, after_json, created_at
        FROM admin_operation_logs
    """
    params: list[Any] = []
    if target_type:
        sql += " WHERE target_type = ?"
        params.append(str(target_type or "").strip())
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(max(1, min(int(limit), 200)))
    rows = get_db().execute(sql, tuple(params)).fetchall()
    return [dict(row) for row in rows]


def get_latest_audit_map(*, target_type: str, target_ids: list[str]) -> dict[str, dict[str, Any]]:
    normalized_target_ids = [str(item or "").strip() for item in target_ids if str(item or "").strip()]
    if not normalized_target_ids:
        return {}
    placeholders = ",".join("?" for _ in normalized_target_ids)
    rows = get_db().execute(
        f"""
        SELECT id, operator, action_type, target_type, target_id, before_json, after_json, created_at
        FROM admin_operation_logs
        WHERE target_type = ? AND target_id IN ({placeholders})
        ORDER BY id DESC
        """,
        (str(target_type or "").strip(), *normalized_target_ids),
    ).fetchall()
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        target_id = str(row.get("target_id") or "").strip()
        if not target_id or target_id in result:
            continue
        result[target_id] = dict(row)
    return result


def get_automation_conversion_segment_counts() -> dict[str, int]:
    counts = {"unknown": 0, "normal": 0, "focus": 0}
    rows = get_db().execute(
        """
        SELECT main_stage, sub_stage, state_payload_json
        FROM customer_marketing_state_current
        """
    ).fetchall()
    for row in rows:
        payload = _json_loads(row.get("state_payload_json"), default={})
        if not isinstance(payload, dict):
            payload = {}
        segment = str(payload.get("followup_segment") or payload.get("current_segment") or "").strip().lower()
        if not segment:
            main_stage = str(row.get("main_stage") or "").strip().lower()
            sub_stage = str(row.get("sub_stage") or "").strip().lower()
            if main_stage == "pool" and sub_stage in {"inactive_focus", "active_focus"}:
                segment = "focus"
            elif main_stage == "pool" and sub_stage in {"inactive_normal", "active_normal"}:
                segment = "normal"
            else:
                segment = "unknown"
        if segment in counts:
            counts[segment] += 1
    return counts


def list_automation_conversion_dispatch_history(*, status: str = "", limit: int = 50) -> list[dict[str, Any]]:
    normalized_status = str(status or "").strip()
    filters: list[str] = []
    params: list[Any] = []
    if normalized_status:
        filters.append("log.dispatch_status = ?")
        params.append(normalized_status)
    where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""
    params.append(max(1, min(int(limit), 200)))
    rows = get_db().execute(
        f"""
        SELECT
            log.batch_id,
            log.external_userid,
            COALESCE(
                (
                    SELECT c.owner_userid
                    FROM contacts c
                    WHERE c.external_userid = log.external_userid
                    ORDER BY c.updated_at DESC, c.id DESC
                    LIMIT 1
                ),
                ''
            ) AS owner_userid,
            COALESCE(
                (
                    SELECT s.state_payload_json
                    FROM customer_marketing_state_current s
                    WHERE s.external_userid = log.external_userid
                    ORDER BY s.updated_at DESC, s.id DESC
                    LIMIT 1
                ),
                '{{}}'
            ) AS segment,
            COALESCE(
                (
                    SELECT s.main_stage
                    FROM customer_marketing_state_current s
                    WHERE s.external_userid = log.external_userid
                    ORDER BY s.updated_at DESC, s.id DESC
                    LIMIT 1
                ),
                ''
            ) AS main_stage,
            COALESCE(
                (
                    SELECT s.sub_stage
                    FROM customer_marketing_state_current s
                    WHERE s.external_userid = log.external_userid
                    ORDER BY s.updated_at DESC, s.id DESC
                    LIMIT 1
                ),
                ''
            ) AS sub_stage,
            log.dispatch_status,
            log.created_at,
            log.acked_at
        FROM conversion_dispatch_log log
        {where_sql}
        ORDER BY log.created_at DESC, log.id DESC
        LIMIT ?
        """,
        tuple(params),
    ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        payload = _json_loads(row.get("segment"), default={})
        if not isinstance(payload, dict):
            payload = {}
        item["segment"] = str(payload.get("followup_segment") or payload.get("current_segment") or "").strip().lower() or "unknown"
        result.append(item)
    return result
