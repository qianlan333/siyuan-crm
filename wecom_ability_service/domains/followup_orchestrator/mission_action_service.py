from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from ..customer_pulse import execute_customer_pulse_card_action, get_customer_pulse_card_payload
from ..customer_pulse import repo as customer_pulse_repo
from . import repo
from .service import (
    FOLLOWUP_ORCHESTRATOR_FLAG_KEY,
    _assert_mission_items_accessible,
    _execution_state_label,
    _feature_gate_context,
    _normalized_text,
    _resolved_followup_read_scope,
    _sha_token,
)


def _resolved_mission_item_context(
    *,
    mission_key: str,
    mission_item_key: str,
    access_context: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], str, dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Internal only: resolve mission/item/decision runtime context for item actions."""
    read_scope = _resolved_followup_read_scope(access_context=access_context)
    context = _feature_gate_context(access_context)
    tenant_key = _normalized_text(read_scope.get("tenant_key")) or _normalized_text(context.get("tenant_key")) or "aicrm"
    mission = repo.get_followup_orchestrator_mission_by_key(_normalized_text(mission_key), tenant_key=tenant_key)
    if not mission:
        raise LookupError("mission not found")
    item = repo.get_followup_orchestrator_mission_item_by_key(_normalized_text(mission_item_key), tenant_key=tenant_key)
    if not item or int(item.get("mission_id") or 0) != int(mission.get("id") or 0):
        raise LookupError("mission item not found")
    _assert_mission_items_accessible([item], read_scope=read_scope)
    decision = repo.get_followup_orchestrator_assignment_decision_for_item(
        mission_item_id=int(item.get("id") or 0),
        tenant_key=tenant_key,
    ) or {}
    return context, tenant_key, mission, item, decision, read_scope


def _executor_execution_state(action_type: str) -> str:
    """Internal only: normalize pulse action type into orchestrator execution state."""
    if _normalized_text(action_type) == "generate_reply_draft":
        return "draft_ready"
    return "executed"


def _undo_restored_item_status(item: Mapping[str, Any], decision: Mapping[str, Any] | None) -> str:
    """Internal only: decide which item status should be restored by undo."""
    current_status = _normalized_text(item.get("item_status"))
    if current_status in {"accepted", "approved", "suggested", "unassigned"}:
        return current_status
    decision_status = _normalized_text((decision or {}).get("decision_status"))
    if decision_status == "approved":
        return "approved"
    if decision_status in {"accepted", "completed"}:
        return "accepted"
    if _normalized_text(item.get("owner_userid")) or _normalized_text(item.get("suggested_assignee_userid")):
        return "accepted"
    return "suggested"


def _artifact_status_from_card_payload(card_payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """Internal only: derive handoff artifact status from pulse card payload."""
    latest_execution = dict((card_payload or {}).get("latest_execution") or {})
    recent_activities = [dict(item) for item in ((card_payload or {}).get("recent_activities") or []) if isinstance(item, dict)]
    has_open_activity = lambda activity_type: any(
        _normalized_text(item.get("activity_type")) == activity_type and not _normalized_text(item.get("undone_at"))
        for item in recent_activities
    )
    latest_action_type = _normalized_text(latest_execution.get("action_type"))
    latest_action_status = _normalized_text(latest_execution.get("execution_status"))
    return {
        "draft_ready": bool(
            latest_action_type == "generate_reply_draft"
            and latest_action_status == "confirmed"
            and not _normalized_text(latest_execution.get("undone_at"))
        ),
        "followup_task_open": has_open_activity("followup_task"),
        "reminder_scheduled": has_open_activity("followup_reminder"),
        "stage_updated": has_open_activity("followup_segment_update"),
        "tags_updated": has_open_activity("tag_update"),
        "latest_action_type": latest_action_type,
        "latest_action_status": latest_action_status,
    }


def _build_handoff_packet(
    *,
    mission: Mapping[str, Any],
    item: Mapping[str, Any],
    decision: Mapping[str, Any] | None,
    tenant_context: Mapping[str, Any],
    tenant_key: str,
) -> dict[str, Any]:
    """Internal only: build the handoff payload shown on mission item details."""
    card_payload: dict[str, Any] = {}
    pulse_card_id = int(item.get("pulse_card_id") or 0)
    if pulse_card_id > 0:
        try:
            card_payload = get_customer_pulse_card_payload(
                pulse_card_id,
                tenant_context=dict(tenant_context or {}),
                tenant_key=tenant_key,
            )
        except Exception:
            card_payload = {}
    recent_activities = [dict(activity) for activity in (card_payload.get("recent_activities") or []) if isinstance(activity, dict)]
    recent_key_events = [
        {
            "title": _normalized_text(activity.get("title")),
            "summary": _normalized_text(activity.get("summary")),
            "created_at": _normalized_text(activity.get("created_at")),
            "activity_type": _normalized_text(activity.get("activity_type")),
        }
        for activity in recent_activities[:3]
    ]
    recent_event_summary = "；".join(
        filter(
            None,
            [
                " / ".join(filter(None, [_normalized_text(event.get("title")), _normalized_text(event.get("created_at"))]))
                for event in recent_key_events
            ],
        )
    )
    mission_recommendation = dict((mission.get("ai_enhancement") or {}).get("recommendation") or {})
    return {
        "mission_key": _normalized_text(mission.get("mission_key")),
        "mission_title": _normalized_text(mission_recommendation.get("missionTitle")) or _normalized_text(mission.get("title")),
        "handoff_summary": _normalized_text(mission.get("handoff_summary")) or _normalized_text(mission_recommendation.get("handoffSummary")),
        "current_judgement": _normalized_text(item.get("current_judgement")),
        "next_action_suggestion": _normalized_text(item.get("suggested_action_label")),
        "next_action_type": _normalized_text(item.get("suggested_action_type")),
        "why_now": _normalized_text(item.get("why_now")),
        "recent_event_summary": recent_event_summary,
        "recent_key_events": recent_key_events,
        "evidence_refs": list(item.get("evidence_refs") or []),
        "artifact_status": _artifact_status_from_card_payload(card_payload),
        "latest_execution": dict(card_payload.get("latest_execution") or {}),
        "decision": {
            "decision_type": _normalized_text((decision or {}).get("decision_type")),
            "decision_status": _normalized_text((decision or {}).get("decision_status")),
            "current_owner_userid": _normalized_text((decision or {}).get("current_owner_userid")),
            "suggested_owner_userid": _normalized_text((decision or {}).get("suggested_owner_userid")),
            "reason": _normalized_text(((decision or {}).get("payload") or {}).get("reason")),
        },
        "generated_at": datetime.now().replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S"),
    }


def _record_orchestrator_activity(
    *,
    item: Mapping[str, Any],
    tenant_key: str,
    operator: str,
    activity_type: str,
    activity_status: str,
    title: str,
    summary: str,
    payload: Mapping[str, Any] | None = None,
    due_at: str = "",
    idempotency_key: str = "",
) -> dict[str, Any]:
    """Internal only: write a customer pulse activity log for followup actions."""
    pulse_card_id = int(item.get("pulse_card_id") or 0)
    if pulse_card_id <= 0:
        return {}
    try:
        return customer_pulse_repo.insert_customer_pulse_activity_log(
            card_id=pulse_card_id,
            external_userid=_normalized_text(item.get("external_userid")),
            owner_userid=_normalized_text(item.get("owner_userid")),
            activity_type=activity_type,
            activity_status=activity_status,
            title=title,
            summary=summary,
            operator=_normalized_text(operator) or "crm_console",
            due_at=_normalized_text(due_at),
            activity_source=FOLLOWUP_ORCHESTRATOR_FLAG_KEY,
            tenant_key=tenant_key,
            execution_key=_sha_token(activity_type, _normalized_text(item.get("mission_item_key")), length=16),
            idempotency_key=idempotency_key
            or _sha_token(
                _normalized_text(item.get("mission_item_key")),
                activity_type,
                _normalized_text(summary),
                length=20,
            ),
            payload=dict(payload or {}),
        )
    except Exception:
        return {}


def _with_item_runtime_payload(
    item_payload: Mapping[str, Any],
    *,
    execution_state: str | None = None,
    latest_pulse_execution: Mapping[str, Any] | None = None,
    latest_pulse_result: Mapping[str, Any] | None = None,
    latest_pulse_action_type: str = "",
    latest_pulse_execution_id: int = 0,
    latest_pulse_activity_log_id: int = 0,
    handoff_packet: Mapping[str, Any] | None = None,
    active_assignee_userid: str = "",
    latest_orchestrator_activity_id: int = 0,
) -> dict[str, Any]:
    """Internal only: merge runtime execution fields into the stored mission item payload."""
    payload = dict(item_payload or {})
    if execution_state is not None:
        payload["execution_state"] = _normalized_text(execution_state)
        payload["execution_state_label"] = _execution_state_label(execution_state)
    if latest_pulse_execution is not None:
        payload["latest_pulse_execution"] = dict(latest_pulse_execution or {})
    if latest_pulse_result is not None:
        payload["latest_pulse_result"] = dict(latest_pulse_result or {})
    if latest_pulse_action_type:
        payload["latest_pulse_action_type"] = _normalized_text(latest_pulse_action_type)
    if latest_pulse_execution_id:
        payload["latest_pulse_execution_id"] = int(latest_pulse_execution_id)
    if latest_pulse_activity_log_id:
        payload["latest_pulse_activity_log_id"] = int(latest_pulse_activity_log_id)
    if handoff_packet is not None:
        payload["handoff_packet"] = dict(handoff_packet or {})
    if active_assignee_userid:
        payload["active_assignee_userid"] = _normalized_text(active_assignee_userid)
    if latest_orchestrator_activity_id:
        payload["latest_orchestrator_activity_id"] = int(latest_orchestrator_activity_id)
    return payload


def _execute_followup_orchestrator_item_action(
    *,
    mission: Mapping[str, Any],
    item: Mapping[str, Any],
    decision: Mapping[str, Any] | None,
    action_type: str,
    actor_userid: str,
    actor_role: str,
    operator: str,
    note: str,
    extra_payload: Mapping[str, Any] | None,
    tenant_context: Mapping[str, Any] | None,
    tenant_key: str,
) -> dict[str, Any]:
    """Internal only: execute a mission item action and persist runtime state."""
    if int(item.get("pulse_card_id") or 0) <= 0:
        raise ValueError("mission item is not linked to customer_pulse card")
    execution_response = execute_customer_pulse_card_action(
        int(item.get("pulse_card_id") or 0),
        action_type=_normalized_text(action_type),
        operator=_normalized_text(operator),
        extra_payload=dict(extra_payload or {}),
        tenant_context=dict(tenant_context or {}),
        tenant_key=tenant_key,
    )
    pulse_execution = dict(execution_response.get("execution") or {})
    pulse_result = dict(execution_response.get("result") or {})
    payload = _with_item_runtime_payload(
        dict(item.get("payload") or {}),
        execution_state=_executor_execution_state(action_type),
        latest_pulse_execution=pulse_execution,
        latest_pulse_result=pulse_result,
        latest_pulse_action_type=_normalized_text(action_type),
        latest_pulse_execution_id=int(pulse_execution.get("id") or 0),
        latest_pulse_activity_log_id=int(
            pulse_execution.get("activity_log_id") or pulse_result.get("activity_log_id") or 0
        ),
        active_assignee_userid=_normalized_text(actor_userid)
        or _normalized_text(item.get("suggested_assignee_userid"))
        or _normalized_text(item.get("owner_userid")),
    )
    updated_item = repo.update_followup_orchestrator_mission_item(
        int(item.get("id") or 0),
        tenant_key=tenant_key,
        item_status="executing",
        assignment_status=_normalized_text(item.get("assignment_status")) or "accepted",
        payload_json=payload,
    )
    updated_decision = {}
    if decision:
        next_decision_status = _normalized_text(decision.get("decision_status"))
        if next_decision_status in {"", "suggested", "approved"}:
            next_decision_status = "accepted"
        updated_decision = repo.update_followup_orchestrator_assignment_decision(
            int(decision.get("id") or 0),
            tenant_key=tenant_key,
            decision_status=next_decision_status or "accepted",
            decided_by_userid=_normalized_text(actor_userid),
            payload_json={
                **dict(decision.get("payload") or {}),
                "last_executor_action_type": _normalized_text(action_type),
                "last_executor_execution_id": int(pulse_execution.get("id") or 0),
            },
        )
    orchestrator_log = repo.insert_followup_orchestrator_execution_log(
        tenant_key=tenant_key,
        mission_id=int(mission.get("id") or 0),
        mission_item_id=int(updated_item.get("id") or 0),
        action_type=f"execute_{_normalized_text(action_type)}",
        execution_status=_normalized_text(pulse_execution.get("execution_status")) or "confirmed",
        operator=_normalized_text(operator),
        actor_userid=_normalized_text(actor_userid),
        actor_role=_normalized_text(actor_role),
        resource_type="followup_orchestrator_mission_item",
        resource_id=_normalized_text(item.get("mission_item_key")),
        tenant_context=tenant_context,
        request_payload={
            "action_type": _normalized_text(action_type),
            "note": _normalized_text(note),
            "extra_payload": dict(extra_payload or {}),
        },
        result_payload={
            "execution_state": _executor_execution_state(action_type),
            "pulse_execution": pulse_execution,
            "pulse_result": pulse_result,
        },
        error_message="",
    )
    return {
        "item": updated_item,
        "decision": updated_decision,
        "pulse_execution": pulse_execution,
        "pulse_result": pulse_result,
        "orchestrator_log": orchestrator_log,
    }


__all__ = [
    "_artifact_status_from_card_payload",
    "_build_handoff_packet",
    "_execute_followup_orchestrator_item_action",
    "_executor_execution_state",
    "_record_orchestrator_activity",
    "_resolved_mission_item_context",
    "_undo_restored_item_status",
    "_with_item_runtime_payload",
]
