from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "docs/archive/route_inventory/customer_automation_webhook_route_inventory.md"


def test_customer_webhook_inventory_contains_required_matrix_and_boundaries():
    text = INVENTORY.read_text(encoding="utf-8")

    assert "Retired Route Matrix" in text
    assert "/api/customers/automation/activation-webhook" in text
    assert "/api/customers/automation/webhook-deliveries/{delivery_id}/retry" in text
    assert "/api/customers/automation/webhook-deliveries/retry-due" in text
    assert "/api/customer-automation/activation-webhook" in text
    assert "/api/customers/automation/signup-conversion/batches" in text
    assert "legacy_customer_automation_retired" in text
    assert "legacy_fallback_allowed=false" in text
    assert "external_effect_job 不会被创建" in text
    assert "real_external_call_executed=false" in text
    assert "outbound_webhook_executed=false" in text
    assert "automation_runtime_executed=false" in text
    assert "wecom_send_executed=false" in text
    assert "does not call the retired customer automation commands" in text
    assert "ApplyCustomerActivationWebhookCommand" not in text
    assert "PlanCustomerWebhookDeliveryRetryCommand" not in text
    assert "PlanCustomerWebhookDeliveryRetryDueCommand" not in text
