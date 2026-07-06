from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.main import create_app


def test_customer_webhook_retry_retirement_is_idempotent(monkeypatch):
    monkeypatch.delenv("AICRM_NEXT_FORCE_PRODUCTION_DATA", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    client = TestClient(create_app(), raise_server_exceptions=False)
    headers = {"Idempotency-Key": "same-customer-webhook-retry-key"}

    first = client.post("/api/customers/automation/webhook-deliveries/12/retry", json={}, headers=headers)
    second = client.post("/api/customers/automation/webhook-deliveries/34/retry", json={}, headers=headers)

    assert first.status_code == 410
    assert second.status_code == 410
    assert first.json()["error"] == "legacy_customer_automation_retired"
    assert second.json()["error"] == "legacy_customer_automation_retired"
    assert first.json()["real_external_call_executed"] is False
    assert second.json()["real_external_call_executed"] is False
