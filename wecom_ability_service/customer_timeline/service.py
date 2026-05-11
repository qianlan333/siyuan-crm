from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from ..domains.marketing_automation.presenter import (
    conversion_marked_summary as business_conversion_marked_summary,
    marketing_state_change_summary as business_marketing_state_change_summary,
    value_segment_change_summary as business_value_segment_change_summary,
)
from ..services import extract_roomid_from_raw_payload, format_message_row, get_group_chat_map
from .dto import TimelineDTO, TimelineItemDTO
from .repo import (
    fetch_archived_messages,
    fetch_conversion_dispatch_logs,
    fetch_marketing_state_changes,
    fetch_questionnaire_submissions,
    fetch_status_changes,
    fetch_value_segment_changes,
    fetch_wecom_events,
    has_customer_timeline_scope,
)


def _stringify(value: Any) -> str:
    return str(value or "").strip()


def _json_loads(value: Any, *, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not value:
        return default
    try:
        decoded = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default
    return decoded


def _format_unix_timestamp(value: Any) -> str:
    try:
        if value in (None, ""):
            return ""
        return datetime.fromtimestamp(int(value)).strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError, OSError):
        return ""


def _stage_key(main_stage: Any, sub_stage: Any) -> str:
    main = _stringify(main_stage)
    sub = _stringify(sub_stage)
    if main and sub:
        return f"{main}/{sub}"
    return main or sub


def _coalesce_text(*values: Any) -> str:
    for value in values:
        text = _stringify(value)
        if text:
            return text
    return ""


def _marketing_state_summary(*, previous_stage: str, current_stage: str) -> str:
    return business_marketing_state_change_summary(previous_stage=previous_stage, current_stage=current_stage)


def _value_segment_summary(*, previous_segment: str, current_segment: str) -> str:
    return business_value_segment_change_summary(previous_segment=previous_segment, current_segment=current_segment)


def _conversion_marked_summary(action: str, source: str) -> str:
    return business_conversion_marked_summary(action=action, source=source)


def _dispatch_summary(row: dict[str, Any]) -> str:
    batch_id = row.get("batch_id")
    batch_label = f"批次 #{batch_id}" if batch_id not in (None, "") else "候选批次"
    dispatch_status = _stringify(row.get("dispatch_status"))
    if dispatch_status in {"converted_before_dispatch", "cancelled"}:
        return f"OpenClaw 转化候选 {batch_label} 已取消，状态={dispatch_status}"
    if dispatch_status == "acked":
        return f"OpenClaw 转化候选 {batch_label} 已确认接收"
    if _stringify(row.get("dispatched_at")):
        return f"OpenClaw 已下发转化候选 {batch_label}"
    if dispatch_status:
        return f"OpenClaw 转化候选 {batch_label} 状态更新为 {dispatch_status}"
    return f"OpenClaw 转化候选 {batch_label} 已记录"


def _message_items(external_userid: str, *, limit: int | None = None) -> list[TimelineItemDTO]:
    rows = fetch_archived_messages(external_userid, limit=limit)
    group_map = get_group_chat_map([extract_roomid_from_raw_payload(row.get("raw_payload")) for row in rows])
    items: list[TimelineItemDTO] = []
    for row in rows:
        message = format_message_row(row, group_map=group_map)
        event_time = _stringify(row.get("send_time")) or _stringify(row.get("created_at"))
        items.append(
            TimelineItemDTO(
                event_id=f"message:{row['id']}",
                event_type="message",
                event_time=event_time,
                occurred_at=event_time,
                title=f"消息 · {_stringify(message.get('msgtype')) or 'unknown'}",
                summary=_stringify(message.get("content")),
                source_table="archived_messages",
                source_id=str(row["id"]),
                operator_userid=_stringify(message.get("from") or row.get("sender") or row.get("owner_userid")),
                external_userid=external_userid,
                payload=message,
                metadata=message,
            )
        )
    return items


def _status_change_items(external_userid: str, *, limit: int | None = None) -> list[TimelineItemDTO]:
    rows = fetch_status_changes(external_userid, limit=limit)
    items: list[TimelineItemDTO] = []
    for row in rows:
        event_time = _stringify(row.get("set_at")) or _stringify(row.get("created_at"))
        items.append(
            TimelineItemDTO(
                event_id=f"status_change:{row['id']}",
                event_type="status_change",
                event_time=event_time,
                occurred_at=event_time,
                title="状态变更",
                summary=f"{_stringify(row.get('old_signup_status')) or '-'} -> {_stringify(row.get('new_signup_status')) or '-'}",
                source_table="class_user_status_history",
                source_id=str(row["id"]),
                operator_userid=_stringify(row.get("set_by_userid") or row.get("owner_userid_snapshot")),
                external_userid=external_userid,
                payload=dict(row),
                metadata=dict(row),
            )
        )
    return items


def _questionnaire_items(external_userid: str, *, limit: int | None = None) -> list[TimelineItemDTO]:
    rows = fetch_questionnaire_submissions(external_userid, limit=limit)
    items: list[TimelineItemDTO] = []
    for row in rows:
        title_suffix = _stringify(row.get("questionnaire_title")) or _stringify(row.get("questionnaire_name"))
        event_time = _stringify(row.get("submitted_at"))
        final_tags = _json_loads(row.get("final_tags"), default=[])
        metadata = dict(row)
        metadata["final_tags"] = final_tags if isinstance(final_tags, list) else []
        items.append(
            TimelineItemDTO(
                event_id=f"questionnaire_submit:{row['id']}",
                event_type="questionnaire_submit",
                event_time=event_time,
                occurred_at=event_time,
                title="问卷提交" + (f" · {title_suffix}" if title_suffix else ""),
                summary=f"score={row.get('total_score') or 0}",
                source_table="questionnaire_submissions",
                source_id=str(row["id"]),
                operator_userid=_stringify(row.get("follow_user_userid") or row.get("staff_id")),
                external_userid=external_userid,
                payload=metadata,
                metadata=metadata,
            )
        )
    return items


def _wecom_event_items(external_userid: str, *, limit: int | None = None) -> list[TimelineItemDTO]:
    rows = fetch_wecom_events(external_userid, limit=limit)
    items: list[TimelineItemDTO] = []
    for row in rows:
        event_time = _format_unix_timestamp(row.get("event_time")) or _stringify(row.get("created_at")) or _stringify(
            row.get("updated_at")
        )
        metadata = dict(row)
        metadata["payload_json"] = _json_loads(row.get("payload_json"), default={})
        items.append(
            TimelineItemDTO(
                event_id=f"wecom_event:{row['id']}",
                event_type="wecom_event",
                event_time=event_time,
                occurred_at=event_time,
                title="企微事件",
                summary=f"{_stringify(row.get('event_type'))} · {_stringify(row.get('change_type'))}",
                source_table="wecom_external_contact_event_logs",
                source_id=str(row["id"]),
                operator_userid=_stringify(row.get("user_id")),
                external_userid=external_userid,
                payload=metadata,
                metadata=metadata,
            )
        )
    return items


def _marketing_state_change_items(
    external_userid: str,
    rows: list[dict[str, Any]],
) -> list[TimelineItemDTO]:
    items: list[TimelineItemDTO] = []
    for index, row in enumerate(rows):
        payload_json = _json_loads(row.get("state_payload_json"), default={})
        if not isinstance(payload_json, dict):
            payload_json = {}
        current_stage = _stage_key(row.get("main_stage"), row.get("sub_stage"))
        previous_row = rows[index + 1] if index + 1 < len(rows) else {}
        previous_stage = _stage_key(previous_row.get("main_stage"), previous_row.get("sub_stage"))
        event_time = _coalesce_text(row.get("recorded_at"), row.get("created_at"), row.get("last_conversion_marked_at"))
        metadata = dict(row)
        metadata["state_payload_json"] = payload_json
        metadata["current_stage"] = current_stage
        metadata["previous_stage"] = previous_stage
        items.append(
            TimelineItemDTO(
                event_id=f"marketing_state_change:{row['id']}",
                event_type="marketing_state_change",
                type="marketing_state_change",
                event_time=event_time,
                occurred_at=event_time,
                title="营销阶段变更",
                summary=_marketing_state_summary(previous_stage=previous_stage, current_stage=current_stage),
                source_table="customer_marketing_state_history",
                source_id=str(row["id"]),
                operator_userid=_coalesce_text(
                    payload_json.get("manual_conversion_operator"),
                    payload_json.get("manual_conversion_source"),
                ),
                external_userid=external_userid,
                payload=metadata,
                metadata=metadata,
            )
        )
    return items


def _conversion_marked_items(
    external_userid: str,
    rows: list[dict[str, Any]],
) -> list[TimelineItemDTO]:
    items: list[TimelineItemDTO] = []
    for row in rows:
        payload_json = _json_loads(row.get("state_payload_json"), default={})
        if not isinstance(payload_json, dict):
            payload_json = {}
        action = _coalesce_text(payload_json.get("manual_conversion_action"), row.get("change_reason"))
        if action not in {"mark_enrolled", "unmark_enrolled"}:
            continue
        event_time = _coalesce_text(row.get("recorded_at"), row.get("created_at"), row.get("last_conversion_marked_at"))
        current_stage = _stage_key(row.get("main_stage"), row.get("sub_stage"))
        metadata = dict(row)
        metadata["state_payload_json"] = payload_json
        metadata["current_stage"] = current_stage
        metadata["conversion_action"] = action
        items.append(
            TimelineItemDTO(
                event_id=f"conversion_marked:{row['id']}",
                event_type="conversion_marked",
                type="conversion_marked",
                event_time=event_time,
                occurred_at=event_time,
                title="成交确认",
                summary=_conversion_marked_summary(
                    action=action,
                    source=_coalesce_text(payload_json.get("manual_conversion_source")),
                ),
                source_table="customer_marketing_state_history",
                source_id=str(row["id"]),
                operator_userid=_coalesce_text(
                    payload_json.get("manual_conversion_operator"),
                    payload_json.get("manual_conversion_source"),
                ),
                external_userid=external_userid,
                payload=metadata,
                metadata=metadata,
            )
        )
    return items


def _value_segment_change_items(
    external_userid: str,
    rows: list[dict[str, Any]],
) -> list[TimelineItemDTO]:
    items: list[TimelineItemDTO] = []
    for index, row in enumerate(rows):
        matched_question_ids = _json_loads(row.get("matched_question_ids_json"), default=[])
        if not isinstance(matched_question_ids, list):
            matched_question_ids = []
        source_payload = _json_loads(row.get("source_payload_json"), default={})
        if not isinstance(source_payload, dict):
            source_payload = {}
        current_segment = _stringify(row.get("segment"))
        previous_segment = _stringify((rows[index + 1] if index + 1 < len(rows) else {}).get("segment"))
        event_time = _coalesce_text(row.get("recorded_at"), row.get("evaluated_at"), row.get("created_at"))
        metadata = dict(row)
        metadata["matched_question_ids_json"] = matched_question_ids
        metadata["source_payload_json"] = source_payload
        metadata["current_segment"] = current_segment
        metadata["previous_segment"] = previous_segment
        items.append(
            TimelineItemDTO(
                event_id=f"value_segment_change:{row['id']}",
                event_type="value_segment_change",
                type="value_segment_change",
                event_time=event_time,
                occurred_at=event_time,
                title="客户分层变更",
                summary=_value_segment_summary(previous_segment=previous_segment, current_segment=current_segment),
                source_table="customer_value_segment_history",
                source_id=str(row["id"]),
                operator_userid="",
                external_userid=external_userid,
                payload=metadata,
                metadata=metadata,
            )
        )
    return items


def _openclaw_dispatch_items(external_userid: str, *, limit: int | None = None) -> list[TimelineItemDTO]:
    rows = fetch_conversion_dispatch_logs(external_userid, limit=limit)
    items: list[TimelineItemDTO] = []
    for row in rows:
        dispatch_payload = _json_loads(row.get("dispatch_payload_json"), default={})
        if not isinstance(dispatch_payload, dict):
            dispatch_payload = {}
        event_time = _coalesce_text(row.get("dispatched_at"), row.get("acked_at"), row.get("updated_at"), row.get("created_at"))
        metadata = dict(row)
        metadata["dispatch_payload_json"] = dispatch_payload
        items.append(
            TimelineItemDTO(
                event_id=f"openclaw_dispatch:{row['id']}",
                event_type="openclaw_dispatch",
                type="openclaw_dispatch",
                event_time=event_time,
                occurred_at=event_time,
                title="OpenClaw 派发",
                summary=_dispatch_summary(row),
                source_table="conversion_dispatch_log",
                source_id=str(row["id"]),
                operator_userid=_coalesce_text(
                    dispatch_payload.get("operator"),
                    dispatch_payload.get("source"),
                ),
                external_userid=external_userid,
                payload=metadata,
                metadata=metadata,
            )
        )
    return items


def _get_customer_timeline_impl(
    external_userid: str,
    filters: dict[str, Any],
) -> dict[str, Any] | None:
    normalized_external_userid = _stringify(external_userid)
    if not normalized_external_userid:
        return None
    if not has_customer_timeline_scope(normalized_external_userid):
        return None

    limit = int(filters["normalized_limit"])
    offset = int(filters["normalized_offset"])
    # Each source needs to return at least ``offset + limit`` rows to guarantee
    # the global top-N after sort is correct. Cap with a small headroom in case
    # one source dominates the ordering.
    per_source_limit = max(offset + limit, 50) * 2

    marketing_state_rows = fetch_marketing_state_changes(normalized_external_userid, limit=per_source_limit)
    value_segment_rows = fetch_value_segment_changes(normalized_external_userid, limit=per_source_limit)
    items = (
        _message_items(normalized_external_userid, limit=per_source_limit)
        + _status_change_items(normalized_external_userid, limit=per_source_limit)
        + _questionnaire_items(normalized_external_userid, limit=per_source_limit)
        + _wecom_event_items(normalized_external_userid, limit=per_source_limit)
        + _marketing_state_change_items(normalized_external_userid, marketing_state_rows)
        + _conversion_marked_items(normalized_external_userid, marketing_state_rows)
        + _value_segment_change_items(normalized_external_userid, value_segment_rows)
        + _openclaw_dispatch_items(normalized_external_userid, limit=per_source_limit)
    )

    event_type = _stringify(filters.get("event_type"))
    if event_type:
        items = [item for item in items if item.event_type == event_type]

    items.sort(key=lambda item: (item.event_time, item.source_table, item.source_id), reverse=True)

    page_items = items[offset : offset + limit]

    payload = TimelineDTO(
        external_userid=normalized_external_userid,
        items=page_items,
        count=len(page_items),
        limit=limit,
        offset=offset,
        filters={
            "event_type": _stringify(filters.get("event_type")),
            "limit": _stringify(filters.get("limit")),
            "offset": _stringify(filters.get("offset")),
        },
        total=len(items),
    )
    return payload.to_dict()


def get_customer_timeline(
    external_userid: str,
    filters: dict[str, Any],
) -> dict[str, Any] | None:
    """Legacy compatibility wrapper around the Wave 1 customer read-model query."""

    from ..application.customer_read_model import CustomerTimelineQueryDTO, GetCustomerTimelineQuery

    raw_filters = dict(filters or {})
    return GetCustomerTimelineQuery()(
        CustomerTimelineQueryDTO(
            external_userid=external_userid,
            event_type=str(raw_filters.get("event_type", "") or ""),
            limit=raw_filters.get("limit", raw_filters.get("normalized_limit", 50)),
            offset=raw_filters.get("offset", raw_filters.get("normalized_offset", 0)),
        )
    )
