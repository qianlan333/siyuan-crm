"""customer_value_segment + marketing_value_segment (阶段 5.4).

Extracted from repo.py. External callers keep using
``marketing_automation.repo.X``.
"""

from __future__ import annotations

from typing import Any

from ...db import get_db
from ._repo_helpers import (  # noqa: F401
    _fetchone_dict,
    _json_dumps,
    _normalized_text,
    _normalized_text_list,
    _placeholders,
)


def get_latest_questionnaire_submission_for_value_segment(
    questionnaire_id: int,
    *,
    external_userids: list[str] | None = None,
    mobile_snapshot: str = "",
) -> dict[str, Any] | None:
    normalized_external_userids = _normalized_text_list(external_userids)
    normalized_mobile = _normalized_text(mobile_snapshot)
    filters: list[str] = []
    params: list[Any] = [int(questionnaire_id)]
    if normalized_external_userids:
        filters.append(f"external_userid IN ({_placeholders(normalized_external_userids)})")
        params.extend(normalized_external_userids)
    if normalized_mobile:
        filters.append("mobile_snapshot = ?")
        params.append(normalized_mobile)
    if not filters:
        return None
    return _fetchone_dict(
        f"""
        SELECT *
        FROM questionnaire_submissions
        WHERE questionnaire_id = ?
          AND ({' OR '.join(filters)})
        ORDER BY submitted_at DESC, id DESC
        LIMIT 1
        """,
        tuple(params),
    )


def get_customer_value_segment_current(external_userid: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM customer_value_segment_current
        WHERE external_userid = ?
        """,
        (_normalized_text(external_userid),),
    )


def upsert_customer_value_segment_current(
    *,
    external_userid: str,
    segment: str,
    segment_rank: int,
    score: int,
    scoring_version: str,
    computed_reason: str,
    submission_id: int | None,
    matched_question_ids: list[int],
    source_payload: dict[str, Any] | None,
    evaluated_at: str,
) -> dict[str, Any]:
    db = get_db()
    params = (
        _normalized_text(external_userid),
        _normalized_text(segment),
        int(segment_rank),
        int(score),
        _normalized_text(scoring_version),
        _normalized_text(computed_reason),
        submission_id,
        _json_dumps(matched_question_ids),
        _json_dumps(source_payload),
        _normalized_text(evaluated_at),
    )
    row = db.execute(
        """
        INSERT INTO customer_value_segment_current (
            external_userid,
            segment,
            segment_rank,
            score,
            scoring_version,
            computed_reason,
            submission_id,
            matched_question_ids_json,
            source_payload_json,
            evaluated_at,
            computed_at,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?::jsonb, ?::jsonb, ?::timestamptz, ?::timestamptz, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT (external_userid) DO UPDATE SET
            segment = EXCLUDED.segment,
            segment_rank = EXCLUDED.segment_rank,
            score = EXCLUDED.score,
            scoring_version = EXCLUDED.scoring_version,
            computed_reason = EXCLUDED.computed_reason,
            submission_id = EXCLUDED.submission_id,
            matched_question_ids_json = EXCLUDED.matched_question_ids_json,
            source_payload_json = EXCLUDED.source_payload_json,
            evaluated_at = EXCLUDED.evaluated_at,
            computed_at = EXCLUDED.computed_at,
            updated_at = CURRENT_TIMESTAMP
        RETURNING *
        """,
        params + (_normalized_text(evaluated_at),),
    ).fetchone()
    return dict(row) if row else {}


def insert_customer_value_segment_history(
    *,
    external_userid: str,
    segment: str,
    segment_rank: int,
    score: int,
    scoring_version: str,
    change_reason: str,
    submission_id: int | None,
    matched_question_ids: list[int],
    source_payload: dict[str, Any] | None,
    evaluated_at: str,
) -> dict[str, Any]:
    db = get_db()
    params = (
        _normalized_text(external_userid),
        _normalized_text(segment),
        int(segment_rank),
        int(score),
        _normalized_text(scoring_version),
        _normalized_text(change_reason),
        submission_id,
        _json_dumps(matched_question_ids),
        _json_dumps(source_payload),
        _normalized_text(evaluated_at),
    )
    row = db.execute(
        """
        INSERT INTO customer_value_segment_history (
            external_userid,
            segment,
            segment_rank,
            score,
            scoring_version,
            change_reason,
            submission_id,
            matched_question_ids_json,
            source_payload_json,
            evaluated_at,
            recorded_at,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?::jsonb, ?::jsonb, ?::timestamptz, ?::timestamptz, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        params + (_normalized_text(evaluated_at),),
    ).fetchone()
    return dict(row) if row else {}


def count_customer_value_segment_history(external_userid: str) -> int:
    row = _fetchone_dict(
        """
        SELECT COUNT(*) AS total
        FROM customer_value_segment_history
        WHERE external_userid = ?
        """,
        (_normalized_text(external_userid),),
    )
    return int((row or {}).get("total") or 0)


def get_marketing_value_segment_current(external_userid: str, *, scenario_key: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM marketing_value_segment_current
        WHERE scenario_key = ? AND external_userid = ?
        """,
        (scenario_key, external_userid),
    )


def upsert_marketing_value_segment_current(
    *,
    scenario_key: str,
    external_userid: str,
    value_segment: str,
    segment_label: str,
    score: int,
    score_breakdown: dict[str, Any] | None,
    source_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    db = get_db()
    params = (
        scenario_key,
        external_userid,
        value_segment,
        segment_label,
        int(score),
        _json_dumps(score_breakdown),
        _json_dumps(source_payload),
    )
    row = db.execute(
        """
        INSERT INTO marketing_value_segment_current (
            scenario_key,
            external_userid,
            value_segment,
            segment_label,
            score,
            score_breakdown_json,
            source_payload_json
        )
        VALUES (?, ?, ?, ?, ?, ?::jsonb, ?::jsonb)
        ON CONFLICT (scenario_key, external_userid) DO UPDATE SET
            value_segment = EXCLUDED.value_segment,
            segment_label = EXCLUDED.segment_label,
            score = EXCLUDED.score,
            score_breakdown_json = EXCLUDED.score_breakdown_json,
            source_payload_json = EXCLUDED.source_payload_json,
            updated_at = CURRENT_TIMESTAMP
        RETURNING *
        """,
        params,
    ).fetchone()
    db.commit()
    return dict(row) if row else {}




__all__ = [
    "count_customer_value_segment_history",
    "get_customer_value_segment_current",
    "get_latest_questionnaire_submission_for_value_segment",
    "get_marketing_value_segment_current",
    "insert_customer_value_segment_history",
    "upsert_customer_value_segment_current",
    "upsert_marketing_value_segment_current",
]
