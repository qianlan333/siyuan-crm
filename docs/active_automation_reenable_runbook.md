# Active Automation Re-enable Runbook

## Scope

This runbook covers the active automation timers that are still disabled:

- `aicrm-automation-jobs-run-due.timer`
- `aicrm-campaign-run-due.timer`

It does not enable timers, modify systemd/nginx/deploy config, remove legacy fallback, or execute real external calls.

## Recovery Order

### 1. Dry-run no-op

Call each Next-owned compatibility route with `dry_run=true` in the JSON body, query string, or `X-AICRM-Dry-Run=true`.

Required result:

- `side_effect_executed=false`
- `legacy_forwarded=false`
- no DB sentinel changes
- no WeCom, OpenClaw, agent runtime, webhook, or campaign dispatch call

### 2. Preview no-op

Call:

- `POST /api/admin/automation-conversion/jobs/run-due/preview`
- `POST /api/admin/cloud-orchestrator/campaigns/run-due/preview`

or pass `preview=true` to the existing run-due routes.

Required result:

- read-only response
- candidate IDs and risk flags returned
- no `automation_sop_batch`
- no `automation_workflow_execution`
- no `user_ops_send_records`
- no `outbound_tasks`
- no external calls

### 3. Bounded single execution with allowlist

Do not run a real active automation route unless the request includes an explicit allowlist and tight limits.

Automation jobs require:

- `allow_task_ids`, `allow_workflow_ids`, or `allow_node_ids`
- `max_send_records`
- `max_outbound_tasks`
- `operator`

Campaign jobs require:

- `allow_campaign_ids`
- `batch_size`
- `max_dispatch_count`

Production requests without an allowlist must fail with a 409/400 guardrail response.

### 3a. Scheduled safe mode for systemd timers

Systemd timers should not call raw true execution directly. Future `ExecStart` payloads should use scheduled safe mode so a timer tick exits successfully when there is nothing to do, and stays non-destructive when candidates exist but no allowlist has been approved.

Automation jobs payload:

```bash
--data '{"operator":"aicrm-automation-jobs-run-due","jobs":["sop","conversion_workflow"],"scheduled_safe_mode":true}'
```

Operation-task coverage is opt-in until bounded execution has been approved:

```bash
AUTOMATION_CONVERSION_DUE_JOBS=operation_task python3 scripts/run_automation_conversion_due_jobs.py
```

This script selection must still point at the approved internal/script execution path. The Next
`/api/admin/automation-conversion/jobs/run-due` route is plan-only and must report
`jobs_run_due_executed=false`, `operation_tasks_executed=0`, `actual_enqueued_count=0`,
and `blocked_reason=next_plan_only_route` when probed directly.

Campaign payload:

```bash
--data '{"operator":"aicrm-campaign-run-due","batch_size":200,"scheduled_safe_mode":true}'
```

Expected behavior:

- no due candidates: HTTP 200 with `status=idle`
- due candidates but no allowlist: HTTP 200 with `status=blocked_not_executed`
- `side_effect_executed=false`
- `legacy_forwarded=false`
- no WeCom, OpenClaw, agent runtime, webhook, or campaign dispatch call
- no writes to the DB sentinel tables

### 4. Observe DB and logs

After any approved bounded execution, compare:

- `user_ops_send_records max(id)`
- `outbound_tasks max(id)`
- `automation_sop_batch max(id)`
- `automation_sop_batch_item max(id)`
- `automation_workflow_execution max(id)`
- `automation_workflow_execution_item max(id)`
- `automation_operation_task_execution max(id)`
- `automation_operation_task_execution_item max(id)`

Also review application logs for any external dispatch attempt.

### 5. Enable timer only after evidence

Only enable the disabled timers after:

- dry-run checker passes
- preview checker passes
- bounded single execution is approved and observed
- logs and DB sentinels are reviewed
- human operator signs off

## Validation

Run:

```bash
python3 tools/check_active_automation_run_due_guardrails.py \
  --output-md /tmp/active_automation_guardrails.md \
  --output-json /tmp/active_automation_guardrails.json

python3 tools/check_active_automation_scheduled_safe_mode.py \
  --output-md /tmp/active_automation_scheduled_safe_mode.md \
  --output-json /tmp/active_automation_scheduled_safe_mode.json
```

Both checkers must pass before moving from dry-run to preview, scheduled safe mode, or bounded execution.
