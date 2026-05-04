from __future__ import annotations

from typing import Any, Mapping

from .mission_assignment_service import _mission_title
from .service import (
    FOLLOWUP_ORCHESTRATOR_EXECUTION_STATES,
    FOLLOWUP_ORCHESTRATOR_RULES_VERSION,
    _decision_status_label,
    _execution_state_label,
    _mission_status_label,
    _normalized_text,
)


def _current_item_execution_state(
    item: Mapping[str, Any],
    *,
    decision: Mapping[str, Any] | None,
) -> str:
    """Internal only: derive the current execution state shown on mission items."""
    payload = dict(item.get("payload") or {})
    normalized_payload_state = _normalized_text(payload.get("execution_state"))
    if normalized_payload_state in FOLLOWUP_ORCHESTRATOR_EXECUTION_STATES:
        return normalized_payload_state
    item_status = _normalized_text(item.get("item_status"))
    decision_payload = dict((decision or {}).get("payload") or {})
    decision_status = _normalized_text((decision or {}).get("decision_status"))
    if item_status == "completed":
        return "completed"
    if item_status == "skipped":
        return "skipped"
    if item_status == "escalated":
        return "escalated"
    if bool(decision_payload.get("needs_manager_approval")) and decision_status in {"", "suggested", "accepted"}:
        return "pending_approval"
    latest_pulse_execution = dict(payload.get("latest_pulse_execution") or {})
    if latest_pulse_execution and _normalized_text(latest_pulse_execution.get("execution_status")) == "confirmed":
        if _normalized_text(latest_pulse_execution.get("action_type")) == "generate_reply_draft":
            return "draft_ready"
        return "executed"
    return "not_started"


def _decorate_mission(
    mission: Mapping[str, Any],
    *,
    items: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    logs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Internal only: build the stable admin/read payload for a mission."""
    payload = dict(mission.get("payload") or {})
    return {
        **dict(mission),
        "title": _mission_title(_normalized_text(mission.get("mission_type"))),
        "mission_status_label": _mission_status_label(mission.get("mission_status")),
        "items": items,
        "decisions": decisions,
        "execution_logs": logs,
        "evidence_refs": list(payload.get("evidence_refs") or []),
        "rules_version": _normalized_text(payload.get("rules_version")) or FOLLOWUP_ORCHESTRATOR_RULES_VERSION,
        "ai_enhancement": dict(payload.get("ai_enhancement") or {}) if isinstance(payload.get("ai_enhancement"), dict) else {},
    }


def _decorate_item(item: Mapping[str, Any], *, decision: Mapping[str, Any] | None) -> dict[str, Any]:
    """Internal only: build the stable admin/read payload for a mission item."""
    payload = dict(item.get("payload") or {})
    execution_state = _current_item_execution_state(item, decision=decision)
    return {
        **dict(item),
        "item_status_label": _mission_status_label(item.get("item_status")),
        "assignment_status_label": _decision_status_label(item.get("assignment_status")),
        "signals": payload.get("signals") or {},
        "why_now": _normalized_text(payload.get("why_now")),
        "title": _normalized_text(payload.get("title")),
        "current_judgement": _normalized_text(payload.get("current_judgement")),
        "suggested_action_type": _normalized_text(payload.get("suggested_action_type")),
        "suggested_action_label": _normalized_text(payload.get("suggested_action_label")),
        "stage_key": _normalized_text(payload.get("stage_key")),
        "stage_label": _normalized_text(payload.get("stage_label")),
        "owner_display_name": _normalized_text(payload.get("owner_display_name")),
        "batchable": bool(payload.get("batchable")),
        "batch_group_key": _normalized_text(payload.get("batch_group_key")),
        "escalation_reason": _normalized_text(payload.get("escalation_reason")),
        "rule_reasons": list(payload.get("rule_reasons") or []),
        "risk_flags": list(payload.get("risk_flags") or []),
        "opportunity_flags": list(payload.get("opportunity_flags") or []),
        "draft_blocked_by_ai": bool(payload.get("draft_blocked_by_ai")),
        "ai_draft_suggestion": dict(payload.get("ai_draft_suggestion") or {}) if isinstance(payload.get("ai_draft_suggestion"), dict) else {},
        "execution_state": execution_state,
        "execution_state_label": _execution_state_label(execution_state),
        "handoff_packet": dict(payload.get("handoff_packet") or {}) if isinstance(payload.get("handoff_packet"), dict) else {},
        "latest_pulse_execution": dict(payload.get("latest_pulse_execution") or {}) if isinstance(payload.get("latest_pulse_execution"), dict) else {},
        "latest_pulse_result": dict(payload.get("latest_pulse_result") or {}) if isinstance(payload.get("latest_pulse_result"), dict) else {},
        "active_assignee_userid": _normalized_text(payload.get("active_assignee_userid")) or _normalized_text(item.get("suggested_assignee_userid")),
        "decision": dict(decision or {}),
    }


__all__ = ["_current_item_execution_state", "_decorate_item", "_decorate_mission"]
