from __future__ import annotations

from datetime import datetime, timezone

from aicrm_next.background_jobs.automation_ops_scheduler import run_automation_ops_scheduler


def test_automation_ops_scheduler_reports_only_group_ops_component() -> None:
    calls: list[str] = []

    def fake_group_ops_runner(*, now, operator, dry_run):
        calls.append(f"{operator}:{now.isoformat()}:{dry_run}")
        return {
            "component": "group_ops_scheduler",
            "status": "ok",
            "group_ops_scanned_plans": 3,
            "group_ops_due_nodes": 4,
            "group_ops_enqueued_jobs": 1,
            "errors": [],
        }

    now = datetime(2026, 5, 29, 8, 0, tzinfo=timezone.utc)
    summary = run_automation_ops_scheduler(now=now, operator="pytest", group_ops_runner=fake_group_ops_runner)

    assert calls == ["pytest:2026-05-29T08:00:00+00:00:False"]
    assert summary["ok"] is True
    assert [item["component"] for item in summary["components"]] == ["group_ops_scheduler"]
    assert summary["components"][0]["group_ops_enqueued_jobs"] == 1


def test_automation_ops_scheduler_dry_run_is_group_ops_only() -> None:
    summary = run_automation_ops_scheduler(
        dry_run=True,
        now=datetime(2026, 5, 30, 3, 5, tzinfo=timezone.utc),
        operator="pytest",
        group_ops_runner=lambda **kwargs: {"component": "group_ops_scheduler", "status": "skipped", "reason": "dry_run"},
    )

    assert summary["ok"] is True
    assert summary["components"] == [
        {"component": "group_ops_scheduler", "status": "skipped", "reason": "dry_run"}
    ]


def test_automation_ops_scheduler_reports_group_ops_failure() -> None:
    def failing_group_ops_runner(**kwargs):
        raise RuntimeError("repo unavailable")

    summary = run_automation_ops_scheduler(group_ops_runner=failing_group_ops_runner)

    assert summary["ok"] is False
    assert summary["errors"] == [{"scope": "group_ops_scheduler", "error": "repo unavailable"}]
