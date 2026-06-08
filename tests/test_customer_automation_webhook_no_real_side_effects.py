from __future__ import annotations

import ast
from pathlib import Path

from fastapi.testclient import TestClient

from aicrm_next.automation_engine.customer_webhooks import reset_customer_webhook_fixture_state
from aicrm_next.main import create_app


ROOT = Path(__file__).resolve().parents[1]


def _joined(*parts: str) -> str:
    return "".join(parts)


def test_customer_webhook_routes_return_no_real_side_effect_flags(monkeypatch):
    monkeypatch.delenv("AICRM_NEXT_FORCE_PRODUCTION_DATA", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    reset_customer_webhook_fixture_state()
    client = TestClient(create_app(), raise_server_exceptions=False)

    cases = (
        ("/api/customers/automation/activation-webhook", {"mobile": "13800000000"}, "local"),
        ("/api/customers/automation/webhook-deliveries/1/retry", {}, "real_blocked"),
        ("/api/customers/automation/webhook-deliveries/retry-due", {"limit": 2}, "real_blocked"),
    )
    for path, payload, adapter_mode in cases:
        response = client.post(path, json=payload, headers={"Idempotency-Key": f"customer-webhook-safe-{path}"})
        assert response.status_code == 200
        body = response.json()
        assert body["adapter_mode"] == adapter_mode
        assert body["real_external_call_executed"] is False
        assert body["outbound_webhook_executed"] is False
        assert body["automation_runtime_executed"] is False
        assert body["wecom_send_executed"] is False


def test_customer_webhook_source_does_not_reference_legacy_runtime_or_direct_clients():
    runtime_source = (ROOT / "aicrm_next/automation_engine/customer_webhooks.py").read_text(encoding="utf-8")
    api_source = (ROOT / "aicrm_next/automation_engine/api.py").read_text(encoding="utf-8")
    tree = ast.parse(api_source)
    handler_sources = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and "customer_automation" in node.name:
            handler_sources.append(ast.get_source_segment(api_source, node) or "")
    combined = runtime_source + "\n" + "\n".join(handler_sources)

    forbidden = [
        _joined("wecom_", "ability_service"),
        _joined("Apply", "ActivationWebhook", "Command"),
        _joined("Retry", "OutboundWebhookDelivery", "Command"),
        _joined("Run", "DueOutboundWebhookRetries", "Command"),
        _joined("send_", "outbound_webhook"),
        _joined("req", "uests."),
        _joined("htt", "px."),
        _joined("access", "_token"),
    ]
    for marker in forbidden:
        assert marker not in combined

    true_markers = [
        _joined("real_external_call_executed", "=True"),
        _joined("outbound_webhook_executed", "=True"),
        _joined("automation_runtime_executed", "=True"),
        _joined("wecom_send_executed", "=True"),
        _joined("real_", "enabled def", "ault"),
        _joined("def", "ault real_", "enabled"),
    ]
    for marker in true_markers:
        assert marker not in combined
