from __future__ import annotations

import json
from typing import Any

from aicrm_next.shared.postgres_connection import get_db

from .domain import (
    CONTENT_AGENT_GENERATED,
    CONTENT_FIXED_MESSAGE,
    CONTENT_LAYERED_MESSAGE,
    LEGACY_CONTENT_MAP,
    LEGACY_TRIGGER_MAP,
    TRIGGER_ON_ENTER_STAGE,
    TRIGGER_SCHEDULED,
    as_int,
    text,
)


def _decode(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if value is None or value == "":
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def normalize_task(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row or {})
    trigger_type = text(item.get("trigger_type")) or "scheduled_daily"
    content_mode = text(item.get("content_mode")) or "unified"
    runtime_trigger = LEGACY_TRIGGER_MAP.get(trigger_type, trigger_type)
    content_type = LEGACY_CONTENT_MAP.get(content_mode, content_mode)
    unified = _decode(item.get("unified_content_json"), {})
    segments = _decode(item.get("segment_contents_json"), [])
    agent = _decode(item.get("agent_config_json"), {})
    trigger_config = _decode(item.get("trigger_config_json"), {}) if "trigger_config_json" in item else {}
    layer_basis = ""
    if content_mode == "profile_layered":
        layer_basis = "profile"
    elif content_mode == "behavior_layered":
        layer_basis = "behavior"
    if content_type == CONTENT_LAYERED_MESSAGE and not layer_basis:
        layer_basis = text(item.get("layer_basis") or agent.get("layer_basis")) or "questionnaire"
    target_stage = text(item.get("target_stage_code") or item.get("target_audience_code")) or "operating"
    day_offset = as_int(item.get("audience_day_offset"), 1)
    schedule_type = text(
        trigger_config.get("schedule_type")
        or item.get("schedule_type")
        or agent.get("schedule_type")
        or unified.get("schedule_type")
    )
    if not schedule_type and runtime_trigger == TRIGGER_SCHEDULED:
        schedule_type = "stage_day_offset" if trigger_type == "scheduled_daily" and day_offset > 1 else "daily_time"
    runtime_v2 = {
        "trigger_type": runtime_trigger,
        "content_type": content_type,
        "trigger_event_type": text(item.get("trigger_event_type") or trigger_config.get("event_type") or agent.get("trigger_event_type")),
        "target_stage": target_stage,
        "schedule_type": schedule_type,
        "send_time": text(item.get("send_time")) or "10:00",
        "day_offset": day_offset,
        "webhook_key": text(item.get("webhook_key") or trigger_config.get("webhook_key") or agent.get("webhook_key")),
        "layer_basis": layer_basis,
    }
    return {
        **item,
        "id": as_int(item.get("id")),
        "program_id": as_int(item.get("program_id")),
        "status": text(item.get("status")) or "draft",
        "trigger_type": trigger_type,
        "content_mode": content_mode,
        "target_stage_code": target_stage,
        "unified_content_json": unified,
        "segment_contents_json": segments,
        "agent_config_json": agent,
        "runtime_v2": runtime_v2,
        "content_type": content_type,
        "trigger_kind": runtime_trigger,
    }


def get_task(task_id: int) -> dict[str, Any] | None:
    row = get_db().execute("SELECT * FROM automation_operation_task WHERE id = ? LIMIT 1", (int(task_id),)).fetchone()
    return normalize_task(dict(row)) if row else None


def list_active_tasks(program_id: int) -> list[dict[str, Any]]:
    rows = get_db().execute(
        "SELECT * FROM automation_operation_task WHERE program_id = ? AND status = 'active' ORDER BY id ASC",
        (int(program_id),),
    ).fetchall()
    return [normalize_task(dict(row)) for row in rows]


def with_runtime_fields(task: dict[str, Any]) -> dict[str, Any]:
    return normalize_task(task)
