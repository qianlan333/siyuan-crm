"""Cross-table reads (agent_config / archived_messages / automation_member) used by workflow flows (阶段 6.1).

Extracted from workflow_repo.py. External callers keep using
``automation_conversion.workflow_repo.X``.
"""

from __future__ import annotations

from typing import Any

from ._repo_helpers import (  # noqa: F401
    _fetchall_dicts,
    _fetchone_dict,
    _normalized_text,
)
from ._workflow_repo_serializers import (
    _serialize_automation_member_row,
)


def list_agent_config_codes() -> list[str]:
    rows = _fetchall_dicts("SELECT agent_code FROM automation_agent_config ORDER BY agent_code ASC")
    return [_normalized_text(row.get("agent_code")) for row in rows if _normalized_text(row.get("agent_code"))]


def list_agent_config_summary_rows(*, enabled_only: bool = False) -> list[dict[str, Any]]:
    sql = """
        SELECT
            agent_code,
            display_name,
            last_change_summary AS description,
            CASE
                WHEN COALESCE(enabled, FALSE) IS NOT TRUE THEN 'disabled'
                WHEN published_version > 0 THEN 'published'
                ELSE 'draft'
            END AS status_code,
            updated_at
        FROM automation_agent_config
        WHERE 1 = 1
    """
    params: list[Any] = []
    if enabled_only:
        sql += " AND COALESCE(enabled, FALSE) IS TRUE AND published_version > 0"
    sql += " ORDER BY updated_at DESC, agent_code ASC"
    return _fetchall_dicts(sql, tuple(params))


def list_automation_member_rows() -> list[dict[str, Any]]:
    return [
        _serialize_automation_member_row(row)
        for row in _fetchall_dicts(
            """
            SELECT *
            FROM automation_member
            ORDER BY id ASC
            """
        )
    ]


def get_automation_member_row(member_id: int) -> dict[str, Any] | None:
    row = _fetchone_dict(
        """
        SELECT *
        FROM automation_member
        WHERE id = ?
        LIMIT 1
        """,
        (int(member_id),),
    )
    return _serialize_automation_member_row(row) if row else None


def count_archived_customer_messages(external_userid: str) -> int:
    row = _fetchone_dict(
        """
        SELECT COUNT(*) AS total
        FROM archived_messages
        WHERE external_userid = ?
          AND sender = ?
        """,
        (_normalized_text(external_userid), _normalized_text(external_userid)),
    ) or {}
    return int(row.get("total") or 0)


def get_archived_customer_message_counts(external_userids: list[str]) -> dict[str, int]:
    normalized_userids = [_normalized_text(item) for item in external_userids if _normalized_text(item)]
    if not normalized_userids:
        return {}
    placeholders = ",".join("?" for _ in normalized_userids)
    rows = _fetchall_dicts(
        f"""
        SELECT external_userid, COUNT(*) AS total
        FROM archived_messages
        WHERE external_userid IN ({placeholders})
          AND sender = external_userid
        GROUP BY external_userid
        """,
        tuple(normalized_userids),
    )
    counts = {_normalized_text(row.get("external_userid")): int(row.get("total") or 0) for row in rows}
    for external_userid in normalized_userids:
        counts.setdefault(external_userid, 0)
    return counts




__all__ = [
    "count_archived_customer_messages",
    "get_archived_customer_message_counts",
    "get_automation_member_row",
    "list_agent_config_codes",
    "list_agent_config_summary_rows",
    "list_automation_member_rows",
]
