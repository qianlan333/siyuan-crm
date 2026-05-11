"""Helpers for questionnaire/service.py (阶段 7.2).

Extracted from service.py — line 51-629 helper region. Module-level
imports complete copy (heavy import header) so helpers can call any
application command/query / Flask util / outbound_webhook service.

Note: tests only monkeypatch ``service.requests`` and ``service.domains``
module attributes (not datetime). Helpers in this file do NOT call
``requests.*`` directly (verified) — only main service.py uses requests
for external push, so the requests.post monkeypatch keeps working.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import requests
from flask import current_app, has_request_context, session

from ...application.identity_contact.commands import BindExternalContactIdentityCommand
from ...application.identity_contact.dto import (
    BindExternalContactIdentityCommandDTO,
    ResolveExternalContactIdentityQueryDTO,
    ResolvePersonIdentityQueryDTO,
)
from ...application.identity_contact.queries import (
    ResolveExternalContactIdentityQuery,
    ResolvePersonIdentityQuery,
)
from ...db import get_db
from ...infra.settings import get_setting
from ..outbound_webhook.service import EVENT_QUESTIONNAIRE_SUBMIT, send_outbound_webhook
from ..tags import repo as tags_repo

questionnaire_logger = logging.getLogger("questionnaire")
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


def _resolve_external_contact_identity_payload(
    *,
    corp_id: str = "",
    unionid: str = "",
    openid: str = "",
    external_userid: str = "",
) -> dict[str, Any] | None:
    return ResolveExternalContactIdentityQuery()(
        ResolveExternalContactIdentityQueryDTO(
            corp_id=str(corp_id or "").strip(),
            unionid=str(unionid or "").strip(),
            openid=str(openid or "").strip(),
            external_userid=str(external_userid or "").strip(),
        )
    )


def _resolve_questionnaire_person_identity(
    *,
    external_userid: str = "",
    mobile: str = "",
    unionid: str = "",
) -> dict[str, Any]:
    return ResolvePersonIdentityQuery()(
        ResolvePersonIdentityQueryDTO(
            external_userid=str(external_userid or "").strip(),
            mobile=str(mobile or "").strip(),
            unionid=str(unionid or "").strip(),
        )
    )


def _bind_questionnaire_identity(
    *,
    external_userid: str,
    owner_userid: str = "",
    bind_by_userid: str = "",
    mobile: str = "",
    openid: str = "",
    unionid: str = "",
    force_rebind: bool = False,
    corp_id: str = "",
) -> dict[str, Any] | None:
    return BindExternalContactIdentityCommand()(
        BindExternalContactIdentityCommandDTO(
            external_userid=str(external_userid or "").strip(),
            owner_userid=str(owner_userid or "").strip(),
            bind_by_userid=str(bind_by_userid or "").strip(),
            mobile=str(mobile or "").strip(),
            openid=str(openid or "").strip(),
            unionid=str(unionid or "").strip(),
            force_rebind=bool(force_rebind),
            corp_id=str(corp_id or "").strip(),
        )
    )


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _json_loads(value: Any, *, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    text = str(value or "").strip()
    if not text:
        return default
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default
    return parsed


def _json_array(value: Any) -> list[Any]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _dedupe_strings(values: list[Any]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        deduped.append(text)
    return deduped


def _normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _normalize_float(value: Any, field_name: str, *, allow_none: bool = False) -> float | None:
    if value in (None, ""):
        if allow_none:
            return None
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a number") from exc


def _normalize_int(value: Any, default: int) -> int:
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("sort_order must be an integer") from exc


def _normalize_required_integer(value: Any, field_name: str, *, allow_none: bool = False) -> int | None:
    if value in (None, ""):
        if allow_none:
            return None
        return 0
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer") from exc


def _validate_tag_codes_payload(value: Any, field_name: str) -> list[str]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be an array")
    return _dedupe_strings(value)


def _slugify_questionnaire(value: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not base:
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        suffix = uuid4().hex[:6]
        base = f"q-{timestamp}-{suffix}"
    return base[:120]


def _questionnaire_exists_by_slug(slug: str, *, exclude_id: int | None = None) -> bool:
    sql = "SELECT id FROM questionnaires WHERE slug = ?"
    params: list[Any] = [slug]
    if exclude_id is not None:
        sql += " AND id <> ?"
        params.append(int(exclude_id))
    row = get_db().execute(sql, tuple(params)).fetchone()
    return row is not None


def _dedupe_questionnaire_slug(slug: str, *, exclude_id: int | None = None) -> str:
    candidate = _slugify_questionnaire(slug)
    if not _questionnaire_exists_by_slug(candidate, exclude_id=exclude_id):
        return candidate

    while True:
        suffix = uuid4().hex[:6]
        prefix = candidate[: max(120 - len(suffix) - 1, 1)].rstrip("-")
        fallback_prefix = datetime.utcnow().strftime("q-%Y%m%d%H%M%S")
        deduped = f"{prefix or fallback_prefix}-{suffix}"[:120]
        if not _questionnaire_exists_by_slug(deduped, exclude_id=exclude_id):
            return deduped


def _normalize_tag_codes(value: Any) -> list[str]:
    # The questionnaire schema keeps the historical field name `tag_codes`,
    # but values are treated end-to-end as the exact WeCom tag identifiers
    # accepted by externalcontact/mark_tag.
    if isinstance(value, str):
        candidate = value.strip()
        if candidate.startswith("[") and candidate.endswith("]"):
            return _dedupe_strings(_json_array(candidate))
        if "/" in candidate:
            return _dedupe_strings(candidate.split("/"))
        if "," in candidate:
            return _dedupe_strings(candidate.split(","))
        return _dedupe_strings([candidate])
    if isinstance(value, (list, tuple)):
        return _dedupe_strings(list(value))
    return []


def _normalize_questionnaire_external_push_custom_params(value: Any) -> list[dict[str, str]]:
    if value in (None, ""):
        return []
    raw_items = _json_loads(value, default=[]) if isinstance(value, str) else value
    if raw_items in (None, ""):
        return []
    if not isinstance(raw_items, list):
        raise ValueError("external_push_custom_params must be an array")

    normalized: list[dict[str, str]] = []
    seen_names: set[str] = set()
    for item in raw_items:
        if not isinstance(item, dict):
            raise ValueError("external_push_custom_params item must be an object")
        name = str(item.get("name") or item.get("key") or "").strip()
        param_value = str(item.get("value") or item.get("detail") or "").strip()
        if not name and not param_value:
            continue
        if not name:
            raise ValueError("external_push_custom_params name is required")
        if name in QUESTIONNAIRE_EXTERNAL_PUSH_RESERVED_KEYS:
            raise ValueError(f"external_push_custom_params name '{name}' is reserved")
        if name in seen_names:
            raise ValueError(f"external_push_custom_params name '{name}' is duplicated")
        seen_names.add(name)
        normalized.append({"name": name, "value": param_value})
    return normalized


def _normalize_questionnaire_payload(
    payload: dict[str, Any],
    *,
    questionnaire_id: int | None = None,
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    raw_slug = payload.get("slug")
    has_explicit_slug = raw_slug not in (None, "")
    name = str(payload.get("name") or "").strip()
    title = str(payload.get("title") or "").strip()
    description = str(payload.get("description") or "").strip()
    redirect_url = str(payload.get("redirect_url") or "").strip()
    external_push_enabled = _normalize_bool(
        payload.get("external_push_enabled", (existing or {}).get("external_push_enabled"))
    )
    external_push_url = str(payload.get("external_push_url") or "").strip()
    external_push_day = _normalize_required_integer(
        payload.get("external_push_day", (existing or {}).get("external_push_day")),
        "external_push_day",
        allow_none=True,
    )
    external_push_frequency = _normalize_required_integer(
        payload.get("external_push_frequency", (existing or {}).get("external_push_frequency")),
        "external_push_frequency",
        allow_none=True,
    )
    external_push_remark = str(
        payload.get("external_push_remark", (existing or {}).get("external_push_remark")) or ""
    ).strip()
    external_push_custom_params = _normalize_questionnaire_external_push_custom_params(
        payload.get("external_push_custom_params", (existing or {}).get("external_push_custom_params"))
    )
    slug_source = str(raw_slug or (existing or {}).get("slug") or name or title).strip()
    slug = _slugify_questionnaire(slug_source)

    if not name:
        raise ValueError("name is required")
    if not title:
        raise ValueError("title is required")
    if external_push_enabled and not external_push_url:
        raise ValueError("external_push_url is required when external_push_enabled is enabled")
    if _questionnaire_exists_by_slug(slug, exclude_id=questionnaire_id):
        if has_explicit_slug:
            raise ValueError("slug already exists")
        slug = _dedupe_questionnaire_slug(slug_source, exclude_id=questionnaire_id)

    raw_questions = payload.get("questions", [])
    if raw_questions is None:
        raw_questions = []
    if not isinstance(raw_questions, list):
        raise ValueError("questions must be an array")

    normalized_questions: list[dict[str, Any]] = []
    for index, item in enumerate(raw_questions, start=1):
        if not isinstance(item, dict):
            raise ValueError("question must be an object")
        question_type = str(item.get("type") or "").strip()
        if question_type not in QUESTIONNAIRE_TYPES:
            raise ValueError("question type must be single_choice, multi_choice, textarea or mobile")
        question_title = str(item.get("title") or "").strip()
        if not question_title:
            raise ValueError("question title is required")
        question_payload = {
            "id": int(item["id"]) if item.get("id") not in (None, "") else None,
            "type": question_type,
            "title": question_title,
            "placeholder_text": "",
            "required": _normalize_bool(item.get("required")),
            "sort_order": _normalize_int(item.get("sort_order"), index),
            "options": [],
        }
        if question_type in {"textarea", "mobile"}:
            question_payload["placeholder_text"] = str(item.get("placeholder_text") or "").strip()
        raw_options = item.get("options") or []
        if question_type in {"single_choice", "multi_choice"}:
            if not isinstance(raw_options, list) or not raw_options:
                raise ValueError(f"question '{question_title}' must have options")
            normalized_options: list[dict[str, Any]] = []
            for option_index, option in enumerate(raw_options, start=1):
                if not isinstance(option, dict):
                    raise ValueError("option must be an object")
                option_text = str(option.get("option_text") or "").strip()
                if not option_text:
                    raise ValueError(f"question '{question_title}' has an empty option_text")
                normalized_options.append(
                    {
                        "id": int(option["id"]) if option.get("id") not in (None, "") else None,
                        "option_text": option_text,
                        "score": _normalize_required_integer(option.get("score"), "score"),
                        "tag_codes": _validate_tag_codes_payload(option.get("tag_codes"), "tag_codes"),
                        "sort_order": _normalize_int(option.get("sort_order"), option_index),
                    }
                )
            question_payload["options"] = normalized_options
        normalized_questions.append(question_payload)

    raw_score_rules = payload.get("score_rules") or []
    if not isinstance(raw_score_rules, list):
        raise ValueError("score_rules must be an array")
    normalized_score_rules: list[dict[str, Any]] = []
    for index, item in enumerate(raw_score_rules, start=1):
        if not isinstance(item, dict):
            raise ValueError("score rule must be an object")
        min_score = _normalize_required_integer(item.get("min_score"), "min_score", allow_none=True)
        max_score = _normalize_required_integer(item.get("max_score"), "max_score", allow_none=True)
        if min_score is None and max_score is None:
            raise ValueError("score rule must have min_score or max_score")
        if min_score is not None and max_score is not None and min_score > max_score:
            raise ValueError("score rule min_score cannot be greater than max_score")
        tag_codes = _validate_tag_codes_payload(item.get("tag_codes"), "tag_codes")
        if not tag_codes:
            raise ValueError("score rule tag_codes cannot be empty")
        normalized_score_rules.append(
            {
                "id": int(item["id"]) if item.get("id") not in (None, "") else None,
                "min_score": min_score,
                "max_score": max_score,
                "tag_codes": tag_codes,
                "sort_order": _normalize_int(item.get("sort_order"), index),
            }
        )

    return {
        "slug": slug,
        "name": name,
        "title": title,
        "description": description,
        "is_disabled": _normalize_bool(payload.get("is_disabled", (existing or {}).get("is_disabled"))),
        "redirect_url": redirect_url,
        "external_push_enabled": external_push_enabled,
        "external_push_url": external_push_url,
        "external_push_day": external_push_day,
        "external_push_frequency": external_push_frequency,
        "external_push_remark": external_push_remark,
        "external_push_custom_params": external_push_custom_params,
        "questions": normalized_questions,
        "score_rules": normalized_score_rules,
    }


def _get_questionnaire_row(questionnaire_id: int) -> dict[str, Any] | None:
    return get_db().execute(
        """
        SELECT id, slug, name, title, description, is_disabled, redirect_url,
               external_push_enabled, external_push_url, external_push_day, external_push_frequency,
               external_push_remark, external_push_custom_params, created_at, updated_at
        FROM questionnaires
        WHERE id = ?
        """,
        (int(questionnaire_id),),
    ).fetchone()


def _serialize_questionnaire_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "slug": row.get("slug", ""),
        "name": row.get("name", ""),
        "title": row.get("title", ""),
        "description": row.get("description", "") or "",
        "is_disabled": _normalize_bool(row.get("is_disabled")),
        "redirect_url": row.get("redirect_url", "") or "",
        "external_push_enabled": _normalize_bool(row.get("external_push_enabled")),
        "external_push_url": row.get("external_push_url", "") or "",
        "external_push_day": int(row["external_push_day"]) if row.get("external_push_day") is not None else "",
        "external_push_frequency": int(row["external_push_frequency"])
        if row.get("external_push_frequency") is not None
        else "",
        "external_push_remark": row.get("external_push_remark", "") or "",
        "external_push_custom_params": _normalize_questionnaire_external_push_custom_params(
            row.get("external_push_custom_params")
        ),
        "created_at": row.get("created_at", ""),
        "updated_at": row.get("updated_at", ""),
    }


def _load_questionnaire_questions(questionnaire_id: int) -> list[dict[str, Any]]:
    question_rows = get_db().execute(
        """
        SELECT id, questionnaire_id, type, title, placeholder_text, required, sort_order, created_at, updated_at
        FROM questionnaire_questions
        WHERE questionnaire_id = ?
        ORDER BY sort_order ASC, id ASC
        """,
        (int(questionnaire_id),),
    ).fetchall()
    if not question_rows:
        return []
    question_ids = [int(row["id"]) for row in question_rows]
    placeholders = ",".join("?" for _ in question_ids)
    option_rows = get_db().execute(
        f"""
        SELECT id, question_id, option_text, score, tag_codes, sort_order, created_at, updated_at
        FROM questionnaire_options
        WHERE question_id IN ({placeholders})
        ORDER BY sort_order ASC, id ASC
        """,
        tuple(question_ids),
    ).fetchall()
    options_by_question: dict[int, list[dict[str, Any]]] = {}
    for row in option_rows:
        options_by_question.setdefault(int(row["question_id"]), []).append(
            {
                "id": int(row["id"]),
                "question_id": int(row["question_id"]),
                "option_text": row.get("option_text", ""),
                "score": float(row.get("score") or 0),
                "tag_codes": _normalize_tag_codes(row.get("tag_codes")),
                "sort_order": int(row.get("sort_order") or 0),
                "created_at": row.get("created_at", ""),
                "updated_at": row.get("updated_at", ""),
            }
        )
    return [
        {
            "id": int(row["id"]),
            "questionnaire_id": int(row["questionnaire_id"]),
            "type": row.get("type", ""),
            "title": row.get("title", ""),
            "placeholder_text": row.get("placeholder_text", "") or "",
            "required": _normalize_bool(row.get("required")),
            "sort_order": int(row.get("sort_order") or 0),
            "created_at": row.get("created_at", ""),
            "updated_at": row.get("updated_at", ""),
            "options": options_by_question.get(int(row["id"]), []),
        }
        for row in question_rows
    ]


def _load_questionnaire_score_rules(questionnaire_id: int) -> list[dict[str, Any]]:
    rows = get_db().execute(
        """
        SELECT id, questionnaire_id, min_score, max_score, tag_codes, sort_order, created_at, updated_at
        FROM questionnaire_score_rules
        WHERE questionnaire_id = ?
        ORDER BY sort_order ASC, id ASC
        """,
        (int(questionnaire_id),),
    ).fetchall()
    return [
        {
            "id": int(row["id"]),
            "questionnaire_id": int(row["questionnaire_id"]),
            "min_score": float(row["min_score"]) if row.get("min_score") is not None else None,
            "max_score": float(row["max_score"]) if row.get("max_score") is not None else None,
            "tag_codes": _normalize_tag_codes(row.get("tag_codes")),
            "sort_order": int(row.get("sort_order") or 0),
            "created_at": row.get("created_at", ""),
            "updated_at": row.get("updated_at", ""),
        }
        for row in rows
    ]


def _questionnaire_submission_stats(questionnaire_id: int) -> dict[str, Any]:
    row = get_db().execute(
        """
        SELECT COUNT(*) AS submission_count, MAX(submitted_at) AS last_submitted_at
        FROM questionnaire_submissions
        WHERE questionnaire_id = ?
        """,
        (int(questionnaire_id),),
    ).fetchone()
    return {
        "submission_count": int(row["submission_count"] or 0) if row else 0,
        "last_submitted_at": row.get("last_submitted_at", "") if row else "",
    }


def _build_questionnaire_detail(row: dict[str, Any]) -> dict[str, Any]:
    detail = _serialize_questionnaire_row(row)
    detail["questions"] = _load_questionnaire_questions(int(row["id"]))
    detail["score_rules"] = _load_questionnaire_score_rules(int(row["id"]))
    detail.update(_questionnaire_submission_stats(int(row["id"])))
    return detail


def _insert_questionnaire_options(question_id: int, options: list[dict[str, Any]]) -> None:
    db = get_db()
    for item in options:
        db.execute(
            """
            INSERT INTO questionnaire_options (
                question_id, option_text, score, tag_codes, sort_order, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                int(question_id),
                item["option_text"],
                item["score"],
                _json_dumps(item["tag_codes"]),
                item["sort_order"],
            ),
        )


def _sync_questionnaire_questions(questionnaire_id: int, questions: list[dict[str, Any]]) -> None:
    db = get_db()
    db.execute("DELETE FROM questionnaire_questions WHERE questionnaire_id = ?", (int(questionnaire_id),))

    for item in questions:
        row = db.execute(
            """
            INSERT INTO questionnaire_questions (
                questionnaire_id, type, title, placeholder_text, required, sort_order, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            RETURNING id
            """,
            (
                int(questionnaire_id),
                item["type"],
                item["title"],
                item.get("placeholder_text", "") or "",
                item["required"],
                item["sort_order"],
            ),
        ).fetchone()
        current_question_id = int(row["id"])
        if item["type"] not in {"textarea", "mobile"}:
            _insert_questionnaire_options(current_question_id, item.get("options") or [])


def _sync_questionnaire_score_rules(questionnaire_id: int, score_rules: list[dict[str, Any]]) -> None:
    db = get_db()
    db.execute("DELETE FROM questionnaire_score_rules WHERE questionnaire_id = ?", (int(questionnaire_id),))

    for item in score_rules:
        db.execute(
            """
            INSERT INTO questionnaire_score_rules (
                questionnaire_id, min_score, max_score, tag_codes, sort_order, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                int(questionnaire_id),
                item["min_score"],
                item["max_score"],
                _json_dumps(item["tag_codes"]),
                item["sort_order"],
            ),
        )




__all__ = [
    "_bind_questionnaire_identity",
    "_build_questionnaire_detail",
    "_dedupe_questionnaire_slug",
    "_dedupe_strings",
    "_get_questionnaire_row",
    "_insert_questionnaire_options",
    "_json_array",
    "_json_dumps",
    "_json_loads",
    "_load_questionnaire_questions",
    "_load_questionnaire_score_rules",
    "_normalize_bool",
    "_normalize_float",
    "_normalize_int",
    "_normalize_questionnaire_external_push_custom_params",
    "_normalize_questionnaire_payload",
    "_normalize_required_integer",
    "_normalize_tag_codes",
    "_questionnaire_exists_by_slug",
    "_questionnaire_submission_stats",
    "_resolve_external_contact_identity_payload",
    "_resolve_questionnaire_person_identity",
    "_serialize_questionnaire_row",
    "_slugify_questionnaire",
    "_sync_questionnaire_questions",
    "_sync_questionnaire_score_rules",
    "_validate_tag_codes_payload",
]
