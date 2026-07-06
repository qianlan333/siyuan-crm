# External Orders payment.succeeded Consumer Run-Due Runbook

This runbook describes how an operator can collect evidence for the
`payment.succeeded` internal-event consumers that block External Orders 90%+
evidence.

It does not authorize production writes by itself. It does not change deploy,
systemd, nginx, or environment files. It does not execute consumers, trigger
external effects, or run migrations from git.

## Safety Rules

- Preview first. Do not execute before reading the preview result.
- Prefer batch-size-one and single-consumer execution.
- Record operator approval before any non-dry-run action.
- Confirm token, auto-execute, and allowlist gates before execution.
- Confirm whether a consumer can create or reuse an external effect job.
- If external-effect planning may happen, collect a second approval for that
  consumer before execution.
- Record each consumer result independently.
- Only commit redacted evidence.
- Do not commit token, `Authorization` header, raw `external_userid`, mobile
  number, `openid`, `unionid`, full order number, customer secret, payment
  credential, corp secret, or access token.

## Scope

External Orders evidence currently depends on a `payment.succeeded` event for
an internal order. Expected consumers:

- `order_projection_consumer`
- `webhook_order_paid_consumer`
- `ai_audience_source_poke_consumer`
- `customer_business_summary_consumer`
- `dnd_policy_consumer`
- `ai_assist_notify_consumer`

The worker records `real_external_call_executed=false`; handlers that need
external work must enqueue an external effect job instead. The
`webhook_order_paid_consumer` can create or reuse a `webhook.order_paid.push`
external effect job, so it requires explicit external-effect risk review before
non-dry-run execution.

## Step 1: Readonly Diagnostic

Run:

```bash
.venv/bin/python scripts/diagnose_external_orders_blockers.py --order-id <internal_order_id>
```

Expected fields:

- `payment_succeeded_consumer_run_due.classification`
- `payment_succeeded_consumer_run_due.run_due_eligible`
- `payment_succeeded_consumer_run_due.preview_route_available`
- `payment_succeeded_consumer_run_due.run_route_available`
- `payment_succeeded_consumer_run_due.retry_route_available`
- `payment_succeeded_consumer_run_due.skip_route_available`
- `payment_succeeded_consumer_run_due.auto_execute_enabled`
- `payment_succeeded_consumer_run_due.token_gate_status`
- `payment_succeeded_consumer_run_due.allowlist_status`
- `payment_succeeded_consumer_run_due.real_external_call_risk`
- `payment_succeeded_consumer_run_due.production_write_risk`
- `payment_succeeded_consumer_run_due.recommended_execution_mode`

If classification is `run_due_blocked_by_token`,
`run_due_blocked_by_auto_execute_config`, or `run_due_blocked_by_allowlist`, stop
and resolve the gate outside git. Do not execute.

## Step 2: Preview

Preview must use the internal token in the approved environment. Do not paste
the token into git or the evidence report.

```bash
curl -sS -X POST "$BASE_URL/api/admin/internal-events/run-due/preview" \
  -H "Authorization: Bearer <redacted>" \
  -H "Content-Type: application/json" \
  -d '{
    "batch_size": 1,
    "event_types": ["payment.succeeded"],
    "consumer_names": ["<consumer_name>"]
  }'
```

Record only redacted preview evidence:

- event id redacted
- consumer name
- candidate count
- would execute
- aggregate type / internal numeric aggregate id
- no token or raw customer identifier

If preview shows no candidate, keep the evidence as `BLOCKED` or
`run_due_not_eligible` until the reason is understood.

## Step 3: Single-Consumer Dry Run

Use the single-consumer route in dry-run mode first:

```bash
curl -sS -X POST "$BASE_URL/api/admin/internal-events/<event_id>/consumers/<consumer_name>/run" \
  -H "Authorization: Bearer <redacted>" \
  -H "Content-Type: application/json" \
  -d '{
    "dry_run": true,
    "reason": "external-orders-payment-consumer-preview"
  }'
```

Expected:

- `dry_run=true`
- `real_external_call_executed=false`
- `counts.candidate_count=1`
- no production effect is executed

## Step 4: Non-Dry-Run Execution Approval

Before any non-dry-run execution, record outside git:

- operator name
- approval window
- exact event id, redacted for committed evidence
- exact consumer name
- reason
- rollback / follow-up owner
- whether external-effect planning can happen

For `webhook_order_paid_consumer`, collect a second approval because it can
create or reuse an external effect job. Do not execute it if the external effect
risk is not approved.

Preferred command shape:

```bash
curl -sS -X POST "$BASE_URL/api/admin/internal-events/<event_id>/consumers/<consumer_name>/run" \
  -H "Authorization: Bearer <redacted>" \
  -H "Content-Type: application/json" \
  -d '{
    "dry_run": false,
    "reason": "approved external orders evidence window"
  }'
```

Record only:

- consumer name
- terminal status (`succeeded`, `skipped`, `failed_retryable`,
  `failed_terminal`, or `blocked`)
- attempt id redacted
- error code / message if present
- whether retryable
- whether operator action is still required
- `real_external_call_executed=false`

## Step 5: Retry Or Skip

Retry is only for `failed_retryable`, `failed_terminal`, or `blocked` consumer
runs:

```bash
curl -sS -X POST "$BASE_URL/api/admin/internal-events/<event_id>/consumers/<consumer_name>/retry" \
  -H "Authorization: Bearer <redacted>" \
  -H "Content-Type: application/json" \
  -d '{}'
```

Skip is only allowed with an approved reason and redacted evidence:

```bash
curl -sS -X POST "$BASE_URL/api/admin/internal-events/<event_id>/consumers/<consumer_name>/skip" \
  -H "Authorization: Bearer <redacted>" \
  -H "Content-Type: application/json" \
  -d '{"reason": "approved non-applicable consumer for this evidence window"}'
```

Do not skip a consumer just to pass evidence. It must be explicitly
non-applicable or approved as operationally safe to skip.

## Step 6: Recollect Evidence

After each approved action, re-run:

```bash
.venv/bin/python scripts/diagnose_external_orders_blockers.py --order-id <internal_order_id>
```

Then rerun External Orders evidence collection and the business closeout
summary. External Orders cannot claim 90%+ unless:

- all expected consumers are `succeeded`, `skipped` with approved reason, or
  formally classified non-applicable;
- customer projection blocker is resolved or approved backfill path is complete;
- no blocking reason remains;
- closeout summary allows the claim.

## Classification Guide

| Classification | Meaning | Next action |
| --- | --- | --- |
| `run_due_ready_for_operator_preview` | Consumer rows are pending/due and gates look present. | Preview first, then execute one consumer only after approval. |
| `run_due_blocked_by_token` | Internal token gate is missing. | Configure token outside git before preview. |
| `run_due_blocked_by_auto_execute_config` | Run-due execute gate is disabled. | Use approved single-consumer path or update approved config outside git. |
| `run_due_blocked_by_allowlist` | Event/consumer allowlist is missing or incomplete. | Add approved allowlist outside git before execution. |
| `run_due_not_eligible` | Run is not currently due. | Wait or inspect retry schedule. |
| `consumer_already_succeeded` | No execution needed. | Recollect External Orders evidence. |
| `consumer_failed_retryable` | Retry path may be safe with approval. | Preview/retry in operator window. |
| `consumer_failed_terminal` | Manual review required. | Do not auto retry. |
| `consumer_explicitly_skippable` | Consumer may be non-applicable if approved. | Preview and skip only with reason. |
| `consumer_non_applicable` | Event is not `payment.succeeded`. | Keep outside External Orders evidence. |
| `runtime_repair_required` | Consumer run records or handlers are missing. | Create repair PR. |
| `unknown_requires_manual_review` | Classifier cannot decide safely. | Manual review before any action. |

## Evidence Template

Use redacted fields only:

```text
internal_order_id:
redacted_internal_event_id:
consumer_name:
before_status:
before_attempt_count:
preview_candidate_count:
dry_run_result:
operator_approval_evidence:
external_effect_risk_review:
after_status:
after_attempt_id:
retryable:
operator_action_required:
business_explanation:
real_external_call_executed:
production_write_executed:
sensitive_data_check:
- token_removed:
- authorization_header_removed:
- raw_external_userid_removed:
- mobile_removed:
- openid_unionid_removed:
- full_order_no_removed:
```

## Rollback

This runbook itself has no runtime rollback. Revert the PR if the documented
process is wrong.

For future approved execution, rollback depends on the consumer result:

- `order_projection_consumer`: collect corrective evidence; no external call
  should have happened.
- `webhook_order_paid_consumer`: inspect the external effect job it created or
  reused; cancel/retry according to external effect runbook if needed.
- `ai_audience_source_poke_consumer`: inspect dependent AI Audience packages and
  their `next_incremental_refresh_at` update evidence.
- skipped optional consumers: record the manual skip reason and retry only after
  a new approval.
