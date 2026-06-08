from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "docs/architecture/customer_automation_webhook_route_inventory.md"


def test_customer_webhook_inventory_contains_required_matrix_and_boundaries():
    text = INVENTORY.read_text(encoding="utf-8")

    assert "Caller ↔ API ↔ CommandBus ↔ SideEffectPlan Matrix" in text
    assert "/api/customers/automation/activation-webhook" in text
    assert "/api/customers/automation/webhook-deliveries/{delivery_id}/retry" in text
    assert "/api/customers/automation/webhook-deliveries/retry-due" in text
    assert "ApplyCustomerActivationWebhookCommand" in text
    assert "PlanCustomerWebhookDeliveryRetryCommand" in text
    assert "PlanCustomerWebhookDeliveryRetryDueCommand" in text
    assert "next_customer_activation_webhook" in text
    assert "next_customer_webhook_retry_plan" in text
    assert "next_customer_webhook_retry_due_plan" in text
    assert "legacy_fallback_allowed=false" in text
    assert "deletion_locked" in text
    assert "adapter_mode=local" in text
    assert "adapter_mode=real_blocked" in text
    assert "real_external_call_executed=false" in text
    assert "outbound_webhook_executed=false" in text
    assert "does not call the legacy Flask customer automation blueprint" in text
