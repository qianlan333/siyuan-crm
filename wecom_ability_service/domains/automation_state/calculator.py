from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from .evaluator import evaluate_marketing_eligibility
from .state_defs import (
    FOLLOWUP_SEGMENT_FOCUS,
    FOLLOWUP_SEGMENT_NORMAL,
    FOLLOWUP_SEGMENT_UNKNOWN,
    POOL_ACTIVE_FOCUS,
    POOL_ACTIVE_NORMAL,
    POOL_INACTIVE_FOCUS,
    POOL_INACTIVE_NORMAL,
    POOL_NEW_USER,
    POOL_SILENT,
)

POOL_STAGE = "pool"
CONVERTED_STAGE_KEY = "converted/enrolled"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    text = _text(value)
    if not text:
        return None
    import re as _re
    text = _re.sub(r"[+-]\d{2}(:\d{2})?$", "", text).rstrip()
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(text, pattern)
        except ValueError:
            continue
    return None


def pool_stage_key(pool_key: Any) -> str:
    normalized_pool_key = _text(pool_key)
    if not normalized_pool_key:
        return ""
    return f"{POOL_STAGE}/{normalized_pool_key}"


def resolve_current_segment(
    *,
    has_questionnaire_submission: bool,
    questionnaire_segment: str,
    manual_segment: str,
) -> dict[str, str]:
    normalized_manual_segment = _text(manual_segment)
    if normalized_manual_segment:
        return {
            "current_segment": normalized_manual_segment,
            "current_segment_source": "manual_override",
        }
    normalized_questionnaire_segment = _text(questionnaire_segment)
    if has_questionnaire_submission:
        return {
            "current_segment": normalized_questionnaire_segment or FOLLOWUP_SEGMENT_NORMAL,
            "current_segment_source": "questionnaire",
        }
    return {
        "current_segment": FOLLOWUP_SEGMENT_UNKNOWN,
        "current_segment_source": "awaiting_questionnaire",
    }


def resolve_pool_key_for_customer(
    *,
    has_questionnaire_submission: bool,
    trial_opened: bool,
    activated: bool,
    current_segment: str,
) -> str:
    if not has_questionnaire_submission:
        return POOL_NEW_USER
    if activated:
        return POOL_ACTIVE_FOCUS if _text(current_segment) == FOLLOWUP_SEGMENT_FOCUS else POOL_ACTIVE_NORMAL
    if not trial_opened:
        return POOL_NEW_USER
    return POOL_INACTIVE_FOCUS if _text(current_segment) == FOLLOWUP_SEGMENT_FOCUS else POOL_INACTIVE_NORMAL


def resolve_pool_reference_at(
    *,
    pool_key: str,
    trial_opened_at: str,
    submission_at: str,
    activation_at: str,
    last_message_at: str,
    now: str,
) -> str:
    if pool_key in {POOL_ACTIVE_NORMAL, POOL_ACTIVE_FOCUS}:
        return last_message_at or now
    if pool_key in {POOL_INACTIVE_NORMAL, POOL_INACTIVE_FOCUS}:
        return last_message_at or now
    return last_message_at or submission_at or trial_opened_at or activation_at or now


def should_enter_silent_pool(*, entered_at: str, silent_threshold_days: int, now: str) -> bool:
    entered_dt = _parse_timestamp(entered_at)
    now_dt = _parse_timestamp(now)
    if entered_dt is None or now_dt is None:
        return False
    return now_dt >= entered_dt + timedelta(days=int(silent_threshold_days))


def calculate_marketing_state(
    *,
    has_questionnaire_submission: bool,
    questionnaire_segment: str,
    manual_segment: str,
    trial_opened: bool,
    activated: bool,
    converted: bool,
    has_external_userid: bool,
    submission_at: str,
    trial_opened_at: str,
    activation_at: str,
    last_message_at: str,
    silent_threshold_days: int,
    existing_stage_key: str,
    existing_entered_at: str,
    existing_state_payload: dict[str, Any] | None,
    now: str,
    converted_at: str = "",
    force_base_entered_at: str = "",
) -> dict[str, Any]:
    existing_payload = dict(existing_state_payload or {})
    current_segment_payload = resolve_current_segment(
        has_questionnaire_submission=has_questionnaire_submission,
        questionnaire_segment=_text(questionnaire_segment),
        manual_segment=_text(manual_segment),
    )
    current_segment = current_segment_payload["current_segment"]
    current_segment_source = current_segment_payload["current_segment_source"]

    base_pool_key = resolve_pool_key_for_customer(
        has_questionnaire_submission=has_questionnaire_submission,
        trial_opened=trial_opened,
        activated=activated,
        current_segment=current_segment,
    )
    base_stage_key = pool_stage_key(base_pool_key)
    base_reference_at = resolve_pool_reference_at(
        pool_key=base_pool_key,
        trial_opened_at=_text(trial_opened_at),
        submission_at=_text(submission_at),
        activation_at=_text(activation_at),
        last_message_at=_text(last_message_at),
        now=_text(now),
    )
    base_entered_at = base_reference_at or _text(now)
    if _text(existing_stage_key) == base_stage_key and _text(existing_entered_at):
        base_entered_at = _text(existing_entered_at)
    elif (
        _text(existing_stage_key) == pool_stage_key(POOL_SILENT)
        and _text(existing_payload.get("silent_base_pool_key")) == base_pool_key
    ):
        base_entered_at = (
            _text(existing_payload.get("silent_base_pool_entered_at"))
            or _text(existing_payload.get("base_pool_entered_at"))
            or base_reference_at
            or _text(now)
        )
    if _text(force_base_entered_at):
        base_reference_at = _text(force_base_entered_at)
        base_entered_at = _text(force_base_entered_at)

    final_pool_key = base_pool_key
    if not converted:
        if (
            _text(existing_stage_key) == pool_stage_key(POOL_SILENT)
            and _text(existing_payload.get("silent_base_pool_key")) == base_pool_key
        ):
            final_pool_key = POOL_SILENT
        elif should_enter_silent_pool(
            entered_at=base_entered_at,
            silent_threshold_days=silent_threshold_days,
            now=_text(now),
        ):
            final_pool_key = POOL_SILENT

    if converted:
        stage_key = CONVERTED_STAGE_KEY
        main_stage = "converted"
        sub_stage = "enrolled"
        lifecycle_status = "converted"
        exit_reason = "enrolled"
        entered_at = _text(existing_entered_at)
        if _text(existing_stage_key) != stage_key:
            entered_at = _text(converted_at) or _text(now)
        exited_at = _text(converted_at) or _text(now)
    else:
        stage_key = pool_stage_key(final_pool_key)
        main_stage = POOL_STAGE
        sub_stage = final_pool_key
        lifecycle_status = "silent" if final_pool_key == POOL_SILENT else "pool"
        if final_pool_key == POOL_SILENT:
            exit_reason = "silent_timeout"
        elif not has_questionnaire_submission:
            exit_reason = "awaiting_questionnaire"
        elif not trial_opened and not activated:
            exit_reason = "trial_not_opened"
        else:
            exit_reason = ""
        entered_at = _text(existing_entered_at)
        if _text(existing_stage_key) != stage_key:
            entered_at = _text(now) if final_pool_key == POOL_SILENT else (base_reference_at or _text(now))
        exited_at = ""

    eligibility = evaluate_marketing_eligibility(
        trial_opened=trial_opened,
        activated=activated,
        has_questionnaire_submission=has_questionnaire_submission,
        converted=converted,
        has_external_userid=has_external_userid,
        final_pool_key=final_pool_key,
        stage_key=stage_key,
        exit_reason=exit_reason,
    )
    return {
        "stage_key": stage_key,
        "pool_key": final_pool_key,
        "current_segment": current_segment,
        "current_segment_source": current_segment_source,
        "lifecycle_status": lifecycle_status,
        "entered_at": entered_at,
        "exited_at": exited_at,
        "exit_reason": exit_reason,
        "eligible_for_conversion": bool(eligibility["eligible_for_conversion"]),
        "openclaw_eligible": bool(eligibility["openclaw_eligible"]),
        "ineligible_reason": _text(eligibility["ineligible_reason"]),
        "main_stage": main_stage,
        "sub_stage": sub_stage,
        "base_pool_key": base_pool_key,
        "base_stage_key": base_stage_key,
        "base_reference_at": base_reference_at,
        "base_entered_at": base_entered_at,
    }
