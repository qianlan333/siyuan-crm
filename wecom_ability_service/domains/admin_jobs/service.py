from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from flask import current_app

from ...application.automation_engine.commands import (
    RetryOutboundWebhookDeliveryCommand,
    RunDueOutboundWebhookRetriesCommand,
)
from ...application.automation_engine.dto import (
    OutboundWebhookListQueryDTO,
    OutboundWebhookRetryBatchCommandDTO,
    OutboundWebhookRetryCommandDTO,
)
from ...application.automation_engine.queries import (
    GetOutboundWebhookDeliveryCountsQuery,
    ListOutboundWebhookDeliveriesQuery,
)
from ...application.user_ops.commands import RunDueUserOpsDeferredJobsCommand
from ...application.user_ops.dto import RunDueUserOpsDeferredJobsCommandDTO
from ...application.user_ops.queries import GetUserOpsDeferredJobCountsQuery
from ...http.sync_jobs import run_archive_health_check, run_manual_archive_sync
from ...infra.settings import get_setting
from ...services import get_message_batch
from ...wecom_callback import get_callback_config
from ..admin_config import repo as admin_config_repo
from ..archive.service import ack_message_batch, get_last_sync_run
from . import repo

TARGET_JOBS_ACTION = "jobs_console_action"

JOB_TABS = (
    {"key": "overview", "label": "概览"},
    {"key": "archive", "label": "聊天同步"},
    {"key": "callbacks", "label": "回调状态"},
    {"key": "batches", "label": "消息批次"},
    {"key": "deferred", "label": "待处理作业"},
    {"key": "webhooks", "label": "Webhook 投递"},
    {"key": "broadcast_queue", "label": "群发队列", "href": "/admin/broadcast-jobs"},
)


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _normalized_int(value: Any, *, default: int, minimum: int = 1, maximum: int = 200) -> int:
    try:
        parsed = int(value if value not in (None, "") else default)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _normalized_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _normalized_text(value).lower() in {"1", "true", "yes", "y", "on"}


def _operator(value: Any) -> str:
    return _normalized_text(value) or "crm_console"


def _status_tone(status: str) -> str:
    normalized_status = _normalized_text(status).lower()
    if normalized_status in {"success", "acked", "enabled", "healthy"}:
        return "ok"
    if normalized_status in {"failed", "disabled", "error"}:
        return "danger"
    if normalized_status in {"pending", "running", "processing", "conflict", "skipped"}:
        return "warn"
    return "neutral"


def _status_label(status: Any) -> str:
    mapping = {
        "success": "成功",
        "failed": "失败",
        "pending": "待处理",
        "processing": "处理中",
        "running": "运行中",
        "conflict": "冲突",
        "skipped": "已跳过",
        "acked": "已确认",
        "enabled": "已开启",
        "disabled": "未开启",
        "healthy": "正常",
        "never": "暂无记录",
        "retry_scheduled": "待自动重试",
        "exhausted": "已耗尽",
    }
    normalized = _normalized_text(status).lower()
    return mapping.get(normalized, _normalized_text(status) or "-")


def _batch_status_options() -> list[str]:
    return ["", "pending", "acked"]


def _deferred_status_options() -> list[str]:
    return ["", "pending", "running", "success", "conflict", "skipped", "failed"]


def _webhook_status_options() -> list[str]:
    return ["", "pending", "success", "failed", "retry_scheduled", "exhausted"]


def _webhook_event_type_options() -> list[dict[str, str]]:
    return [
        {"value": "", "label": "全部事件"},
        {"value": "openclaw_focus_message", "label": "OpenClaw 焦点消息"},
        {"value": "questionnaire_submit", "label": "问卷提交外发"},
    ]


def _get_user_ops_deferred_job_counts_payload() -> dict[str, Any]:
    return GetUserOpsDeferredJobCountsQuery()()


def _run_user_ops_deferred_jobs_payload(limit: int) -> dict[str, Any]:
    return RunDueUserOpsDeferredJobsCommand()(RunDueUserOpsDeferredJobsCommandDTO(limit=int(limit)))


def get_outbound_webhook_delivery_counts() -> dict[str, Any]:
    return GetOutboundWebhookDeliveryCountsQuery()()


def list_outbound_webhook_deliveries(*, event_type: str = "", status: str = "", limit: int = 50) -> dict[str, Any]:
    return ListOutboundWebhookDeliveriesQuery()(
        OutboundWebhookListQueryDTO(
            event_type=_normalized_text(event_type),
            status=_normalized_text(status),
            limit=int(limit),
        )
    )


def retry_outbound_webhook_delivery(delivery_id: int) -> dict[str, Any]:
    return RetryOutboundWebhookDeliveryCommand()(
        OutboundWebhookRetryCommandDTO(delivery_id=int(delivery_id))
    )


def run_due_outbound_webhook_retries(*, limit: int = 20) -> dict[str, Any]:
    return RunDueOutboundWebhookRetriesCommand()(
        OutboundWebhookRetryBatchCommandDTO(limit=int(limit))
    )


def jobs_tabs(active_key: str) -> list[dict[str, Any]]:
    normalized_active_key = _normalized_text(active_key) or "overview"
    return [
        {
            **item,
            "active": item["key"] == normalized_active_key,
            "href": _normalized_text(item.get("href")) or f"/admin/jobs?tab={item['key']}",
        }
        for item in JOB_TABS
    ]


def _archive_sync_form_defaults() -> dict[str, str]:
    end_time = datetime.now().replace(microsecond=0)
    start_time = end_time - timedelta(hours=1)
    return {
        "start_time": start_time.strftime("%Y-%m-%d %H:%M:%S"),
        "end_time": end_time.strftime("%Y-%m-%d %H:%M:%S"),
        "owner_userid": _normalized_text(current_app.config.get("WECOM_DEFAULT_OWNER_USERID")),
        "cursor": "",
        "operator": "",
    }


def _archive_sync_request_payload(source: Any) -> dict[str, str]:
    return {
        "start_time": _normalized_text(source.get("start_time")),
        "end_time": _normalized_text(source.get("end_time")),
        "owner_userid": _normalized_text(source.get("owner_userid")) or _normalized_text(current_app.config.get("WECOM_DEFAULT_OWNER_USERID")),
        "cursor": _normalized_text(source.get("cursor")),
    }


def _callback_enabled() -> bool:
    callback_config = get_callback_config()
    return bool(callback_config.get("token") and callback_config.get("aes_key") and callback_config.get("corp_id"))


def _mcp_auth_configured() -> bool:
    return bool(_normalized_text(get_setting("MCP_BEARER_TOKEN")) or _normalized_text(current_app.config.get("MCP_BEARER_TOKEN")))


def _audit_log(
    *,
    operator: str,
    action_type: str,
    target_id: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> None:
    # Delegates to the unified entry in admin_audit. ``target_type`` stays
    # pinned to TARGET_JOBS_ACTION because callers in this module are all
    # job-bucket operations.
    from ..admin_audit import record_audit

    record_audit(
        operator=_operator(operator),
        action_type=_normalized_text(action_type),
        target_type=TARGET_JOBS_ACTION,
        target_id=_normalized_text(target_id),
        before=before or {},
        after=after or {},
    )


def _sync_row_view(row: dict[str, Any]) -> dict[str, Any]:
    status = _normalized_text(row.get("status")) or "unknown"
    return {
        **row,
        "status_label": _status_label(status),
        "status_tone": _status_tone(status),
        "finished_or_created_at": _normalized_text(row.get("finished_at")) or _normalized_text(row.get("created_at")) or "-",
    }


def _callback_row_view(row: dict[str, Any]) -> dict[str, Any]:
    status = _normalized_text(row.get("process_status")) or "pending"
    return {
        **row,
        "status_tone": _status_tone(status),
        "process_status_label": _status_label(status),
        "event_label": _normalized_text(row.get("change_type")) or _normalized_text(row.get("event_type")) or "回调事件",
    }


def _batch_row_view(row: dict[str, Any]) -> dict[str, Any]:
    status = _normalized_text(row.get("status")) or "pending"
    return {
        **row,
        "status_label": _status_label(status),
        "status_tone": _status_tone(status),
        "window_label": f"{_normalized_text(row.get('window_start'))} ~ {_normalized_text(row.get('window_end'))}",
    }


def _deferred_row_view(row: dict[str, Any]) -> dict[str, Any]:
    status = _normalized_text(row.get("status")) or "pending"
    return {
        **row,
        "status_label": _status_label(status),
        "status_tone": _status_tone(status),
    }


def _mask_target_url(value: Any) -> str:
    text = _normalized_text(value)
    if not text:
        return "-"
    if "://" not in text:
        return text[:80]
    scheme, rest = text.split("://", 1)
    host, _, path = rest.partition("/")
    path_prefix = f"/{path[:32]}" if path else ""
    return f"{scheme}://{host}{path_prefix}"


def _webhook_event_label(event_type: Any) -> str:
    mapping = {
        "openclaw_focus_message": "OpenClaw 焦点消息",
        "questionnaire_submit": "问卷提交外发",
    }
    return mapping.get(_normalized_text(event_type), _normalized_text(event_type) or "-")


def _webhook_delivery_state_label(row: dict[str, Any]) -> str:
    status = _normalized_text(row.get("status"))
    last_error = _normalized_text(row.get("last_error"))
    if last_error == "webhook_not_configured":
        return "未配置"
    if status == "retry_scheduled":
        return "待自动重试"
    if status == "exhausted":
        return "已耗尽"
    if status == "success":
        return "已成功"
    if status == "failed":
        return "发送失败"
    return _status_label(status)


def _webhook_delivery_state_tone(row: dict[str, Any]) -> str:
    status = _normalized_text(row.get("status"))
    last_error = _normalized_text(row.get("last_error"))
    if last_error == "webhook_not_configured":
        return "warn"
    if status in {"retry_scheduled"}:
        return "warn"
    if status in {"failed", "exhausted"}:
        return "danger"
    if status == "success":
        return "ok"
    return "neutral"


def _webhook_row_view(row: dict[str, Any]) -> dict[str, Any]:
    status = _normalized_text(row.get("status"))
    source_key = _normalized_text(row.get("source_key"))
    source_id = _normalized_text(row.get("source_id"))
    return {
        **row,
        "status_label": _status_label(status),
        "status_tone": _status_tone(status),
        "event_label": _webhook_event_label(row.get("event_type")),
        "target_url_masked": _mask_target_url(row.get("target_url")),
        "delivery_state_label": _webhook_delivery_state_label(row),
        "delivery_state_tone": _webhook_delivery_state_tone(row),
        "source_label": f"{source_key}:{source_id}" if source_key or source_id else "-",
        "can_retry": status in {"failed", "retry_scheduled", "exhausted"},
    }


def _build_pending_message_batches_group() -> dict[str, Any]:
    rows = [_batch_row_view(item) for item in repo.list_message_batches(status="pending", limit=5)]
    total_count = len(rows)
    return {
        "key": "pending_message_batches",
        "title": "待确认消息批次",
        "count": total_count,
        "description": "这里展示还没有确认处理的消息批次。",
        "tone": "warn" if total_count else "ok",
        "items": [
            {
                "title": f"消息批次 #{item['id']}",
                "meta": item["window_label"],
                "detail": f"消息 {int(item.get('message_count') or 0)} 条 · 状态 {_status_label(item.get('status', 'pending'))}",
            }
            for item in rows
        ],
        "empty_title": "暂无待确认批次",
        "href": "/admin/jobs?tab=batches&batch_status=pending",
    }


def _build_deferred_jobs_group() -> dict[str, Any]:
    counts = _get_user_ops_deferred_job_counts_payload()
    total_pending = int(counts.get("pending_count") or 0)
    total_failed = int(counts.get("failed_count") or 0)
    items: list[dict[str, Any]] = []
    if total_pending:
        items.append(
            {
                "title": f"{total_pending} 个待执行任务",
                "meta": "等待执行",
                "detail": "需要按计划继续处理",
            }
        )
    if total_failed:
        items.append(
            {
                "title": f"{total_failed} 个失败任务",
                "meta": "执行失败",
                "detail": "需要人工复查或重试",
            }
        )
    return {
        "key": "deferred_jobs",
        "title": "待处理作业",
        "count": total_pending + total_failed,
        "description": "这里展示待处理和失败的作业。",
        "tone": "danger" if total_failed else ("warn" if total_pending else "ok"),
        "items": items,
        "empty_title": "暂无待处理作业异常",
        "href": "/admin/jobs?tab=deferred&job_status=pending",
    }


def _build_failed_sync_group() -> dict[str, Any]:
    rows = [_sync_row_view(item) for item in repo.list_sync_runs(status="failed", limit=5)]
    return {
        "key": "failed_sync_runs",
        "title": "同步失败",
        "count": len(rows),
        "description": "这里展示最近失败的聊天同步。",
        "tone": "danger" if rows else "ok",
        "items": [
            {
                "title": f"同步任务 #{row['id']}",
                "meta": row["finished_or_created_at"],
                "detail": _normalized_text(row.get("error_message")) or "聊天同步失败",
            }
            for row in rows
        ],
        "empty_title": "最近没有同步失败",
        "href": "/admin/jobs?tab=archive&archive_status=failed",
    }


def _build_failed_callbacks_group() -> dict[str, Any]:
    rows = [_callback_row_view(item) for item in repo.list_callback_logs(process_status="failed", limit=5)]
    return {
        "key": "failed_callbacks",
        "title": "回调失败",
        "count": len(rows),
        "description": "最近失败的回调处理记录。",
        "tone": "danger" if rows else "ok",
        "items": [
            {
                "title": item["event_label"],
                "meta": _normalized_text(item.get("updated_at")) or _normalized_text(item.get("created_at")) or "暂无时间",
                "detail": _normalized_text(item.get("error_message")) or _normalized_text(item.get("external_userid")) or "回调处理失败",
            }
            for item in rows
        ],
        "empty_title": "最近没有回调失败",
        "href": "/admin/jobs?tab=callbacks&callback_status=failed",
    }


def build_jobs_runtime_snapshot(*, include_archive_health: bool = False) -> dict[str, Any]:
    last_sync_run = dict(get_last_sync_run() or {})
    snapshot = {
        "last_sync_run": _sync_row_view(last_sync_run) if last_sync_run else {},
        "sync_counts": repo.get_sync_run_counts(),
        "callback_enabled": _callback_enabled(),
        "background_async_enabled": bool(current_app.config.get("CALLBACK_ASYNC_ENABLED", True)),
        "callback_counts": repo.get_callback_counts(),
        "batch_counts": repo.get_message_batch_counts(),
        "deferred_counts": _get_user_ops_deferred_job_counts_payload(),
        "webhook_counts": get_outbound_webhook_delivery_counts(),
    }
    if include_archive_health:
        try:
            snapshot["archive_health"] = run_archive_health_check()
            snapshot["archive_health_error"] = ""
        except Exception as exc:
            snapshot["archive_health"] = {}
            snapshot["archive_health_error"] = str(exc)
    else:
        snapshot["archive_health"] = {}
        snapshot["archive_health_error"] = ""
    return snapshot


def build_jobs_dashboard_groups() -> list[dict[str, Any]]:
    return [
        _build_pending_message_batches_group(),
        _build_deferred_jobs_group(),
        _build_failed_callbacks_group(),
        _build_failed_sync_group(),
    ]


def build_jobs_payload(args: Any) -> dict[str, Any]:
    active_tab = _normalized_text(args.get("tab")) or "overview"
    valid_tabs = {item["key"] for item in JOB_TABS}
    if active_tab not in valid_tabs:
        active_tab = "overview"

    archive_filters = {
        "status": _normalized_text(args.get("archive_status")),
        "limit": _normalized_int(args.get("archive_limit"), default=20),
    }
    callback_filters = {
        "process_status": _normalized_text(args.get("callback_status")),
        "query": _normalized_text(args.get("callback_query")),
        "limit": _normalized_int(args.get("callback_limit"), default=20),
    }
    batch_filters = {
        "status": _normalized_text(args.get("batch_status")),
        "limit": _normalized_int(args.get("batch_limit"), default=20),
        "selected_batch_id": _normalized_text(args.get("batch_id")),
    }
    deferred_filters = {
        "status": _normalized_text(args.get("job_status")),
        "owner_userid": _normalized_text(args.get("owner_userid")),
        "external_userid": _normalized_text(args.get("external_userid")),
        "limit": _normalized_int(args.get("job_limit"), default=20),
    }
    webhook_filters = {
        "event_type": _normalized_text(args.get("webhook_event_type")),
        "status": _normalized_text(args.get("webhook_status")),
        "limit": _normalized_int(args.get("webhook_limit"), default=20),
    }

    runtime_snapshot = build_jobs_runtime_snapshot(include_archive_health=active_tab in {"overview", "archive"})
    last_sync_run = dict(runtime_snapshot.get("last_sync_run") or {})
    sync_counts = runtime_snapshot["sync_counts"]
    callback_counts = runtime_snapshot["callback_counts"]
    batch_counts = runtime_snapshot["batch_counts"]
    deferred_counts = runtime_snapshot["deferred_counts"]
    webhook_counts = runtime_snapshot["webhook_counts"]

    sync_runs = [_sync_row_view(item) for item in repo.list_sync_runs(status=archive_filters["status"], limit=archive_filters["limit"])]
    callback_logs = [
        _callback_row_view(item)
        for item in repo.list_callback_logs(
            process_status=callback_filters["process_status"],
            query=callback_filters["query"],
            limit=callback_filters["limit"],
        )
    ]
    batch_rows = [_batch_row_view(item) for item in repo.list_message_batches(status=batch_filters["status"], limit=batch_filters["limit"])]
    deferred_jobs = [
        _deferred_row_view(item)
        for item in repo.list_deferred_jobs(
            status=deferred_filters["status"],
            owner_userid=deferred_filters["owner_userid"],
            external_userid=deferred_filters["external_userid"],
            limit=deferred_filters["limit"],
        )
    ]
    webhook_deliveries = [
        _webhook_row_view(item)
        for item in list_outbound_webhook_deliveries(
            event_type=webhook_filters["event_type"],
            status=webhook_filters["status"],
            limit=webhook_filters["limit"],
        ).get("items", [])
    ]

    selected_batch = {}
    selected_batch_messages: list[dict[str, Any]] = []
    selected_batch_id = _normalized_text(batch_filters["selected_batch_id"])
    if selected_batch_id.isdigit():
        batch_detail = get_message_batch(int(selected_batch_id), limit=50) or {}
        selected_batch = dict(batch_detail.get("batch") or repo.get_selected_message_batch(int(selected_batch_id)) or {})
        selected_batch_messages = list(batch_detail.get("messages") or [])
        if selected_batch:
            selected_batch = {
                **_batch_row_view(selected_batch),
                "paging": batch_detail.get("paging") or {},
            }

    summary_cards = [
        {
            "label": "聊天同步",
            "value": _status_label(_normalized_text(last_sync_run.get("status")) or "never"),
            "description": (
                f"任务 #{last_sync_run.get('id') or '-'} · {_normalized_text(last_sync_run.get('finished_at')) or _normalized_text(last_sync_run.get('created_at')) or '暂无记录'}"
            ),
            "tone": _status_tone(_normalized_text(last_sync_run.get("status")) or "unknown"),
        },
        {
            "label": "回调状态",
            "value": "已开启" if _callback_enabled() else "未开启",
            "description": f"失败 {int(callback_counts.get('failed_count') or 0)} · 异步{'已开启' if bool(current_app.config.get('CALLBACK_ASYNC_ENABLED', True)) else '未开启'}",
            "tone": "ok" if _callback_enabled() else "danger",
        },
        {
            "label": "消息批次",
            "value": int(batch_counts.get("pending_count") or 0),
            "description": f"待处理 · 已确认 {int(batch_counts.get('acked_count') or 0)}",
            "tone": "warn" if int(batch_counts.get("pending_count") or 0) else "ok",
        },
        {
            "label": "待处理作业",
            "value": int(deferred_counts.get("pending_count") or 0),
            "description": f"待处理 · 失败 {int(deferred_counts.get('failed_count') or 0)}",
            "tone": "danger" if int(deferred_counts.get("failed_count") or 0) else ("warn" if int(deferred_counts.get("pending_count") or 0) else "ok"),
        },
        {
            "label": "Webhook 投递",
            "value": int(webhook_counts.get("retry_scheduled_count") or 0) + int(webhook_counts.get("exhausted_count") or 0),
            "description": f"待重试 {int(webhook_counts.get('retry_scheduled_count') or 0)} · 已耗尽 {int(webhook_counts.get('exhausted_count') or 0)}",
            "tone": "danger" if int(webhook_counts.get("exhausted_count") or 0) else ("warn" if int(webhook_counts.get("retry_scheduled_count") or 0) else "ok"),
        },
    ]

    return {
        "active_tab": active_tab,
        "tabs": jobs_tabs(active_tab),
        "summary_cards": summary_cards,
        "archive_runtime": {
            "last_sync_run": _sync_row_view(last_sync_run) if last_sync_run else {},
            "sync_counts": sync_counts,
            "health": runtime_snapshot.get("archive_health") or {},
            "health_error": _normalized_text(runtime_snapshot.get("archive_health_error")),
            "sync_form": _archive_sync_form_defaults(),
        },
        "callback_runtime": {
            "enabled": runtime_snapshot["callback_enabled"],
            "async_enabled": runtime_snapshot["background_async_enabled"],
            "counts": callback_counts,
        },
        "batches_runtime": {
            "counts": batch_counts,
        },
        "deferred_runtime": {
            "counts": deferred_counts,
            "mcp_auth_configured": _mcp_auth_configured(),
        },
        "webhook_runtime": {
            "counts": webhook_counts,
        },
        "archive_filters": archive_filters,
        "callback_filters": callback_filters,
        "batch_filters": batch_filters,
        "deferred_filters": deferred_filters,
        "webhook_filters": webhook_filters,
        "archive_status_options": ["", "success", "failed"],
        "callback_status_options": ["", "pending", "processing", "success", "failed"],
        "batch_status_options": _batch_status_options(),
        "deferred_status_options": _deferred_status_options(),
        "webhook_status_options": _webhook_status_options(),
        "webhook_event_type_options": _webhook_event_type_options(),
        "sync_runs": sync_runs,
        "callback_logs": callback_logs,
        "batch_rows": batch_rows,
        "selected_batch": selected_batch,
        "selected_batch_messages": selected_batch_messages,
        "deferred_jobs": deferred_jobs,
        "webhook_deliveries": webhook_deliveries,
    }


def build_jobs_summary_payload(args: Any) -> dict[str, Any]:
    payload = build_jobs_payload(args)
    return {
        "summary_cards": payload["summary_cards"],
        "archive_runtime": payload["archive_runtime"],
        "callback_runtime": payload["callback_runtime"],
        "batches_runtime": payload["batches_runtime"],
        "deferred_runtime": payload["deferred_runtime"],
        "webhook_runtime": payload["webhook_runtime"],
    }


def build_jobs_archive_sync_payload(args: Any) -> dict[str, Any]:
    raw_args = dict(args or {})
    raw_args["tab"] = "archive"
    payload = build_jobs_payload(raw_args)
    return {
        "runtime": payload["archive_runtime"],
        "filters": payload["archive_filters"],
        "items": payload["sync_runs"],
        "status_options": payload["archive_status_options"],
    }


def build_jobs_callbacks_payload(args: Any) -> dict[str, Any]:
    raw_args = dict(args or {})
    raw_args["tab"] = "callbacks"
    payload = build_jobs_payload(raw_args)
    return {
        "runtime": payload["callback_runtime"],
        "filters": payload["callback_filters"],
        "items": payload["callback_logs"],
        "status_options": payload["callback_status_options"],
    }


def build_jobs_message_batches_payload(args: Any) -> dict[str, Any]:
    raw_args = dict(args or {})
    raw_args["tab"] = "batches"
    payload = build_jobs_payload(raw_args)
    return {
        "runtime": payload["batches_runtime"],
        "filters": payload["batch_filters"],
        "items": payload["batch_rows"],
        "status_options": payload["batch_status_options"],
    }


def build_jobs_message_batch_detail_payload(batch_id: int, args: Any) -> dict[str, Any]:
    raw_args = dict(args or {})
    raw_args["tab"] = "batches"
    raw_args["batch_id"] = str(int(batch_id))
    payload = build_jobs_payload(raw_args)
    return {
        "runtime": payload["batches_runtime"],
        "filters": payload["batch_filters"],
        "batch": payload["selected_batch"],
        "messages": payload["selected_batch_messages"],
    }


def build_jobs_deferred_jobs_payload(args: Any) -> dict[str, Any]:
    raw_args = dict(args or {})
    raw_args["tab"] = "deferred"
    payload = build_jobs_payload(raw_args)
    return {
        "runtime": payload["deferred_runtime"],
        "filters": payload["deferred_filters"],
        "items": payload["deferred_jobs"],
        "status_options": payload["deferred_status_options"],
    }


def build_jobs_webhook_deliveries_payload(args: Any) -> dict[str, Any]:
    raw_args = dict(args or {})
    raw_args["tab"] = "webhooks"
    payload = build_jobs_payload(raw_args)
    return {
        "runtime": payload["webhook_runtime"],
        "filters": payload["webhook_filters"],
        "items": payload["webhook_deliveries"],
        "status_options": payload["webhook_status_options"],
        "event_type_options": payload["webhook_event_type_options"],
    }


def execute_jobs_action(*, action: str, form: Any, operator: str) -> dict[str, Any]:
    normalized_action = _normalized_text(action)
    operator_value = _operator(operator)

    if normalized_action == "run-archive-sync":
        request_payload = _archive_sync_request_payload(form)
        if not request_payload["start_time"] or not request_payload["end_time"] or not request_payload["owner_userid"]:
            raise ValueError("开始时间、结束时间和负责人账号不能为空")
        if not _normalized_bool(form.get("confirm")):
            preview = {
                "ok": True,
                "preview_only": True,
                "confirm_required": True,
                "request": request_payload,
            }
            _audit_log(
                operator=operator_value,
                action_type="preview_archive_sync",
                target_id="archive_sync",
                before=request_payload,
                after=preview,
            )
            return preview
        payload = run_manual_archive_sync(**request_payload)
        _audit_log(
            operator=operator_value,
            action_type="run_archive_sync",
            target_id=str((payload.get("sync_run") or {}).get("id") or "archive_sync"),
            before=request_payload,
            after=payload,
        )
        return payload

    if normalized_action == "ack-message-batch":
        if not _normalized_bool(form.get("confirm")):
            raise ValueError("确认消息批次前请先勾选确认")
        batch_id = _normalized_int(form.get("batch_id"), default=0, minimum=1, maximum=10**9)
        ack_note = _normalized_text(form.get("ack_note"))
        payload = ack_message_batch(batch_id, ack_note=ack_note, acked_by=operator_value)
        if not payload:
            raise ValueError("未找到对应消息批次")
        result = dict(payload)
        _audit_log(
            operator=operator_value,
            action_type="ack_message_batch",
            target_id=str(batch_id),
            before={"batch_id": batch_id, "ack_note": ack_note},
            after=result,
        )
        return {"ok": True, "batch": result}

    if normalized_action == "run-deferred-jobs":
        if not _normalized_bool(form.get("confirm")):
            raise ValueError("执行待处理作业前请先勾选确认")
        limit = _normalized_int(form.get("limit"), default=20)
        payload = _run_user_ops_deferred_jobs_payload(limit=limit)
        _audit_log(
            operator=operator_value,
            action_type="run_deferred_jobs",
            target_id=f"limit:{limit}",
            before={"limit": limit},
            after=payload,
        )
        return payload

    if normalized_action == "retry-webhook-delivery":
        if not _normalized_bool(form.get("confirm")):
            raise ValueError("重试 webhook 投递前请先勾选确认")
        delivery_id = _normalized_int(form.get("delivery_id"), default=0, minimum=1, maximum=10**9)
        payload = retry_outbound_webhook_delivery(delivery_id)
        _audit_log(
            operator=operator_value,
            action_type="retry_webhook_delivery",
            target_id=str(delivery_id),
            before={"delivery_id": delivery_id},
            after=payload,
        )
        return payload

    if normalized_action == "run-webhook-retries":
        if not _normalized_bool(form.get("confirm")):
            raise ValueError("执行 webhook 自动重试前请先勾选确认")
        limit = _normalized_int(form.get("limit"), default=20)
        payload = run_due_outbound_webhook_retries(limit=limit)
        _audit_log(
            operator=operator_value,
            action_type="run_webhook_retries",
            target_id=f"limit:{limit}",
            before={"limit": limit},
            after=payload,
        )
        return payload

    raise ValueError("不支持的同步任务操作")
