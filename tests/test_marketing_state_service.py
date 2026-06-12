from __future__ import annotations

from aicrm_next.automation_engine.customer_webhooks import (
    ApplyCustomerActivationWebhookCommand,
    execute_customer_webhook_command,
    reset_customer_webhook_fixture_state,
)


def test_marketing_activation_state_projection_is_next_local_plan() -> None:
    reset_customer_webhook_fixture_state()

    result = execute_customer_webhook_command(
        ApplyCustomerActivationWebhookCommand(
            mobile="13800138000",
            activated_at="2026-05-01T08:00:00+08:00",
            source="marketing_test",
            source_route="/api/customer-automation/activation-webhook",
        )
    )

    assert result["ok"] is True
    assert result["source_status"] == "next_customer_activation_webhook"
    assert result["status"] == "planned_local_only"
    assert result["route_owner"] == "ai_crm_next"
    assert result["fallback_used"] is False
    assert result["real_external_call_executed"] is False
