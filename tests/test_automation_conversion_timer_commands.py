from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.automation_engine.timers import (
    get_timer_audit_events,
    get_timer_external_call_attempts,
    get_timer_side_effect_plans,
    reset_timer_fixture_state,
)
from aicrm_next.main import create_app


def _client(monkeypatch) -> TestClient:
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)
    monkeypatch.delenv("AICRM_NEXT_FORCE_PRODUCTION_DATA", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    reset_timer_fixture_state()
    return TestClient(create_app(), raise_server_exceptions=False)


def _assert_safe_contract(body: dict) -> None:
    assert body["ok"] is True
    assert body["route_owner"] == "ai_crm_next"
    assert body["fallback_used"] is False
    assert body["adapter_mode"] == "real_blocked"
    assert body["real_external_call_executed"] is False
    assert body["automation_runtime_executed"] is False
    assert body["wecom_send_executed"] is False
    assert body["processed_count"] == 0
    assert body["sent_count"] == 0
    assert body["failed_count"] == 0


def test_reply_monitor_capture_returns_blocked_plan(monkeypatch):
    client = _client(monkeypatch)

    response = client.post(
        "/api/admin/automation-conversion/reply-monitor/capture",
        json={"limit": 5},
        headers={"Idempotency-Key": "timer-capture-plan"},
    )

    assert response.status_code == 200
    body = response.json()
    _assert_safe_contract(body)
    assert body["source_status"] == "next_reply_monitor_capture_plan"
    assert body["reply_monitor_capture_executed"] is False
    assert body["captured_count"] == 0
    assert body["planned_count"] == 1
    assert body["side_effect_plan"]["effect_type"] == "automation_conversion.reply_monitor.capture"
    assert body["side_effect_plan"]["status"] == "blocked"
    assert body["external_call_attempt"]["status"] == "blocked"
    assert len(get_timer_side_effect_plans()) == 1
    assert len(get_timer_external_call_attempts()) == 1
    assert get_timer_audit_events()


def test_reply_monitor_run_due_returns_blocked_plan(monkeypatch):
    client = _client(monkeypatch)

    response = client.post(
        "/api/admin/automation-conversion/reply-monitor/run-due",
        json={"limit": 5},
        headers={"Idempotency-Key": "timer-reply-run-due-plan"},
    )

    assert response.status_code == 200
    body = response.json()
    _assert_safe_contract(body)
    assert body["source_status"] == "next_reply_monitor_run_due_plan"
    assert body["reply_monitor_run_due_executed"] is False
    assert body["planned_count"] == 1
    assert body["skipped_count"] == 1
    assert body["side_effect_plan"]["effect_type"] == "automation_conversion.reply_monitor.run_due"
    assert body["side_effect_plan"]["requires_approval"] is True


def test_jobs_run_due_returns_blocked_plan_with_job_codes(monkeypatch):
    client = _client(monkeypatch)

    response = client.post(
        "/api/admin/automation-conversion/jobs/run-due",
        json={"jobs": ["job_a", "job_b"], "batch_size": 2},
        headers={"Idempotency-Key": "timer-jobs-run-due-plan"},
    )

    assert response.status_code == 200
    body = response.json()
    _assert_safe_contract(body)
    assert body["source_status"] == "next_jobs_run_due_plan"
    assert body["jobs_run_due_executed"] is False
    assert body["job_codes"] == ["job_a", "job_b"]
    assert body["planned_count"] == 2
    assert body["side_effect_plan"]["effect_type"] == "automation_conversion.jobs.run_due"


def test_options_and_invalid_limit(monkeypatch):
    client = _client(monkeypatch)

    options = client.options("/api/admin/automation-conversion/reply-monitor/capture")
    assert options.status_code == 200
    body = options.json()
    assert body["source_status"] == "next_reply_monitor_capture_plan"
    assert body["allowed_methods"] == ["POST", "OPTIONS"]
    assert body["automation_runtime_executed"] is False

    invalid = client.post("/api/admin/automation-conversion/jobs/run-due", json={"limit": 0})
    assert invalid.status_code == 400
    invalid_body = invalid.json()
    assert invalid_body["ok"] is False
    assert invalid_body["source_status"] == "next_jobs_run_due_plan"
    assert "limit" in invalid_body["error"]
