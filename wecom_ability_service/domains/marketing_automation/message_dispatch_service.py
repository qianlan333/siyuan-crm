from __future__ import annotations

from typing import Any

from . import service as _legacy


def send_pool_private_message(
    *,
    owner_userid: str,
    pool_key: str,
    content: str = "",
    confirm: bool = False,
    operator: str = "",
    images: list[dict[str, Any]] | None = None,
    image_media_ids: list[str] | None = None,
    attachments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Internal automation message-dispatch owner for pool private-message sends."""

    normalized_owner_userid, owner_role = _legacy._validate_send_owner_userid(owner_userid)
    normalized_pool_key = _legacy._normalized_text(pool_key)
    if normalized_pool_key not in _legacy._POOL_SENDABLE_POOL_KEYS:
        if normalized_pool_key == _legacy.POOL_SILENT:
            raise ValueError("silent pool is record-only and does not support batch send")
        raise ValueError("pool_key is invalid")

    payload = {
        "content": _legacy._normalized_text(content),
        "images": list(images or []),
        "image_media_ids": list(image_media_ids or []),
        "attachments": list(attachments or []),
    }
    task_payload, content_preview, image_count = _legacy.user_ops_page_service._build_private_message_payload(payload)
    plan = _legacy._build_pool_send_plan(owner_userid=normalized_owner_userid, pool_key=normalized_pool_key)
    result = {
        "pool_key": normalized_pool_key,
        "pool_label": _legacy._pool_label(normalized_pool_key),
        "owner_userid": normalized_owner_userid,
        "owner_display_name": _legacy._normalized_text(owner_role.get("display_name")) or normalized_owner_userid,
        "matched_count": int(plan["matched_count"]),
        "sendable_count": int(plan["eligible_count"]),
        "skipped_count": int(plan["skipped_count"]),
        "skipped_by_reason": dict(plan["skipped_by_reason"]),
        "content_preview": content_preview,
        "image_count": image_count,
        "record_id": None,
        "confirmed": bool(confirm),
        "executed": False,
    }
    if not confirm:
        return result
    if not plan["matched_count"]:
        result.update({"status": "empty", "empty_reason": "no_customers_in_pool_for_owner"})
        return result
    if not plan["eligible_items"]:
        result.update({"status": "empty", "empty_reason": "no_sendable_customers_in_pool_for_owner"})
        return result

    task_results: list[dict[str, Any]] = []
    outbound_task_ids: list[int] = []
    sender_userids: list[str] = []
    eligible_items = list(plan["eligible_items"])
    grouped_targets: dict[str, list[dict[str, Any]]] = {}
    for item in eligible_items:
        grouped_targets.setdefault(_legacy._normalized_text(item.get("owner_userid")), []).append(item)

    for sender_userid, items in sorted(grouped_targets.items()):
        if not sender_userid:
            continue
        sender_userids.append(sender_userid)
        request_payload = {
            "sender": sender_userid,
            "external_userid": [
                _legacy._normalized_text(item.get("external_userid"))
                for item in items
                if _legacy._normalized_text(item.get("external_userid"))
            ],
            **task_payload,
        }
        try:
            # Keep the monkeypatch seam on marketing_automation.service.dispatch_wecom_task.
            wecom_result = _legacy.dispatch_wecom_task("private_message", "create_private_message_task", request_payload)
            outbound_task_ids.append(int(wecom_result["task_id"]))
            task_results.append(_legacy.user_ops_page_service._build_sender_success_result(sender_userid, items, wecom_result))
        except (_legacy.WeComClientError, AttributeError) as exc:
            task_results.append(_legacy.user_ops_page_service._build_sender_failure_result(sender_userid, items, exc))

    sent_count = sum(
        int(item.get("target_count") or 0) for item in task_results if _legacy._normalized_text(item.get("status")) != "failed"
    )
    status = _legacy.user_ops_page_service._derive_record_status(task_results, eligible_count=int(plan["eligible_count"]))
    record_id = _legacy.user_ops_page_service._insert_send_record(
        outbound_task_ids=outbound_task_ids,
        task_results=task_results,
        selected_count=int(plan["matched_count"]),
        eligible_count=int(plan["eligible_count"]),
        sent_count=sent_count,
        skipped_count=int(plan["skipped_count"]),
        skipped_reasons=dict(plan["skipped_by_reason"]),
        include_do_not_disturb=False,
        content_preview=content_preview,
        image_count=image_count,
        sender_userids=sender_userids,
        filter_snapshot={
            "selection_mode": "marketing_pool",
            "pool_key": normalized_pool_key,
            "pool_label": _legacy._pool_label(normalized_pool_key),
            "owner_userid": normalized_owner_userid,
        },
        operator=_legacy._normalized_text(operator) or "openclaw_pool_send",
        status=status,
    )
    result.update(
        {
            "record_id": int(record_id),
            "sent_count": int(sent_count),
            "executed": True,
            "task_results": task_results,
            "status": status,
        }
    )
    return result


def trigger_openclaw_focus_message_webhook(
    *,
    external_userid: str,
    recent_message_limit: int = 10,
) -> dict[str, Any]:
    """Internal automation message-dispatch owner for focus-webhook triggering."""

    normalized_external_userid = _legacy._normalized_text(external_userid)
    if not normalized_external_userid:
        return {"ok": False, "sent": False, "reason": "missing_external_userid"}
    marketing_profile = _legacy.get_openclaw_customer_marketing_profile(
        external_userid=normalized_external_userid,
        recent_message_limit=max(1, min(int(recent_message_limit), 20)),
    )
    marketing_state = dict(marketing_profile.get("marketing_state") or {})
    owner_userid = (
        _legacy._normalized_text((marketing_profile.get("owner") or {}).get("owner_userid"))
        or _legacy.DEFAULT_AUTOMATION_OWNER_USERID
    )
    pool_key = _legacy._normalized_text(marketing_state.get("pool_key"))
    if pool_key not in _legacy._FOCUS_POOL_KEYS:
        return {"ok": False, "sent": False, "reason": "pool_not_focus_followup", "pool_key": pool_key}
    payload = _legacy._build_openclaw_focus_message_webhook_payload(
        external_userid=normalized_external_userid,
        recent_message_limit=recent_message_limit,
    )
    delivery_result = _legacy.send_outbound_webhook(
        event_type=_legacy.EVENT_OPENCLAW_FOCUS_MESSAGE,
        payload=payload,
        source_key="external_userid",
        source_id=normalized_external_userid,
    )
    delivery = dict(delivery_result.get("delivery") or {})
    return {
        "ok": bool(delivery_result.get("ok")),
        "sent": bool(delivery_result.get("sent")),
        "external_userid": normalized_external_userid,
        "pool_key": pool_key,
        "owner_userid": owner_userid,
        "status_code": delivery.get("response_status_code"),
        "reason": _legacy._normalized_text(delivery_result.get("reason")),
        "error": _legacy._normalized_text(delivery_result.get("reason")),
        "delivery": delivery,
        "payload": payload,
    }


def process_inbound_messages_for_openclaw(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """Internal automation message-dispatch owner for inbound-triggered focus routing."""

    latest_by_external_userid: dict[str, dict[str, Any]] = {}
    for item in messages:
        normalized_external_userid = _legacy._normalized_text(item.get("external_userid"))
        if not normalized_external_userid:
            continue
        if _legacy._normalized_text(item.get("chat_type")) != "private":
            continue
        if _legacy._normalized_text(item.get("sender")) != normalized_external_userid:
            continue
        previous = latest_by_external_userid.get(normalized_external_userid)
        if previous and _legacy._normalized_text(previous.get("send_time")) >= _legacy._normalized_text(item.get("send_time")):
            continue
        latest_by_external_userid[normalized_external_userid] = dict(item)
    automation_scope_userids: set[str] = set()
    if latest_by_external_userid:
        from ..automation_conversion import repo as automation_repo

        automation_scope_userids = {
            _legacy._normalized_text(item)
            for item in automation_repo.list_active_automation_external_contact_ids(sorted(latest_by_external_userid.keys()))
            if _legacy._normalized_text(item)
        }
    results = [
        trigger_openclaw_focus_message_webhook(external_userid=external_userid)
        for external_userid in sorted(latest_by_external_userid.keys())
        if external_userid not in automation_scope_userids
    ]
    return {
        "processed_count": len(latest_by_external_userid) - len(automation_scope_userids),
        "sent_count": sum(1 for item in results if item.get("sent")),
        "skipped_automation_scope_count": len(automation_scope_userids),
        "results": results,
    }


__all__ = [
    "process_inbound_messages_for_openclaw",
    "send_pool_private_message",
    "trigger_openclaw_focus_message_webhook",
]
