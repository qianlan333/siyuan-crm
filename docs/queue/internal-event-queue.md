# Internal Event Queue

Internal Event Queue records business facts and per-consumer execution state.
It is separate from the External Effect Queue.

## Data Model

- `internal_event` records a business fact, such as `payment.succeeded` or
  `questionnaire.submitted`.
- `internal_event_consumer_run` records one execution state per consumer for an
  event.
- `internal_event_consumer_attempt` records every consumer attempt.
- `external_effect_job` records only external side-effect work, such as webhook
  delivery. Internal events must not be stored in `external_effect_job`.

Consumers that need an external call must create an `external_effect_job` and
return. The internal event worker itself must not call external services.

## Configuration

Production defaults are safe:

```bash
AICRM_INTERNAL_EVENTS_ENABLED=0
AICRM_INTERNAL_EVENTS_PAYMENT_ENABLED=0
AICRM_INTERNAL_EVENTS_SHADOW_ONLY=1
AICRM_INTERNAL_EVENTS_ALLOWED_EVENT_TYPES=
AICRM_INTERNAL_EVENT_WORKER_BATCH_SIZE=50
```

Use `AICRM_INTERNAL_EVENTS_ALLOWED_EVENT_TYPES` to gray one event family at a
time:

```bash
export AICRM_INTERNAL_EVENTS_ALLOWED_EVENT_TYPES=payment.succeeded,questionnaire.submitted
```

## Admin APIs

以下写请求使用 `automation_worker` 换取的短期 JWT（`audience=internal_worker`、`scope=write`），通过环境变量 `AICRM_ACCESS_TOKEN` 注入；见 [`../auth_client_credentials.md`](../auth_client_credentials.md)。人员在后台操作时改用企微 Session + CSRF/action grant。

List and inspect events:

```bash
curl -sS "$BASE_URL/api/admin/internal-events?event_type=payment.succeeded"
curl -sS "$BASE_URL/api/admin/internal-events/$EVENT_ID"
curl -sS "$BASE_URL/api/admin/internal-events/diagnostics"
```

Preview due consumers:

```bash
curl -sS -X POST "$BASE_URL/api/admin/internal-events/run-due/preview" \
  -H "Authorization: Bearer $AICRM_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"batch_size":1,"event_types":["payment.succeeded"]}'
```

Dry-run due consumers:

```bash
curl -sS -X POST "$BASE_URL/api/admin/internal-events/run-due" \
  -H "Authorization: Bearer $AICRM_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"batch_size":1,"dry_run":true,"event_types":["payment.succeeded"]}'
```

Execute one allowed event type after gray approval:

```bash
curl -sS -X POST "$BASE_URL/api/admin/internal-events/run-due" \
  -H "Authorization: Bearer $AICRM_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"batch_size":1,"dry_run":false,"event_types":["payment.succeeded"],"consumer_names":["ai_audience_source_poke_consumer"]}'
```

Retry or skip a single consumer run:

```bash
curl -sS -X POST "$BASE_URL/api/admin/internal-events/$EVENT_ID/consumers/$CONSUMER_NAME/retry" \
  -H "X-Admin-Action-Token: $ADMIN_ACTION_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'

curl -sS -X POST "$BASE_URL/api/admin/internal-events/$EVENT_ID/consumers/$CONSUMER_NAME/skip" \
  -H "X-Admin-Action-Token: $ADMIN_ACTION_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason":"operator_confirmed_noop"}'
```

## Worker

The timer uses `scripts/run_internal_event_worker.py`. It defaults to dry-run:

```bash
python scripts/run_internal_event_worker.py --limit 50
```

Execute consumers only after config is enabled and shadow-only is disabled:

```bash
export AICRM_INTERNAL_EVENTS_ENABLED=1
export AICRM_INTERNAL_EVENTS_SHADOW_ONLY=0
export AICRM_INTERNAL_EVENTS_ALLOWED_EVENT_TYPES=payment.succeeded
python scripts/run_internal_event_worker.py --execute --limit 1 --event-types payment.succeeded
```
