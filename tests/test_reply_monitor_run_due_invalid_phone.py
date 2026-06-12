from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.automation_engine.timers import reset_timer_fixture_state
from aicrm_next.main import create_app


def test_reply_monitor_run_due_returns_2xx_structured_plan_without_item_send(monkeypatch) -> None:
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    monkeypatch.setenv("AUTOMATION_INTERNAL_API_TOKEN", "timer-token")
    reset_timer_fixture_state()
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.post(
        "/api/admin/automation-conversion/reply-monitor/run-due",
        json={"limit": 10},
        headers={"Authorization": "Bearer timer-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["source_status"] == "next_reply_monitor_run_due_plan"
    assert body["processed_count"] == 0
    assert body["sent_count"] == 0
    assert body["failed_count"] == 0
    assert body["real_external_call_executed"] is False
    assert body["side_effect_plan"]["status"] == "blocked"
