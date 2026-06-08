# Reply System Re-enable Runbook

## Scope

This runbook describes how to safely restore the reply-system timers after AI-CRM Next owns the compatibility routes.
It does not enable timers, change systemd/nginx/deploy config, remove legacy fallback, or execute real external sends.

## Safety Rules

- Timer compatibility routes must treat `dry_run=true` in JSON body, query string, or `X-AICRM-Dry-Run=true` header as a Next-owned no-op.
- Dry-run responses must include `side_effect_executed=false` and `legacy_forwarded=false`.
- `tools/check_next_timer_route_readiness.py` must pass the dry-run DB sentinel before timers are re-enabled.
- `tools/check_reply_monitor_run_due_readiness.py` must pass before the reply-monitor run-due timer is re-enabled.
- Active automation timers are separate from reply-system timers. `aicrm-automation-jobs-run-due.timer` and `aicrm-campaign-run-due.timer` remain disabled until the active automation dry-run, preview, bounded execution, DB sentinel, and log-observation checks pass.
- A single queue item with invalid phone, missing phone, or unresolvable identity is an item-level failure. It must not make the run-due route return 5xx.
- `tools/check_next_production_cutover_readiness.py` may report `safe_to_enable_timers=true` only when automation production data is ready and the dry-run DB sentinel passes.
- 5013 callback fallback remains in place until a separate observation window approves removal.

## Layer A: Capture

Purpose: capture new private-chat messages only.

Re-enable order: first.

Allowed behavior:

- Read/capture new WeCom private-chat messages.
- Record archive/message activity required for the reply pipeline.
- Avoid dispatching AI-generated or WeCom outbound messages.

Preflight:

- Confirm callback fallback is still available.
- Confirm capture route is Next-owned and dry-run no-op works.
- Confirm logs can distinguish capture from queue dispatch.

Rollback:

- Disable only the capture timer.
- Keep queue/run-due and dispatch/send disabled.

## Layer B: Queue / Run-due

Purpose: process due queue records without external dispatch.

Re-enable order: second, only after Layer A is stable.

Allowed behavior:

- Select due queue items.
- Validate queue state and update internal no-op/dry-run diagnostics when explicitly requested.
- In dry-run, do not forward to legacy and do not change sentinel tables.
- In real run-due, mark invalid phone / missing phone / unresolvable customer identity as `failed` on that queue item, include `failed_items` in the response, and continue to the next due item.
- Return a systemd-compatible 2xx response for item-level failures so `curl -f` does not fail the whole service due to one bad record.
- Do not create `user_ops_send_records` or `outbound_tasks` unless a real external task is successfully created.

Required dry-run sentinel:

- `automation_reply_monitor_config.updated_at`
- `automation_sop_batch max(id)`
- `automation_sop_batch_item max(id)`
- `automation_sop_progress max(updated_at)`
- `automation_workflow_execution max(id)`
- `automation_workflow_execution_item max(id)`
- `user_ops_send_records max(id)`
- `outbound_tasks max(id)`

Preflight:

- Run `python3 tools/check_next_timer_route_readiness.py --output-md /tmp/next_timer_route_readiness.md --output-json /tmp/next_timer_route_readiness.json`.
- Run `python3 tools/check_reply_monitor_run_due_readiness.py --output-md /tmp/reply_monitor_run_due_readiness.md --output-json /tmp/reply_monitor_run_due_readiness.json`.
- Confirm `dry_run_db_sentinel.status=pass`.
- Confirm `safe_to_enable_timers=true`.
- Confirm invalid queue items return `partial_failed=true`, `error_code=reply_monitor_item_failed`, and do not change `user_ops_send_records` / `outbound_tasks` sentinels.

Rollback:

- Disable queue/run-due timers.
- Keep capture status independent.
- Do not enable dispatch/send while queue validation is unresolved.

## Layer C: Dispatch / Send

Purpose: execute real outbound effects through WeCom, AI, or external message channels.

Re-enable order: last.

Required evidence:

- Layer A and B observation windows have no unexpected writes.
- Internal token guard is verified on server.
- External adapter env flags are explicitly reviewed.
- Human signoff confirms real outbound messaging can resume.

Rollback:

- Disable dispatch/send immediately.
- Keep capture and queue decisions separate.
- Preserve audit logs for all real outbound attempts.

## Active Automation Timers

The following timers are not part of the reply-monitor restore path and must stay disabled during reply-system recovery:

- `aicrm-automation-jobs-run-due.timer`
- `aicrm-campaign-run-due.timer`

Before either timer can be enabled, follow `docs/active_automation_reenable_runbook.md`:

1. dry-run no-op
2. preview no-op
3. bounded single execution with allowlist
4. observe DB and logs
5. only then enable the timer

## Current Position

D9/D8 legacy retirement work does not authorize reply-system dispatch. This emergency fix keeps dry-run safe and makes reply-monitor run-due tolerant of item-level invalid phone failures before any timer re-enable decision.
