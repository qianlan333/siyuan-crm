from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from ...db import get_db
from aicrm_next.automation_engine.operation_task_contract import (
    agent_runtime_diagnostics,
    has_send_body as contract_has_send_body,
    publishable_diagnostics,
    validate_publishable_task,
)
from ..broadcast_jobs import repo as broadcast_queue_repo
from ..broadcast_jobs import service as broadcast_queue
from .agents import repo as agent_repo
from . import operation_task_repo as repo
from . import workflow_repo
from . import workflow_runtime
from .private_message_dispatch import _dispatch_private_message_batch
from .workflow_definitions import (
    AGENT_BINDING_SCOPE_PERSONALIZED,
    AUDIENCE_CONVERTED,
    AUDIENCE_OPERATING,
    AUDIENCE_PENDING_QUESTIONNAIRE,
    GENERATION_MODE_PERSONALIZED_SINGLE,
    SEGMENTATION_BASIS_NONE,
    STAGE_COMPAT_AUDIENCE,
    STAGE_COMPAT_ENTRY_REASON,
    STAGE_CONVERTED,
    STAGE_OPERATING,
    STAGE_ORDER_REVIEW,
    STAGE_QUESTIONNAIRE_REVIEW,
    list_supported_behavior_tiers,
)
from .workflow_service import get_conversion_profile_segment_template_bundle


AUDIENCE_CODES = {AUDIENCE_PENDING_QUESTIONNAIRE, AUDIENCE_OPERATING, AUDIENCE_CONVERTED}
TASK_STATUSES = {"draft", "active", "paused", "archived"}
BEHAVIOR_FILTERS = {"none", "lt_2", "between_2_9", "gte_10"}
CONTENT_MODES = {"unified", "profile_layered", "behavior_layered", "agent"}
TRIGGER_TYPES = {"scheduled_daily", "audience_entered"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any, *, default: int = 0, minimum: int | None = None) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError):
        result = int(default)
    if minimum is not None:
        result = max(result, minimum)
    return result


def _now() -> datetime:
    return datetime.now()


def _parse_time(value: Any) -> str:
    text = _text(value) or "10:00"
    try:
        parsed = datetime.strptime(text, "%H:%M")
    except ValueError as exc:
        raise ValueError("发送时间格式必须是 HH:MM") from exc
    return parsed.strftime("%H:%M")


def _parse_date(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    text = _text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        pass
    for pattern, size in (
        ("%Y-%m-%d %H:%M:%S", 19),
        ("%Y-%m-%dT%H:%M:%S", 19),
        ("%Y-%m-%d %H:%M", 16),
        ("%Y-%m-%d", 10),
    ):
        try:
            return datetime.strptime(text[:size], pattern)
        except ValueError:
            continue
    return None


def _stage_flow(program_id: int) -> dict[str, Any]:
    from .program_setup_service import build_program_stage_flow

    return build_program_stage_flow(int(program_id))


def _targetable_stages(program_id: int) -> list[dict[str, Any]]:
    return [dict(item or {}) for item in list((_stage_flow(int(program_id)).get("targetable_stages") or []))]


def _targetable_stage_by_code(program_id: int) -> dict[str, dict[str, Any]]:
    return {_text(item.get("stage_code")): dict(item) for item in _targetable_stages(int(program_id))}


def infer_stage_code_from_audience(program_id: int, audience_code: str) -> str:
    code = _text(audience_code) or AUDIENCE_OPERATING
    targetable = _targetable_stage_by_code(int(program_id))
    if code == AUDIENCE_PENDING_QUESTIONNAIRE:
        if STAGE_QUESTIONNAIRE_REVIEW in targetable:
            return STAGE_QUESTIONNAIRE_REVIEW
        if STAGE_ORDER_REVIEW in targetable:
            return STAGE_ORDER_REVIEW
        return STAGE_OPERATING
    if code == AUDIENCE_CONVERTED:
        return STAGE_CONVERTED if STAGE_CONVERTED in targetable else STAGE_OPERATING
    return STAGE_OPERATING


def resolve_stage_target_filter(program_id: int, target_stage_code: str, *, fallback_audience_code: str = "") -> dict[str, Any]:
    stage_code = _text(target_stage_code)
    if not stage_code:
        stage_code = infer_stage_code_from_audience(int(program_id), fallback_audience_code)
    targetable = _targetable_stage_by_code(int(program_id))
    stage = targetable.get(stage_code)
    if not stage:
        stage_code = infer_stage_code_from_audience(int(program_id), STAGE_COMPAT_AUDIENCE.get(stage_code, fallback_audience_code))
        stage = targetable.get(stage_code) or targetable.get(STAGE_OPERATING) or {
            "stage_code": STAGE_OPERATING,
            "label": "运营中",
            "description": "已通过前置条件",
            "compat_audience_code": AUDIENCE_OPERATING,
            "compat_entry_reason": "",
        }
    return {
        "stage_code": _text(stage.get("stage_code")) or STAGE_OPERATING,
        "stage_label": _text(stage.get("label")) or "运营中",
        "stage_description": _text(stage.get("description")),
        "audience_code": _text(stage.get("compat_audience_code")) or STAGE_COMPAT_AUDIENCE.get(_text(stage.get("stage_code")), AUDIENCE_OPERATING),
        "entry_reason": _text(stage.get("compat_entry_reason")) or STAGE_COMPAT_ENTRY_REASON.get(_text(stage.get("stage_code")), ""),
    }


def _with_stage_metadata(task: dict[str, Any]) -> dict[str, Any]:
    item = dict(task or {})
    if not item:
        return item
    stage_filter = resolve_stage_target_filter(
        int(item.get("program_id") or 0),
        _text(item.get("target_stage_code")),
        fallback_audience_code=_text(item.get("target_audience_code")),
    )
    item["target_stage_code"] = stage_filter["stage_code"]
    item["target_stage_label"] = stage_filter["stage_label"]
    item["target_stage_description"] = stage_filter["stage_description"]
    item["target_audience_code"] = stage_filter["audience_code"]
    item["target_entry_reason"] = stage_filter["entry_reason"]
    return item


def _task_scheduled_for(task: dict[str, Any], base_time: datetime) -> datetime:
    send_time = _parse_time(task.get("send_time"))
    send_hour, send_minute = [int(part) for part in send_time.split(":", 1)]
    return base_time.replace(hour=send_hour, minute=send_minute, second=0, microsecond=0)


def _execution_id_for_task(task_id: int, scheduled_for: datetime) -> str:
    return f"actask-{int(task_id)}-{scheduled_for.strftime('%Y%m%d%H%M')}"


def _event_execution_id_for_task(task_id: int, audience_entry_id: int) -> str:
    return f"actask-event-{int(task_id)}-{int(audience_entry_id)}"


def _normalize_content_item(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "content_text": _text(payload.get("content_text")),
        "image_library_ids": [_int(item, minimum=1) for item in list(payload.get("image_library_ids") or []) if _int(item, minimum=0) > 0],
        "miniprogram_library_ids": [
            _int(item, minimum=1) for item in list(payload.get("miniprogram_library_ids") or []) if _int(item, minimum=0) > 0
        ],
        "attachment_library_ids": [
            _int(item, minimum=1) for item in list(payload.get("attachment_library_ids") or []) if _int(item, minimum=0) > 0
        ][:9],
    }


def _normalize_segment_contents(items: Any) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for raw in list(items or []):
        item = dict(raw or {})
        segment_key = _text(item.get("segment_key"))
        if not segment_key:
            continue
        normalized.append(
            {
                "segment_key": segment_key,
                "segment_name": _text(item.get("segment_name")) or segment_key,
                **_normalize_content_item(item),
            }
        )
    return normalized


def _normalize_task_payload(payload: dict[str, Any], *, program_id: int, operator_id: str, existing: dict[str, Any] | None = None) -> dict[str, Any]:
    source = dict(payload or {})
    current = dict(existing or {})
    status = _text(source.get("status") if "status" in source else current.get("status")) or "draft"
    if status not in TASK_STATUSES:
        raise ValueError("任务状态不正确")
    trigger_type = _text(source.get("trigger_type") if "trigger_type" in source else current.get("trigger_type")) or "scheduled_daily"
    if trigger_type not in TRIGGER_TYPES:
        raise ValueError("触发方式不正确")
    audience_code = _text(source.get("target_audience_code") if "target_audience_code" in source else current.get("target_audience_code")) or AUDIENCE_OPERATING
    if audience_code not in AUDIENCE_CODES:
        raise ValueError("触达阶段不正确")
    target_stage_code = _text(source.get("target_stage_code") if "target_stage_code" in source else current.get("target_stage_code"))
    stage_filter = resolve_stage_target_filter(int(program_id), target_stage_code, fallback_audience_code=audience_code)
    behavior_filter = _text(source.get("behavior_filter") if "behavior_filter" in source else current.get("behavior_filter")) or "none"
    if behavior_filter not in BEHAVIOR_FILTERS:
        raise ValueError("行为过滤不正确")
    content_mode = _text(source.get("content_mode") if "content_mode" in source else current.get("content_mode")) or "unified"
    if content_mode not in CONTENT_MODES:
        raise ValueError("发送策略不正确")
    task_name = _text(source.get("task_name") if "task_name" in source else current.get("task_name"))
    if not task_name:
        raise ValueError("任务名称不能为空")
    profile_template_id = _int(
        source.get("profile_segment_template_id") if "profile_segment_template_id" in source else current.get("profile_segment_template_id"),
        default=0,
        minimum=0,
    ) or None
    if content_mode == "profile_layered" and not profile_template_id:
        raise ValueError("请选择画像分层模板")
    normalized = {
        "program_id": int(program_id),
        "group_id": _int(source.get("group_id") if "group_id" in source else current.get("group_id"), default=0, minimum=0) or None,
        "task_name": task_name,
        "description": _text(source.get("description") if "description" in source else current.get("description")),
        "status": status,
        "trigger_type": trigger_type,
        "send_time": _parse_time(source.get("send_time") if "send_time" in source else current.get("send_time")),
        "timezone": _text(source.get("timezone") if "timezone" in source else current.get("timezone")) or "Asia/Shanghai",
        "target_audience_code": stage_filter["audience_code"],
        "target_stage_code": stage_filter["stage_code"],
        "audience_day_offset": _int(
            source.get("audience_day_offset") if "audience_day_offset" in source else current.get("audience_day_offset"),
            default=1,
            minimum=1,
        ),
        "behavior_filter": behavior_filter,
        "content_mode": content_mode,
        "profile_segment_template_id": profile_template_id,
        "unified_content_json": _normalize_content_item(dict(source.get("unified_content_json") or current.get("unified_content_json") or {})),
        "segment_contents_json": _normalize_segment_contents(source.get("segment_contents_json") or current.get("segment_contents_json") or []),
        "agent_config_json": dict(source.get("agent_config_json") or current.get("agent_config_json") or {}),
        "created_by": _text(current.get("created_by") or operator_id),
        "updated_by": _text(operator_id),
    }
    _validate_publishable_task(normalized)
    return normalized


def _validate_publishable_task(task: dict[str, Any]) -> None:
    if _text(task.get("status")) != "active":
        return
    validate_publishable_task(task, agent_runtime_context=_agent_runtime_context(task, require_questionnaire_context=False))


def list_task_groups(program_id: int) -> dict[str, Any]:
    return {"groups": repo.list_groups(int(program_id))}


def create_task_group(program_id: int, payload: dict[str, Any], *, operator_id: str) -> dict[str, Any]:
    name = _text(payload.get("group_name"))
    if not name:
        raise ValueError("分组名称不能为空")
    group = repo.insert_group(
        {
            "program_id": int(program_id),
            "group_name": name,
            "sort_order": _int(payload.get("sort_order"), default=0, minimum=0),
            "created_by": operator_id,
            "updated_by": operator_id,
        }
    )
    get_db().commit()
    return {"group": group}


def update_task_group(group_id: int, payload: dict[str, Any], *, operator_id: str) -> dict[str, Any]:
    group = repo.get_group(int(group_id))
    if not group:
        raise LookupError("分组不存在")
    name = _text(payload.get("group_name") or group.get("group_name"))
    if not name:
        raise ValueError("分组名称不能为空")
    updated = repo.update_group(int(group_id), {"group_name": name, "sort_order": _int(payload.get("sort_order"), default=group.get("sort_order") or 0), "updated_by": operator_id})
    get_db().commit()
    return {"group": updated}


def delete_task_group(group_id: int, *, operator_id: str) -> dict[str, Any]:
    if not repo.get_group(int(group_id)):
        raise LookupError("分组不存在")
    repo.archive_group(int(group_id), operator_id=operator_id)
    get_db().commit()
    return {"deleted": True}


def list_operation_tasks(program_id: int, *, group_id: int | None = None, keyword: str = "", status: str = "") -> dict[str, Any]:
    return {
        "groups": repo.list_groups(int(program_id)),
        "tasks": [_with_stage_metadata(task) for task in repo.list_tasks(int(program_id), group_id=group_id, status=status, keyword=keyword)],
        "behavior_tiers": list_supported_behavior_tiers(),
        "targetable_stages": _targetable_stages(int(program_id)),
    }


def get_operation_task(task_id: int) -> dict[str, Any]:
    task = repo.get_task(int(task_id))
    if not task:
        raise LookupError("任务不存在")
    return {"task": _with_stage_metadata(task)}


def create_operation_task(program_id: int, payload: dict[str, Any], *, operator_id: str) -> dict[str, Any]:
    normalized = _normalize_task_payload(payload, program_id=int(program_id), operator_id=operator_id)
    task = repo.insert_task(normalized)
    get_db().commit()
    return {"task": _with_stage_metadata(task)}


def update_operation_task(task_id: int, payload: dict[str, Any], *, operator_id: str) -> dict[str, Any]:
    existing = repo.get_task(int(task_id))
    if not existing:
        raise LookupError("任务不存在")
    normalized = _normalize_task_payload(payload, program_id=int(existing["program_id"]), operator_id=operator_id, existing=existing)
    task = repo.update_task(int(task_id), normalized)
    get_db().commit()
    return {"task": _with_stage_metadata(task)}


def copy_operation_task(task_id: int, *, operator_id: str) -> dict[str, Any]:
    existing = repo.get_task(int(task_id))
    if not existing:
        raise LookupError("任务不存在")
    copied = {
        **existing,
        "task_name": f"{existing.get('task_name') or '运营任务'} / 复制",
        "status": "draft",
        "created_by": operator_id,
        "updated_by": operator_id,
    }
    task = repo.insert_task(copied)
    get_db().commit()
    return {"task": _with_stage_metadata(task)}


def activate_operation_task(task_id: int, *, operator_id: str) -> dict[str, Any]:
    task = update_operation_task(int(task_id), {"status": "active"}, operator_id=operator_id)["task"]
    return {"task": task}


def pause_operation_task(task_id: int, *, operator_id: str) -> dict[str, Any]:
    task = update_operation_task(int(task_id), {"status": "paused"}, operator_id=operator_id)["task"]
    return {"task": task}


def delete_operation_task(task_id: int, *, operator_id: str) -> dict[str, Any]:
    if not repo.get_task(int(task_id)):
        raise LookupError("任务不存在")
    repo.archive_task(int(task_id), operator_id=operator_id)
    get_db().commit()
    return {"deleted": True}


def _entry_due(entry: dict[str, Any], *, day_offset: int, now: datetime) -> bool:
    entered_at = _parse_date(entry.get("entered_at")) or _parse_date((entry.get("member") or {}).get("current_audience_entered_at"))
    if not entered_at:
        return True
    target_date = (entered_at.date() + timedelta(days=max(1, int(day_offset)) - 1))
    return target_date == now.date()


def _behavior_key(member: dict[str, Any]) -> str:
    match = workflow_runtime._resolve_behavior_segment_match(member)
    return _text(match.get("segment_key"))


def _profile_key(member: dict[str, Any], template_id: int | None) -> str:
    if not template_id:
        return ""
    bundle = get_conversion_profile_segment_template_bundle(int(template_id))
    match = workflow_runtime._resolve_profile_segment_match(member=member, workflow_bundle={"profile_segment_template": bundle})
    return _text(match.get("segment_key"))


def _program_scoped_member(task: dict[str, Any], member: dict[str, Any]) -> dict[str, Any]:
    program_id = _int(task.get("program_id"), minimum=0)
    external_contact_id = _text(member.get("external_contact_id"))
    if program_id <= 0 or not external_contact_id:
        return dict(member)
    row = get_db().execute(
        """
        SELECT
            COALESCE(latest_source_channel_id, source_channel_id) AS source_channel_id,
            NULLIF(state_payload_json ->> 'profile_segment_key', '') AS profile_segment_key,
            NULLIF(state_payload_json ->> 'behavior_tier_key', '') AS behavior_tier_key
        FROM automation_program_member
        WHERE program_id = ?
          AND external_contact_id = ?
          AND in_program = ?
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (program_id, external_contact_id, True),
    ).fetchone()
    if not row:
        return dict(member)
    scoped = dict(member)
    source_channel_id = _int(row.get("source_channel_id"), minimum=0)
    if source_channel_id > 0:
        scoped["source_channel_id"] = source_channel_id
    profile_segment_key = _text(row.get("profile_segment_key"))
    if profile_segment_key:
        scoped["profile_segment_key"] = profile_segment_key
    behavior_tier_key = _text(row.get("behavior_tier_key"))
    if behavior_tier_key:
        scoped["behavior_tier_key"] = behavior_tier_key
    return scoped


def _entry_for_task(task: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any]:
    scoped = dict(entry)
    scoped["member"] = _program_scoped_member(task, dict(entry.get("member") or {}))
    return scoped


def _candidate_entries(task: dict[str, Any], *, now: datetime | None = None) -> list[dict[str, Any]]:
    current_time = now or _now()
    program_channel_ids = _program_channel_ids(int(task.get("program_id") or 0))
    stage_filter = resolve_stage_target_filter(
        int(task.get("program_id") or 0),
        _text(task.get("target_stage_code")),
        fallback_audience_code=_text(task.get("target_audience_code")),
    )
    entries = repo.list_current_audience_entries(
        stage_filter["audience_code"],
        program_id=int(task.get("program_id") or 0),
        entry_reason=stage_filter["entry_reason"],
    )
    result: list[dict[str, Any]] = []
    for entry in entries:
        scoped_entry = _entry_for_task(task, entry)
        member = dict(scoped_entry.get("member") or {})
        if not _member_in_program_channels(member, program_channel_ids):
            continue
        if _text(task.get("trigger_type")) != "audience_entered" and not _entry_due(
            scoped_entry,
            day_offset=_int(task.get("audience_day_offset"), default=1, minimum=1),
            now=current_time,
        ):
            continue
        behavior_filter = _text(task.get("behavior_filter")) or "none"
        if behavior_filter != "none" and _behavior_key(member) != behavior_filter:
            continue
        result.append(scoped_entry)
    return result


PREVIEW_REASON_KEYS = (
    "source_channel_missing",
    "program_channel_not_matched",
    "audience_code_not_matched",
    "entry_reason_not_matched",
    "day_offset_not_due",
    "behavior_filter_not_matched",
    "profile_segment_not_matched",
    "content_missing",
    "external_contact_id_missing",
)


def _preview_all_current_entries(program_id: int) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for audience_code in sorted(AUDIENCE_CODES):
        entries.extend(repo.list_current_audience_entries(audience_code, program_id=int(program_id)))
    by_id: dict[int, dict[str, Any]] = {}
    for entry in entries:
        by_id[int(entry.get("id") or 0)] = entry
    return list(by_id.values())


def _agent_code(task: dict[str, Any]) -> str:
    return _text((dict(task.get("agent_config_json") or {})).get("agent_code"))


def _agent_published_prompt_context(task: dict[str, Any]) -> dict[str, Any]:
    agent_code = _agent_code(task)
    if not agent_code:
        return {
            "agent_published_prompt_present": False,
            "agent_published_role_prompt_present": False,
            "agent_published_task_prompt_present": False,
            "enabled_context_sources": [],
            "agent_prompt_error": "",
        }
    try:
        row = agent_repo.deserialize_agent_config_row(agent_repo.get_agent_config_row(agent_code) or {})
        role_prompt = _text(row.get("published_role_prompt"))
        task_prompt = _text(row.get("published_task_prompt"))
        enabled_context_sources = workflow_runtime._resolve_effective_enabled_context_sources(
            role_prompt=role_prompt,
            task_prompt=task_prompt,
            enabled_context_sources=None,
            variables=row.get("published_variables_json") or [],
        )
        return {
            "agent_published_prompt_present": bool(role_prompt or task_prompt),
            "agent_published_role_prompt_present": bool(role_prompt),
            "agent_published_task_prompt_present": bool(task_prompt),
            "enabled_context_sources": list(enabled_context_sources),
            "agent_prompt_error": "",
        }
    except Exception as exc:
        return {
            "agent_published_prompt_present": False,
            "agent_published_role_prompt_present": False,
            "agent_published_task_prompt_present": False,
            "enabled_context_sources": [],
            "agent_prompt_error": str(exc),
        }


def _member_questionnaire_context(member: dict[str, Any]) -> dict[str, Any]:
    latest_submission = workflow_repo.get_latest_any_questionnaire_submission_row(
        external_contact_ids=[_text(member.get("external_contact_id"))],
        phone=_text(member.get("phone")),
    )
    answers = (
        workflow_repo.list_questionnaire_submission_answer_rows(int(latest_submission["id"]))
        if latest_submission
        else []
    )
    return {
        "questionnaire_context_available": bool(answers),
        "questionnaire_submission_id": int((latest_submission or {}).get("id") or 0),
        "questionnaire_answer_count": len(answers),
    }


def _agent_runtime_context(
    task: dict[str, Any],
    *,
    member: dict[str, Any] | None = None,
    require_questionnaire_context: bool | None = None,
) -> dict[str, Any]:
    config = dict(task.get("agent_config_json") or {})
    context = _agent_published_prompt_context(task)
    enabled_sources = list(context.get("enabled_context_sources") or [])
    if require_questionnaire_context is None:
        require_questionnaire_context = bool(config.get("questionnaire_context_required")) or "questionnaire" in enabled_sources
    if member is not None:
        context.update(_member_questionnaire_context(member))
    else:
        context.update(
            {
                "questionnaire_context_available": False,
                "questionnaire_submission_id": 0,
                "questionnaire_answer_count": 0,
            }
        )
    context["questionnaire_context_required"] = bool(require_questionnaire_context)
    return context


def _agent_runtime_context_for_entries(task: dict[str, Any], entries: list[dict[str, Any]]) -> dict[str, Any]:
    base = _agent_runtime_context(task, require_questionnaire_context=None)
    questionnaire_available = False
    questionnaire_submission_id = 0
    questionnaire_answer_count = 0
    for entry in entries:
        member_context = _agent_runtime_context(task, member=dict(entry.get("member") or {}), require_questionnaire_context=None)
        if bool(member_context.get("questionnaire_context_available")):
            questionnaire_available = True
            questionnaire_submission_id = int(member_context.get("questionnaire_submission_id") or 0)
            questionnaire_answer_count += int(member_context.get("questionnaire_answer_count") or 0)
    base["questionnaire_context_available"] = questionnaire_available
    base["questionnaire_submission_id"] = questionnaire_submission_id
    base["questionnaire_answer_count"] = questionnaire_answer_count
    return base


def _preview_content_ready(task: dict[str, Any], entry: dict[str, Any]) -> tuple[bool, str]:
    member = dict(entry.get("member") or {})
    mode = _text(task.get("content_mode")) or "unified"
    if mode == "agent":
        diag = agent_runtime_diagnostics(task, agent_runtime_context=_agent_runtime_context(task, member=member))
        return bool(diag.get("expected_send_body_present")), "agent"
    segment_key, content_text, content = _render_for_member(task, member, request_id="preview")
    return _content_has_send_body(content_text, content), segment_key


def _preview_entries(task: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    current_time = now or _now()
    program_id = int(task.get("program_id") or 0)
    program_channel_ids = _program_channel_ids(program_id)
    stage_filter = resolve_stage_target_filter(
        program_id,
        _text(task.get("target_stage_code")),
        fallback_audience_code=_text(task.get("target_audience_code")),
    )
    behavior_filter = _text(task.get("behavior_filter")) or "none"
    profile_template_id = task.get("profile_segment_template_id")
    filtered_out_counts = {key: 0 for key in PREVIEW_REASON_KEYS}
    segment_counts: dict[str, int] = {}
    target_entries: list[dict[str, Any]] = []

    for entry in _preview_all_current_entries(program_id):
        member = dict(entry.get("member") or {})
        reasons: list[str] = []
        if _int(member.get("source_channel_id"), minimum=0) <= 0:
            reasons.append("source_channel_missing")
        elif not _member_in_program_channels(member, program_channel_ids):
            reasons.append("program_channel_not_matched")
        if _text(entry.get("audience_code")) != stage_filter["audience_code"]:
            reasons.append("audience_code_not_matched")
        if stage_filter["entry_reason"] and _text(entry.get("entry_reason")) != stage_filter["entry_reason"]:
            reasons.append("entry_reason_not_matched")
        if _text(task.get("trigger_type")) != "audience_entered" and not _entry_due(
            entry,
            day_offset=_int(task.get("audience_day_offset"), default=1, minimum=1),
            now=current_time,
        ):
            reasons.append("day_offset_not_due")
        if behavior_filter != "none" and _behavior_key(member) != behavior_filter:
            reasons.append("behavior_filter_not_matched")
        if _text(task.get("content_mode")) == "profile_layered" and not _profile_key(member, profile_template_id):
            reasons.append("profile_segment_not_matched")
        content_ready, segment_key = _preview_content_ready(task, entry)
        if not content_ready:
            reasons.append("content_missing")
        if not _text(member.get("external_contact_id")):
            reasons.append("external_contact_id_missing")

        if reasons:
            for reason in dict.fromkeys(reasons):
                filtered_out_counts[reason] += 1
            continue
        target_entries.append(entry)
        if segment_key:
            segment_counts[segment_key] = segment_counts.get(segment_key, 0) + 1

    return {
        "entries": target_entries,
        "segment_counts": segment_counts,
        "filtered_out_counts": {key: value for key, value in filtered_out_counts.items() if value},
        "reasons": [key for key, value in filtered_out_counts.items() if value],
    }


def preview_operation_task_audience(program_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    task = _normalize_task_payload(
        {"task_name": payload.get("task_name") or "预览任务", **dict(payload or {})},
        program_id=int(program_id),
        operator_id="preview",
    )
    preview = _preview_entries(task)
    agent_context = None
    if task["content_mode"] == "agent":
        context_entries = preview["entries"] or _preview_all_current_entries(int(program_id))
        agent_context = _agent_runtime_context_for_entries(task, context_entries)
    diagnostics = publishable_diagnostics(task, agent_runtime_context=agent_context)
    return {
        "preview": {
            "target_count": len(preview["entries"]),
            "segment_counts": preview["segment_counts"],
            "filtered_out_counts": preview["filtered_out_counts"],
            "reasons": preview["reasons"],
            "content_diagnostics": diagnostics,
            "agent_runtime_diagnostics": agent_runtime_diagnostics(task, agent_runtime_context=agent_context)
            if task["content_mode"] == "agent"
            else {},
        }
    }


def _segment_content(task: dict[str, Any], segment_key: str) -> dict[str, Any]:
    for item in list(task.get("segment_contents_json") or []):
        if _text(item.get("segment_key")) == segment_key:
            return dict(item)
    return {}


def _render_agent_for_member(
    *,
    task: dict[str, Any],
    member: dict[str, Any],
    request_id: str,
) -> tuple[str, str, dict[str, Any]]:
    config = dict(task.get("agent_config_json") or {})
    standard_content_text = (
        _text(config.get("fallback_content"))
        or _text(config.get("requirement"))
        or _text(config.get("prompt"))
        or _text(config.get("material_prompt"))
        or _text(task.get("description"))
    )
    agent_context = _agent_runtime_context(task, member=member)
    workflow_bundle = {
        "workflow": {
            "workflow_code": f"operation_task_{int(task.get('program_id') or 0)}",
            "workflow_name": "自动化运营任务",
            "generation_mode": GENERATION_MODE_PERSONALIZED_SINGLE,
            "segmentation_basis": SEGMENTATION_BASIS_NONE,
        }
    }
    node = {
        "node_code": f"operation_task_{int(task.get('id') or 0)}",
        "node_name": _text(task.get("task_name")) or "自动化运营任务",
        "target_audience_code": _text(task.get("target_audience_code")),
        "trigger_mode": _text(task.get("trigger_type")),
        "day_offset": _int(task.get("audience_day_offset"), default=1, minimum=1),
        "send_time": _text(task.get("send_time")),
        "content_mode": "personalized_single",
        "segmentation_basis": SEGMENTATION_BASIS_NONE,
        "standard_content_text": standard_content_text,
    }
    agent_code = _text(config.get("agent_code"))
    behavior_match = workflow_runtime._resolve_behavior_segment_match(member)
    generated = workflow_runtime._generate_content_with_agent(
        member=member,
        workflow_bundle=workflow_bundle,
        node=node,
        agent_binding={
            "agent_code": agent_code,
            "binding_scope": AGENT_BINDING_SCOPE_PERSONALIZED,
        },
        standard_content_text=standard_content_text,
        segment_match={"matched": False, "segment_key": "", "segment_label": "", "reason": "operation_task_personalized"},
        behavior_match=behavior_match,
        request_id=_text(request_id) or f"operation-task-{int(task.get('id') or 0)}-{int(member.get('id') or 0)}",
        generation_source="automation_operation_task",
    )
    content = {
        **config,
        "agent_config": config,
        "agent_code": _text(generated.get("agent_code")) or agent_code,
        "agent_published_prompt_present": bool(agent_context.get("agent_published_prompt_present")),
        "agent_published_role_prompt_present": bool(agent_context.get("agent_published_role_prompt_present")),
        "agent_published_task_prompt_present": bool(agent_context.get("agent_published_task_prompt_present")),
        "questionnaire_context_required": bool(agent_context.get("questionnaire_context_required")),
        "questionnaire_context_available": bool(agent_context.get("questionnaire_context_available")),
        "questionnaire_submission_id": int(agent_context.get("questionnaire_submission_id") or 0),
        "questionnaire_answer_count": int(agent_context.get("questionnaire_answer_count") or 0),
        "generation_source": "automation_operation_task",
        "content_source": _text(generated.get("content_source")) or "standard_content",
        "fallback_reason": _text(generated.get("fallback_reason")),
        "agent_run_id": _text(generated.get("agent_run_id")),
        "agent_output_id": _text(generated.get("agent_output_id")),
        "behavior_match": behavior_match,
        "agent_runtime_context": agent_context,
    }
    return "agent", _text(generated.get("content_text")) or standard_content_text, content


def _render_for_member(task: dict[str, Any], member: dict[str, Any], *, request_id: str = "") -> tuple[str, str, dict[str, Any]]:
    mode = _text(task.get("content_mode")) or "unified"
    if mode == "behavior_layered":
        segment_key = _behavior_key(member)
        content = _segment_content(task, segment_key)
        return segment_key, _text(content.get("content_text")), content
    if mode == "profile_layered":
        segment_key = _profile_key(member, task.get("profile_segment_template_id"))
        content = _segment_content(task, segment_key)
        return segment_key, _text(content.get("content_text")), content
    if mode == "agent":
        return _render_agent_for_member(task=task, member=member, request_id=request_id)
    content = dict(task.get("unified_content_json") or {})
    return "unified", _text(content.get("content_text")), content


def _content_image_media_ids(content: dict[str, Any]) -> list[str]:
    media_ids: list[str] = []
    for media_id in list(content.get("image_media_ids") or []):
        normalized = _text(media_id)
        if normalized:
            media_ids.append(normalized)
    image_library_ids = [_int(item, minimum=1) for item in list(content.get("image_library_ids") or []) if _int(item, minimum=0) > 0]
    if image_library_ids:
        from .. import image_library

        for library_id in image_library_ids[:3]:
            media_id = _text(image_library.resolve_image_media_id(int(library_id)))
            if media_id:
                media_ids.append(media_id)
    return list(dict.fromkeys(media_ids))


def _content_miniprogram_library_ids(content: dict[str, Any]) -> list[int]:
    return [_int(item, minimum=1) for item in list(content.get("miniprogram_library_ids") or []) if _int(item, minimum=0) > 0]


def _content_attachment_library_ids(content: dict[str, Any]) -> list[int]:
    return [_int(item, minimum=1) for item in list(content.get("attachment_library_ids") or []) if _int(item, minimum=0) > 0][:9]


def _content_has_send_body(content_text: str, content: dict[str, Any]) -> bool:
    return contract_has_send_body(content, content_text=content_text)


def _diagnostic_reason_from_contract(task: dict[str, Any], diagnostics: dict[str, Any]) -> str:
    errors = list(diagnostics.get("errors") or [])
    if not errors:
        return ""
    if "questionnaire_context_missing" in errors:
        return "questionnaire_context_missing"
    if "agent_runtime_content_missing" in errors:
        return "agent_runtime_content_missing"
    if "behavior_segment_content_missing" in errors:
        return "behavior_segment_content_missing"
    if "content_missing" in errors:
        return "content_missing"
    return "task_unpublishable"


def _render_result_summary_for_entry(task: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any]:
    member = dict(entry.get("member") or {})
    mode = _text(task.get("content_mode")) or "unified"
    if mode == "agent":
        agent_context = _agent_runtime_context(task, member=member)
        agent_diag = agent_runtime_diagnostics(task, agent_runtime_context=agent_context)
        return {
            "content_mode": mode,
            "segment_key": "agent",
            "content_text_present": False,
            "send_body_present": bool(agent_diag.get("expected_send_body_present")),
            "external_contact_id_present": bool(_text(member.get("external_contact_id"))),
            "agent_runtime_diagnostics": agent_diag,
            "agent_runtime_context": agent_context,
        }
    segment_key, content_text, content = _render_for_member(task, member, request_id="diagnostic")
    return {
        "content_mode": mode,
        "segment_key": segment_key,
        "content_text_present": bool(_text(content_text)),
        "send_body_present": _content_has_send_body(content_text, content),
        "external_contact_id_present": bool(_text(member.get("external_contact_id"))),
    }


def _diagnostic_reason_from_render(task: dict[str, Any], summary: dict[str, Any]) -> str:
    if not bool(summary.get("external_contact_id_present")):
        return "external_contact_id_missing"
    if bool(summary.get("send_body_present")):
        return ""
    mode = _text(task.get("content_mode")) or "unified"
    if mode == "agent":
        agent_diag = dict(summary.get("agent_runtime_diagnostics") or {})
        if (
            agent_diag.get("agent_published_prompt_present")
            and agent_diag.get("questionnaire_context_required")
            and not agent_diag.get("questionnaire_context_available")
            and not agent_diag.get("task_instruction_present")
            and not agent_diag.get("task_material_present")
        ):
            return "questionnaire_context_missing"
        return "agent_runtime_content_missing"
    if mode == "behavior_layered":
        return "behavior_segment_content_missing"
    return "content_missing"


def _execution_without_items(execution: dict[str, Any], items: list[dict[str, Any]]) -> bool:
    if not execution or items:
        return False
    summary = dict(execution.get("summary_json") or {})
    status = _text(execution.get("status"))
    return status in {"failed", "finished", "queued"} and int(summary.get("created_item_count") or 0) == 0


def _event_task_diagnostic_result(
    *,
    task: dict[str, Any],
    execution_id: str,
    audience_entry_id: int,
    enqueued_count: int,
    status: str = "",
    reason: str = "",
    render_result_summary: Any = None,
    blocked_by_existing_execution: bool = False,
    blocked_by_existing_job: bool = False,
) -> dict[str, Any]:
    render_summary = dict(render_result_summary) if isinstance(render_result_summary, dict) else {}
    agent_context = dict(render_summary.get("agent_runtime_context") or {})
    diagnostics = publishable_diagnostics(task, agent_runtime_context=agent_context or None)
    result = {
        "task_id": int(task.get("id") or 0),
        "task_name": _text(task.get("task_name")),
        "execution_id": _text(execution_id),
        "audience_entry_id": int(audience_entry_id or 0),
        "enqueued_count": int(enqueued_count or 0),
        "status": _text(status),
        "reason": _text(reason) or _diagnostic_reason_from_contract(task, diagnostics) or "ok",
        "content_diagnostics": diagnostics,
        "agent_runtime_diagnostics": agent_runtime_diagnostics(task, agent_runtime_context=agent_context or None)
        if _text(task.get("content_mode")) == "agent"
        else {},
        "render_result_summary": dict(render_result_summary)
        if isinstance(render_result_summary, dict)
        else {"items": list(render_result_summary or [])}
        if isinstance(render_result_summary, list)
        else {},
        "blocked_by_existing_execution": bool(blocked_by_existing_execution),
        "blocked_by_existing_job": bool(blocked_by_existing_job),
    }
    return result


def _program_channels(program_id: int, *, include_inactive: bool = True) -> list[dict[str, Any]]:
    if not int(program_id or 0):
        return []
    sql = """
        SELECT DISTINCT c.*
        FROM automation_channel c
        WHERE (
            c.program_id = ?
            OR c.id IN (
                SELECT channel_id
                FROM automation_program_channel_binding
                WHERE program_id = ?
            )
        )
    """
    params: list[Any] = [int(program_id), int(program_id)]
    if not include_inactive:
        sql += " AND c.status IN ('active', 'configured')"
    sql += " ORDER BY c.updated_at DESC, c.id DESC"
    return [dict(row or {}) for row in get_db().execute(sql, tuple(params)).fetchall()]


def _program_channel_ids(program_id: int) -> set[int]:
    return {
        int(channel.get("id") or 0)
        for channel in _program_channels(int(program_id), include_inactive=True)
        if int(channel.get("id") or 0)
    }


def _member_in_program_channels(member: dict[str, Any], program_channel_ids: set[int]) -> bool:
    if not program_channel_ids:
        return False
    return _int(member.get("source_channel_id"), minimum=0) in program_channel_ids


def _program_channel_sender_userid(program_id: int) -> str:
    if not int(program_id or 0):
        return workflow_runtime.DEFAULT_AUTOMATION_SENDER
    channels = _program_channels(int(program_id), include_inactive=True)
    default_channel_codes = {f"program_{int(program_id)}_default_qrcode", "default_qrcode"}
    for channel in channels:
        if _text(channel.get("channel_code")) not in default_channel_codes:
            continue
        sender = _text(channel.get("owner_staff_id"))
        if sender:
            return sender
    channels = [channel for channel in channels if _text(channel.get("status")) in {"active", "configured"}]
    for channel in channels:
        sender = _text(channel.get("owner_staff_id"))
        if sender:
            return sender
    return workflow_runtime.DEFAULT_AUTOMATION_SENDER


def _is_duplicate_schedule_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return (
        "uq_broadcast_jobs_source_scheduled" in message
        or "duplicate key" in message
        or "unique constraint" in message
        or "unique failed" in message
    )


def _refresh_execution_status(execution_id: str) -> dict[str, Any]:
    execution = repo.get_execution(execution_id) or {}
    items = repo.list_execution_items(execution_id)
    sent_count = sum(1 for item in items if _text(item.get("status")) == "sent")
    failed_count = sum(1 for item in items if _text(item.get("status")) in {"failed", "skipped"})
    queued_count = sum(1 for item in items if _text(item.get("status")) in {"queued", "pending", "running"})
    if queued_count:
        status = "queued"
    elif failed_count and sent_count:
        status = "partial_failed"
    elif failed_count:
        status = "failed"
    else:
        status = "finished"
    return repo.update_execution(
        execution_id,
        {
            "status": status,
            "target_count": int(execution.get("target_count") or len(items)),
            "enqueued_count": len(items),
            "sent_count": sent_count,
            "failed_count": failed_count,
            "summary_json": {
                **dict(execution.get("summary_json") or {}),
                "sent_count": sent_count,
                "failed_count": failed_count,
                "queued_count": queued_count,
            },
        },
    )


def _materialize_operation_task_execution(
    *,
    task: dict[str, Any],
    scheduled_for: datetime,
    operator_id: str,
    entries: list[dict[str, Any]] | None = None,
    execution_id: str = "",
    summary_extra: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    execution_id = _text(execution_id) or _execution_id_for_task(int(task["id"]), scheduled_for)
    execution = repo.insert_execution(
        {
            "execution_id": execution_id,
            "program_id": task["program_id"],
            "task_id": task["id"],
            "scheduled_for": scheduled_for,
            "status": "running",
            "target_count": 0,
        }
    )
    existing_items = repo.list_execution_items(execution_id)
    if existing_items:
        return execution, existing_items

    entries = list(entries) if entries is not None else _candidate_entries(task, now=scheduled_for)
    agent_context = _agent_runtime_context_for_entries(task, entries) if _text(task.get("content_mode")) == "agent" else None
    diagnostics = publishable_diagnostics(task, agent_runtime_context=agent_context)
    contract_reason = _diagnostic_reason_from_contract(task, diagnostics)
    if contract_reason:
        execution = repo.update_execution(
            execution_id,
            {
                "status": "failed" if entries else "finished",
                "target_count": len(entries),
                "enqueued_count": 0,
                "sent_count": 0,
                "failed_count": len(entries),
                "summary_json": {
                    "created_item_count": 0,
                    "materialized_by": _text(operator_id) or "operation_task_runner",
                    "reason": contract_reason,
                    "content_diagnostics": diagnostics,
                    "no_execution_items": True,
                    **dict(summary_extra or {}),
                },
            },
        )
        return execution, []

    created_items: list[dict[str, Any]] = []
    failed_count = 0
    skipped_summaries: list[dict[str, Any]] = []
    for entry in entries:
        member = dict(entry.get("member") or {})
        render_request_id = f"{execution_id}:{int(entry.get('id') or 0) or int(member.get('id') or 0)}"
        if _text(task.get("content_mode")) == "agent":
            entry_agent_context = _agent_runtime_context(task, member=member)
            entry_diagnostics = publishable_diagnostics(task, agent_runtime_context=entry_agent_context)
            entry_contract_reason = _diagnostic_reason_from_contract(task, entry_diagnostics)
            if entry_contract_reason:
                failed_count += 1
                skipped_summaries.append(
                    {
                        "audience_entry_id": int(entry.get("id") or 0),
                        "member_id": int(member.get("id") or entry.get("member_id") or 0),
                        "segment_key": "agent",
                        "content_text_present": False,
                        "send_body_present": False,
                        "external_contact_id_present": bool(_text(member.get("external_contact_id"))),
                        "reason": entry_contract_reason,
                        "content_diagnostics": entry_diagnostics,
                        "agent_runtime_diagnostics": entry_diagnostics.get("details", {}).get("agent_runtime_diagnostics") or {},
                        "agent_runtime_context": entry_agent_context,
                    }
                )
                continue
        segment_key, content_text, content = _render_for_member(task, member, request_id=render_request_id)
        if not _content_has_send_body(content_text, content) or not _text(member.get("external_contact_id")):
            failed_count += 1
            render_summary = {
                "audience_entry_id": int(entry.get("id") or 0),
                "member_id": int(member.get("id") or entry.get("member_id") or 0),
                "segment_key": segment_key,
                "content_text_present": bool(_text(content_text)),
                "send_body_present": _content_has_send_body(content_text, content),
                "external_contact_id_present": bool(_text(member.get("external_contact_id"))),
            }
            render_summary["reason"] = _diagnostic_reason_from_render(task, render_summary)
            skipped_summaries.append(render_summary)
            continue
        item = repo.insert_execution_item(
            {
                "execution_id": execution_id,
                "task_id": task["id"],
                "member_id": entry.get("member_id"),
                "audience_entry_id": entry.get("id"),
                "external_contact_id": member.get("external_contact_id"),
                "segment_key": segment_key,
                "rendered_content_text": content_text,
                "content_snapshot_json": content,
                "status": "queued",
            }
        )
        if item:
            created_items.append(item)
    execution_status = "queued" if created_items else ("finished" if not entries else "failed")
    execution = repo.update_execution(
        execution_id,
        {
            "status": execution_status,
            "target_count": len(entries),
            "enqueued_count": len(created_items),
            "sent_count": 0,
            "failed_count": max(failed_count, len(entries) - len(created_items)),
            "summary_json": {
                "created_item_count": len(created_items),
                "materialized_by": _text(operator_id) or "operation_task_runner",
                "reason": "" if created_items else (skipped_summaries[0].get("reason") if skipped_summaries else ""),
                "render_result_summary": skipped_summaries[:10],
                "no_execution_items": not bool(created_items),
                **dict(summary_extra or {}),
            },
        },
    )
    return execution, created_items


def _entry_matches_event_task(task: dict[str, Any], entry: dict[str, Any]) -> bool:
    if _text(task.get("status")) != "active":
        return False
    if _text(task.get("trigger_type")) != "audience_entered":
        return False
    stage_filter = resolve_stage_target_filter(
        int(task.get("program_id") or 0),
        _text(task.get("target_stage_code")),
        fallback_audience_code=_text(task.get("target_audience_code")),
    )
    if stage_filter["audience_code"] != _text(entry.get("audience_code")):
        return False
    if stage_filter["entry_reason"] and stage_filter["entry_reason"] != _text(entry.get("entry_reason")):
        return False
    member = dict(_entry_for_task(task, entry).get("member") or {})
    if not _member_in_program_channels(member, _program_channel_ids(int(task.get("program_id") or 0))):
        return False
    behavior_filter = _text(task.get("behavior_filter")) or "none"
    if behavior_filter != "none" and _behavior_key(member) != behavior_filter:
        return False
    return True


def _entry_bundle_for_event(*, member_id: int, audience_entry_id: int = 0, audience_code: str = "") -> dict[str, Any] | None:
    member = workflow_repo.get_automation_member_row(int(member_id))
    if not member:
        return None
    entries = workflow_repo.list_member_audience_entry_rows(int(member_id), current_only=True)
    selected: dict[str, Any] | None = None
    for entry in entries:
        if audience_entry_id and int(entry.get("id") or 0) == int(audience_entry_id):
            selected = dict(entry)
            break
    if selected is None:
        for entry in entries:
            if not _text(audience_code) or _text(entry.get("audience_code")) == _text(audience_code):
                selected = dict(entry)
                break
    if selected is None:
        return None
    selected["member"] = dict(member)
    return selected


def _program_id_for_audience_entry(entry: dict[str, Any], *, source_channel_id: int) -> int:
    snapshot = dict(entry.get("source_snapshot_json") or {})
    program_id = _int(snapshot.get("program_id"), minimum=0)
    if program_id > 0:
        return program_id
    program_member_id = _int(snapshot.get("program_member_id"), minimum=0)
    if program_member_id > 0:
        row = get_db().execute(
            "SELECT program_id FROM automation_program_member WHERE id = ? LIMIT 1",
            (program_member_id,),
        ).fetchone()
        if row and int(row.get("program_id") or 0) > 0:
            return int(row["program_id"])
    binding_id = _int(snapshot.get("binding_id"), minimum=0)
    if binding_id > 0:
        row = get_db().execute(
            "SELECT program_id FROM automation_program_channel_binding WHERE id = ? LIMIT 1",
            (binding_id,),
        ).fetchone()
        if row and int(row.get("program_id") or 0) > 0:
            return int(row["program_id"])
    channel_row = get_db().execute(
        "SELECT program_id FROM automation_channel WHERE id = ? LIMIT 1",
        (int(source_channel_id),),
    ).fetchone()
    return int((channel_row or {}).get("program_id") or 0)


def run_audience_entered_operation_tasks(
    *,
    member_id: int,
    audience_code: str,
    audience_entry_id: int = 0,
    now: datetime | None = None,
    operator_id: str = "operation_task_event",
) -> dict[str, Any]:
    entry = _entry_bundle_for_event(
        member_id=int(member_id),
        audience_entry_id=int(audience_entry_id or 0),
        audience_code=_text(audience_code),
    )
    if not entry:
        return {"ok": True, "ran": 0, "enqueued_count": 0, "results": [], "reason": "audience_entry_not_found"}
    current_time = now or _now()
    member = dict(entry.get("member") or {})
    source_channel_id = _int(member.get("source_channel_id"), minimum=0)
    if source_channel_id <= 0:
        return {"ok": True, "ran": 0, "enqueued_count": 0, "results": [], "reason": "source_channel_missing"}
    program_id = _program_id_for_audience_entry(entry, source_channel_id=source_channel_id)
    if program_id <= 0:
        return {"ok": True, "ran": 0, "enqueued_count": 0, "results": [], "reason": "program_channel_missing"}
    tasks = repo.list_tasks(program_id, status="active")
    results: list[dict[str, Any]] = []
    for task in tasks:
        scoped_entry = _entry_for_task(task, entry)
        if not _entry_matches_event_task(task, scoped_entry):
            continue
        execution_id = _event_execution_id_for_task(int(task["id"]), int(scoped_entry.get("id") or 0))
        source_id = f"{int(task['id'])}:audience_entered:{int(scoped_entry.get('id') or 0)}"
        existing_execution = repo.get_execution(execution_id)
        existing_items = repo.list_execution_items(execution_id) if existing_execution else []
        existing_job = broadcast_queue_repo.fetch_job_by_source(
            source_type="operation_task",
            source_id=source_id,
            source_table="automation_operation_task_execution",
        )
        if existing_execution or existing_job:
            reason = "existing_broadcast_job" if existing_job else "existing_execution"
            if _execution_without_items(existing_execution or {}, existing_items):
                reason = "existing_execution_without_items"
            results.append(
                _event_task_diagnostic_result(
                    task=task,
                    execution_id=execution_id,
                    audience_entry_id=int(scoped_entry.get("id") or 0),
                    enqueued_count=0,
                    status=_text((existing_execution or {}).get("status") or (existing_job or {}).get("status")),
                    reason=reason,
                    render_result_summary=dict((existing_execution or {}).get("summary_json") or {}).get("render_result_summary")
                    or {},
                    blocked_by_existing_execution=bool(existing_execution),
                    blocked_by_existing_job=bool(existing_job),
                )
            )
            continue
        execution, items = _materialize_operation_task_execution(
            task=task,
            scheduled_for=current_time,
            operator_id=operator_id,
            entries=[scoped_entry],
            execution_id=execution_id,
            summary_extra={
                "trigger_type": "audience_entered",
                "audience_entry_id": int(scoped_entry.get("id") or 0),
            },
        )
        if not items:
            summary = dict(execution.get("summary_json") or {})
            render_summary = summary.get("render_result_summary") or _render_result_summary_for_entry(task, scoped_entry)
            results.append(
                _event_task_diagnostic_result(
                    task=task,
                    execution_id=execution_id,
                    audience_entry_id=int(scoped_entry.get("id") or 0),
                    enqueued_count=0,
                    status=_text(execution.get("status")),
                    reason=_text(summary.get("reason")) or _diagnostic_reason_from_render(task, render_summary),
                    render_result_summary=render_summary if isinstance(render_summary, dict) else {"items": render_summary},
                )
            )
            continue
        job_id = broadcast_queue.enqueue_job(
            source_type="operation_task",
            source_id=source_id,
            source_table="automation_operation_task_execution",
            scheduled_for=current_time,
            target_external_userids=[],
            target_summary=f"{task.get('task_name')} 入池即触发",
            content_type="private_message",
            content_payload={
                "trigger_type": "audience_entered",
                "scheduled_for": current_time.strftime("%Y-%m-%d %H:%M:%S"),
                "execution_id": execution_id,
                "task_id": int(task["id"]),
                "operator_id": operator_id,
            },
            content_summary=_text(task.get("task_name"))[:100],
            trace_id=execution_id,
            created_by=operator_id,
            allow_empty_targets=True,
        )
        results.append(
            _event_task_diagnostic_result(
                task=task,
                execution_id=execution_id,
                audience_entry_id=int(scoped_entry.get("id") or 0),
                enqueued_count=1,
                status="queued",
                reason="ok",
                render_result_summary={"created_item_count": len(items), "job_id": int(job_id or 0), "source_id": source_id},
            )
            | {"scheduled_for": current_time.strftime("%Y-%m-%d %H:%M:%S")}
        )
    get_db().commit()
    return {
        "ok": True,
        "ran": len(results),
        "enqueued_count": sum(int(item.get("enqueued_count") or 0) for item in results),
        "results": results,
    }


def run_operation_task_broadcast_job(job: dict[str, Any]) -> dict[str, Any]:
    payload = dict(job.get("content_payload") or {})
    task_id = _int(payload.get("task_id"), minimum=0)
    task = repo.get_task(task_id) if task_id else None
    if not task:
        return {"ok": False, "error": "operation_task not found"}
    if _text(task.get("status")) != "active":
        return {"ok": True, "sent_count": 0, "failed_count": 0, "status": "task_inactive"}
    scheduled_for = _parse_date(payload.get("scheduled_for")) or _parse_date(job.get("scheduled_for")) or _now()
    if payload.get("pre_scheduled") or not _text(payload.get("execution_id") or job.get("trace_id")):
        execution, _ = _materialize_operation_task_execution(
            task=task,
            scheduled_for=scheduled_for,
            operator_id=_text(payload.get("operator_id")) or "operation_task_runner",
        )
        execution_id = _text(execution.get("execution_id"))
    else:
        execution_id = _text(payload.get("execution_id") or job.get("trace_id"))
    segment_key = _text(payload.get("segment_key"))
    if not execution_id or not task_id:
        return {"ok": False, "error": "operation_task job missing execution_id or task_id"}

    target_external_userids = {
        _text(item)
        for item in list(job.get("target_external_userids") or [])
        if _text(item)
    }
    items = repo.list_execution_items(execution_id, statuses=["queued"])
    selected_items: list[dict[str, Any]] = []
    for item in items:
        if int(item.get("task_id") or 0) != task_id:
            continue
        if segment_key and _text(item.get("segment_key")) != segment_key:
            continue
        if target_external_userids and _text(item.get("external_contact_id")) not in target_external_userids:
            continue
        selected_items.append(item)
    if not selected_items:
        return {"ok": True, "sent_count": 0, "failed_count": 0, "status": "already_processed"}

    task_sender_userid = _program_channel_sender_userid(int(task.get("program_id") or 0))
    prepared_groups: dict[tuple[str, str, tuple[str, ...], tuple[int, ...], tuple[int, ...]], list[dict[str, Any]]] = {}
    failed_before_send = 0
    for item in selected_items:
        member = workflow_repo.get_automation_member_row(int(item.get("member_id") or 0)) or {}
        external_userid = _text(item.get("external_contact_id") or member.get("external_contact_id"))
        content_text = _text(item.get("rendered_content_text"))
        content = dict(item.get("content_snapshot_json") or {})
        if not member or not external_userid or not _content_has_send_body(content_text, content):
            repo.update_execution_item(
                int(item["id"]),
                {
                    **item,
                    "status": "failed",
                    "error_message": "发送对象或发送内容缺失",
                    "rendered_content_text": content_text,
                    "content_snapshot_json": dict(item.get("content_snapshot_json") or {}),
                },
            )
            failed_before_send += 1
            continue
        image_media_ids = tuple(_content_image_media_ids(content))
        miniprogram_library_ids = tuple(_content_miniprogram_library_ids(content))
        attachment_library_ids = tuple(_content_attachment_library_ids(content))
        sender_userid = task_sender_userid
        prepared = {
            "item": item,
            "member": member,
            "external_userid": external_userid,
            "sender_userid": sender_userid,
            "content_text": content_text,
            "content": content,
            "image_media_ids": list(image_media_ids),
            "miniprogram_library_ids": list(miniprogram_library_ids),
            "attachment_library_ids": list(attachment_library_ids),
        }
        prepared_groups.setdefault((sender_userid, content_text, image_media_ids, miniprogram_library_ids, attachment_library_ids), []).append(prepared)

    sent_count = 0
    failed_count = failed_before_send
    outbound_task_id: int | None = None
    for group in prepared_groups.values():
        first = group[0]
        send_result = _dispatch_private_message_batch(
            target_items=[
                {
                    "external_userid": _text(item.get("external_userid")),
                    "owner_display_name": _text(item.get("sender_userid")),
                }
                for item in group
            ],
            sender_userid=_text(first.get("sender_userid")) or workflow_runtime.DEFAULT_AUTOMATION_SENDER,
            content=_text(first.get("content_text")),
            image_media_ids=list(first.get("image_media_ids") or []),
            miniprogram_library_ids=list(first.get("miniprogram_library_ids") or []),
            attachment_library_ids=list(first.get("attachment_library_ids") or []),
            operator_id=_text(payload.get("operator_id")) or "operation_task_runner",
            filter_snapshot={
                "selection_mode": "automation_operation_task",
                "task_id": task_id,
                "execution_id": execution_id,
                "segment_key": segment_key,
                "execution_item_ids": [int(dict(item.get("item") or {}).get("id") or 0) for item in group],
                "broadcast_job_id": int(job.get("id") or 0),
            },
        )
        if not outbound_task_id and (send_result.get("task_ids") or []):
            outbound_task_id = int((send_result.get("task_ids") or [0])[0] or 0) or None
        failed_external_userids = {
            _text(item)
            for item in list(send_result.get("fail_external_userids") or [])
            if _text(item)
        }
        batch_failed = _text(send_result.get("status")) == "failed" and not int(send_result.get("sent_count") or 0)
        for prepared in group:
            item = dict(prepared.get("item") or {})
            external_userid = _text(prepared.get("external_userid"))
            item_failed = batch_failed or external_userid in failed_external_userids
            repo.update_execution_item(
                int(item["id"]),
                {
                    **item,
                    "status": "failed" if item_failed else "sent",
                    "error_message": _text(send_result.get("error_message")) if item_failed else "",
                    "rendered_content_text": _text(prepared.get("content_text")),
                    "content_snapshot_json": {
                        **dict(prepared.get("content") or {}),
                        "sender_userid": _text(prepared.get("sender_userid")),
                    },
                    "send_record_id": int(send_result.get("record_id") or 0) or None,
                },
            )
            if item_failed:
                failed_count += 1
            else:
                sent_count += 1

    refreshed_execution = _refresh_execution_status(execution_id)
    get_db().commit()
    return {
        "ok": True,
        "sent_count": sent_count,
        "failed_count": failed_count,
        "outbound_task_id": outbound_task_id,
        "execution_status": refreshed_execution.get("status"),
    }


def run_due_operation_tasks(*, program_id: int | None = None, now: datetime | None = None, operator_id: str = "operation_task_runner") -> dict[str, Any]:
    current_time = now or _now()
    try:
        workflow_runtime.sync_all_conversion_member_audiences()
    except Exception:
        pass
    programs = [int(program_id)] if program_id else []
    tasks: list[dict[str, Any]] = []
    if programs:
        tasks = repo.list_tasks(programs[0], status="active")
    else:
        rows = get_db().execute("SELECT DISTINCT program_id FROM automation_operation_task WHERE status = 'active'").fetchall()
        for row in rows:
            tasks.extend(repo.list_tasks(int(row["program_id"]), status="active"))
    results: list[dict[str, Any]] = []
    for task in tasks:
        if _text(task.get("trigger_type")) == "audience_entered":
            continue
        schedule_dates = [
            current_time,
            current_time + timedelta(days=1),
        ]
        for schedule_base in schedule_dates:
            scheduled_for = _task_scheduled_for(task, schedule_base)
            execution_id = _execution_id_for_task(int(task["id"]), scheduled_for)
            if repo.get_execution(execution_id):
                continue
            source_id = f"{int(task['id'])}:schedule:{scheduled_for.strftime('%Y%m%d%H%M')}"
            if broadcast_queue_repo.fetch_job_by_source(
                source_type="operation_task",
                source_id=source_id,
                source_table="automation_operation_task_execution",
            ):
                continue
            try:
                broadcast_queue.enqueue_job(
                    source_type="operation_task",
                    source_id=source_id,
                    source_table="automation_operation_task_execution",
                    scheduled_for=scheduled_for,
                    target_external_userids=[],
                    target_summary=f"{task.get('task_name')} 到点现场筛选",
                    content_type="private_message",
                    content_payload={
                        "pre_scheduled": True,
                        "scheduled_for": scheduled_for.strftime("%Y-%m-%d %H:%M:%S"),
                        "task_id": int(task["id"]),
                        "operator_id": operator_id,
                    },
                    content_summary=_text(task.get("task_name"))[:100],
                    trace_id=execution_id,
                    created_by=operator_id,
                    allow_empty_targets=True,
                )
            except Exception as exc:
                if _is_duplicate_schedule_error(exc):
                    try:
                        get_db().rollback()
                    except Exception:
                        pass
                    continue
                raise
            results.append(
                {
                    "task_id": int(task["id"]),
                    "execution_id": execution_id,
                    "scheduled_for": scheduled_for.strftime("%Y-%m-%d %H:%M:%S"),
                    "enqueued_count": 1,
                }
            )
    get_db().commit()
    return {
        "ok": True,
        "ran": len(results),
        "enqueued_count": sum(int(item.get("enqueued_count") or 0) for item in results),
        "failed_count": 0,
        "results": results,
    }
