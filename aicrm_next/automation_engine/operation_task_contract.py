from __future__ import annotations

from typing import Any


CONTENT_MODES = {"unified", "profile_layered", "behavior_layered", "agent"}
TRIGGER_TYPES = {"scheduled_daily", "audience_entered"}
TASK_STATUSES = {"draft", "active", "paused", "archived"}
BEHAVIOR_FILTERS = {"none", "lt_2", "between_2_9", "gte_10"}
BEHAVIOR_SEGMENT_KEYS = ("lt_2", "between_2_9", "gte_10")


def text(value: Any) -> str:
    return str(value or "").strip()


def int_list(value: Any) -> list[int]:
    result: list[int] = []
    for item in list(value or []):
        try:
            parsed = int(item)
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            result.append(parsed)
    return result


def positive_int(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return parsed if parsed > 0 else 0


def has_send_body(content: dict[str, Any] | None, *, content_text: str = "") -> bool:
    payload = dict(content or {})
    return bool(
        text(content_text) or text(payload.get("content_text"))
        or int_list(payload.get("image_library_ids"))
        or int_list(payload.get("miniprogram_library_ids"))
        or int_list(payload.get("attachment_library_ids"))
        or [text(item) for item in list(payload.get("image_media_ids") or []) if text(item)]
    )


def agent_instruction_present(task: dict[str, Any]) -> bool:
    config = dict(task.get("agent_config_json") or {})
    return bool(
        text(config.get("fallback_content"))
        or text(config.get("requirement"))
        or text(task.get("description"))
        or text(config.get("prompt"))
        or text(config.get("task_prompt"))
        or text(config.get("role_prompt"))
        or text(config.get("user_prompt"))
        or text(config.get("system_prompt"))
        or text(config.get("material_prompt"))
    )


def agent_material_present(config: dict[str, Any] | None) -> bool:
    payload = dict(config or {})
    return has_send_body(payload)


def agent_fallback_present(task: dict[str, Any]) -> bool:
    config = dict(task.get("agent_config_json") or {})
    return bool(text(config.get("fallback_content")) or text(config.get("requirement")) or text(task.get("description")))


def agent_runtime_diagnostics(
    task: dict[str, Any],
    *,
    agent_runtime_context: dict[str, Any] | None = None,
) -> dict[str, bool]:
    config = dict(task.get("agent_config_json") or {})
    context = dict(agent_runtime_context or {})
    task_instruction_present = agent_instruction_present(task)
    task_material_present = agent_material_present(config)
    agent_published_prompt_present = bool(context.get("agent_published_prompt_present"))
    questionnaire_context_required = bool(context.get("questionnaire_context_required"))
    questionnaire_context_available = bool(context.get("questionnaire_context_available"))
    prompt_context_ready = bool(
        agent_published_prompt_present
        and (questionnaire_context_available or not questionnaire_context_required)
    )
    material_present = agent_material_present(config)
    return {
        "agent_code_present": bool(text(config.get("agent_code"))),
        "fallback_present": agent_fallback_present(task),
        "task_instruction_present": task_instruction_present,
        "task_material_present": task_material_present,
        "material_present": material_present,
        "agent_published_prompt_present": agent_published_prompt_present,
        "questionnaire_context_required": questionnaire_context_required,
        "questionnaire_context_available": questionnaire_context_available,
        "expected_send_body_present": bool(task_instruction_present or task_material_present or prompt_context_ready),
    }


def publishable_diagnostics(
    task: dict[str, Any],
    *,
    agent_runtime_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    mode = text(task.get("content_mode")) or "unified"
    errors: list[str] = []
    warnings: list[str] = []
    details: dict[str, Any] = {"content_mode": mode}

    if mode not in CONTENT_MODES:
        errors.append("content_mode_invalid")
    if text(task.get("trigger_type") or "scheduled_daily") not in TRIGGER_TYPES:
        errors.append("trigger_type_invalid")
    if text(task.get("behavior_filter") or "none") not in BEHAVIOR_FILTERS:
        errors.append("behavior_filter_invalid")
    if text(task.get("status") or "draft") not in TASK_STATUSES:
        errors.append("status_invalid")

    if mode == "unified":
        if not has_send_body(dict(task.get("unified_content_json") or {})):
            errors.append("content_missing")
    elif mode == "profile_layered":
        if not positive_int(task.get("profile_segment_template_id")):
            errors.append("profile_segment_template_missing")
        contents = [dict(item or {}) for item in list(task.get("segment_contents_json") or [])]
        if not contents:
            errors.append("segment_content_missing")
        missing = [text(item.get("segment_key")) or "unknown" for item in contents if not has_send_body(item)]
        if missing:
            errors.append("segment_content_incomplete")
            details["missing_segment_keys"] = missing
    elif mode == "behavior_layered":
        contents = [dict(item or {}) for item in list(task.get("segment_contents_json") or [])]
        by_key = {text(item.get("segment_key")): item for item in contents if text(item.get("segment_key"))}
        behavior_filter = text(task.get("behavior_filter")) or "none"
        required = [behavior_filter] if behavior_filter in BEHAVIOR_SEGMENT_KEYS else list(BEHAVIOR_SEGMENT_KEYS)
        missing = [key for key in required if not has_send_body(by_key.get(key))]
        if missing:
            errors.append("behavior_segment_content_missing")
            details["missing_segment_keys"] = missing
    elif mode == "agent":
        agent_diag = agent_runtime_diagnostics(task, agent_runtime_context=agent_runtime_context)
        details["agent_runtime_diagnostics"] = agent_diag
        if not agent_diag["agent_code_present"]:
            errors.append("agent_code_missing")
        if (
            agent_diag["agent_published_prompt_present"]
            and agent_diag["questionnaire_context_required"]
            and not agent_diag["questionnaire_context_available"]
            and not agent_diag["task_instruction_present"]
            and not agent_diag["task_material_present"]
        ):
            errors.append("questionnaire_context_missing")
        if not agent_diag["expected_send_body_present"]:
            errors.append("agent_runtime_content_missing")
            warnings.append("agent_instruction_prompt_or_material_required")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "details": details,
    }


def validate_publishable_task(
    task: dict[str, Any],
    *,
    agent_runtime_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    diagnostics = publishable_diagnostics(task, agent_runtime_context=agent_runtime_context)
    if diagnostics["errors"]:
        message_map = {
            "content_mode_invalid": "发送策略不正确",
            "trigger_type_invalid": "触发方式不正确",
            "behavior_filter_invalid": "行为过滤不正确",
            "status_invalid": "任务状态不正确",
            "content_missing": "统一内容至少需要文本、图片、小程序或附件",
            "profile_segment_template_missing": "请选择画像分层模板",
            "segment_content_missing": "请先填写分层话术",
            "segment_content_incomplete": "每个分层都需要可发送内容",
            "behavior_segment_content_missing": "行为分层必须覆盖所选分层且每层有可发送内容",
            "agent_code_missing": "agent 模式必须提供 agent_code",
            "questionnaire_context_missing": "agent 模式需要问卷答案上下文",
            "agent_runtime_content_missing": "agent 模式必须配置任务生成要求、兜底话术、素材，或使用已发布 Agent 提示词",
        }
        first = diagnostics["errors"][0]
        raise ValueError(message_map.get(first, first))
    return diagnostics
