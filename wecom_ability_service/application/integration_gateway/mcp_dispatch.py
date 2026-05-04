from __future__ import annotations

import json
import re
import time
from datetime import date, datetime, timedelta
from typing import Any

from ...customer_center.service import get_customer_detail
from ...customer_timeline.service import get_customer_timeline
from ...db import get_db
from ...domains.admin_config import mcp_tool_enabled
from ...domains.automation_conversion import (
    audit_agent_skill_call,
    crm_get_member_basic,
    crm_get_member_questionnaire,
    crm_get_member_recent_events,
    crm_get_member_recent_outputs,
    crm_get_member_snapshot,
    crm_get_member_stage,
    create_agent_config_draft_via_mcp,
    create_agent_output_export_job,
    create_conversion_workflow,
    create_conversion_workflow_node,
    diff_agent_prompt,
    get_agent_config_detail,
    get_agent_output_detail,
    get_agent_output_export_job,
    get_agent_outputs_by_request,
    get_agent_outputs_by_user,
    get_all_agent_prompts,
    get_pool_snapshot,
    list_agent_configs,
    list_agent_outputs,
    list_conversion_workflow_nodes,
    list_conversion_workflow_registry,
    list_conversion_workflows,
    list_pending_agent_prompt_publish_requests,
    save_agent_config_draft,
    script_create_draft,
    script_diff_draft,
    script_get_item,
    script_list_drafts,
    script_list_items,
    script_search_items,
    script_submit_for_publish,
    script_update_draft,
    submit_agent_prompt_for_publish,
    suggest_pool_action,
    update_conversion_workflow,
    update_conversion_workflow_node,
)
from ...services import (
    ack_conversion_batch,
    ack_message_batch,
    extract_roomid_from_raw_payload,
    format_message_row,
    get_contact_by_external_userid,
    get_conversion_batch,
    get_group_chat_by_chat_id,
    get_group_chat_map,
    get_message_batch,
    get_messages_by_user,
    get_openclaw_customer_marketing_profile,
    get_pending_conversion_batches,
    get_recent_messages_by_user,
    get_routing_config,
    get_signup_conversion_batch,
    get_signup_tag_rules_config,
    list_message_batches,
    list_owner_role_map,
    list_signup_conversion_batches,
    mark_enrolled,
    materialize_message_batches,
    record_conversion_feedback,
    remove_tag_snapshot,
    resolve_person_identity,
    save_outbound_task,
    save_tag_snapshot,
    search_messages,
    send_pool_private_message,
    unmark_enrolled,
)
from ...wecom_client import WeComClient


def _tool_result(payload: Any) -> dict[str, Any]:
    payload = _json_safe(payload)
    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
        "structuredContent": payload,
    }


def _tool_result_messages(messages: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"messages": _json_safe(messages)}
    for key, value in extra.items():
        payload[key] = _json_safe(value)
    return _tool_result(payload)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat(sep=" ")
    return value


def _normalize_customer_ref(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    compact = re.sub(r"[\s()\-]+", "", text)
    if compact.startswith("+86"):
        compact = compact[3:]
    elif compact.startswith("86") and len(compact) == 13:
        compact = compact[2:]
    if re.fullmatch(r"1\d{10}", compact):
        return compact
    return text


def _is_mobile_customer_ref(value: str) -> bool:
    return bool(re.fullmatch(r"1\d{10}", value))


def _resolve_customer_locator(arguments: dict[str, Any], *, required: bool = True) -> dict[str, Any]:
    explicit_external_userid = str(arguments.get("external_userid") or "").strip()
    customer_ref = _normalize_customer_ref(arguments.get("customer_ref"))
    if explicit_external_userid:
        return {
            "customer_ref": customer_ref or explicit_external_userid,
            "matched_by": "external_userid",
            "external_userid": explicit_external_userid,
            "identity": resolve_person_identity(external_userid=explicit_external_userid),
        }
    if not customer_ref:
        if required:
            raise ValueError("customer_ref or external_userid is required")
        return {
            "customer_ref": "",
            "matched_by": "",
            "external_userid": "",
            "identity": {},
        }
    if _is_mobile_customer_ref(customer_ref):
        identity = resolve_person_identity(mobile=customer_ref)
        external_userid = str(identity.get("external_userid") or "").strip()
        if not external_userid:
            raise ValueError(f"customer not found for mobile: {customer_ref}")
        return {
            "customer_ref": customer_ref,
            "matched_by": "mobile",
            "external_userid": external_userid,
            "identity": identity,
        }
    return {
        "customer_ref": customer_ref,
        "matched_by": "external_userid",
        "external_userid": customer_ref,
        "identity": resolve_person_identity(external_userid=customer_ref),
    }


def _require_customer_detail(external_userid: str) -> dict[str, Any]:
    customer = get_customer_detail(external_userid)
    if not customer:
        raise ValueError("customer not found")
    return customer


def _normalize_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        candidates = [value]
    elif isinstance(value, (list, tuple, set)):
        candidates = list(value)
    else:
        candidates = [value]

    normalized: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def _normalize_limit(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        limit = int(value if value is not None else default)
    except (TypeError, ValueError) as exc:
        raise ValueError("limit must be an integer") from exc
    return max(minimum, min(limit, maximum))


def _normalize_boolean(value: Any, *, field_name: str, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if not text:
        return default
    if text in {"1", "true", "yes", "y"}:
        return True
    if text in {"0", "false", "no", "n"}:
        return False
    raise ValueError(f"{field_name} must be a boolean")


def _normalize_lookback_minutes(value: Any) -> int:
    try:
        lookback_minutes = int(value if value is not None else 60)
    except (TypeError, ValueError) as exc:
        raise ValueError("lookback_minutes must be an integer") from exc
    return max(1, min(lookback_minutes, 1440))


def _require_text(value: Any, *, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} is required")
    return text


def _collect_customer_refs(arguments: dict[str, Any]) -> list[str]:
    refs = _normalize_string_list(arguments.get("customer_refs"))
    refs.extend(item for item in _normalize_string_list(arguments.get("external_userids")) if item not in refs)
    if refs:
        return refs

    single_ref = (
        str(arguments.get("customer_ref") or "").strip()
        or str(arguments.get("external_userid") or "").strip()
    )
    return [single_ref] if single_ref else []


def _resolve_customers(arguments: dict[str, Any], *, allow_multiple: bool) -> list[dict[str, Any]]:
    refs = _collect_customer_refs(arguments)
    if not refs:
        raise ValueError("customer_ref or external_userid is required")
    if not allow_multiple and len(refs) != 1:
        raise ValueError("exactly one customer_ref is required")

    resolved: list[dict[str, Any]] = []
    seen_external_userids: set[str] = set()
    for ref in refs:
        locator_arguments = {"customer_ref": ref}
        locator = _resolve_customer_locator(locator_arguments)
        external_userid = locator["external_userid"]
        if external_userid in seen_external_userids:
            continue
        seen_external_userids.add(external_userid)
        resolved.append(
            {
                "customer_ref": ref,
                "matched_by": locator["matched_by"],
                "external_userid": external_userid,
                "identity": locator["identity"],
                "customer": _require_customer_detail(external_userid),
            }
        )
    return resolved


def _resolve_sender_userids(customers: list[dict[str, Any]], explicit_userid: Any = "") -> list[str]:
    explicit = str(explicit_userid or "").strip()
    if explicit:
        return [explicit]

    userids: list[str] = []
    seen: set[str] = set()
    for item in customers:
        owner_userid = str((item.get("customer") or {}).get("owner_userid") or "").strip()
        if not owner_userid or owner_userid in seen:
            continue
        seen.add(owner_userid)
        userids.append(owner_userid)
    if userids:
        return userids
    raise ValueError("userid is required because no owner_userid could be resolved")


def _list_owner_archived_messages(
    owner_userid: str,
    *,
    window_start: str,
    window_end: str,
    include_private: bool,
    include_group: bool,
) -> list[dict[str, Any]]:
    if not include_private and not include_group:
        return []

    sql = """
        SELECT id, seq, msgid, chat_type, external_userid, owner_userid, sender, receiver, msgtype, content, send_time, raw_payload
        FROM archived_messages
        WHERE owner_userid = ? AND send_time >= ? AND send_time <= ?
    """
    params: list[Any] = [owner_userid, window_start, window_end]
    if include_private and not include_group:
        sql += " AND chat_type = ?"
        params.append("private")
    elif include_group and not include_private:
        sql += " AND chat_type = ?"
        params.append("group")
    sql += " ORDER BY send_time ASC, id ASC"
    return get_db().execute(sql, tuple(params)).fetchall()


def _sender_role_for_message(message: dict[str, Any], *, owner_userid: str) -> str:
    sender = str(message.get("from") or message.get("sender") or "").strip()
    external_userid = str(message.get("external_userid") or "").strip()
    if sender and sender == owner_userid:
        return "staff"
    if sender and external_userid and sender == external_userid:
        return "customer"
    return "unknown"


def _build_owner_recent_chat_dump(arguments: dict[str, Any]) -> dict[str, Any]:
    owner_userid = _require_text(arguments.get("owner_userid"), field_name="owner_userid")
    lookback_minutes = _normalize_lookback_minutes(arguments.get("lookback_minutes"))
    include_private = _normalize_boolean(arguments.get("include_private"), field_name="include_private", default=True)
    include_group = _normalize_boolean(arguments.get("include_group"), field_name="include_group", default=True)

    window_end_dt = datetime.now()
    window_start_dt = window_end_dt - timedelta(minutes=lookback_minutes)
    window_start = window_start_dt.strftime("%Y-%m-%d %H:%M:%S")
    window_end = window_end_dt.strftime("%Y-%m-%d %H:%M:%S")

    rows = _list_owner_archived_messages(
        owner_userid,
        window_start=window_start,
        window_end=window_end,
        include_private=include_private,
        include_group=include_group,
    )
    group_map = get_group_chat_map([extract_roomid_from_raw_payload(row.get("raw_payload")) for row in rows])
    formatted_messages = [format_message_row(row, group_map=group_map) for row in rows]

    private_conversations_by_userid: dict[str, dict[str, Any]] = {}
    group_conversations_by_chat_id: dict[str, dict[str, Any]] = {}
    contact_cache: dict[str, dict[str, Any]] = {}

    for message in formatted_messages:
        chat_type = str(message.get("chat_type") or "").strip().lower()
        if chat_type == "private":
            external_userid = str(message.get("external_userid") or "").strip()
            if not external_userid:
                continue
            contact = contact_cache.get(external_userid)
            if contact is None:
                contact = get_contact_by_external_userid(external_userid) or {}
                contact_cache[external_userid] = contact
            conversation = private_conversations_by_userid.setdefault(
                external_userid,
                {
                    "external_userid": external_userid,
                    "customer_name": str(contact.get("customer_name") or "").strip(),
                    "messages": [],
                },
            )
            conversation["messages"].append(
                {
                    "send_time": str(message.get("send_time") or "").strip(),
                    "sender_role": _sender_role_for_message(message, owner_userid=owner_userid),
                    "msgtype": str(message.get("msgtype") or "").strip(),
                    "content": str(message.get("content") or "").strip(),
                    "owner_userid": owner_userid,
                    "sender": str(message.get("sender") or "").strip(),
                    "from": str(message.get("from") or "").strip(),
                    "tolist": message.get("tolist") or [],
                }
            )
            continue

        if chat_type != "group":
            continue

        chat_id = str(message.get("roomid") or message.get("chat_id") or "").strip()
        conversation = group_conversations_by_chat_id.setdefault(
            chat_id,
            {
                "roomid": chat_id,
                "chat_id": chat_id,
                "group_name": str(message.get("group_name") or "").strip(),
                "messages": [],
            },
        )
        conversation["messages"].append(
            {
                "send_time": str(message.get("send_time") or "").strip(),
                "sender_role": _sender_role_for_message(message, owner_userid=owner_userid),
                "external_userid": str(message.get("external_userid") or "").strip(),
                "msgtype": str(message.get("msgtype") or "").strip(),
                "content": str(message.get("content") or "").strip(),
                "owner_userid": owner_userid,
                "sender": str(message.get("sender") or "").strip(),
                "from": str(message.get("from") or "").strip(),
                "tolist": message.get("tolist") or [],
            }
        )

    return {
        "ok": True,
        "owner_userid": owner_userid,
        "lookback_minutes": lookback_minutes,
        "window_start": window_start,
        "window_end": window_end,
        "include_private": include_private,
        "include_group": include_group,
        "private_conversations": list(private_conversations_by_userid.values()),
        "group_conversations": list(group_conversations_by_chat_id.values()),
    }


def _build_customer_context_payload(arguments: dict[str, Any]) -> dict[str, Any]:
    resolved = _resolve_customers(arguments, allow_multiple=False)[0]
    external_userid = resolved["external_userid"]
    refresh_tags = bool(arguments.get("refresh_tags"))
    recent_message_limit = _normalize_limit(arguments.get("recent_message_limit"), default=20, minimum=1, maximum=200)
    timeline_limit = _normalize_limit(arguments.get("timeline_limit"), default=20, minimum=1, maximum=200)
    customer = get_customer_detail(external_userid, refresh_tags=refresh_tags)
    timeline, degraded, warnings = _get_customer_timeline_payload(external_userid, timeline_limit)
    return {
        "ok": True,
        "customer_ref": resolved["customer_ref"],
        "matched_by": resolved["matched_by"],
        "external_userid": external_userid,
        "customer": customer or resolved["customer"],
        "recent_messages": get_recent_messages_by_user(external_userid, recent_message_limit),
        "timeline": timeline,
        "recent_timeline_events": timeline.get("items", []),
        "source_status": "live",
        "degraded": degraded,
        "warnings": warnings,
        "refresh_tags": refresh_tags,
    }


def _normalize_tag_arguments(arguments: dict[str, Any]) -> tuple[list[str], list[str]]:
    add_tags = _normalize_string_list(arguments.get("add_tags"))
    if not add_tags:
        add_tags = _normalize_string_list(arguments.get("add_tag"))
    remove_tags = _normalize_string_list(arguments.get("remove_tags"))
    if not remove_tags:
        remove_tags = _normalize_string_list(arguments.get("remove_tag"))
    if not add_tags and not remove_tags:
        raise ValueError("at least one of add_tags/remove_tags is required")
    return add_tags, remove_tags


def _run_tag_operation(operation: Any) -> dict[str, Any]:
    try:
        payload = operation()
    except Exception as exc:  # pragma: no cover - exact exception type depends on WeCom/API path
        return {
            "ok": False,
            "error": str(exc),
            "error_type": exc.__class__.__name__,
        }
    return {
        "ok": True,
        "response": payload,
    }


def _update_customer_tags(arguments: dict[str, Any]) -> dict[str, Any]:
    resolved = _resolve_customers(arguments, allow_multiple=False)[0]
    add_tags, remove_tags = _normalize_tag_arguments(arguments)
    sender_userid = _resolve_sender_userids([resolved], arguments.get("userid"))[0]
    external_userid = resolved["external_userid"]
    client = WeComClient.from_app()

    result: dict[str, Any] = {
        "ok": True,
        "external_userid": external_userid,
        "userid": sender_userid,
        "add_tags": add_tags,
        "remove_tags": remove_tags,
        "results": {},
    }

    if add_tags:
        result["results"]["mark"] = _run_tag_operation(
            lambda: client.mark_tag(
                {
                    "userid": sender_userid,
                    "external_userid": external_userid,
                    "add_tag": add_tags,
                }
            )
        )
        if result["results"]["mark"]["ok"]:
            save_tag_snapshot(sender_userid, external_userid, add_tags)

    if remove_tags:
        result["results"]["unmark"] = _run_tag_operation(
            lambda: client.mark_tag(
                {
                    "userid": sender_userid,
                    "external_userid": external_userid,
                    "remove_tag": remove_tags,
                }
            )
        )
        if result["results"]["unmark"]["ok"]:
            remove_tag_snapshot(sender_userid, external_userid, remove_tags)

    result["ok"] = all(item["ok"] for item in result["results"].values())
    return result


def _build_private_message_payload(customers: list[dict[str, Any]], *, content: str, userid: Any = "") -> tuple[dict[str, Any], list[str]]:
    sender_userids = _resolve_sender_userids(customers, userid)
    payload = {
        "chat_type": "single",
        "external_userid": [customers[0]["external_userid"]],
        "sender": sender_userids[0] if sender_userids else "",
        "text": {"content": content},
    }
    return payload, sender_userids


def _build_group_message_payload(customers: list[dict[str, Any]], *, content: str, userid: Any = "") -> tuple[dict[str, Any], list[str]]:
    sender_userids = _resolve_sender_userids(customers, userid)
    payload = {
        "chat_type": "group",
        "external_userid": [item["external_userid"] for item in customers],
        "sender": sender_userids,
        "text": {"content": content},
    }
    return payload, sender_userids


def _build_moment_payload(customers: list[dict[str, Any]], *, content: str, userid: Any = "") -> tuple[dict[str, Any], list[str]]:
    sender_userids = _resolve_sender_userids(customers, userid)
    payload = {
        "visible_range": {"sender_list": {"userid": sender_userids}},
        "text": {"content": content},
    }
    return payload, sender_userids


def _build_task_result(
    task_result: dict[str, Any],
    *,
    task_type: str,
    customers: list[dict[str, Any]],
    sender_userids: list[str],
) -> dict[str, Any]:
    external_userids = [item["external_userid"] for item in customers]
    return {
        "ok": True,
        "task_type": task_type,
        "task_id": task_result["task_id"],
        "wecom_result": task_result["wecom_result"],
        "external_userid": external_userids[0] if len(external_userids) == 1 else "",
        "external_userids": external_userids,
        "userid": sender_userids[0] if len(sender_userids) == 1 else "",
        "userids": sender_userids,
        "resolved_customers": [
            {
                "customer_ref": item["customer_ref"],
                "matched_by": item["matched_by"],
                "external_userid": item["external_userid"],
                "customer_name": str((item.get("customer") or {}).get("customer_name") or "").strip(),
                "owner_userid": str((item.get("customer") or {}).get("owner_userid") or "").strip(),
            }
            for item in customers
        ],
    }


def _default_timeline_payload(external_userid: str, timeline_limit: int) -> dict[str, Any]:
    return {
        "external_userid": external_userid,
        "items": [],
        "count": 0,
        "limit": timeline_limit,
        "offset": 0,
        "filters": {"event_type": "", "limit": str(timeline_limit), "offset": "0"},
        "total": 0,
    }


def _normalize_timeline_payload(
    timeline: Any,
    *,
    external_userid: str,
    timeline_limit: int,
    compatibility_mode: bool,
) -> tuple[dict[str, Any], bool]:
    if not isinstance(timeline, dict):
        return _default_timeline_payload(external_userid, timeline_limit), True
    items = timeline.get("items")
    if not isinstance(items, list):
        items = []
    if compatibility_mode:
        items = items[:timeline_limit]
    normalized = dict(timeline)
    normalized["external_userid"] = str(timeline.get("external_userid") or external_userid).strip() or external_userid
    normalized["items"] = items
    normalized["count"] = len(items)
    normalized["limit"] = int(timeline.get("limit") or timeline_limit)
    normalized["offset"] = int(timeline.get("offset") or 0)
    normalized["filters"] = timeline.get("filters") or {
        "event_type": "",
        "limit": str(timeline_limit),
        "offset": "0",
    }
    normalized["total"] = int(timeline.get("total") or len(items))
    return normalized, False


def _get_customer_timeline_payload(external_userid: str, timeline_limit: int) -> tuple[dict[str, Any], bool, list[str]]:
    filters = {
        "normalized_limit": timeline_limit,
        "normalized_offset": 0,
        "limit": timeline_limit,
        "offset": 0,
        "event_type": "",
    }
    warnings: list[str] = []
    try:
        timeline = get_customer_timeline(external_userid, filters)
        normalized, fallback_failed = _normalize_timeline_payload(
            timeline,
            external_userid=external_userid,
            timeline_limit=timeline_limit,
            compatibility_mode=False,
        )
        return normalized, fallback_failed, warnings
    except TypeError as exc:
        message = str(exc)
        if "positional argument" not in message:
            raise
        warnings.append("timeline compatibility fallback applied: legacy get_customer_timeline signature")
        timeline = get_customer_timeline(external_userid)  # type: ignore[misc]
        normalized, fallback_failed = _normalize_timeline_payload(
            timeline,
            external_userid=external_userid,
            timeline_limit=timeline_limit,
            compatibility_mode=True,
        )
        return normalized, fallback_failed, warnings


def _parse_dry_run(arguments: dict[str, Any]) -> bool:
    dry_run = arguments.get("dry_run")
    if dry_run is None:
        return True
    if isinstance(dry_run, bool):
        return dry_run
    text = str(dry_run).strip().lower()
    if text in {"", "1", "true", "yes", "y"}:
        return True
    if text in {"0", "false", "no", "n"}:
        return False
    raise ValueError("dry_run must be a boolean")


def _parse_confirm(arguments: dict[str, Any]) -> bool:
    confirm = arguments.get("confirm")
    if isinstance(confirm, bool):
        return confirm
    text = str(confirm or "").strip().lower()
    return text in {"1", "true", "yes", "y"}


def _build_task_preview_result(
    *,
    task_type: str,
    customers: list[dict[str, Any]],
    sender_userids: list[str],
    payload: dict[str, Any],
) -> dict[str, Any]:
    resolved_customers = [
        {
            "customer_ref": item["customer_ref"],
            "matched_by": item["matched_by"],
            "external_userid": item["external_userid"],
            "customer_name": str((item.get("customer") or {}).get("customer_name") or "").strip(),
            "owner_userid": str((item.get("customer") or {}).get("owner_userid") or "").strip(),
        }
        for item in customers
    ]
    resolved_external_userids = [item["external_userid"] for item in customers]
    resolved_owner_userids = [userid for userid in sender_userids if userid]
    result: dict[str, Any] = {
        "ok": True,
        "task_type": task_type,
        "dry_run": True,
        "would_execute": True,
        "preview_payload": payload,
        "resolved_customers": resolved_customers,
        "resolved_external_userids": resolved_external_userids,
        "resolved_owner_userids": resolved_owner_userids,
    }
    if len(resolved_customers) == 1:
        result["resolved_customer"] = resolved_customers[0]
    return result


def _call_business_task(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    business_mode = bool(_collect_customer_refs(arguments) or str(arguments.get("content") or "").strip())
    dry_run = _parse_dry_run(arguments)
    confirm = _parse_confirm(arguments)
    if not dry_run and not confirm:
        raise ValueError("confirm=true is required when dry_run=false")
    if not business_mode:
        mapping = {
            "create_private_message_task": ("create_private_message_task", "private_message"),
            "create_group_message_task": ("create_group_message_task", "group_message"),
            "create_moment_task": ("create_moment_task", "moment"),
        }
        fn_name, task_type = mapping[name]
        if dry_run:
            return _tool_result(
                {
                    "ok": True,
                    "task_type": task_type,
                    "dry_run": True,
                    "would_execute": True,
                    "preview_payload": arguments,
                    "resolved_customers": [],
                    "resolved_external_userids": _normalize_string_list(arguments.get("external_userids") or arguments.get("external_userid")),
                    "resolved_owner_userids": _normalize_string_list(arguments.get("sender") or arguments.get("userid")),
                }
            )
        return _tool_result(_call_wecom_task(fn_name, task_type, arguments))

    content = _require_text(arguments.get("content"), field_name="content")
    if name == "create_private_message_task":
        customers = _resolve_customers(arguments, allow_multiple=False)
        payload, sender_userids = _build_private_message_payload(customers, content=content, userid=arguments.get("userid"))
        if dry_run:
            return _tool_result(
                _build_task_preview_result(
                    task_type="private_message",
                    customers=customers,
                    sender_userids=sender_userids,
                    payload=payload,
                )
            )
        task_result = _call_wecom_task("create_private_message_task", "private_message", payload)
        return _tool_result(_build_task_result(task_result, task_type="private_message", customers=customers, sender_userids=sender_userids))
    if name == "create_group_message_task":
        customers = _resolve_customers(arguments, allow_multiple=True)
        payload, sender_userids = _build_group_message_payload(customers, content=content, userid=arguments.get("userid"))
        if dry_run:
            return _tool_result(
                _build_task_preview_result(
                    task_type="group_message",
                    customers=customers,
                    sender_userids=sender_userids,
                    payload=payload,
                )
            )
        task_result = _call_wecom_task("create_group_message_task", "group_message", payload)
        return _tool_result(_build_task_result(task_result, task_type="group_message", customers=customers, sender_userids=sender_userids))
    if name == "create_moment_task":
        customers = _resolve_customers(arguments, allow_multiple=True)
        payload, sender_userids = _build_moment_payload(customers, content=content, userid=arguments.get("userid"))
        if dry_run:
            return _tool_result(
                _build_task_preview_result(
                    task_type="moment",
                    customers=customers,
                    sender_userids=sender_userids,
                    payload=payload,
                )
            )
        task_result = _call_wecom_task("create_moment_task", "moment", payload)
        return _tool_result(_build_task_result(task_result, task_type="moment", customers=customers, sender_userids=sender_userids))
    raise ValueError(f"unknown business task: {name}")


def _parse_timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, pattern)
        except ValueError:
            continue
    return None


def _stringify_tags(customer: dict[str, Any]) -> list[str]:
    tags = customer.get("tags") or []
    result: list[str] = []
    seen: set[str] = set()
    for item in tags:
        if isinstance(item, dict):
            value = str(item.get("tag_name") or item.get("tag_id") or "").strip()
        else:
            value = str(item or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    class_status = customer.get("class_user_status") or {}
    signup_label_name = str(class_status.get("signup_label_name") or "").strip()
    if signup_label_name and signup_label_name not in seen:
        result.append(signup_label_name)
    return result


def _build_followup_candidates(arguments: dict[str, Any]) -> dict[str, Any]:
    limit = _normalize_limit(arguments.get("limit"), default=20, minimum=1, maximum=100)
    lookback_hours = _normalize_limit(arguments.get("lookback_hours"), default=24, minimum=1, maximum=168)
    now = datetime.now()
    since = (now - timedelta(hours=lookback_hours)).strftime("%Y-%m-%d %H:%M:%S")
    rows = get_db().execute(
        """
        SELECT external_userid, MAX(send_time) AS last_message_at
        FROM archived_messages
        WHERE external_userid IS NOT NULL AND external_userid <> '' AND send_time >= ?
        GROUP BY external_userid
        ORDER BY last_message_at DESC, external_userid ASC
        """,
        (since,),
    ).fetchall()

    blocked_keywords = ("已成交", "成交", "勿扰", "关闭", "黑名单")
    high_intent_keywords = ("高意向", "待跟进", "已报价")
    candidates: list[dict[str, Any]] = []

    for row in rows:
        external_userid = str(row.get("external_userid") or "").strip()
        if not external_userid:
            continue
        customer = get_customer_detail(external_userid)
        if not customer:
            continue

        tags = _stringify_tags(customer)
        class_status = customer.get("class_user_status") or {}
        status_text = " ".join(
            [
                str(class_status.get("signup_status") or "").strip(),
                str(class_status.get("signup_label_name") or "").strip(),
                " ".join(tags),
            ]
        )
        if any(keyword in status_text for keyword in blocked_keywords):
            continue

        recent_messages = get_recent_messages_by_user(external_userid, 20)
        if not recent_messages:
            continue

        score = 0
        reasons: list[str] = []
        last_customer_message_at: datetime | None = None
        latest_message_from_customer = False
        for index, message in enumerate(recent_messages):
            sender = str(message.get("from") or message.get("sender") or "").strip()
            send_time = _parse_timestamp(message.get("send_time"))
            if index == 0 and sender == external_userid:
                latest_message_from_customer = True
            if sender == external_userid and send_time is not None:
                last_customer_message_at = send_time
                break

        if last_customer_message_at is not None:
            age_hours = (now - last_customer_message_at).total_seconds() / 3600
            if age_hours <= 1:
                score += 5
                reasons.append("最近1小时客户有消息")
            elif age_hours <= 6:
                score += 3
                reasons.append("最近6小时客户有消息")

        if latest_message_from_customer:
            score += 4
            reasons.append("客户最后一条消息后暂无顾问跟进")

        if any(keyword in tag for tag in tags for keyword in high_intent_keywords):
            score += 3
            reasons.append("当前标签包含高意向信号")

        score += 2
        reasons.append("客户仍处于可继续跟进状态")

        if score <= 0:
            continue

        candidates.append(
            {
                "external_userid": external_userid,
                "customer_name": str(customer.get("customer_name") or "").strip(),
                "owner_userid": str(customer.get("owner_userid") or "").strip(),
                "score": score,
                "reason": reasons[0],
                "reasons": reasons,
                "suggested_action": "contact_now" if score >= 6 else "review_context",
                "last_message_at": str(customer.get("last_message_at") or row.get("last_message_at") or "").strip(),
                "tags": tags,
                "class_user_status": class_status,
            }
        )

    candidates.sort(key=lambda item: (int(item["score"]), str(item["last_message_at"]), item["external_userid"]), reverse=True)
    ranked = []
    for index, item in enumerate(candidates[:limit], start=1):
        payload = dict(item)
        payload["rank"] = index
        ranked.append(payload)

    return {
        "ok": True,
        "generated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "lookback_hours": lookback_hours,
        "limit": limit,
        "candidates": ranked,
    }


def _call_wecom_task(fn_name: str, task_type: str, arguments: dict[str, Any]) -> dict[str, Any]:
    client = WeComClient.from_app()
    result = getattr(client, fn_name)(arguments)
    local_id = save_outbound_task(task_type, arguments, result)
    return {"ok": True, "task_id": local_id, "wecom_result": result}


def _run_agent_skill(
    skill_code: str,
    arguments: dict[str, Any],
    *,
    permission_scope: str,
    fn,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    idempotency_key = str(arguments.get("idempotency_key") or "").strip()
    try:
        payload = fn()
    except Exception as exc:
        error_code = str(getattr(exc, "error_code", "") or "runtime_error").strip() or "runtime_error"
        response_payload = {"ok": False, "error": str(exc)}
        if hasattr(exc, "to_payload") and callable(getattr(exc, "to_payload")):
            try:
                response_payload["detail"] = exc.to_payload()
            except Exception:
                pass
        audit_agent_skill_call(
            skill_code=skill_code,
            source="mcp",
            permissions_scope=permission_scope,
            request_payload=arguments,
            response_payload=response_payload,
            status="error",
            error_code=error_code,
            error_message=str(exc),
            latency_ms=int((time.perf_counter() - started_at) * 1000),
            idempotency_key=idempotency_key,
        )
        raise
    audit_agent_skill_call(
        skill_code=skill_code,
        source="mcp",
        permissions_scope=permission_scope,
        request_payload=arguments,
        response_payload=payload,
        status="success",
        latency_ms=int((time.perf_counter() - started_at) * 1000),
        idempotency_key=idempotency_key,
    )
    return _tool_result(payload)


def _call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    arguments = arguments or {}
    if not mcp_tool_enabled(name):
        raise ValueError(f"tool is disabled: {name}")
    if name == "resolve_customer":
        payload = _build_customer_context_payload(arguments) if bool(arguments.get("include_context")) else {}
        if not payload:
            resolved = _resolve_customers(arguments, allow_multiple=False)[0]
            payload = {
                "ok": True,
                "customer_ref": resolved["customer_ref"],
                "matched_by": resolved["matched_by"],
                "external_userid": resolved["external_userid"],
                "customer": resolved["customer"],
            }
        payload["available_actions"] = [
            "get_customer_context",
            "get_contact",
            "get_messages",
            "get_recent_messages",
            "search_messages",
            "update_customer_tags",
            "mark_tags",
            "unmark_tags",
            "create_private_message_task",
            "create_group_message_task",
            "create_moment_task",
            "send_pool_private_message",
        ]
        return _tool_result(payload)
    if name == "get_contact":
        external_userid = _resolve_customer_locator(arguments)["external_userid"]
        return _tool_result(
            get_contact_by_external_userid(external_userid, refresh_tags=bool(arguments.get("refresh_tags"))) or {}
        )
    if name == "get_customer_context":
        return _tool_result(_build_customer_context_payload(arguments))
    if name == "get_messages":
        external_userid = _resolve_customer_locator(arguments)["external_userid"]
        return _tool_result_messages(
            get_messages_by_user(
                external_userid,
                chat_type=arguments.get("chat_type"),
            ),
            external_userid=external_userid,
            chat_type=(arguments.get("chat_type") or "").strip(),
        )
    if name == "get_recent_messages":
        external_userid = _resolve_customer_locator(arguments)["external_userid"]
        limit = int(arguments.get("limit", 20))
        return _tool_result_messages(
            get_recent_messages_by_user(
                external_userid,
                limit,
                chat_type=arguments.get("chat_type"),
            ),
            external_userid=external_userid,
            limit=limit,
            chat_type=(arguments.get("chat_type") or "").strip(),
        )
    if name == "search_messages":
        external_userid = _resolve_customer_locator(arguments)["external_userid"]
        keyword = (arguments.get("keyword") or "").strip()
        return _tool_result_messages(
            search_messages(
                external_userid,
                keyword,
            ),
            external_userid=external_userid,
            keyword=keyword,
        )
    if name == "get_group_chat":
        chat_id = (arguments.get("chat_id") or "").strip()
        if not chat_id:
            raise ValueError("chat_id is required")
        return _tool_result(get_group_chat_by_chat_id(chat_id) or {})
    if name == "update_customer_tags":
        return _tool_result(_update_customer_tags(arguments))
    if name == "mark_tags":
        result = _update_customer_tags(arguments)
        return _tool_result({"ok": result["ok"], "result": result["results"].get("mark")})
    if name == "unmark_tags":
        result = _update_customer_tags(arguments)
        return _tool_result({"ok": result["ok"], "result": result["results"].get("unmark")})
    if name == "create_private_message_task":
        return _call_business_task(name, arguments)
    if name == "create_moment_task":
        return _call_business_task(name, arguments)
    if name == "create_group_message_task":
        return _call_business_task(name, arguments)
    if name == "send_pool_private_message":
        return _tool_result(
            send_pool_private_message(
                owner_userid=str(arguments.get("owner_userid") or "").strip(),
                pool_key=str(arguments.get("pool_key") or "").strip(),
                content=str(arguments.get("content") or "").strip(),
                images=list(arguments.get("images") or []),
                image_media_ids=list(arguments.get("image_media_ids") or []),
                attachments=list(arguments.get("attachments") or []),
                confirm=bool(arguments.get("confirm")),
                operator=str(arguments.get("operator") or "").strip(),
            )
        )
    if name == "record_conversion_feedback":
        locator = _resolve_customer_locator(arguments, required=False)
        feedback_result = record_conversion_feedback(
            feedback_type=(arguments.get("feedback_type") or "").strip(),
            external_userid=locator["external_userid"],
            chat_id=(arguments.get("chat_id") or "").strip(),
            actor=(arguments.get("actor") or "").strip(),
            feedback_payload=arguments.get("feedback_payload") or {},
        )
        return _tool_result(feedback_result)
    if name == "get_owner_role_map":
        return _tool_result(
            {
                "items": list_owner_role_map(active_only=bool(arguments.get("active_only", False))),
            }
        )
    if name == "get_signup_tag_rules":
        return _tool_result(get_signup_tag_rules_config())
    if name == "get_routing_config":
        return _tool_result(get_routing_config())
    if name == "get_owner_recent_chat_dump":
        return _tool_result(_build_owner_recent_chat_dump(arguments))
    if name == "get_pending_message_batches":
        materialize_message_batches(window_minutes=3)
        return _tool_result(
            list_message_batches(
                limit=int(arguments.get("limit", 20)),
                cursor=str(arguments.get("cursor", "") or ""),
            )
        )
    if name == "get_message_batch":
        materialize_message_batches(window_minutes=3)
        batch = get_message_batch(
            int(arguments.get("batch_id", 0)),
            limit=int(arguments.get("limit", 200)),
            cursor=str(arguments.get("cursor", "") or ""),
        )
        if not batch:
            raise ValueError("batch not found")
        return _tool_result(batch)
    if name == "ack_message_batch":
        batch = ack_message_batch(
            int(arguments.get("batch_id", 0)),
            ack_note=(arguments.get("ack_note") or ""),
            acked_by=(arguments.get("acked_by") or ""),
        )
        if not batch:
            raise ValueError("batch not found")
        return _tool_result(batch)
    if name == "get_signup_conversion_batches":
        return _tool_result(
            list_signup_conversion_batches(
                limit=int(arguments.get("limit", 20)),
                cursor=str(arguments.get("cursor", "") or ""),
            )
        )
    if name == "get_customer_marketing_profile":
        return _tool_result(
            get_openclaw_customer_marketing_profile(
                external_userid=str(arguments.get("external_userid") or "").strip(),
                person_id=arguments.get("person_id"),
                recent_message_limit=_normalize_limit(arguments.get("recent_message_limit"), default=3, minimum=1, maximum=50),
            )
        )
    if name == "get_pending_conversion_batches":
        return _tool_result(
            get_pending_conversion_batches(
                limit=int(arguments.get("limit", 20)),
                cursor=str(arguments.get("cursor", "") or ""),
            )
        )
    if name == "get_conversion_batch":
        batch = get_conversion_batch(
            int(arguments.get("batch_id", 0)),
            recent_message_limit=_normalize_limit(arguments.get("recent_message_limit"), default=3, minimum=1, maximum=50),
        )
        if not batch:
            raise ValueError("batch not found")
        return _tool_result(batch)
    if name == "ack_conversion_batch":
        batch = ack_conversion_batch(
            int(arguments.get("batch_id", 0)),
            ack_note=(arguments.get("ack_note") or ""),
            acked_by=(arguments.get("acked_by") or ""),
        )
        if not batch:
            raise ValueError("batch not found")
        return _tool_result(batch)
    if name == "get_signup_conversion_batch":
        batch = get_signup_conversion_batch(int(arguments.get("batch_id", 0)))
        if not batch:
            raise ValueError("batch not found")
        recent_message_limit = _normalize_limit(arguments.get("recent_message_limit"), default=20, minimum=1, maximum=200)
        timeline_limit = _normalize_limit(arguments.get("timeline_limit"), default=20, minimum=1, maximum=200)
        candidates: list[dict[str, Any]] = []
        for item in batch.get("candidates") or []:
            candidate = dict(item)
            external_userid = str(candidate.get("external_userid") or "").strip()
            if external_userid:
                candidate["customer_context"] = _build_customer_context_payload(
                    {
                        "external_userid": external_userid,
                        "recent_message_limit": recent_message_limit,
                        "timeline_limit": timeline_limit,
                    }
                )
            else:
                candidate["customer_context"] = {}
            candidates.append(candidate)
        batch["candidates"] = candidates
        return _tool_result(batch)
    if name == "mark_enrolled":
        return _tool_result(
            mark_enrolled(
                external_userid=str(arguments.get("external_userid") or "").strip(),
                owner_userid=str(arguments.get("owner_userid") or "").strip(),
                operator=str(arguments.get("operator") or "").strip(),
                source=str(arguments.get("source") or "").strip() or "mcp",
                signup_status=str(arguments.get("signup_status") or "").strip(),
            )
        )
    if name == "unmark_enrolled":
        return _tool_result(
            unmark_enrolled(
                external_userid=str(arguments.get("external_userid") or "").strip(),
                owner_userid=str(arguments.get("owner_userid") or "").strip(),
                operator=str(arguments.get("operator") or "").strip(),
                source=str(arguments.get("source") or "").strip() or "mcp",
                restore_signup_status=str(arguments.get("restore_signup_status") or "").strip(),
            )
        )
    if name == "get_hourly_followup_candidates":
        return _tool_result(_build_followup_candidates(arguments))
    if name == "crm.get_member_basic":
        return _run_agent_skill(
            "crm.get_member_basic",
            arguments,
            permission_scope="crm_read",
            fn=lambda: crm_get_member_basic(
                external_contact_id=str(arguments.get("external_contact_id") or "").strip(),
                phone=str(arguments.get("phone") or "").strip(),
            ),
        )
    if name == "crm.get_member_stage":
        return _run_agent_skill(
            "crm.get_member_stage",
            arguments,
            permission_scope="crm_read",
            fn=lambda: crm_get_member_stage(
                external_contact_id=str(arguments.get("external_contact_id") or "").strip(),
                phone=str(arguments.get("phone") or "").strip(),
            ),
        )
    if name == "crm.get_member_questionnaire":
        return _run_agent_skill(
            "crm.get_member_questionnaire",
            arguments,
            permission_scope="crm_read",
            fn=lambda: crm_get_member_questionnaire(
                external_contact_id=str(arguments.get("external_contact_id") or "").strip(),
                phone=str(arguments.get("phone") or "").strip(),
            ),
        )
    if name == "crm.get_member_recent_events":
        return _run_agent_skill(
            "crm.get_member_recent_events",
            arguments,
            permission_scope="crm_read",
            fn=lambda: crm_get_member_recent_events(
                external_contact_id=str(arguments.get("external_contact_id") or "").strip(),
                phone=str(arguments.get("phone") or "").strip(),
                limit=int(arguments.get("limit") or 20),
            ),
        )
    if name == "crm.get_member_recent_outputs":
        return _run_agent_skill(
            "crm.get_member_recent_outputs",
            arguments,
            permission_scope="crm_read",
            fn=lambda: crm_get_member_recent_outputs(
                external_contact_id=str(arguments.get("external_contact_id") or "").strip(),
                phone=str(arguments.get("phone") or "").strip(),
                limit=int(arguments.get("limit") or 20),
            ),
        )
    if name == "crm.get_member_snapshot":
        return _run_agent_skill(
            "crm.get_member_snapshot",
            arguments,
            permission_scope="crm_read",
            fn=lambda: crm_get_member_snapshot(
                external_contact_id=str(arguments.get("external_contact_id") or "").strip(),
                phone=str(arguments.get("phone") or "").strip(),
            ),
        )
    if name == "script.list_items":
        return _run_agent_skill(
            "script.list_items",
            arguments,
            permission_scope="script_read",
            fn=lambda: script_list_items(query=str(arguments.get("query") or "").strip()),
        )
    if name == "script.get_item":
        return _run_agent_skill(
            "script.get_item",
            arguments,
            permission_scope="script_read",
            fn=lambda: script_get_item(str(arguments.get("agent_code") or "").strip()),
        )
    if name == "script.search_items":
        return _run_agent_skill(
            "script.search_items",
            arguments,
            permission_scope="script_read",
            fn=lambda: script_search_items(str(arguments.get("keyword") or "").strip()),
        )
    if name == "script.create_draft":
        return _run_agent_skill(
            "script.create_draft",
            arguments,
            permission_scope="draft_write",
            fn=lambda: script_create_draft(
                str(arguments.get("agent_code") or "").strip(),
                operator_id=str(arguments.get("operator") or "lobster_mcp").strip() or "lobster_mcp",
                from_version=str(arguments.get("from_version") or "published").strip() or "published",
                change_summary=str(arguments.get("change_summary") or "").strip(),
            ),
        )
    if name == "script.update_draft":
        return _run_agent_skill(
            "script.update_draft",
            arguments,
            permission_scope="draft_write",
            fn=lambda: script_update_draft(
                str(arguments.get("agent_code") or "").strip(),
                operator_id=str(arguments.get("operator") or "lobster_mcp").strip() or "lobster_mcp",
                display_name=arguments.get("display_name"),
                enabled=arguments.get("enabled"),
                role_prompt=arguments.get("role_prompt"),
                task_prompt=arguments.get("task_prompt"),
                variables=arguments.get("variables"),
                output_schema=arguments.get("output_schema"),
                change_summary=str(arguments.get("change_summary") or "").strip(),
            ),
        )
    if name == "script.diff_draft":
        return _run_agent_skill(
            "script.diff_draft",
            arguments,
            permission_scope="script_read",
            fn=lambda: script_diff_draft(str(arguments.get("agent_code") or "").strip()),
        )
    if name == "script.submit_for_publish":
        return _run_agent_skill(
            "script.submit_for_publish",
            arguments,
            permission_scope="publish_request",
            fn=lambda: script_submit_for_publish(
                str(arguments.get("agent_code") or "").strip(),
                operator_id=str(arguments.get("operator") or "lobster_mcp").strip() or "lobster_mcp",
                change_summary=str(arguments.get("change_summary") or "").strip(),
            ),
        )
    if name == "script.list_drafts":
        return _run_agent_skill(
            "script.list_drafts",
            arguments,
            permission_scope="script_read",
            fn=lambda: script_list_drafts(changed_only=bool(arguments.get("changed_only", True))),
        )
    if name == "crm.automation.get_workflow_registry":
        return _run_agent_skill(
            "crm.automation.get_workflow_registry",
            arguments,
            permission_scope="workflow_read",
            fn=lambda: list_conversion_workflow_registry(),
        )
    if name == "crm.automation.list_workflows":
        return _run_agent_skill(
            "crm.automation.list_workflows",
            arguments,
            permission_scope="workflow_read",
            fn=lambda: list_conversion_workflows(
                include_archived=bool(arguments.get("include_archived")),
                status=str(arguments.get("status") or "").strip(),
            ),
        )
    if name == "crm.automation.get_workflow_nodes":
        return _run_agent_skill(
            "crm.automation.get_workflow_nodes",
            arguments,
            permission_scope="workflow_read",
            fn=lambda: list_conversion_workflow_nodes(int(arguments.get("workflow_id") or 0)),
        )
    if name == "crm.automation.create_workflow":
        return _run_agent_skill(
            "crm.automation.create_workflow",
            arguments,
            permission_scope="workflow_write",
            fn=lambda: create_conversion_workflow(
                {
                    key: value
                    for key, value in {
                        "workflow_name": arguments.get("workflow_name"),
                        "workflow_code": arguments.get("workflow_code"),
                        "description": arguments.get("description"),
                        "status": arguments.get("status"),
                        "recipient_filter_basis": arguments.get("recipient_filter_basis"),
                        "recipient_behavior_tier_keys": arguments.get("recipient_behavior_tier_keys"),
                        "content_segmentation_basis": arguments.get("content_segmentation_basis"),
                        "content_profile_segment_template_id": arguments.get("content_profile_segment_template_id"),
                        "segmentation_basis": arguments.get("segmentation_basis"),
                        "generation_mode": arguments.get("generation_mode"),
                        "profile_segment_template_id": arguments.get("profile_segment_template_id"),
                        "fallback_to_standard_content": arguments.get("fallback_to_standard_content"),
                        "audiences": arguments.get("audiences"),
                        "agent_bindings": arguments.get("agent_bindings"),
                    }.items()
                    if value is not None
                },
                operator_id=str(arguments.get("operator") or "lobster_mcp").strip() or "lobster_mcp",
            ),
        )
    if name == "crm.automation.create_workflow_node":
        return _run_agent_skill(
            "crm.automation.create_workflow_node",
            arguments,
            permission_scope="workflow_write",
            fn=lambda: create_conversion_workflow_node(
                int(arguments.get("workflow_id") or 0),
                {
                    key: value
                    for key, value in {
                        "node_name": arguments.get("node_name"),
                        "node_code": arguments.get("node_code"),
                        "target_audience_code": arguments.get("target_audience_code"),
                        "trigger_mode": arguments.get("trigger_mode"),
                        "day_offset": arguments.get("day_offset"),
                        "send_time": arguments.get("send_time"),
                        "timezone": arguments.get("timezone"),
                        "position_index": arguments.get("position_index"),
                        "enabled": arguments.get("enabled"),
                        "content_mode": arguments.get("content_mode"),
                        "segmentation_basis": arguments.get("segmentation_basis"),
                        "standard_content_text": arguments.get("standard_content_text"),
                        "standard_content_payload": arguments.get("standard_content_payload"),
                        "fallback_to_standard_content": arguments.get("fallback_to_standard_content"),
                        "content_variants": arguments.get("content_variants"),
                        "agent_bindings": arguments.get("agent_bindings"),
                    }.items()
                    if value is not None
                },
                operator_id=str(arguments.get("operator") or "lobster_mcp").strip() or "lobster_mcp",
            ),
        )
    if name == "crm.automation.update_workflow":
        return _run_agent_skill(
            "crm.automation.update_workflow",
            arguments,
            permission_scope="workflow_write",
            fn=lambda: update_conversion_workflow(
                int(arguments.get("workflow_id") or 0),
                {
                    key: value
                    for key, value in {
                        "workflow_name": arguments.get("workflow_name"),
                        "workflow_code": arguments.get("workflow_code"),
                        "description": arguments.get("description"),
                        "status": arguments.get("status"),
                        "recipient_filter_basis": arguments.get("recipient_filter_basis"),
                        "recipient_behavior_tier_keys": arguments.get("recipient_behavior_tier_keys"),
                        "content_segmentation_basis": arguments.get("content_segmentation_basis"),
                        "content_profile_segment_template_id": arguments.get("content_profile_segment_template_id"),
                        "segmentation_basis": arguments.get("segmentation_basis"),
                        "generation_mode": arguments.get("generation_mode"),
                        "profile_segment_template_id": arguments.get("profile_segment_template_id"),
                        "fallback_to_standard_content": arguments.get("fallback_to_standard_content"),
                        "audiences": arguments.get("audiences"),
                        "agent_bindings": arguments.get("agent_bindings"),
                    }.items()
                    if value is not None
                },
                operator_id=str(arguments.get("operator") or "lobster_mcp").strip() or "lobster_mcp",
            ),
        )
    if name == "crm.automation.update_workflow_node":
        return _run_agent_skill(
            "crm.automation.update_workflow_node",
            arguments,
            permission_scope="workflow_write",
            fn=lambda: update_conversion_workflow_node(
                int(arguments.get("node_id") or 0),
                {
                    key: value
                    for key, value in {
                        "node_name": arguments.get("node_name"),
                        "node_code": arguments.get("node_code"),
                        "target_audience_code": arguments.get("target_audience_code"),
                        "trigger_mode": arguments.get("trigger_mode"),
                        "day_offset": arguments.get("day_offset"),
                        "send_time": arguments.get("send_time"),
                        "timezone": arguments.get("timezone"),
                        "position_index": arguments.get("position_index"),
                        "enabled": arguments.get("enabled"),
                        "content_mode": arguments.get("content_mode"),
                        "segmentation_basis": arguments.get("segmentation_basis"),
                        "standard_content_text": arguments.get("standard_content_text"),
                        "standard_content_payload": arguments.get("standard_content_payload"),
                        "fallback_to_standard_content": arguments.get("fallback_to_standard_content"),
                        "content_variants": arguments.get("content_variants"),
                        "agent_bindings": arguments.get("agent_bindings"),
                    }.items()
                    if value is not None
                },
                operator_id=str(arguments.get("operator") or "lobster_mcp").strip() or "lobster_mcp",
            ),
        )
    if name == "get_pool_snapshot":
        return _run_agent_skill(
            "get_pool_snapshot",
            arguments,
            permission_scope="read",
            fn=lambda: get_pool_snapshot(
                pool_key=str(arguments.get("pool_key") or "").strip(),
                limit=int(arguments.get("limit") or 10),
            ),
        )
    if name == "get_agent_config":
        return _run_agent_skill(
            "get_agent_config",
            arguments,
            permission_scope="read",
            fn=lambda: {"agent": get_agent_config_detail(str(arguments.get("agent_code") or "").strip())},
        )
    if name == "list_agent_configs":
        return _run_agent_skill(
            "list_agent_configs",
            arguments,
            permission_scope="read",
            fn=lambda: list_agent_configs(enabled_only=bool(arguments.get("enabled_only"))),
        )
    if name == "create_agent_config":
        return _run_agent_skill(
            "create_agent_config",
            arguments,
            permission_scope="draft_write",
            fn=lambda: create_agent_config_draft_via_mcp(
                {
                    key: value
                    for key, value in {
                        "agent_code": arguments.get("agent_code"),
                        "display_name": arguments.get("display_name"),
                        "enabled": arguments.get("enabled"),
                        "role_prompt": arguments.get("role_prompt"),
                        "task_prompt": arguments.get("task_prompt"),
                        "enabled_context_sources": arguments.get("enabled_context_sources"),
                        "variables": arguments.get("variables"),
                        "output_schema": arguments.get("output_schema"),
                        "change_summary": arguments.get("change_summary"),
                    }.items()
                    if value is not None
                },
                operator_id=str(arguments.get("operator") or "lobster_mcp").strip() or "lobster_mcp",
            ),
        )
    if name == "get_all_agent_prompts":
        return _run_agent_skill(
            "get_all_agent_prompts",
            arguments,
            permission_scope="read",
            fn=lambda: get_all_agent_prompts(enabled_only=bool(arguments.get("enabled_only"))),
        )
    if name == "save_agent_prompt_draft":
        return _run_agent_skill(
            "save_agent_prompt_draft",
            arguments,
            permission_scope="draft_write",
            fn=lambda: save_agent_config_draft(
                str(arguments.get("agent_code") or "").strip(),
                {
                    **(dict(arguments.get("patch") or {}) if isinstance(arguments.get("patch"), dict) else {}),
                    **{
                        key: value
                        for key, value in {
                            "display_name": arguments.get("display_name"),
                            "enabled": arguments.get("enabled"),
                            "role_prompt": arguments.get("role_prompt"),
                            "task_prompt": arguments.get("task_prompt"),
                            "enabled_context_sources": arguments.get("enabled_context_sources"),
                            "variables": arguments.get("variables"),
                            "output_schema": arguments.get("output_schema"),
                            "change_summary": arguments.get("change_summary"),
                            "expected_draft_version": arguments.get("expected_draft_version"),
                        }.items()
                        if value is not None
                    },
                },
                operator_id=str(arguments.get("operator") or "mcp").strip() or "mcp",
                source="mcp",
            ),
        )
    if name == "diff_agent_prompt":
        return _run_agent_skill(
            "diff_agent_prompt",
            arguments,
            permission_scope="read",
            fn=lambda: diff_agent_prompt(str(arguments.get("agent_code") or "").strip()),
        )
    if name == "submit_agent_prompt_for_publish":
        return _run_agent_skill(
            "submit_agent_prompt_for_publish",
            arguments,
            permission_scope="draft_write",
            fn=lambda: submit_agent_prompt_for_publish(
                str(arguments.get("agent_code") or "").strip(),
                operator_id=str(arguments.get("operator") or "mcp").strip() or "mcp",
                change_summary=str(arguments.get("change_summary") or "").strip(),
                expected_draft_version=arguments.get("expected_draft_version"),
            ),
        )
    if name == "list_pending_agent_prompt_publish_requests":
        return _run_agent_skill(
            "list_pending_agent_prompt_publish_requests",
            arguments,
            permission_scope="read",
            fn=lambda: list_pending_agent_prompt_publish_requests(
                agent_code=str(arguments.get("agent_code") or "").strip(),
                enabled_only=bool(arguments.get("enabled_only")),
                page=int(arguments.get("page") or 1),
                page_size=int(arguments.get("page_size") or 20),
            ),
        )
    if name == "list_agent_outputs":
        return _run_agent_skill(
            "list_agent_outputs",
            arguments,
            permission_scope="read",
            fn=lambda: list_agent_outputs(
                dict(arguments.get("filters") or {}),
                page=int(arguments.get("page") or 1),
                page_size=int(arguments.get("page_size") or 20),
                visibility="full",
            ),
        )
    if name == "get_agent_output":
        return _run_agent_skill(
            "get_agent_output",
            arguments,
            permission_scope="read",
            fn=lambda: get_agent_output_detail(str(arguments.get("output_id") or "").strip(), visibility="full"),
        )
    if name == "get_agent_outputs_by_request":
        return _run_agent_skill(
            "list_agent_outputs",
            arguments,
            permission_scope="read",
            fn=lambda: get_agent_outputs_by_request(str(arguments.get("request_id") or "").strip(), visibility="full"),
        )
    if name == "get_agent_outputs_by_user":
        return _run_agent_skill(
            "list_agent_outputs",
            arguments,
            permission_scope="read",
            fn=lambda: get_agent_outputs_by_user(
                str(arguments.get("userid") or "").strip(),
                limit=int(arguments.get("limit") or 20),
                visibility="full",
            ),
        )
    if name == "export_agent_outputs":
        return _run_agent_skill(
            "export_agent_outputs",
            arguments,
            permission_scope="export",
            fn=lambda: {"job": create_agent_output_export_job(dict(arguments.get("filters") or {}), requested_by=str(arguments.get("requested_by") or "mcp").strip() or "mcp")},
        )
    if name == "suggest_pool_action":
        return _run_agent_skill(
            "suggest_pool_action",
            arguments,
            permission_scope="suggest_only",
            fn=lambda: suggest_pool_action(
                external_contact_id=str(arguments.get("external_contact_id") or "").strip(),
                phone=str(arguments.get("phone") or "").strip(),
                operator_id=str(arguments.get("operator") or "mcp").strip() or "mcp",
            ),
        )
    raise ValueError(f"unknown tool: {name}")


class DispatchMcpToolCommand:
    """Wave 1 application dispatch for MCP tools.

    This keeps legacy business execution outside the JSON-RPC transport module
    while preserving current tool behavior and payload shape.
    """

    def __call__(self, tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        normalized_name = str(tool_name or "").strip()
        if not normalized_name:
            raise ValueError("tool_name is required")
        return _call_tool(normalized_name, dict(arguments or {}))

    execute = __call__


def execute_mcp_tool_runtime(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """Legacy-compatible runtime delegate used by admin console and Wave 1 shims."""

    return DispatchMcpToolCommand()(name, arguments)


__all__ = ["DispatchMcpToolCommand", "execute_mcp_tool_runtime"]
