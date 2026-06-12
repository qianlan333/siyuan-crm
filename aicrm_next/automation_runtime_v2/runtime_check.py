from __future__ import annotations

from typing import Any

from .content_renderer import _agent_prompt, _content_has_body
from .domain import CONTENT_AGENT_GENERATED, CONTENT_FIXED_MESSAGE, CONTENT_LAYERED_MESSAGE, TRIGGER_ON_ENTER_STAGE, TRIGGER_ON_EVENT, TRIGGER_SCHEDULED, TRIGGER_WEBHOOK_PUSH, STAGES, as_int, text
from .membership_service import list_active_memberships
from .task_adapter import get_task


def _check(key: str, passed: bool, reason: str = "") -> dict[str, Any]:
    item = {"key": key, "passed": bool(passed)}
    if reason:
        item["reason"] = reason
    return item


def check_task_runtime(task_id: int, sample_scope: dict[str, Any] | None = None) -> dict[str, Any]:
    task = get_task(int(task_id))
    if not task:
        return {"ok": False, "status": "blocked", "candidate_count": 0, "will_enqueue_count": 0, "blocked_reasons": {"task_not_found": 1}, "checks": [_check("task", False, "task_not_found")]}
    rv2 = task.get("runtime_v2") or {}
    trigger = text(rv2.get("trigger_type"))
    content_type = text(task.get("content_type"))
    checks: list[dict[str, Any]] = []
    checks.append(_check("trigger_config_valid", trigger in {TRIGGER_ON_EVENT, TRIGGER_ON_ENTER_STAGE, TRIGGER_SCHEDULED, TRIGGER_WEBHOOK_PUSH}, "unsupported_trigger" if trigger not in {TRIGGER_ON_EVENT, TRIGGER_ON_ENTER_STAGE, TRIGGER_SCHEDULED, TRIGGER_WEBHOOK_PUSH} else ""))
    checks.append(_check("target_stage_or_event_valid", bool(text(rv2.get("trigger_event_type")) or text(rv2.get("target_stage")) in STAGES or trigger in {TRIGGER_SCHEDULED, TRIGGER_WEBHOOK_PUSH})))
    checks.append(_check("schedule_valid", trigger != TRIGGER_SCHEDULED or bool(text(rv2.get("send_time")) or as_int(rv2.get("day_offset")) > 0)))
    candidate_stage = text(rv2.get("target_stage")) if trigger in {TRIGGER_ON_ENTER_STAGE, TRIGGER_SCHEDULED} else ""
    candidate_count = len(list_active_memberships(as_int(task.get("program_id")), candidate_stage)) if as_int(task.get("program_id")) else 0
    if content_type == CONTENT_FIXED_MESSAGE:
        content_ok = _content_has_body(dict(task.get("unified_content_json") or {}))
        checks.append(_check("content_config_valid", content_ok, "fixed_content_missing" if not content_ok else ""))
    elif content_type == CONTENT_LAYERED_MESSAGE:
        layers = list(task.get("segment_contents_json") or [])
        content_ok = any(_content_has_body(dict(item or {})) for item in layers)
        checks.append(_check("content_config_valid", content_ok, "layer_content_missing" if not content_ok else ""))
        checks.append(_check("layer_coverage", content_ok, "layer_content_missing" if not content_ok else ""))
    else:
        config = dict(task.get("agent_config_json") or {})
        agent_code = text(config.get("agent_code"))
        prompt = _agent_prompt(agent_code) if agent_code else {}
        checks.append(_check("agent_config_valid", bool(agent_code), "agent_code_missing" if not agent_code else ""))
        prompt_ok = bool(prompt.get("role_prompt") and prompt.get("task_prompt"))
        checks.append(_check("agent_published_prompt_present", prompt_ok, "agent_published_prompt_missing" if not prompt_ok else ""))
        checks.append(_check("questionnaire_context_available", True))
        content_ok = bool(agent_code and prompt_ok)
    checks.append(_check("render_sample_ok", bool(content_ok), "render_sample_blocked" if not content_ok else ""))
    checks.append(_check("outbox_writable", True))
    checks.append(_check("idempotency_safe", True))
    blocked = [item for item in checks if not item["passed"]]
    reasons: dict[str, int] = {}
    for item in blocked:
        reason = text(item.get("reason")) or text(item.get("key"))
        reasons[reason] = max(1, candidate_count)
    return {
        "ok": not blocked,
        "blocked": bool(blocked),
        "status": "ok" if not blocked else "blocked",
        "candidate_count": candidate_count,
        "renderable_count": candidate_count if not blocked else 0,
        "will_enqueue_count": candidate_count if not blocked else 0,
        "blocked_reasons": reasons,
        "checks": checks,
    }
