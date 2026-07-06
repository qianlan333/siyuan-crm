# External Orders Enablement Evidence - 2026-06-22

Verdict: `EVIDENCE_COLLECTED_NOT_READY`

This report records production readonly evidence for External Orders enablement.
It does not contain tokens, `Authorization` headers, raw external user ids,
phone numbers, receiver identifiers, or customer secrets. The evidence was
collected through readonly HTTP GET probes and readonly PostgreSQL
transactions. No production write, migration, deploy change, env change, or
external call was executed by the diagnostic commands.

## Operator And Window

- Operator: redacted operator / Codex readonly evidence collection
- Review date: 2026-06-22
- Gray window: existing production evidence discovered by readonly inspection
- Environment: production
- Source system: External Orders / WeChat Pay order external push
- Approval reference: not provided in this evidence packet

## Safety Attestation

- Diagnostic `real_external_call_executed`: `false`
- Diagnostic `production_write_executed`: `false`
- `deploy_or_env_modified`: `false`
- Token configured: `true`
- Token value logged: `false`
- Request token redacted: `true`
- No raw phone number / raw external_userid / `Authorization` header included:
  `true`
- Production DB access mode: readonly queries only

## Evidence Sources

- External Orders no-token probe:
  `GET /api/external/orders`
- External Orders wrong-token probe:
  `GET /api/external/orders` with a dummy invalid bearer token
- External Orders valid-token list probe:
  `GET /api/external/orders?limit=3`
- External Orders valid-token detail probe:
  `GET /api/external/orders/156`
- Admin order visibility:
  `GET /admin/wechat-pay/transactions/156`
- Admin order API visibility:
  `GET /api/admin/orders?provider=wechat&order_no=<redacted_order_no>&limit=5`
- Delivery visibility:
  `GET /api/admin/wechat-pay/orders/156/external-push-deliveries`
- Push Center reconciliation:
  `GET /api/admin/push-center/jobs/96/reconciliation`
- PostgreSQL readonly transaction for order, delivery, effect, event, and
  linkage checks

## Evidence Payload

| Field | Value | Notes |
| --- | --- | --- |
| `token_configured` | `true` | Confirmed from production process env without printing token. |
| `token_redacted` | `true` | Token value is not included. |
| `token_never_logged` | `true` | Commands only printed configured booleans and HTTP result summaries. |
| `auth_status` | `valid_token_readiness_collected` | No-token and wrong-token failures also collected. |
| `route_owner` | `ai_crm_next` | External Orders and Push Center routes returned Next owner. |
| `fallback_used` | `false` | External Orders list/detail returned `fallback_used=false`. |
| `controlled_disabled_reason` | `not_applicable_token_configured` | Token is configured in production. |
| `request_mode` | `no_token`, `wrong_token`, `valid_token` | All three auth modes were checked. |
| `order_id` | `156` | Internal order id; no customer PII included. |
| `external_order_id` | `WXP***C2` | Redacted order number from valid-token API detail/list. |
| `idempotency_key` | `external-push:deliv_***FVp6:2:external-effect` | Redacted key from Push Center reconciliation. |
| `customer_id` | `not_collected` | Customer read model row was not linked for this order. |
| `channel_id` | `redacted_channel_present` | Readonly DB query found one channel id via channel contact linkage. |
| `source` | `h5_checkout` | From `wechat_pay_orders.order_source`. |
| `internal_event_id` | `iev_***dff3` | Redacted internal event id exists for order 156. |
| `admin_order_visibility` | `visible` | Admin detail page and admin orders API both show order 156. |
| `reconciliation_status` | `sent` | Push Center job #96 is sent. |
| `retryable` | `false` | Push Center reconciliation says no retry needed. |
| `operator_action_required` | `true` | Internal event consumers remain pending; customer read model link is missing. |
| `business_explanation` | `Order external push succeeded, but the full 90%+ business closure evidence is not ready until pending internal consumers and customer linkage are resolved or accepted as non-blocking.` | Business-readable summary. |

## Auth Evidence

| Mode | Result |
| --- | --- |
| No token | `401 missing_internal_token`, `route_owner=ai_crm_next`, `fallback_used=false` |
| Wrong token | `401 invalid_internal_token`, `route_owner=ai_crm_next`, `fallback_used=false` |
| Valid token list | `200`, `total=223`, `has_more=true`, `route_owner=ai_crm_next`, `fallback_used=false` |
| Valid token detail for order 156 | `200`, `source_status=external_order_detail`, `fallback_used=false` |

Sensitive fields were present in the valid-token detail payload, but their raw
values were not copied into this report.

## Push Center Reconciliation Evidence

| Field | Value |
| --- | --- |
| `push_center_job_id` | `external_effect_job:96` |
| `display_id` | `#96` |
| `effective_status` | `sent` |
| `effective_status_label` | `已发送` |
| `business_explanation` | `主发送链路已完成，当前不需要运营处理。` |
| `retryable` | `false` |
| `operator_action_required` | `false` |
| `next_action_label` | `无需操作` |
| `business_type` | `commerce_order` |
| `business_id` | `156` |
| `target_type` | `external_push_delivery` |
| `target_id` | `deliv_***FVp6` |
| `trace_id` | `deliv_***FVp6` |
| `linked_external_effect_jobs` | `2` |
| `linked_external_effect_attempts` | `2` |
| `broadcast_jobs` | `0` |
| `outbound_tasks` | `0` |

Linked external effect jobs:

| Job id | Status | Execution mode | Effect type | Last error |
| --- | --- | --- | --- | --- |
| `96` | `succeeded` | `execute` | `webhook.order_paid.push` | none |
| `95` | `succeeded` | `execute` | `webhook.order_paid.push` | none |

Linked attempts:

| Attempt row id | Attempt id | Job id | Status | Adapter mode | Error |
| --- | --- | --- | --- | --- | --- |
| `97` | `eea_***78d2` | `96` | `succeeded` / `sent` | `execute` | none |
| `96` | `eea_***6c71` | `95` | `succeeded` / `sent` | `execute` | none |

Historical attempt summaries showed `status_code=200` and
`real_external_call_executed=true` for both attempts. This report did not execute
those calls; it only read their recorded summaries.

## Idempotency Evidence

| Evidence | Value |
| --- | --- |
| Delivery unique indexes | `external_push_delivery_delivery_id_key`, `uq_external_push_delivery_config_order_event` |
| Transaction paid delivery count for order 156 | `1` |
| Distinct delivery count for order 156 | `1` |
| Duplicate delivery detected | `false` |
| External effect job idempotency present | `true` for jobs 95 and 96 |
| Internal event idempotency present | `true` for event `iev_***dff3` |

This is structural and record-count idempotency evidence. It is not a new
duplicate request execution.

## Order Linkage Evidence

| Field | Value | Notes |
| --- | --- | --- |
| Order projection visible | `true` | Valid-token External Orders API and admin API both returned order 156. |
| Payment status | `paid` | `trade_state=SUCCESS`. |
| Product code | `premium_monthly_trial` | Not a secret. |
| Source linked | `h5_checkout` | From production order row. |
| External user id present | `true` | Raw value not included. |
| Customer read model linked | `false` | `customer_list_index_next` rows: `0`. |
| Channel linked | `true` | Channel contact rows: `1`; channel id value redacted. |
| Admin order visibility | `visible` | `/admin/wechat-pay/transactions/156` and `/api/admin/orders?...` are visible. |
| External push delivery visible | `true` | Delivery row exists for order 156. |
| Internal event linked | `true` | `payment.succeeded` internal event exists. |

## Internal Event Evidence

Internal event:

| Field | Value |
| --- | --- |
| `internal_event_id` | `iev_***dff3` |
| `event_type` | `payment.succeeded` |
| `aggregate_type` | `wechat_pay_order` |
| `aggregate_id` | `156` |
| `source_module` | `public_product.h5_wechat_pay` |
| `source_route` | `/api/h5/wechat-pay/notify` |
| `idempotency_present` | `true` |

Consumer run state for this event:

| Consumer | Status | Attempt count | Error |
| --- | --- | --- | --- |
| `order_projection_consumer` | `pending` | `0` | none |
| `webhook_order_paid_consumer` | `pending` | `0` | none |
| `automation_payment_consumer` | `pending` | `0` | none |
| `customer_business_summary_consumer` | `pending` | `0` | none |
| `dnd_policy_consumer` | `pending` | `0` | none |
| `ai_assist_notify_consumer` | `pending` | `0` | none |

These pending consumers are the main reason this evidence packet is not marked
as 90%+ ready.

## Blocking Reason Matrix

| Code | Present? | Evidence / next action |
| --- | --- | --- |
| `missing_internal_token_config` | No | Production token is configured, value not logged. |
| `missing_request_token` | No | No-token path returns controlled 401. |
| `invalid_request_token` | No | Wrong-token path returns controlled 401. |
| `token_configured_but_not_executed` | No | Valid-token list/detail readonly probes succeeded. |
| `missing_order_evidence` | No | Order 156 evidence collected. |
| `missing_idempotency_evidence` | No | Unique delivery count and idempotency-present checks collected. |
| `missing_customer_channel_link` | Partially | Channel link exists; customer read model row is missing. |
| `missing_internal_event` | No | `payment.succeeded` event exists. |
| `missing_admin_visibility` | No | Admin page/API visibility confirmed. |
| `order_linked` | Partially | Order, channel, event, and push center linked; customer read model and consumer runs remain incomplete. |

## Decision

Result: `EVIDENCE_COLLECTED_NOT_READY`

Do not claim `PASS_WITH_NOTES`, `PASS_90_PLUS_CANDIDATE`, or `PASS_90_PLUS` from
this evidence packet.

Reasons:

- All External Orders auth modes were tested without exposing token values.
- Push Center reconciliation proves the external order push succeeded.
- Admin order visibility exists.
- Idempotency evidence exists at the delivery and effect/event layers.
- However, internal event consumers for the order remain `pending`.
- The customer read model link was not found, although channel contact linkage
  exists.

Next operator action:

1. Resolve or intentionally classify pending internal event consumers for event
   `iev_***dff3`.
2. Confirm whether missing `customer_list_index_next` linkage is expected for
   this order/customer, or backfill/repair it through an approved runtime path.
3. Re-run the External Orders evidence diagnostic and Business Closure closeout
   summary after the above is resolved.
