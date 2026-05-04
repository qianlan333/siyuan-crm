from __future__ import annotations

from datetime import datetime
from typing import Any

from ...db import get_db
from . import repo
from .service import (
    DEFAULT_CORE_THRESHOLD,
    DEFAULT_SCENARIO_KEY,
    DEFAULT_TOP_THRESHOLD,
    VALUE_SEGMENT_SCORING_VERSION,
    _VALUE_SEGMENT_LABELS,
    _json_loads,
    _normalize_int,
    _normalized_text,
    _parse_timestamp,
    _segment_rank,
    get_signup_conversion_config,
)


def _iso_now() -> str:
    from . import service as _svc
    return _svc._iso_now()


def _value_segment_config_ready(config: dict[str, Any]) -> bool:
    return bool(
        config.get("configured")
        and config.get("enabled")
        and config.get("questionnaire_id")
        and len(config.get("question_rules") or []) > 0
    )


def _serialize_current_customer_value_segment(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    segment = _normalized_text(row.get("segment")) or "unknown"
    raw_matched_question_ids = _json_loads(row.get("matched_question_ids_json"), default=[])
    if not isinstance(raw_matched_question_ids, list):
        raw_matched_question_ids = []
    matched_question_ids = [
        int(item)
        for item in raw_matched_question_ids
        if str(item).strip()
    ]
    return {
        "id": int(row.get("id") or 0),
        "external_userid": _normalized_text(row.get("external_userid")),
        "segment": segment,
        "segment_label": _VALUE_SEGMENT_LABELS.get(segment, segment),
        "segment_rank": int(row.get("segment_rank") or _segment_rank(segment)),
        "score": int(row.get("score") or 0),
        "hit_count": int(row.get("score") or 0),
        "scoring_version": _normalized_text(row.get("scoring_version")) or VALUE_SEGMENT_SCORING_VERSION,
        "computed_reason": _normalized_text(row.get("computed_reason")),
        "submission_id": _normalize_int(row.get("submission_id"), "submission_id", allow_none=True),
        "matched_question_ids_json": matched_question_ids,
        "evaluated_at": _normalized_text(row.get("evaluated_at")) or _normalized_text(row.get("computed_at")),
        "source_payload": _json_loads(row.get("source_payload_json"), default={}),
        "is_core": segment in {"core", "top"},
        "is_top": segment == "top",
        "updated_at": _normalized_text(row.get("updated_at")),
    }


def _normalize_answer_option_ids(value: Any) -> set[int]:
    raw_value = _json_loads(value, default=[])
    if not isinstance(raw_value, list):
        return set()
    return {
        int(item)
        for item in raw_value
        if str(item).strip()
    }


def _resolve_value_segment_target(
    *,
    external_userid: str,
    person_id: int | None,
) -> dict[str, Any]:
    normalized_external_userid = _normalized_text(external_userid)
    normalized_person_id = _normalize_int(person_id, "person_id", allow_none=True)
    external_userids: list[str] = []
    mobile = ""
    if normalized_external_userid:
        external_userids = [normalized_external_userid]
    elif normalized_person_id is not None:
        external_userids = repo.list_external_userids_by_person(int(normalized_person_id))
        mobile = repo.get_person_mobile(int(normalized_person_id))
        normalized_external_userid = external_userids[0] if external_userids else ""
    else:
        raise ValueError("external_userid or person_id is required")
    return {
        "external_userid": normalized_external_userid,
        "external_userids": external_userids,
        "person_id": normalized_person_id,
        "mobile": mobile,
    }


def _resolve_latest_value_segment_submission(
    questionnaire_id: int,
    *,
    target: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    submission = repo.get_latest_questionnaire_submission_for_value_segment(
        int(questionnaire_id),
        external_userids=target.get("external_userids") or [target["external_userid"]],
        mobile_snapshot=_normalized_text(target.get("mobile")),
    )
    if not submission:
        return None, []
    answers = repo.list_questionnaire_submission_answers(int(submission["id"]))
    if not answers:
        return None, []
    return submission, answers


def _compute_submission_hit_result(
    *,
    config: dict[str, Any],
    submission: dict[str, Any] | None,
    answers: list[dict[str, Any]],
) -> dict[str, Any]:
    if not submission or not answers:
        return {
            "segment": "unknown",
            "hit_count": 0,
            "matched_question_ids": [],
            "submission_id": None,
            "computed_reason": "no_valid_submission",
        }
    answers_by_question: dict[int, set[int]] = {}
    for item in answers:
        question_id = int(item.get("question_id") or 0)
        if question_id <= 0:
            continue
        answers_by_question.setdefault(question_id, set()).update(_normalize_answer_option_ids(item.get("selected_option_ids")))
    matched_question_ids: list[int] = []
    for rule in config.get("question_rules") or []:
        question_id = int(rule.get("questionnaire_question_id") or 0)
        configured_option_ids = {int(option_id) for option_id in rule.get("hit_option_ids_json") or []}
        if question_id <= 0 or not configured_option_ids:
            continue
        if answers_by_question.get(question_id, set()) & configured_option_ids:
            matched_question_ids.append(question_id)
    hit_count = len(matched_question_ids)
    top_threshold = int(config.get("top_threshold") or DEFAULT_TOP_THRESHOLD)
    core_threshold = int(config.get("core_threshold") or DEFAULT_CORE_THRESHOLD)
    if hit_count >= top_threshold:
        segment = "top"
    elif hit_count >= core_threshold:
        segment = "core"
    else:
        segment = "normal"
    return {
        "segment": segment,
        "hit_count": hit_count,
        "matched_question_ids": matched_question_ids,
        "submission_id": int(submission["id"]),
        "computed_reason": f"hit_count={hit_count};core_threshold={core_threshold};top_threshold={top_threshold}",
    }


def evaluate_customer_value_segment(
    *,
    external_userid: str = "",
    person_id: int | None = None,
    automation_key: str = DEFAULT_SCENARIO_KEY,
    persist: bool = True,
) -> dict[str, Any]:
    target = _resolve_value_segment_target(external_userid=external_userid, person_id=person_id)
    config = get_signup_conversion_config(automation_key=automation_key)
    evaluated_at = _iso_now()
    questionnaire_id = _normalize_int(config.get("questionnaire_id"), "questionnaire_id", allow_none=True)
    if not _normalized_text(target.get("external_userid")):
        result = {
            "external_userid": "",
            "person_id": target.get("person_id"),
            "questionnaire_id": questionnaire_id,
            "segment": "unknown",
            "segment_label": _VALUE_SEGMENT_LABELS["unknown"],
            "segment_rank": _segment_rank("unknown"),
            "score": 0,
            "hit_count": 0,
            "submission_id": None,
            "matched_question_ids_json": [],
            "evaluated_at": evaluated_at,
            "scoring_version": VALUE_SEGMENT_SCORING_VERSION,
            "computed_reason": "missing_external_userid",
            "source_payload": {
                "automation_key": automation_key,
                "person_id": target.get("person_id"),
                "mobile": _normalized_text(target.get("mobile")),
            },
            "is_core": False,
            "is_top": False,
            "history_written": False,
        }
        return result
    if not _value_segment_config_ready(config) or questionnaire_id is None:
        result = {
            "external_userid": target["external_userid"],
            "person_id": target.get("person_id"),
            "questionnaire_id": questionnaire_id,
            "segment": "unknown",
            "segment_label": _VALUE_SEGMENT_LABELS["unknown"],
            "segment_rank": _segment_rank("unknown"),
            "score": 0,
            "hit_count": 0,
            "submission_id": None,
            "matched_question_ids_json": [],
            "evaluated_at": evaluated_at,
            "scoring_version": VALUE_SEGMENT_SCORING_VERSION,
            "computed_reason": "automation_config_not_ready",
            "source_payload": {"automation_key": automation_key, "config_enabled": bool(config.get("enabled"))},
            "is_core": False,
            "is_top": False,
        }
    else:
        submission, answers = _resolve_latest_value_segment_submission(int(questionnaire_id), target=target)
        evaluated = _compute_submission_hit_result(config=config, submission=submission, answers=answers)
        segment = evaluated["segment"]
        result = {
            "external_userid": target["external_userid"],
            "person_id": target.get("person_id"),
            "questionnaire_id": int(questionnaire_id),
            "segment": segment,
            "segment_label": _VALUE_SEGMENT_LABELS[segment],
            "segment_rank": _segment_rank(segment),
            "score": int(evaluated["hit_count"]),
            "hit_count": int(evaluated["hit_count"]),
            "submission_id": evaluated["submission_id"],
            "matched_question_ids_json": list(evaluated["matched_question_ids"]),
            "evaluated_at": evaluated_at,
            "scoring_version": VALUE_SEGMENT_SCORING_VERSION,
            "computed_reason": _normalized_text(evaluated["computed_reason"]),
            "source_payload": {
                "automation_key": automation_key,
                "questionnaire_id": int(questionnaire_id),
                "core_threshold": int(config.get("core_threshold") or DEFAULT_CORE_THRESHOLD),
                "top_threshold": int(config.get("top_threshold") or DEFAULT_TOP_THRESHOLD),
                "latest_submission_external_userid": _normalized_text((submission or {}).get("external_userid")),
                "latest_submission_submitted_at": _normalized_text((submission or {}).get("submitted_at")),
                "person_id": target.get("person_id"),
            },
            "is_core": segment in {"core", "top"},
            "is_top": segment == "top",
        }

    if not persist:
        result["person_id"] = target.get("person_id")
        result["questionnaire_id"] = questionnaire_id
        result["history_written"] = False
        return result

    existing = _serialize_current_customer_value_segment(repo.get_customer_value_segment_current(target["external_userid"]))
    db = get_db()
    history_written = False
    try:
        if not existing or _normalized_text(existing.get("segment")) != result["segment"]:
            repo.insert_customer_value_segment_history(
                external_userid=target["external_userid"],
                segment=result["segment"],
                segment_rank=int(result["segment_rank"]),
                score=int(result["score"]),
                scoring_version=result["scoring_version"],
                change_reason="initial_compute" if not existing else "segment_changed",
                submission_id=result["submission_id"],
                matched_question_ids=result["matched_question_ids_json"],
                source_payload=result["source_payload"],
                evaluated_at=result["evaluated_at"],
            )
            history_written = True
        current = repo.upsert_customer_value_segment_current(
            external_userid=target["external_userid"],
            segment=result["segment"],
            segment_rank=int(result["segment_rank"]),
            score=int(result["score"]),
            scoring_version=result["scoring_version"],
            computed_reason=result["computed_reason"],
            submission_id=result["submission_id"],
            matched_question_ids=result["matched_question_ids_json"],
            source_payload=result["source_payload"],
            evaluated_at=result["evaluated_at"],
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    serialized_current = _serialize_current_customer_value_segment(current) or result
    serialized_current["person_id"] = target.get("person_id")
    serialized_current["questionnaire_id"] = questionnaire_id
    serialized_current["history_written"] = history_written
    return serialized_current



def _dedupe_tag_names(base: dict[str, Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for tag in base.get("tags") or []:
        tag_name = _normalized_text((tag or {}).get("tag_name") or (tag or {}).get("tag_id"))
        if not tag_name or tag_name in seen:
            continue
        seen.add(tag_name)
        result.append(tag_name)
    signup_label_name = _normalized_text(base.get("signup_label_name"))
    if signup_label_name and signup_label_name not in seen:
        result.append(signup_label_name)
    return result


def _compute_value_segment(base: dict[str, Any], *, config: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now()
    score = 0
    score_breakdown: dict[str, int] = {}

    if bool(base.get("is_bound")):
        score_breakdown["mobile_bound"] = 25
        score += 25
    if int(base.get("questionnaire_submission_count") or 0) > 0:
        score_breakdown["questionnaire_submitted"] = 20
        score += 20
    if _normalized_text(base.get("owner_userid")):
        score_breakdown["owner_assigned"] = 5
        score += 5

    tag_names = _dedupe_tag_names(base)
    if any(keyword in tag_name for tag_name in tag_names for keyword in _HIGH_INTENT_TAG_KEYWORDS):
        score_breakdown["high_intent_tags"] = 20
        score += 20

    last_customer_text_at = _parse_timestamp(base.get("last_customer_text_at"))
    if last_customer_text_at is not None:
        age_hours = (now - last_customer_text_at).total_seconds() / 3600
        if age_hours <= 6:
            score_breakdown["recent_customer_text_6h"] = 30
            score += 30
        elif age_hours <= 24:
            score_breakdown["recent_customer_text_24h"] = 20
            score += 20
        elif age_hours <= 72:
            score_breakdown["recent_customer_text_72h"] = 10
            score += 10

    top_threshold = int(config.get("top_threshold") or DEFAULT_TOP_THRESHOLD)
    core_threshold = int(config.get("core_threshold") or DEFAULT_CORE_THRESHOLD)
    if score >= top_threshold:
        value_segment = "top"
    elif score >= core_threshold:
        value_segment = "core"
    else:
        value_segment = "normal"

    return {
        "scenario_key": DEFAULT_SCENARIO_KEY,
        "external_userid": _normalized_text(base.get("external_userid")),
        "value_segment": value_segment,
        "segment_label": _VALUE_SEGMENT_LABELS[value_segment],
        "score": score,
        "score_breakdown": score_breakdown,
        "is_core": value_segment in {"core", "top"},
        "is_top": value_segment == "top",
    }



def _persist_value_segment(base: dict[str, Any], *, scenario_key: str, config: dict[str, Any]) -> dict[str, Any]:
    if _value_segment_config_ready(config):
        evaluated = evaluate_customer_value_segment(
            external_userid=_normalized_text(base.get("external_userid")),
            automation_key=scenario_key,
        )
        return {
            "value_segment": _normalized_text(evaluated.get("segment")),
            "segment_label": _normalized_text(evaluated.get("segment_label"))
            or _VALUE_SEGMENT_LABELS.get(_normalized_text(evaluated.get("segment")), ""),
            "score": int(evaluated.get("score") or 0),
            "score_breakdown": {
                "question_hit_count": int(evaluated.get("hit_count") or 0),
                "matched_question_ids": list(evaluated.get("matched_question_ids_json") or []),
                "submission_id": evaluated.get("submission_id"),
            },
            "is_core": bool(evaluated.get("is_core")),
            "is_top": bool(evaluated.get("is_top")),
            "updated_at": _normalized_text(evaluated.get("updated_at")) or _normalized_text(evaluated.get("evaluated_at")),
        }
    value_segment = _compute_value_segment(base, config=config)
    row = repo.upsert_marketing_value_segment_current(
        scenario_key=scenario_key,
        external_userid=_normalized_text(base.get("external_userid")),
        value_segment=value_segment["value_segment"],
        segment_label=value_segment["segment_label"],
        score=int(value_segment["score"]),
        score_breakdown=value_segment["score_breakdown"],
        source_payload={
            "is_bound": bool(base.get("is_bound")),
            "questionnaire_submission_count": int(base.get("questionnaire_submission_count") or 0),
            "last_customer_text_at": _normalized_text(base.get("last_customer_text_at")),
            "tag_names": _dedupe_tag_names(base),
            "core_threshold": int(config.get("core_threshold") or DEFAULT_CORE_THRESHOLD),
            "top_threshold": int(config.get("top_threshold") or DEFAULT_TOP_THRESHOLD),
        },
    )
    row["score_breakdown"] = _json_loads(row.get("score_breakdown_json"), default={})
    row["is_core"] = _normalized_text(row.get("value_segment")) in {"core", "top"}
    row["is_top"] = _normalized_text(row.get("value_segment")) == "top"
    return row



