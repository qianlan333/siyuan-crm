# Internal Event payment.succeeded Worker Gray Runbook

This runbook is for GitHub issue #1267. It enables batch_size=1 automatic execution for selected `payment.succeeded` consumers while keeping External Effect real execution disabled.

## Current Production State

Expected starting state:

```bash
export AICRM_INTERNAL_EVENTS_ENABLED=1
export AICRM_INTERNAL_EVENTS_PAYMENT_ENABLED=1
export AICRM_INTERNAL_EVENTS_PAYMENT_DISABLE_LEGACY_AUTOMATION_DIRECT=1
export AICRM_INTERNAL_EVENTS_SHADOW_ONLY=1
export AICRM_INTERNAL_EVENTS_ALLOWED_EVENT_TYPES=payment.succeeded
export AICRM_INTERNAL_EVENTS_AUTO_EXECUTE=0
export AICRM_EXTERNAL_EFFECT_WEBHOOK_EXECUTE=0
export AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES=
```

External Effect must stay disabled during this gray run. The Internal Event Worker must not trigger real webhook, WeCom, Feishu, payment query, or refund actions.

## Configuration Gates

The worker execute path requires all of these gates:

```bash
export AICRM_INTERNAL_EVENTS_AUTO_EXECUTE=1
export AICRM_INTERNAL_EVENTS_ALLOWED_EVENT_TYPES=payment.succeeded
export AICRM_INTERNAL_EVENTS_ALLOWED_EVENT_CONSUMERS=payment.succeeded:order_projection_consumer,payment.succeeded:customer_business_summary_consumer,payment.succeeded:dnd_policy_consumer,payment.succeeded:ai_assist_notify_consumer
export AICRM_INTERNAL_EVENTS_ALLOWED_CONSUMERS=order_projection_consumer,customer_business_summary_consumer,dnd_policy_consumer,ai_assist_notify_consumer
export AICRM_INTERNAL_EVENTS_WORKER_BATCH_SIZE=1
export AICRM_INTERNAL_EVENTS_AUTO_EXECUTE_MAX_BATCH_SIZE=1
```

`AICRM_INTERNAL_EVENT_WORKER_BATCH_SIZE` is still accepted as a legacy fallback, but the plural `AICRM_INTERNAL_EVENTS_WORKER_BATCH_SIZE` should be used for this rollout.

`AICRM_INTERNAL_EVENTS_ALLOWED_EVENT_CONSUMERS` is the preferred production gate. It is pair-aware: every entry names one `event_type:consumer_name` pair. This matters when a generic consumer such as `ai_assist_notify_consumer` is registered on multiple event types. A consumer-name-only allowlist can accidentally make the same consumer executable for newly enabled event families; the pair allowlist keeps `payment.succeeded:ai_assist_notify_consumer` separate from `customer.tagged:ai_assist_notify_consumer`.

When `AICRM_INTERNAL_EVENTS_ALLOWED_EVENT_CONSUMERS` is non-empty, it has priority over `AICRM_INTERNAL_EVENTS_ALLOWED_CONSUMERS`. The legacy consumer-name allowlist is kept for single-event compatibility, but production multi-event auto-execute should use pair-aware entries.

## Stage 1

Stage 1 only allows no-op/projection consumers:

```bash
export AICRM_INTERNAL_EVENTS_ALLOWED_CONSUMERS=order_projection_consumer,customer_business_summary_consumer,dnd_policy_consumer,ai_assist_notify_consumer
export AICRM_INTERNAL_EVENTS_ALLOWED_EVENT_CONSUMERS=payment.succeeded:order_projection_consumer,payment.succeeded:customer_business_summary_consumer,payment.succeeded:dnd_policy_consumer,payment.succeeded:ai_assist_notify_consumer
```

Expected results:

- `order_projection_consumer`: `succeeded`
- `customer_business_summary_consumer`: `skipped`, reason `summary_refresh_not_configured`
- `dnd_policy_consumer`: `skipped`, reason `dnd_policy_not_configured`
- `ai_assist_notify_consumer`: `skipped`, reason `ai_assist_notify_not_configured`

## Stage 2

Stage 2 adds AI Audience source-poke after Stage 1 is stable:

```bash
export AICRM_INTERNAL_EVENTS_ALLOWED_CONSUMERS=order_projection_consumer,customer_business_summary_consumer,dnd_policy_consumer,ai_assist_notify_consumer,ai_audience_source_poke_consumer
export AICRM_INTERNAL_EVENTS_ALLOWED_EVENT_CONSUMERS=payment.succeeded:order_projection_consumer,payment.succeeded:customer_business_summary_consumer,payment.succeeded:dnd_policy_consumer,payment.succeeded:ai_assist_notify_consumer,payment.succeeded:ai_audience_source_poke_consumer
```

Expected result:

- `ai_audience_source_poke_consumer`: `succeeded`, and any dependent AI Audience package may have `next_incremental_refresh_at` moved forward.

## Stage 3

Stage 3 may add the webhook planner only after Stage 2 is stable:

```bash
export AICRM_INTERNAL_EVENTS_ALLOWED_CONSUMERS=order_projection_consumer,customer_business_summary_consumer,dnd_policy_consumer,ai_assist_notify_consumer,ai_audience_source_poke_consumer,webhook_order_paid_consumer
export AICRM_INTERNAL_EVENTS_ALLOWED_EVENT_CONSUMERS=payment.succeeded:order_projection_consumer,payment.succeeded:customer_business_summary_consumer,payment.succeeded:dnd_policy_consumer,payment.succeeded:ai_assist_notify_consumer,payment.succeeded:ai_audience_source_poke_consumer,payment.succeeded:webhook_order_paid_consumer
```

The webhook consumer may create or reuse a `webhook.order_paid.push` `external_effect_job`, but it must not dispatch `external_effect_attempt`. The job must remain `execution_mode=shadow` and `status=planned` or another safe non-executing state.

## Diagnostics

Check effective gates:

```bash
curl -sS "$BASE_URL/api/admin/internal-events/diagnostics" \
  -H "Authorization: Bearer $INTERNAL_TOKEN" | jq '{
    auto_execute_enabled,
    shadow_only,
    allowed_event_types,
    allowed_consumers,
    allowed_event_consumers,
    pair_allowlist_enabled,
    worker_batch_size,
    due_count,
    due_count_by_event_type,
    due_count_by_consumer,
    blocked_by_config_count,
    blocked_by_pair_allowlist_count,
    config_warnings,
    real_external_call_executed
  }'
```

Check External Effect remains disabled:

```bash
curl -sS "$BASE_URL/api/admin/external-effects/diagnostics" \
  -H "Authorization: Bearer $INTERNAL_TOKEN" | jq '{
    real_execution_enabled,
    execution_mode,
    allowed_effect_types,
    real_external_call_executed
  }'
```

Expected:

- `auto_execute_enabled=true` only during the gray execute window.
- `allowed_event_types=["payment.succeeded"]`.
- `allowed_event_consumers` contains only the current stage `payment.succeeded:<consumer>` pairs.
- `pair_allowlist_enabled=true` when multiple internal event families are enabled in production.
- `worker_batch_size=1`.
- `real_external_call_executed=false`.
- External Effect `real_execution_enabled=false`.

If diagnostics shows `auto_execute_multi_event_without_pair_allowlist`, stop execute and set `AICRM_INTERNAL_EVENTS_ALLOWED_EVENT_CONSUMERS` before continuing.

## Preview

Preview must run before dry-run and execute:

```bash
curl -sS -X POST "$BASE_URL/api/admin/internal-events/run-due/preview" \
  -H "Authorization: Bearer $INTERNAL_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "batch_size": 1,
    "event_types": ["payment.succeeded"]
  }' | jq .
```

Expected:

- `dry_run=true`
- `counts.candidate_count` is `0` or `1`
- Each item shows `event_id`, `consumer_name`, and `would_execute=true`
- `real_external_call_executed=false`
- No `internal_event_consumer_attempt` is created

## Dry Run

Dry-run uses the same filter but does not execute handlers:

```bash
curl -sS -X POST "$BASE_URL/api/admin/internal-events/run-due" \
  -H "Authorization: Bearer $INTERNAL_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "batch_size": 1,
    "dry_run": true,
    "event_types": ["payment.succeeded"]
  }' | jq .
```

Expected:

- `dry_run=true`
- `counts.processed_count=0`
- `real_external_call_executed=false`
- No handler is called
- No external effect attempt is created

## Execute

Execute only when preview and dry-run are clean:

```bash
curl -sS -X POST "$BASE_URL/api/admin/internal-events/run-due" \
  -H "Authorization: Bearer $INTERNAL_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "batch_size": 1,
    "dry_run": false,
    "event_types": ["payment.succeeded"]
  }' | jq .
```

Expected:

- `dry_run=false`
- `counts.candidate_count=1`
- `counts.processed_count=1`
- `processed[0].event_id` is the processed event
- `processed[0].consumer_name` is in `AICRM_INTERNAL_EVENTS_ALLOWED_CONSUMERS`
- `processed[0].attempt_id` is present
- `real_external_call_executed=false`

If `batch_size` is greater than `AICRM_INTERNAL_EVENTS_AUTO_EXECUTE_MAX_BATCH_SIZE`, execute is rejected with `batch_size_exceeds_auto_execute_limit`.

## Proving It Does Not Scan The Whole Queue

The execute path applies filters before locking:

- `event_type` must match `AICRM_INTERNAL_EVENTS_ALLOWED_EVENT_TYPES`.
- If `AICRM_INTERNAL_EVENTS_ALLOWED_EVENT_CONSUMERS` is set, `event_type:consumer_name` must match one configured pair.
- If the pair allowlist is empty, `consumer_name` must match `AICRM_INTERNAL_EVENTS_ALLOWED_CONSUMERS`.
- Requested API filters are intersected with configured allowlists.
- An empty intersection returns zero candidates, not an unfiltered scan.
- Only executable statuses are considered: `pending`, `failed_retryable`, `failed_terminal`, `blocked`.
- `succeeded` and `skipped` are not acquired again.

Example: keep payment automation enabled while also allowing `questionnaire.submitted` and customer-tag events to emit:

```bash
export AICRM_INTERNAL_EVENTS_ALLOWED_EVENT_TYPES=payment.succeeded,questionnaire.submitted,customer.tagged,customer.untagged
export AICRM_INTERNAL_EVENTS_ALLOWED_EVENT_CONSUMERS=payment.succeeded:order_projection_consumer,payment.succeeded:customer_business_summary_consumer,payment.succeeded:dnd_policy_consumer,payment.succeeded:ai_assist_notify_consumer,payment.succeeded:ai_audience_source_poke_consumer
```

With that configuration, `customer.tagged:ai_assist_notify_consumer` remains blocked even though `ai_assist_notify_consumer` is allowed for `payment.succeeded`.

Use diagnostics to compare:

```bash
curl -sS "$BASE_URL/api/admin/internal-events/diagnostics" \
  -H "Authorization: Bearer $INTERNAL_TOKEN" | jq '{
    due_count,
    effective_queue_metrics,
    blocked_by_config_count,
    blocked_by_pair_allowlist_count
  }'
```

`blocked_by_config_count` shows due work intentionally excluded by the allowlists.

## Confirming No Real External Call

Before and after each execute:

```bash
curl -sS "$BASE_URL/api/admin/external-effects/diagnostics" \
  -H "Authorization: Bearer $INTERNAL_TOKEN" | jq '.real_execution_enabled,.allowed_effect_types,.real_external_call_executed'
```

For webhook planner validation:

```sql
SELECT id, effect_type, status, execution_mode, attempt_count
FROM external_effect_job
WHERE effect_type = 'webhook.order_paid.push'
ORDER BY id DESC
LIMIT 10;
```

Expected:

- `real_execution_enabled=false`
- `allowed_effect_types=[]`
- `real_external_call_executed=false`
- `external_effect_attempt` count does not increase
- Webhook jobs stay `shadow` and `planned` or another safe non-executing state

## Rollback To Manual Single-Consumer Mode

Disable automatic due execution:

```bash
export AICRM_INTERNAL_EVENTS_AUTO_EXECUTE=0
export AICRM_INTERNAL_EVENTS_ALLOWED_CONSUMERS=
export AICRM_INTERNAL_EVENTS_ALLOWED_EVENT_CONSUMERS=
```

Restart or reload the app/worker process that reads env. The manual endpoint remains available:

```bash
curl -sS -X POST "$BASE_URL/api/admin/internal-events/{event_id}/consumers/{consumer_name}/run" \
  -H "Authorization: Bearer $INTERNAL_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "dry_run": true,
    "force": false,
    "reason": "rollback_manual_single_consumer_check"
  }' | jq .
```

Do not enable External Effect real execution during rollback.

## PASS / WARN / FAIL

PASS:

- Preview, dry-run, and execute process at most one configured `payment.succeeded` consumer.
- Stage consumers finish with the expected `succeeded` or `skipped` statuses.
- No `failed_terminal`, stale lock, duplicate automation event, duplicate webhook job, or external effect attempt.
- `real_external_call_executed=false` throughout.

WARN:

- Candidates are absent because there is no new `payment.succeeded` due work.
- Small `failed_retryable` counts have clear reasons and can be retried manually.
- Expected no-op consumers are `skipped` with clear reasons.

FAIL:

- Execute processes a non-payment event type or a consumer outside the allowlist.
- `batch_size>1` executes during this phase.
- Any real webhook, WeCom, Feishu, payment query, or refund is triggered.
- External Effect real execution becomes enabled.
- A consumer reaches `failed_terminal`.
- The worker repeatedly crashes or leaves stale locks.
