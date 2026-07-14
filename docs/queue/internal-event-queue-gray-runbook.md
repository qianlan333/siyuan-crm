# Internal Event Queue Gray Runbook

This runbook mirrors the External Effect Queue gray pattern: disabled by
default, observable first, preview before execution, dry-run by default,
batch-size-one execution, and config-only rollback.

## Relationship To External Effect Queue

- `internal_event` records business facts.
- `internal_event_consumer_run` records each consumer's independent execution
  state.
- `internal_event_consumer_attempt` records every consumer attempt.
- `external_effect_job` records only external side-effect tasks.

Internal Event consumers must not perform external calls directly. A consumer
that needs webhook delivery, WeCom sending, or another external side effect must
create an `external_effect_job`.

## Default Safe Configuration

Keep production disabled until an approved gray window:

```bash
export AICRM_INTERNAL_EVENTS_ENABLED=0
export AICRM_INTERNAL_EVENTS_PAYMENT_ENABLED=0
export AICRM_INTERNAL_EVENTS_SHADOW_ONLY=1
export AICRM_INTERNAL_EVENTS_ALLOWED_EVENT_TYPES=
export AICRM_INTERNAL_EVENT_WORKER_BATCH_SIZE=50
```

Confirm diagnostics:

```bash
curl -sS "$BASE_URL/api/admin/internal-events/diagnostics" \
  | jq '{internal_events_enabled,payment_internal_events_enabled,shadow_only,allowed_event_types,worker_batch_size,due_count,failed_retryable_count,failed_terminal_count,oldest_pending_age_seconds}'
```

## payment.succeeded Gray Steps

1. Enable shadow emit only:

```bash
export AICRM_INTERNAL_EVENTS_ENABLED=1
export AICRM_INTERNAL_EVENTS_PAYMENT_ENABLED=1
export AICRM_INTERNAL_EVENTS_SHADOW_ONLY=1
export AICRM_INTERNAL_EVENTS_ALLOWED_EVENT_TYPES=payment.succeeded
```

2. Keep legacy direct automation enabled during the first shadow phase:

```bash
export AICRM_INTERNAL_EVENTS_PAYMENT_DISABLE_LEGACY_AUTOMATION_DIRECT=0
```

3. Trigger or wait for one paid notification, then inspect the event:

```bash
curl -sS "$BASE_URL/api/admin/internal-events?event_type=payment.succeeded&trace_id=$OUT_TRADE_NO" \
  | jq '{total,items}'
```

4. Preview consumers:

   `AICRM_ACCESS_TOKEN` 必须是 `automation_worker` 的短期 JWT（`audience=internal_worker`、`scope=write`）；见 [`../auth_client_credentials.md`](../auth_client_credentials.md)。

```bash
curl -sS -X POST "$BASE_URL/api/admin/internal-events/run-due/preview" \
  -H "Authorization: Bearer $AICRM_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"batch_size":1,"event_types":["payment.succeeded"]}' \
  | jq '{counts,dry_run,real_external_call_executed,items}'
```

5. Dry-run worker:

```bash
curl -sS -X POST "$BASE_URL/api/admin/internal-events/run-due" \
  -H "Authorization: Bearer $AICRM_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"batch_size":1,"dry_run":true,"event_types":["payment.succeeded"]}' \
  | jq '{counts,dry_run,real_external_call_executed}'
```

6. Batch-size-one `run_due` for a no-op/projection consumer first:

```bash
export AICRM_INTERNAL_EVENTS_SHADOW_ONLY=0

curl -sS -X POST "$BASE_URL/api/admin/internal-events/run-due" \
  -H "Authorization: Bearer $AICRM_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"batch_size":1,"dry_run":false,"event_types":["payment.succeeded"],"consumer_names":["order_projection_consumer"]}' \
  | jq '{counts,dry_run,items}'
```

7. Open the AI Audience source-poke consumer after projection checks pass:

```bash
curl -sS -X POST "$BASE_URL/api/admin/internal-events/run-due" \
  -H "Authorization: Bearer $AICRM_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"batch_size":1,"dry_run":false,"event_types":["payment.succeeded"],"consumer_names":["ai_audience_source_poke_consumer"]}' \
  | jq '{counts,items}'
```

8. Open the webhook external-effect consumer. This consumer must only create
   `external_effect_job`:

```bash
curl -sS -X POST "$BASE_URL/api/admin/internal-events/run-due" \
  -H "Authorization: Bearer $AICRM_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"batch_size":1,"dry_run":false,"event_types":["payment.succeeded"],"consumer_names":["webhook_order_paid_consumer"]}' \
  | jq '{counts,items}'
```

Then inspect External Effect Queue before any webhook execution:

```bash
curl -sS "$BASE_URL/api/admin/external-effects?effect_type=webhook.order_paid.push" \
  | jq '{total,items}'
```

9. Close the direct automation call only after the automation consumer is stable:

```bash
export AICRM_INTERNAL_EVENTS_PAYMENT_DISABLE_LEGACY_AUTOMATION_DIRECT=1
```

## Rollback

Rollback is config-only:

```bash
export AICRM_INTERNAL_EVENTS_PAYMENT_ENABLED=0
export AICRM_INTERNAL_EVENTS_SHADOW_ONLY=1
```

If needed, disable all internal event production writes and execution:

```bash
export AICRM_INTERNAL_EVENTS_ENABLED=0
export AICRM_INTERNAL_EVENTS_ALLOWED_EVENT_TYPES=
```

Keep `internal_event`, `internal_event_consumer_run`, and
`internal_event_consumer_attempt` rows for diagnosis. No schema rollback is
required.

## Troubleshooting

### failed_retryable

Inspect the event detail:

```bash
curl -sS "$BASE_URL/api/admin/internal-events/$EVENT_ID" \
  | jq '{event,consumers,attempts}'
```

Retry after the dependency or payload issue is understood:

```bash
curl -sS -X POST "$BASE_URL/api/admin/internal-events/$EVENT_ID/consumers/$CONSUMER_NAME/retry" \
  -H "X-Admin-Action-Token: $ADMIN_ACTION_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'
```

Run preview again before execution.

### skipped

`skipped` means the consumer intentionally did no work, usually because the
feature is not configured, the event is not applicable, or the current phase is
shadow-only. Check `result_summary_json.reason` and the latest attempt response.

If an operator confirms that a pending consumer should not run, mark just that
consumer skipped:

```bash
curl -sS -X POST "$BASE_URL/api/admin/internal-events/$EVENT_ID/consumers/$CONSUMER_NAME/skip" \
  -H "X-Admin-Action-Token: $ADMIN_ACTION_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason":"operator_confirmed_noop"}'
```

### duplicate event

Duplicate emits should resolve through `(tenant_id, idempotency_key)`:

```bash
curl -sS "$BASE_URL/api/admin/internal-events?idempotency_key=payment.succeeded:$OUT_TRADE_NO" \
  | jq '{total,items}'
```

There should be one event and one `consumer_run` per registered consumer.

### stuck running

If a consumer remains `running`, first check whether the lock is still fresh:

```bash
curl -sS "$BASE_URL/api/admin/internal-events/diagnostics" \
  | jq '{due_count,oldest_pending_age_seconds,queue_metrics}'
```

The repository's due scan ignores fresh locks. Wait for lock timeout before
retrying. If the lock is stale and operationally approved, release it with a
database update scoped to the single consumer run:

```sql
UPDATE internal_event_consumer_run
SET status = 'pending', locked_at = NULL, locked_by = '', updated_at = CURRENT_TIMESTAMP
WHERE event_id = :event_id
  AND consumer_name = :consumer_name
  AND status = 'running';
```

Then preview and retry the single consumer.
