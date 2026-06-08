from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.automation_engine.customer_webhooks import reset_customer_webhook_fixture_state
from aicrm_next.main import create_app


def _client(monkeypatch) -> TestClient:
    monkeypatch.delenv("AICRM_NEXT_FORCE_PRODUCTION_DATA", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    reset_customer_webhook_fixture_state()
    return TestClient(create_app(), raise_server_exceptions=False)


def test_retry_due_returns_blocked_next_safe_mode_plan(monkeypatch):
    client = _client(monkeypatch)

    response = client.post(
        "/api/customers/automation/webhook-deliveries/retry-due",
        json={"limit": 7},
        headers={"Idempotency-Key": "customer-webhook-retry-due"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["source_status"] == "next_customer_webhook_retry_due_plan"
    assert body["status"] == "planned_blocked"
    assert body["limit"] == 7
    assert body["adapter_mode"] == "real_blocked"
    assert body["fallback_used"] is False
    assert body["real_external_call_executed"] is False
    assert body["outbound_webhook_executed"] is False
    assert body["retried_count"] == 0
    assert body["estimated_actions"]["planned_action_count"] == 7
    assert body["estimated_actions"]["blocked_external_call_count"] == 7
    assert body["side_effect_plan"]["effect_type"] == "customer_automation.webhook_delivery.retry_due"
    assert body["external_call_attempt"]["status"] == "blocked"


def test_retry_due_options_and_invalid_limit_are_controlled(monkeypatch):
    client = _client(monkeypatch)

    options = client.options("/api/customers/automation/webhook-deliveries/retry-due")
    assert options.status_code == 200
    assert options.json()["source_status"] == "next_customer_webhook_retry_due_plan"

    invalid = client.post("/api/customers/automation/webhook-deliveries/retry-due", json={"limit": 0})
    assert invalid.status_code == 400
    body = invalid.json()
    assert body["ok"] is False
    assert body["source_status"] == "next_customer_webhook_retry_due_plan"
    assert "limit" in body["error"]
