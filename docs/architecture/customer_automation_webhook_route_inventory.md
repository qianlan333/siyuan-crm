# Customer Automation Webhook Route Inventory

## Caller ↔ API ↔ CommandBus ↔ SideEffectPlan Matrix

| Caller surface | API route | Next handler | CommandBus command | SideEffectPlan / attempt | Response contract |
| --- | --- | --- | --- | --- | --- |
| Activation webhook producer | `POST /api/customers/automation/activation-webhook` | `api_customer_automation_activation_webhook` | `ApplyCustomerActivationWebhookCommand` | `adapter_mode=local`, `requires_approval=false`, no outbound webhook attempt | `source_status=next_customer_activation_webhook`, `customer_automation_applied=local_only`, `real_external_call_executed=false`, `outbound_webhook_executed=false` |
| Admin delivery retry action | `POST /api/customers/automation/webhook-deliveries/{delivery_id}/retry` | `api_plan_customer_automation_webhook_delivery_retry` | `PlanCustomerWebhookDeliveryRetryCommand` | `adapter_mode=real_blocked`, `requires_approval=true`, blocked `ExternalCallAttempt` | `source_status=next_customer_webhook_retry_plan`, `status=planned_blocked`, `retried_count=0`, `outbound_webhook_executed=false` |
| Timer/manual due retry action | `POST /api/customers/automation/webhook-deliveries/retry-due` | `api_plan_customer_automation_webhook_delivery_retry_due` | `PlanCustomerWebhookDeliveryRetryDueCommand` | `adapter_mode=real_blocked`, `requires_approval=true`, blocked `ExternalCallAttempt` | `source_status=next_customer_webhook_retry_due_plan`, `status=planned_blocked`, `retried_count=0`, `outbound_webhook_executed=false` |
| Preflight | `OPTIONS /api/customers/automation/activation-webhook` | `api_customer_automation_activation_webhook_options` | none | diagnostics only | `allowed_methods=["POST","OPTIONS"]`, `fallback_used=false` |
| Preflight | `OPTIONS /api/customers/automation/webhook-deliveries/{delivery_id}/retry` | `api_customer_automation_webhook_delivery_retry_options` | none | diagnostics only | `allowed_methods=["POST","OPTIONS"]`, `fallback_used=false` |
| Preflight | `OPTIONS /api/customers/automation/webhook-deliveries/retry-due` | `api_customer_automation_webhook_delivery_retry_due_options` | none | diagnostics only | `allowed_methods=["POST","OPTIONS"]`, `fallback_used=false` |

## Deletion Boundary

These plural customer automation webhook write routes are `legacy_fallback_allowed=false` and `deletion_locked`.

The exact production_compat decorators for the three routes have been removed from `aicrm_next/production_compat/api.py`. The Next replacement does not call the legacy Flask customer automation blueprint and does not import legacy application commands.

The locked safe-mode response must continue to expose:

- `route_owner=ai_crm_next`
- `fallback_used=false`
- `real_external_call_executed=false`
- `outbound_webhook_executed=false`
- `automation_runtime_executed=false`
- `wecom_send_executed=false`
- `adapter_mode=local` for activation local projection
- `adapter_mode=real_blocked` for retry and retry-due delivery plans

## Out Of Scope

`GET /api/customers/automation/webhook-deliveries` remains a separate Next readonly facade. The old singular `POST /api/customer-automation/activation-webhook` remains outside this group and is not used as rollback for the plural customer automation webhook routes.
