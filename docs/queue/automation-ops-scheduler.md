# Automation Ops Scheduler

`scripts/run_automation_ops_scheduler.py` is the business-domain scheduler for automation ops. It creates due `broadcast_jobs` rows and refreshes backend-owned read models such as the HXC dashboard snapshot. Real WeCom delivery stays in `scripts/run_broadcast_queue_worker.py`, `broadcast_jobs.handlers`, `tasks.service`, and the WeCom adapter guard.

## group_ops due_at

Only standard group operation plans are scanned:

- `plan_type = standard`
- plan `status = active`
- node `status = active`
- at least one active bound group
- node content can be normalized into a WeCom customer-group payload

For every active plan node and every active bound group:

1. Read `scheduled_time`; if missing, derive `HH:MM` from `trigger_time_label`.
2. Interpret `scheduled_time` as business wall-clock time in `Asia/Shanghai` by default. Override only with `AICRM_GROUP_OPS_TIMEZONE`.
3. Use `automation_group_ops_plan_groups.created_at` as the group start time.
4. If a binding has no `created_at`, use `automation_group_ops_plans.created_at`.
5. Convert the start anchor to the business timezone, take that local date, then compute `due_at = start_date + (day_index - 1) days + scheduled_time`.
6. Store `scheduled_for` as business-timezone ISO, for example `2026-05-29T13:00:00+08:00`.
7. Compare due-ness by converting both `due_at` and scheduler `now` to UTC.
8. If `due_at <= now`, enqueue through `LegacyBroadcastJobQueueGateway.enqueue_group_message`.

Groups with the same `plan_id`, `node_id`, `due_at` minute, owner, and content hash are merged into one job. Their `content_payload.chat_ids` contains all due `chat_id` values. Groups with different `due_at` values are not merged.

The queue job keeps the current group_ops contract: `source_type=workflow`, `source_table=automation_group_ops_plans`, `business_domain=group_ops`, `channel=wecom_customer_group`, `target_kind=chat_id`, and `content_type=wecom_customer_group`. `scheduled_for` is the computed `due_at`, not scheduler runtime.

## Idempotency

The scheduler uses a stable source/idempotency shape that includes:

- `plan_id`
- `node_id`
- `due_at` minute
- sorted `chat_ids` hash

The `broadcast_jobs` unique idempotency guard is still the final protection, so rerunning the timer does not duplicate queue rows.

## operation_task

The same runner calls `run_due_operation_tasks(...)` for `scheduled_daily` operation tasks. That service pre-schedules `operation_task` jobs into `broadcast_jobs`; the worker later resolves the audience and sends through the existing operation-task handler.

## HXC dashboard snapshot

The HXC dashboard is backend-refreshed. The scheduler checks `user_ops_hxc_dashboard_meta` every minute and calls `refresh_hxc_dashboard_snapshot(...)` only when the latest successful snapshot is at least 30 minutes old. The admin page must not auto-POST `/api/admin/hxc-dashboard/refresh`; it only reads the snapshot and keeps the manual refresh button for operator-initiated repair.

## Responsibility Boundary

- Automation ops scheduler: compute due business work and enqueue `broadcast_jobs`.
- HXC dashboard scheduler path: refresh the snapshot read model at a 30-minute cadence.
- Broadcast queue worker: claim due queue rows and dispatch handlers.
- Handlers and tasks service: create recoverable outbound intent.
- WeCom adapter: decide whether fake, blocked, or production side effects may run.

The scheduler must not call WeCom directly.

## group_ops Real E2E Notes

`scheduled_time` keeps the product rule: `08:00-23:30`, in 30-minute steps, interpreted as the `Asia/Shanghai` business timezone unless `AICRM_GROUP_OPS_TIMEZONE` is explicitly set.

For real group-send acceptance, choose the current `Asia/Shanghai` time and round down to the nearest 30-minute slot:

- `13:07` -> `13:00`
- `13:35` -> `13:30`

If the current business time is outside `08:00-23:30`, do not run real group-send E2E; run unit tests only.

Real group_ops acceptance must use only:

```bash
python scripts/run_automation_ops_scheduler.py
python scripts/run_broadcast_queue_worker.py
```

Do not use group_ops run-due or direct queue writes to stand in for automatic scheduling.

## WeCom Modes

- `AICRM_WECOM_GROUP_ADAPTER_MODE=fake`: worker can mark group jobs sent, while the adapter records `side_effect_executed=false`.
- `AICRM_WECOM_GROUP_ADAPTER_MODE=disabled` or `staging`: group sending is blocked and jobs fail or remain blocked through the adapter path.
- `AICRM_WECOM_GROUP_ADAPTER_MODE=production`: real group messages still require `AICRM_ENABLE_REAL_WECOM_GROUP_MESSAGE=true`; otherwise the production guard fails.

## systemd

Install and enable the scheduler timer alongside the existing broadcast worker:

```bash
sudo cp deploy/openclaw-automation-ops-scheduler.service /etc/systemd/system/
sudo cp deploy/openclaw-automation-ops-scheduler.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now openclaw-automation-ops-scheduler.timer
sudo systemctl status openclaw-automation-ops-scheduler.timer
```

The timer runs every minute. Idempotency makes this safe even when no tasks are due.
