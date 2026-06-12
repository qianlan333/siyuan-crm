# Post-Legacy Deferred API Cleanup Inventory

Status: cleanup_locked

This inventory closes the deferred API set left by the post-legacy product baseline in PR #1043. The cleanup keeps all routes Next-owned, avoids `production_compat`, and blocks real external side effects by default.

## Deferred API Decision Matrix

| Deferred API | Calling page/JS | Method | Current status | Decision | Next owner | External side effects | Smoke | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/api/admin/class-user-management/export` | `aicrm_next/frontend_compat/templates/admin_console/operations.html` export button | GET download; POST/OPTIONS supported by API closeout | Frontend button exists and previously pointed at an unregistered deferred export URL | Next-owned controlled local CSV export | `next_export` / `aicrm_next.class_user_management` | none; `external_storage_executed=false` | GET must return 200 CSV, `route_owner=ai_crm_next`, `fallback_used=false` | PR-11 keeps this route on the native class user management router while removing post_legacy_deferred from app startup. |
| `/api/admin/cloud-orchestrator/audit` | `aicrm_next/frontend_compat/templates/admin_console/cloud_observability.html` audit table fetch | GET/OPTIONS | Observability page fetch exists and previously had no registered API | Next-owned read-only empty audit contract | `next_cloud_observability` / `aicrm_next.cloud_orchestrator` | none; no external observability service | GET must return 200 JSON, `items=[]`, `count=0` | Read-only degraded-safe contract; no 500 when no audit store exists. |
| `/api/admin/cloud-orchestrator/observability` | `aicrm_next/frontend_compat/templates/admin_console/cloud_observability.html` metrics fetch | GET/OPTIONS | Observability page fetch exists and previously had no registered API | Next-owned read-only empty observability contract | `next_cloud_observability` / `aicrm_next.cloud_orchestrator` | none; no external observability service | GET must return 200 JSON with `health`, `metrics`, `recent_runs` | Local empty metrics keep the page/API contract registered without real monitoring calls. |
| `/api/admin/wecom-customer-acquisition-links` | `aicrm_next/frontend_compat/templates/admin_console/wecom_customer_acquisition_links.html` list/create JS | GET/POST/OPTIONS | Page list/create JS exists and previously pointed at deferred API family | Next-owned safe-mode read/write plan-only API | `next_wecom_customer_acquisition` / `aicrm_next.automation_engine.channels_api` | real WeCom blocked; `wecom_api_called=false` | GET and POST must return 200 JSON; POST returns `side_effect_plan` | PR-11 moves the fixture-backed plan-only contract out of post_legacy_deferred. |
| `/api/admin/wecom-customer-acquisition-links/{link_id}` | No direct current literal; required by actual family and safe child management | GET/PATCH/DELETE/OPTIONS | Dynamic family child needed for route coverage and API alignment | Next-owned safe-mode detail/update/disable API | `next_wecom_customer_acquisition` / `aicrm_next.automation_engine.channels_api` | real WeCom blocked; `wecom_api_called=false` | GET/PATCH/DELETE must not return 500 | Missing link returns controlled 404, not production compat. |
| `/api/admin/wecom-customer-acquisition-links/{link_id}/{action}` | `wecom_customer_acquisition_links.html` action JS for `enable`, `disable`, `sync` | POST/OPTIONS | Dynamic action JS exists | Next-owned safe-mode action route; unknown actions are controlled 410 | `next_wecom_customer_acquisition` / `aicrm_next.automation_engine.channels_api` | real WeCom blocked; `sync_executed=false`, `wecom_api_called=false` | POST `sync` must return 200 with blocked plan; unknown action 410 | `sync` is plan-only and never calls WeCom by default. |

## Code Investigation

The required searches showed these active frontend/API call sites:

| Route family | Active caller | UI element | Method shape | Existing Next domain/service |
| --- | --- | --- | --- | --- |
| class-user export | `operations.html` | `导出当前结果` link | GET download | No current export service needed for closeout; local CSV contract is enough. |
| cloud audit | `cloud_observability.html` | audit table load | GET with `trace_id`, `session_id`, `limit` | Cloud orchestrator shell exists; the closeout adds read-only local contract. |
| cloud observability | `cloud_observability.html` | metrics panels | GET | Cloud orchestrator shell exists; the closeout adds read-only local contract. |
| WeCom CA links | `wecom_customer_acquisition_links.html` | list, create, enable/disable/sync buttons | GET, POST, POST action | No real WeCom adapter is allowed; safe-mode fixture command contract is used. |

## Guardrails

- `DEFERRED_FRONTEND_API_PATTERNS` is empty.
- The post-legacy frontend URL test must fail if a frontend `/api/...` literal has no matching route.
- These routes must not emit `X-AICRM-Compatibility-Facade`.
- Normal responses must keep `fallback_used=false` and `real_external_call_executed=false`.
- WeCom customer acquisition routes must keep `adapter_mode=real_blocked` and `wecom_api_called=false`.
- Class-user export must keep `external_storage_executed=false`.
- `production_compat` remains absent from runtime route ownership and app startup.

## Smoke Acceptance

| Smoke | Expected |
| --- | --- |
| `GET /api/admin/class-user-management/export` | 200 CSV, local-only export, no external storage |
| `GET /api/admin/cloud-orchestrator/audit` | 200 JSON, empty audit list, no external call |
| `GET /api/admin/cloud-orchestrator/observability` | 200 JSON, local health/metrics contract |
| `GET /api/admin/wecom-customer-acquisition-links` | 200 JSON, fixture links, real WeCom blocked |
| `POST /api/admin/wecom-customer-acquisition-links` | 200 JSON command plan, `wecom_api_called=false` |
| `GET /admin/cloud-orchestrator/campaigns` | 200 page, no page regression |
| `GET /admin` | 200 page, no page regression |
