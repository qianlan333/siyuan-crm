from __future__ import annotations

import time
from datetime import datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests
from flask import current_app

from ...db import get_db
from ...infra.settings import DEFAULT_LAOHUANG_CHAT_WEBHOOK_URL, get_setting
from ...wecom_client import WeComClientError
from ..admin_console.customer_profile_service import get_customer_messages_payload
from ..tasks.service import dispatch_wecom_task
from ..user_ops import page_service as user_ops_page_service
from . import repo
from .workflow_service import send_text_via_bazhuayu_webhook

DEFAULT_LAOHUANG_CHAT_TIMEOUT_SECONDS = 10
DEFAULT_LAOHUANG_CHAT_SEND_CHANNEL = "private_message"
DEFAULT_OWNER_STAFF_ID = "HuangYouCan"

LAOHUANG_FINAL_FAILURE_STATUSES = {"user_not_found", "llm_failed"}
LAOHUANG_REVIEWABLE_STATUSES = {"callback_success", "send_success", "send_failed"}
LAOHUANG_STATUS_LABELS = {
    "created": "已创建",
    "accepted": "已受理",
    "duplicate": "重复受理",
    "callback_success": "已生成待处理",
    "callback_failed": "回调失败",
    "send_success": "已推企微",
    "send_failed": "企微推送失败",
    "user_not_found": "用户未找到",
    "llm_failed": "生成失败",
}


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return _normalized_text(value).lower() in {"1", "true", "yes", "y", "on"}


def _iso_now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _setting_text(key: str, *, default: str = "") -> str:
    stored = get_setting(key)
    if stored is not None:
        return _normalized_text(stored)
    configured = _normalized_text(current_app.config.get(key))
    return configured if configured else default


def _setting_bool(key: str, *, default: bool = False) -> bool:
    raw_value = _setting_text(key)
    if raw_value == "":
        return bool(default)
    return _normalize_bool(raw_value)


def _setting_int(key: str, *, default: int, minimum: int = 1, maximum: int = 300) -> int:
    raw_value = _setting_text(key)
    try:
        value = int(raw_value or default)
    except (TypeError, ValueError):
        value = int(default)
    return max(int(minimum), min(int(value), int(maximum)))


def laohuang_chat_enabled() -> bool:
    return _setting_bool("LAOHUANG_CHAT_ENABLED", default=False)


def _laohuang_webhook_url() -> str:
    return _setting_text("LAOHUANG_CHAT_WEBHOOK_URL", default=DEFAULT_LAOHUANG_CHAT_WEBHOOK_URL) or DEFAULT_LAOHUANG_CHAT_WEBHOOK_URL


def _laohuang_webhook_token() -> str:
    return _setting_text("LAOHUANG_CHAT_WEBHOOK_TOKEN", default="")


def _laohuang_webhook_url_with_token() -> str:
    target_url = _laohuang_webhook_url()
    token = _laohuang_webhook_token()
    if not token:
        return target_url
    parts = urlsplit(target_url)
    query_items = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key != "token"]
    query_items.append(("token", token))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query_items), parts.fragment))


def _laohuang_timeout_seconds() -> int:
    return _setting_int(
        "LAOHUANG_CHAT_TIMEOUT_SECONDS",
        default=DEFAULT_LAOHUANG_CHAT_TIMEOUT_SECONDS,
        minimum=1,
        maximum=120,
    )


def _laohuang_send_channel() -> str:
    return _setting_text("LAOHUANG_CHAT_SEND_CHANNEL", default=DEFAULT_LAOHUANG_CHAT_SEND_CHANNEL) or DEFAULT_LAOHUANG_CHAT_SEND_CHANNEL


def _reply_monitor_config_payload() -> dict[str, Any]:
    row = repo.get_reply_monitor_config() or {}
    if not row:
        return {
            "enabled": False,
            "last_capture_cursor": 0,
            "last_capture_at": "",
            "last_capture_status": "",
            "last_capture_summary_json": {},
            "last_dispatch_at": "",
            "last_dispatch_status": "",
            "last_dispatch_summary_json": {},
            "last_error": "",
            "quiet_hours_start": "23:00",
            "quiet_hours_end": "09:00",
            "dispatch_interval_seconds": 30,
        }
    return repo.deserialize_reply_monitor_config_row(row)


def _save_reply_monitor_dispatch_status(
    *,
    status: str,
    summary: dict[str, Any],
    last_error: str = "",
    last_dispatch_at: str = "",
) -> None:
    current = _reply_monitor_config_payload()
    repo.save_reply_monitor_config(
        {
            **current,
            "last_dispatch_at": last_dispatch_at or current.get("last_dispatch_at") or "",
            "last_dispatch_status": _normalized_text(status),
            "last_dispatch_summary_json": dict(summary or {}),
            "last_error": _normalized_text(last_error),
        }
    )


def _queue_message_ids(queue_item: dict[str, Any]) -> list[int]:
    return sorted({int(item) for item in (queue_item.get("message_ids") or []) if str(item).isdigit()})


def _external_message_id(*, queue_id: int, last_message_id: int) -> str:
    return f"ai-crm:reply-monitor:{int(queue_id)}:{int(last_message_id)}"


def _external_session_id(external_contact_id: str) -> str:
    return f"ai-crm:{_normalized_text(external_contact_id)}"


def _laohuang_messages(messages_payload: dict[str, Any], *, external_contact_id: str) -> list[dict[str, str]]:
    normalized_external_contact_id = _normalized_text(external_contact_id)
    result: list[dict[str, str]] = []
    for item in list(messages_payload.get("messages") or [])[-20:]:
        content = _normalized_text(item.get("content"))
        if not content:
            continue
        sender = _normalized_text(item.get("sender"))
        result.append(
            {
                "role": "user" if sender == normalized_external_contact_id else "assistant",
                "content": content,
            }
        )
    return result


def _build_request_payload(
    *,
    queue_item: dict[str, Any],
    member: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    queue_id = int(queue_item["id"])
    message_ids = _queue_message_ids(queue_item)
    if not message_ids:
        raise ValueError("reply_monitor_message_ids_empty")
    external_contact_id = _normalized_text(member.get("external_contact_id")) or _normalized_text(queue_item.get("external_userid"))
    if not external_contact_id:
        raise ValueError("external_contact_id is required")
    phone = _normalized_text(member.get("phone"))
    owner_userid = _normalized_text(queue_item.get("owner_userid")) or _normalized_text(member.get("owner_staff_id")) or DEFAULT_OWNER_STAFF_ID
    messages_payload = get_customer_messages_payload(external_userid=external_contact_id, mobile=phone, limit=20)
    resolved_phone = phone or _normalized_text(messages_payload.get("mobile"))
    last_message_id = max(message_ids)
    meta = {
        "queue_id": queue_id,
        "member_id": int(member.get("id") or 0),
        "external_contact_id": external_contact_id,
        "owner_userid": owner_userid,
    }
    request_payload = {
        "phone": resolved_phone,
        "messages": _laohuang_messages(messages_payload, external_contact_id=external_contact_id),
        "external_message_id": _external_message_id(queue_id=queue_id, last_message_id=last_message_id),
        "external_session_id": _external_session_id(external_contact_id),
        "source": "ai-crm",
        "meta": meta,
    }
    return request_payload, messages_payload


def _serialize_job(row: dict[str, Any] | None) -> dict[str, Any]:
    return repo.deserialize_laohuang_chat_job_row(dict(row or {})) if row else {}


def _review_output_id(job_id: int) -> str:
    return f"lhjob-{int(job_id)}"


def _job_id_from_review_output_id(output_id: str) -> int:
    normalized = _normalized_text(output_id)
    if normalized.startswith("lhjob-"):
        normalized = normalized.removeprefix("lhjob-")
    if not normalized.isdigit():
        raise LookupError("未找到对应老黄 AI 回复")
    return int(normalized)


def _review_row_from_job(row: dict[str, Any]) -> dict[str, Any]:
    job = _serialize_job(row)
    job_id = int(job.get("id") or 0)
    status = _normalized_text(job.get("status"))
    callback_payload = job.get("callback_payload_json") if isinstance(job.get("callback_payload_json"), dict) else {}
    request_payload = job.get("request_payload_json") if isinstance(job.get("request_payload_json"), dict) else {}
    meta = callback_payload.get("meta") if isinstance(callback_payload.get("meta"), dict) else {}
    if not meta:
        meta = request_payload.get("meta") if isinstance(request_payload.get("meta"), dict) else {}
    owner_userid = _normalized_text(meta.get("owner_userid"))
    reply_text = _normalized_text(job.get("reply_text"))
    send_record_id = int(job.get("send_record_id") or 0)
    return {
        "output_id": _review_output_id(job_id),
        "job_id": job_id,
        "request_id": _normalized_text(job.get("external_message_id")),
        "external_message_id": _normalized_text(job.get("external_message_id")),
        "external_session_id": _normalized_text(job.get("external_session_id")),
        "external_contact_id": _normalized_text(job.get("external_contact_id")),
        "phone": _normalized_text(job.get("phone")),
        "agent_code": "laohuang_chat",
        "output_type": "laohuang_chat_reply",
        "rendered_output_text": reply_text,
        "rendered_content_preview": reply_text[:120],
        "reason": _normalized_text(job.get("error_message")),
        "outcome_status": status,
        "outcome_status_label": LAOHUANG_STATUS_LABELS.get(status, status or "未闭环"),
        "review_note": _normalized_text(job.get("error_message")),
        "reviewed_at": _normalized_text(job.get("finished_at")),
        "created_at": _normalized_text(job.get("updated_at") or job.get("created_at")),
        "is_reviewable": status in LAOHUANG_REVIEWABLE_STATUSES,
        "owner_userid": owner_userid,
        "send_record_id": send_record_id,
        "laohuang_task_id": _normalized_text(job.get("laohuang_task_id")),
    }


def list_recent_laohuang_review_outputs(*, limit: int = 20) -> dict[str, Any]:
    safe_limit = max(1, min(50, int(limit or 20)))
    rows = repo.list_laohuang_chat_jobs_for_review(limit=safe_limit)
    items = [_review_row_from_job(row) for row in rows]
    return {
        "rows": items,
        "total": len(items),
        "limit": safe_limit,
        "source": "laohuang_chat_job",
    }


def _get_review_job(output_id: str) -> dict[str, Any]:
    job_id = _job_id_from_review_output_id(output_id)
    row = repo.get_laohuang_chat_job(job_id)
    if not row:
        raise LookupError("未找到对应老黄 AI 回复")
    job = _serialize_job(row)
    if not _normalized_text(job.get("reply_text")):
        raise ValueError("老黄 AI 回复内容为空")
    return job


def _existing_queue_id(value: Any) -> int | None:
    try:
        queue_id = int(value or 0)
    except (TypeError, ValueError):
        return None
    if queue_id <= 0:
        return None
    return queue_id if repo.get_reply_monitor_queue_item(queue_id) else None


def _existing_member_id(value: Any) -> int | None:
    try:
        member_id = int(value or 0)
    except (TypeError, ValueError):
        return None
    if member_id <= 0:
        return None
    return member_id if repo.get_member_by_id(member_id) else None


def _create_or_refresh_job(
    *,
    request_payload: dict[str, Any],
    send_channel: str,
) -> dict[str, Any]:
    meta = request_payload.get("meta") if isinstance(request_payload.get("meta"), dict) else {}
    existing = repo.get_laohuang_chat_job_by_external_message_id(_normalized_text(request_payload.get("external_message_id")))
    payload = {
        "queue_id": int(meta.get("queue_id") or 0) or None,
        "member_id": int(meta.get("member_id") or 0) or None,
        "external_contact_id": _normalized_text(meta.get("external_contact_id")),
        "phone": _normalized_text(request_payload.get("phone")),
        "external_message_id": _normalized_text(request_payload.get("external_message_id")),
        "external_session_id": _normalized_text(request_payload.get("external_session_id")),
        "request_payload_json": request_payload,
        "status": "created",
        "send_channel": send_channel,
    }
    if existing:
        return repo.update_laohuang_chat_job(int(existing["id"]), payload)
    return repo.insert_laohuang_chat_job(payload)


def _update_reply_monitor_queue_after_laohuang(
    queue_item: dict[str, Any],
    *,
    member_id: int | None,
    status: str,
    last_dispatch_at: str,
    error_message: str = "",
    payload_snapshot: dict[str, Any] | None = None,
) -> None:
    repo.update_reply_monitor_queue_item(
        int(queue_item["id"]),
        {
            "member_id": member_id,
            "external_userid": queue_item.get("external_userid"),
            "owner_userid": queue_item.get("owner_userid"),
            "status": status,
            "message_ids_json": queue_item.get("message_ids") or [],
            "message_count": int(queue_item.get("message_count") or 0),
            "first_inbound_at": queue_item.get("first_inbound_at"),
            "last_inbound_at": queue_item.get("last_inbound_at"),
            "not_before": queue_item.get("not_before"),
            "last_dispatch_at": last_dispatch_at,
            "error_message": error_message,
            "payload_snapshot_json": dict(payload_snapshot or {}),
        },
    )


def dispatch_reply_monitor_queue_item(
    queue_item: dict[str, Any],
    *,
    operator_id: str = "",
    operator_type: str = "system",
) -> dict[str, Any]:
    now_text = _iso_now()
    queue_id = int(queue_item["id"])
    member = (
        repo.get_member_by_id(int(queue_item.get("member_id") or 0))
        if int(queue_item.get("member_id") or 0) > 0
        else repo.get_member_by_external_contact_id(queue_item.get("external_userid") or "")
    )
    if not member:
        _update_reply_monitor_queue_after_laohuang(
            queue_item,
            member_id=queue_item.get("member_id") or None,
            status="failed",
            last_dispatch_at="",
            error_message="automation_member_not_found",
        )
        summary = {"processed_count": 1, "success_count": 0, "failed_count": 1, "queue_id": queue_id}
        _save_reply_monitor_dispatch_status(status="failed", summary=summary, last_error="automation_member_not_found")
        get_db().commit()
        return {"ok": False, "status": "failed", "error": "automation_member_not_found", "summary": summary}

    send_channel = _laohuang_send_channel()
    from ...infra.http_client import OutboundHttpError, get_outbound_client

    try:
        request_payload, messages_payload = _build_request_payload(queue_item=queue_item, member=dict(member))
        job = _create_or_refresh_job(request_payload=request_payload, send_channel=send_channel)
        started = time.perf_counter()
        client = get_outbound_client(
            "laohuang_chat",
            timeout=float(_laohuang_timeout_seconds()),
            retry_max=2,
        )
        try:
            response = client.post(
                _laohuang_webhook_url_with_token(),
                json=request_payload,
            )
        except OutboundHttpError as exc:
            # Surface as the existing RequestException so the outer handler
            # below keeps doing its bookkeeping unchanged. Preserve the
            # upstream message verbatim.
            original_message = str(exc.cause) if exc.cause else str(exc)
            raise requests.RequestException(original_message) from exc
        latency_ms = int((time.perf_counter() - started) * 1000)
        response_text = response.text or ""
        try:
            accepted_payload = response.json() if response_text else {}
        except ValueError:
            accepted_payload = {"raw_body": response_text}
        if not response.ok:
            raise requests.RequestException(response_text.strip() or f"http_status_{int(response.status_code)}")
        accepted_status = _normalized_text(accepted_payload.get("status"))
        if not bool(accepted_payload.get("ok")) or accepted_status not in {"accepted", "duplicate"}:
            raise requests.RequestException(response_text.strip() or f"unexpected_status:{accepted_status}")
        laohuang_task_id = _normalized_text(accepted_payload.get("task_id"))
        updated_job = repo.update_laohuang_chat_job(
            int(job["id"]),
            {
                "laohuang_task_id": laohuang_task_id,
                "accepted_payload_json": {
                    **accepted_payload,
                    "_http_status": int(response.status_code),
                    "_latency_ms": latency_ms,
                },
                "status": accepted_status,
                "error_code": "",
                "error_message": "",
            },
        )
        _update_reply_monitor_queue_after_laohuang(
            queue_item,
            member_id=int(member.get("id") or 0) or None,
            status="dispatched",
            last_dispatch_at=now_text,
            payload_snapshot={
                "bridge": "laohuang_chat",
                "job_id": int(updated_job.get("id") or job["id"]),
                "task_id": laohuang_task_id,
                "external_message_id": request_payload["external_message_id"],
                "messages_count": len(request_payload.get("messages") or []),
                "customer_messages_count": int(messages_payload.get("count") or 0),
            },
        )
        summary = {
            "processed_count": 1,
            "success_count": 1,
            "failed_count": 0,
            "queue_id": queue_id,
            "job_id": int(updated_job.get("id") or job["id"]),
            "laohuang_status": accepted_status,
            "task_id": laohuang_task_id,
            "external_message_id": request_payload["external_message_id"],
        }
        _save_reply_monitor_dispatch_status(status="success", summary=summary, last_error="", last_dispatch_at=now_text)
        get_db().commit()
        return {
            "ok": True,
            "status": "success",
            "summary": summary,
            "laohuang_chat": {
                "status": accepted_status,
                "task_id": laohuang_task_id,
                "job": _serialize_job(updated_job),
            },
        }
    except Exception as exc:
        current_app.logger.exception("laohuang chat bridge dispatch failed")
        error_message = _normalized_text(str(exc)) or exc.__class__.__name__
        existing_external_message_id = ""
        try:
            message_ids = _queue_message_ids(queue_item)
            if message_ids:
                existing_external_message_id = _external_message_id(queue_id=queue_id, last_message_id=max(message_ids))
        except Exception:
            existing_external_message_id = ""
        existing_job = repo.get_laohuang_chat_job_by_external_message_id(existing_external_message_id) if existing_external_message_id else None
        if existing_job:
            repo.update_laohuang_chat_job(
                int(existing_job["id"]),
                {
                    "status": "send_failed" if "dispatch" in error_message else "created",
                    "error_code": "laohuang_request_failed",
                    "error_message": error_message,
                },
            )
        _update_reply_monitor_queue_after_laohuang(
            queue_item,
            member_id=int(member.get("id") or 0) if member else queue_item.get("member_id") or None,
            status="failed",
            last_dispatch_at=now_text,
            error_message=error_message,
        )
        summary = {"processed_count": 1, "success_count": 0, "failed_count": 1, "queue_id": queue_id}
        _save_reply_monitor_dispatch_status(status="failed", summary=summary, last_error=error_message, last_dispatch_at=now_text)
        get_db().commit()
        return {"ok": False, "status": "failed", "error": error_message, "summary": summary}


def _job_from_callback(payload: dict[str, Any]) -> dict[str, Any]:
    external_message_id = _normalized_text(payload.get("external_message_id"))
    task_id = _normalized_text(payload.get("task_id"))
    job = repo.get_laohuang_chat_job_by_external_message_id(external_message_id) if external_message_id else None
    if not job and task_id:
        job = repo.get_laohuang_chat_job_by_task_id(task_id)
    if job:
        return job
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    return repo.insert_laohuang_chat_job(
        {
            "queue_id": _existing_queue_id(meta.get("queue_id")),
            "member_id": _existing_member_id(meta.get("member_id")),
            "external_contact_id": _normalized_text(meta.get("external_contact_id")),
            "phone": _normalized_text(payload.get("phone")),
            "external_message_id": external_message_id,
            "external_session_id": _normalized_text(payload.get("external_session_id")),
            "laohuang_task_id": task_id,
            "callback_payload_json": payload,
            "status": "created",
            "send_channel": _laohuang_send_channel(),
        }
    )


def _send_reply(
    job: dict[str, Any],
    callback_payload: dict[str, Any],
    *,
    source: str = "laohuang_chat_manual_wecom",
    operator: str = "crm_console",
) -> dict[str, Any]:
    serialized_job = _serialize_job(job)
    meta = callback_payload.get("meta") if isinstance(callback_payload.get("meta"), dict) else {}
    external_contact_id = (
        _normalized_text(meta.get("external_contact_id"))
        or _normalized_text(serialized_job.get("external_contact_id"))
        or _normalized_text(str(callback_payload.get("external_session_id") or "").removeprefix("ai-crm:"))
    )
    owner_userid = _normalized_text(meta.get("owner_userid")) or DEFAULT_OWNER_STAFF_ID
    phone = _normalized_text(callback_payload.get("phone")) or _normalized_text(serialized_job.get("phone"))
    reply_text = _normalized_text(callback_payload.get("reply"))
    send_channel = _normalized_text(serialized_job.get("send_channel")) or _laohuang_send_channel()
    if send_channel != "private_message":
        return {
            "ok": False,
            "status": "send_failed",
            "error": f"unsupported_send_channel:{send_channel}",
            "send_channel": send_channel,
        }
    if not external_contact_id:
        return {"ok": False, "status": "send_failed", "error": "external_contact_id is required", "send_channel": send_channel}
    if not reply_text:
        return {"ok": False, "status": "send_failed", "error": "reply is required", "send_channel": send_channel}

    task_payload, content_preview, image_count = user_ops_page_service._build_private_message_payload({"content": reply_text})
    target_items = [
        {
            "id": int(serialized_job.get("member_id") or 0),
            "external_userid": external_contact_id,
            "owner_userid": owner_userid,
            "owner_display_name": owner_userid,
            "mobile": phone,
        }
    ]
    request_payload = {
        "sender": owner_userid,
        "external_userid": [external_contact_id],
        **task_payload,
    }
    outbound_task_ids: list[int] = []
    task_results: list[dict[str, Any]] = []
    fail_external_userids: list[str] = []
    try:
        wecom_result = dispatch_wecom_task("private_message", "create_private_message_task", request_payload)
        fail_external_userids = [
            _normalized_text(item)
            for item in (wecom_result.get("wecom_result") or {}).get("fail_list", [])
            if _normalized_text(item)
        ]
        outbound_task_ids.append(int(wecom_result["task_id"]))
        task_results.append(user_ops_page_service._build_sender_success_result(owner_userid, target_items, wecom_result))
    except (WeComClientError, AttributeError, RuntimeError, ValueError) as exc:
        task_results.append(user_ops_page_service._build_sender_failure_result(owner_userid, target_items, exc))

    if fail_external_userids:
        sent_count = max(0, len(target_items) - len(set(fail_external_userids)))
        status = "partial_failed" if sent_count > 0 else "failed"
    else:
        sent_count = sum(int(item.get("target_count") or 0) for item in task_results if _normalized_text(item.get("status")) != "failed")
        status = user_ops_page_service._derive_record_status(task_results, eligible_count=len(target_items))
    record_id = user_ops_page_service._insert_send_record(
        outbound_task_ids=outbound_task_ids,
        task_results=task_results,
        selected_count=len(target_items),
        eligible_count=len(target_items),
        sent_count=sent_count,
        skipped_count=0,
        skipped_reasons={},
        include_do_not_disturb=False,
        content_preview=content_preview,
        image_count=image_count,
        sender_userids=[owner_userid],
        filter_snapshot={
            "source": _normalized_text(source) or "laohuang_chat_manual_wecom",
            "job_id": int(serialized_job.get("id") or 0),
            "external_message_id": _normalized_text(serialized_job.get("external_message_id")),
        },
        operator=_normalized_text(operator) or "crm_console",
        status=status,
    )
    return {
        "ok": status != "failed",
        "status": "send_success" if status != "failed" else "send_failed",
        "record_status": status,
        "send_record_id": int(record_id),
        "request_payload": request_payload,
        "task_ids": outbound_task_ids,
        "task_results": task_results,
        "sent_count": sent_count,
        "fail_external_userids": fail_external_userids,
        "send_channel": send_channel,
        "error": (
            _normalized_text(task_results[0].get("error_message"))
            if status == "failed" and task_results
            else ""
        ),
    }


def send_laohuang_review_output_via_webhook(output_id: str, *, operator_id: str = "") -> dict[str, Any]:
    job = _get_review_job(output_id)
    result = send_text_via_bazhuayu_webhook(
        userid=_normalized_text(job.get("external_contact_id")),
        text=_normalized_text(job.get("reply_text")),
        operator_id=operator_id,
        result_id_key="job_id",
        result_id_value=int(job.get("id") or 0),
    )
    send_result = dict(job.get("send_result_json") or {})
    send_result["webhook"] = result
    send_result["webhook_sent_at"] = _iso_now()
    updated = repo.update_laohuang_chat_job(
        int(job["id"]),
        {
            "send_result_json": send_result,
            "error_code": "",
            "error_message": "",
        },
    )
    get_db().commit()
    return {
        "ok": True,
        "output_id": _review_output_id(int(job.get("id") or 0)),
        "job_id": int(job.get("id") or 0),
        "requested_by": _normalized_text(operator_id) or "crm_console",
        "job": _serialize_job(updated),
        **result,
    }


def send_laohuang_review_output_via_wecom(output_id: str, *, operator_id: str = "") -> dict[str, Any]:
    job = _get_review_job(output_id)
    status = _normalized_text(job.get("status"))
    if status == "send_success" and int(job.get("send_record_id") or 0) > 0:
        return {
            "ok": True,
            "status": "send_success",
            "idempotent": True,
            "output_id": _review_output_id(int(job.get("id") or 0)),
            "job_id": int(job.get("id") or 0),
            "send_record_id": int(job.get("send_record_id") or 0),
            "job": job,
        }
    callback_payload = job.get("callback_payload_json") if isinstance(job.get("callback_payload_json"), dict) else {}
    if not callback_payload:
        callback_payload = {
            "reply": _normalized_text(job.get("reply_text")),
            "phone": _normalized_text(job.get("phone")),
            "external_session_id": _normalized_text(job.get("external_session_id")),
            "meta": {
                "external_contact_id": _normalized_text(job.get("external_contact_id")),
            },
        }
    send_result = _send_reply(
        job,
        callback_payload,
        source="laohuang_chat_manual_wecom",
        operator=_normalized_text(operator_id) or "crm_console",
    )
    final_status = "send_success" if send_result.get("ok") else "send_failed"
    updated = repo.update_laohuang_chat_job(
        int(job["id"]),
        {
            "status": final_status,
            "send_record_id": int(send_result.get("send_record_id") or 0) or None,
            "send_result_json": send_result,
            "error_code": "" if send_result.get("ok") else "send_failed",
            "error_message": "" if send_result.get("ok") else _normalized_text(send_result.get("error")),
        },
    )
    get_db().commit()
    return {
        "ok": bool(send_result.get("ok")),
        "status": final_status,
        "output_id": _review_output_id(int(job.get("id") or 0)),
        "job_id": int(job.get("id") or 0),
        "job": _serialize_job(updated),
        "send_result": send_result,
    }


def handle_laohuang_chat_result_callback(payload: dict[str, Any]) -> dict[str, Any]:
    callback_payload = dict(payload or {})
    if _normalized_text(callback_payload.get("source")) != "ai-crm":
        return {"ok": False, "status": "rejected", "error": "invalid_source"}
    callback_status = _normalized_text(callback_payload.get("status"))
    if not callback_status:
        return {"ok": False, "status": "rejected", "error": "missing_status"}
    job = _job_from_callback(callback_payload)
    if not job:
        return {"ok": False, "status": "rejected", "error": "job_not_found"}
    job_id = int(job["id"])
    if callback_status in LAOHUANG_FINAL_FAILURE_STATUSES:
        updated = repo.update_laohuang_chat_job(
            job_id,
            {
                "laohuang_task_id": _normalized_text(callback_payload.get("task_id")) or _normalized_text(job.get("laohuang_task_id")),
                "callback_payload_json": callback_payload,
                "status": callback_status,
                "reply_text": _normalized_text(callback_payload.get("reply")),
                "error_code": _normalized_text(callback_payload.get("error_code")) or callback_status,
                "error_message": _normalized_text(callback_payload.get("error_message")),
                "finished_at": _iso_now(),
            },
        )
        get_db().commit()
        return {"ok": True, "status": callback_status, "job": _serialize_job(updated)}
    if callback_status != "success":
        updated = repo.update_laohuang_chat_job(
            job_id,
            {
                "laohuang_task_id": _normalized_text(callback_payload.get("task_id")) or _normalized_text(job.get("laohuang_task_id")),
                "callback_payload_json": callback_payload,
                "status": "callback_failed",
                "reply_text": _normalized_text(callback_payload.get("reply")),
                "error_code": _normalized_text(callback_payload.get("error_code")) or callback_status,
                "error_message": _normalized_text(callback_payload.get("error_message")) or f"unsupported_status:{callback_status}",
                "finished_at": _iso_now(),
            },
        )
        get_db().commit()
        return {"ok": True, "status": "callback_failed", "job": _serialize_job(updated)}

    serialized_before = _serialize_job(job)
    if _normalized_text(serialized_before.get("status")) in {"callback_success", "send_success"}:
        return {"ok": True, "status": _normalized_text(serialized_before.get("status")), "idempotent": True, "job": serialized_before}

    updated = repo.update_laohuang_chat_job(
        job_id,
        {
            "laohuang_task_id": _normalized_text(callback_payload.get("task_id")) or _normalized_text(job.get("laohuang_task_id")),
            "callback_payload_json": callback_payload,
            "status": "callback_success",
            "reply_text": _normalized_text(callback_payload.get("reply")),
            "error_code": "",
            "error_message": "",
            "finished_at": _iso_now(),
        },
    )
    get_db().commit()
    return {
        "ok": True,
        "status": "callback_success",
        "job": _serialize_job(updated),
    }


def laohuang_request_example() -> dict[str, Any]:
    return {
        "phone": "13800138000",
        "messages": [
            {"role": "user", "content": "用户消息"},
            {"role": "assistant", "content": "历史 AI/员工回复"},
            {"role": "user", "content": "用户最新消息"},
        ],
        "external_message_id": "ai-crm:reply-monitor:123:456",
        "external_session_id": "ai-crm:wm_xxx",
        "source": "ai-crm",
        "meta": {
            "queue_id": 123,
            "member_id": 456,
            "external_contact_id": "wm_xxx",
            "owner_userid": "HuangYouCan",
        },
    }


def laohuang_callback_example() -> dict[str, Any]:
    return {
        "task_id": "laohuang-task-id",
        "source": "ai-crm",
        "external_session_id": "ai-crm:wm_xxx",
        "external_message_id": "ai-crm:reply-monitor:123:456",
        "status": "success",
        "phone": "13800138000",
        "user_id": "laohuang-user-id",
        "reply": "老黄 AI 生成的最终回复",
        "error_code": "",
        "error_message": "",
        "meta": {
            "queue_id": 123,
            "member_id": 456,
            "external_contact_id": "wm_xxx",
            "owner_userid": "HuangYouCan",
        },
    }
