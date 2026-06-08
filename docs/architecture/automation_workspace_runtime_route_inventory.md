# Automation Workspace Runtime Route Inventory

Scope: Legacy Exit group 22 locks the automation workspace operation-task runtime and execution-item outbound dispatch routes to Next safe-mode plans. The production_compat rollback is removed for the two exact API routes in this document. This group enforces no real operation task runtime and does not enable real outbound dispatch, real WeCom send, real OpenClaw call, payment, storage, customer automation webhooks, member actions, manual-send, focus-send, or SOP timers.

## Caller ↔ API ↔ CommandBus ↔ SideEffectPlan Matrix

| 调用方 | 文件/入口 | 动作 | API | Method | Handler | CommandBus | Runtime/Outbound 行为 | SideEffectPlan | Closeout 状态 | Smoke |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Admin workspace page | `/admin/automation-conversion` | 页面入口；本组未发现直接按钮触发 workspace runtime | N/A | GET | Existing frontend shell | N/A | API-only / timer-only for this group | N/A | Page remains out of scope; no route lock change | Frontend contract asserts no active caller depends on removed rollback |
| Program setup page | `/admin/automation-conversion/programs/{program_id}/setup` | Program setup and operation-task configuration | N/A | GET | Existing frontend shell | N/A | API-only / timer-only for runtime dispatch; setup APIs stay current owner | N/A | Page remains out of scope; no route lock change | Frontend contract asserts no direct runtime button is added by this group |
| Operation tasks frontend/JS | `aicrm_next/automation_engine/templates` and `aicrm_next/automation_engine/static` | No direct runtime caller found for this group | `/api/admin/automation-conversion/tasks/run-due` | POST | `api_plan_automation_workspace_tasks_run_due` | `PlanAutomationOperationTasksRunDueCommand` | Safe-mode only; does not execute operation tasks; does not call legacy runtime service; returns `ok`, `status`, `planned_count`, `processed_count`, `sent_count`, `failed_count`, `skipped_count`, `side_effect_plan` | `effect_type=automation.operation_tasks.run_due`; `adapter_mode=real_blocked`; `status=blocked`; `operation_tasks_executed=false`; `automation_runtime_executed=false` | `legacy_fallback_allowed=false`; `delete_status=deletion_locked`; `replacement_status=locked` | POST with `program_id=1` returns `source_status=next_automation_tasks_run_due_plan`; invalid `program_id=-1` returns 400 |
| Execution item outbound frontend/JS | `aicrm_next/automation_engine/templates` and `aicrm_next/automation_engine/static` | No direct outbound dispatch caller found for this group | `/api/admin/automation-conversion/execution-items/{execution_item_id}/send-via-bazhuayu` | POST | `api_plan_automation_workspace_execution_item_outbound` | `PlanAutomationExecutionItemBazhuayuDispatchCommand` logical command; implemented by the Next outbound dispatch planner | Safe-mode only; does not call external dispatcher; does not call legacy outbound service; returns `ok`, `status`, `command_id`, `execution_item_id`, `side_effect_plan` | `effect_type=automation.execution_item.send_via_bazhuayu`; `adapter_mode=real_blocked`; `status=blocked`; `bazhuayu_send_executed=false`; `wecom_send_executed=false`; `automation_runtime_executed=false` | `legacy_fallback_allowed=false`; `delete_status=deletion_locked`; `replacement_status=locked` | POST with `execution_item_id=1` returns `source_status=next_bazhuayu_dispatch_plan` and all execution flags false |
| Scheduler / operator / smoke | API-only | Diagnostics | `/api/admin/automation-conversion/tasks/run-due` | OPTIONS | `api_automation_workspace_tasks_run_due_options` | No command execution | Diagnostics only; no legacy forward | Diagnostics plan shape with `adapter_mode=real_blocked` and all execution flags false | Next exact route before production_compat after rollback removal | OPTIONS returns `route_owner=ai_crm_next`, `fallback_used=false` |
| Scheduler / operator / smoke | API-only | Diagnostics | `/api/admin/automation-conversion/execution-items/{execution_item_id}/send-via-bazhuayu` | OPTIONS | `api_automation_workspace_execution_item_outbound_options` | No command execution | Diagnostics only; no legacy forward | Diagnostics plan shape with `adapter_mode=real_blocked` and all execution flags false | Next exact route before production_compat after rollback removal | OPTIONS returns `route_owner=ai_crm_next`, `fallback_used=false` |
| Historical Flask handler | `wecom_ability_service/http/automation_conversion_task_runtime.py::api_admin_automation_conversion_tasks_run_due` | Former runtime execution | `/api/admin/automation-conversion/tasks/run-due` | POST | Removed from production_compat rollback | N/A | Historical only; not invoked by Next route | N/A | rollback removed; no compatibility facade | grep production_compat exact route returns no output |
| Historical Flask handler | `wecom_ability_service/http/automation_conversion_execution_outbound.py::api_admin_automation_conversion_execution_item_send_via_bazhuayu` | Former outbound dispatch | `/api/admin/automation-conversion/execution-items/{execution_item_id}/send-via-bazhuayu` | POST | Removed from production_compat rollback | N/A | Historical only; not invoked by Next route | N/A | rollback removed; no compatibility facade | grep production_compat exact route returns no output |
| Out-of-scope member/manual/focus/SOP surfaces | Existing member, manual-send, focus-send, SOP routes | Not handled by group 22 | N/A | N/A | Current owners unchanged | N/A | Current state preserved; no new real send path introduced | N/A | not marked locked by this group | Out-of-scope smoke verifies route family is not misclassified as this closeout |

## Compatibility Fields

The two Next POST responses preserve the legacy-facing fields needed by existing callers:

- `ok`
- `status`
- `planned_count`
- `processed_count`
- `sent_count`
- `failed_count`
- `skipped_count`
- `side_effect_plan`

Both routes also return `route_owner=ai_crm_next`, `fallback_used=false`, `real_external_call_executed=false`, `automation_runtime_executed=false`, `operation_tasks_executed=false`, `bazhuayu_send_executed=false`, and `wecom_send_executed=false`.

## No-Real-Runtime Boundary

- The Next task route only creates a due-task plan.
- The Next outbound route only creates an outbound dispatch plan.
- No legacy runtime service is invoked.
- No external dispatcher, WeCom, OpenClaw, or direct HTTP client is invoked.
- Production compatibility rollback is removed only for the two exact routes in this inventory.
