# Automation Runtime v2 Staging Smoke

This runbook validates Automation Runtime v2 on staging after the legacy Flask
HTTP/runtime archive. It does not replace frontend click acceptance, and it must
not be run against production as staging evidence.

## Safety Boundary

- Do not start the broadcast worker for this smoke.
- Do not real-send WeCom messages.
- Only smoke test data and `broadcast_jobs` rows may be written.
- Smoke data must use the `smoke_runtime_v2` prefix.
- Cleanup must run with the emitted `smoke_run_id`.

## Required Queue Isolation

Checking only `systemctl --user` is not enough to prove the broadcast worker is
stopped. A staging server may have both user-level and root/system-level
`aicrm-broadcast-queue-worker.timer` units. Before any smoke or real-send
acceptance that relies on a manual due queue guard, inspect both levels.

Record the original state before stopping anything:

```bash
systemctl --user status aicrm-broadcast-queue-worker.timer
systemctl --user status aicrm-broadcast-queue-worker.service
systemctl --user is-active aicrm-broadcast-queue-worker.timer
systemctl --user is-active aicrm-broadcast-queue-worker.service

systemctl status aicrm-broadcast-queue-worker.timer
systemctl status aicrm-broadcast-queue-worker.service
systemctl is-active aicrm-broadcast-queue-worker.timer
systemctl is-active aicrm-broadcast-queue-worker.service
```

Pause every active timer before the smoke. If the user-level timer is active:

```bash
systemctl --user stop aicrm-broadcast-queue-worker.timer
```

If the root/system-level timer is active:

```bash
sudo systemctl stop aicrm-broadcast-queue-worker.timer
```

Confirm every worker unit is inactive or absent before continuing:

```bash
systemctl --user is-active aicrm-broadcast-queue-worker.timer
systemctl --user is-active aicrm-broadcast-queue-worker.service
systemctl is-active aicrm-broadcast-queue-worker.timer
systemctl is-active aicrm-broadcast-queue-worker.service
```

The user-level timer, user-level service, root-level timer, and root-level
service must all be inactive or absent before acceptance. If any worker unit
remains active, stop and do not continue the smoke.

The smoke harness checks for recent `automation_runtime_v2` worker activity and
fails the run if smoke jobs are claimed while scenarios are executing.

## Manual Worker Due Queue Guard

For real-send acceptance cases that intentionally run the worker manually, run
this query immediately before every `worker --limit 1` invocation:

```sql
SELECT id, source_type, source_id, channel, target_external_userids,
       content_payload, content_summary, scheduled_for, priority
FROM broadcast_jobs
WHERE status = 'queued' AND scheduled_for <= NOW()
ORDER BY priority ASC, scheduled_for ASC, id ASC
LIMIT 20;
```

Only run the worker when the first due job is the current case job and all of
these checks pass:

- `source_type = 'automation_runtime_v2'`
- `channel = 'wecom_private'`
- `target_external_userids` contains only the expected test external userid.
- `content_payload.sender_userid` equals the expected sender.
- `content_summary` contains the test marker.

If the first due job is anything else, stop and investigate. Do not run the
worker, because it claims due jobs by queue order rather than by a specific
`job_id`.

## Remote App Smoke

```bash
python scripts/smoke_automation_runtime_v2.py \
  --database-url "$STAGING_DATABASE_URL" \
  --app-url "$STAGING_APP_URL" \
  --admin-cookie "$ADMIN_COOKIE" \
  --scenario all \
  --allow-write
```

All seven scenarios must pass:

- `channel-binding`
- `large-channel-protection`
- `future-scan`
- `questionnaire-agent`
- `payment`
- `webhook`
- `scheduled`

## Cleanup

```bash
python scripts/smoke_automation_runtime_v2.py \
  --database-url "$STAGING_DATABASE_URL" \
  --cleanup \
  --smoke-run-id "<smoke_run_id>"
```

Cleanup only cancels smoke-scoped queued, pending, planned, or un-dispatched
claimed jobs and marks smoke task plans cancelled. It does not physically delete
real memberships.

After cleanup, restore only timers that were active before the run:

```bash
# If the root/system-level timer was originally active:
sudo systemctl start aicrm-broadcast-queue-worker.timer
systemctl is-active aicrm-broadcast-queue-worker.timer
systemctl is-active aicrm-broadcast-queue-worker.service

# If the user-level timer was originally active:
systemctl --user start aicrm-broadcast-queue-worker.timer
systemctl --user is-active aicrm-broadcast-queue-worker.timer
systemctl --user is-active aicrm-broadcast-queue-worker.service
```

The restored timer should be active, and the service should settle back to
inactive after its run completes.
