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


def test_activation_webhook_returns_next_local_safe_mode_plan(monkeypatch):
    client = _client(monkeypatch)

    response = client.post(
        "/api/customers/automation/activation-webhook",
        json={"mobile": "13800000000", "source": "app"},
        headers={"Idempotency-Key": "customer-activation-local"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["source_status"] == "next_customer_activation_webhook"
    assert body["route_owner"] == "ai_crm_next"
    assert body["fallback_used"] is False
    assert body["status"] == "planned_local_only"
    assert body["adapter_mode"] == "local"
    assert body["customer_automation_applied"] == "local_only"
    assert body["real_external_call_executed"] is False
    assert body["outbound_webhook_executed"] is False
    assert body["automation_runtime_executed"] is False
    assert body["wecom_send_executed"] is False
    assert body["side_effect_plan"]["adapter_mode"] == "local"
    assert body["side_effect_plan"]["status"] == "planned"
    assert body["side_effect_plan"]["requires_approval"] is False
    assert "external_call_attempt" not in body
    assert len(get_customer_webhook_side_effect_plans()) == 1
    assert get_customer_webhook_external_call_attempts() == []
    assert get_customer_webhook_audit_events()


def test_activation_options_and_missing_mobile_are_controlled(monkeypatch):
    client = _client(monkeypatch)

    options = client.options("/api/customers/automation/activation-webhook")
    assert options.status_code == 200
    options_body = options.json()
    assert options_body["allowed_methods"] == ["POST", "OPTIONS"]
    assert options_body["source_status"] == "next_customer_activation_webhook"
    assert options_body["fallback_used"] is False
    assert options_body["real_external_call_executed"] is False

    missing = client.post("/api/customers/automation/activation-webhook", json={})
    assert missing.status_code == 400
    missing_body = missing.json()
    assert missing_body["ok"] is False
    assert missing_body["source_status"] == "next_customer_activation_webhook"
    assert "mobile" in missing_body["error"]
