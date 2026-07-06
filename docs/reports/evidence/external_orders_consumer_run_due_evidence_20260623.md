# External Orders Consumer Run-Due Evidence - 2026-06-23

Verdict: `EVIDENCE_COLLECTED`

This report records approved production operator evidence for External Orders
order `156` after the remaining `payment.succeeded` internal-event consumer
blocker was processed. It also records the scoped customer read-model projection
repair required after #1339.

This report does not contain tokens, `Authorization` headers, raw
`external_userid`, phone numbers, `openid`, `unionid`, full order numbers,
customer secrets, or payment credentials.

## Scope

- Environment: production
- Review date: 2026-06-23
- Internal order id: `156`
- Source: External Orders / H5 WeChat Pay order evidence
- Redacted internal event id: `iev_***dff3`
- Event type: `payment.succeeded`
- Aggregate type: `wechat_pay_order`
- Operator approval: user authorized Codex to handle production operator
  evidence collection and repairs in the approved window.

## Safety Attestation

| Field | Result |
| --- | --- |
| Production deploy/systemd/nginx/env modified | `false` |
| Production migration executed | `false` |
| New route added | `false` |
| Token or authorization header logged | `false` |
| Raw customer/payment identifier committed | `false` |
| Internal-event consumer execution wrote consumer attempts | `true` |
| Customer read-model scoped backfill wrote target rows | `true` |
| External call executed by diagnostic / consumer worker | `false` |

Historical external effect attempts for this order already existed and recorded
HTTP 200 responses before this evidence window. This report did not execute
those historical outbound calls.

## Pre-Execution State

Before operator execution, the target event had six expected consumer runs, all
pending with no attempts and no error:

| Consumer | Before status | Attempt count |
| --- | --- | --- |
| `order_projection_consumer` | `pending` | `0` |
| `webhook_order_paid_consumer` | `pending` | `0` |
| `automation_payment_consumer` | `pending` | `0` |
| `customer_business_summary_consumer` | `pending` | `0` |
| `dnd_policy_consumer` | `pending` | `0` |
| `ai_assist_notify_consumer` | `pending` | `0` |

External effect risk review:

- Existing `webhook.order_paid.push` jobs were present: `95`, `96`.
- Both jobs were already `succeeded`.
- Both jobs had `webhook_url` configured in their payload.
- `webhook_order_paid_consumer` was expected to reuse an existing configured
  job rather than execute a real outbound call.

## Preview And Dry-Run Evidence

Single-consumer dry-run was performed for each consumer before execution.

| Consumer | Dry-run HTTP | Dry-run ok | Candidate count | Processed count | Real external call |
| --- | --- | --- | --- | --- | --- |
| `order_projection_consumer` | `200` | `true` | `1` | `0` | `false` |
| `webhook_order_paid_consumer` | `200` | `true` | `1` | `0` | `false` |
| `automation_payment_consumer` | `200` | `true` | `1` | `0` | `false` |
| `customer_business_summary_consumer` | `200` | `true` | `1` | `0` | `false` |
| `dnd_policy_consumer` | `200` | `true` | `1` | `0` | `false` |
| `ai_assist_notify_consumer` | `200` | `true` | `1` | `0` | `false` |

The generic run-due preview route is not event-specific and may surface another
due event when multiple events are pending. The exact-event single-consumer
dry-run above was used as the execution safety check for this event.

## Execution Evidence

Consumers were executed one at a time through the single-consumer run route with
an approved evidence-window reason.

| Consumer | After status | Attempt count | Attempt id | Error | Real external call |
| --- | --- | --- | --- | --- | --- |
| `order_projection_consumer` | `succeeded` | `1` | `iea_***ec48` | none | `false` |
| `webhook_order_paid_consumer` | `succeeded` | `1` | `iea_***796a` | none | `false` |
| `automation_payment_consumer` | `succeeded` | `1` | `iea_***92fa` | none | `false` |
| `customer_business_summary_consumer` | `skipped` | `1` | `iea_***9c91` | none | `false` |
| `dnd_policy_consumer` | `skipped` | `1` | `iea_***be46` | none | `false` |
| `ai_assist_notify_consumer` | `skipped` | `1` | `iea_***9273` | none | `false` |

Post-run classification:

- `payment_succeeded_consumer_run_due.classification=consumer_already_succeeded`
- `internal_event.classification=expected_not_applicable`
- `consumer_status.pending=0`
- `consumer_status.succeeded=3`
- `consumer_status.skipped=3`
- `operator_action_required=false`

## Customer Read-Model Projection Evidence

After consumer execution, the customer read-model target still needed scoped
repair:

- `projection_source_found=true`
- `projection_target_found=false`
- `customer_list_index_next_rows=0`
- `customer_detail_snapshot_next_rows=0`
- repair decision: `backfill_required`

A scoped production repair was performed for only the single redacted external
identity associated with order `156`.

Dry-run evidence before write:

- source customer found: `true`
- target before: `customer_list_index_next=0`,
  `customer_detail_snapshot_next=0`
- planned scope: single external identity for order `156`

Scoped write result:

| Target | Before | After |
| --- | --- | --- |
| `customer_list_index_next` | `0` | `1` |
| `customer_detail_snapshot_next` | `0` | `1` |

Post-repair classification:

- `customer_read_model_linkage_decision.projection_status=projection_fixed`
- `projection_source_found=true`
- `projection_target_found=true`
- `customer_list_index_next_lookup_result=1`
- `customer_detail_snapshot_next_lookup_result=1`
- `backfill_required=false`

The scoped repair did not execute internal-event consumers, external effects,
deploy changes, env changes, or migrations.

## External Effect / Push Center Evidence

External effect evidence remains linked:

| Field | Result |
| --- | --- |
| effect job count | `2` |
| attempt count | `2` |
| attempt statuses | `succeeded` |
| Push Center visibility | `true` |
| Push Center status | `sent` |
| External effect blocker | none |

## External Orders Scenario Evidence

Parameterized business closure diagnostic after the repairs:

| Field | Result |
| --- | --- |
| `status` | `order_linked` |
| `evidence_status` | `ORDER_LINKED_EVIDENCE_ATTACHED` |
| `request_mode` | `valid_token` |
| `route_owner` | `ai_crm_next` |
| `fallback_used` | `false` |
| `source` | `h5_checkout` |
| `internal_event_id` | `iev_***dff3` |
| `effect_job_id` | `external_effect_job:96` |
| `push_center_job_id` | `external_effect_job:96` |
| `consumer_status` | `succeeded_and_skipped` |
| `duplicate_handling` | `delivery_unique` |
| `retryable` | `false` |
| `operator_action_required` | `false` |
| `real_external_call_executed` | `false` |
| `production_write_executed` | `false` for diagnostic |

The diagnostic itself did not write production data. The production writes in
this evidence window were the approved single-consumer run results and the
scoped customer read-model projection repair described above.

## Decision

External Orders can move from `EVIDENCE_COLLECTED_NOT_READY` to
`EVIDENCE_COLLECTED`.

External Orders has order, auth, idempotency, customer/channel/source,
internal-event, consumer-run, Push Center, and admin visibility evidence
attached in redacted form.

This report does not claim global `PASS_90_PLUS`, because the business closure
closeout still requires the other core scenarios:

- Group Ops / Push Center
- Ops Plan -> Broadcast E2E
- WeCom Auth / Callback

## Sensitive Data Redaction Evidence

Not included:

- token
- `Authorization` header
- raw `external_userid`
- phone number
- `openid`
- `unionid`
- full order number
- customer secret
- payment credential
- request/response body with customer PII

## Next Action

Use this report as the External Orders evidence packet for the final business
closure closeout.

Remaining business closure evidence work:

1. Group Ops / Push Center real evidence
2. Ops Plan -> Broadcast E2E real evidence
3. WeCom Auth / Callback real evidence
4. Business Closure final closeout summary
