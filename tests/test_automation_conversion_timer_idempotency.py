from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.automation_engine.timers import get_timer_side_effect_plans, reset_timer_fixture_state
from aicrm_next.main import create_app


def test_jobs_run_due_idempotency_key_reuses_planned_result(monkeypatch):
    monkeypatch.delenv("AICRM_NEXT_FORCE_PRODUCTION_DATA", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    reset_timer_fixture_state()
    client = TestClient(create_app(), raise_server_exceptions=False)
    headers = {"Idempotency-Key": "same-automation-timer-key"}

    first = client.post("/api/admin/automation-conversion/jobs/run-due", json={"jobs": ["job_a"]}, headers=headers)
    second = client.post("/api/admin/automation-conversion/jobs/run-due", json={"jobs": ["job_b"]}, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["command_id"] == second.json()["command_id"]
    assert first.json()["job_codes"] == ["job_a"]
    assert second.json()["job_codes"] == ["job_a"]
    assert len(get_timer_side_effect_plans()) == 1
