from __future__ import annotations

from aicrm_next.automation_engine.application import (
    CreateTaskCommand,
    ListAutomationMembersQuery,
    ListTasksQuery,
)
from aicrm_next.automation_engine.customer_webhooks import (
    ApplyCustomerActivationWebhookCommand,
    execute_customer_webhook_command,
    reset_customer_webhook_fixture_state,
)


def test_automation_application_surface_is_next_native() -> None:
    assert ListTasksQuery
    assert CreateTaskCommand
    assert ListAutomationMembersQuery
    assert ApplyCustomerActivationWebhookCommand


def test_activation_webhook_command_plans_local_projection_without_external_call() -> None:
    reset_customer_webhook_fixture_state()

    result = execute_customer_webhook_command(
        ApplyCustomerActivationWebhookCommand(
            mobile="13800138000",
            activated_at="2026-05-01T00:00:00+00:00",
            source="pytest",
            source_route="/api/customer-automation/activation-webhook",
        )
    )

    assert result["ok"] is True
    assert result["source_status"] == "next_customer_activation_webhook"
    assert result["route_owner"] == "ai_crm_next"
    assert result["fallback_used"] is False
    assert result["real_external_call_executed"] is False
    assert result["side_effect_plan"]["adapter_mode"] == "local"
