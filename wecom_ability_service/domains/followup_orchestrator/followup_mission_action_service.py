from __future__ import annotations

from typing import Any, Mapping

from ..customer_pulse.access import customer_pulse_tenant_context_summary
from . import repo
from .followup_mission_read_service import get_followup_orchestrator_mission_detail_payload
from .service import (
    FOLLOWUP_ORCHESTRATOR_EXECUTOR_ACTION_TYPES,
    FOLLOWUP_ORCHESTRATOR_MAX_MISSION_ITEMS,
    FOLLOWUP_ORCHESTRATOR_MISSION_ACTIONS,
    FOLLOWUP_ORCHESTRATOR_REJECTABLE_ACTIONS,
    _assert_mission_items_accessible,
    _build_handoff_packet,
    _decorate_item,
    _feature_gate_context,
    _normalized_text,
    _record_orchestrator_activity,
    _resolved_followup_read_scope,
    _stable_mission_status,
    _summarize_mission_items,
    _undo_restored_item_status as _legacy_undo_restored_item_status,
    _with_item_runtime_payload,
    execute_customer_pulse_card_action,
    preview_customer_pulse_card_action,
    undo_customer_pulse_card_action_execution,
)


def _resolved_mission_item_context(
    *,
    mission_key: str,
    mission_item_key: str,
    access_context: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], str, dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
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
    if _normalized_text(action_type) == "generate_reply_draft":
        return "draft_ready"
    return "executed"


def _undo_restored_item_status(item: Mapping[str, Any], decision: Mapping[str, Any] | None) -> str:
    return _legacy_undo_restored_item_status(item, decision)


def preview_followup_orchestrator_mission_item_action(
    *,
    mission_key: str,
    mission_item_key: str,
    action_type: str = "",
    actor_userid: str = "",
    operator: str = "",
    access_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Internal owner for mission-item action preview."""
    context, tenant_key, mission, item, decision, _read_scope = _resolved_mission_item_context(
        mission_key=mission_key,
        mission_item_key=mission_item_key,
        access_context=access_context,
    )
    resolved_action_type = _normalized_text(action_type) or _normalized_text((item.get("payload") or {}).get("suggested_action_type"))
    if resolved_action_type not in FOLLOWUP_ORCHESTRATOR_EXECUTOR_ACTION_TYPES:
        raise ValueError("unsupported executor action_type")
    if int(item.get("pulse_card_id") or 0) <= 0:
        raise ValueError("mission item is not linked to customer_pulse card")
    preview = preview_customer_pulse_card_action(
        int(item.get("pulse_card_id") or 0),
        action_type=resolved_action_type,
        track_click=False,
        operator=_normalized_text(operator),
        tenant_context=dict(context or {}),
        tenant_key=tenant_key,
    )
    return {
        "mission_key": _normalized_text(mission.get("mission_key")),
        "mission_item_key": _normalized_text(item.get("mission_item_key")),
        "tenant_context": customer_pulse_tenant_context_summary(context),
        "actor_userid": _normalized_text(actor_userid) or _normalized_text(context.get("actor_userid") or context.get("user_id")),
        "preview": preview,
        "item": _decorate_item(item, decision=decision),
    }


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
            pulse_execution.get("activity_log_id")
            or pulse_result.get("activity_log_id")
            or 0
        ),
        active_assignee_userid=_normalized_text(actor_userid) or _normalized_text(item.get("suggested_assignee_userid")) or _normalized_text(item.get("owner_userid")),
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


def execute_followup_orchestrator_mission_item_action(
    *,
    mission_key: str,
    mission_item_key: str,
    action_type: str = "",
    actor_userid: str,
    actor_role: str,
    operator: str,
    note: str = "",
    extra_payload: Mapping[str, Any] | None = None,
    access_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Internal owner for mission-item action execution."""
    context, tenant_key, mission, item, decision, _read_scope = _resolved_mission_item_context(
        mission_key=mission_key,
        mission_item_key=mission_item_key,
        access_context=access_context,
    )
    resolved_action_type = _normalized_text(action_type) or _normalized_text((item.get("payload") or {}).get("suggested_action_type"))
    if resolved_action_type not in FOLLOWUP_ORCHESTRATOR_EXECUTOR_ACTION_TYPES:
        raise ValueError("unsupported executor action_type")
    execution_result = _execute_followup_orchestrator_item_action(
        mission=mission,
        item=item,
        decision=decision,
        action_type=resolved_action_type,
        actor_userid=actor_userid,
        actor_role=actor_role,
        operator=operator,
        note=note,
        extra_payload=extra_payload,
        tenant_context=context,
        tenant_key=tenant_key,
    )
    return {
        "mission": get_followup_orchestrator_mission_detail_payload(
            mission_key=_normalized_text(mission.get("mission_key")),
            access_context=context,
            tenant_key=tenant_key,
        ),
        "mission_item_key": _normalized_text(mission_item_key),
        "action_type": resolved_action_type,
        **execution_result,
    }


def undo_followup_orchestrator_mission_item_action(
    *,
    mission_key: str,
    mission_item_key: str,
    execution_id: int = 0,
    actor_userid: str,
    actor_role: str,
    operator: str,
    access_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Internal owner for mission-item action undo."""
    context, tenant_key, mission, item, decision, _read_scope = _resolved_mission_item_context(
        mission_key=mission_key,
        mission_item_key=mission_item_key,
        access_context=access_context,
    )
    payload = dict(item.get("payload") or {})
    resolved_execution_id = int(execution_id or payload.get("latest_pulse_execution_id") or ((payload.get("latest_pulse_execution") or {}).get("id") or 0))
    if resolved_execution_id <= 0:
        raise ValueError("missing execution_id")
    undo_result = undo_customer_pulse_card_action_execution(
        resolved_execution_id,
        operator=_normalized_text(operator),
        tenant_context=dict(context or {}),
        tenant_key=tenant_key,
    )
    next_execution_state = "pending_approval" if bool(((decision or {}).get("payload") or {}).get("needs_manager_approval")) and _normalized_text((decision or {}).get("decision_status")) in {"", "suggested"} else "not_started"
    updated_item = repo.update_followup_orchestrator_mission_item(
        int(item.get("id") or 0),
        tenant_key=tenant_key,
        item_status=_undo_restored_item_status(item, decision=decision),
        payload_json=_with_item_runtime_payload(
            payload,
            execution_state=next_execution_state,
            latest_pulse_execution=dict(undo_result.get("execution") or {}),
            latest_pulse_result=dict(undo_result or {}),
            latest_pulse_execution_id=int((undo_result.get("execution") or {}).get("id") or 0),
            latest_pulse_activity_log_id=int((undo_result.get("undo_activity") or {}).get("id") or 0),
            latest_pulse_action_type=_normalized_text((undo_result.get("execution") or {}).get("action_type")),
        ),
    )
    orchestrator_log = repo.insert_followup_orchestrator_execution_log(
        tenant_key=tenant_key,
        mission_id=int(mission.get("id") or 0),
        mission_item_id=int(updated_item.get("id") or 0),
        action_type="undo_customer_pulse_execution",
        execution_status="undone",
        operator=_normalized_text(operator),
        actor_userid=_normalized_text(actor_userid),
        actor_role=_normalized_text(actor_role),
        resource_type="followup_orchestrator_mission_item",
        resource_id=_normalized_text(item.get("mission_item_key")),
        tenant_context=context,
        request_payload={"execution_id": resolved_execution_id},
        result_payload=undo_result,
        error_message="",
    )
    return {
        "mission": get_followup_orchestrator_mission_detail_payload(
            mission_key=_normalized_text(mission.get("mission_key")),
            access_context=context,
            tenant_key=tenant_key,
        ),
        "mission_item_key": _normalized_text(mission_item_key),
        "execution": dict(undo_result.get("execution") or {}),
        "undo_result": undo_result,
        "orchestrator_log": orchestrator_log,
    }


def apply_followup_orchestrator_mission_action(
    *,
    mission_key: str,
    action_type: str,
    actor_userid: str,
    actor_role: str,
    operator: str,
    tenant_context: Mapping[str, Any] | None = None,
    mission_item_key: str = "",
    note: str = "",
) -> dict[str, Any]:
    """Internal owner for mission-level batch and approval actions."""
    context = dict(tenant_context or {})
    read_scope = _resolved_followup_read_scope(access_context=context)
    tenant_key = _normalized_text(read_scope.get("tenant_key")) or _normalized_text(context.get("tenant_key")) or "aicrm"
    mission = repo.get_followup_orchestrator_mission_by_key(_normalized_text(mission_key), tenant_key=tenant_key)
    if not mission:
        raise LookupError("mission not found")
    items = repo.list_followup_orchestrator_mission_items(
        tenant_key=tenant_key,
        mission_id=int(mission.get("id") or 0),
        limit=FOLLOWUP_ORCHESTRATOR_MAX_MISSION_ITEMS,
    )
    target_items = items
    normalized_item_key = _normalized_text(mission_item_key)
    if normalized_item_key:
        target_items = [item for item in items if _normalized_text(item.get("mission_item_key")) == normalized_item_key]
        if not target_items:
            raise LookupError("mission item not found")
    normalized_action = _normalized_text(action_type)
    if normalized_action not in FOLLOWUP_ORCHESTRATOR_MISSION_ACTIONS:
        raise ValueError("unsupported action_type")
    _assert_mission_items_accessible(target_items, read_scope=read_scope, action_type=normalized_action)
    updated_items: list[dict[str, Any]] = []
    updated_decisions: list[dict[str, Any]] = []
    batch_execution_results: list[dict[str, Any]] = []
    for item in target_items:
        next_item_status = _normalized_text(item.get("item_status"))
        next_assignment_status = _normalized_text(item.get("assignment_status"))
        decision = repo.get_followup_orchestrator_assignment_decision_for_item(
            mission_item_id=int(item.get("id") or 0),
            tenant_key=tenant_key,
        )
        decision_update: dict[str, Any] = {}
        payload = dict(item.get("payload") or {})
        if normalized_action in {"accept", "claim"}:
            next_item_status = "accepted"
            next_assignment_status = "accepted" if decision else next_assignment_status or "accepted"
            payload = _with_item_runtime_payload(
                payload,
                execution_state="not_started",
                active_assignee_userid=_normalized_text(actor_userid) or _normalized_text(item.get("suggested_assignee_userid")) or _normalized_text(item.get("owner_userid")),
            )
            decision_update = {"decision_status": "accepted", "decided_by_userid": _normalized_text(actor_userid)}
            _record_orchestrator_activity(
                item=item,
                tenant_key=tenant_key,
                operator=operator,
                activity_type=f"orchestrator_{normalized_action}",
                activity_status="accepted",
                title="已接受团队任务包" if normalized_action == "accept" else "已认领客户项",
                summary=_normalized_text(note) or ("当前客户项已由负责人接手处理。" if normalized_action == "accept" else "当前客户项已由团队成员认领。"),
                payload={"mission_key": _normalized_text(mission.get("mission_key")), "mission_item_key": _normalized_text(item.get("mission_item_key"))},
            )
        elif normalized_action == "request_manager_approval":
            next_item_status = "approved"
            next_assignment_status = "approved" if decision else next_assignment_status or "approved"
            handoff_packet = _build_handoff_packet(
                mission=mission,
                item=_decorate_item({**dict(item), "payload": payload}, decision=decision),
                decision={
                    **dict(decision or {}),
                    "decision_status": "approved",
                    "payload": {**dict((decision or {}).get("payload") or {}), "needs_manager_approval": bool(((decision or {}).get("payload") or {}).get("needs_manager_approval"))},
                },
                tenant_context=context,
                tenant_key=tenant_key,
            )
            payload = _with_item_runtime_payload(
                payload,
                execution_state="executed",
                handoff_packet=handoff_packet,
                active_assignee_userid=_normalized_text(item.get("suggested_assignee_userid")) or _normalized_text(item.get("owner_userid")),
            )
            decision_update = {
                "decision_status": "approved",
                "approved_by_userid": _normalized_text(actor_userid),
                "payload_json": {
                    **dict((decision or {}).get("payload") or {}),
                    "handoff_packet": handoff_packet,
                },
            }
            _record_orchestrator_activity(
                item=item,
                tenant_key=tenant_key,
                operator=operator,
                activity_type="orchestrator_handoff_approved",
                activity_status="completed",
                title="已批准转派接力",
                summary=_normalized_text(note) or "经理已批准当前客户项的接力建议，已生成 handoff packet。",
                payload={"handoff_packet": handoff_packet, "mission_key": _normalized_text(mission.get("mission_key"))},
            )
        elif normalized_action == "escalate":
            next_item_status = "escalated"
            next_assignment_status = "approved" if decision else next_assignment_status or "approved"
            payload["manual_escalation_note"] = _normalized_text(note) or "用户手动触发升级"
            payload = _with_item_runtime_payload(payload, execution_state="escalated")
            decision_update = {"decision_status": "approved", "approved_by_userid": _normalized_text(actor_userid)} if decision else {}
            _record_orchestrator_activity(
                item=item,
                tenant_key=tenant_key,
                operator=operator,
                activity_type="orchestrator_escalation",
                activity_status="completed",
                title="已升级处理",
                summary=_normalized_text(note) or "当前客户项已升级处理。",
                payload={"mission_key": _normalized_text(mission.get("mission_key"))},
            )
        elif normalized_action == "complete":
            next_item_status = "completed"
            next_assignment_status = "completed" if decision else next_assignment_status or "completed"
            payload["completed_note"] = _normalized_text(note) or "用户标记为已完成"
            payload = _with_item_runtime_payload(payload, execution_state="completed")
            decision_update = {"decision_status": "completed", "decided_by_userid": _normalized_text(actor_userid)} if decision else {}
            _record_orchestrator_activity(
                item=item,
                tenant_key=tenant_key,
                operator=operator,
                activity_type="orchestrator_completed",
                activity_status="completed",
                title="已完成团队任务项",
                summary=_normalized_text(note) or "当前客户项已完成。",
                payload={"mission_key": _normalized_text(mission.get("mission_key"))},
            )
        elif normalized_action == "prebuild_batch_draft":
            try:
                execution_result = _execute_followup_orchestrator_item_action(
                    mission=mission,
                    item=item,
                    decision=decision,
                    action_type="generate_reply_draft",
                    actor_userid=actor_userid,
                    actor_role=actor_role,
                    operator=operator,
                    note=note,
                    extra_payload={},
                    tenant_context=context,
                    tenant_key=tenant_key,
                )
                updated_items.append(execution_result["item"])
                if execution_result.get("decision"):
                    updated_decisions.append(execution_result["decision"])
                batch_execution_results.append(
                    {
                        "mission_item_key": _normalized_text(item.get("mission_item_key")),
                        "external_userid": _normalized_text(item.get("external_userid")),
                        "status": "success",
                        "pulse_execution_id": int((execution_result.get("pulse_execution") or {}).get("id") or 0),
                        "activity_log_id": int(((execution_result.get("pulse_result") or {}).get("activity_log_id") or 0)),
                    }
                )
            except Exception as exc:
                failed_payload = {
                    **payload,
                    "batch_draft_prebuild_requested": True,
                    "last_batch_error": str(exc),
                }
                failed_item = repo.update_followup_orchestrator_mission_item(
                    int(item.get("id") or 0),
                    tenant_key=tenant_key,
                    item_status=_normalized_text(item.get("item_status")) or "accepted",
                    assignment_status=_normalized_text(item.get("assignment_status")) or "accepted",
                    payload_json=failed_payload,
                )
                updated_items.append(failed_item)
                batch_execution_results.append(
                    {
                        "mission_item_key": _normalized_text(item.get("mission_item_key")),
                        "external_userid": _normalized_text(item.get("external_userid")),
                        "status": "failed",
                        "error": str(exc),
                    }
                )
                repo.insert_followup_orchestrator_execution_log(
                    tenant_key=tenant_key,
                    mission_id=int(mission.get("id") or 0),
                    mission_item_id=int(item.get("id") or 0),
                    action_type="execute_generate_reply_draft",
                    execution_status="failed",
                    operator=_normalized_text(operator),
                    actor_userid=_normalized_text(actor_userid),
                    actor_role=_normalized_text(actor_role),
                    resource_type="followup_orchestrator_mission_item",
                    resource_id=_normalized_text(item.get("mission_item_key")),
                    tenant_context=context,
                    request_payload={"action_type": "generate_reply_draft", "note": _normalized_text(note)},
                    result_payload={"error": str(exc)},
                    error_message=str(exc),
                )
            continue
        elif normalized_action in FOLLOWUP_ORCHESTRATOR_REJECTABLE_ACTIONS:
            next_item_status = "skipped"
            next_assignment_status = "rejected" if decision else next_assignment_status or "rejected"
            payload["skip_reason"] = _normalized_text(note) or normalized_action
            payload = _with_item_runtime_payload(payload, execution_state="skipped")
            decision_update = {"decision_status": "rejected", "decided_by_userid": _normalized_text(actor_userid)} if decision else {}
            _record_orchestrator_activity(
                item=item,
                tenant_key=tenant_key,
                operator=operator,
                activity_type=f"orchestrator_{normalized_action}",
                activity_status="completed",
                title="已标记阻塞" if normalized_action == "mark_blocked" else "已跳过客户项",
                summary=_normalized_text(note) or ("当前客户项已标记阻塞。" if normalized_action == "mark_blocked" else "当前客户项已跳过。"),
                payload={"mission_key": _normalized_text(mission.get("mission_key"))},
            )
        elif normalized_action == "suggest_assignment":
            payload = _with_item_runtime_payload(payload, execution_state="pending_approval")
            decision_update = {"decision_status": "suggested", "decided_by_userid": _normalized_text(actor_userid)} if decision else {}
            _record_orchestrator_activity(
                item=item,
                tenant_key=tenant_key,
                operator=operator,
                activity_type="orchestrator_assignment_suggested",
                activity_status="pending",
                title="已建议转派接力",
                summary=_normalized_text(note) or "当前客户项已提出转派接力建议，等待审批。",
                payload={"mission_key": _normalized_text(mission.get("mission_key"))},
            )
        updated_item = repo.update_followup_orchestrator_mission_item(
            int(item.get("id") or 0),
            tenant_key=tenant_key,
            item_status=next_item_status,
            assignment_status=next_assignment_status,
            payload_json=payload,
        )
        updated_items.append(updated_item)
        if decision:
            updated_decision = repo.update_followup_orchestrator_assignment_decision(
                int(decision.get("id") or 0),
                tenant_key=tenant_key,
                **decision_update,
            )
            updated_decisions.append(updated_decision)
        repo.insert_followup_orchestrator_execution_log(
            tenant_key=tenant_key,
            mission_id=int(mission.get("id") or 0),
            mission_item_id=int(item.get("id") or 0),
            action_type=normalized_action,
            execution_status="accepted" if normalized_action in {"accept", "claim", "request_manager_approval"} else next_item_status,
            operator=_normalized_text(operator),
            actor_userid=_normalized_text(actor_userid),
            actor_role=_normalized_text(actor_role),
            resource_type="followup_orchestrator_mission_item",
            resource_id=_normalized_text(item.get("mission_item_key")),
            tenant_context=context,
            request_payload={"note": _normalized_text(note), "action_type": normalized_action},
            result_payload={"item_status": next_item_status, "assignment_status": next_assignment_status},
        )
    refreshed_items = repo.list_followup_orchestrator_mission_items(
        tenant_key=tenant_key,
        mission_id=int(mission.get("id") or 0),
        limit=FOLLOWUP_ORCHESTRATOR_MAX_MISSION_ITEMS,
    )
    refreshed_status, refreshed_count = _summarize_mission_items(refreshed_items)
    stable_mission_status = _stable_mission_status(mission)
    if stable_mission_status and normalized_action not in {"accept", "claim", "request_manager_approval", "prebuild_batch_draft"}:
        refreshed_status = _normalized_text(mission.get("mission_status"))
    refreshed_mission = repo.update_followup_orchestrator_mission(
        int(mission.get("id") or 0),
        tenant_key=tenant_key,
        mission_status=refreshed_status,
        item_count=refreshed_count,
        payload_json={
            **dict(mission.get("payload") or {}),
            "last_action_note": _normalized_text(note),
            "last_action_type": normalized_action,
            "last_action_results": batch_execution_results if batch_execution_results else [],
        },
    )
    return {
        "mission": get_followup_orchestrator_mission_detail_payload(
            mission_key=_normalized_text(refreshed_mission.get("mission_key")),
            tenant_key=tenant_key,
            access_context=context,
        ),
        "updated_items": updated_items,
        "updated_decisions": updated_decisions,
    }
