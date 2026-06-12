# Automation Conversion Timer Route Inventory

This inventory locks the reply monitor and registered jobs timer family to Next safe-mode planning. The legacy Flask handlers remain documented as historical sources only; the Next routes below do not invoke `run_reply_monitor_capture`, `run_due_reply_monitor`, or `run_registered_due_jobs`.

## Caller ↔ API ↔ CommandBus ↔ SideEffectPlan Matrix

| Caller | API | CommandBus | SideEffectPlan |
| --- | --- | --- | --- |
| Scheduler, admin smoke, or operator with POST/OPTIONS | POST `/api/admin/automation-conversion/reply-monitor/capture` | `automation_conversion.reply_monitor.capture.plan` via `PlanReplyMonitorCaptureCommand`; idempotency key supported; JSON/query `limit`, `batch_size`, `dry_run` supported; invalid limit returns 400 | `effect_type=automation_conversion.reply_monitor.capture`; `adapter_mode=real_blocked`; `status=blocked`; no external capture; no legacy runtime; `source_status=next_reply_monitor_capture_plan`; `reply_monitor_capture_executed=false` |
| Scheduler, admin smoke, or operator with POST/OPTIONS | OPTIONS `/api/admin/automation-conversion/reply-monitor/capture` | No command execution; diagnostics only | Diagnostics declare `allowed_methods=[POST, OPTIONS]`, `route_owner=ai_crm_next`, `fallback_used=false`, and all execution flags false |
| Scheduler, admin smoke, or operator with POST/OPTIONS | POST `/api/admin/automation-conversion/reply-monitor/run-due` | `automation_conversion.reply_monitor.run_due.plan` via `PlanReplyMonitorRunDueCommand`; idempotency key supported; JSON/query `limit`, `batch_size`, `dry_run` supported; invalid limit returns 400 | `effect_type=automation_conversion.reply_monitor.run_due`; `adapter_mode=real_blocked`; `status=blocked`; no reply runtime; no real send; `source_status=next_reply_monitor_run_due_plan`; `reply_monitor_run_due_executed=false`; `wecom_send_executed=false` |
| Scheduler, admin smoke, or operator with POST/OPTIONS | OPTIONS `/api/admin/automation-conversion/reply-monitor/run-due` | No command execution; diagnostics only | Diagnostics declare `allowed_methods=[POST, OPTIONS]`, `route_owner=ai_crm_next`, `fallback_used=false`, and all execution flags false |
| Scheduler, admin smoke, or operator with POST/OPTIONS | POST `/api/admin/automation-conversion/jobs/run-due/preview` | `automation_conversion.jobs.run_due.preview` via `PreviewAutomationJobsRunDueCommand`; idempotency key supported; JSON/query `jobs`, `job_codes`, `limit`, `batch_size`, `dry_run` supported; invalid inputs return 400 | Preview-only response with `source_status=next_jobs_run_due_preview`, `candidates`, `job_codes`, and `estimated_actions`; no writes; no runtime execution; no SideEffectPlan is executed |
| Scheduler, admin smoke, or operator with POST/OPTIONS | OPTIONS `/api/admin/automation-conversion/jobs/run-due/preview` | No command execution; diagnostics only | Diagnostics declare `allowed_methods=[POST, OPTIONS]`, `route_owner=ai_crm_next`, `fallback_used=false`, and all execution flags false |
| Scheduler, admin smoke, or operator with POST/OPTIONS | POST `/api/admin/automation-conversion/jobs/run-due` | `automation_conversion.jobs.run_due.plan` via `PlanAutomationJobsRunDueCommand`; idempotency key supported; JSON/query `jobs`, `job_codes`, `limit`, `batch_size`, `dry_run` supported; invalid inputs return 400 | `effect_type=automation_conversion.jobs.run_due`; `adapter_mode=real_blocked`; `status=blocked`; no registered jobs runtime; `source_status=next_jobs_run_due_plan`; `jobs_run_due_executed=false` |
| Scheduler, admin smoke, or operator with POST/OPTIONS | OPTIONS `/api/admin/automation-conversion/jobs/run-due` | No command execution; diagnostics only | Diagnostics declare `allowed_methods=[POST, OPTIONS]`, `route_owner=ai_crm_next`, `fallback_used=false`, and all execution flags false |

## Operation Task Runtime Contract

- Next `/api/admin/automation-conversion/jobs/run-due` is a planning route only. Even when `jobs=["operation_task"]`, it must return `jobs_run_due_executed=false`, `operation_tasks_executed=0`, `actual_enqueued_count=0`, and `blocked_reason=next_plan_only_route`.
- The legacy operation-task due runner has been retired with the legacy package body. Active automation scheduling now runs through Next-native background job and automation engine owners.
- `scripts/run_automation_conversion_due_jobs.py` can select `AUTOMATION_CONVERSION_DUE_JOBS=operation_task`, but the default scheduled set stays `sop,conversion_workflow` until the runbook allowlist and worker coverage are explicitly approved.
- `scripts/run_broadcast_queue_worker.py` is the separate consumer for `broadcast_jobs.source_type=operation_task`; timer success must not be treated as send success unless the worker dispatch result is observed.

## Reply Monitor Timer Contract

- `deploy/aicrm-reply-monitor-capture.service` calls `scripts/run_reply_monitor_capture.py`, not a bare curl command.
- `deploy/aicrm-reply-monitor-capture.timer` owns the three-minute capture cadence and overwrites the previously observed production-only stale unit on deploy.
- The capture runner posts JSON to `/api/admin/automation-conversion/reply-monitor/capture` with `Authorization: Bearer $AUTOMATION_INTERNAL_API_TOKEN`, `operator=reply_monitor_capture_timer`, `limit=500`, and `dry_run=true` by default.
- If `AUTOMATION_INTERNAL_API_TOKEN` is missing, the capture runner emits structured skipped diagnostics and does not call the route.
- The capture route keeps the path unchanged and must return a controlled non-400 safe plan for a valid internal-token timer request with an empty or safe payload.
- `deploy/aicrm-reply-monitor-run-due.service` calls `scripts/run_reply_monitor_run_due.py`, not a bare curl command.
- The runner posts JSON to `/api/admin/automation-conversion/reply-monitor/run-due` with `Authorization: Bearer $AUTOMATION_INTERNAL_API_TOKEN`, `operator=reply_monitor_run_due_timer`, `limit=20`, and `dry_run=true` by default.
- If `AUTOMATION_INTERNAL_API_TOKEN` is missing, the runner emits structured skipped diagnostics and does not call the route.
- The route must reject missing/invalid internal tokens with structured 401 diagnostics and must return a controlled non-400 safe plan for a valid timer request with no body or no due work.
- The timer contract is plan-only and keeps `real_external_call_executed=false`, `automation_runtime_executed=false`, `wecom_send_executed=false`, and `fallback_used=false`.

## Adjacent Workspace Routes

| Caller | API | CommandBus | SideEffectPlan |
| --- | --- | --- | --- |
| Existing production workspace callers | POST/OPTIONS `/api/admin/automation-conversion/tasks/run-due` | Covered by `automation_workspace_runtime_route_inventory.md` after the group 22 cutover | Next safe-mode planner returns `source_status=next_automation_tasks_run_due_plan` with no legacy runtime execution |
| Existing production workspace callers | POST/OPTIONS `/api/admin/automation-conversion/execution-items/{execution_item_id}/send-via-bazhuayu` | Covered by `automation_workspace_runtime_route_inventory.md` after the group 22 cutover | Next safe-mode planner returns `source_status=next_bazhuayu_dispatch_plan` with no outbound send |

## Deletion Lock

- The four timer routes are registered as Next-owned before `production_compat`.
- `legacy_fallback_allowed=false`, `delete_status=deletion_locked`, and `replacement_status=locked` are required in both lifecycle files.
- Safe-mode responses must keep `real_external_call_executed=false`, `automation_runtime_executed=false`, `wecom_send_executed=false`, and the route-specific execution flags false.
