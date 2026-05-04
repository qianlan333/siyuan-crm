from __future__ import annotations

import json
from typing import Any

from ...db import get_db

ALLOWED_SORT_COLUMNS = {
    "created_at": "created_at",
    "operator": "operator",
    "action_type": "action_type",
    "target_type": "target_type",
    "target_id": "target_id",
    "id": "id",
}


def _json_loads(value: Any, *, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    text = str(value or "").strip()
    if not text:
        return default
    try:
        return json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def list_admin_operation_logs(
    *,
    q: str,
    target_type: str,
    action_type: str,
    operator: str,
    target_id: str,
    page: int,
    page_size: int,
    sort_by: str,
    sort_dir: str,
) -> dict[str, Any]:
    where: list[str] = []
    params: list[Any] = []
    normalized_q = str(q or "").strip()
    normalized_target_type = str(target_type or "").strip()
    normalized_action_type = str(action_type or "").strip()
    normalized_operator = str(operator or "").strip()
    normalized_target_id = str(target_id or "").strip()

    if normalized_target_type:
        where.append("target_type = ?")
        params.append(normalized_target_type)
    if normalized_action_type:
        where.append("action_type = ?")
        params.append(normalized_action_type)
    if normalized_operator:
        where.append("operator = ?")
        params.append(normalized_operator)
    if normalized_target_id:
        where.append("target_id = ?")
        params.append(normalized_target_id)
    if normalized_q:
        like = f"%{normalized_q}%"
        where.append(
            "(operator LIKE ? OR action_type LIKE ? OR target_type LIKE ? OR target_id LIKE ? OR CAST(before_json AS TEXT) LIKE ? OR CAST(after_json AS TEXT) LIKE ?)"
        )
        params.extend([like, like, like, like, like, like])

    where_clause = f" WHERE {' AND '.join(where)}" if where else ""
    sort_column = ALLOWED_SORT_COLUMNS.get(str(sort_by or "").strip(), "created_at")
    direction = "ASC" if str(sort_dir or "").strip().lower() == "asc" else "DESC"

    total_row = get_db().execute(
        f"SELECT COUNT(*) AS total FROM admin_operation_logs{where_clause}",
        tuple(params),
    ).fetchone()
    total = int(total_row["total"] or 0) if total_row else 0

    rows = get_db().execute(
        f"""
        SELECT id, operator, action_type, target_type, target_id, before_json, after_json, created_at
        FROM admin_operation_logs
        {where_clause}
        ORDER BY {sort_column} {direction}, id {direction}
        LIMIT ? OFFSET ?
        """,
        (*params, int(page_size), max(0, (int(page) - 1) * int(page_size))),
    ).fetchall()
    items = []
    for row in rows:
        payload = dict(row)
        payload["before_json"] = _json_loads(payload.get("before_json"), default={})
        payload["after_json"] = _json_loads(payload.get("after_json"), default={})
        items.append(payload)
    return {
        "items": items,
        "total": total,
    }


def get_admin_operation_log(log_id: int) -> dict[str, Any] | None:
    row = get_db().execute(
        """
        SELECT id, operator, action_type, target_type, target_id, before_json, after_json, created_at
        FROM admin_operation_logs
        WHERE id = ?
        """,
        (int(log_id),),
    ).fetchone()
    if not row:
        return None
    payload = dict(row)
    payload["before_json"] = _json_loads(payload.get("before_json"), default={})
    payload["after_json"] = _json_loads(payload.get("after_json"), default={})
    return payload


def list_distinct_values(field_name: str, *, limit: int = 100) -> list[str]:
    normalized_field_name = ALLOWED_SORT_COLUMNS.get(str(field_name or "").strip())
    if normalized_field_name not in {"operator", "action_type", "target_type", "target_id"}:
        return []
    rows = get_db().execute(
        f"""
        SELECT DISTINCT {normalized_field_name} AS value
        FROM admin_operation_logs
        WHERE {normalized_field_name} IS NOT NULL AND {normalized_field_name} <> ''
        ORDER BY {normalized_field_name} ASC
        LIMIT ?
        """,
        (max(1, min(int(limit), 500)),),
    ).fetchall()
    return [str(row["value"] or "").strip() for row in rows if str(row["value"] or "").strip()]
