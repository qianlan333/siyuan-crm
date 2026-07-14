# External Effect Queue Gray Runbook

The External Effect Queue records standardized external-action jobs in
`external_effect_job` and execution attempts in `external_effect_attempt`.
Production real execution is disabled by default. P0-1D only permits gray
execution for these low-risk webhook effect types:

- `webhook.questionnaire_submission.push`
- `webhook.order_paid.push`

Do not enable real execution for WeCom private messages, group sends, group
messages, welcome messages, tag mutations, payment queries, Feishu, OpenClaw, or
MCP effects through this runbook.

## Default Disabled Configuration

Leave webhook execution disabled unless a gray window has been approved:

```bash
unset AICRM_EXTERNAL_EFFECT_WEBHOOK_EXECUTE
unset AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES
```

Equivalent explicit disabled configuration:

```bash
AICRM_EXTERNAL_EFFECT_WEBHOOK_EXECUTE=0
AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES=
```

Expected diagnostics:

```bash
curl -sS "$BASE_URL/api/admin/external-effects/diagnostics" \
  | jq '.real_execution_enabled,.execution_mode,.allowed_effect_types'
```

Expected values:

```json
false
"disabled"
[]
```

## Observability Checks

Use diagnostics before and after any gray step:

```bash
curl -sS "$BASE_URL/api/admin/external-effects/diagnostics" \
  | jq '{
    real_execution_enabled,
    execution_mode,
    allowed_effect_types,
    eligible_due_count,
    dispatching_count,
    failed_retryable_count,
    failed_terminal_count,
    oldest_queued_age_seconds,
    oldest_failed_retryable_age_seconds
  }'
```

Alert manually if any of these are true during a gray window:

- `dispatching_count` stays above `0` longer than the worker lock timeout.
- `failed_terminal_count` increases after a batch.
- `failed_retryable_count` increases repeatedly across retries.
- `oldest_queued_age_seconds` or `oldest_failed_retryable_age_seconds` keeps
  growing while due jobs exist.
- Any response contains `real_external_call_executed=true` outside an approved
  gray window.

## Test Environment Enablement

For staging or a local test environment, enable one low-risk type at a time:

```bash
export AICRM_EXTERNAL_EFFECT_WEBHOOK_EXECUTE=1
export AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES=webhook.questionnaire_submission.push
```

Confirm the mode before running anything:

```bash
curl -sS "$BASE_URL/api/admin/external-effects/diagnostics" \
  | jq '.real_execution_enabled,.execution_mode,.allowed_effect_types'
```

## Production Single Effect-Type Enablement

Production enablement must be one effect type at a time:

```bash
export AICRM_EXTERNAL_EFFECT_WEBHOOK_EXECUTE=1
export AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES=webhook.order_paid.push
```

Keep all other external effect types out of the allowlist. This queue must not
be used as a shortcut to enable WeCom or payment-query execution.

## Run-Due Preview

Preview never dispatches adapters and must be the first step:

`AICRM_ACCESS_TOKEN` 必须是 `automation_worker` 通过 `audience=internal_worker`、`scope=write` 换取的短期 JWT；见 [`../auth_client_credentials.md`](../auth_client_credentials.md)。

```bash
curl -sS -X POST "$BASE_URL/api/admin/external-effects/run-due/preview" \
  -H "Authorization: Bearer $AICRM_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "batch_size": 10,
    "effect_types": ["webhook.questionnaire_submission.push"]
  }' | jq '{counts,dry_run,real_external_call_executed}'
```

Expected:

```json
{
  "dry_run": true,
  "real_external_call_executed": false
}
```

## Dry-Run

`run-due` defaults to `dry_run=true`; keep it explicit in gray checks:

```bash
curl -sS -X POST "$BASE_URL/api/admin/external-effects/run-due" \
  -H "Authorization: Bearer $AICRM_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "batch_size": 10,
    "dry_run": true,
    "effect_types": ["webhook.questionnaire_submission.push"]
  }' | jq '{counts,dry_run,real_external_call_executed}'
```

Expected:

```json
{
  "dry_run": true,
  "real_external_call_executed": false
}
```

## Batch Size 1 Real Execution

Only after preview and dry-run match the expected candidate set, execute a
single job:

```bash
curl -sS -X POST "$BASE_URL/api/admin/external-effects/run-due" \
  -H "Authorization: Bearer $AICRM_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "batch_size": 1,
    "dry_run": false,
    "effect_types": ["webhook.questionnaire_submission.push"]
  }' | jq '{counts,dry_run,real_external_call_executed,items}'
```

If the response has `real_external_call_executed=true`, immediately inspect the
job detail and attempts:

```bash
curl -sS "$BASE_URL/api/admin/external-effects/jobs/$JOB_ID" | jq '{job,attempts}'
```

## Manual Retry

Retry only failed or blocked jobs after the root cause is understood:

```bash
curl -sS -X POST "$BASE_URL/api/admin/external-effects/jobs/$JOB_ID/retry" \
  -H "X-Admin-Action-Token: $ADMIN_ACTION_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'
```

The job should return to `queued`. Run preview again before any execution.

## Manual Cancel

Cancel a job when it should not be dispatched:

```bash
curl -sS -X POST "$BASE_URL/api/admin/external-effects/jobs/$JOB_ID/cancel" \
  -H "X-Admin-Action-Token: $ADMIN_ACTION_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'
```

Cancelled jobs are not scanned by run-due.

## Rollback To Disabled

Rollback is configuration-only for P0-1D:

```bash
export AICRM_EXTERNAL_EFFECT_WEBHOOK_EXECUTE=0
export AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES=
```

After the app process picks up the config, confirm:

```bash
curl -sS "$BASE_URL/api/admin/external-effects/diagnostics" \
  | jq '.real_execution_enabled,.execution_mode,.allowed_effect_types'
```

Expected:

```json
false
"disabled"
[]
```

No schema rollback is required for disabling execution. Existing shadow jobs and
attempt logs remain available for diagnosis.
