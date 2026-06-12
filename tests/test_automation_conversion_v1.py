from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.automation_engine.timers import reset_timer_fixture_state
from aicrm_next.main import create_app


def _client(monkeypatch) -> TestClient:
    monkeypatch.delenv("AICRM_NEXT_FORCE_PRODUCTION_DATA", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    monkeypatch.setenv("AUTOMATION_INTERNAL_API_TOKEN", "timer-token")
    reset_timer_fixture_state()
    return TestClient(create_app(), raise_server_exceptions=False)


def _headers(idempotency_key: str) -> dict[str, str]:
    return {"Idempotency-Key": idempotency_key, "Authorization": "Bearer timer-token"}


def test_reply_monitor_run_due_is_next_plan_only_contract(monkeypatch) -> None:
    response = _client(monkeypatch).post(
        "/api/admin/automation-conversion/reply-monitor/run-due",
        json={"limit": 5},
        headers=_headers("next-reply-monitor-run-due"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["route_owner"] == "ai_crm_next"
    assert body["fallback_used"] is False
    assert body["source_status"] == "next_reply_monitor_run_due_plan"
    assert body["real_external_call_executed"] is False
    assert body["automation_runtime_executed"] is False
    assert body["wecom_send_executed"] is False
    assert body["side_effect_plan"]["status"] == "blocked"


def test_jobs_run_due_keeps_next_safe_mode(monkeypatch) -> None:
    response = _client(monkeypatch).post(
        "/api/admin/automation-conversion/jobs/run-due",
        json={"jobs": ["registered_due_jobs"], "batch_size": 1},
        headers=_headers("next-jobs-run-due"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["source_status"] == "next_jobs_run_due_plan"
    assert body["jobs_run_due_executed"] is False
    assert body["planned_count"] == 1
    assert body["side_effect_plan"]["adapter_mode"] == "real_blocked"
    assert body["real_external_call_executed"] is False
