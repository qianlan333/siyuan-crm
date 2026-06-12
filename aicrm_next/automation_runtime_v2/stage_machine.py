from __future__ import annotations

from typing import Any

from aicrm_next.shared.postgres_connection import get_db

from .domain import (
    EVENT_CHANNEL_ENTERED,
    EVENT_PAYMENT_SUCCEEDED,
    EVENT_QUESTIONNAIRE_SUBMITTED,
    EVENT_WEBHOOK_RECEIVED,
    STAGE_CONVERTED,
    STAGE_OPERATING,
    STAGE_PENDING_QUESTIONNAIRE,
    STAGES,
    StageTransitionResult,
    as_int,
    text,
)


def _payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload_json")
    return payload if isinstance(payload, dict) else {}


def _load_audience_entry_rule_config(program_id: int) -> dict[str, Any]:
    if int(program_id or 0) <= 0:
        return {}
    row = get_db().execute(
        """
        SELECT payload_json
        FROM automation_program_config_block
        WHERE program_id = ? AND block_key = 'audience_entry_rule'
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (int(program_id),),
    ).fetchone()
    if not row:
        return {}
    payload = row.get("payload_json")
    return payload if isinstance(payload, dict) else {}


def _questionnaire_review_enabled(config: dict[str, Any]) -> bool:
    review = config.get("questionnaire_review")
    return bool(review.get("enabled")) if isinstance(review, dict) else False


def _selected_questionnaire_id(config: dict[str, Any]) -> int:
    review = config.get("questionnaire_review")
    if not isinstance(review, dict):
        return 0
    return as_int(review.get("selected_questionnaire_id"))


def _find_enabled_rule(config: dict[str, Any], event_names: set[str]) -> dict[str, Any]:
    rules = config.get("rules")
    if not isinstance(rules, list):
        return {}
    normalized = {text(name) for name in event_names if text(name)}
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        if not bool(rule.get("enabled")):
            continue
        if text(rule.get("event")) in normalized:
            return rule
    return {}


def _rule_target_stage(rule: dict[str, Any]) -> str:
    target = text(rule.get("target_audience_code") or rule.get("target_stage_code") or rule.get("target_stage"))
    return target if target in STAGES else ""


def _nested_value(payload: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = payload
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _event_questionnaire_id(event: dict[str, Any]) -> int:
    payload = _payload(event)
    candidates = (
        payload.get("questionnaire_id"),
        payload.get("questionnaireId"),
        payload.get("selected_questionnaire_id"),
        _nested_value(payload, ("submission", "questionnaire_id")),
        _nested_value(payload, ("questionnaire", "id")),
    )
    for candidate in candidates:
        value = as_int(candidate)
        if value > 0:
            return value
    return 0


def _questionnaire_rule_matches(rule: dict[str, Any], config: dict[str, Any], event: dict[str, Any]) -> tuple[bool, int, int]:
    selected_id = _selected_questionnaire_id(config)
    event_id = _event_questionnaire_id(event)
    if text(rule.get("condition_type")) == "questionnaire_id_matched" and selected_id > 0:
        return event_id == selected_id, event_id, selected_id
    return True, event_id, selected_id


def _program_requires_questionnaire(program_id: int) -> bool:
    row = get_db().execute(
        """
        SELECT payload_json
        FROM automation_program_config_block
        WHERE program_id = ? AND block_key IN ('audience_entry_rule', 'entry_questionnaire', 'questionnaire')
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (int(program_id),),
    ).fetchone()
    if not row:
        return False
    payload = row.get("payload_json")
    if isinstance(payload, dict):
        return bool(
            payload.get("requires_questionnaire")
            or payload.get("questionnaire_required")
            or payload.get("enabled")
            or _questionnaire_review_enabled(payload)
        )
    return "questionnaire" in text(payload).lower()


def _has_questionnaire_submission(membership: dict[str, Any], event: dict[str, Any], selected_questionnaire_id: int = 0) -> bool:
    if text(event.get("event_type")) == EVENT_QUESTIONNAIRE_SUBMITTED:
        event_questionnaire_id = _event_questionnaire_id(event)
        return selected_questionnaire_id <= 0 or event_questionnaire_id == selected_questionnaire_id
    external = text(membership.get("external_userid") or event.get("external_userid"))
    phone = text(membership.get("phone") or event.get("phone"))
    identity_conditions: list[str] = []
    params: list[Any] = []
    if external:
        identity_conditions.append("NULLIF(COALESCE(external_userid, ''), '') = ?")
        params.append(external)
    if phone:
        identity_conditions.append("NULLIF(COALESCE(mobile_snapshot, respondent_key, ''), '') = ?")
        params.append(phone)
    if not identity_conditions:
        return False
    where = f"({' OR '.join(identity_conditions)})"
    if int(selected_questionnaire_id or 0) > 0:
        where += " AND questionnaire_id = ?"
        params.append(int(selected_questionnaire_id))
    row = get_db().execute(
        f"""
        SELECT id
        FROM questionnaire_submissions
        WHERE {where}
        LIMIT 1
        """,
        tuple(params),
    ).fetchone()
    return bool(row)


def _has_successful_payment(membership: dict[str, Any], event: dict[str, Any]) -> bool:
    if text(event.get("event_type")) == EVENT_PAYMENT_SUCCEEDED:
        return True
    external = text(membership.get("external_userid") or event.get("external_userid"))
    phone = text(membership.get("phone") or event.get("phone"))
    identity_conditions: list[str] = []
    params: list[Any] = []
    if external:
        identity_conditions.append("NULLIF(COALESCE(external_userid, ''), '') = ?")
        params.append(external)
    if phone:
        identity_conditions.append("NULLIF(COALESCE(mobile_snapshot, respondent_key, ''), '') = ?")
        params.append(phone)
    if not identity_conditions:
        return False
    row = get_db().execute(
        f"""
        SELECT id
        FROM wechat_pay_orders
        WHERE ({" OR ".join(identity_conditions)})
          AND (status = 'paid' OR trade_state = 'SUCCESS')
        LIMIT 1
        """,
        tuple(params),
    ).fetchone()
    return bool(row)


def resolve_next_stage(event: dict[str, Any], membership: dict[str, Any], program_config: dict[str, Any] | None = None) -> StageTransitionResult:
    event_type = text(event.get("event_type"))
    payload = _payload(event)
    current_stage = text(membership.get("current_stage")) or STAGE_PENDING_QUESTIONNAIRE
    target_stage = current_stage
    reason = "stage_unchanged"
    program_id = as_int(membership.get("program_id") or event.get("program_id"))
    audience_config = _load_audience_entry_rule_config(program_id)
    selected_questionnaire_id = _selected_questionnaire_id(audience_config)
    questionnaire_review_enabled = _questionnaire_review_enabled(audience_config)
    matched_rule: dict[str, Any] = {}
    event_questionnaire_id = _event_questionnaire_id(event)
    questionnaire_id_matched: bool | None = None
    if event_type == EVENT_CHANNEL_ENTERED:
        if _has_successful_payment(membership, event):
            target_stage = STAGE_CONVERTED
            reason = "payment_already_succeeded"
        elif _has_questionnaire_submission(membership, event, selected_questionnaire_id):
            target_stage = STAGE_OPERATING
            reason = "questionnaire_already_submitted"
            questionnaire_id_matched = True
        elif (matched_rule := _find_enabled_rule(audience_config, {"channel_enter", EVENT_CHANNEL_ENTERED})):
            target_stage = _rule_target_stage(matched_rule) or STAGE_PENDING_QUESTIONNAIRE
            reason = "audience_entry_rule_channel_entered"
        elif bool((program_config or {}).get("requires_questionnaire")) or bool(payload.get("requires_questionnaire")) or _program_requires_questionnaire(as_int(membership.get("program_id"))):
            target_stage = STAGE_PENDING_QUESTIONNAIRE
            reason = "channel_entered_requires_questionnaire"
        else:
            target_stage = STAGE_OPERATING
            reason = "channel_entered"
    elif event_type == EVENT_QUESTIONNAIRE_SUBMITTED:
        matched_rule = _find_enabled_rule(audience_config, {EVENT_QUESTIONNAIRE_SUBMITTED})
        if matched_rule:
            questionnaire_id_matched, event_questionnaire_id, selected_questionnaire_id = _questionnaire_rule_matches(matched_rule, audience_config, event)
            if questionnaire_id_matched:
                target_stage = _rule_target_stage(matched_rule) or STAGE_OPERATING
                reason = "audience_entry_rule_questionnaire_submitted"
            else:
                target_stage = current_stage
                reason = "questionnaire_id_not_matched"
        else:
            target_stage = STAGE_OPERATING
            reason = "questionnaire_submitted"
    elif event_type == EVENT_PAYMENT_SUCCEEDED:
        target_stage = STAGE_CONVERTED
        reason = "payment_succeeded"
    elif event_type == EVENT_WEBHOOK_RECEIVED:
        requested = text(payload.get("stage_transition") or payload.get("target_stage"))
        if requested in STAGES:
            target_stage = requested
            reason = "webhook_stage_transition"
        else:
            target_stage = current_stage
            reason = "webhook_no_stage_transition"
    should_create_initial_stage_entry = (
        event_type == EVENT_CHANNEL_ENTERED
        and target_stage == current_stage
        and as_int(membership.get("current_stage_entry_id")) <= 0
    )
    return StageTransitionResult(
        target_stage=target_stage,
        changed=target_stage != current_stage or should_create_initial_stage_entry,
        entry_reason=reason,
        diagnostics={
            "event_type": event_type,
            "previous_stage": current_stage,
            "target_stage": target_stage,
            "audience_entry_rule_loaded": bool(audience_config),
            "matched_rule_event": text(matched_rule.get("event")) if matched_rule else "",
            "matched_rule_target": _rule_target_stage(matched_rule) if matched_rule else "",
            "questionnaire_review_enabled": questionnaire_review_enabled,
            "selected_questionnaire_id": selected_questionnaire_id,
            "event_questionnaire_id": event_questionnaire_id,
            "questionnaire_id_matched": questionnaire_id_matched,
        },
    )
