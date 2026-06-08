from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path


_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import run_automation_ops_scheduler as scheduler  # type: ignore[import-not-found]


def test_automation_ops_scheduler_calls_operation_task_and_group_ops(monkeypatch):
    calls: list[str] = []

    def fake_operation_task_summary(*, now, operator):
        calls.append(f"operation_task:{operator}:{now.isoformat()}")
        return {"ok": True, "enqueued_count": 2}

    def fake_group_ops_summary(*, now, operator):
        calls.append(f"group_ops:{operator}:{now.isoformat()}")
        return {
            "group_ops_scanned_plans": 3,
            "group_ops_due_nodes": 4,
            "group_ops_enqueued_jobs": 1,
            "group_ops_skipped_future": 5,
            "group_ops_skipped_duplicate": 6,
            "errors": [],
        }

    def fake_hxc_dashboard_summary(*, now, operator):
        calls.append(f"hxc_dashboard:{operator}:{now.isoformat()}")
        return {"attempted": False, "skipped_reason": "fresh_snapshot"}

    monkeypatch.setattr(scheduler, "_operation_task_summary", fake_operation_task_summary)
    monkeypatch.setattr(scheduler, "_group_ops_summary", fake_group_ops_summary)
    monkeypatch.setattr(scheduler, "_hxc_dashboard_summary", fake_hxc_dashboard_summary)
    monkeypatch.setattr(
        scheduler,
        "_broadcast_feishu_hourly_summary",
        lambda *, now: {"attempted": False, "skipped_reason": "not_hourly_report_minute"},
    )

    now = datetime(2026, 5, 29, 8, 0, tzinfo=timezone.utc)
    summary = scheduler.run(now=now, operator="pytest")

    assert calls == [
        "operation_task:pytest:2026-05-29T08:00:00+00:00",
        "group_ops:pytest:2026-05-29T08:00:00+00:00",
        "hxc_dashboard:pytest:2026-05-29T08:00:00+00:00",
    ]
    assert summary == {
        "scanned_at": "2026-05-29T08:00:00+00:00",
        "group_ops_scanned_plans": 3,
        "group_ops_due_nodes": 4,
        "group_ops_enqueued_jobs": 1,
        "group_ops_skipped_future": 5,
        "group_ops_skipped_duplicate": 6,
        "operation_task_enqueued_jobs": 2,
        "hxc_dashboard_refresh": {"attempted": False, "skipped_reason": "fresh_snapshot"},
        "broadcast_feishu_hourly_report": {"attempted": False, "skipped_reason": "not_hourly_report_minute"},
        "errors": [],
    }


def test_automation_ops_scheduler_runs_broadcast_feishu_hourly_report_at_minute_five(monkeypatch):
    calls: list[str] = []

    monkeypatch.setattr(scheduler, "_operation_task_summary", lambda *, now, operator: {"enqueued_count": 0})
    monkeypatch.setattr(
        scheduler,
        "_group_ops_summary",
        lambda *, now, operator: {
            "group_ops_scanned_plans": 0,
            "group_ops_due_nodes": 0,
            "group_ops_enqueued_jobs": 0,
            "group_ops_skipped_future": 0,
            "group_ops_skipped_duplicate": 0,
            "errors": [],
        },
    )
    monkeypatch.setattr(scheduler, "_hxc_dashboard_summary", lambda *, now, operator: {"attempted": False})

    def fake_broadcast_feishu_summary(*, now):
        calls.append(now.isoformat())
        return {"attempted": True, "status": "sent", "summary": {"totalJobs": 827, "successJobs": 827, "failedJobs": 0}}

    monkeypatch.setattr(scheduler, "_broadcast_feishu_hourly_summary", fake_broadcast_feishu_summary)

    summary = scheduler.run(now=datetime(2026, 5, 30, 3, 5, tzinfo=timezone.utc), operator="pytest")

    assert calls == ["2026-05-30T03:05:00+00:00"]
    assert summary["broadcast_feishu_hourly_report"] == {
        "attempted": True,
        "status": "sent",
        "summary": {"totalJobs": 827, "successJobs": 827, "failedJobs": 0},
    }
    assert summary["errors"] == []


def test_automation_ops_scheduler_reports_broadcast_feishu_hourly_failure(monkeypatch):
    monkeypatch.setattr(scheduler, "_operation_task_summary", lambda *, now, operator: {"enqueued_count": 0})
    monkeypatch.setattr(
        scheduler,
        "_group_ops_summary",
        lambda *, now, operator: {
            "group_ops_scanned_plans": 0,
            "group_ops_due_nodes": 0,
            "group_ops_enqueued_jobs": 0,
            "group_ops_skipped_future": 0,
            "group_ops_skipped_duplicate": 0,
            "errors": [],
        },
    )
    monkeypatch.setattr(scheduler, "_hxc_dashboard_summary", lambda *, now, operator: {"attempted": False})
    monkeypatch.setattr(
        scheduler,
        "_broadcast_feishu_hourly_summary",
        lambda *, now: {"attempted": True, "status": "failed", "message": "飞书小时报发送失败"},
    )

    summary = scheduler.run(now=datetime(2026, 5, 30, 3, 5, tzinfo=timezone.utc), operator="pytest")

    assert summary["broadcast_feishu_hourly_report"] == {
        "attempted": True,
        "status": "failed",
        "message": "飞书小时报发送失败",
    }
    assert summary["errors"] == [
        {"scope": "broadcast_feishu_hourly_report", "error": "飞书小时报发送失败"}
    ]


def test_hxc_dashboard_scheduler_skips_fresh_snapshot(monkeypatch):
    calls: list[str] = []

    def fake_latest_snapshot_meta():
        return {"finished_at": "2026-05-29T07:45:00+00:00", "status": "success"}

    def fake_refresh_snapshot(*, trigger_source):
        calls.append(trigger_source)
        return {"ok": True, "row_count": 1}

    monkeypatch.setattr(
        "wecom_ability_service.domains.user_ops.hxc_dashboard_snapshot_service.get_latest_snapshot_meta",
        fake_latest_snapshot_meta,
    )
    monkeypatch.setattr(
        "wecom_ability_service.domains.user_ops.hxc_dashboard_snapshot_service.refresh_hxc_dashboard_snapshot",
        fake_refresh_snapshot,
    )

    result = scheduler._hxc_dashboard_summary(
        now=datetime(2026, 5, 29, 8, 0, tzinfo=timezone.utc),
        operator="pytest",
    )

    assert calls == []
    assert result["attempted"] is False
    assert result["skipped_reason"] == "fresh_snapshot"
    assert result["latest_refresh_at"] == "2026-05-29T07:45:00+00:00"
    assert result["next_refresh_after"] == "2026-05-29T08:15:00+00:00"


def test_hxc_dashboard_scheduler_refreshes_stale_snapshot(monkeypatch):
    calls: list[str] = []

    def fake_latest_snapshot_meta():
        return {"finished_at": "2026-05-29 07:20:00", "status": "success"}

    def fake_refresh_snapshot(*, trigger_source):
        calls.append(trigger_source)
        return {"ok": True, "row_count": 1266}

    monkeypatch.setattr(
        "wecom_ability_service.domains.user_ops.hxc_dashboard_snapshot_service.get_latest_snapshot_meta",
        fake_latest_snapshot_meta,
    )
    monkeypatch.setattr(
        "wecom_ability_service.domains.user_ops.hxc_dashboard_snapshot_service.refresh_hxc_dashboard_snapshot",
        fake_refresh_snapshot,
    )

    result = scheduler._hxc_dashboard_summary(
        now=datetime(2026, 5, 29, 8, 0, tzinfo=timezone.utc),
        operator="pytest",
    )

    assert calls == ["pytest:hxc_dashboard_30m"]
    assert result == {
        "attempted": True,
        "ok": True,
        "status": "success",
        "row_count": 1266,
        "error": "",
    }
