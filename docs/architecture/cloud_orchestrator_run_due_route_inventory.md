# Cloud Orchestrator Run-Due Route Inventory

Scope: Legacy Exit group 20 locks Cloud campaign run-due and preview timers to Next safe-mode planner routes. The production_compat rollback removed state is intentional. This group does not enable real campaign runtime, real automation runtime, real WeCom send, payment, storage, OpenClaw, Automation conversion timers, reply monitor timers, jobs timers, or send-via-bazhuayu.

Route precedence:

- `aicrm_next.cloud_orchestrator.api` registers exact POST/OPTIONS routes, and production_compat is no longer registered by `aicrm_next.main`.
- `aicrm_next/production_compat/api.py` has been removed; no production_compat runtime route or fallback remains for `/api/admin/cloud-orchestrator/campaigns/run-due` or `/api/admin/cloud-orchestrator/campaigns/run-due/preview`.
- Automation timer fallback routes remain production_compat and out-of-scope: `/api/admin/automation-conversion/reply-monitor/run-due`, `/api/admin/automation-conversion/reply-monitor/capture`, `/api/admin/automation-conversion/jobs/run-due`, `/api/admin/automation-conversion/jobs/run-due/preview`.

## Caller ↔ API ↔ CommandBus ↔ SideEffectPlan Matrix

| 调用方 | 文件/入口 | 动作 | API | Method | Handler | CommandBus | Runtime 行为 | SideEffectPlan | Closeout 状态 | Smoke |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| retired cron / timer caller | legacy campaign scheduler script retired; no Next page caller | Plan due campaign delivery | `/api/admin/cloud-orchestrator/campaigns/run-due` | POST | `api_plan_cloud_campaign_run_due` | `PlanCloudCampaignRunDueCommand` | No real scheduler, no campaign runtime, no automation runtime, no WeCom send | `cloud_orchestrator.campaign.run_due`, `adapter_mode=real_blocked`, `requires_approval=true`, blocked ExternalCallAttempt | `deletion_locked`, `legacy_fallback_allowed=false` | POST run-due 200, `source_status=next_run_due_plan` |
| manual admin caller | API-only / timer-only; no page entry found in `cloud_campaigns_workspace.html` | Operator-triggered plan-only run-due | `/api/admin/cloud-orchestrator/campaigns/run-due` | POST | `api_plan_cloud_campaign_run_due` | `PlanCloudCampaignRunDueCommand` | Plan-only, no state advance, no send | SideEffectPlan plus AuditLedger and ExternalCallAttempt blocked record | locked Next route; no compatibility facade | POST run-due with Idempotency-Key |
| tests / scripts caller | `tests/test_cloud_orchestrator_run_due_*.py`; curl smoke | Preview due candidates | `/api/admin/cloud-orchestrator/campaigns/run-due/preview` | POST | `api_preview_cloud_campaign_run_due` | `PreviewCloudCampaignRunDueCommand` | Read model/fixture candidate estimate only; no writes | none created by preview | locked Next route | POST preview 200 |
| diagnostics caller | curl / route resolution checker | Confirm owner and allowed methods | `/api/admin/cloud-orchestrator/campaigns/run-due` | OPTIONS | `api_cloud_campaign_run_due_options` | none | No runtime | diagnostic SideEffectPlan contract only | locked Next route | OPTIONS run-due 200 |
| diagnostics caller | curl / route resolution checker | Confirm owner and allowed methods | `/api/admin/cloud-orchestrator/campaigns/run-due/preview` | OPTIONS | `api_cloud_campaign_run_due_preview_options` | none | No runtime | diagnostic SideEffectPlan contract only | locked Next route | OPTIONS preview 200 |
| legacy Flask scheduler | `wecom_ability_service.domains.campaigns.scheduler.process_due_campaign_members` | Historical actual execution | production_compat rollback deleted | n/a | none | none | Not imported, not called, not forwarded | none | removed; guarded by strict no-new-legacy check | source search |
| production_compat rollback | `aicrm_next/production_compat/api.py` | Historical forward to legacy Flask | deleted for Cloud run-due/preview | n/a | none | none | Not available for this route family | none | removed; automation timer fallback retained | route precedence |

## API Contracts

POST `/api/admin/cloud-orchestrator/campaigns/run-due/preview` accepts JSON body or query params:

- `batch_size`: default 200, min 1, max 1000.
- `dry_run`: accepted for caller compatibility; preview is always no-write/no-send.

Preview response includes `ok=true`, `source_status=next_run_due_preview`, `route_owner=ai_crm_next`, `fallback_used=false`, `candidates`, `candidate_count`, `estimated_actions`, `real_external_call_executed=false`, `campaign_runtime_executed=false`, `automation_runtime_executed=false`, and `wecom_send_executed=false`.

POST `/api/admin/cloud-orchestrator/campaigns/run-due` accepts JSON body or query params:

- `batch_size`: default 200, min 1, max 1000.
- `dry_run`: defaults true.
- `force_plan`: defaults true.
- `Idempotency-Key`: repeated keys return the same CommandBus result and command_id.

Run-due response keeps legacy-compatible counters: `processed_count`, `sent_count`, `failed_count`, `skipped_count`, and `planned_count`. It also returns `source_status=next_run_due_plan`, `side_effect_plan`, `external_call_attempt`, `route_owner=ai_crm_next`, `fallback_used=false`, `real_external_call_executed=false`, `campaign_runtime_executed=false`, `automation_runtime_executed=false`, and `wecom_send_executed=false`.

Invalid `batch_size` returns 400 `input_error` without legacy forward.

## Guard Boundaries

- No `process_due_campaign_members` import or call in `aicrm_next/cloud_orchestrator/run_due.py`.
- No `WeComClient.from_app`, direct `send_message`, direct HTTP clients, or token exchange in the run-due path.
- No `real_external_call_executed=true`, `campaign_runtime_executed=true`, `automation_runtime_executed=true`, or `wecom_send_executed=true` defaults.
- Campaign read/write and media upload remain `deletion_locked`.
- Automation conversion timer fallbacks remain production_compat and out-of-scope.
