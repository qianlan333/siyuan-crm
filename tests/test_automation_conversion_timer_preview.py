from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.automation_engine.timers import get_timer_external_call_attempts, get_timer_side_effect_plans, reset_timer_fixture_state
from aicrm_next.main import create_app


def test_jobs_preview_lists_candidates_without_plan(monkeypatch):
    monkeypatch.delenv("AICRM_NEXT_FORCE_PRODUCTION_DATA", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    reset_timer_fixture_state()
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.post(
        "/api/admin/automation-conversion/jobs/run-due/preview",
        json={"job_codes": "job_a,job_b", "batch_size": 2},
        headers={"Idempotency-Key": "timer-jobs-preview"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["source_status"] == "next_jobs_run_due_preview"
    assert body["route_owner"] == "ai_crm_next"
    assert body["fallback_used"] is False
    assert body["real_external_call_executed"] is False
    assert body["automation_runtime_executed"] is False
    assert body["jobs_run_due_executed"] is False
    assert body["candidate_count"] == 2
    assert body["job_codes"] == ["job_a", "job_b"]
    assert body["estimated_actions"]["planned_action_count"] == 2
    assert body["planned_count"] == 0
    assert get_timer_side_effect_plans() == []
    assert get_timer_external_call_attempts() == []
