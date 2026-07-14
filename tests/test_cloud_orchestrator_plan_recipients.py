from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.cloud_orchestrator.campaigns_read import reset_campaign_read_fixture_state
from aicrm_next.cloud_orchestrator.run_due import reset_run_due_fixture_state
from aicrm_next.main import create_app


def test_cloud_orchestrator_run_due_lists_recipients_without_dispatch(monkeypatch) -> None:
    monkeypatch.delenv("AICRM_NEXT_FORCE_PRODUCTION_DATA", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    reset_campaign_read_fixture_state()
    reset_run_due_fixture_state()
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.post(
        "/api/admin/cloud-orchestrator/campaigns/run-due/preview",
        json={"batch_size": 10},
        headers={"Idempotency-Key": "cloud-run-due-recipient-preview", "Authorization": "Bearer timer-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["candidate_count"] >= 1
    assert body["estimated_actions"]["planned_message_count"] == body["candidate_count"]
    assert body["real_external_call_executed"] is False
    assert body["wecom_send_executed"] is False
