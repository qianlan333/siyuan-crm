from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import requests  # noqa: F401 - legacy external-push monkeypatch seam
from flask import current_app, has_request_context, session

from ...db import get_db
from ...domains.identity import service as identity_domain_service
from ...infra.settings import get_setting
from ..outbound_webhook.service import EVENT_QUESTIONNAIRE_SUBMIT, send_outbound_webhook
from ..tags import repo as tags_repo

questionnaire_logger = logging.getLogger("questionnaire")
_normalize_mobile = identity_domain_service.normalize_mobile
QUESTIONNAIRE_TYPES = {"single_choice", "multi_choice", "textarea", "mobile"}
QUESTIONNAIRE_EXTERNAL_PUSH_STATUS_SUCCESS = "success"
QUESTIONNAIRE_EXTERNAL_PUSH_STATUS_FAILED = "failed"
QUESTIONNAIRE_EXTERNAL_PUSH_STATUS_SKIPPED = "skipped"
QUESTIONNAIRE_EXTERNAL_PUSH_GLOBAL_ENABLED_KEY = "QUESTIONNAIRE_EXTERNAL_PUSH_GLOBAL_ENABLED"
QUESTIONNAIRE_EXTERNAL_PUSH_GLOBAL_DISABLED_REASON = "skipped by global external push switch"
QUESTIONNAIRE_EXTERNAL_PUSH_RESERVED_KEYS = {
    "user_id",
    "questionnaire_title",
    "submitted_at",
    "answers",
    "phone_number",
    "day",
    "frequency",
    "remark",
}


class QuestionnaireAlreadySubmittedError(ValueError):
    pass


from ._service_helpers import (  # noqa: F401  helpers — 阶段 7.2
    _bind_questionnaire_identity,
    _build_questionnaire_detail,
    _count_questionnaire_external_push_retry_logs,
    _create_questionnaire_external_push_log,
    _dedupe_questionnaire_slug,
    _dedupe_strings,
    _get_questionnaire_external_push_log,
    _get_questionnaire_row,
    _get_questionnaire_row_by_slug,
    _insert_questionnaire_options,
    _json_array,
    _json_dumps,
    _json_loads,
    _load_questionnaire_questions,
    _load_questionnaire_score_rules,
    _normalize_bool,
    _normalize_answer_display_mode,
    _normalize_float,
    _normalize_int,
    _normalize_questionnaire_assessment_config,
    _normalize_questionnaire_external_push_custom_params,
    _normalize_questionnaire_payload,
    _normalize_required_integer,
    _normalize_tag_codes,
    _questionnaire_exists_by_slug,
    _questionnaire_submission_stats,
    _resolve_external_contact_identity_payload,
    _resolve_questionnaire_person_identity,
    _safe_create_questionnaire_external_push_log,
    _serialize_questionnaire_row,
    _slugify_questionnaire,
    _sync_questionnaire_questions,
    _sync_questionnaire_score_rules,
    _validate_tag_codes_payload,
)


def list_questionnaires() -> list[dict[str, Any]]:
    last_submitted_at_expr = "to_char(MAX(s.submitted_at) AT TIME ZONE 'Asia/Shanghai', 'YYYY-MM-DD HH24:MI:SS')"
    rows = get_db().execute(
        f"""
        SELECT q.id, q.slug, q.name, q.title, q.description, q.is_disabled, q.redirect_url,
               q.answer_display_mode,
               q.assessment_enabled, q.assessment_config,
               q.external_push_enabled, q.external_push_url, q.external_push_day, q.external_push_frequency,
               q.external_push_remark, q.external_push_custom_params, q.created_at, q.updated_at,
               COUNT(s.id) AS submission_count, {last_submitted_at_expr} AS last_submitted_at
        FROM questionnaires q
        LEFT JOIN questionnaire_submissions s ON s.questionnaire_id = q.id
        GROUP BY q.id, q.slug, q.name, q.title, q.description, q.is_disabled, q.redirect_url,
                 q.answer_display_mode,
                 q.assessment_enabled, q.assessment_config,
                 q.external_push_enabled, q.external_push_url, q.external_push_day, q.external_push_frequency,
                 q.external_push_remark, q.external_push_custom_params, q.created_at, q.updated_at
        ORDER BY q.updated_at DESC, q.id DESC
        """
    ).fetchall()
    results: list[dict[str, Any]] = []
    for row in rows:
        item = _serialize_questionnaire_row(row)
        item["submission_count"] = int(row["submission_count"] or 0)
        item["last_submitted_at"] = row.get("last_submitted_at", "") or ""
        results.append(item)
    return results


def list_available_wecom_tags() -> list[dict[str, Any]]:
    from ...wecom_client import WeComClient

    client = WeComClient.from_app()
    payload = client.list_external_contact_tags()
    items: list[dict[str, Any]] = []
    for group in payload.get("tag_group") or []:
        group_name = str(group.get("group_name") or "").strip()
        group_id = str(group.get("group_id") or "").strip()
        for tag in group.get("tag") or []:
            tag_id = str(tag.get("id") or "").strip()
            tag_name = str(tag.get("name") or "").strip()
            if not tag_id or not tag_name:
                continue
            items.append(
                {
                    "tag_id": tag_id,
                    "tag_name": tag_name,
                    "group_name": group_name,
                    "group_id": group_id,
                }
            )
    return sorted(items, key=lambda item: ((item.get("group_name") or ""), (item.get("tag_name") or ""), item["tag_id"]))


def get_latest_questionnaire_submit_debug(questionnaire_id: int) -> dict[str, Any] | None:
    submission = get_db().execute(
        """
        SELECT id, questionnaire_id, submitted_at, matched_by, identity_map_id, openid, unionid,
               external_userid, follow_user_userid, total_score, final_tags,
               assessment_result_snapshot, result_token, redirect_url_snapshot
        FROM questionnaire_submissions
        WHERE questionnaire_id = ?
        ORDER BY submitted_at DESC, id DESC
        LIMIT 1
        """,
        (int(questionnaire_id),),
    ).fetchone()
    if not submission:
        return None

    scrm_apply = get_db().execute(
        """
        SELECT status, error_message, add_tag_ids, matched_score_tier_id, matched_score_tier_name,
               matched_dimension_categories
        FROM questionnaire_scrm_apply_logs
        WHERE submission_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (int(submission["id"]),),
    ).fetchone()
    assessment_result = _normalize_questionnaire_assessment_config(
        submission.get("assessment_result_snapshot")
    )
    tag_plan = assessment_result.get("tag_plan") if isinstance(assessment_result.get("tag_plan"), dict) else {}
    matched_dimension_categories = tag_plan.get("matched_dimension_categories") or []
    dimension_category_tag_ids = _dedupe_strings(
        tag
        for item in matched_dimension_categories
        for tag in _normalize_tag_codes((item or {}).get("tag_ids"))
    )
    score_tier_tag_ids = _normalize_tag_codes(tag_plan.get("score_tier_tag_ids"))
    scrm_dimension_categories = _json_array((scrm_apply or {}).get("matched_dimension_categories"))
    scrm_add_tag_ids = _json_array((scrm_apply or {}).get("add_tag_ids"))
    return {
        "questionnaire_id": int(submission["questionnaire_id"]),
        "submission_id": int(submission["id"]),
        "submitted_at": submission.get("submitted_at", "") or "",
        "matched_by": submission.get("matched_by", "") or "",
        "identity_map_id": int(submission["identity_map_id"]) if submission.get("identity_map_id") is not None else None,
        "openid": submission.get("openid", "") or "",
        "unionid": submission.get("unionid", "") or "",
        "external_userid": submission.get("external_userid", "") or "",
        "follow_user_userid": submission.get("follow_user_userid", "") or "",
        "total_score": float(submission.get("total_score") or 0),
        "final_tags": _dedupe_strings(_json_array(submission.get("final_tags"))),
        "assessment_result_snapshot": assessment_result,
        "matched_score_tier_id": (scrm_apply or {}).get("matched_score_tier_id", "") or tag_plan.get("matched_score_tier_id", "") or "",
        "matched_score_tier_name": (scrm_apply or {}).get("matched_score_tier_name", "") or tag_plan.get("matched_score_tier_name", "") or "",
        "matched_dimension_categories": scrm_dimension_categories or matched_dimension_categories,
        "dimension_category_tag_ids": dimension_category_tag_ids,
        "score_tier_tag_ids": score_tier_tag_ids,
        "final_add_tag_ids": _dedupe_strings(scrm_add_tag_ids or tag_plan.get("final_tag_ids") or _json_array(submission.get("final_tags"))),
        "identity_resolved": bool(str(submission.get("external_userid") or "").strip()),
        "result_token": submission.get("result_token", "") or "",
        "redirect_url_snapshot": submission.get("redirect_url_snapshot", "") or "",
        "scrm_apply_status": (scrm_apply or {}).get("status", "") or "",
        "scrm_apply_error": (scrm_apply or {}).get("error_message", "") or "",
    }


def create_questionnaire(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_questionnaire_payload(payload)
    db = get_db()
    try:
        row = db.execute(
            """
            INSERT INTO questionnaires (
                slug, name, title, description, is_disabled, redirect_url,
                answer_display_mode,
                assessment_enabled, assessment_config,
                external_push_enabled, external_push_url, external_push_day, external_push_frequency,
                external_push_remark, external_push_custom_params, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            RETURNING id
            """,
            (
                normalized["slug"],
                normalized["name"],
                normalized["title"],
                normalized["description"],
                normalized["is_disabled"],
                normalized["redirect_url"],
                normalized["answer_display_mode"],
                normalized["assessment_enabled"],
                _json_dumps(normalized["assessment_config"]),
                normalized["external_push_enabled"],
                normalized["external_push_url"],
                normalized["external_push_day"],
                normalized["external_push_frequency"],
                normalized["external_push_remark"],
                _json_dumps(normalized["external_push_custom_params"]),
            ),
        ).fetchone()
        questionnaire_id = int(row["id"])
        _sync_questionnaire_questions(questionnaire_id, normalized["questions"])
        _sync_questionnaire_score_rules(questionnaire_id, normalized["score_rules"])
        db.commit()
        created = get_questionnaire_detail(questionnaire_id)
        if created is None:
            raise RuntimeError("questionnaire creation failed")
        return created
    except Exception:
        db.rollback()
        raise


def get_questionnaire_detail(questionnaire_id: int) -> dict[str, Any] | None:
    row = _get_questionnaire_row(int(questionnaire_id))
    if not row:
        return None
    return _build_questionnaire_detail(row)


def update_questionnaire(questionnaire_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
    existing = _get_questionnaire_row(int(questionnaire_id))
    if not existing:
        return None
    normalized = _normalize_questionnaire_payload(payload, questionnaire_id=int(questionnaire_id), existing=existing)
    db = get_db()
    try:
        db.execute(
            """
            UPDATE questionnaires
            SET slug = ?, name = ?, title = ?, description = ?, is_disabled = ?, redirect_url = ?,
                answer_display_mode = ?,
                assessment_enabled = ?, assessment_config = ?,
                external_push_enabled = ?, external_push_url = ?, external_push_day = ?, external_push_frequency = ?,
                external_push_remark = ?, external_push_custom_params = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                normalized["slug"],
                normalized["name"],
                normalized["title"],
                normalized["description"],
                normalized["is_disabled"],
                normalized["redirect_url"],
                normalized["answer_display_mode"],
                normalized["assessment_enabled"],
                _json_dumps(normalized["assessment_config"]),
                normalized["external_push_enabled"],
                normalized["external_push_url"],
                normalized["external_push_day"],
                normalized["external_push_frequency"],
                normalized["external_push_remark"],
                _json_dumps(normalized["external_push_custom_params"]),
                int(questionnaire_id),
            ),
        )
        _sync_questionnaire_questions(int(questionnaire_id), normalized["questions"])
        _sync_questionnaire_score_rules(int(questionnaire_id), normalized["score_rules"])
        db.commit()
        return get_questionnaire_detail(int(questionnaire_id))
    except Exception:
        db.rollback()
        raise


def disable_questionnaire(questionnaire_id: int, is_disabled: bool = True) -> dict[str, Any] | None:
    db = get_db()
    db.execute(
        """
        UPDATE questionnaires
        SET is_disabled = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (_normalize_bool(is_disabled), int(questionnaire_id)),
    )
    db.commit()
    return get_questionnaire_detail(int(questionnaire_id))


def delete_questionnaire(questionnaire_id: int) -> bool:
    db = get_db()
    cursor = db.execute("DELETE FROM questionnaires WHERE id = ?", (int(questionnaire_id),))
    db.commit()
    return cursor.rowcount > 0


def _list_questionnaire_export_records(questionnaire_id: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    db = get_db()
    submission_rows = db.execute(
        """
        SELECT id, submitted_at, respondent_key, openid, unionid, external_userid, follow_user_userid,
               matched_by, source_channel, campaign_id, staff_id, total_score, final_tags,
               assessment_result_snapshot
        FROM questionnaire_submissions
        WHERE questionnaire_id = ?
        ORDER BY submitted_at DESC, id DESC
        """,
        (int(questionnaire_id),),
    ).fetchall()
    answer_rows = db.execute(
        """
        SELECT submission_id, question_id, question_type, question_title_snapshot,
               selected_option_texts_snapshot, text_value
        FROM questionnaire_submission_answers
        WHERE submission_id IN (
            SELECT id FROM questionnaire_submissions WHERE questionnaire_id = ?
        )
        ORDER BY submission_id ASC, id ASC
        """,
        (int(questionnaire_id),),
    ).fetchall()
    return submission_rows, answer_rows


def _build_questionnaire_export_columns(
    questionnaire: dict[str, Any],
    answer_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    current_sort_order = {
        int(question["id"]): int(question.get("sort_order") or 0) for question in questionnaire["questions"]
    }
    if not answer_rows:
        return [
            {
                "question_id": int(question["id"]),
                "title": question["title"],
                "sort_order": int(question.get("sort_order") or 0),
            }
            for question in questionnaire["questions"]
        ]
    question_columns: list[dict[str, Any]] = []
    seen_question_ids: set[int] = set()
    for row in answer_rows:
        question_id = int(row["question_id"])
        if question_id in seen_question_ids:
            continue
        seen_question_ids.add(question_id)
        question_columns.append(
            {
                "question_id": question_id,
                "title": row.get("question_title_snapshot", "") or f"Question {question_id}",
                "sort_order": current_sort_order.get(question_id, 10_000 + len(question_columns)),
            }
        )
    question_columns.sort(key=lambda item: (item["sort_order"], item["question_id"]))
    return question_columns


def _build_questionnaire_export_answer_values(answer_rows: list[dict[str, Any]]) -> dict[int, dict[int, str]]:
    answer_values_by_submission: dict[int, dict[int, str]] = {}
    for row in answer_rows:
        submission_id = int(row["submission_id"])
        question_id = int(row["question_id"])
        question_type = row.get("question_type", "")
        if question_type in {"textarea", "mobile"}:
            cell_value = row.get("text_value", "") or ""
        else:
            cell_value = "/".join(_dedupe_strings(_json_array(row.get("selected_option_texts_snapshot"))))
        answer_values_by_submission.setdefault(submission_id, {})[question_id] = cell_value
    return answer_values_by_submission


def _build_questionnaire_export_row(
    questionnaire_name: str,
    submission: dict[str, Any],
    *,
    answer_map: dict[int, str],
    question_order: list[int],
) -> list[str]:
    assessment_result = _normalize_questionnaire_assessment_config(submission.get("assessment_result_snapshot"))
    overall_level = assessment_result.get("overall_level") if isinstance(assessment_result, dict) else {}
    dimensions = assessment_result.get("dimensions") if isinstance(assessment_result, dict) else []
    dimension_summary = ""
    if isinstance(dimensions, list):
        dimension_summary = " / ".join(
            _dedupe_strings(
                [
                    f"{item.get('name') or item.get('key')}: {item.get('score')}"
                    for item in dimensions
                    if isinstance(item, dict) and (item.get("name") or item.get("key"))
                ]
            )
        )
    return [
        submission.get("submitted_at", "") or "",
        questionnaire_name,
        submission.get("respondent_key", "") or "",
        submission.get("openid", "") or "",
        submission.get("unionid", "") or "",
        submission.get("external_userid", "") or "",
        submission.get("follow_user_userid", "") or "",
        submission.get("matched_by", "") or "",
        submission.get("source_channel", "") or "",
        submission.get("campaign_id", "") or "",
        submission.get("staff_id", "") or "",
        str(submission.get("total_score", "") or 0),
        "/".join(_dedupe_strings(_json_array(submission.get("final_tags")))),
        str((overall_level or {}).get("title") or (overall_level or {}).get("name") or ""),
        "/".join(item.get("name", "") for item in assessment_result.get("strengths", []) if isinstance(item, dict)),
        "/".join(item.get("name", "") for item in assessment_result.get("weaknesses", []) if isinstance(item, dict)),
        dimension_summary,
        *[answer_map.get(question_id, "") for question_id in question_order],
    ]


def export_questionnaire_submissions(questionnaire_id: int) -> dict[str, Any]:
    questionnaire = get_questionnaire_detail(int(questionnaire_id))
    if not questionnaire:
        raise LookupError("questionnaire not found")

    submission_rows, answer_rows = _list_questionnaire_export_records(int(questionnaire_id))
    question_columns = _build_questionnaire_export_columns(questionnaire, answer_rows)
    question_headers = [column["title"] for column in question_columns]
    question_order = [column["question_id"] for column in question_columns]
    answer_values_by_submission = _build_questionnaire_export_answer_values(answer_rows)
    headers = [
        "提交时间",
        "问卷名称",
        "respondent_key",
        "openid",
        "unionid",
        "external_userid",
        "follow_user_userid",
        "matched_by",
        "source_channel",
        "campaign_id",
        "staff_id",
        "总分",
        "最终标签",
        "测评等级",
        "测评优势项",
        "测评劣势项",
        "五维分数摘要",
        *question_headers,
    ]
    rows: list[list[str]] = []
    for submission in submission_rows:
        submission_id = int(submission["id"])
        rows.append(
            _build_questionnaire_export_row(
                questionnaire["name"],
                submission,
                answer_map=answer_values_by_submission.get(submission_id, {}),
                question_order=question_order,
            )
        )

    return {
        "questionnaire": questionnaire,
        "headers": headers,
        "rows": rows,
        "filename": f"questionnaire-{questionnaire['slug']}-submissions.xls",
    }


def get_public_questionnaire_by_slug(slug: str) -> dict[str, Any] | None:
    row = _get_questionnaire_row_by_slug(slug, require_enabled=True)
    if not row:
        return None
    detail = _build_questionnaire_detail(row)
    detail["answer_display_mode"] = _normalize_answer_display_mode(detail.get("answer_display_mode"))
    detail["questions"] = [
        {
            "id": question["id"],
            "type": question["type"],
            "title": question["title"],
            "placeholder_text": question.get("placeholder_text", "") or "",
            "required": question["required"],
            "sort_order": question["sort_order"],
            "options": [
                {
                    "id": option["id"],
                    "option_text": option["option_text"],
                    "sort_order": option["sort_order"],
                }
                for option in question["options"]
            ],
        }
        for question in detail["questions"]
    ]
    detail.pop("score_rules", None)
    detail.pop("submission_count", None)
    detail.pop("last_submitted_at", None)
    detail.pop("assessment_enabled", None)
    detail.pop("assessment_config", None)
    detail.pop("external_push_enabled", None)
    detail.pop("external_push_url", None)
    detail.pop("external_push_day", None)
    detail.pop("external_push_frequency", None)
    detail.pop("external_push_remark", None)
    detail.pop("external_push_custom_params", None)
    return detail


def get_questionnaire_assessment_result_by_token(slug: str, result_token: str) -> dict[str, Any] | None:
    normalized_slug = str(slug or "").strip()
    normalized_token = str(result_token or "").strip()
    if not normalized_slug or not normalized_token:
        return None
    row = get_db().execute(
        """
        SELECT
            q.id AS questionnaire_id,
            q.slug,
            q.name,
            q.title,
            q.description,
            s.id AS submission_id,
            s.submitted_at,
            s.total_score,
            s.final_tags,
            s.assessment_result_snapshot,
            s.result_token
        FROM questionnaire_submissions s
        JOIN questionnaires q ON q.id = s.questionnaire_id
        WHERE q.slug = ? AND q.is_disabled = ? AND s.result_token = ?
        LIMIT 1
        """,
        (normalized_slug, False, normalized_token),
    ).fetchone()
    if not row:
        return None
    assessment_result = _normalize_questionnaire_assessment_config(row.get("assessment_result_snapshot"))
    if not assessment_result:
        return None
    return {
        "questionnaire": {
            "id": int(row["questionnaire_id"]),
            "slug": row.get("slug", "") or "",
            "name": row.get("name", "") or "",
            "title": row.get("title", "") or "",
            "description": row.get("description", "") or "",
        },
        "submission": {
            "id": int(row["submission_id"]),
            "submitted_at": row.get("submitted_at", "") or "",
            "total_score": float(row.get("total_score") or 0),
            "final_tags": _dedupe_strings(_json_array(row.get("final_tags"))),
            "result_token": row.get("result_token", "") or "",
        },
        "assessment_result": assessment_result,
    }


def delete_questionnaire_submissions_by_slug(slug: str) -> dict[str, Any]:
    normalized_slug = str(slug or "").strip()
    if not normalized_slug:
        raise ValueError("slug is required")
    db = get_db()
    questionnaire = db.execute(
        """
        SELECT id, slug, title, name
        FROM questionnaires
        WHERE slug = ?
        LIMIT 1
        """,
        (normalized_slug,),
    ).fetchone()
    if not questionnaire:
        raise LookupError("questionnaire not found")

    questionnaire_id = int(questionnaire["id"])
    counts = db.execute(
        """
        SELECT
            COUNT(*) AS submission_count,
            COALESCE((
                SELECT COUNT(*)
                FROM questionnaire_submission_answers
                WHERE submission_id IN (
                    SELECT id FROM questionnaire_submissions WHERE questionnaire_id = ?
                )
            ), 0) AS answer_count,
            COALESCE((
                SELECT COUNT(*)
                FROM questionnaire_scrm_apply_logs
                WHERE submission_id IN (
                    SELECT id FROM questionnaire_submissions WHERE questionnaire_id = ?
                )
            ), 0) AS scrm_apply_log_count,
            COALESCE((
                SELECT COUNT(*)
                FROM questionnaire_external_push_logs
                WHERE submission_record_id IN (
                    SELECT id FROM questionnaire_submissions WHERE questionnaire_id = ?
                )
            ), 0) AS external_push_log_count
        FROM questionnaire_submissions
        WHERE questionnaire_id = ?
        """,
        (questionnaire_id, questionnaire_id, questionnaire_id, questionnaire_id),
    ).fetchone()
    db.execute(
        """
        DELETE FROM questionnaire_submissions
        WHERE questionnaire_id = ?
        """,
        (questionnaire_id,),
    )
    db.commit()
    return {
        "questionnaire_id": questionnaire_id,
        "slug": str(questionnaire["slug"] or ""),
        "questionnaire_title": str(questionnaire["title"] or questionnaire["name"] or ""),
        "deleted_submission_count": int((counts or {}).get("submission_count") or 0),
        "deleted_answer_count": int((counts or {}).get("answer_count") or 0),
        "deleted_scrm_apply_log_count": int((counts or {}).get("scrm_apply_log_count") or 0),
        "deleted_external_push_log_count": int((counts or {}).get("external_push_log_count") or 0),
    }


def _normalize_answer_payload(answers: Any) -> dict[str, Any]:
    if isinstance(answers, dict):
        return {str(key): value for key, value in answers.items()}
    if isinstance(answers, list):
        normalized: dict[str, Any] = {}
        for item in answers:
            if not isinstance(item, dict):
                continue
            question_id = item.get("question_id") or item.get("id")
            if question_id in (None, ""):
                continue
            value = item.get("value")
            if value is None and "selected_option_ids" in item:
                value = item.get("selected_option_ids")
            if value is None and "text_value" in item:
                value = item.get("text_value")
            normalized[str(question_id)] = value
        return normalized
    raise ValueError("answers must be an object or array")


def validate_questionnaire_answers(questionnaire: dict[str, Any], answers: Any) -> list[dict[str, Any]]:
    normalized_answers = _normalize_answer_payload(answers)
    known_question_ids = {str(int(question["id"])) for question in questionnaire.get("questions") or []}
    unknown_question_ids = sorted(set(normalized_answers.keys()) - known_question_ids)
    if unknown_question_ids:
        raise ValueError(f"unknown question_id: {','.join(unknown_question_ids)}")
    validated: list[dict[str, Any]] = []

    for question in questionnaire.get("questions") or []:
        question_id = int(question["id"])
        question_key = str(question_id)
        question_type = question["type"]
        raw_value = normalized_answers.get(question_key)
        option_map = {int(option["id"]): option for option in question.get("options") or []}

        if question_type in {"textarea", "mobile"}:
            text_value = str(raw_value or "").strip()
            if question_type == "mobile" and text_value:
                text_value = _normalize_mobile(text_value)
            if question["required"] and not text_value:
                raise ValueError(f"question '{question['title']}' is required")
            validated.append(
                {
                    "question": question,
                    "question_id": question_id,
                    "question_type": question_type,
                    "selected_options": [],
                    "text_value": text_value,
                }
            )
            continue

        selected_ids_raw: list[Any]
        if raw_value in (None, ""):
            selected_ids_raw = []
        elif isinstance(raw_value, list):
            selected_ids_raw = raw_value
        else:
            selected_ids_raw = [raw_value]

        normalized_ids: list[int] = []
        seen_ids: set[int] = set()
        for raw_id in selected_ids_raw:
            try:
                option_id = int(raw_id)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"question '{question['title']}' has an invalid option") from exc
            if option_id in seen_ids:
                continue
            if option_id not in option_map:
                raise ValueError(f"question '{question['title']}' has an invalid option")
            seen_ids.add(option_id)
            normalized_ids.append(option_id)

        if question_type == "single_choice" and len(normalized_ids) > 1:
            raise ValueError(f"question '{question['title']}' only allows one option")
        if question["required"] and not normalized_ids:
            raise ValueError(f"question '{question['title']}' is required")

        validated.append(
            {
                "question": question,
                "question_id": question_id,
                "question_type": question_type,
                "selected_options": [option_map[option_id] for option_id in normalized_ids],
                "text_value": "",
            }
        )

    return validated


def _as_assessment_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _assessment_dimension_configs(config: dict[str, Any]) -> list[dict[str, Any]]:
    raw_dimensions = config.get("dimensions") or []
    if isinstance(raw_dimensions, dict):
        raw_dimensions = [{"key": key, **(value if isinstance(value, dict) else {})} for key, value in raw_dimensions.items()]
    dimensions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(_as_assessment_list(raw_dimensions), start=1):
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or item.get("dimension_key") or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        dimensions.append(
            {
                **item,
                "key": key,
                "name": str(item.get("name") or item.get("title") or key).strip(),
                "sort_order": int(item.get("sort_order") or index),
                "enabled": _normalize_bool(item.get("enabled", True)),
                "participates_in_total_score": _normalize_bool(item.get("participates_in_total_score", True)),
                "show_in_result": _normalize_bool(item.get("show_in_result", True)),
            }
        )
    dimensions.sort(key=lambda item: (int(item.get("sort_order") or 0), str(item.get("key") or "")))
    return dimensions


def _assessment_types_map(dimension_config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw_types = dimension_config.get("types") or dimension_config.get("type_options") or []
    if isinstance(raw_types, dict):
        raw_types = [{"key": key, **(value if isinstance(value, dict) else {})} for key, value in raw_types.items()]
    type_map: dict[str, dict[str, Any]] = {}
    for item in _as_assessment_list(raw_types):
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or item.get("type_key") or "").strip()
        if not key:
            continue
        type_map[key] = {
            **item,
            "key": key,
            "name": str(item.get("name") or item.get("title") or key).strip(),
            "title": str(item.get("title") or item.get("name") or key).strip(),
            "greeting": str(item.get("greeting") or "").strip(),
            "diagnosis": str(item.get("diagnosis") or item.get("summary") or item.get("description") or "").strip(),
            "problem_hint": str(item.get("problem_hint") or "").strip(),
            "recommended_action": str(item.get("recommended_action") or "").strip(),
            "course_name": str(item.get("course_name") or "").strip(),
            "course_url": str(item.get("course_url") or item.get("cta_url") or "").strip(),
            "cta_text": str(item.get("cta_text") or "").strip(),
            "enabled": _normalize_bool(item.get("enabled", True)),
            "show_in_result": _normalize_bool(item.get("show_in_result", True)),
            "sort_order": int(item.get("sort_order") or len(type_map) + 1),
            "tag_codes": _normalize_tag_codes(item.get("tag_codes")),
        }
    return type_map


def _assessment_dimension_by_key(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["key"]: item for item in _assessment_dimension_configs(config)}


def _match_assessment_level(levels: Any, *, score: float, score_percent: float | None = None) -> dict[str, Any] | None:
    for item in _as_assessment_list(levels):
        if not isinstance(item, dict):
            continue
        min_score = item.get("min_score")
        max_score = item.get("max_score")
        min_percent = item.get("min_percent")
        max_percent = item.get("max_percent")
        if min_score not in (None, "") and score < float(min_score):
            continue
        if max_score not in (None, "") and score > float(max_score):
            continue
        if score_percent is not None:
            if min_percent not in (None, "") and score_percent < float(min_percent):
                continue
            if max_percent not in (None, "") and score_percent > float(max_percent):
                continue
        return {
            "key": str(item.get("key") or item.get("level_key") or "").strip(),
            "name": str(item.get("name") or item.get("title") or item.get("label") or "").strip(),
            "title": str(item.get("title") or item.get("name") or item.get("label") or "").strip(),
            "greeting": str(item.get("greeting") or "").strip(),
            "summary": str(item.get("summary") or item.get("description") or item.get("diagnosis") or "").strip(),
            "recommended_action": str(item.get("recommended_action") or "").strip(),
            "course_name": str(item.get("course_name") or "").strip(),
            "course_url": str(item.get("course_url") or item.get("cta_url") or "").strip(),
            "cta_text": str(item.get("cta_text") or "").strip(),
            "enabled": _normalize_bool(item.get("enabled", True)),
            "tag_codes": _normalize_tag_codes(item.get("tag_codes")),
        }
    return None


def _assessment_question_max_score(question: dict[str, Any]) -> float:
    option_scores = [float(option.get("score") or 0) for option in question.get("options") or []]
    if not option_scores:
        return 0.0
    if question.get("type") == "multi_choice":
        positive_total = sum(score for score in option_scores if score > 0)
        return positive_total if positive_total > 0 else max(option_scores)
    return max(option_scores)


def _select_assessment_type(
    type_counts: dict[str, int],
    type_scores: dict[str, float],
    type_sort_orders: dict[str, int],
    dimension_config: dict[str, Any],
    type_map: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if not type_counts:
        return {}
    top_count = max(type_counts.values())
    candidates = {key for key, count in type_counts.items() if count == top_count}
    if len(candidates) > 1:
        top_score = max(float(type_scores.get(key) or 0) for key in candidates)
        candidates = {key for key in candidates if float(type_scores.get(key) or 0) == top_score}
    if len(candidates) > 1:
        best_sort_order = min(int(type_sort_orders.get(key) or 999999) for key in candidates)
        candidates = {key for key in candidates if int(type_sort_orders.get(key) or 999999) == best_sort_order}
    priority = [str(item or "").strip() for item in dimension_config.get("type_priority") or []]
    if not priority:
        priority = list(type_map.keys())
    dominant_key = ""
    for key in priority:
        if key in candidates:
            dominant_key = key
            break
    if not dominant_key:
        dominant_key = sorted(candidates)[0]
    type_config = type_map.get(dominant_key) or {"key": dominant_key, "name": dominant_key, "tag_codes": []}
    return {
        "key": dominant_key,
        "name": str(type_config.get("name") or dominant_key).strip(),
        "title": str(type_config.get("title") or type_config.get("name") or dominant_key).strip(),
        "count": int(type_counts[dominant_key]),
        "score": float(type_scores.get(dominant_key) or 0),
        "greeting": str(type_config.get("greeting") or "").strip(),
        "summary": str(type_config.get("summary") or type_config.get("diagnosis") or type_config.get("description") or "").strip(),
        "diagnosis": str(type_config.get("diagnosis") or type_config.get("summary") or type_config.get("description") or "").strip(),
        "problem_hint": str(type_config.get("problem_hint") or "").strip(),
        "recommended_action": str(type_config.get("recommended_action") or "").strip(),
        "course_name": str(type_config.get("course_name") or "").strip(),
        "course_url": str(type_config.get("course_url") or type_config.get("cta_url") or "").strip(),
        "cta_text": str(type_config.get("cta_text") or "").strip(),
        "enabled": _normalize_bool(type_config.get("enabled", True)),
        "show_in_result": _normalize_bool(type_config.get("show_in_result", True)),
        "tag_codes": _normalize_tag_codes(type_config.get("tag_codes")),
    }


def _assessment_recommendations(
    config: dict[str, Any],
    dimensions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rules = _as_assessment_list(config.get("recommendations") or config.get("recommendation_rules"))
    recommendations: list[dict[str, Any]] = []
    dimension_by_key = {item["key"]: item for item in dimensions}
    for item in rules:
        if not isinstance(item, dict):
            continue
        dimension_key = str(item.get("dimension_key") or "").strip()
        dimension = dimension_by_key.get(dimension_key) if dimension_key else None
        score = float((dimension or {}).get("score") or 0)
        score_percent = (dimension or {}).get("score_percent")
        if dimension_key and not dimension:
            continue
        matched_level = _match_assessment_level([item], score=score, score_percent=score_percent)
        if not matched_level:
            continue
        recommendations.append(
            {
                "dimension_key": dimension_key,
                "title": str(item.get("title") or item.get("name") or "").strip(),
                "summary": str(item.get("summary") or item.get("description") or "").strip(),
                "cta_text": str(item.get("cta_text") or "").strip(),
                "cta_url": str(item.get("cta_url") or "").strip(),
                "tag_codes": _normalize_tag_codes(item.get("tag_codes")),
            }
        )
    return recommendations


def _compute_assessment_result(questionnaire: dict[str, Any], validated_answers: list[dict[str, Any]]) -> dict[str, Any]:
    if not _normalize_bool(questionnaire.get("assessment_enabled")):
        return {}
    config = _normalize_questionnaire_assessment_config(questionnaire.get("assessment_config"))
    dimension_config_by_key = _assessment_dimension_by_key(config)
    dimension_order = list(dimension_config_by_key.keys())
    default_dimension_key = "ungrouped"
    has_ungrouped_question = any(
        str((item.get("question") or {}).get("type") or "").strip() in {"single_choice", "multi_choice"}
        and not str((item.get("question") or {}).get("assessment_dimension_key") or "").strip()
        for item in validated_answers
    )
    if has_ungrouped_question and default_dimension_key not in dimension_config_by_key:
        dimension_config_by_key[default_dimension_key] = {
            "key": default_dimension_key,
            "name": "未分组维度",
            "sort_order": len(dimension_order) + 1,
            "enabled": True,
            "participates_in_total_score": True,
            "show_in_result": True,
            "types": [],
            "type_priority": [],
        }
        dimension_order.append(default_dimension_key)
    accumulator: dict[str, dict[str, Any]] = {}

    def ensure_dimension(key: str) -> dict[str, Any]:
        if key not in accumulator:
            cfg = dimension_config_by_key.get(key) or {
                "key": key,
                "name": key,
                "sort_order": len(dimension_order) + len(accumulator) + 1,
            }
            accumulator[key] = {
                "key": key,
                "name": str(cfg.get("name") or key).strip(),
                "sort_order": int(cfg.get("sort_order") or 0),
                "score": 0.0,
                "max_score": 0.0,
                "answer_count": 0,
                "type_counts": {},
                "type_scores": {},
                "type_sort_orders": {},
            }
        return accumulator[key]

    for key in dimension_order:
        ensure_dimension(key)

    for item in validated_answers:
        question = item.get("question") or {}
        question_type = str(question.get("type") or "").strip()
        if question_type not in {"single_choice", "multi_choice"}:
            continue
        dimension_key = str(question.get("assessment_dimension_key") or "").strip() or default_dimension_key
        bucket = ensure_dimension(dimension_key)
        selected_options = item.get("selected_options") or []
        bucket["max_score"] += _assessment_question_max_score(question)
        selected_score = sum(float(option.get("score") or 0) for option in selected_options)
        bucket["score"] += selected_score
        if selected_options:
            bucket["answer_count"] += 1
        type_counts = bucket["type_counts"]
        type_scores = bucket["type_scores"]
        type_sort_orders = bucket["type_sort_orders"]
        for option in selected_options:
            type_key = str(option.get("assessment_type_key") or "").strip()
            if not type_key:
                type_key = "unknown"
                type_sort_orders.setdefault(type_key, 999999)
            else:
                type_sort_orders[type_key] = min(
                    int(type_sort_orders.get(type_key) or 999999),
                    int(option.get("sort_order") or 999999),
                )
            if not type_key:
                continue
            type_counts[type_key] = int(type_counts.get(type_key) or 0) + 1
            type_scores[type_key] = float(type_scores.get(type_key) or 0) + float(option.get("score") or 0)

    dimensions: list[dict[str, Any]] = []
    assessment_tag_codes: list[str] = []
    dimension_category_tag_codes: list[str] = []
    matched_dimension_categories: list[dict[str, Any]] = []
    for key, bucket in accumulator.items():
        cfg = dimension_config_by_key.get(key) or {"key": key, "name": bucket["name"]}
        type_map = _assessment_types_map(cfg)
        if "unknown" in (bucket.get("type_counts") or {}) and "unknown" not in type_map:
            type_map["unknown"] = {
                "key": "unknown",
                "name": "未分类",
                "title": "未分类",
                "summary": "该维度暂未配置明确分类结果。",
                "tag_codes": [],
            }
        max_score = float(bucket.get("max_score") or 0)
        score = float(bucket.get("score") or 0)
        score_percent = round(score / max_score * 100, 2) if max_score > 0 else None
        dominant_type = _select_assessment_type(
            bucket.get("type_counts") or {},
            bucket.get("type_scores") or {},
            bucket.get("type_sort_orders") or {},
            cfg,
            type_map,
        )
        dimension_level = _match_assessment_level(
            cfg.get("levels") or cfg.get("score_levels"),
            score=score,
            score_percent=score_percent,
        )
        dominant_type_tag_codes = _normalize_tag_codes(dominant_type.get("tag_codes"))
        dimension_category_tag_codes.extend(dominant_type_tag_codes)
        assessment_tag_codes.extend(dominant_type_tag_codes)
        matched_dimension_categories.append(
            {
                "dimension_key": key,
                "dimension_name": str(cfg.get("name") or bucket["name"] or key).strip(),
                "category_key": str(dominant_type.get("key") or "").strip(),
                "category_name": str(dominant_type.get("name") or dominant_type.get("title") or "").strip(),
                "tag_ids": dominant_type_tag_codes,
            }
        )
        dimensions.append(
            {
                "key": key,
                "name": str(cfg.get("name") or bucket["name"] or key).strip(),
                "enabled": _normalize_bool(cfg.get("enabled", True)),
                "participates_in_total_score": _normalize_bool(cfg.get("participates_in_total_score", True)),
                "show_in_result": _normalize_bool(cfg.get("show_in_result", True)),
                "score": score,
                "max_score": max_score,
                "score_percent": score_percent,
                "answer_count": int(bucket.get("answer_count") or 0),
                "type_counts": dict(bucket.get("type_counts") or {}),
                "dominant_type": {
                    key: value for key, value in dominant_type.items() if key != "tag_codes"
                },
                "level": {
                    key: value for key, value in (dimension_level or {}).items() if key != "tag_codes"
                },
                "feedback": cfg.get("feedback") if isinstance(cfg.get("feedback"), dict) else {},
            }
        )

    dimensions.sort(key=lambda item: (int((dimension_config_by_key.get(item["key"]) or {}).get("sort_order") or 0), item["key"]))
    total_score = sum(float(item.get("score") or 0) for item in dimensions if item.get("participates_in_total_score") is not False)
    total_max_score = sum(float(item.get("max_score") or 0) for item in dimensions if item.get("participates_in_total_score") is not False)
    overall_level = _match_assessment_level(config.get("overall_levels"), score=total_score)
    score_tier_tag_codes: list[str] = []
    if overall_level:
        score_tier_tag_codes = _normalize_tag_codes(overall_level.get("tag_codes"))
        assessment_tag_codes.extend(score_tier_tag_codes)
    else:
        overall_level = {
            "key": "fallback",
            "name": "暂未命中分层",
            "title": "暂未命中分层",
            "summary": "当前总分没有命中已配置的分数区间，请联系管理员完善分层配置。",
        }

    ranked = sorted(
        dimensions,
        key=lambda item: (
            item.get("score_percent") if item.get("score_percent") is not None else float(item.get("score") or 0),
            float(item.get("score") or 0),
        ),
        reverse=True,
    )
    strength_count = int(config.get("strength_count") or 2)
    weakness_count = int(config.get("weakness_count") or 2)
    strengths = ranked[: max(0, strength_count)]
    weaknesses = list(reversed(ranked[-max(0, weakness_count) :])) if weakness_count > 0 else []
    recommendations = _assessment_recommendations(config, dimensions)
    final_tag_codes = _dedupe_strings(assessment_tag_codes)
    overall_level_key = str((overall_level or {}).get("key") or (overall_level or {}).get("local_key") or "").strip()
    overall_level_name = str((overall_level or {}).get("name") or (overall_level or {}).get("title") or "").strip()

    return {
        "enabled": True,
        "total_score": total_score,
        "total_max_score": total_max_score,
        "overall_level": {key: value for key, value in (overall_level or {}).items() if key != "tag_codes"},
        "strengths": [{"key": item["key"], "name": item["name"], "score": item["score"]} for item in strengths],
        "weaknesses": [{"key": item["key"], "name": item["name"], "score": item["score"]} for item in weaknesses],
        "dimensions": dimensions,
        "recommendations": [
            {key: value for key, value in item.items() if key != "tag_codes"} for item in recommendations
        ],
        "final_recommendation": config.get("final_recommendation") if isinstance(config.get("final_recommendation"), dict) else {},
        "tag_codes": final_tag_codes,
        "tag_plan": {
            "matched_score_tier_id": overall_level_key,
            "matched_score_tier_name": overall_level_name,
            "matched_dimension_categories": matched_dimension_categories,
            "dimension_category_tag_ids": _dedupe_strings(dimension_category_tag_codes),
            "score_tier_tag_ids": score_tier_tag_codes,
            "final_tag_ids": final_tag_codes,
        },
    }


def compute_questionnaire_submission_outcome(questionnaire: dict[str, Any], answers: Any) -> dict[str, Any]:
    validated_answers = answers if isinstance(answers, list) and answers and "question" in answers[0] else validate_questionnaire_answers(questionnaire, answers)
    is_assessment = _normalize_bool(questionnaire.get("assessment_enabled"))
    total_score = 0.0
    option_tags: list[str] = []
    answer_snapshots: list[dict[str, Any]] = []

    for item in validated_answers:
        question = item["question"]
        selected_options = item.get("selected_options") or []
        selected_option_ids = [int(option["id"]) for option in selected_options]
        selected_option_texts = [option["option_text"] for option in selected_options]
        selected_option_scores = [float(option.get("score") or 0) for option in selected_options]
        selected_option_tags = _dedupe_strings(
            [tag for option in selected_options for tag in _normalize_tag_codes(option.get("tag_codes"))]
        )
        score_contribution = sum(selected_option_scores)
        if question["type"] in {"single_choice", "multi_choice"}:
            total_score += score_contribution
            if not is_assessment:
                option_tags.extend(selected_option_tags)

        answer_snapshots.append(
            {
                "question_id": int(question["id"]),
                "question_type": question["type"],
                "question_title_snapshot": question["title"],
                "selected_option_ids": selected_option_ids,
                "selected_option_texts_snapshot": selected_option_texts,
                "selected_option_scores_snapshot": selected_option_scores,
                "selected_option_tags_snapshot": selected_option_tags,
                "text_value": item.get("text_value", ""),
                "score_contribution": score_contribution if question["type"] not in {"textarea", "mobile"} else 0.0,
            }
        )

    assessment_result = _compute_assessment_result(questionnaire, validated_answers)
    if assessment_result:
        total_score = float(assessment_result.get("total_score") or 0)

    matched_rule_tags: list[str] = []
    if not is_assessment:
        for rule in questionnaire.get("score_rules") or []:
            min_score = rule.get("min_score")
            max_score = rule.get("max_score")
            if min_score is not None and total_score < float(min_score):
                continue
            if max_score is not None and total_score > float(max_score):
                continue
            matched_rule_tags.extend(_normalize_tag_codes(rule.get("tag_codes")))

    result_token = uuid4().hex if assessment_result else ""
    result_url = f"/s/{questionnaire.get('slug')}/result/{result_token}" if result_token else ""
    if assessment_result and result_url:
        assessment_result["result_path"] = result_url
    final_tags = _dedupe_strings(_normalize_tag_codes(assessment_result.get("tag_codes")) if is_assessment else option_tags + matched_rule_tags)
    return {
        "validated_answers": validated_answers,
        "answer_snapshots": answer_snapshots,
        "total_score": total_score,
        "final_tags": final_tags,
        "assessment_result": assessment_result,
        "result_token": result_token,
        "result_url": result_url,
        "redirect_url": result_url or questionnaire.get("redirect_url", "") or "",
    }


def resolve_questionnaire_submit_identity(
    openid: str = "",
    unionid: str = "",
    external_userid: str = "",
) -> dict[str, Any] | None:
    corp_id = str(current_app.config.get("WECOM_CORP_ID", "") or "").strip()
    if not corp_id:
        return None
    lookup_order = [
        ("unionid", str(unionid or "").strip()),
        ("openid", str(openid or "").strip()),
        ("external_userid", str(external_userid or "").strip()),
    ]
    for matched_by, value in lookup_order:
        if not value:
            continue
        resolved = _resolve_external_contact_identity_payload(corp_id=corp_id, **{matched_by: value})
        if resolved:
            identity = dict(resolved)
            identity["matched_by"] = matched_by
            return identity
    return None


def _get_questionnaire_session_identity() -> dict[str, str]:
    if not has_request_context():
        return {}
    identity = session.get("questionnaire_h5_identity") or {}
    if not isinstance(identity, dict):
        return {}
    return {
        "openid": str(identity.get("openid") or "").strip(),
        "unionid": str(identity.get("unionid") or "").strip(),
        "respondent_key": str(identity.get("respondent_key") or "").strip(),
    }


def _extract_mobile_snapshot_from_validated_answers(validated_answers: list[dict[str, Any]]) -> str:
    for item in validated_answers or []:
        question = item.get("question") or {}
        if str(question.get("type") or "").strip() != "mobile":
            continue
        text_value = str(item.get("text_value") or "").strip()
        if text_value:
            return text_value
    return ""


def _build_respondent_key(identity: dict[str, Any] | None, request_meta: dict[str, Any] | None) -> str:
    meta = request_meta or {}
    explicit = str(meta.get("respondent_key") or "").strip()
    if explicit:
        return explicit
    if identity:
        for field in ["unionid", "openid", "external_userid"]:
            value = str(identity.get(field) or "").strip()
            if value:
                return value
    for field in ["unionid", "openid", "external_userid"]:
        value = str(meta.get(field) or "").strip()
        if value:
            return value
    ip = str(meta.get("ip") or "").strip()
    if ip:
        return f"ip:{ip}"
    return f"anon:{uuid4().hex}"


def has_questionnaire_submission(questionnaire_id: int, identity: dict[str, Any] | None) -> bool:
    normalized = identity or {}
    lookup_order = [
        ("external_userid", str(normalized.get("external_userid") or "").strip()),
        ("unionid", str(normalized.get("unionid") or "").strip()),
        ("openid", str(normalized.get("openid") or "").strip()),
        ("respondent_key", str(normalized.get("respondent_key") or "").strip()),
    ]
    db = get_db()
    for field, value in lookup_order:
        if not value:
            continue
        row = db.execute(
            f"""
            SELECT id
            FROM questionnaire_submissions
            WHERE questionnaire_id = ? AND {field} = ?
            LIMIT 1
            """,
            (int(questionnaire_id), value),
        ).fetchone()
        if row:
            return True
    return False


def save_questionnaire_submission(
    questionnaire: dict[str, Any],
    identity: dict[str, Any] | None,
    computed_result: dict[str, Any],
    answers: Any,
    request_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    del answers
    meta = request_meta or {}
    identity = identity or {}
    db = get_db()
    respondent_key = _build_respondent_key(identity, meta)
    openid = str(identity.get("openid") or meta.get("openid") or "").strip()
    unionid = str(identity.get("unionid") or meta.get("unionid") or "").strip()
    external_userid = str(identity.get("external_userid") or meta.get("external_userid") or "").strip()
    follow_user_userid = str(identity.get("follow_user_userid") or "").strip()
    mobile_snapshot = str(computed_result.get("mobile_snapshot") or "").strip()
    assessment_result_snapshot = computed_result.get("assessment_result") or {}
    result_token = str(computed_result.get("result_token") or "").strip()
    row = db.execute(
        """
        INSERT INTO questionnaire_submissions (
            questionnaire_id, identity_map_id, respondent_key, openid, unionid, external_userid,
            follow_user_userid, matched_by, mobile_snapshot, source_channel, campaign_id, staff_id,
            total_score, final_tags, assessment_result_snapshot, result_token, redirect_url_snapshot, submitted_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        RETURNING id, submitted_at
        """,
        (
            int(questionnaire["id"]),
            identity.get("identity_map_id"),
            respondent_key,
            openid,
            unionid,
            external_userid,
            follow_user_userid,
            str(identity.get("matched_by") or "").strip(),
            mobile_snapshot,
            str(meta.get("source_channel") or "").strip(),
            str(meta.get("campaign_id") or "").strip(),
            str(meta.get("staff_id") or "").strip(),
            float(computed_result.get("total_score") or 0),
            _json_dumps(computed_result.get("final_tags") or []),
            _json_dumps(assessment_result_snapshot),
            result_token,
            str(computed_result.get("redirect_url") or questionnaire.get("redirect_url") or "").strip(),
        ),
    ).fetchone()
    submission_id = int(row["id"])

    for item in computed_result.get("answer_snapshots") or []:
        db.execute(
            """
            INSERT INTO questionnaire_submission_answers (
                submission_id, question_id, question_type, question_title_snapshot,
                selected_option_ids, selected_option_texts_snapshot, selected_option_scores_snapshot,
                selected_option_tags_snapshot, text_value, score_contribution, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                submission_id,
                int(item["question_id"]),
                item["question_type"],
                item["question_title_snapshot"],
                _json_dumps(item.get("selected_option_ids") or []),
                _json_dumps(item.get("selected_option_texts_snapshot") or []),
                _json_dumps(item.get("selected_option_scores_snapshot") or []),
                _json_dumps(item.get("selected_option_tags_snapshot") or []),
                item.get("text_value", "") or "",
                float(item.get("score_contribution") or 0),
            ),
        )
    db.commit()
    questionnaire_logger.info(
        "questionnaire submission saved submission_id=%s total_score=%s final_tags=%s",
        submission_id,
        float(computed_result.get("total_score") or 0),
        ",".join(computed_result.get("final_tags") or []),
    )
    return {
        "id": submission_id,
        "submitted_at": row.get("submitted_at", ""),
        "questionnaire_id": int(questionnaire["id"]),
        "respondent_key": respondent_key,
        "openid": openid,
        "unionid": unionid,
        "external_userid": external_userid,
        "follow_user_userid": follow_user_userid,
        "matched_by": str(identity.get("matched_by") or "").strip(),
        "mobile_snapshot": mobile_snapshot,
        "total_score": float(computed_result.get("total_score") or 0),
        "final_tags": computed_result.get("final_tags") or [],
        "assessment_result_snapshot": assessment_result_snapshot,
        "result_token": result_token,
        "result_url": str(computed_result.get("result_url") or "").strip(),
        "redirect_url_snapshot": str(computed_result.get("redirect_url") or questionnaire.get("redirect_url") or "").strip(),
    }


def _questionnaire_submit_webhook_payload(submission: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "mobile": str((submission or {}).get("mobile_snapshot") or "").strip(),
        "userid": str((submission or {}).get("follow_user_userid") or "").strip(),
        "unionid": str((submission or {}).get("unionid") or "").strip(),
    }
    assessment_result = (submission or {}).get("assessment_result_snapshot")
    if isinstance(assessment_result, dict) and assessment_result:
        payload["assessment_result_snapshot"] = assessment_result
        payload["assessment_result_url"] = str((submission or {}).get("result_url") or "").strip()
    return payload


def _questionnaire_external_push_timeout_seconds() -> float:
    raw_value = get_setting("QUESTIONNAIRE_EXTERNAL_PUSH_TIMEOUT_SECONDS")
    if raw_value in (None, ""):
        raw_value = current_app.config.get("QUESTIONNAIRE_EXTERNAL_PUSH_TIMEOUT_SECONDS", 3)
    try:
        timeout_seconds = float(raw_value or 3)
    except (TypeError, ValueError):
        timeout_seconds = 3.0
    return max(0.5, min(timeout_seconds, 10.0))


def is_questionnaire_external_push_global_enabled() -> bool:
    raw_value = get_setting(QUESTIONNAIRE_EXTERNAL_PUSH_GLOBAL_ENABLED_KEY)
    if raw_value in (None, ""):
        raw_value = current_app.config.get(QUESTIONNAIRE_EXTERNAL_PUSH_GLOBAL_ENABLED_KEY, True)
    if raw_value in (None, ""):
        return True
    return _normalize_bool(raw_value)


def _format_iso_datetime(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    normalized = text.replace(" ", "T")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return text
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone(timedelta(hours=8)))
    return dt.isoformat()


def _questionnaire_external_push_user_id(submission: dict[str, Any]) -> str:
    for field in ["respondent_key", "external_userid", "unionid", "openid"]:
        value = str((submission or {}).get(field) or "").strip()
        if value:
            return value
    return ""


def _serialize_questionnaire_external_push_answers(answer_snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    for item in answer_snapshots or []:
        question_type = str(item.get("question_type") or "").strip()
        title = str(item.get("question_title_snapshot") or "").strip()
        if question_type == "multi_choice":
            answer_value: str | list[str] = _dedupe_strings(item.get("selected_option_texts_snapshot") or [])
        elif question_type in {"single_choice", "textarea", "mobile"}:
            if question_type == "single_choice":
                answer_value = str((_dedupe_strings(item.get("selected_option_texts_snapshot") or []) or [""])[0] or "")
            else:
                answer_value = str(item.get("text_value") or "").strip()
        else:
            continue
        serialized.append({"title": title, "answer": answer_value})
    return serialized


def _questionnaire_external_push_phone_number(answer_snapshots: list[dict[str, Any]]) -> str:
    for item in answer_snapshots or []:
        if str(item.get("question_type") or "").strip() != "mobile":
            continue
        mobile_value = str(item.get("text_value") or "").strip()
        return mobile_value or "NULL"
    return "NULL"


def _build_questionnaire_external_push_payload(
    questionnaire: dict[str, Any],
    submission: dict[str, Any],
    computed_result: dict[str, Any],
) -> dict[str, Any]:
    answer_snapshots = computed_result.get("answer_snapshots") or []
    payload: dict[str, Any] = {
        "user_id": _questionnaire_external_push_user_id(submission),
        "questionnaire_title": str(questionnaire.get("title") or questionnaire.get("name") or "").strip(),
        "submitted_at": _format_iso_datetime(submission.get("submitted_at")),
        "phone_number": _questionnaire_external_push_phone_number(answer_snapshots),
        "answers": _serialize_questionnaire_external_push_answers(answer_snapshots),
    }
    if questionnaire.get("external_push_day") not in (None, ""):
        payload["day"] = int(questionnaire["external_push_day"])
    if questionnaire.get("external_push_frequency") not in (None, ""):
        payload["frequency"] = int(questionnaire["external_push_frequency"])
    remark = str(questionnaire.get("external_push_remark") or "").strip()
    if remark:
        payload["remark"] = remark
    assessment_result = computed_result.get("assessment_result")
    if isinstance(assessment_result, dict) and assessment_result:
        payload["assessment_result_snapshot"] = assessment_result
    for item in _normalize_questionnaire_external_push_custom_params(questionnaire.get("external_push_custom_params")):
        payload[item["name"]] = item["value"]
    return payload


def _execute_questionnaire_external_push_request(
    *,
    target_url: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    normalized_target_url = str(target_url or "").strip()
    if not normalized_target_url:
        return {
            "ok": False,
            "attempted": False,
            "response_status_code": None,
            "response_body": "",
            "failure_reason": "external push url is empty",
        }
    from ...infra.http_client import OutboundHttpError, get_outbound_client

    # Questionnaire pushes are user-driven and admin-retriable from the
    # console; we want the breaker (so a stuck upstream doesn't pile up new
    # requests) but not in-call retries (which would hide the original
    # failure response from the persisted log).
    client = get_outbound_client(
        "questionnaire_external_push",
        timeout=_questionnaire_external_push_timeout_seconds(),
        retry_max=0,
    )
    try:
        response = client.post(
            normalized_target_url,
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        response_body = (response.text or "")[:5000]
        if int(response.status_code) == 200:
            return {
                "ok": True,
                "attempted": True,
                "response_status_code": int(response.status_code),
                "response_body": response_body,
                "failure_reason": "",
            }
        return {
            "ok": False,
            "attempted": True,
            "response_status_code": int(response.status_code),
            "response_body": response_body,
            "failure_reason": f"HTTP {int(response.status_code)}",
        }
    except OutboundHttpError as exc:
        # The shared client already retried & breaker-counted. Translate to
        # the legacy result shape so callers' downstream logging keeps
        # working unchanged. Preserve the upstream body for ``http_status``
        # so the persisted log row still contains the original error text.
        category = exc.category
        if category == "timeout":
            failure_reason = "request timeout"
        elif category == "circuit_open":
            failure_reason = f"circuit_open: {exc}"
        elif category == "http_status":
            failure_reason = f"HTTP {exc.status_code}"
        else:
            failure_reason = f"network error: {exc}"
        return {
            "ok": False,
            "attempted": True,
            "response_status_code": exc.status_code,
            "response_body": (exc.response_text or "")[:5000],
            "failure_reason": failure_reason,
        }
    except Exception as exc:
        questionnaire_logger.exception("questionnaire external push internal failure")
        return {
            "ok": False,
            "attempted": True,
            "response_status_code": None,
            "response_body": "",
            "failure_reason": f"internal error: {str(exc).strip() or exc.__class__.__name__}",
        }


def _deliver_questionnaire_external_push(
    questionnaire: dict[str, Any],
    submission: dict[str, Any],
    computed_result: dict[str, Any],
) -> dict[str, Any]:
    if not _normalize_bool(questionnaire.get("external_push_enabled")):
        return {"enabled": False, "attempted": False, "reason": "external_push_disabled"}

    target_url = str(questionnaire.get("external_push_url") or "").strip()
    payload = _build_questionnaire_external_push_payload(questionnaire, submission, computed_result)
    questionnaire_id = int(questionnaire["id"])
    submission_record_id = int(submission["id"])
    questionnaire_title_snapshot = str(questionnaire.get("title") or questionnaire.get("name") or "").strip()
    user_id = str(payload.get("user_id") or "").strip()
    if not is_questionnaire_external_push_global_enabled():
        log_row = _safe_create_questionnaire_external_push_log(
            questionnaire_id=questionnaire_id,
            questionnaire_title_snapshot=questionnaire_title_snapshot,
            submission_record_id=submission_record_id,
            user_id=user_id,
            target_url=target_url,
            request_payload=payload,
            response_status_code=None,
            response_body="",
            status=QUESTIONNAIRE_EXTERNAL_PUSH_STATUS_SKIPPED,
            failure_reason=QUESTIONNAIRE_EXTERNAL_PUSH_GLOBAL_DISABLED_REASON,
        )
        questionnaire_logger.warning(
            "questionnaire external push skipped by global switch submission_id=%s questionnaire_id=%s",
            submission_record_id,
            questionnaire_id,
        )
        return {
            "enabled": True,
            "attempted": False,
            "ok": False,
            "reason": "global_switch_disabled",
            "log": log_row,
            "skipped": True,
        }
    result = _execute_questionnaire_external_push_request(target_url=target_url, payload=payload)
    log_row = _safe_create_questionnaire_external_push_log(
        questionnaire_id=questionnaire_id,
        questionnaire_title_snapshot=questionnaire_title_snapshot,
        submission_record_id=submission_record_id,
        user_id=user_id,
        target_url=target_url,
        request_payload=payload,
        response_status_code=result.get("response_status_code"),
        response_body=str(result.get("response_body") or ""),
        status=QUESTIONNAIRE_EXTERNAL_PUSH_STATUS_SUCCESS if result.get("ok") else QUESTIONNAIRE_EXTERNAL_PUSH_STATUS_FAILED,
        failure_reason=str(result.get("failure_reason") or ""),
    )
    if result.get("ok"):
        questionnaire_logger.info(
            "questionnaire external push success submission_id=%s questionnaire_id=%s status_code=%s",
            submission_record_id,
            questionnaire_id,
            result.get("response_status_code"),
        )
    elif not result.get("attempted"):
        questionnaire_logger.warning(
            "questionnaire external push skipped submission_id=%s questionnaire_id=%s reason=empty_url",
            submission_record_id,
            questionnaire_id,
        )
    else:
        questionnaire_logger.warning(
            "questionnaire external push failed submission_id=%s questionnaire_id=%s reason=%s",
            submission_record_id,
            questionnaire_id,
            result.get("failure_reason"),
        )
    return {
        "enabled": True,
        "attempted": bool(result.get("attempted")),
        "ok": bool(result.get("ok")),
        "reason": str(result.get("failure_reason") or ("empty_url" if not result.get("attempted") else "")).strip(),
        "log": log_row,
    }


def retry_questionnaire_external_push_log(push_log_id: int) -> dict[str, Any]:
    source_log = _get_questionnaire_external_push_log(int(push_log_id))
    if not source_log:
        raise LookupError("questionnaire external push log not found")
    if str(source_log.get("status") or "").strip() != QUESTIONNAIRE_EXTERNAL_PUSH_STATUS_FAILED:
        raise ValueError("only failed external push logs can be retried")

    payload = _json_loads(source_log.get("request_payload"), default={})
    if not isinstance(payload, dict):
        payload = {}
    root_log_id = int(source_log.get("retry_from_log_id") or source_log.get("id") or 0)
    retry_attempt = _count_questionnaire_external_push_retry_logs(root_log_id) + 1
    result = _execute_questionnaire_external_push_request(
        target_url=str(source_log.get("target_url") or "").strip(),
        payload=payload,
    )
    log_row = _safe_create_questionnaire_external_push_log(
        questionnaire_id=int(source_log.get("questionnaire_id") or 0),
        questionnaire_title_snapshot=str(source_log.get("questionnaire_title_snapshot") or "").strip(),
        submission_record_id=int(source_log.get("submission_record_id") or 0),
        retry_from_log_id=root_log_id,
        retry_attempt=retry_attempt,
        user_id=str(source_log.get("user_id") or "").strip(),
        target_url=str(source_log.get("target_url") or "").strip(),
        request_payload=payload,
        response_status_code=result.get("response_status_code"),
        response_body=str(result.get("response_body") or ""),
        status=QUESTIONNAIRE_EXTERNAL_PUSH_STATUS_SUCCESS if result.get("ok") else QUESTIONNAIRE_EXTERNAL_PUSH_STATUS_FAILED,
        failure_reason=str(result.get("failure_reason") or ""),
    )
    return {
        "ok": bool(result.get("ok")),
        "attempted": bool(result.get("attempted")),
        "reason": str(result.get("failure_reason") or "").strip(),
        "source_log": source_log,
        "log": log_row,
    }


def retry_questionnaire_external_push_logs(push_log_ids: list[int]) -> dict[str, Any]:
    normalized_ids: list[int] = []
    seen: set[int] = set()
    for value in push_log_ids or []:
        try:
            normalized_value = int(value)
        except (TypeError, ValueError):
            continue
        if normalized_value <= 0 or normalized_value in seen:
            continue
        seen.add(normalized_value)
        normalized_ids.append(normalized_value)
    result = {
        "selected_count": len(normalized_ids),
        "retried_count": 0,
        "success_count": 0,
        "failed_count": 0,
        "skipped_count": 0,
        "items": [],
    }
    for push_log_id in normalized_ids:
        try:
            item = retry_questionnaire_external_push_log(push_log_id)
            result["retried_count"] += 1
            if item.get("ok"):
                result["success_count"] += 1
            else:
                result["failed_count"] += 1
            result["items"].append({"push_log_id": push_log_id, **item, "skipped": False})
        except Exception as exc:
            result["skipped_count"] += 1
            result["items"].append(
                {
                    "push_log_id": push_log_id,
                    "ok": False,
                    "attempted": False,
                    "reason": str(exc).strip() or exc.__class__.__name__,
                    "skipped": True,
                }
            )
    return result


def _fire_questionnaire_submit_webhook(submission: dict[str, Any]) -> dict[str, Any]:
    payload = _questionnaire_submit_webhook_payload(submission)
    result = send_outbound_webhook(
        event_type=EVENT_QUESTIONNAIRE_SUBMIT,
        payload=payload,
        source_key="submission_id",
        source_id=str(submission.get("id") or ""),
    )
    delivery = dict(result.get("delivery") or {})
    return {
        "sent": bool(result.get("sent")),
        "ok": bool(result.get("ok")),
        "reason": str(result.get("reason") or "").strip(),
        "status_code": delivery.get("response_status_code"),
        "delivery": delivery,
        "payload": payload,
    }


def apply_questionnaire_mobile_binding(submission: dict[str, Any]) -> dict[str, Any]:
    mobile_snapshot = str((submission or {}).get("mobile_snapshot") or "").strip()
    external_userid = str((submission or {}).get("external_userid") or "").strip()
    follow_user_userid = str((submission or {}).get("follow_user_userid") or "").strip()
    if not mobile_snapshot:
        return {"bound": False, "reason": "no_mobile_snapshot"}
    if not external_userid:
        return {"bound": False, "reason": "no_external_userid"}
    try:
        binding = _bind_questionnaire_identity(
            external_userid=external_userid,
            owner_userid=follow_user_userid,
            bind_by_userid="questionnaire_submit",
            mobile=mobile_snapshot,
            force_rebind=True,
        )
        resolved_identity = _resolve_questionnaire_person_identity(external_userid=external_userid)
        questionnaire_logger.info(
            "questionnaire mobile bound submission_id=%s external_userid=%s mobile=%s person_id=%s",
            int(submission.get("id") or 0),
            external_userid,
            mobile_snapshot,
            str((resolved_identity or {}).get("person_id") or (binding or {}).get("person_id") or ""),
        )
        return {"bound": True, "binding": binding}
    except Exception as exc:
        questionnaire_logger.exception(
            "questionnaire mobile bind failed submission_id=%s external_userid=%s",
            int(submission.get("id") or 0),
            external_userid,
        )
        return {"bound": False, "reason": "bind_failed", "error": str(exc)}


def _log_questionnaire_scrm_apply(
    submission_id: int,
    *,
    questionnaire_id: int = 0,
    openid: str = "",
    unionid: str = "",
    external_userid: str,
    follow_user_userid: str,
    final_tags: list[str],
    status: str,
    error_message: str = "",
    matched_score_tier_id: str = "",
    matched_score_tier_name: str = "",
    matched_dimension_categories: list[dict[str, Any]] | None = None,
    add_tag_ids: list[str] | None = None,
    wecom_response: Any = None,
) -> None:
    get_db().execute(
        """
        INSERT INTO questionnaire_scrm_apply_logs (
            submission_id, questionnaire_id, openid, unionid, external_userid, follow_user_userid,
            final_tags, matched_score_tier_id, matched_score_tier_name, matched_dimension_categories,
            add_tag_ids, status, error_message, wecom_response, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (
            int(submission_id),
            int(questionnaire_id or 0),
            openid,
            unionid,
            external_userid,
            follow_user_userid,
            _json_dumps(final_tags),
            matched_score_tier_id,
            matched_score_tier_name,
            _json_dumps(matched_dimension_categories or []),
            _json_dumps(add_tag_ids if add_tag_ids is not None else final_tags),
            status,
            error_message,
            _json_dumps(wecom_response if isinstance(wecom_response, (dict, list)) else {}),
        ),
    )
    get_db().commit()


def apply_questionnaire_submission_tags_to_scrm(submission_id: int) -> dict[str, Any]:
    submission = get_db().execute(
        """
        SELECT id, questionnaire_id, openid, unionid, external_userid, follow_user_userid,
               final_tags, assessment_result_snapshot
        FROM questionnaire_submissions
        WHERE id = ?
        """,
        (int(submission_id),),
    ).fetchone()
    if not submission:
        return {"applied": False, "reason": "submission_not_found"}

    external_userid = str(submission.get("external_userid") or "").strip()
    follow_user_userid = str(submission.get("follow_user_userid") or "").strip()
    final_tags = _dedupe_strings(_json_array(submission.get("final_tags")))
    assessment_result = _normalize_questionnaire_assessment_config(submission.get("assessment_result_snapshot"))
    tag_plan = assessment_result.get("tag_plan") if isinstance(assessment_result.get("tag_plan"), dict) else {}
    log_context = {
        "questionnaire_id": int(submission.get("questionnaire_id") or 0),
        "openid": str(submission.get("openid") or "").strip(),
        "unionid": str(submission.get("unionid") or "").strip(),
        "external_userid": external_userid,
        "follow_user_userid": follow_user_userid,
        "final_tags": final_tags,
        "matched_score_tier_id": str(tag_plan.get("matched_score_tier_id") or "").strip(),
        "matched_score_tier_name": str(tag_plan.get("matched_score_tier_name") or "").strip(),
        "matched_dimension_categories": tag_plan.get("matched_dimension_categories") if isinstance(tag_plan.get("matched_dimension_categories"), list) else [],
        "add_tag_ids": final_tags,
    }
    if not external_userid:
        _log_questionnaire_scrm_apply(
            submission_id,
            **log_context,
            status="identity_unresolved",
            error_message="external_userid 未解析，已跳过企微打标签",
        )
        questionnaire_logger.info("questionnaire scrm skip submission_id=%s reason=no_external_userid", submission_id)
        return {"applied": False, "reason": "no_external_userid"}

    if not follow_user_userid:
        _log_questionnaire_scrm_apply(
            submission_id,
            **log_context,
            status="identity_unresolved",
            error_message="follow_user_userid 未解析，已跳过企微打标签",
        )
        questionnaire_logger.info("questionnaire scrm skip submission_id=%s reason=no_follow_user_userid", submission_id)
        return {"applied": False, "reason": "no_follow_user_userid"}

    if not final_tags:
        _log_questionnaire_scrm_apply(
            submission_id,
            **log_context,
            status="skipped_no_tags",
            error_message="本次命中的维度分类和总分分层没有配置标签",
        )
        questionnaire_logger.info("questionnaire scrm skip submission_id=%s reason=no_final_tags", submission_id)
        return {"applied": False, "reason": "no_final_tags"}

    try:
        from ...wecom_client import WeComClient

        client = WeComClient.from_app()
        result = client.mark_external_contact_tags(
            external_userid=external_userid,
            follow_user_userid=follow_user_userid,
            add_tags=final_tags,
            remove_tags=None,
        )
        tags_repo.save_tag_snapshot(follow_user_userid, external_userid, final_tags)
        _log_questionnaire_scrm_apply(
            submission_id,
            **log_context,
            status="success",
            wecom_response=result,
        )
        questionnaire_logger.info(
            "questionnaire scrm applied submission_id=%s external_userid=%s follow_user_userid=%s tags=%s",
            submission_id,
            external_userid,
            follow_user_userid,
            ",".join(final_tags),
        )
        return {"applied": True, "result": result}
    except Exception as exc:
        status = "wecom_not_configured" if "not configured" in str(exc).lower() or "is not configured" in str(exc).lower() else "failed"
        _log_questionnaire_scrm_apply(
            submission_id,
            **log_context,
            status=status,
            error_message=str(exc),
        )
        questionnaire_logger.exception(
            "questionnaire scrm apply failed submission_id=%s external_userid=%s follow_user_userid=%s",
            submission_id,
            external_userid,
            follow_user_userid,
        )
        return {"applied": False, "reason": "wecom_error", "error": str(exc)}


def submit_questionnaire(slug: str, payload: dict[str, Any], request_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    slug_value = str(slug or "").strip()
    row = _get_questionnaire_row_by_slug(slug_value, require_enabled=True)
    if not row:
        raise LookupError("questionnaire not found")
    questionnaire = _build_questionnaire_detail(row)

    answers = payload.get("answers")
    if answers is None:
        raise ValueError("answers is required")

    submit_meta = dict(request_meta or {})
    session_identity = _get_questionnaire_session_identity()
    for field in ["source_channel", "campaign_id", "staff_id"]:
        if field in payload and payload.get(field) is not None:
            submit_meta[field] = payload.get(field)
    submit_meta["respondent_key"] = session_identity.get("respondent_key") or str(payload.get("respondent_key") or "").strip()
    submit_meta["openid"] = session_identity.get("openid") or str(payload.get("openid") or "").strip()
    submit_meta["unionid"] = session_identity.get("unionid") or str(payload.get("unionid") or "").strip()
    submit_meta["external_userid"] = str(payload.get("external_userid") or "").strip()

    resolved_unionid = submit_meta["unionid"]
    resolved_openid = submit_meta["openid"]
    payload_external_userid = submit_meta["external_userid"]

    identity = resolve_questionnaire_submit_identity(
        openid=resolved_openid,
        unionid=resolved_unionid,
        external_userid=payload_external_userid,
    )
    if identity and identity.get("matched_by") == "unionid" and resolved_openid and not str(identity.get("openid") or "").strip():
        corp_id = str(current_app.config.get("WECOM_CORP_ID", "") or "").strip()
        rebound = _bind_questionnaire_identity(
            corp_id=corp_id,
            external_userid=str(identity.get("external_userid") or "").strip(),
            openid=resolved_openid,
            unionid=resolved_unionid,
        )
        if rebound:
            identity = dict(rebound)
            identity["matched_by"] = "unionid"
    if identity:
        identity["openid"] = str(identity.get("openid") or resolved_openid or "").strip()
        identity["unionid"] = str(identity.get("unionid") or resolved_unionid or "").strip()

    questionnaire_logger.info(
        "questionnaire identity resolved slug=%s questionnaire_id=%s matched_by=%s identity_map_id=%s external_userid=%s follow_user_userid=%s",
        slug_value,
        int(questionnaire["id"]),
        str((identity or {}).get("matched_by") or ""),
        str((identity or {}).get("identity_map_id") or ""),
        str((identity or {}).get("external_userid") or ""),
        str((identity or {}).get("follow_user_userid") or ""),
    )

    duplicate_identity = {
        "external_userid": str((identity or {}).get("external_userid") or payload_external_userid or "").strip(),
        "unionid": str((identity or {}).get("unionid") or resolved_unionid or "").strip(),
        "openid": str((identity or {}).get("openid") or resolved_openid or "").strip(),
        "respondent_key": str(submit_meta.get("respondent_key") or "").strip(),
    }
    has_strict_identity = any(str(duplicate_identity.get(field) or "").strip() for field in ["external_userid", "unionid", "openid", "respondent_key"])
    if has_strict_identity and has_questionnaire_submission(int(questionnaire["id"]), duplicate_identity):
        raise QuestionnaireAlreadySubmittedError("已经提交")
    if not has_strict_identity:
        questionnaire_logger.info(
            "questionnaire duplicate guard identity_unresolved slug=%s questionnaire_id=%s",
            slug_value,
            int(questionnaire["id"]),
        )

    validated_answers = validate_questionnaire_answers(questionnaire, answers)
    computed_result = compute_questionnaire_submission_outcome(questionnaire, validated_answers)
    computed_result["mobile_snapshot"] = _extract_mobile_snapshot_from_validated_answers(
        computed_result.get("validated_answers") or validated_answers
    )
    submission = save_questionnaire_submission(
        questionnaire,
        identity,
        computed_result,
        answers,
        request_meta=submit_meta,
    )
    apply_questionnaire_mobile_binding(submission)
    apply_questionnaire_submission_tags_to_scrm(submission["id"])
    try:
        from ..automation_conversion.service import sync_member_from_questionnaire_submission

        sync_member_from_questionnaire_submission(
            external_contact_id=str(submission.get("external_userid") or "").strip(),
            phone=str(submission.get("mobile_snapshot") or "").strip(),
            operator_id="questionnaire_submit",
        )
    except Exception:
        questionnaire_logger.exception(
            "automation conversion sync failed after questionnaire submit submission_id=%s",
            submission.get("id"),
        )
    _fire_questionnaire_submit_webhook(submission)
    _deliver_questionnaire_external_push(questionnaire, submission, computed_result)
    return {
        "success": True,
        "redirect_url": submission.get("result_url") or computed_result.get("redirect_url", "") or "",
        "result_url": submission.get("result_url", "") or "",
        "message": "已收到提交",
    }
