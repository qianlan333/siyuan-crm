from __future__ import annotations

from datetime import datetime
from typing import Any

import requests

STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"
GLOBAL_ENABLED_KEY = "QUESTIONNAIRE_EXTERNAL_PUSH_GLOBAL_ENABLED"
TIMEOUT_SECONDS_KEY = "QUESTIONNAIRE_EXTERNAL_PUSH_TIMEOUT_SECONDS"
GLOBAL_DISABLED_REASON = "skipped by global external push switch"


def deliver_questionnaire_external_push(
    *,
    repo: Any,
    questionnaire: dict[str, Any],
    submission: dict[str, Any],
    computed_result: dict[str, Any],
) -> dict[str, Any]:
    config = dict(questionnaire.get("external_push_config") or {})
    if not _bool(config.get("enabled") or questionnaire.get("external_push_enabled")):
        return {"enabled": False, "attempted": False, "ok": True, "reason": "external_push_disabled"}

    target_url = _text(config.get("webhook_url") or questionnaire.get("external_push_url"))
    payload = build_questionnaire_external_push_payload(
        questionnaire=questionnaire,
        submission=submission,
        computed_result=computed_result,
    )
    if not _global_enabled(repo):
        log = _log(
            repo=repo,
            questionnaire=questionnaire,
            submission=submission,
            target_url=target_url,
            payload=payload,
            response_status_code=None,
            response_body="",
            status=STATUS_SKIPPED,
            failure_reason=GLOBAL_DISABLED_REASON,
        )
        return {
            "enabled": True,
            "attempted": False,
            "ok": False,
            "reason": "global_switch_disabled",
            "status": STATUS_SKIPPED,
            "log": log,
        }

    result = _execute_request(target_url=target_url, payload=payload, timeout_seconds=_timeout_seconds(repo))
    log = _log(
        repo=repo,
        questionnaire=questionnaire,
        submission=submission,
        target_url=target_url,
        payload=payload,
        response_status_code=result.get("response_status_code"),
        response_body=_text(result.get("response_body")),
        status=STATUS_SUCCESS if result.get("ok") else STATUS_FAILED,
        failure_reason=_text(result.get("failure_reason")),
    )
    return {
        "enabled": True,
        "attempted": bool(result.get("attempted")),
        "ok": bool(result.get("ok")),
        "reason": _text(result.get("failure_reason")),
        "status": STATUS_SUCCESS if result.get("ok") else STATUS_FAILED,
        "response_status_code": result.get("response_status_code"),
        "log": log,
    }


def build_questionnaire_external_push_payload(
    *,
    questionnaire: dict[str, Any],
    submission: dict[str, Any],
    computed_result: dict[str, Any],
) -> dict[str, Any]:
    config = dict(questionnaire.get("external_push_config") or {})
    answer_snapshots = list(submission.get("answer_snapshots") or computed_result.get("answer_snapshots") or [])
    payload: dict[str, Any] = {
        "user_id": _external_push_user_id(submission),
        "questionnaire_title": _text(questionnaire.get("title") or questionnaire.get("name")),
        "submitted_at": _iso_datetime(submission.get("submitted_at") or submission.get("created_at")),
        "phone_number": _phone_number(answer_snapshots),
        "answers": _serialized_answers(answer_snapshots),
    }
    _copy_int(payload, "day", config.get("day") if "day" in config else questionnaire.get("external_push_day"))
    _copy_int(payload, "frequency", config.get("frequency") if "frequency" in config else questionnaire.get("external_push_frequency"))
    _copy_int(
        payload,
        "expires_at_ts",
        config.get("expires_at_ts") if "expires_at_ts" in config else questionnaire.get("external_push_expires_at_ts"),
    )
    push_type = _text(config.get("type") or questionnaire.get("external_push_type"))
    if push_type:
        payload["type"] = push_type
    remark = _text(config.get("remark") or questionnaire.get("external_push_remark"))
    if remark:
        payload["remark"] = remark
    assessment_result = computed_result.get("assessment_result")
    if isinstance(assessment_result, dict) and assessment_result:
        payload["assessment_result_snapshot"] = assessment_result
    for item in _custom_params(config.get("custom_params") or questionnaire.get("external_push_custom_params")):
        payload[item["name"]] = item["value"]
    return payload


def _execute_request(*, target_url: str, payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
    if not target_url:
        return {
            "ok": False,
            "attempted": False,
            "response_status_code": None,
            "response_body": "",
            "failure_reason": "external push url is empty",
        }
    try:
        response = requests.post(
            target_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=timeout_seconds,
        )
    except requests.Timeout as exc:
        return {
            "ok": False,
            "attempted": True,
            "response_status_code": None,
            "response_body": "",
            "failure_reason": f"request timeout: {exc}",
        }
    except requests.RequestException as exc:
        return {
            "ok": False,
            "attempted": True,
            "response_status_code": None,
            "response_body": "",
            "failure_reason": f"network error: {exc}",
        }
    response_body = (response.text or "")[:5000]
    return {
        "ok": int(response.status_code) == 200,
        "attempted": True,
        "response_status_code": int(response.status_code),
        "response_body": response_body,
        "failure_reason": "" if int(response.status_code) == 200 else f"HTTP {int(response.status_code)}",
    }


def _log(
    *,
    repo: Any,
    questionnaire: dict[str, Any],
    submission: dict[str, Any],
    target_url: str,
    payload: dict[str, Any],
    response_status_code: int | None,
    response_body: str,
    status: str,
    failure_reason: str,
) -> dict[str, Any]:
    create_log = getattr(repo, "create_external_push_log", None)
    if not callable(create_log):
        return {}
    try:
        return create_log(
            questionnaire_id=int(questionnaire["id"]),
            questionnaire_title_snapshot=_text(questionnaire.get("title") or questionnaire.get("name")),
            submission_record_id=submission.get("id") or submission.get("submission_id"),
            retry_from_log_id=None,
            retry_attempt=0,
            user_id=_text(payload.get("user_id")),
            target_url=target_url,
            request_payload=payload,
            response_status_code=response_status_code,
            response_body=response_body,
            status=status,
            failure_reason=failure_reason,
        )
    except Exception:
        return {}


def _global_enabled(repo: Any) -> bool:
    value = _setting(repo, GLOBAL_ENABLED_KEY)
    if value in (None, ""):
        return True
    return _bool(value)


def _timeout_seconds(repo: Any) -> float:
    value = _setting(repo, TIMEOUT_SECONDS_KEY)
    try:
        timeout = float(value if value not in (None, "") else 3)
    except (TypeError, ValueError):
        timeout = 3.0
    return max(0.5, min(timeout, 10.0))


def _setting(repo: Any, key: str) -> str | None:
    get_setting = getattr(repo, "get_app_setting", None)
    if not callable(get_setting):
        return None
    return get_setting(key)


def _serialized_answers(answer_snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    for item in answer_snapshots:
        question_type = _text(item.get("question_type"))
        title = _text(item.get("question_title_snapshot"))
        if question_type == "multi_choice":
            answer: str | list[str] = _dedupe([_text(value) for value in item.get("selected_option_texts_snapshot") or []])
        elif question_type == "single_choice":
            answer = (_dedupe([_text(value) for value in item.get("selected_option_texts_snapshot") or []]) or [""])[0]
        elif question_type in {"textarea", "mobile"}:
            answer = _text(item.get("text_value"))
        else:
            continue
        serialized.append({"title": title, "answer": answer})
    return serialized


def _phone_number(answer_snapshots: list[dict[str, Any]]) -> str:
    for item in answer_snapshots:
        if _text(item.get("question_type")) != "mobile":
            continue
        return _text(item.get("text_value")) or "NULL"
    return "NULL"


def _external_push_user_id(submission: dict[str, Any]) -> str:
    for field in ["respondent_key", "external_userid", "unionid", "openid"]:
        value = _text(submission.get(field))
        if value:
            return value
    return ""


def _copy_int(payload: dict[str, Any], key: str, value: Any) -> None:
    if value in (None, ""):
        return
    payload[key] = int(value)


def _custom_params(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, str]] = []
    reserved = {"user_id", "questionnaire_title", "submitted_at", "answers", "phone_number", "type", "expires_at_ts", "day", "frequency", "remark"}
    for item in value:
        if not isinstance(item, dict):
            continue
        name = _text(item.get("name"))
        if not name or name in reserved:
            continue
        result.append({"name": name, "value": _text(item.get("value"))})
    return result


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _iso_datetime(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return _text(value)


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _bool(value: Any) -> bool:
    return str(value if value is not None else "").strip().lower() in {"1", "true", "yes", "on", "t"}
