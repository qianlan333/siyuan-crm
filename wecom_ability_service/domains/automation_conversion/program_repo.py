from __future__ import annotations

import json
from typing import Any

from ...db import get_db


DEFAULT_AUTOMATION_PROGRAM_CODE = "signup_conversion_v1"
DEFAULT_AUTOMATION_PROGRAM_NAME = "默认自动化转化方案"


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _json_loads(value: Any, *, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    text = _normalized_text(value)
    if not text:
        return default
    try:
        return json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _fetchone_dict(sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    row = get_db().execute(sql, params).fetchone()
    return dict(row) if row else None


def _fetchall_dicts(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    rows = get_db().execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def serialize_program_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "id": int(row.get("id") or 0),
        "config_json": _json_loads(row.get("config_json"), default={}),
    }


def serialize_config_block_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "id": int(row.get("id") or 0),
        "program_id": int(row.get("program_id") or 0),
        "payload_json": _json_loads(row.get("payload_json"), default={}),
        "version": int(row.get("version") or 1),
        "copied_from_program_id": int(row.get("copied_from_program_id") or 0) or None,
        "copied_from_block_id": int(row.get("copied_from_block_id") or 0) or None,
    }


def get_program_row(program_id: int) -> dict[str, Any] | None:
    row = _fetchone_dict(
        """
        SELECT *
        FROM automation_program
        WHERE id = ?
        LIMIT 1
        """,
        (int(program_id),),
    )
    return serialize_program_row(row) if row else None


def get_program_row_by_code(program_code: str) -> dict[str, Any] | None:
    row = _fetchone_dict(
        """
        SELECT *
        FROM automation_program
        WHERE program_code = ?
        LIMIT 1
        """,
        (_normalized_text(program_code),),
    )
    return serialize_program_row(row) if row else None


def list_program_rows(*, include_archived: bool = False) -> list[dict[str, Any]]:
    sql = """
        SELECT *
        FROM automation_program
        WHERE 1 = 1
    """
    params: list[Any] = []
    if not include_archived:
        sql += " AND status <> ?"
        params.append("archived")
    sql += """
        ORDER BY
            CASE status
                WHEN 'active' THEN 0
                WHEN 'draft' THEN 1
                WHEN 'paused' THEN 2
                ELSE 3
            END,
            updated_at DESC,
            id DESC
    """
    return [serialize_program_row(row) for row in _fetchall_dicts(sql, tuple(params))]


def get_default_program_row() -> dict[str, Any] | None:
    return get_program_row_by_code(DEFAULT_AUTOMATION_PROGRAM_CODE)


def get_config_block_row(program_id: int, block_key: str) -> dict[str, Any] | None:
    row = _fetchone_dict(
        """
        SELECT *
        FROM automation_program_config_block
        WHERE program_id = ?
          AND block_key = ?
        LIMIT 1
        """,
        (int(program_id), _normalized_text(block_key)),
    )
    return serialize_config_block_row(row) if row else None


def list_config_block_rows(program_id: int) -> list[dict[str, Any]]:
    return [
        serialize_config_block_row(row)
        for row in _fetchall_dicts(
            """
            SELECT *
            FROM automation_program_config_block
            WHERE program_id = ?
            ORDER BY block_key ASC
            """,
            (int(program_id),),
        )
    ]


def upsert_config_block_row(
    program_id: int,
    block_key: str,
    payload_json: dict[str, Any],
    *,
    status: str = "draft",
    copied_from_program_id: int | None = None,
    copied_from_block_id: int | None = None,
) -> dict[str, Any]:
    existing = get_config_block_row(int(program_id), block_key)
    payload_text = json.dumps(payload_json or {}, ensure_ascii=False)
    if existing:
        row = get_db().execute(
            """
            UPDATE automation_program_config_block
            SET payload_json = CAST(? AS jsonb),
                status = ?,
                version = version + 1,
                copied_from_program_id = COALESCE(?, copied_from_program_id),
                copied_from_block_id = COALESCE(?, copied_from_block_id),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            RETURNING *
            """,
            (
                payload_text,
                _normalized_text(status) or "draft",
                int(copied_from_program_id or 0) or None,
                int(copied_from_block_id or 0) or None,
                int(existing["id"]),
            ),
        ).fetchone()
    else:
        row = get_db().execute(
            """
            INSERT INTO automation_program_config_block (
                program_id,
                block_key,
                payload_json,
                status,
                version,
                copied_from_program_id,
                copied_from_block_id,
                created_at,
                updated_at
            )
            VALUES (?, ?, CAST(? AS jsonb), ?, 1, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            RETURNING *
            """,
            (
                int(program_id),
                _normalized_text(block_key),
                payload_text,
                _normalized_text(status) or "draft",
                int(copied_from_program_id or 0) or None,
                int(copied_from_block_id or 0) or None,
            ),
        ).fetchone()
    return serialize_config_block_row(dict(row) if row else {})


def copy_config_blocks(source_program_id: int, target_program_id: int) -> list[dict[str, Any]]:
    copied: list[dict[str, Any]] = []
    for block in list_config_block_rows(int(source_program_id)):
        payload = dict(block.get("payload_json") or {})
        if str(block.get("block_key") or "") == "entry_channel":
            qrcode = dict(payload.get("qrcode") or {})
            for key in ("qr_ticket", "qr_url", "scene_value", "config_id", "wecom_response"):
                qrcode.pop(key, None)
            payload["qrcode"] = qrcode
            payload.pop("customer_acquisition_link_ids", None)
        copied.append(
            upsert_config_block_row(
                int(target_program_id),
                str(block.get("block_key") or ""),
                payload,
                status=str(block.get("status") or "draft"),
                copied_from_program_id=int(source_program_id),
                copied_from_block_id=int(block.get("id") or 0),
            )
        )
    return copied


def insert_program_row(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_program (
            program_code,
            program_name,
            description,
            status,
            config_json,
            created_by,
            updated_by,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            _normalized_text(payload.get("program_code")),
            _normalized_text(payload.get("program_name")),
            _normalized_text(payload.get("description")),
            _normalized_text(payload.get("status")) or "draft",
            json.dumps(payload.get("config_json") or {}, ensure_ascii=False),
            _normalized_text(payload.get("created_by")),
            _normalized_text(payload.get("updated_by")),
        ),
    ).fetchone()
    return serialize_program_row(dict(row) if row else {})


def update_program_row(program_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE automation_program
        SET program_code = ?,
            program_name = ?,
            description = ?,
            status = ?,
            config_json = ?,
            updated_by = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        RETURNING *
        """,
        (
            _normalized_text(payload.get("program_code")),
            _normalized_text(payload.get("program_name")),
            _normalized_text(payload.get("description")),
            _normalized_text(payload.get("status")) or "draft",
            json.dumps(payload.get("config_json") or {}, ensure_ascii=False),
            _normalized_text(payload.get("updated_by")),
            int(program_id),
        ),
    ).fetchone()
    return serialize_program_row(dict(row) if row else {})


def update_program_basic_info_row(program_id: int, *, program_name: str, description: str, operator_id: str) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE automation_program
        SET program_name = ?,
            description = ?,
            updated_by = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        RETURNING *
        """,
        (
            _normalized_text(program_name),
            _normalized_text(description),
            _normalized_text(operator_id),
            int(program_id),
        ),
    ).fetchone()
    return serialize_program_row(dict(row) if row else {})


def update_program_status_row(program_id: int, *, status: str, operator_id: str) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE automation_program
        SET status = ?,
            updated_by = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        RETURNING *
        """,
        (_normalized_text(status), _normalized_text(operator_id), int(program_id)),
    ).fetchone()
    return serialize_program_row(dict(row) if row else {})


def get_program_summary(program_id: int) -> dict[str, Any]:
    workflow_count_row = _fetchone_dict(
        """
        SELECT COUNT(*) AS total
        FROM automation_workflow
        WHERE program_id = ?
          AND status <> 'archived'
        """,
        (int(program_id),),
    ) or {}
    execution_row = _fetchone_dict(
        """
        SELECT MAX(
            CASE
                WHEN COALESCE(CAST(scheduled_for AS TEXT), '') <> '' THEN CAST(scheduled_for AS TEXT)
                WHEN updated_at IS NOT NULL THEN CAST(updated_at AS TEXT)
                ELSE COALESCE(CAST(created_at AS TEXT), '')
            END
        ) AS latest_execution_at
        FROM automation_workflow_execution
        WHERE program_id = ?
        """,
        (int(program_id),),
    ) or {}
    channel_count_row = _fetchone_dict(
        """
        SELECT COUNT(*) AS total
        FROM automation_channel
        WHERE program_id = ?
          AND status <> 'archived'
        """,
        (int(program_id),),
    ) or {}
    return {
        "workflow_count": int(workflow_count_row.get("total") or 0),
        "channel_count": int(channel_count_row.get("total") or 0),
        "latest_execution_at": _normalized_text(execution_row.get("latest_execution_at")),
    }
