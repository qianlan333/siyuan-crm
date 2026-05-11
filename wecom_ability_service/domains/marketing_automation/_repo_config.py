"""marketing_automation config + owner_role + question_rules (阶段 5.4).

Extracted from repo.py. External callers keep using
``marketing_automation.repo.X``.
"""

from __future__ import annotations

from typing import Any

from ...customer_center.repo import (
    fetch_owner_role_map,
)
from ...db import get_db, get_db_backend
from ._repo_helpers import (  # noqa: F401
    _fetchall_dicts,
    _fetchone_dict,
    _json_dumps,
    _normalized_text,
)


def get_owner_role_item(userid: str) -> dict[str, Any]:
    normalized_userid = _normalized_text(userid)
    if not normalized_userid:
        return {}
    return fetch_owner_role_map([normalized_userid]).get(normalized_userid, {})


def get_marketing_automation_config(automation_key: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM marketing_automation_configs
        WHERE automation_key = ?
        """,
        (_normalized_text(automation_key),),
    )


def list_marketing_automation_question_rules(automation_config_id: int) -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT *
        FROM marketing_automation_question_rules
        WHERE automation_config_id = ?
        ORDER BY sort_order ASC, id ASC
        """,
        (int(automation_config_id),),
    )


def upsert_marketing_automation_config(
    *,
    automation_key: str,
    automation_name: str,
    target_event: str,
    channel_type: str,
    status: str,
    do_not_start_after_hour: int,
    config_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    db = get_db()
    params = (
        _normalized_text(automation_key),
        _normalized_text(automation_name),
        _normalized_text(target_event),
        _normalized_text(channel_type),
        _normalized_text(status),
        int(do_not_start_after_hour),
        _json_dumps(config_payload),
    )
    if get_db_backend() == "postgres":
        row = db.execute(
            """
            INSERT INTO marketing_automation_configs (
                automation_key,
                automation_name,
                target_event,
                channel_type,
                status,
                do_not_start_after_hour,
                config_payload_json,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (automation_key) DO UPDATE SET
                automation_name = EXCLUDED.automation_name,
                target_event = EXCLUDED.target_event,
                channel_type = EXCLUDED.channel_type,
                status = EXCLUDED.status,
                do_not_start_after_hour = EXCLUDED.do_not_start_after_hour,
                config_payload_json = EXCLUDED.config_payload_json,
                updated_at = CURRENT_TIMESTAMP
            RETURNING *
            """,
            params,
        ).fetchone()
    else:
        row = db.execute(
            """
            INSERT INTO marketing_automation_configs (
                automation_key,
                automation_name,
                target_event,
                channel_type,
                status,
                do_not_start_after_hour,
                config_payload_json,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (automation_key) DO UPDATE SET
                automation_name = excluded.automation_name,
                target_event = excluded.target_event,
                channel_type = excluded.channel_type,
                status = excluded.status,
                do_not_start_after_hour = excluded.do_not_start_after_hour,
                config_payload_json = excluded.config_payload_json,
                updated_at = CURRENT_TIMESTAMP
            RETURNING *
            """,
            params,
        ).fetchone()
    return dict(row) if row else {}


def replace_marketing_automation_question_rules(
    *,
    automation_config_id: int,
    questionnaire_id: int,
    rules: list[dict[str, Any]],
) -> None:
    db = get_db()
    db.execute(
        "DELETE FROM marketing_automation_question_rules WHERE automation_config_id = ?",
        (int(automation_config_id),),
    )
    for item in rules:
        params = (
            int(automation_config_id),
            int(questionnaire_id),
            int(item["questionnaire_question_id"]),
            _normalized_text(item["rule_code"]),
            _normalized_text(item["rule_name"]),
            "any_of",
            _json_dumps(item.get("hit_option_ids_json") or []),
            int(item.get("sort_order") or 0),
            _json_dumps(item.get("rule_payload") or {}),
        )
        if get_db_backend() == "postgres":
            db.execute(
                """
                INSERT INTO marketing_automation_question_rules (
                    automation_config_id,
                    questionnaire_id,
                    question_id,
                    rule_code,
                    rule_name,
                    answer_match_type,
                    answer_match_value_json,
                    score_delta,
                    segment_hint,
                    stage_hint,
                    is_active,
                    sort_order,
                    rule_payload_json,
                    created_at,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, 0, '', '', TRUE, %s, %s::jsonb, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                params,
            )
        else:
            db.execute(
                """
                INSERT INTO marketing_automation_question_rules (
                    automation_config_id,
                    questionnaire_id,
                    question_id,
                    rule_code,
                    rule_name,
                    answer_match_type,
                    answer_match_value_json,
                    score_delta,
                    segment_hint,
                    stage_hint,
                    is_active,
                    sort_order,
                    rule_payload_json,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, '', '', 1, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                params,
                )




__all__ = [
    "get_marketing_automation_config",
    "get_owner_role_item",
    "list_marketing_automation_question_rules",
    "replace_marketing_automation_question_rules",
    "upsert_marketing_automation_config",
]
