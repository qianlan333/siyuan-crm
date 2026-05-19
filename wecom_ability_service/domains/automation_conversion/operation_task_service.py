from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from ...db import get_db
from ..broadcast_jobs import repo as broadcast_queue_repo
from ..broadcast_jobs import service as broadcast_queue
from . import operation_task_repo as repo
from . import repo as channel_repo
from . import workflow_repo
from . import workflow_runtime
from .private_message_dispatch import _dispatch_private_message_batch
from .workflow_definitions import (
    AUDIENCE_CONVERTED,
    AUDIENCE_OPERATING,
    AUDIENCE_PENDING_QUESTIONNAIRE,
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
        raise ValueError("目标人群不正确")
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
        "target_audience_code": audience_code,
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
    mode = _text(task.get("content_mode")) or "unified"
    if mode == "unified" and not _text((task.get("unified_content_json") or {}).get("content_text")):
        raise ValueError("统一内容不能为空")
    if mode == "agent" and not _text((task.get("agent_config_json") or {}).get("agent_code")):
        raise ValueError("请选择 Agent")
    if mode in {"behavior_layered", "profile_layered"}:
        contents = list(task.get("segment_contents_json") or [])
        if not contents:
            raise ValueError("请先填写分层话术")
        missing = [item for item in contents if not _text(item.get("content_text"))]
        if missing:
            raise ValueError("每个分层都需要填写话术")


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
        "tasks": repo.list_tasks(int(program_id), group_id=group_id, status=status, keyword=keyword),
        "behavior_tiers": list_supported_behavior_tiers(),
    }


def get_operation_task(task_id: int) -> dict[str, Any]:
    task = repo.get_task(int(task_id))
    if not task:
        raise LookupError("任务不存在")
    return {"task": task}


def create_operation_task(program_id: int, payload: dict[str, Any], *, operator_id: str) -> dict[str, Any]:
    normalized = _normalize_task_payload(payload, program_id=int(program_id), operator_id=operator_id)
    task = repo.insert_task(normalized)
    get_db().commit()
    return {"task": task}


def update_operation_task(task_id: int, payload: dict[str, Any], *, operator_id: str) -> dict[str, Any]:
    existing = repo.get_task(int(task_id))
    if not existing:
        raise LookupError("任务不存在")
    normalized = _normalize_task_payload(payload, program_id=int(existing["program_id"]), operator_id=operator_id, existing=existing)
    task = repo.update_task(int(task_id), normalized)
    get_db().commit()
    return {"task": task}


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
    return {"task": task}


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


def _candidate_entries(task: dict[str, Any], *, now: datetime | None = None) -> list[dict[str, Any]]:
    current_time = now or _now()
    program_channel_ids = _program_channel_ids(int(task.get("program_id") or 0))
    entries = repo.list_current_audience_entries(_text(task.get("target_audience_code")) or AUDIENCE_OPERATING)
    result: list[dict[str, Any]] = []
    for entry in entries:
        member = dict(entry.get("member") or {})
        if not _member_in_program_channels(member, program_channel_ids):
            continue
        if _text(task.get("trigger_type")) != "audience_entered" and not _entry_due(
            entry,
            day_offset=_int(task.get("audience_day_offset"), default=1, minimum=1),
            now=current_time,
        ):
            continue
        behavior_filter = _text(task.get("behavior_filter")) or "none"
        if behavior_filter != "none" and _behavior_key(member) != behavior_filter:
            continue
        result.append(entry)
    return result


def preview_operation_task_audience(program_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    task = _normalize_task_payload(
        {"task_name": payload.get("task_name") or "预览任务", **dict(payload or {})},
        program_id=int(program_id),
        operator_id="preview",
    )
    entries = _candidate_entries(task)
    segment_counts: dict[str, int] = {}
    if task["content_mode"] == "behavior_layered":
        for entry in entries:
            key = _behavior_key(dict(entry.get("member") or {}))
            if key:
                segment_counts[key] = segment_counts.get(key, 0) + 1
    elif task["content_mode"] == "profile_layered":
        for entry in entries:
            key = _profile_key(dict(entry.get("member") or {}), task.get("profile_segment_template_id"))
            if key:
                segment_counts[key] = segment_counts.get(key, 0) + 1
    return {"preview": {"target_count": len(entries), "segment_counts": segment_counts}}


def _segment_content(task: dict[str, Any], segment_key: str) -> dict[str, Any]:
    for item in list(task.get("segment_contents_json") or []):
        if _text(item.get("segment_key")) == segment_key:
            return dict(item)
    return {}


def _render_for_member(task: dict[str, Any], member: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
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
        config = dict(task.get("agent_config_json") or {})
        content_text = _text(config.get("fallback_content")) or _text(config.get("requirement")) or _text(task.get("description"))
        return "agent", content_text, {**config, "agent_config": config}
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
    return bool(
        _text(content_text)
        or [_text(item) for item in list(content.get("image_media_ids") or []) if _text(item)]
        or [_int(item, minimum=1) for item in list(content.get("image_library_ids") or []) if _int(item, minimum=0) > 0]
        or _content_miniprogram_library_ids(content)
        or _content_attachment_library_ids(content)
    )


def _program_channel_ids(program_id: int) -> set[int]:
    if not int(program_id or 0):
        return set()
    return {
        int(channel.get("id") or 0)
        for channel in channel_repo.list_channels_by_program(int(program_id), include_inactive=True)
        if int(channel.get("id") or 0)
    }


def _member_in_program_channels(member: dict[str, Any], program_channel_ids: set[int]) -> bool:
    if not program_channel_ids:
        return False
    return _int(member.get("source_channel_id"), minimum=0) in program_channel_ids


def _program_channel_sender_userid(program_id: int) -> str:
    if not int(program_id or 0):
        return workflow_runtime.DEFAULT_AUTOMATION_SENDER
    channels = channel_repo.list_channels_by_program(int(program_id), include_inactive=True)
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
    created_items: list[dict[str, Any]] = []
    failed_count = 0
    for entry in entries:
        member = dict(entry.get("member") or {})
        segment_key, content_text, content = _render_for_member(task, member)
        if not _content_has_send_body(content_text, content) or not _text(member.get("external_contact_id")):
            failed_count += 1
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
    if _text(task.get("target_audience_code")) != _text(entry.get("audience_code")):
        return False
    member = dict(entry.get("member") or {})
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
    channel_row = get_db().execute(
        "SELECT program_id FROM automation_channel WHERE id = ? LIMIT 1",
        (source_channel_id,),
    ).fetchone()
    if not channel_row or not int(channel_row["program_id"] or 0):
        return {"ok": True, "ran": 0, "enqueued_count": 0, "results": [], "reason": "program_channel_missing"}
    program_id = int(channel_row["program_id"])
    tasks = repo.list_tasks(program_id, status="active")
    results: list[dict[str, Any]] = []
    for task in tasks:
        if not _entry_matches_event_task(task, entry):
            continue
        execution_id = _event_execution_id_for_task(int(task["id"]), int(entry.get("id") or 0))
        source_id = f"{int(task['id'])}:audience_entered:{int(entry.get('id') or 0)}"
        if repo.get_execution(execution_id) or broadcast_queue_repo.fetch_job_by_source(
            source_type="operation_task",
            source_id=source_id,
            source_table="automation_operation_task_execution",
        ):
            continue
        execution, items = _materialize_operation_task_execution(
            task=task,
            scheduled_for=current_time,
            operator_id=operator_id,
            entries=[entry],
            execution_id=execution_id,
            summary_extra={
                "trigger_type": "audience_entered",
                "audience_entry_id": int(entry.get("id") or 0),
            },
        )
        if not items:
            results.append(
                {
                    "task_id": int(task["id"]),
                    "execution_id": execution_id,
                    "enqueued_count": 0,
                    "status": _text(execution.get("status")),
                }
            )
            continue
        broadcast_queue.enqueue_job(
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
            {
                "task_id": int(task["id"]),
                "execution_id": execution_id,
                "enqueued_count": 1,
                "scheduled_for": current_time.strftime("%Y-%m-%d %H:%M:%S"),
            }
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
