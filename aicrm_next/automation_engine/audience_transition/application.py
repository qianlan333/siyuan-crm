from __future__ import annotations

from typing import Any

from .domain import AudienceTransitionEvent, base_realtime_result
from aicrm_next.shared.postgres_connection import get_db

from .integration_gateway import OperationTaskRealtimeTriggerGateway
from .repository import AudienceTransitionRepository


def _safe_rollback() -> None:
    connections = []
    try:
        from flask import g, has_app_context

        if has_app_context():
            for name in ("next_db", "db"):
                db = getattr(g, name, None)
                if db is not None:
                    connections.append(db)
    except Exception:
        pass
    try:
        connections.append(get_db())
    except Exception:
        pass
    for db in connections:
        try:
            db.rollback()
        except Exception:
            continue


def _normalise_trigger_result(event: AudienceTransitionEvent, result: dict[str, Any]) -> dict[str, Any]:
    payload = base_realtime_result(event)
    results = list(result.get("results") or [])
    payload.update(
        {
            "realtime_operation_tasks_ran": int(result.get("ran") or len(results) or 0),
            "realtime_operation_tasks_enqueued_count": int(result.get("enqueued_count") or 0),
            "realtime_operation_tasks_results": results,
            "realtime_operation_tasks_error": "" if result.get("ok", True) else str(result.get("error") or result.get("reason") or ""),
            "realtime_operation_tasks_reason": str(result.get("reason") or ""),
            "side_effect_plan": dict(result.get("side_effect_plan") or {}),
        }
    )
    return payload


def trigger_realtime_operation_tasks_for_event(
    event: AudienceTransitionEvent,
    *,
    gateway: OperationTaskRealtimeTriggerGateway | None = None,
) -> dict[str, Any]:
    if not event.is_complete():
        payload = base_realtime_result(event)
        payload["realtime_operation_tasks_error"] = "audience_transition_event_incomplete"
        payload["realtime_operation_tasks_reason"] = "audience_transition_event_incomplete"
        return payload
    try:
        result = (gateway or OperationTaskRealtimeTriggerGateway()).trigger(event)
        return _normalise_trigger_result(event, dict(result or {}))
    except Exception as exc:
        _safe_rollback()
        payload = base_realtime_result(event)
        payload["realtime_operation_tasks_error"] = str(exc)
        return payload


def handle_committed_audience_transition(
    *,
    member_id: int = 0,
    external_userid: str = "",
    operator_id: str = "",
    entry_source: str = "",
    repository: AudienceTransitionRepository | None = None,
    gateway: OperationTaskRealtimeTriggerGateway | None = None,
) -> dict[str, Any]:
    try:
        event = (repository or AudienceTransitionRepository()).build_current_event(
            member_id=int(member_id or 0),
            external_userid=external_userid,
            operator_id=operator_id,
            entry_source=entry_source,
        )
    except Exception as exc:
        _safe_rollback()
        payload = base_realtime_result(None)
        payload["realtime_operation_tasks_error"] = str(exc)
        payload["realtime_operation_tasks_reason"] = "audience_transition_event_build_failed"
        return payload
    if not event:
        payload = base_realtime_result(None)
        payload["realtime_operation_tasks_error"] = "audience_transition_event_not_found"
        payload["realtime_operation_tasks_reason"] = "audience_transition_event_not_found"
        return payload
    return trigger_realtime_operation_tasks_for_event(event, gateway=gateway)
