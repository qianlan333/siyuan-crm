from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from flask import current_app

from ...db import get_db
from . import repo
from .service import (
    REPLY_MONITOR_DEFAULT_DISPATCH_INTERVAL_SECONDS,
    REPLY_MONITOR_DEFAULT_QUIET_HOURS_END,
    REPLY_MONITOR_DEFAULT_QUIET_HOURS_START,
    REPLY_MONITOR_STATUS_DEFERRED,
    REPLY_MONITOR_STATUS_DISPATCHED,
    REPLY_MONITOR_STATUS_FAILED,
    REPLY_MONITOR_STATUS_PAUSED,
    REPLY_MONITOR_STATUS_PENDING,
    REPLY_MONITOR_TRIGGER_TYPE,
    _member_snapshot,
    _normalize_bool,
    _normalized_text,
    _parse_timestamp,
    _resolve_existing_member,
    _serialize_member,
    _write_event,
)



def _iso_now() -> str:
    """Lazy proxy to service._iso_now so monkeypatch on service._iso_now propagates here."""
    from . import service as _svc
    return _svc._iso_now()


def _reply_monitor_status_label(value: str) -> str:
    normalized = _normalized_text(value)
    return {
        "idle": "空闲",
        "disabled": "已关闭",
        "success": "成功",
        "failed": "失败",
        "running": "执行中",
        "not_configured": "未配置",
    }.get(normalized, normalized or "暂无记录")


def _reply_monitor_queue_status_label(value: str) -> str:
    normalized = _normalized_text(value)
    return {
        REPLY_MONITOR_STATUS_PENDING: "待触发",
        REPLY_MONITOR_STATUS_DEFERRED: "夜间暂缓",
        REPLY_MONITOR_STATUS_DISPATCHED: "已触发",
        REPLY_MONITOR_STATUS_FAILED: "触发失败",
        REPLY_MONITOR_STATUS_PAUSED: "已暂停",
    }.get(normalized, normalized or "未知")


def _reply_monitor_default_config() -> dict[str, Any]:
    return {
        "enabled": False,
        "last_capture_cursor": 0,
        "last_capture_at": "",
        "last_capture_status": "disabled",
        "last_capture_summary_json": {},
        "last_dispatch_at": "",
        "last_dispatch_status": "disabled",
        "last_dispatch_summary_json": {},
        "last_error": "",
        "quiet_hours_start": REPLY_MONITOR_DEFAULT_QUIET_HOURS_START,
        "quiet_hours_end": REPLY_MONITOR_DEFAULT_QUIET_HOURS_END,
        "dispatch_interval_seconds": REPLY_MONITOR_DEFAULT_DISPATCH_INTERVAL_SECONDS,
    }


def _reply_monitor_config() -> dict[str, Any]:
    row = repo.get_reply_monitor_config()
    base = _reply_monitor_default_config()
    if not row:
        return dict(base)
    deserialized = repo.deserialize_reply_monitor_config_row(row)
    return {
        **base,
        **deserialized,
        "enabled": _normalize_bool(deserialized.get("enabled")),
        "last_capture_cursor": int(deserialized.get("last_capture_cursor") or 0),
        "last_capture_summary_json": dict(deserialized.get("last_capture_summary_json") or {}),
        "last_dispatch_summary_json": dict(deserialized.get("last_dispatch_summary_json") or {}),
        "quiet_hours_start": _normalized_text(deserialized.get("quiet_hours_start")) or REPLY_MONITOR_DEFAULT_QUIET_HOURS_START,
        "quiet_hours_end": _normalized_text(deserialized.get("quiet_hours_end")) or REPLY_MONITOR_DEFAULT_QUIET_HOURS_END,
        "dispatch_interval_seconds": int(deserialized.get("dispatch_interval_seconds") or REPLY_MONITOR_DEFAULT_DISPATCH_INTERVAL_SECONDS),
    }


def _save_reply_monitor_config(payload: dict[str, Any]) -> dict[str, Any]:
    current = _reply_monitor_config()
    merged = {
        **current,
        **payload,
        "enabled": _normalize_bool(payload.get("enabled", current.get("enabled"))),
        "last_capture_cursor": int(payload.get("last_capture_cursor", current.get("last_capture_cursor") or 0) or 0),
        "last_capture_summary_json": payload.get("last_capture_summary_json", current.get("last_capture_summary_json") or {}),
        "last_dispatch_summary_json": payload.get("last_dispatch_summary_json", current.get("last_dispatch_summary_json") or {}),
        "quiet_hours_start": _normalized_text(payload.get("quiet_hours_start", current.get("quiet_hours_start"))) or REPLY_MONITOR_DEFAULT_QUIET_HOURS_START,
        "quiet_hours_end": _normalized_text(payload.get("quiet_hours_end", current.get("quiet_hours_end"))) or REPLY_MONITOR_DEFAULT_QUIET_HOURS_END,
        "dispatch_interval_seconds": int(payload.get("dispatch_interval_seconds", current.get("dispatch_interval_seconds") or REPLY_MONITOR_DEFAULT_DISPATCH_INTERVAL_SECONDS) or REPLY_MONITOR_DEFAULT_DISPATCH_INTERVAL_SECONDS),
    }
    saved = repo.save_reply_monitor_config(merged)
    get_db().commit()
    return _reply_monitor_config() if not saved else {
        **_reply_monitor_default_config(),
        **repo.deserialize_reply_monitor_config_row(saved),
        "enabled": _normalize_bool(saved.get("enabled")),
        "last_capture_cursor": int(saved.get("last_capture_cursor") or 0),
        "last_capture_summary_json": dict(repo.deserialize_reply_monitor_config_row(saved).get("last_capture_summary_json") or {}),
        "last_dispatch_summary_json": dict(repo.deserialize_reply_monitor_config_row(saved).get("last_dispatch_summary_json") or {}),
        "quiet_hours_start": _normalized_text(saved.get("quiet_hours_start")) or REPLY_MONITOR_DEFAULT_QUIET_HOURS_START,
        "quiet_hours_end": _normalized_text(saved.get("quiet_hours_end")) or REPLY_MONITOR_DEFAULT_QUIET_HOURS_END,
        "dispatch_interval_seconds": int(saved.get("dispatch_interval_seconds") or REPLY_MONITOR_DEFAULT_DISPATCH_INTERVAL_SECONDS),
    }


def _serialize_reply_monitor_queue_item(row: dict[str, Any]) -> dict[str, Any]:
    deserialized = repo.deserialize_reply_monitor_queue_row(row)
    return {
        "id": int(deserialized.get("id") or 0),
        "member_id": int(deserialized.get("member_id") or 0) if deserialized.get("member_id") not in (None, "") else 0,
        "external_userid": _normalized_text(deserialized.get("external_userid")),
        "owner_userid": _normalized_text(deserialized.get("owner_userid")),
        "status": _normalized_text(deserialized.get("status")),
        "status_label": _reply_monitor_queue_status_label(deserialized.get("status")),
        "message_ids": [int(item) for item in list(deserialized.get("message_ids_json") or []) if str(item).strip()],
        "message_count": int(deserialized.get("message_count") or 0),
        "first_inbound_at": _normalized_text(deserialized.get("first_inbound_at")),
        "last_inbound_at": _normalized_text(deserialized.get("last_inbound_at")),
        "not_before": _normalized_text(deserialized.get("not_before")),
        "last_dispatch_at": _normalized_text(deserialized.get("last_dispatch_at")),
        "error_message": _normalized_text(deserialized.get("error_message")),
        "payload_snapshot": dict(deserialized.get("payload_snapshot_json") or {}),
        "created_at": _normalized_text(deserialized.get("created_at")),
        "updated_at": _normalized_text(deserialized.get("updated_at")),
    }


def _reply_monitor_status_payload() -> dict[str, Any]:
    config = _reply_monitor_config()
    queue_counts = repo.get_reply_monitor_queue_counts()
    recent_items = [_serialize_reply_monitor_queue_item(item) for item in repo.list_recent_reply_monitor_queue_items(limit=12)]
    enabled = _normalize_bool(config.get("enabled"))
    last_capture_status = _normalized_text(config.get("last_capture_status")) or ("disabled" if not enabled else "idle")
    last_dispatch_status = _normalized_text(config.get("last_dispatch_status")) or ("disabled" if not enabled else "idle")
    return {
        "enabled": enabled,
        "status": "enabled" if enabled else "disabled",
        "status_label": "开启中" if enabled else "已关闭",
        "description": "开启后自动监控自动化范围内用户的新私聊消息；夜间只入队不触发；关闭后停止自动触发但不影响聊天入库。",
        "last_capture_cursor": int(config.get("last_capture_cursor") or 0),
        "last_capture_at": _normalized_text(config.get("last_capture_at")),
        "last_capture_status": last_capture_status,
        "last_capture_status_label": _reply_monitor_status_label(last_capture_status),
        "last_capture_summary": dict(config.get("last_capture_summary_json") or {}),
        "last_dispatch_at": _normalized_text(config.get("last_dispatch_at")),
        "last_dispatch_status": last_dispatch_status,
        "last_dispatch_status_label": _reply_monitor_status_label(last_dispatch_status),
        "last_dispatch_summary": dict(config.get("last_dispatch_summary_json") or {}),
        "last_error": _normalized_text(config.get("last_error")),
        "quiet_hours_start": _normalized_text(config.get("quiet_hours_start")) or REPLY_MONITOR_DEFAULT_QUIET_HOURS_START,
        "quiet_hours_end": _normalized_text(config.get("quiet_hours_end")) or REPLY_MONITOR_DEFAULT_QUIET_HOURS_END,
        "dispatch_interval_seconds": int(config.get("dispatch_interval_seconds") or REPLY_MONITOR_DEFAULT_DISPATCH_INTERVAL_SECONDS),
        "queue_counts": queue_counts,
        "recent_items": recent_items,
    }


def _parse_clock_minutes(value: str, *, default_minutes: int) -> int:
    text = _normalized_text(value)
    if not text:
        return default_minutes
    try:
        parsed = datetime.strptime(text, "%H:%M")
    except ValueError:
        return default_minutes
    return parsed.hour * 60 + parsed.minute


def _is_reply_monitor_quiet_hours(config: dict[str, Any], *, now: datetime | None = None) -> bool:
    current = now or datetime.now()
    current_minutes = current.hour * 60 + current.minute
    start_minutes = _parse_clock_minutes(
        _normalized_text(config.get("quiet_hours_start")),
        default_minutes=23 * 60,
    )
    end_minutes = _parse_clock_minutes(
        _normalized_text(config.get("quiet_hours_end")),
        default_minutes=9 * 60,
    )
    if start_minutes == end_minutes:
        return False
    if start_minutes < end_minutes:
        return start_minutes <= current_minutes < end_minutes
    return current_minutes >= start_minutes or current_minutes < end_minutes


def _next_reply_monitor_daytime_start(config: dict[str, Any], *, now: datetime | None = None) -> datetime:
    current = now or datetime.now()
    end_minutes = _parse_clock_minutes(
        _normalized_text(config.get("quiet_hours_end")),
        default_minutes=9 * 60,
    )
    next_start = current.replace(hour=end_minutes // 60, minute=end_minutes % 60, second=0, microsecond=0)
    if _is_reply_monitor_quiet_hours(config, now=current):
        current_minutes = current.hour * 60 + current.minute
        if current_minutes >= _parse_clock_minutes(_normalized_text(config.get("quiet_hours_start")), default_minutes=23 * 60):
            next_start += timedelta(days=1)
    elif next_start <= current:
        next_start += timedelta(days=1)
    return next_start


def _reply_monitor_next_dispatch_dt(config: dict[str, Any], *, now_dt: datetime, seed_dt: datetime | None = None) -> datetime:
    interval_seconds = max(1, int(config.get("dispatch_interval_seconds") or REPLY_MONITOR_DEFAULT_DISPATCH_INTERVAL_SECONDS))
    latest_not_before_dt = _parse_timestamp(repo.get_latest_reply_monitor_not_before())
    last_dispatch_dt = _parse_timestamp(config.get("last_dispatch_at"))
    candidates = [now_dt]
    if seed_dt:
        candidates.append(seed_dt)
    if latest_not_before_dt:
        candidates.append(latest_not_before_dt)
    if last_dispatch_dt:
        candidates.append(last_dispatch_dt + timedelta(seconds=interval_seconds))
    next_dt = max(candidates)
    if _is_reply_monitor_quiet_hours(config, now=next_dt):
        next_dt = _next_reply_monitor_daytime_start(config, now=next_dt)
    return next_dt


def _build_reply_monitor_recent_messages(messages: list[dict[str, Any]], *, external_contact_id: str) -> list[dict[str, Any]]:
    normalized_external_contact_id = _normalized_text(external_contact_id)
    normalized_messages: list[dict[str, Any]] = []
    for item in list(messages or [])[-20:]:
        sender = _normalized_text(item.get("sender"))
        normalized_messages.append(
            {
                "role": "customer" if sender == normalized_external_contact_id else "staff",
                "content": _normalized_text(item.get("content")),
                "created_at": _normalized_text(item.get("send_time")),
            }
        )
    return normalized_messages


def save_reply_monitor_enabled(*, enabled: bool, operator_id: str = "") -> dict[str, Any]:
    current = _reply_monitor_config()
    next_enabled = _normalize_bool(enabled)
    payload = {
        "enabled": next_enabled,
        "last_error": "",
    }
    if next_enabled and not _normalize_bool(current.get("enabled")):
        payload["last_capture_cursor"] = repo.get_latest_archived_message_storage_id()
        payload["last_capture_at"] = _iso_now()
        payload["last_capture_status"] = "idle"
        payload["last_capture_summary_json"] = {
            "reset_reason": "enabled_from_current_cursor",
            "cursor": int(payload["last_capture_cursor"]),
        }
        payload["last_dispatch_status"] = "idle"
    if not next_enabled:
        payload["last_capture_status"] = "disabled"
        payload["last_dispatch_status"] = "disabled"
    config = _save_reply_monitor_config(payload)
    return _reply_monitor_status_payload() if config else _reply_monitor_status_payload()


def _reply_monitor_candidate_message(message: dict[str, Any]) -> bool:
    if _normalized_text(message.get("chat_type")) != "private":
        return False
    external_userid = _normalized_text(message.get("external_userid"))
    owner_userid = _normalized_text(message.get("owner_userid"))
    if not external_userid or not owner_userid:
        return False
    if _normalized_text(message.get("sender")) != external_userid:
        return False
    receiver = _normalized_text(message.get("receiver"))
    if receiver and receiver != owner_userid:
        return False
    if _normalized_text(message.get("msgtype")) in {"event", "revoke", "calendar", "vote"}:
        return False
    return True


def _safe_timestamp_min(*values: Any) -> str:
    candidates = [item for item in (_parse_timestamp(value) for value in values) if item is not None]
    if not candidates:
        return _normalized_text(values[0] if values else "")
    return min(candidates).strftime("%Y-%m-%d %H:%M:%S")


def _safe_timestamp_max(*values: Any) -> str:
    candidates = [item for item in (_parse_timestamp(value) for value in values) if item is not None]
    if not candidates:
        return _normalized_text(values[0] if values else "")
    return max(candidates).strftime("%Y-%m-%d %H:%M:%S")


def run_reply_monitor_capture(
    *,
    operator_id: str = "",
    operator_type: str = "system",
    limit: int = 500,
) -> dict[str, Any]:
    config = _reply_monitor_config()
    if not _normalize_bool(config.get("enabled")):
        return {
            "ok": False,
            "status": "disabled",
            "error": "reply monitor is disabled",
            "reply_monitor": _reply_monitor_status_payload(),
        }
    now_text = _iso_now()
    now_dt = _parse_timestamp(now_text) or datetime.now()
    after_cursor = int(config.get("last_capture_cursor") or 0)
    scanned_rows = repo.list_archived_messages_after_storage_cursor(after_id=after_cursor, limit=max(1, min(int(limit), 1000)))
    latest_cursor = max([after_cursor] + [int(item.get("id") or 0) for item in scanned_rows])
    candidate_rows = [dict(item) for item in scanned_rows if _reply_monitor_candidate_message(item)]
    active_members = repo.list_active_automation_members_by_external_contact_ids(
        list({ _normalized_text(item.get("external_userid")) for item in candidate_rows if _normalized_text(item.get("external_userid")) })
    )
    member_by_external = {
        _normalized_text(item.get("external_contact_id")): _serialize_member(item)
        for item in active_members
        if _normalized_text(item.get("external_contact_id"))
    }
    grouped_messages: dict[str, list[dict[str, Any]]] = {}
    message_owner_userids: dict[str, str] = {}
    for row in candidate_rows:
        external_userid = _normalized_text(row.get("external_userid"))
        member = member_by_external.get(external_userid)
        if not member:
            continue
        grouped_messages.setdefault(external_userid, []).append(dict(row))
        message_owner_userids[external_userid] = _normalized_text(row.get("owner_userid")) or _normalized_text(member.get("owner_staff_id"))

    created_count = 0
    merged_count = 0
    processed_users = 0
    seed_dt = _reply_monitor_next_dispatch_dt(config, now_dt=now_dt)
    quiet_now = _is_reply_monitor_quiet_hours(config, now=now_dt)
    for external_userid, message_rows in sorted(grouped_messages.items(), key=lambda item: int((item[1][0].get("id") or 0))):
        member = member_by_external[external_userid]
        owner_userid = message_owner_userids.get(external_userid) or _normalized_text(member.get("owner_staff_id"))
        message_ids = [int(item.get("id") or 0) for item in message_rows if int(item.get("id") or 0) > 0]
        if not message_ids:
            continue
        processed_users += 1
        existing = repo.get_active_reply_monitor_queue_item(external_userid)
        if existing:
            serialized_existing = _serialize_reply_monitor_queue_item(existing)
            merged_ids = sorted(set(list(serialized_existing.get("message_ids") or []) + message_ids))
            status = serialized_existing["status"]
            not_before = serialized_existing["not_before"]
            if status != REPLY_MONITOR_STATUS_PAUSED:
                if _is_reply_monitor_quiet_hours(config, now=now_dt):
                    status = REPLY_MONITOR_STATUS_DEFERRED
                    not_before = _safe_timestamp_max(not_before, _next_reply_monitor_daytime_start(config, now=now_dt).strftime("%Y-%m-%d %H:%M:%S"))
                else:
                    status = REPLY_MONITOR_STATUS_PENDING
                    not_before = not_before or seed_dt.strftime("%Y-%m-%d %H:%M:%S")
            repo.update_reply_monitor_queue_item(
                int(serialized_existing["id"]),
                {
                    "member_id": int(member.get("id") or 0) or None,
                    "external_userid": external_userid,
                    "owner_userid": owner_userid,
                    "status": status,
                    "message_ids_json": merged_ids,
                    "message_count": len(merged_ids),
                    "first_inbound_at": _safe_timestamp_min(serialized_existing.get("first_inbound_at"), *(item.get("send_time") for item in message_rows)),
                    "last_inbound_at": _safe_timestamp_max(serialized_existing.get("last_inbound_at"), *(item.get("send_time") for item in message_rows)),
                    "not_before": not_before,
                    "last_dispatch_at": serialized_existing.get("last_dispatch_at"),
                    "error_message": "",
                    "payload_snapshot_json": serialized_existing.get("payload_snapshot") or {},
                },
            )
            merged_count += 1
            continue

        next_not_before_dt = seed_dt
        if quiet_now:
            status = REPLY_MONITOR_STATUS_DEFERRED
            next_not_before_dt = _parse_timestamp(_next_reply_monitor_daytime_start(config, now=now_dt).strftime("%Y-%m-%d %H:%M:%S")) or next_not_before_dt
            if seed_dt > next_not_before_dt:
                next_not_before_dt = seed_dt
        else:
            status = REPLY_MONITOR_STATUS_PENDING
        repo.insert_reply_monitor_queue_item(
            {
                "member_id": int(member.get("id") or 0) or None,
                "external_userid": external_userid,
                "owner_userid": owner_userid,
                "status": status,
                "message_ids_json": message_ids,
                "message_count": len(message_ids),
                "first_inbound_at": _safe_timestamp_min(*(item.get("send_time") for item in message_rows)),
                "last_inbound_at": _safe_timestamp_max(*(item.get("send_time") for item in message_rows)),
                "not_before": next_not_before_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "last_dispatch_at": "",
                "error_message": "",
                "payload_snapshot_json": {},
            }
        )
        created_count += 1
        seed_dt = next_not_before_dt + timedelta(seconds=max(1, int(config.get("dispatch_interval_seconds") or REPLY_MONITOR_DEFAULT_DISPATCH_INTERVAL_SECONDS)))

    summary = {
        "cursor_from": after_cursor,
        "cursor_to": latest_cursor,
        "scanned_new_messages": len(scanned_rows),
        "candidate_messages": len(candidate_rows),
        "hit_users": processed_users,
        "created_queue_items": created_count,
        "merged_queue_items": merged_count,
    }
    saved_config = _save_reply_monitor_config(
        {
            "last_capture_cursor": latest_cursor,
            "last_capture_at": now_text,
            "last_capture_status": "success",
            "last_capture_summary_json": summary,
            "last_error": "",
        }
    )
    return {
        "ok": True,
        "status": "success",
        "summary": summary,
        "reply_monitor": _reply_monitor_status_payload() if saved_config else _reply_monitor_status_payload(),
    }


def run_due_reply_monitor(
    *,
    operator_id: str = "",
    operator_type: str = "system",
    limit: int = 20,
) -> dict[str, Any]:
    config = _reply_monitor_config()
    if not _normalize_bool(config.get("enabled")):
        return {
            "ok": False,
            "status": "disabled",
            "error": "reply monitor is disabled",
            "reply_monitor": _reply_monitor_status_payload(),
        }
    now_text = _iso_now()
    now_dt = _parse_timestamp(now_text) or datetime.now()
    interval_seconds = max(1, int(config.get("dispatch_interval_seconds") or REPLY_MONITOR_DEFAULT_DISPATCH_INTERVAL_SECONDS))
    if _is_reply_monitor_quiet_hours(config, now=now_dt):
        due_items = [_serialize_reply_monitor_queue_item(item) for item in repo.list_due_reply_monitor_queue_items(now_text=now_text, limit=max(1, min(int(limit), 100)))]
        next_start_text = _next_reply_monitor_daytime_start(config, now=now_dt).strftime("%Y-%m-%d %H:%M:%S")
        deferred_count = 0
        seed_dt = _parse_timestamp(next_start_text) or now_dt
        for item in due_items:
            repo.update_reply_monitor_queue_item(
                int(item["id"]),
                {
                    "member_id": item.get("member_id") or None,
                    "external_userid": item.get("external_userid"),
                    "owner_userid": item.get("owner_userid"),
                    "status": REPLY_MONITOR_STATUS_DEFERRED,
                    "message_ids_json": item.get("message_ids") or [],
                    "message_count": int(item.get("message_count") or 0),
                    "first_inbound_at": item.get("first_inbound_at"),
                    "last_inbound_at": item.get("last_inbound_at"),
                    "not_before": seed_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "last_dispatch_at": item.get("last_dispatch_at"),
                    "error_message": item.get("error_message"),
                    "payload_snapshot_json": item.get("payload_snapshot") or {},
                },
            )
            deferred_count += 1
            seed_dt = seed_dt + timedelta(seconds=interval_seconds)
        summary = {
            "processed_count": 0,
            "success_count": 0,
            "failed_count": 0,
            "deferred_count": deferred_count,
            "reason": "quiet_hours",
        }
        _save_reply_monitor_config(
            {
                "last_dispatch_status": "idle",
                "last_dispatch_summary_json": summary,
                "last_error": "",
            }
        )
        return {
            "ok": True,
            "status": "quiet_hours",
            "summary": summary,
            "reply_monitor": _reply_monitor_status_payload(),
        }

    last_dispatch_dt = _parse_timestamp(config.get("last_dispatch_at"))
    if last_dispatch_dt and now_dt < (last_dispatch_dt + timedelta(seconds=interval_seconds)):
        wait_seconds = max(1, int(((last_dispatch_dt + timedelta(seconds=interval_seconds)) - now_dt).total_seconds()))
        summary = {
            "processed_count": 0,
            "success_count": 0,
            "failed_count": 0,
            "pending_count": int(repo.get_reply_monitor_queue_counts().get("pending") or 0),
            "deferred_count": int(repo.get_reply_monitor_queue_counts().get("deferred_quiet_hours") or 0),
            "wait_seconds": wait_seconds,
        }
        _save_reply_monitor_config(
            {
                "last_dispatch_status": "idle",
                "last_dispatch_summary_json": summary,
                "last_error": "",
            }
        )
        return {
            "ok": True,
            "status": "throttled",
            "summary": summary,
            "reply_monitor": _reply_monitor_status_payload(),
        }

    due_items = [_serialize_reply_monitor_queue_item(item) for item in repo.list_due_reply_monitor_queue_items(now_text=now_text, limit=max(1, min(int(limit), 100)))]
    if not due_items:
        summary = {
            "processed_count": 0,
            "success_count": 0,
            "failed_count": 0,
            "pending_count": int(repo.get_reply_monitor_queue_counts().get("pending") or 0),
            "deferred_count": int(repo.get_reply_monitor_queue_counts().get("deferred_quiet_hours") or 0),
        }
        _save_reply_monitor_config(
            {
                "last_dispatch_status": "idle",
                "last_dispatch_summary_json": summary,
                "last_error": "",
            }
        )
        return {
            "ok": True,
            "status": "idle",
            "summary": summary,
            "reply_monitor": _reply_monitor_status_payload(),
        }

    queue_item = due_items[0]
    from .laohuang_chat_service import dispatch_reply_monitor_queue_item, laohuang_chat_enabled

    if laohuang_chat_enabled():
        return dispatch_reply_monitor_queue_item(
            queue_item,
            operator_id=operator_id,
            operator_type=operator_type,
        )
    return _dispatch_reply_monitor_queue_item(
        queue_item,
        operator_id=operator_id,
        operator_type=operator_type,
        trigger_action="reply_monitor_dispatch",
        trigger_source="reply_monitor_shadow",
    )


def _dispatch_reply_monitor_queue_item(
    queue_item: dict[str, Any],
    *,
    operator_id: str = "",
    operator_type: str = "system",
    trigger_action: str = "reply_monitor_dispatch",
    trigger_source: str = "reply_monitor_shadow",
) -> dict[str, Any]:
    now_text = _iso_now()
    member = repo.get_member_by_id(int(queue_item.get("member_id") or 0)) if int(queue_item.get("member_id") or 0) > 0 else repo.get_member_by_external_contact_id(queue_item.get("external_userid") or "")
    if not member:
        repo.update_reply_monitor_queue_item(
            int(queue_item["id"]),
            {
                "member_id": queue_item.get("member_id") or None,
                "external_userid": queue_item.get("external_userid"),
                "owner_userid": queue_item.get("owner_userid"),
                "status": REPLY_MONITOR_STATUS_FAILED,
                "message_ids_json": queue_item.get("message_ids") or [],
                "message_count": int(queue_item.get("message_count") or 0),
                "first_inbound_at": queue_item.get("first_inbound_at"),
                "last_inbound_at": queue_item.get("last_inbound_at"),
                "not_before": queue_item.get("not_before"),
                "last_dispatch_at": "",
                "error_message": "automation_member_not_found",
                "payload_snapshot_json": queue_item.get("payload_snapshot") or {},
            }
        )
        _save_reply_monitor_config(
            {
                "last_dispatch_status": "failed",
                "last_dispatch_summary_json": {
                    "processed_count": 1,
                    "success_count": 0,
                    "failed_count": 1,
                    "queue_id": int(queue_item["id"]),
                },
                "last_error": "automation_member_not_found",
            }
        )
        return {
            "ok": False,
            "status": "failed",
            "error": "automation_member_not_found",
            "reply_monitor": _reply_monitor_status_payload(),
        }

    messages = repo.list_archived_messages_by_ids(queue_item.get("message_ids") or [])
    recent_messages = _build_reply_monitor_recent_messages(
        messages,
        external_contact_id=_normalized_text(queue_item.get("external_userid")),
    )
    router_ingress: dict[str, Any] = {}
    try:
        from .orchestration_service import run_agent_router_shadow_decision

        router_ingress = run_agent_router_shadow_decision(
            external_contact_id=_normalized_text(queue_item.get("external_userid")),
            owner_userid=_normalized_text(queue_item.get("owner_userid")),
            batch_id=f"reply_monitor_queue:{int(queue_item['id'])}",
            source=_normalized_text(trigger_source) or "reply_monitor_shadow",
        )
    except Exception:  # pragma: no cover - async ingress must not crash the job runner
        current_app.logger.exception("automation router ingress failed")
        router_ingress = {"ok": False, "status": "shadow_error", "shadow_called": False}
    delivery_reason = _normalized_text(router_ingress.get("status") or router_ingress.get("error"))
    delivery_ok = bool(router_ingress.get("ok"))
    next_status = REPLY_MONITOR_STATUS_DISPATCHED if delivery_ok else REPLY_MONITOR_STATUS_FAILED
    repo.update_reply_monitor_queue_item(
        int(queue_item["id"]),
        {
            "member_id": int(member.get("id") or 0) or None,
            "external_userid": queue_item.get("external_userid"),
            "owner_userid": queue_item.get("owner_userid"),
            "status": next_status,
            "message_ids_json": queue_item.get("message_ids") or [],
            "message_count": int(queue_item.get("message_count") or 0),
            "first_inbound_at": queue_item.get("first_inbound_at"),
            "last_inbound_at": queue_item.get("last_inbound_at"),
            "not_before": queue_item.get("not_before"),
            "last_dispatch_at": now_text,
            "error_message": "" if delivery_ok else delivery_reason,
            "payload_snapshot_json": {
                "request_id": _normalized_text(router_ingress.get("request_id")),
                "external_contact_id": _normalized_text(queue_item.get("external_userid")),
                "recent_messages": recent_messages,
            },
        }
    )
    _write_event(
        member_id=int(member["id"]),
        action=_normalized_text(trigger_action) or "reply_monitor_dispatch",
        operator_type=_normalized_text(operator_type) or "system",
        operator_id=_normalized_text(operator_id) or "reply_monitor_runner",
        before_snapshot=_member_snapshot(_serialize_member(member)),
        after_snapshot=_member_snapshot(_serialize_member(member)),
        remark=(
            f"queue_id={int(queue_item['id'])}; "
            f"trigger_type={REPLY_MONITOR_TRIGGER_TYPE}; "
            f"router_request_id={_normalized_text(router_ingress.get('request_id'))}; "
            f"status={'acked' if delivery_ok else 'failed'}"
        ),
    )
    queue_counts = repo.get_reply_monitor_queue_counts()
    summary = {
        "processed_count": 1,
        "success_count": 1 if delivery_ok else 0,
        "failed_count": 0 if delivery_ok else 1,
        "pending_count": int(queue_counts.get("pending") or 0),
        "deferred_count": int(queue_counts.get("deferred_quiet_hours") or 0),
        "queue_id": int(queue_item["id"]),
        "request_id": _normalized_text(router_ingress.get("request_id")),
    }
    _save_reply_monitor_config(
        {
            "last_dispatch_at": now_text,
            "last_dispatch_status": "success" if delivery_ok else "failed",
            "last_dispatch_summary_json": summary,
            "last_error": "" if delivery_ok else delivery_reason,
        }
    )
    return {
        "ok": delivery_ok,
        "status": "success" if delivery_ok else "failed",
        "queue_item": _serialize_reply_monitor_queue_item(repo.get_reply_monitor_queue_item(int(queue_item["id"])) or {}),
        "summary": summary,
        "reply_monitor": _reply_monitor_status_payload(),
        "error": "" if delivery_ok else delivery_reason,
        "router_ingress": router_ingress,
        "shadow_router": router_ingress,
    }


def run_router_test_dispatch(
    *,
    external_contact_id: str = "",
    phone: str = "",
    operator_id: str = "",
    mode: str = "",
    force_capture: bool = False,
    force_run_due: bool = False,
) -> dict[str, Any]:
    normalized_mode = _normalized_text(mode).lower() or "auto"
    normalized_phone = _normalized_text(phone)
    member = _resolve_existing_member(external_contact_id=external_contact_id, phone=normalized_phone)
    resolved_external_contact_id = (
        _normalized_text(external_contact_id)
        or _normalized_text((member or {}).get("external_contact_id"))
        or repo.find_latest_external_contact_id_by_phone(normalized_phone)
    )
    if not resolved_external_contact_id:
        return {
            "ok": False,
            "status": "member_not_found",
            "error": "member_not_found",
            "message": "未找到可触发的 external_contact_id，请提供有效 external_contact_id 或 phone。",
            "capture_result": {},
            "run_due_result": {},
            "request_id": "",
            "queue_id": 0,
            "member_id": 0,
        }
    if not member:
        member = repo.get_member_by_external_contact_id(resolved_external_contact_id)
    if not member:
        return {
            "ok": False,
            "status": "member_not_found",
            "error": "member_not_found",
            "message": f"成员 {resolved_external_contact_id} 不在自动化成员池中，无法触发 router 测试派发。",
            "capture_result": {},
            "run_due_result": {},
            "request_id": "",
            "queue_id": 0,
            "member_id": 0,
        }

    capture_requested = bool(force_capture) or normalized_mode in {"auto", "capture", "capture_and_run_due", "capture-run-due"}
    dispatch_requested = bool(force_run_due) or normalized_mode in {"auto", "queue", "run_due", "capture_and_run_due", "capture-run-due"}
    direct_requested = normalized_mode in {"direct", "router", "shadow"} or not dispatch_requested
    capture_result: dict[str, Any] = {
        "ok": True,
        "status": "skipped",
        "summary": {"reason": "capture_not_requested"},
    }
    if capture_requested:
        capture_result = run_reply_monitor_capture(
            operator_id=_normalized_text(operator_id) or "router_test_dispatch",
            operator_type="system",
            limit=500,
        )

    queue_row = repo.get_active_reply_monitor_queue_item(resolved_external_contact_id)
    queue_item = _serialize_reply_monitor_queue_item(queue_row) if queue_row else {}
    run_due_result: dict[str, Any] = {
        "ok": False,
        "status": "queue_not_found",
        "summary": {"reason": "queue_not_found"},
        "reply_monitor": _reply_monitor_status_payload(),
    }
    if queue_item and dispatch_requested:
        run_due_result = _dispatch_reply_monitor_queue_item(
            queue_item,
            operator_id=_normalized_text(operator_id) or "router_test_dispatch",
            operator_type="system",
            trigger_action="reply_monitor_test_dispatch",
            trigger_source="router_test_dispatch",
        )

    router_ingress = dict(run_due_result.get("router_ingress") or {})
    queue_id = int((run_due_result.get("queue_item") or {}).get("id") or queue_item.get("id") or 0)
    request_id = _normalized_text(router_ingress.get("request_id"))
    message = "已通过 reply-monitor 队列触发新的 router ingress。"

    if not request_id and (direct_requested or normalized_mode == "auto"):
        from .orchestration_service import run_agent_router_shadow_decision

        direct_ingress = run_agent_router_shadow_decision(
            external_contact_id=resolved_external_contact_id,
            owner_userid=_normalized_text((member or {}).get("owner_staff_id")),
            batch_id=f"router_test_dispatch:{resolved_external_contact_id}",
            source="router_test_dispatch",
        )
        router_ingress = dict(direct_ingress or {})
        request_id = _normalized_text(router_ingress.get("request_id"))
        run_due_result = {
            "ok": bool(router_ingress.get("ok")),
            "status": "success" if bool(router_ingress.get("ok")) else (_normalized_text(router_ingress.get("status")) or "failed"),
            "summary": {
                "processed_count": 1 if bool(router_ingress.get("ok")) else 0,
                "success_count": 1 if bool(router_ingress.get("ok")) else 0,
                "failed_count": 0 if bool(router_ingress.get("ok")) else 1,
                "request_id": request_id,
            },
            "reply_monitor": _reply_monitor_status_payload(),
            "error": "" if bool(router_ingress.get("ok")) else (_normalized_text(router_ingress.get("status")) or _normalized_text(router_ingress.get("error"))),
            "router_ingress": router_ingress,
            "shadow_router": router_ingress,
        }
        message = "未命中可直接派发的 reply-monitor 队列，本次已改为直接触发 router ingress。"

    current_app.logger.info(
        "router_test_dispatch external_contact_id=%s member_id=%s request_id=%s queue_id=%s mode=%s capture_requested=%s dispatch_requested=%s direct_requested=%s",
        resolved_external_contact_id,
        int(member.get("id") or 0),
        request_id,
        queue_id,
        normalized_mode,
        capture_requested,
        dispatch_requested,
        direct_requested,
    )
    return {
        "ok": bool(request_id),
        "status": "accepted" if request_id else (_normalized_text(run_due_result.get("status")) or "failed"),
        "capture_result": capture_result,
        "run_due_result": run_due_result,
        "request_id": request_id,
        "queue_id": queue_id,
        "member_id": int(member.get("id") or 0),
        "external_contact_id": resolved_external_contact_id,
        "message": message if request_id else "未触发新的 router ingress，请检查 capture / queue / router 配置。",
    }
