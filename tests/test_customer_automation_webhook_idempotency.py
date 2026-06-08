from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.automation_engine.customer_webhooks import get_customer_webhook_side_effect_plans, reset_customer_webhook_fixture_state
from aicrm_next.main import create_app


def test_customer_webhook_retry_reuses_idempotent_command_result(monkeypatch):
    monkeypatch.delenv("AICRM_NEXT_FORCE_PRODUCTION_DATA", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    reset_customer_webhook_fixture_state()
    client = TestClient(create_app(), raise_server_exceptions=False)
    headers = {"Idempotency-Key": "same-customer-webhook-retry-key"}

    first = client.post("/api/customers/automation/webhook-deliveries/12/retry", json={}, headers=headers)
    second = client.post("/api/customers/automation/webhook-deliveries/34/retry", json={}, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["command_id"] == second.json()["command_id"]
    assert first.json()["delivery_id"] == 12
    assert second.json()["delivery_id"] == 12
    assert len(get_customer_webhook_side_effect_plans()) == 1
