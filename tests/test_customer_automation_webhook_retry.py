from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.automation_engine.customer_webhooks import (
    get_customer_webhook_audit_events,
    get_customer_webhook_external_call_attempts,
    get_customer_webhook_side_effect_plans,
    reset_customer_webhook_fixture_state,
)
from aicrm_next.main import create_app


def _client(monkeypatch) -> TestClient:
    monkeypatch.delenv("AICRM_NEXT_FORCE_PRODUCTION_DATA", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    reset_customer_webhook_fixture_state()
    return TestClient(create_app(), raise_server_exceptions=False)


def test_delivery_retry_returns_blocked_next_safe_mode_plan(monkeypatch):
    client = _client(monkeypatch)

    response = client.post(
        "/api/customers/automation/webhook-deliveries/12/retry",
        json={},
        headers={"Idempotency-Key": "customer-webhook-retry-12"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["source_status"] == "next_customer_webhook_retry_plan"
    assert body["status"] == "planned_blocked"
    assert body["delivery_id"] == 12
    assert body["route_owner"] == "ai_crm_next"
    assert body["fallback_used"] is False
    assert body["adapter_mode"] == "real_blocked"
    assert body["real_external_call_executed"] is False
    assert body["outbound_webhook_executed"] is False
    assert body["retried_count"] == 0
    assert body["sent_count"] == 0
    assert body["skipped_count"] == 1
    assert body["side_effect_plan"]["effect_type"] == "customer_automation.webhook_delivery.retry"
    assert body["side_effect_plan"]["adapter_mode"] == "real_blocked"
    assert body["side_effect_plan"]["requires_approval"] is True
    assert body["external_call_attempt"]["status"] == "blocked"
    assert len(get_customer_webhook_side_effect_plans()) == 1
    assert len(get_customer_webhook_external_call_attempts()) == 1
    assert get_customer_webhook_audit_events()


def test_delivery_retry_options_are_next_owned(monkeypatch):
    client = _client(monkeypatch)

    response = client.options("/api/customers/automation/webhook-deliveries/12/retry")

    assert response.status_code == 200
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    body = response.json()
    assert body["source_status"] == "next_customer_webhook_retry_plan"
    assert body["delivery_id"] == 12
    assert body["allowed_methods"] == ["POST", "OPTIONS"]
    assert body["fallback_used"] is False
