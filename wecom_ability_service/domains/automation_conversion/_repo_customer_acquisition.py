from __future__ import annotations

from typing import Any

from ._repo_helpers import _db_bool, _fetchall_dicts, _fetchone_dict, _json_dumps, _normalized_text
from ...db import get_db


def get_customer_acquisition_link(link_row_id: int) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT l.*, c.channel_code, c.scene_value, c.status AS channel_status
        FROM wecom_customer_acquisition_links l
        INNER JOIN automation_channel c ON c.id = l.automation_channel_id
        WHERE l.id = ?
        LIMIT 1
        """,
        (int(link_row_id),),
    )


def list_customer_acquisition_links(*, status: str = "", program_id: int | None = None) -> list[dict[str, Any]]:
    normalized_status = _normalized_text(status)
    params: list[Any] = []
    where_parts: list[str] = []
    normalized_program_id = int(program_id or 0) or None
    if normalized_program_id is not None:
        where_parts.append("l.program_id = ?")
        params.append(normalized_program_id)
    if normalized_status:
        where_parts.append("l.status = ?")
        params.append(normalized_status)
    where = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    return _fetchall_dicts(
        f"""
        SELECT l.*, c.channel_code, c.scene_value, c.status AS channel_status
        FROM wecom_customer_acquisition_links l
        INNER JOIN automation_channel c ON c.id = l.automation_channel_id
        {where}
        ORDER BY l.updated_at DESC, l.id DESC
        """,
        tuple(params),
    )


def find_customer_acquisition_link_by_channel(*, corp_id: str, customer_channel: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT l.*, c.channel_code, c.scene_value, c.status AS channel_status
        FROM wecom_customer_acquisition_links l
        INNER JOIN automation_channel c ON c.id = l.automation_channel_id
        WHERE l.corp_id = ?
          AND l.customer_channel = ?
        ORDER BY l.updated_at DESC, l.id DESC
        LIMIT 1
        """,
        (_normalized_text(corp_id), _normalized_text(customer_channel)),
    )


def find_customer_acquisition_link_by_link_id(*, corp_id: str, link_id: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT l.*, c.channel_code, c.scene_value, c.status AS channel_status
        FROM wecom_customer_acquisition_links l
        INNER JOIN automation_channel c ON c.id = l.automation_channel_id
        WHERE l.corp_id = ?
          AND l.link_id = ?
        ORDER BY l.updated_at DESC, l.id DESC
        LIMIT 1
        """,
        (_normalized_text(corp_id), _normalized_text(link_id)),
    )


def insert_customer_acquisition_link(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO wecom_customer_acquisition_links (
            corp_id,
            automation_channel_id,
            program_id,
            workflow_id,
            initial_audience_code,
            link_id,
            link_name,
            link_url,
            customer_channel,
            final_url,
            skip_verify,
            range_user_list,
            range_department_list,
            priority_option,
            status,
            last_sync_at,
            last_event_at,
            last_error,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CAST(? AS jsonb), CAST(? AS jsonb), CAST(? AS jsonb), ?, NULL, NULL, '', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            _normalized_text(payload.get("corp_id")),
            int(payload.get("automation_channel_id") or 0),
            int(payload.get("program_id") or 0) or None,
            int(payload.get("workflow_id") or 0) or None,
            _normalized_text(payload.get("initial_audience_code")) or "pending_questionnaire",
            _normalized_text(payload.get("link_id")),
            _normalized_text(payload.get("link_name")),
            _normalized_text(payload.get("link_url")),
            _normalized_text(payload.get("customer_channel")),
            _normalized_text(payload.get("final_url")),
            _db_bool(bool(payload.get("skip_verify"))),
            _json_dumps(payload.get("range_user_list") or []),
            _json_dumps(payload.get("range_department_list") or []),
            _json_dumps(payload.get("priority_option") or {}),
            _normalized_text(payload.get("status")) or "active",
        ),
    ).fetchone()
    return dict(row) if row else {}


def update_customer_acquisition_link_status(link_row_id: int, *, status: str, last_error: str = "") -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE wecom_customer_acquisition_links
        SET status = ?,
            last_error = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        RETURNING *
        """,
        (_normalized_text(status), _normalized_text(last_error), int(link_row_id)),
    ).fetchone()
    return dict(row) if row else {}


def touch_customer_acquisition_link_event(link_row_id: int, *, last_error: str = "") -> None:
    get_db().execute(
        """
        UPDATE wecom_customer_acquisition_links
        SET last_event_at = CURRENT_TIMESTAMP,
            last_error = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (_normalized_text(last_error), int(link_row_id)),
    )


def update_customer_acquisition_channel_status(channel_id: int, *, status: str) -> None:
    get_db().execute(
        """
        UPDATE automation_channel
        SET status = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (_normalized_text(status), int(channel_id)),
    )
