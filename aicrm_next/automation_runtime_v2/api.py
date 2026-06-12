from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from . import process_event_payload, replay_event, replay_membership, run_due_scheduled_tasks
from .domain import AutomationEventInput, EVENT_WEBHOOK_RECEIVED, text
from .runtime_check import check_task_runtime

router = APIRouter()


def _json(payload: Any) -> JSONResponse:
    return JSONResponse(jsonable_encoder(payload))


def verify_webhook_signature(webhook_key: str, payload: dict[str, Any], signature: str = "") -> bool:
    expected = text(payload.get("signature"))
    return not expected or expected == text(signature)


def _parse_now(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(text(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid now") from exc


@router.post("/api/automation-runtime/v2/webhooks/{webhook_key}", name="api.automation_runtime_v2_webhook")
async def automation_runtime_v2_webhook(webhook_key: str, request: Request, x_aicrm_signature: str | None = Header(default="")) -> JSONResponse:
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="payload must be object")
    if not verify_webhook_signature(webhook_key, payload, x_aicrm_signature or ""):
        raise HTTPException(status_code=401, detail="invalid webhook signature")
    external_event_id = text(payload.get("external_event_id") or payload.get("event_id") or payload.get("id"))
    if not external_event_id:
        raise HTTPException(status_code=400, detail="external_event_id required")
    event_input = AutomationEventInput(
        event_type=EVENT_WEBHOOK_RECEIVED,
        source_type="webhook",
        source_id=f"{webhook_key}:{external_event_id}",
        idempotency_key=f"webhook:{webhook_key}:{external_event_id}",
        program_id=int(payload.get("program_id") or 0) or None,
        external_userid=text(payload.get("external_userid")),
        phone=text(payload.get("phone")),
        person_id=int(payload.get("person_id") or 0) or None,
        payload_json={**payload, "webhook_key": webhook_key},
    )
    return _json({"ok": True, "runtime_v2": process_event_payload(event_input)})


@router.post("/api/automation-runtime/v2/scheduled/run-due", name="api.automation_runtime_v2_run_due")
async def automation_runtime_v2_run_due(payload: dict[str, Any]) -> JSONResponse:
    return _json(run_due_scheduled_tasks(program_id=int(payload.get("program_id") or 0) or None, now=_parse_now(payload.get("now"))))


@router.post("/api/automation-runtime/v2/tasks/{task_id}/check", name="api.automation_runtime_v2_task_check")
async def automation_runtime_v2_task_check(task_id: int, payload: dict[str, Any] | None = None) -> JSONResponse:
    return _json(check_task_runtime(int(task_id), payload or {}))


@router.post("/api/automation-runtime/v2/events/{event_id}/replay", name="api.automation_runtime_v2_event_replay")
async def automation_runtime_v2_event_replay(event_id: int, payload: dict[str, Any] | None = None) -> JSONResponse:
    return _json(replay_event(int(event_id), dry_run=bool((payload or {}).get("dry_run", True))))


@router.post("/api/automation-runtime/v2/memberships/{membership_id}/replay", name="api.automation_runtime_v2_membership_replay")
async def automation_runtime_v2_membership_replay(membership_id: int, payload: dict[str, Any] | None = None) -> JSONResponse:
    return _json(replay_membership(int(membership_id), task_ids=list((payload or {}).get("task_ids") or []), dry_run=bool((payload or {}).get("dry_run", True))))
