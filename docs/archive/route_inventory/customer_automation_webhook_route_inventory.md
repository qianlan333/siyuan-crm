# Customer Automation Webhook Route Inventory

## Retired Route Matrix

The legacy customer automation webhook surfaces are retired. They remain
registered only as explicit tombstone routes so old callers receive a
deterministic `410 legacy_customer_automation_retired` response instead of a
silent fallback.

| Caller surface | API route | Next handler | Response |
| --- | --- | --- | --- |
| Activation webhook producer | `POST /api/customers/automation/activation-webhook` | `api_customer_automation_activation_webhook` | `410 legacy_customer_automation_retired` |
| Activation webhook preflight | `OPTIONS /api/customers/automation/activation-webhook` | `api_customer_automation_activation_webhook_options` | `410 legacy_customer_automation_retired` |
| Delivery retry action | `POST /api/customers/automation/webhook-deliveries/{delivery_id}/retry` | `api_plan_customer_automation_webhook_delivery_retry` | `410 legacy_customer_automation_retired` |
| Delivery retry preflight | `OPTIONS /api/customers/automation/webhook-deliveries/{delivery_id}/retry` | `api_customer_automation_webhook_delivery_retry_options` | `410 legacy_customer_automation_retired` |
| Due retry action | `POST /api/customers/automation/webhook-deliveries/retry-due` | `api_plan_customer_automation_webhook_delivery_retry_due` | `410 legacy_customer_automation_retired` |
| Due retry preflight | `OPTIONS /api/customers/automation/webhook-deliveries/retry-due` | `api_customer_automation_webhook_delivery_retry_due_options` | `410 legacy_customer_automation_retired` |
| Singular activation webhook | `POST /api/customer-automation/activation-webhook` | `activation_webhook` | `410 legacy_customer_automation_retired` |
| Signup conversion batches | `GET /api/customers/automation/signup-conversion/batches` | `signup_conversion_batches` | `410 legacy_customer_automation_retired` |
| Signup conversion batch detail | `GET /api/customers/automation/signup-conversion/batches/{batch_id}` | `signup_conversion_batch` | `410 legacy_customer_automation_retired` |
| Webhook delivery inventory | `GET /api/customers/automation/webhook-deliveries` | `customer_automation_webhook_deliveries` | `410 legacy_customer_automation_retired` |

## Deletion Boundary

These routes are `legacy_fallback_allowed=false`.

The retired handlers do not call the retired customer automation commands,
read models, Runtime V2 membership/task planning, or external effect planning.
This document proves the route surface does not call the retired customer automation commands.
external_effect_job 不会被创建.

Every response must keep the following no-side-effect flags:

- `route_owner=ai_crm_next`
- `fallback_used=false`
- `real_external_call_executed=false`
- `outbound_webhook_executed=false`
- `automation_runtime_executed=false`
- `wecom_send_executed=false`

## Current Replacement Paths

- Use `ai_audience_ops` for SQL audience refresh, member events, and outbound
  planning.
- Use `platform_foundation.internal_events` and `external_effects` as the
  shared event and side-effect queues.
- Use `automation_engine/group_ops` for group operation plans.
- Keep Agent copywriting/log/output capabilities through the dedicated Agent
  surfaces; they are not rollback paths for these old customer automation
  webhook routes.
