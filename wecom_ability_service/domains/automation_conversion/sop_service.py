from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from ...db import get_db
from ..marketing_automation.service import get_signup_conversion_config
from . import repo
from .service import (
    DEFAULT_OWNER_STAFF_ID,
    POOL_CONVERTED,
    POOL_OPERATING,
    POOL_PENDING_QUESTIONNAIRE,
    SOP_BATCH_STATUS_LABELS,
    SOP_RUN_SKIPPED_REASON_LABELS,
    SOP_V1_ALLOWED_POOLS,
    SOP_V1_DEFAULT_SEND_TIME,
    SOP_V1_DEFAULT_TIMEZONE,
    _normalize_bool,
    _normalized_text,
    _parse_timestamp,
    _pool_label,
    _serialize_member,
)
from .private_message_dispatch import _dispatch_private_message_batch



def _iso_now() -> str:
    """Lazy proxy to service._iso_now so monkeypatch on service._iso_now propagates here."""
    from . import service as _svc
    return _svc._iso_now()

def _validate_sop_pool_key(pool_key: str) -> str:
    normalized_pool_key = {
        "new_user": POOL_PENDING_QUESTIONNAIRE,
        "inactive_normal": POOL_OPERATING,
        "inactive_focus": POOL_OPERATING,
        "active_normal": POOL_OPERATING,
        "active_focus": POOL_OPERATING,
        "silent": POOL_OPERATING,
        "won": POOL_CONVERTED,
    }.get(_normalized_text(pool_key), _normalized_text(pool_key))
    if normalized_pool_key not in SOP_V1_ALLOWED_POOLS:
        raise ValueError("sop pool_key must be one of pending_questionnaire, operating, converted")
    return normalized_pool_key


def _normalize_sop_send_time(value: Any) -> str:
    text = _normalized_text(value) or SOP_V1_DEFAULT_SEND_TIME
    try:
        normalized = datetime.strptime(text, "%H:%M")
    except ValueError as exc:
        raise ValueError("sop send_time must use HH:MM") from exc
    return normalized.strftime("%H:%M")


def _default_sop_send_time() -> str:
    try:
        day_start_hour = int(get_signup_conversion_config().get("day_start_hour") or 9)
    except (TypeError, ValueError):
        day_start_hour = 9
    return f"{max(0, min(day_start_hour, 23)):02d}:00"


def _default_sop_pool_config(pool_key: str) -> dict[str, Any]:
    normalized_pool_key = _validate_sop_pool_key(pool_key)
    return {
        "pool_key": normalized_pool_key,
        "enabled": True,
        "max_day_count": 1,
        "send_time": _default_sop_send_time(),
        "timezone": SOP_V1_DEFAULT_TIMEZONE,
        "effective_start_at": _iso_now(),
    }


def _empty_sop_template(pool_key: str, day_index: int) -> dict[str, Any]:
    return {
        "pool_key": _validate_sop_pool_key(pool_key),
        "day_index": int(day_index),
        "content": "",
        "images_json": [],
        "miniprograms_json": [],
        "enabled": True,
    }


def _serialize_sop_pool_config(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    return {
        "id": int(row.get("id") or 0),
        "pool_key": _normalized_text(row.get("pool_key")),
        "pool_label": _pool_label(row.get("pool_key")),
        "enabled": _normalize_bool(row.get("enabled")),
        "max_day_count": int(row.get("max_day_count") or 0),
        "send_time": _normalize_sop_send_time(row.get("send_time")),
        "effective_start_at": _normalized_text(row.get("effective_start_at")),
        "created_at": _normalized_text(row.get("created_at")),
        "updated_at": _normalized_text(row.get("updated_at")),
    }


def _serialize_sop_template(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    deserialized = repo.deserialize_sop_template_row(row)
    return {
        "id": int(deserialized.get("id") or 0),
        "pool_key": _normalized_text(deserialized.get("pool_key")),
        "pool_label": _pool_label(deserialized.get("pool_key")),
        "day_index": int(deserialized.get("day_index") or 0),
        "content": _normalized_text(deserialized.get("content")),
        "images_json": list(deserialized.get("images_json") or []),
        "miniprograms_json": list(deserialized.get("miniprograms_json") or []),
        "enabled": _normalize_bool(deserialized.get("enabled")),
        "created_at": _normalized_text(deserialized.get("created_at")),
        "updated_at": _normalized_text(deserialized.get("updated_at")),
    }


def _template_image_preview_url(item: dict[str, Any]) -> str:
    data_url = _normalized_text(item.get("data_url"))
    if data_url:
        return data_url
    data_base64 = _normalized_text(item.get("data_base64"))
    if data_base64:
        content_type = _normalized_text(item.get("content_type")) or "image/png"
        return f"data:{content_type};base64,{data_base64}"
    return ""


def _serialize_sop_template_for_ui(template: dict[str, Any]) -> dict[str, Any]:
    images: list[dict[str, Any]] = []
    for index, raw_item in enumerate(list(template.get("images_json") or []), start=1):
        if isinstance(raw_item, str):
            item = {"media_id": _normalized_text(raw_item)}
        elif isinstance(raw_item, dict):
            item = dict(raw_item)
        else:
            continue
        images.append(
            {
                "id": f"{template.get('pool_key')}-{template.get('day_index')}-{index}",
                "file_name": _normalized_text(item.get("file_name")) or f"day{template.get('day_index')}-image-{index}.png",
                "content_type": _normalized_text(item.get("content_type")) or "image/png",
                "data_url": _normalized_text(item.get("data_url")),
                "data_base64": _normalized_text(item.get("data_base64")),
                "media_id": _normalized_text(item.get("media_id") or item.get("image_media_id")),
                "preview_url": _template_image_preview_url(item),
                "is_uploaded": bool(_template_image_preview_url(item)),
            }
        )
    return {
        **template,
        "images_json": images,
        "image_count": len(images),
    }


def _serialize_sop_progress(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    deserialized = repo.deserialize_sop_progress_row(row)
    return {
        "id": int(deserialized.get("id") or 0),
        "member_id": int(deserialized.get("member_id") or 0),
        "pool_key": _normalized_text(deserialized.get("pool_key")),
        "pool_label": _pool_label(deserialized.get("pool_key")),
        "first_entered_at": _normalized_text(deserialized.get("first_entered_at")),
        "last_entered_at": _normalized_text(deserialized.get("last_entered_at")),
        "sop_anchor_date": _normalized_text(deserialized.get("sop_anchor_date")),
        "first_effective_in_pool_at": _normalized_text(deserialized.get("first_effective_in_pool_at")),
        "last_in_pool_at": _normalized_text(deserialized.get("last_in_pool_at")),
        "last_sent_day": int(deserialized.get("last_sent_day") or 0),
        "last_sent_at": _normalized_text(deserialized.get("last_sent_at")),
        "completed_at": _normalized_text(deserialized.get("completed_at")),
        "created_at": _normalized_text(deserialized.get("created_at")),
        "updated_at": _normalized_text(deserialized.get("updated_at")),
    }


def _serialize_sop_batch(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    deserialized = repo.deserialize_sop_batch_row(row)
    return {
        "id": int(deserialized.get("id") or 0),
        "pool_key": _normalized_text(deserialized.get("pool_key")),
        "pool_label": _pool_label(deserialized.get("pool_key")),
        "day_index": int(deserialized.get("day_index") or 0),
        "template_id": int(deserialized.get("template_id") or 0) if deserialized.get("template_id") not in (None, "") else None,
        "scheduled_for": _normalized_text(deserialized.get("scheduled_for")),
        "status": _normalized_text(deserialized.get("status")),
        "total_count": int(deserialized.get("total_count") or 0),
        "success_count": int(deserialized.get("success_count") or 0),
        "skipped_count": int(deserialized.get("skipped_count") or 0),
        "failed_count": int(deserialized.get("failed_count") or 0),
        "summary_json": dict(deserialized.get("summary_json") or {}),
        "created_at": _normalized_text(deserialized.get("created_at")),
        "updated_at": _normalized_text(deserialized.get("updated_at")),
    }


def _serialize_sop_batch_item(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    deserialized = repo.deserialize_sop_batch_item_row(row)
    return {
        "id": int(deserialized.get("id") or 0),
        "batch_id": int(deserialized.get("batch_id") or 0),
        "member_id": int(deserialized.get("member_id") or 0) if deserialized.get("member_id") not in (None, "") else None,
        "pool_key": _normalized_text(deserialized.get("pool_key")),
        "day_index": int(deserialized.get("day_index") or 0),
        "day_index_snapshot": int(deserialized.get("day_index_snapshot") or 0),
        "external_userid": _normalized_text(deserialized.get("external_userid")),
        "status": _normalized_text(deserialized.get("status")),
        "error_message": _normalized_text(deserialized.get("error_message")),
        "content_snapshot": _normalized_text(deserialized.get("content_snapshot")),
        "images_snapshot": list(deserialized.get("images_snapshot") or []),
        "sent_record_id": int(deserialized.get("sent_record_id") or 0) if deserialized.get("sent_record_id") not in (None, "") else None,
        "created_at": _normalized_text(deserialized.get("created_at")),
        "updated_at": _normalized_text(deserialized.get("updated_at")),
    }


def _current_sop_template_day_count(pool_key: str) -> int:
    templates = [_serialize_sop_template(row) for row in repo.list_sop_templates(pool_key=pool_key)]
    return max([int(item.get("day_index") or 0) for item in templates] or [0])


def _ensure_sop_template_day_exists(pool_key: str, day_index: int) -> dict[str, Any]:
    normalized_pool_key = _validate_sop_pool_key(pool_key)
    normalized_day_index = max(1, int(day_index or 1))
    template = repo.get_sop_template(pool_key=normalized_pool_key, day_index=normalized_day_index)
    if template:
        return _serialize_sop_template(template)
    return _serialize_sop_template(repo.save_sop_template(_empty_sop_template(normalized_pool_key, normalized_day_index)))


def _latest_sop_execution_summary(pool_key: str) -> dict[str, Any]:
    latest_batch = next(iter([_serialize_sop_batch(row) for row in repo.list_sop_batches(pool_key=pool_key, limit=1)]), {})
    if not latest_batch:
        return {
            "has_record": False,
            "label": "暂无执行记录",
            "scheduled_for": "",
            "success_count": 0,
            "skipped_count": 0,
            "failed_count": 0,
        }
    return {
        "has_record": True,
        "label": latest_batch.get("scheduled_for") or latest_batch.get("created_at") or "最近执行",
        "scheduled_for": _normalized_text(latest_batch.get("scheduled_for")),
        "status": _normalized_text(latest_batch.get("status")),
        "success_count": int(latest_batch.get("success_count") or 0),
        "skipped_count": int(latest_batch.get("skipped_count") or 0),
        "failed_count": int(latest_batch.get("failed_count") or 0),
    }


def ensure_sop_v1_defaults() -> dict[str, Any]:
    configs: list[dict[str, Any]] = []
    templates_by_pool: dict[str, list[dict[str, Any]]] = {}
    for pool_key in SOP_V1_ALLOWED_POOLS:
        _ensure_sop_template_day_exists(pool_key, 1)
        existing = _serialize_sop_pool_config(repo.get_sop_pool_config(pool_key))
        template_count = max(_current_sop_template_day_count(pool_key), 1)
        saved = repo.save_sop_pool_config(
            {
                "pool_key": pool_key,
                "enabled": _normalize_bool(existing.get("enabled")) if existing else True,
                "max_day_count": template_count,
                "send_time": _normalize_sop_send_time(existing.get("send_time") if existing else _default_sop_send_time()),
                "timezone": SOP_V1_DEFAULT_TIMEZONE,
                "effective_start_at": _normalized_text(existing.get("effective_start_at")) or _iso_now(),
            }
        )
        configs.append(_serialize_sop_pool_config(saved))
        templates_by_pool[pool_key] = [_serialize_sop_template(row) for row in repo.list_sop_templates(pool_key=pool_key)]
    get_db().commit()
    return {"configs": configs, "templates": templates_by_pool}


def _sop_batch_status_label(value: Any) -> str:
    normalized = _normalized_text(value)
    return SOP_BATCH_STATUS_LABELS.get(normalized, normalized or "未开始")


def get_sop_v1_config_payload() -> dict[str, Any]:
    defaults = ensure_sop_v1_defaults()
    return {
        "configs": [dict(item) for item in list(defaults.get("configs") or [])],
    }

def get_sop_v1_templates_payload(pool_key: str, *, selected_day_index: int = 0) -> dict[str, Any]:
    normalized_pool_key = _validate_sop_pool_key(pool_key)
    ensure_sop_v1_defaults()
    config = _serialize_sop_pool_config(repo.get_sop_pool_config(normalized_pool_key))
    templates = [_serialize_sop_template(row) for row in repo.list_sop_templates(pool_key=normalized_pool_key)]
    if not templates:
        _ensure_sop_template_day_exists(normalized_pool_key, 1)
        templates = [_serialize_sop_template(row) for row in repo.list_sop_templates(pool_key=normalized_pool_key)]
    template_count = max([int(item.get("day_index") or 0) for item in templates] or [1])
    selected_day = int(selected_day_index or 0)
    if selected_day < 1 or selected_day > template_count:
        selected_day = 1
    selected_template = next((item for item in templates if int(item.get("day_index") or 0) == selected_day), templates[0])
    day_tabs = []
    for template in templates:
        day_index = int(template.get("day_index") or 0)
        day_tabs.append(
            {
                "day_index": day_index,
                "label": f"day{day_index}",
                "is_selected": day_index == selected_day,
                "has_content": bool(_normalized_text(template.get("content")) or list(template.get("images_json") or [])),
                "enabled": _normalize_bool(template.get("enabled")),
            }
        )
    get_db().commit()
    return {
        "pool_key": normalized_pool_key,
        "pool_label": _pool_label(normalized_pool_key),
        "config": config,
        "template_count": template_count,
        "selected_day_index": selected_day,
        "day_tabs": day_tabs,
        "selected_template": _serialize_sop_template_for_ui(selected_template),
        "recent_execution": _latest_sop_execution_summary(normalized_pool_key),
    }


def get_sop_v1_batches_payload(*, limit: int = 20) -> dict[str, Any]:
    batches = [_serialize_sop_batch(row) for row in repo.list_sop_batches(limit=max(1, int(limit)))]
    return {
        "batches": [
            {
                **batch,
                "status_label": _sop_batch_status_label(batch.get("status")),
            }
            for batch in batches
        ]
    }



def get_sop_v1_management_payload(*, selected_pool_key: str = "", selected_day_index: int = 0) -> dict[str, Any]:
    ensure_sop_v1_defaults()
    normalized_pool_key = _validate_sop_pool_key(selected_pool_key) if _normalized_text(selected_pool_key) else SOP_V1_ALLOWED_POOLS[0]
    pool_cards: list[dict[str, Any]] = []
    for pool_key in SOP_V1_ALLOWED_POOLS:
        pool_payload = get_sop_v1_templates_payload(pool_key, selected_day_index=selected_day_index if pool_key == normalized_pool_key else 0)
        config = dict(pool_payload.get("config") or {})
        recent_execution = dict(pool_payload.get("recent_execution") or {})
        pool_cards.append(
            {
                "pool_key": pool_key,
                "pool_label": _pool_label(pool_key),
                "is_selected": pool_key == normalized_pool_key,
                "enabled": _normalize_bool(config.get("enabled")),
                "send_time": _normalize_sop_send_time(config.get("send_time")),
                "template_count": int(pool_payload.get("template_count") or 0),
                "recent_execution": recent_execution,
            }
        )
    current_pool = get_sop_v1_templates_payload(normalized_pool_key, selected_day_index=selected_day_index)
    return {
        "subtitle": "只覆盖未填问卷人群、运营中人群、已转化人群",
        "selected_pool_key": normalized_pool_key,
        "pool_cards": pool_cards,
        "current_pool": current_pool,
    }


def save_sop_v1_pool_config(
    *,
    pool_key: str,
    enabled: bool,
    send_time: str = SOP_V1_DEFAULT_SEND_TIME,
    timezone: str = SOP_V1_DEFAULT_TIMEZONE,
    effective_start_at: str = "",
) -> dict[str, Any]:
    normalized_pool_key = _validate_sop_pool_key(pool_key)
    ensure_sop_v1_defaults()
    existing = _serialize_sop_pool_config(repo.get_sop_pool_config(normalized_pool_key))
    saved = repo.save_sop_pool_config(
        {
            "pool_key": normalized_pool_key,
            "enabled": _normalize_bool(enabled),
            "max_day_count": max(_current_sop_template_day_count(normalized_pool_key), 1),
            "send_time": _normalize_sop_send_time(send_time or existing.get("send_time")),
            "timezone": _normalized_text(timezone) or SOP_V1_DEFAULT_TIMEZONE,
            "effective_start_at": _normalized_text(effective_start_at) or _normalized_text(existing.get("effective_start_at")) or _iso_now(),
        }
    )
    get_db().commit()
    return _serialize_sop_pool_config(saved)


def save_sop_v1_template(
    *,
    pool_key: str,
    day_index: int,
    content: str = "",
    images_json: list[dict[str, Any]] | None = None,
    miniprograms_json: list[dict[str, Any]] | None = None,
    enabled: bool = True,
) -> dict[str, Any]:
    normalized_pool_key = _validate_sop_pool_key(pool_key)
    normalized_day_index = max(1, int(day_index or 1))
    ensure_sop_v1_defaults()
    normalized_miniprograms: list[dict[str, Any]] = []
    for item in (miniprograms_json or []):
        if isinstance(item, int):
            normalized_miniprograms.append({"library_id": int(item)})
            continue
        if not isinstance(item, dict):
            continue
        library_id = item.get("library_id")
        if not library_id:
            continue
        try:
            normalized_miniprograms.append({"library_id": int(library_id)})
        except (TypeError, ValueError):
            continue
    saved = repo.save_sop_template(
        {
            "pool_key": normalized_pool_key,
            "day_index": normalized_day_index,
            "content": _normalized_text(content),
            "images_json": list(images_json or []),
            "miniprograms_json": normalized_miniprograms,
            "enabled": _normalize_bool(enabled),
        }
    )
    repo.save_sop_pool_config(
        {
            **(_serialize_sop_pool_config(repo.get_sop_pool_config(normalized_pool_key)) or _default_sop_pool_config(normalized_pool_key)),
            "pool_key": normalized_pool_key,
            "enabled": _normalize_bool((_serialize_sop_pool_config(repo.get_sop_pool_config(normalized_pool_key)) or {}).get("enabled", True)),
            "max_day_count": max(_current_sop_template_day_count(normalized_pool_key), normalized_day_index, 1),
            "send_time": _normalize_sop_send_time((_serialize_sop_pool_config(repo.get_sop_pool_config(normalized_pool_key)) or {}).get("send_time")),
            "timezone": SOP_V1_DEFAULT_TIMEZONE,
            "effective_start_at": _normalized_text((_serialize_sop_pool_config(repo.get_sop_pool_config(normalized_pool_key)) or {}).get("effective_start_at")) or _iso_now(),
        }
    )
    get_db().commit()
    return _serialize_sop_template_for_ui(_serialize_sop_template(saved))


def delete_sop_v1_template_day(*, pool_key: str, day_index: int) -> dict[str, Any]:
    normalized_pool_key = _validate_sop_pool_key(pool_key)
    normalized_day_index = max(1, int(day_index or 1))
    ensure_sop_v1_defaults()
    repo.delete_sop_template_day(pool_key=normalized_pool_key, day_index=normalized_day_index)
    if _current_sop_template_day_count(normalized_pool_key) <= 0:
        _ensure_sop_template_day_exists(normalized_pool_key, 1)
    repo.save_sop_pool_config(
        {
            **(_serialize_sop_pool_config(repo.get_sop_pool_config(normalized_pool_key)) or _default_sop_pool_config(normalized_pool_key)),
            "pool_key": normalized_pool_key,
            "enabled": _normalize_bool((_serialize_sop_pool_config(repo.get_sop_pool_config(normalized_pool_key)) or {}).get("enabled", True)),
            "max_day_count": max(_current_sop_template_day_count(normalized_pool_key), 1),
            "send_time": _normalize_sop_send_time((_serialize_sop_pool_config(repo.get_sop_pool_config(normalized_pool_key)) or {}).get("send_time")),
            "timezone": SOP_V1_DEFAULT_TIMEZONE,
            "effective_start_at": _normalized_text((_serialize_sop_pool_config(repo.get_sop_pool_config(normalized_pool_key)) or {}).get("effective_start_at")) or _iso_now(),
        }
    )
    get_db().commit()
    remaining_payload = get_sop_v1_templates_payload(
        normalized_pool_key,
        selected_day_index=min(normalized_day_index, max(_current_sop_template_day_count(normalized_pool_key), 1)),
    )
    return remaining_payload


def _later_timestamp_text(*values: Any) -> str:
    latest: datetime | None = None
    latest_text = ""
    for value in values:
        parsed = _parse_timestamp(value)
        if parsed is None:
            continue
        if latest is None or parsed > latest:
            latest = parsed
            latest_text = parsed.strftime("%Y-%m-%d %H:%M:%S")
    return latest_text


def _sop_effective_start_at(pool_config: dict[str, Any]) -> str:
    return _normalized_text(pool_config.get("effective_start_at")) or _iso_now()


def _sop_anchor_date_from_entry(*, entry_time: str, pool_config: dict[str, Any]) -> tuple[str, str]:
    entry_dt = _parse_timestamp(entry_time) or datetime.now()
    first_effective_dt = entry_dt
    hour, minute = _parse_sop_send_time(pool_config.get("send_time"))
    scheduled_same_day = first_effective_dt.replace(hour=hour, minute=minute, second=0, microsecond=0)
    anchor_dt = first_effective_dt if first_effective_dt < scheduled_same_day else first_effective_dt + timedelta(days=1)
    return anchor_dt.strftime("%Y-%m-%d"), first_effective_dt.strftime("%Y-%m-%d %H:%M:%S")


def _upsert_sop_progress_entry(*, member_id: int, pool_key: str, entered_at: str, pool_config: dict[str, Any] | None = None) -> dict[str, Any]:
    normalized_pool_key = _validate_sop_pool_key(pool_key)
    normalized_pool_config = dict(pool_config or _serialize_sop_pool_config(repo.get_sop_pool_config(normalized_pool_key)) or _default_sop_pool_config(normalized_pool_key))
    entry_time = _normalized_text(entered_at) or _iso_now()
    existing = _serialize_sop_progress(repo.get_sop_progress(member_id=int(member_id), pool_key=normalized_pool_key))
    sop_anchor_date = _normalized_text(existing.get("sop_anchor_date"))
    first_effective_in_pool_at = _normalized_text(existing.get("first_effective_in_pool_at"))
    if not sop_anchor_date or not first_effective_in_pool_at:
        sop_anchor_date, first_effective_in_pool_at = _sop_anchor_date_from_entry(
            entry_time=entry_time,
            pool_config=normalized_pool_config,
        )
    payload = {
        "member_id": int(member_id),
        "pool_key": normalized_pool_key,
        "first_entered_at": existing.get("first_entered_at") or entry_time,
        "last_entered_at": entry_time,
        "sop_anchor_date": sop_anchor_date,
        "first_effective_in_pool_at": first_effective_in_pool_at,
        "last_in_pool_at": entry_time,
        "last_sent_day": int(existing.get("last_sent_day") or 0),
        "last_sent_at": _normalized_text(existing.get("last_sent_at")),
        "completed_at": _normalized_text(existing.get("completed_at")),
    }
    return _serialize_sop_progress(repo.save_sop_progress(payload))


def record_sop_pool_entry(*, member_id: int, pool_key: str, entered_at: str = "") -> dict[str, Any]:
    saved = _upsert_sop_progress_entry(member_id=int(member_id), pool_key=pool_key, entered_at=entered_at)
    get_db().commit()
    return saved

def _sop_skip_reason_label(reason: str) -> str:
    normalized_reason = _normalized_text(reason)
    return SOP_RUN_SKIPPED_REASON_LABELS.get(normalized_reason, normalized_reason or "未知原因")


def _parse_sop_send_time(send_time: str) -> tuple[int, int]:
    normalized = _normalize_sop_send_time(send_time)
    hour_text, minute_text = normalized.split(":", 1)
    return int(hour_text), int(minute_text)


def _next_sop_send_slot(reference: datetime, *, send_time: str) -> datetime:
    hour, minute = _parse_sop_send_time(send_time)
    scheduled = reference.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if reference < scheduled:
        return scheduled
    return scheduled + timedelta(days=1)


def _scheduled_sop_datetime_for_date(day_text: str, *, send_time: str) -> datetime | None:
    normalized_day_text = _normalized_text(day_text)
    if not normalized_day_text:
        return None
    try:
        return datetime.strptime(f"{normalized_day_text} {_normalize_sop_send_time(send_time)}", "%Y-%m-%d %H:%M")
    except ValueError:
        return None


def _current_sop_day_index(progress: dict[str, Any], *, now_dt: datetime) -> int:
    anchor_dt = _scheduled_sop_datetime_for_date(_normalized_text(progress.get("sop_anchor_date")), send_time="00:00")
    if anchor_dt is None:
        return 0
    return (now_dt.date() - anchor_dt.date()).days + 1


def _progress_anchor_timestamp(member: dict[str, Any], progress: dict[str, Any], *, now_text: str) -> str:
    return (
        _normalized_text(progress.get("last_in_pool_at"))
        or _normalized_text(progress.get("last_entered_at"))
        or _normalized_text(progress.get("first_entered_at"))
        or _normalized_text(member.get("joined_at"))
        or _normalized_text(member.get("created_at"))
        or now_text
    )


def _get_or_create_sop_progress(member: dict[str, Any], *, pool_config: dict[str, Any], now_text: str) -> dict[str, Any]:
    pool_key = _validate_sop_pool_key(pool_config.get("pool_key"))
    member_id = int(member.get("id") or 0)
    progress = _serialize_sop_progress(repo.get_sop_progress(member_id=member_id, pool_key=pool_key))
    if progress and _normalized_text(progress.get("sop_anchor_date")) and _normalized_text(progress.get("first_effective_in_pool_at")):
        return progress
    return _upsert_sop_progress_entry(
        member_id=member_id,
        pool_key=pool_key,
        entered_at=_progress_anchor_timestamp(member, progress, now_text=now_text),
        pool_config=pool_config,
    )


def _evaluate_sop_due(
    *,
    member: dict[str, Any],
    progress: dict[str, Any],
    pool_config: dict[str, Any],
    now_dt: datetime,
    now_text: str,
) -> dict[str, Any]:
    pool_key = _validate_sop_pool_key(pool_config.get("pool_key"))
    last_sent_day = int(progress.get("last_sent_day") or 0)
    current_day_index = max(_current_sop_day_index(progress, now_dt=now_dt), last_sent_day)
    max_template_day = max(_current_sop_template_day_count(pool_key), 1)
    current_day_index = max(min(current_day_index, max_template_day), last_sent_day)
    send_time = _normalize_sop_send_time(pool_config.get("send_time"))
    today_scheduled_dt = _scheduled_sop_datetime_for_date(now_dt.strftime("%Y-%m-%d"), send_time=send_time)
    if current_day_index <= 0:
        anchor_scheduled_dt = _scheduled_sop_datetime_for_date(_normalized_text(progress.get("sop_anchor_date")), send_time=send_time)
        return {
            "member": member,
            "progress": progress,
            "day_index": 0,
            "scheduled_for": anchor_scheduled_dt.strftime("%Y-%m-%d %H:%M:%S") if anchor_scheduled_dt else now_text,
            "skip_reason": "send_time_not_reached",
        }
    scheduled_for = today_scheduled_dt.strftime("%Y-%m-%d %H:%M:%S") if today_scheduled_dt else now_text
    skip_reason = "send_time_not_reached" if today_scheduled_dt and now_dt < today_scheduled_dt else ""
    return {
        "member": member,
        "progress": progress,
        "day_index": current_day_index,
        "scheduled_for": scheduled_for,
        "skip_reason": skip_reason,
    }


def _normalize_sop_template_images(template: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    image_media_ids: list[str] = []
    images: list[dict[str, Any]] = []
    for item in list(template.get("images_json") or []):
        if isinstance(item, str):
            normalized_media_id = _normalized_text(item)
            if normalized_media_id:
                image_media_ids.append(normalized_media_id)
            continue
        if not isinstance(item, dict):
            continue
        normalized_media_id = _normalized_text(item.get("media_id") or item.get("image_media_id"))
        if normalized_media_id:
            image_media_ids.append(normalized_media_id)
            continue
        if _normalized_text(item.get("data_base64")) or _normalized_text(item.get("data_url")):
            images.append(
                {
                    "file_name": _normalized_text(item.get("file_name")) or "sop-image.png",
                    "content_type": _normalized_text(item.get("content_type")) or "image/png",
                    "data_base64": _normalized_text(item.get("data_base64")),
                    "data_url": _normalized_text(item.get("data_url")),
                }
            )
    deduped_media_ids: list[str] = []
    seen_media_ids: set[str] = set()
    for media_id in image_media_ids:
        if media_id in seen_media_ids:
            continue
        seen_media_ids.add(media_id)
        deduped_media_ids.append(media_id)
    return deduped_media_ids, images


def _template_skip_reason(template: dict[str, Any]) -> str:
    if not template:
        return "no_template"
    if not _normalize_bool(template.get("enabled")):
        return "template_disabled"
    content = _normalized_text(template.get("content"))
    image_media_ids, images = _normalize_sop_template_images(template)
    if not content and not image_media_ids and not images:
        return "template_empty"
    return ""


def _create_sop_batch(
    *,
    pool_key: str,
    day_index: int,
    template: dict[str, Any] | None,
    scheduled_for: str,
    total_count: int,
    summary_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _serialize_sop_batch(
        repo.insert_sop_batch(
            {
                "pool_key": pool_key,
                "day_index": int(day_index),
                "template_id": template.get("id") if template else None,
                "scheduled_for": _normalized_text(scheduled_for),
                "status": "finished",
                "total_count": int(total_count),
                "success_count": 0,
                "skipped_count": 0,
                "failed_count": 0,
                "summary_json": dict(summary_json or {}),
            }
        )
    )


def _record_sop_batch_item(
    *,
    batch_id: int,
    member: dict[str, Any] | None,
    pool_key: str,
    day_index: int,
    external_userid: str,
    status: str,
    content_snapshot: str = "",
    images_snapshot: list[dict[str, Any]] | None = None,
    error_message: str = "",
    sent_record_id: int | None = None,
) -> dict[str, Any]:
    return _serialize_sop_batch_item(
        repo.insert_sop_batch_item(
            {
                "batch_id": int(batch_id),
                "member_id": int(member.get("id") or 0) if member else None,
                "pool_key": pool_key,
                "day_index": int(day_index),
                "day_index_snapshot": int(day_index),
                "external_userid": _normalized_text(external_userid),
                "status": _normalized_text(status),
                "error_message": _normalized_text(error_message),
                "content_snapshot": _normalized_text(content_snapshot),
                "images_snapshot": list(images_snapshot or []),
                "sent_record_id": sent_record_id,
            }
        )
    )


def _finalize_sop_batch(
    batch: dict[str, Any],
    *,
    success_count: int,
    skipped_count: int,
    failed_count: int,
    skipped_reasons: dict[str, int],
    success_record_ids: list[int],
) -> dict[str, Any]:
    total_count = int(batch.get("total_count") or 0)
    updated = repo.update_sop_batch(
        int(batch["id"]),
        {
            **batch,
            "status": "finished",
            "success_count": int(success_count),
            "skipped_count": int(skipped_count),
            "failed_count": int(failed_count),
            "summary_json": {
                "pool_key": _normalized_text(batch.get("pool_key")),
                "day_index": int(batch.get("day_index") or 0),
                "total_count": total_count,
                "success_count": int(success_count),
                "skipped_count": int(skipped_count),
                "failed_count": int(failed_count),
                "skipped_reasons": dict(skipped_reasons),
                "skipped_reason_labels": {key: _sop_skip_reason_label(key) for key in skipped_reasons},
                "success_record_ids": list(success_record_ids),
            },
        },
    )
    return _serialize_sop_batch(updated)


def _update_sop_progress_day(
    progress: dict[str, Any],
    *,
    day_index: int,
    sent_at: str,
) -> dict[str, Any]:
    return _serialize_sop_progress(
        repo.save_sop_progress(
            {
                "member_id": int(progress.get("member_id") or 0),
                "pool_key": _normalized_text(progress.get("pool_key")),
                "first_entered_at": _normalized_text(progress.get("first_entered_at")),
                "last_entered_at": _normalized_text(progress.get("last_entered_at")),
                "sop_anchor_date": _normalized_text(progress.get("sop_anchor_date")),
                "first_effective_in_pool_at": _normalized_text(progress.get("first_effective_in_pool_at")),
                "last_in_pool_at": _normalized_text(progress.get("last_in_pool_at")),
                "last_sent_day": int(day_index),
                "last_sent_at": _normalized_text(sent_at),
                "completed_at": _normalized_text(progress.get("completed_at")),
            }
        )
    )


def run_due_sop(
    *,
    operator_id: str = "",
    operator_type: str = "system",
) -> dict[str, Any]:
    ensure_sop_v1_defaults()
    now_text = _iso_now()
    now_dt = _parse_timestamp(now_text) or datetime.now()
    enabled_configs = [
        dict(item)
        for item in (get_sop_v1_config_payload().get("configs") or [])
        if _normalize_bool(item.get("enabled"))
    ]
    batch_ids: list[int] = []
    batches_payload: list[dict[str, Any]] = []
    total_skipped_count = 0
    created_batch_count = 0

    for pool_config in enabled_configs:
        pool_key = _validate_sop_pool_key(pool_config.get("pool_key"))
        if not repo.try_acquire_sop_pool_run_lock(pool_key=pool_key):
            continue

        members = [_serialize_member(row) for row in repo.list_stage_members_for_manual_send(current_pool=pool_key)]
        due_members: list[dict[str, Any]] = []
        for member in members:
            progress = _get_or_create_sop_progress(member, pool_config=pool_config, now_text=now_text)
            due_payload = _evaluate_sop_due(
                member=member,
                progress=progress,
                pool_config=pool_config,
                now_dt=now_dt,
                now_text=now_text,
            )
            if _normalized_text(due_payload.get("skip_reason")) == "send_time_not_reached":
                continue
            day_index = int(due_payload.get("day_index") or 0)
            if day_index <= 0:
                continue
            if repo.get_sop_batch_item_for_member_day(
                member_id=int(member.get("id") or 0),
                pool_key=pool_key,
                day_index_snapshot=day_index,
            ):
                continue
            template = _serialize_sop_template(repo.get_sop_template(pool_key=pool_key, day_index=day_index))
            template_skip_reason = _template_skip_reason(template)
            due_members.append(
                {
                    "member": member,
                    "progress": progress,
                    "day_index": day_index,
                    "scheduled_for": _normalized_text(due_payload.get("scheduled_for")) or now_text,
                    "template": template,
                    "template_skip_reason": template_skip_reason,
                }
            )

        groups: dict[tuple[str, int], list[dict[str, Any]]] = {}
        for candidate in due_members:
            group_key = (pool_key, int(candidate.get("day_index") or 0))
            groups.setdefault(group_key, []).append(candidate)

        for (_, day_index), candidates in sorted(groups.items(), key=lambda item: item[0][1]):
            template = dict((candidates[0] or {}).get("template") or {})
            batch = _create_sop_batch(
                pool_key=pool_key,
                day_index=day_index,
                template=template or None,
                scheduled_for=_normalized_text((candidates[0] or {}).get("scheduled_for")) or now_text,
                total_count=len(candidates),
                summary_json={"operator_type": _normalized_text(operator_type) or "system", "operator_id": _normalized_text(operator_id) or "sop_runner"},
            )
            created_batch_count += 1
            batch_ids.append(int(batch.get("id") or 0))

            sendable_targets: list[dict[str, Any]] = []
            sendable_candidates: list[dict[str, Any]] = []
            skipped_count = 0
            skipped_reasons: dict[str, int] = {}

            for candidate in candidates:
                member = dict(candidate.get("member") or {})
                progress = dict(candidate.get("progress") or {})
                external_userid = _normalized_text(member.get("external_contact_id"))
                skip_reason = _normalized_text(candidate.get("template_skip_reason"))
                if not external_userid:
                    skip_reason = "missing_external_userid"
                if skip_reason:
                    _record_sop_batch_item(
                        batch_id=int(batch.get("id") or 0),
                        member=member,
                        pool_key=pool_key,
                        day_index=day_index,
                        external_userid=external_userid,
                        status="skipped",
                        error_message=skip_reason,
                    )
                    _update_sop_progress_day(progress, day_index=day_index, sent_at=now_text)
                    skipped_count += 1
                    skipped_reasons[skip_reason] = int(skipped_reasons.get(skip_reason) or 0) + 1
                    continue
                sendable_targets.append(
                    {
                        "member_id": int(member.get("id") or 0),
                        "external_userid": external_userid,
                        "owner_userid": DEFAULT_OWNER_STAFF_ID,
                        "owner_display_name": DEFAULT_OWNER_STAFF_ID,
                        "mobile": _normalized_text(member.get("phone")),
                    }
                )
                sendable_candidates.append(candidate)
                # Record batch item as "pending" immediately so dedup checks work
                # on consecutive runs, and update progress so last_sent_day is tracked
                # before the broadcast_jobs worker runs.
                _record_sop_batch_item(
                    batch_id=int(batch.get("id") or 0),
                    member=member,
                    pool_key=pool_key,
                    day_index=day_index,
                    external_userid=external_userid,
                    status="pending",
                )
                _update_sop_progress_day(progress, day_index=day_index, sent_at=now_text)

            if sendable_targets:
                from ..broadcast_jobs import service as queue_service

                externals = [_normalized_text(t.get("external_userid")) for t in sendable_targets if _normalized_text(t.get("external_userid"))]
                queue_service.enqueue_job(
                    source_type="sop",
                    source_id=str(batch.get("id") or ""),
                    source_table="automation_sop_batches",
                    scheduled_for=datetime.now(),
                    target_external_userids=externals,
                    target_summary=f"sop pool={pool_key} day={day_index} — {len(externals)} 人",
                    content_type="private_message",
                    content_payload={
                        "batch_id": int(batch.get("id") or 0),
                        "pool_key": pool_key,
                        "day_index": day_index,
                        "template": template,
                        "sendable_targets": sendable_targets,
                        "sendable_candidates": sendable_candidates,
                        "operator_id": _normalized_text(operator_id) or "sop_runner",
                    },
                    content_summary=_normalized_text(template.get("content"))[:200],
                )
            else:
                _finalize_sop_batch(
                    batch,
                    success_count=0,
                    skipped_count=skipped_count,
                    failed_count=0,
                    skipped_reasons=skipped_reasons,
                    success_record_ids=[],
                )

            batches_payload.append({"batch_id": int(batch.get("id") or 0)})
            total_skipped_count += skipped_count

    get_db().commit()
    return {
        "ok": True,
        "status": "completed",
        "scanned_pool_count": len(enabled_configs),
        "created_batch_count": created_batch_count,
        "total_skipped_count": total_skipped_count,
        "batch_ids": batch_ids,
        "batches": batches_payload,
    }


def run_sop_batch(*, batch_data: dict[str, Any]) -> dict[str, Any]:
    """broadcast_jobs handler 调用 — 执行一个 SOP batch 的真发 + 记录。"""
    batch_id = int(batch_data.get("batch_id") or 0)
    pool_key = _normalized_text(batch_data.get("pool_key"))
    day_index = int(batch_data.get("day_index") or 0)
    template = batch_data.get("template") or {}
    sendable_targets = batch_data.get("sendable_targets") or []
    sendable_candidates = batch_data.get("sendable_candidates") or []
    operator_id = _normalized_text(batch_data.get("operator_id")) or "sop_runner"

    if not sendable_targets or not batch_id:
        return {"ok": False, "error": "empty sendable_targets or missing batch_id"}

    image_media_ids, images = _normalize_sop_template_images(template)
    miniprogram_library_ids: list[int] = []
    for mp_item in list(template.get("miniprograms_json") or []):
        if isinstance(mp_item, int):
            miniprogram_library_ids.append(int(mp_item))
            continue
        if not isinstance(mp_item, dict):
            continue
        raw_lid = mp_item.get("library_id")
        if not raw_lid:
            continue
        try:
            miniprogram_library_ids.append(int(raw_lid))
        except (TypeError, ValueError):
            continue

    dispatch_result = _dispatch_private_message_batch(
        target_items=sendable_targets,
        content=_normalized_text(template.get("content")),
        image_media_ids=image_media_ids,
        images=images,
        miniprogram_library_ids=miniprogram_library_ids,
        operator_id=operator_id,
        filter_snapshot={
            "selection_mode": "automation_conversion_sop",
            "pool_key": pool_key,
            "day_index": day_index,
        },
    )

    now_text = _iso_now()
    success_count = 0
    failed_count = 0
    success_record_ids: list[int] = []
    if int(dispatch_result.get("record_id") or 0) > 0:
        success_record_ids.append(int(dispatch_result["record_id"]))
    failed_external_userids = {
        _normalized_text(item)
        for item in list(dispatch_result.get("fail_external_userids") or [])
        if _normalized_text(item)
    }

    for target, candidate in zip(sendable_targets, sendable_candidates):
        member = dict(candidate.get("member") or {})
        progress = dict(candidate.get("progress") or {})
        external_userid = _normalized_text(target.get("external_userid"))
        member_id = int(member.get("id") or 0)
        # Look for existing "pending" batch item recorded during run_due_sop
        existing_item = repo.get_sop_batch_item_for_member_day(
            member_id=member_id,
            pool_key=pool_key,
            day_index_snapshot=day_index,
        ) if member_id else None
        final_status = "failed" if external_userid in failed_external_userids else "success"
        error_message = "dispatch_failed" if final_status == "failed" else ""
        content_snapshot = _normalized_text(template.get("content")) if final_status == "success" else ""
        images_snapshot = list(template.get("images_json") or []) if final_status == "success" else []
        sent_record_id = int(dispatch_result.get("record_id") or 0) or None
        if existing_item and int(existing_item.get("id") or 0):
            repo.update_sop_batch_item(
                int(existing_item["id"]),
                {
                    **existing_item,
                    "status": final_status,
                    "error_message": error_message,
                    "content_snapshot": content_snapshot,
                    "images_snapshot": images_snapshot,
                    "sent_record_id": sent_record_id,
                },
            )
        else:
            _record_sop_batch_item(
                batch_id=batch_id,
                member=member,
                pool_key=pool_key,
                day_index=day_index,
                external_userid=external_userid,
                status=final_status,
                error_message=error_message,
                content_snapshot=content_snapshot,
                images_snapshot=images_snapshot,
                sent_record_id=sent_record_id,
            )
        if final_status == "failed":
            failed_count += 1
        else:
            success_count += 1
        _update_sop_progress_day(progress, day_index=day_index, sent_at=now_text)

    batch_row = repo.get_sop_batch(batch_id)
    if batch_row:
        _finalize_sop_batch(
            dict(batch_row),
            success_count=success_count,
            skipped_count=0,
            failed_count=failed_count,
            skipped_reasons={},
            success_record_ids=success_record_ids,
        )
    get_db().commit()
    return {
        "ok": True,
        "sent_count": success_count,
        "failed_count": failed_count,
    }
