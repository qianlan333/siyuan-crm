"""Questionnaire-related read paths used by workflow runtime (阶段 6.1).

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


def get_questionnaire_row(questionnaire_id: int) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT id, name, title, slug, created_at, updated_at
        FROM questionnaires
        WHERE id = ?
        LIMIT 1
        """,
        (int(questionnaire_id),),
    )


def list_questionnaire_rows() -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT id, name, title, slug, created_at, updated_at
        FROM questionnaires
        WHERE COALESCE(is_disabled, FALSE) = FALSE
        ORDER BY updated_at DESC, id DESC
        """
    )


def list_questionnaire_question_rows(questionnaire_id: int) -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT id, questionnaire_id, type, title, placeholder_text, required, sort_order, created_at, updated_at
        FROM questionnaire_questions
        WHERE questionnaire_id = ?
        ORDER BY sort_order ASC, id ASC
        """,
        (int(questionnaire_id),),
    )


def get_questionnaire_question_row(questionnaire_id: int, question_id: int) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT id, questionnaire_id, type, title, placeholder_text, required, sort_order, created_at, updated_at
        FROM questionnaire_questions
        WHERE questionnaire_id = ? AND id = ?
        LIMIT 1
        """,
        (int(questionnaire_id), int(question_id)),
    )


def list_questionnaire_option_rows(question_id: int) -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT id, question_id, option_text, score, tag_codes, sort_order, created_at, updated_at
        FROM questionnaire_options
        WHERE question_id = ?
        ORDER BY sort_order ASC, id ASC
        """,
        (int(question_id),),
    )


def get_latest_questionnaire_submission_row(
    *,
    questionnaire_id: int,
    external_contact_ids: list[str] | None = None,
    phone: str = "",
) -> dict[str, Any] | None:
    normalized_external_contact_ids = [_normalized_text(item) for item in (external_contact_ids or []) if _normalized_text(item)]
    normalized_phone = _normalized_text(phone)
    filters: list[str] = []
    params: list[Any] = [int(questionnaire_id)]
    if normalized_external_contact_ids:
        placeholders = ",".join("?" for _ in normalized_external_contact_ids)
        filters.append(f"external_userid IN ({placeholders})")
        params.extend(normalized_external_contact_ids)
    if normalized_phone:
        filters.append("mobile_snapshot = ?")
        params.append(normalized_phone)
    if not filters:
        return None
    row = _fetchone_dict(
        """
        SELECT *
        FROM questionnaire_submissions
        WHERE questionnaire_id = ?
          AND (
        """
        + " OR ".join(filters)
        + """
          )
        ORDER BY submitted_at DESC, id DESC
        LIMIT 1
        """,
        tuple(params),
    )
    return row


def get_latest_any_questionnaire_submission_row(*, external_contact_ids: list[str] | None = None, phone: str = "") -> dict[str, Any] | None:
    normalized_external_contact_ids = [_normalized_text(item) for item in (external_contact_ids or []) if _normalized_text(item)]
    normalized_phone = _normalized_text(phone)
    filters: list[str] = []
    params: list[Any] = []
    if normalized_external_contact_ids:
        placeholders = ",".join("?" for _ in normalized_external_contact_ids)
        filters.append(f"external_userid IN ({placeholders})")
        params.extend(normalized_external_contact_ids)
    if normalized_phone:
        filters.append("mobile_snapshot = ?")
        params.append(normalized_phone)
    if not filters:
        return None
    row = _fetchone_dict(
        """
        SELECT *
        FROM questionnaire_submissions
        WHERE
        """
        + " OR ".join(filters)
        + """
        ORDER BY submitted_at DESC, id DESC
        LIMIT 1
        """,
        tuple(params),
    )
    return row


def list_questionnaire_submission_answer_rows(submission_id: int) -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT *
        FROM questionnaire_submission_answers
        WHERE submission_id = ?
        ORDER BY id ASC
        """,
        (int(submission_id),),
    )




__all__ = [
    "get_latest_any_questionnaire_submission_row",
    "get_latest_questionnaire_submission_row",
    "get_questionnaire_question_row",
    "get_questionnaire_row",
    "list_questionnaire_option_rows",
    "list_questionnaire_question_rows",
    "list_questionnaire_rows",
    "list_questionnaire_submission_answer_rows",
]
