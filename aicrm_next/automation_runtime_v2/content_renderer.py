from __future__ import annotations

import json
import re
from typing import Any

from aicrm_next.shared.postgres_connection import get_db

from . import agent_gateway
from .agent_runtime import complete_agent_run, create_agent_run, log_llm_call, record_agent_output
from .domain import CONTENT_AGENT_GENERATED, CONTENT_FIXED_MESSAGE, CONTENT_LAYERED_MESSAGE, as_int, text
from .membership_service import get_membership, get_stage_entry
from .task_adapter import get_task
from .task_planner import get_plan, update_plan_status

_TEMPLATE_TOKEN_RE = re.compile(r"{{\s*([^{}]+?)\s*}}")
_SAFE_VARIABLE_RE = re.compile(r"^[A-Za-z0-9_.]+$")
_PROMPT_LEAK_MARKERS = (
    "你将收到以下资料",
    "你的唯一任务是",
    "最终只输出",
    "不要解释",
    "不要输出 JSON",
    "系统说明",
    "可用认知依据",
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


def _content_has_body(content: dict[str, Any]) -> bool:
    return bool(text(content.get("content_text") or content.get("text")) or content.get("image_library_ids") or content.get("miniprogram_library_ids") or content.get("attachment_library_ids") or content.get("attachments"))


def _fallback_content(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if text(value):
        return {"content_text": text(value)}
    return {}


_MISSING = object()


def _stringify_template_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return text(value)


def _resolve_path(source: Any, path: str) -> Any:
    current = source
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
            continue
        return _MISSING
    return current


def _resolve_template_variable(name: str, variables: dict[str, Any]) -> Any:
    if "." not in name:
        webhook = variables.get("webhook") if isinstance(variables.get("webhook"), dict) else {}
        webhook_vars = webhook.get("variables") if isinstance(webhook.get("variables"), dict) else {}
        resolved = _resolve_path(webhook_vars, name)
        if resolved is not _MISSING:
            return resolved
        resolved = _resolve_path(webhook, name)
        if resolved is not _MISSING:
            return resolved
    return _resolve_path(variables, name)


def render_template_text(raw_text: str, variables: dict[str, Any]) -> tuple[str, dict[str, Any], str]:
    raw = text(raw_text)
    matches = list(_TEMPLATE_TOKEN_RE.finditer(raw))
    if not matches:
        return raw, {"template_rendered": False, "template_variables_used": []}, ""
    missing: list[str] = []
    used: list[str] = []
    rendered_parts: list[str] = []
    cursor = 0
    for match in matches:
        rendered_parts.append(raw[cursor : match.start()])
        name = text(match.group(1))
        if not _SAFE_VARIABLE_RE.fullmatch(name):
            missing.append(name or "<invalid>")
            rendered_parts.append("")
            cursor = match.end()
            continue
        value = _resolve_template_variable(name, variables)
        if value is _MISSING or value is None:
            missing.append(name)
            rendered_parts.append("")
            cursor = match.end()
            continue
        used.append(name)
        rendered_parts.append(_stringify_template_value(value))
        cursor = match.end()
    rendered_parts.append(raw[cursor:])
    if missing:
        return "", {"template_rendered": True, "unresolved_template": True, "missing_variables": sorted(set(missing)), "template_variables_used": sorted(set(used))}, "template_variable_missing"
    rendered = "".join(rendered_parts)
    if _TEMPLATE_TOKEN_RE.search(rendered):
        return "", {"template_rendered": True, "unresolved_template": True, "missing_variables": [], "template_variables_used": sorted(set(used))}, "template_variable_missing"
    return rendered, {"template_rendered": True, "template_variables_used": sorted(set(used))}, ""


def _fixed(task: dict[str, Any], variables: dict[str, Any]) -> tuple[bool, dict[str, Any], str, dict[str, Any]]:
    content = dict(task.get("unified_content_json") or {})
    if not _content_has_body(content):
        return False, {}, "fixed_content_missing", {}
    rendered_text, diagnostics, reason = render_template_text(text(content.get("content_text") or content.get("text")), variables)
    if reason:
        return False, {}, reason, diagnostics
    return True, {"type": CONTENT_FIXED_MESSAGE, "content_text": rendered_text, "attachments": {k: content.get(k) for k in ("image_library_ids", "miniprogram_library_ids", "attachment_library_ids", "attachments") if content.get(k)}}, "", diagnostics


def _questionnaire_answers(event: dict[str, Any] | None) -> dict[str, Any]:
    payload = (event or {}).get("payload_json") if isinstance((event or {}).get("payload_json"), dict) else {}
    answers = payload.get("answers") or payload.get("questionnaire_answers") or {}
    if isinstance(answers, list):
        result = {}
        for item in answers:
            if isinstance(item, dict):
                key = text(item.get("question_code") or item.get("question_id") or item.get("name"))
                if key:
                    result[key] = item.get("answer") or item.get("value") or item.get("text_value")
        return result
    return dict(answers or {}) if isinstance(answers, dict) else {}


def _layer_key(task: dict[str, Any], membership: dict[str, Any], event: dict[str, Any] | None) -> str:
    basis = text((task.get("runtime_v2") or {}).get("layer_basis")) or "profile"
    if basis == "behavior":
        return text(membership.get("behavior_tier_key") or (event or {}).get("behavior_tier_key") or "none")
    if basis == "questionnaire":
        answers = _questionnaire_answers(event)
        return text(answers.get("layer_key") or answers.get("segment_key") or next(iter(answers.values()), ""))
    return text(membership.get("profile_segment_key") or (event or {}).get("profile_segment_key") or "default")


def _layered(task: dict[str, Any], membership: dict[str, Any], event: dict[str, Any] | None) -> tuple[bool, dict[str, Any], str]:
    key = _layer_key(task, membership, event)
    fallback: dict[str, Any] = {}
    for raw in list(task.get("segment_contents_json") or []):
        item = dict(raw or {})
        if text(item.get("segment_key")) in {"fallback", "default", "*"}:
            fallback = item
        if text(item.get("segment_key")) == key and _content_has_body(item):
            return True, {"type": CONTENT_LAYERED_MESSAGE, "layer_key": key, "layer_basis": (task.get("runtime_v2") or {}).get("layer_basis"), "content_text": text(item.get("content_text") or item.get("text")), "attachments": item}, ""
    if fallback and _content_has_body(fallback):
        return True, {"type": CONTENT_LAYERED_MESSAGE, "layer_key": key, "fallback": True, "content_text": text(fallback.get("content_text") or fallback.get("text")), "attachments": fallback}, ""
    return False, {}, "layer_content_missing"


def _agent_prompt(agent_code: str) -> dict[str, Any]:
    row = get_db().execute(
        """
        SELECT *
        FROM automation_agent_config
        WHERE agent_code = ?
        LIMIT 1
        """,
        (agent_code,),
    ).fetchone()
    item = dict(row or {})
    return {
        "role_prompt": text(item.get("published_role_prompt") or item.get("role_prompt")),
        "task_prompt": text(item.get("published_task_prompt") or item.get("task_prompt")),
        "published_version": as_int(item.get("published_version")),
        "raw": item,
    }


def build_variables(*, event: dict[str, Any] | None, membership: dict[str, Any], stage_entry: dict[str, Any] | None) -> dict[str, Any]:
    payload = (event or {}).get("payload_json") if isinstance((event or {}).get("payload_json"), dict) else {}
    return {
        "event": event or {},
        "membership": membership,
        "stage": stage_entry or {"stage_code": membership.get("current_stage")},
        "member": membership,
        "questionnaire": {"answers": _questionnaire_answers(event)},
        "payment": payload if text((event or {}).get("event_type")) == "payment_succeeded" else {},
        "webhook": payload if text((event or {}).get("event_type")) == "webhook_received" else {},
        "recent_messages": payload.get("recent_messages") or [],
        "tags": payload.get("tags") or [],
    }


def _explicit_fallback(task: dict[str, Any]) -> dict[str, Any]:
    config = dict(task.get("agent_config_json") or {})
    return _fallback_content(config.get("fallback_content") or config.get("fallback") or {})


def _agent_attachments(task: dict[str, Any]) -> dict[str, Any]:
    config = dict(task.get("agent_config_json") or {})
    attachments: dict[str, Any] = {}
    for key in ("image_library_ids", "miniprogram_library_ids", "attachment_library_ids", "attachments"):
        value = config.get(key)
        if value:
            attachments[key] = value
    return attachments


def _render_agent_fallback(task: dict[str, Any], variables: dict[str, Any], reason: str) -> tuple[bool, dict[str, Any], str, dict[str, Any]]:
    fallback = _explicit_fallback(task)
    if not _content_has_body(fallback):
        return False, {}, reason, {"fallback_used": False, "fallback_reason": reason}
    rendered_text, diagnostics, template_reason = render_template_text(text(fallback.get("content_text") or fallback.get("text")), variables)
    if template_reason:
        return False, {}, "agent_fallback_variable_missing", {"fallback_used": False, "fallback_reason": reason, **diagnostics}
    return True, {"type": CONTENT_AGENT_GENERATED, "fallback": True, "content_text": rendered_text, "attachments": fallback}, "", {"fallback_used": True, "fallback_reason": reason, **diagnostics}


def _render_prompt_text(raw: str, variables: dict[str, Any]) -> tuple[str, dict[str, Any], str]:
    rendered, diagnostics, reason = render_template_text(raw, variables)
    if reason:
        return "", diagnostics, "agent_prompt_variable_missing"
    return rendered, diagnostics, ""


def _looks_like_prompt(final_text: str, *, role_prompt: str, task_prompt: str) -> bool:
    candidate = text(final_text)
    if not candidate:
        return False
    if _TEMPLATE_TOKEN_RE.search(candidate):
        return True
    role = text(role_prompt)
    task = text(task_prompt)
    if candidate == role or candidate == task:
        return True
    if len(task) >= 120 and (task[:120] in candidate or candidate[:120] in task):
        return True
    return any(marker in candidate for marker in _PROMPT_LEAK_MARKERS)


def _agent(task: dict[str, Any], plan: dict[str, Any], membership: dict[str, Any], event: dict[str, Any] | None, stage_entry: dict[str, Any] | None) -> tuple[bool, dict[str, Any], str, dict[str, Any]]:
    config = dict(task.get("agent_config_json") or {})
    agent_code = text(config.get("agent_code"))
    if not agent_code:
        return False, {}, "agent_code_missing", {"fallback_used": False}
    prompt = _agent_prompt(agent_code)
    variables = build_variables(event=event, membership=membership, stage_entry=stage_entry)
    run = create_agent_run(agent_code=agent_code, task=task, plan=plan, membership=membership, event=event, stage_entry=stage_entry, variables=variables)
    run_id = text(run.get("run_id"))
    base_diag = {
        "agent_code": agent_code,
        "agent_run_id": run_id,
        "fallback_used": False,
        "questionnaire_answer_count": len(variables.get("questionnaire", {}).get("answers") or {}),
    }
    if not prompt["role_prompt"] or not prompt["task_prompt"]:
        reason = "agent_published_prompt_missing"
        complete_agent_run(run, status="failed", error_code=reason, error_message=reason)
        log_llm_call(run=run, agent_code=agent_code, provider="", model="", status="failed", error_code=reason, error_message=reason)
        ok, rendered, fallback_reason, fallback_diag = _render_agent_fallback(task, variables, reason)
        if ok:
            output = record_agent_output(run=run, agent_code=agent_code, external_userid=text(membership.get("external_userid")), final_text=text(rendered.get("content_text")), applied_status="fallback")
            return True, rendered, "", {**base_diag, **fallback_diag, "agent_output_id": text(output.get("output_id"))}
        return False, {}, fallback_reason, {**base_diag, **fallback_diag, "render_failed": fallback_reason, "error_code": reason, "error_message": reason}
    role_prompt, role_diag, role_reason = _render_prompt_text(prompt["role_prompt"], variables)
    task_prompt, task_diag, task_reason = _render_prompt_text(prompt["task_prompt"], variables)
    prompt_diag = {
        "role_prompt_template": role_diag,
        "task_prompt_template": task_diag,
    }
    if role_reason or task_reason:
        reason = "agent_prompt_variable_missing"
        missing = sorted(set((role_diag.get("missing_variables") or []) + (task_diag.get("missing_variables") or [])))
        complete_agent_run(run, status="failed", error_code=reason, error_message=",".join(missing))
        log_llm_call(run=run, agent_code=agent_code, provider="", model="", status="failed", error_code=reason, error_message=",".join(missing), prompt_text=f"{prompt['role_prompt']}\n{prompt['task_prompt']}")
        return False, {}, reason, {**base_diag, **prompt_diag, "missing_variables": missing, "render_failed": reason, "error_code": reason, "error_message": ",".join(missing)}
    if config.get("force_fail"):
        gateway_result = agent_gateway.AgentGatewayResult(ok=False, mode="forced", error_code="agent_generation_failed", error_message="Forced agent failure")
    else:
        gateway_result = agent_gateway.generate_agent_reply(agent_code=agent_code, role_prompt=role_prompt, task_prompt=task_prompt, variables=variables, mock_output=text(config.get("mock_output")))
    log = log_llm_call(
        run=run,
        agent_code=agent_code,
        provider=gateway_result.provider,
        model=gateway_result.model,
        status="completed" if gateway_result.ok else "failed",
        latency_ms=gateway_result.latency_ms,
        error_code=gateway_result.error_code,
        error_message=gateway_result.error_message,
        request_summary=gateway_result.request_summary,
        response_summary=gateway_result.response_summary,
        prompt_text=f"{role_prompt}\n{task_prompt}",
    )
    if not gateway_result.ok:
        reason = gateway_result.error_code or "agent_generation_failed"
        complete_agent_run(run, status="failed", provider=gateway_result.provider, latency_ms=gateway_result.latency_ms, final_prompt_preview=task_prompt, error_code=reason, error_message=gateway_result.error_message)
        ok, rendered, fallback_reason, fallback_diag = _render_agent_fallback(task, variables, reason)
        if ok:
            output = record_agent_output(run=run, agent_code=agent_code, external_userid=text(membership.get("external_userid")), final_text=text(rendered.get("content_text")), applied_status="fallback", error_code=reason, error_message=gateway_result.error_message)
            return True, rendered, "", {**base_diag, **fallback_diag, "agent_output_id": text(output.get("output_id")), "llm_call_logged": bool(log), "error_code": reason, "error_message": gateway_result.error_message}
        return False, {}, fallback_reason, {**base_diag, **fallback_diag, "llm_call_logged": bool(log), "render_failed": fallback_reason, "error_code": reason, "error_message": gateway_result.error_message}
    final_text = text(gateway_result.final_text)
    if not final_text:
        reason = "agent_generation_empty"
        complete_agent_run(run, status="failed", provider=gateway_result.provider, latency_ms=gateway_result.latency_ms, final_prompt_preview=task_prompt, error_code=reason, error_message=reason)
        return False, {}, reason, {**base_diag, "llm_call_logged": bool(log), "render_failed": reason, "error_code": reason, "error_message": reason}
    if _looks_like_prompt(final_text, role_prompt=prompt["role_prompt"], task_prompt=prompt["task_prompt"]):
        reason = "agent_output_looks_like_prompt"
        complete_agent_run(run, status="failed", provider=gateway_result.provider, latency_ms=gateway_result.latency_ms, final_prompt_preview=task_prompt, error_code=reason, error_message=reason)
        return False, {}, reason, {**base_diag, "llm_call_logged": bool(log), "render_failed": reason, "error_code": reason, "error_message": reason}
    completed = complete_agent_run(run, status="completed", provider=gateway_result.provider, latency_ms=gateway_result.latency_ms, final_prompt_preview=task_prompt)
    output = record_agent_output(run=completed or run, agent_code=agent_code, external_userid=text(membership.get("external_userid")), final_text=final_text, applied_status="generated")
    attachments = _agent_attachments(task)
    rendered = {"type": CONTENT_AGENT_GENERATED, "agent_code": agent_code, "content_text": final_text, "variables": variables}
    if attachments:
        rendered["attachments"] = attachments
    return True, rendered, "", {**base_diag, "agent_output_id": text(output.get("output_id")), "llm_call_logged": bool(log), "fallback_used": False, "attachment_counts": {key: len(value) if isinstance(value, list) else 1 for key, value in attachments.items()}}


def render(task_plan_id: int, *, event: dict[str, Any] | None = None) -> dict[str, Any]:
    plan = get_plan(int(task_plan_id))
    if not plan:
        raise LookupError("task_plan_not_found")
    task = get_task(as_int(plan.get("task_id")))
    if not task:
        return update_plan_status(int(task_plan_id), "failed", skip_reason="task_not_found")
    membership = get_membership(as_int(plan.get("membership_id"))) or {}
    stage_entry = get_stage_entry(as_int(plan.get("stage_entry_id"))) if as_int(plan.get("stage_entry_id")) else None
    content_type = text(task.get("content_type"))
    diagnostics: dict[str, Any] = {}
    if content_type == CONTENT_FIXED_MESSAGE:
        variables = build_variables(event=event, membership=membership, stage_entry=stage_entry)
        ok, rendered, reason, diagnostics = _fixed(task, variables)
    elif content_type == CONTENT_LAYERED_MESSAGE:
        ok, rendered, reason = _layered(task, membership, event)
    else:
        ok, rendered, reason, diagnostics = _agent(task, plan, membership, event, stage_entry)
    if not ok:
        return update_plan_status(int(task_plan_id), "failed", skip_reason=reason, diagnostics={"render_failed": reason, **diagnostics})
    return update_plan_status(int(task_plan_id), "rendered", rendered=rendered, diagnostics={"rendered": True, "content_type": content_type, **diagnostics})
