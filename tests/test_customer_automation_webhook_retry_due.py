from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.main import create_app


def _client(monkeypatch) -> TestClient:
    monkeypatch.delenv("AICRM_NEXT_FORCE_PRODUCTION_DATA", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    return TestClient(create_app(), raise_server_exceptions=False)


def _assert_retired(response) -> None:
    assert response.status_code == 410
    body = response.json()
    assert body["ok"] is False
    assert body["error"] == "legacy_customer_automation_retired"
    assert body["route_owner"] == "ai_crm_next"
    assert body["real_external_call_executed"] is False
    assert body["outbound_webhook_executed"] is False
    assert body["automation_runtime_executed"] is False


def test_retry_due_route_is_retired(monkeypatch):
    client = _client(monkeypatch)

    response = client.post(
        "/api/customers/automation/webhook-deliveries/retry-due",
        json={"limit": 7},
        headers={"Idempotency-Key": "customer-webhook-retry-due"},
    )

    _assert_retired(response)


def test_retry_due_options_is_retired(monkeypatch):
    client = _client(monkeypatch)

    response = client.options("/api/customers/automation/webhook-deliveries/retry-due")

    _assert_retired(response)
