"""Automation ops scheduler — materialize due business tasks into broadcast_jobs.

This runner does not send WeCom messages. It only lets business domains enqueue
due work into ``broadcast_jobs`` so ``run_broadcast_queue_worker.py`` remains the
single outbound execution path.
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

from script_runtime import ensure_repo_root_on_path, print_json

ensure_repo_root_on_path()


logger = logging.getLogger("automation_ops_scheduler")
DEFAULT_OPERATOR = "automation_ops_scheduler"
HXC_DASHBOARD_REFRESH_INTERVAL = timedelta(minutes=30)
FEISHU_HOURLY_REPORT_MINUTE = 5


def _operation_task_summary(*, now: datetime, operator: str) -> dict[str, Any]:
    from wecom_ability_service.domains.automation_conversion.operation_task_service import (
        run_due_operation_tasks,
    )

    return run_due_operation_tasks(now=now, operator_id=operator)


def _group_ops_summary(*, now: datetime, operator: str) -> dict[str, Any]:
    from aicrm_next.automation_engine.group_ops.scheduler import run_group_ops_due_scheduler

    return run_group_ops_due_scheduler(now=now, operator=operator)


def _as_utc(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        raw = str(value).strip()
        if not raw:
            return None
        normalized = raw.replace(" ", "T", 1)
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _hxc_dashboard_summary(*, now: datetime, operator: str) -> dict[str, Any]:
    from wecom_ability_service.domains.user_ops.hxc_dashboard_snapshot_service import (
        get_latest_snapshot_meta,
        refresh_hxc_dashboard_snapshot,
    )

    latest = get_latest_snapshot_meta()
    latest_refresh_at = _as_utc(latest.get("finished_at") or latest.get("started_at"))
    if latest_refresh_at and now - latest_refresh_at < HXC_DASHBOARD_REFRESH_INTERVAL:
        return {
            "attempted": False,
            "skipped_reason": "fresh_snapshot",
            "latest_refresh_at": latest_refresh_at.isoformat(),
            "next_refresh_after": (latest_refresh_at + HXC_DASHBOARD_REFRESH_INTERVAL).isoformat(),
        }

    result = refresh_hxc_dashboard_snapshot(trigger_source=f"{operator}:hxc_dashboard_30m")
    return {
        "attempted": True,
        "ok": bool(result.get("ok")),
        "status": result.get("status") or ("success" if result.get("ok") else "failed"),
        "row_count": int(result.get("row_count") or 0),
        "error": result.get("error") or "",
    }


def _broadcast_feishu_hourly_summary(*, now: datetime) -> dict[str, Any]:
    if now.minute != FEISHU_HOURLY_REPORT_MINUTE:
        return {"attempted": False, "skipped_reason": "not_hourly_report_minute"}

    from aicrm_next.admin_jobs.notification_settings import (
        send_broadcast_job_hourly_feishu_report,
    )

    result = send_broadcast_job_hourly_feishu_report(now=now)
    return {"attempted": True, **result}


def run(*, now: datetime | None = None, operator: str | None = None) -> dict[str, Any]:
    scanned_at = now or datetime.now(timezone.utc)
    if scanned_at.tzinfo is None:
        scanned_at = scanned_at.replace(tzinfo=timezone.utc)
    actor = (operator or os.getenv("AUTOMATION_OPS_SCHEDULER_OPERATOR", DEFAULT_OPERATOR)).strip() or DEFAULT_OPERATOR
    errors: list[dict[str, Any]] = []
    operation_result: dict[str, Any] = {}
    group_result: dict[str, Any] = {}
    hxc_dashboard_result: dict[str, Any] = {}
    broadcast_feishu_result: dict[str, Any] = {}

    try:
        operation_result = _operation_task_summary(now=scanned_at, operator=actor)
    except Exception as exc:
        logger.exception("operation_task scheduler failed")
        errors.append({"scope": "operation_task", "error": str(exc)})

    try:
        group_result = _group_ops_summary(now=scanned_at, operator=actor)
        errors.extend(list(group_result.get("errors") or []))
    except Exception as exc:
        logger.exception("group_ops scheduler failed")
        errors.append({"scope": "group_ops", "error": str(exc)})

    try:
        hxc_dashboard_result = _hxc_dashboard_summary(now=scanned_at, operator=actor)
        if hxc_dashboard_result.get("attempted") and not hxc_dashboard_result.get("ok"):
            errors.append({"scope": "hxc_dashboard", "error": hxc_dashboard_result.get("error") or "refresh_failed"})
    except Exception as exc:
        logger.exception("hxc_dashboard scheduler failed")
        errors.append({"scope": "hxc_dashboard", "error": str(exc)})

    try:
        broadcast_feishu_result = _broadcast_feishu_hourly_summary(now=scanned_at)
        if broadcast_feishu_result.get("status") == "failed":
            errors.append(
                {
                    "scope": "broadcast_feishu_hourly_report",
                    "error": broadcast_feishu_result.get("message") or "send_failed",
                }
            )
    except Exception as exc:
        logger.exception("broadcast Feishu hourly report failed")
        errors.append({"scope": "broadcast_feishu_hourly_report", "error": str(exc)})

    return {
        "scanned_at": scanned_at.isoformat(),
        "group_ops_scanned_plans": int(group_result.get("group_ops_scanned_plans") or 0),
        "group_ops_due_nodes": int(group_result.get("group_ops_due_nodes") or 0),
        "group_ops_enqueued_jobs": int(group_result.get("group_ops_enqueued_jobs") or 0),
        "group_ops_skipped_future": int(group_result.get("group_ops_skipped_future") or 0),
        "group_ops_skipped_duplicate": int(group_result.get("group_ops_skipped_duplicate") or 0),
        "operation_task_enqueued_jobs": int(operation_result.get("enqueued_count") or 0),
        "hxc_dashboard_refresh": hxc_dashboard_result,
        "broadcast_feishu_hourly_report": broadcast_feishu_result,
        "errors": errors,
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from wecom_ability_service import create_app

    app = create_app()
    with app.app_context():
        summary = run()
    print_json(summary)
    return 0 if not summary.get("errors") else 1


if __name__ == "__main__":
    sys.exit(main())
