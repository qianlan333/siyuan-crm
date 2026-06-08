from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.automation_engine.customer_webhooks import reset_customer_webhook_fixture_state
from aicrm_next.main import create_app
from tools import check_production_route_resolution as checker


def test_customer_webhook_exact_routes_resolve_before_production_compat(monkeypatch):
    monkeypatch.delenv("AICRM_NEXT_FORCE_PRODUCTION_DATA", raising=False)
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    reset_customer_webhook_fixture_state()
    client = TestClient(create_app(), raise_server_exceptions=False)

    activation = client.options("/api/customers/automation/activation-webhook")
    retry = client.options("/api/customers/automation/webhook-deliveries/1/retry")
    retry_due = client.options("/api/customers/automation/webhook-deliveries/retry-due")

    assert activation.status_code == 200
    assert activation.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert activation.headers["X-AICRM-Fallback-Used"] == "false"
    assert activation.json()["source_status"] == "next_customer_activation_webhook"
    assert retry.status_code == 200
    assert retry.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert retry.json()["source_status"] == "next_customer_webhook_retry_plan"
    assert retry_due.status_code == 200
    assert retry_due.json()["source_status"] == "next_customer_webhook_retry_due_plan"


def test_route_resolution_samples_show_customer_webhook_next_owned():
    result = checker.run_check()
    samples = result["resolution_samples"]

    def owner(method: str, path: str) -> str:
        return next(item for item in samples if item["method"] == method and item["path"] == path)["route_owner"]

    def endpoint(method: str, path: str) -> str:
        return next(item for item in samples if item["method"] == method and item["path"] == path)["endpoint_module"]

    for path in (
        "/api/customers/automation/activation-webhook",
        "/api/customers/automation/webhook-deliveries/1/retry",
        "/api/customers/automation/webhook-deliveries/retry-due",
    ):
        assert owner("POST", path) == "next"
        assert endpoint("POST", path) == "aicrm_next.automation_engine.api"
