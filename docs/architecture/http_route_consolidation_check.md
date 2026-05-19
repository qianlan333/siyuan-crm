# HTTP Route Consolidation Check

Snapshot date: 2026-05-19

This document is the consolidation checkpoint for the HTTP/controller cleanup track.
It ties together route registry coverage, route ownership, architecture docs, test matrix, and the remaining large-file backlog.

## Registry And Ownership

Current registry shape:

| Area | Current state |
| --- | --- |
| Route module registry | `HTTP_ROUTE_MODULES` contains 75 route-owner or child-controller modules |
| Direct registrars | `HTTP_ROUTE_REGISTRARS` contains 50 modules registered directly on the Flask blueprint |
| Child controllers | Automation-conversion, Cloud Orchestrator, sidebar, and image-library child modules are registered by their aggregators, so they intentionally appear in `HTTP_ROUTE_MODULES` but not in `HTTP_ROUTE_REGISTRARS` |
| Placement groups | `HTTP_ROUTE_PLACEMENT` uses `customer`, `admin`, `callbacks`, and `ops_settings` |
| Helper modules | 16 unregistered HTTP modules are explicitly listed as helper-only modules in `tests/test_http_registration_contract.py` |
| Exported route inventory | `scripts/export_flask_routes.py` exported 456 route rows in this snapshot |
| Flask view ownership | No Flask view module is outside `HTTP_ROUTE_MODULES`, except explicit app-level routes such as `/favicon.ico` and `/mcp` |

The owner contract is intentionally stricter than "routes import successfully":

- every direct registrar key must exist in `HTTP_ROUTE_MODULES`
- every registered route module file must be mentioned in `HTTP_ROUTE_PLACEMENT`
- every non-registered HTTP Python file must be an explicit helper module
- every Flask view function module must be covered by the HTTP route contract
- HTTP controllers must not call raw SQL, `requests`, or instantiate `WeComClient.from_*` directly
- route-owner files over 300 lines must be explicitly capped in `tests/test_http_registration_contract.py`

## Test Matrix

Run the narrow matrix for this cleanup track after each controller or registry change:

| Check | Command | Purpose |
| --- | --- | --- |
| Compile touched Python files | `python3 -m py_compile <changed files>` | catches syntax/import-time regressions in the current slice |
| HTTP registry contract | `python3 -m pytest -q tests/test_http_registration_contract.py --tb=short` | validates registry, route ownership, helper allowlist, controller guardrails, and split-module ownership |
| Service layout contract | `python3 -m pytest -q tests/test_service_layer_layout.py --tb=short` | validates domain layout registry, docs existence, and service facade guardrails |
| Route inventory contract | `python3 -m pytest -q tests/test_route_inventory_contract.py --tb=short` | validates route inventory stability and API docs route references |
| Focused smoke set | `python3 -m pytest -q tests/test_http_registration_contract.py tests/test_service_layer_layout.py tests/test_route_inventory_contract.py tests/test_admin_config.py tests/test_api.py --tb=short` | current broad-enough regression set for controller cleanup without running the full suite |
| Lint | `python3 scripts/run_lint.py` | catches style and static guardrail issues |
| Route export | `python3 scripts/export_flask_routes.py --json-out /tmp/ai_crm_routes.json && jq -r '.route_count' /tmp/ai_crm_routes.json` | verifies the generated inventory remains exportable |
| Diff whitespace | `git diff --check` | catches trailing whitespace and conflict markers |
| Build smoke | `python3 scripts/run_build.py` | final packaging smoke; currently requires local `DATABASE_URL`/PostgreSQL configuration |

## Remaining Large Files

Large route-owner files that remain worth considering, ordered by current cleanup value:

| File | Lines | Suggested next action |
| --- | ---: | --- |
| `wecom_ability_service/http/admin_config.py` | 339 | already under the current guardrail; only split if another coherent config surface appears |
| `wecom_ability_service/http/internal_auth.py` | 328 | already separated from route-level login; avoid extra auth churn unless there is a clear guard/runtime boundary |
| `wecom_ability_service/http/automation_conversion.py` | 348 | route aggregator; acceptable while it remains registration-only |
| `wecom_ability_service/http/admin_jobs.py` | 265 | already separated from broadcast jobs; keep below the guardrail |
| `wecom_ability_service/http/admin_user_ops.py` | 244 | already separated from delivery/send-record handlers |
| `wecom_ability_service/http/admin_customers.py` | 243 | acceptable unless customer detail actions grow |
| `wecom_ability_service/http/wechat_pay.py` | 272 | public H5/JSAPI checkout and product-intro owner; keep payment client work in the domain |
| `wecom_ability_service/http/admin_wechat_pay_products.py` | 218 | focused owner for product CRUD, sharing, lead-plan binding, and long-image slices |
| `wecom_ability_service/http/admin_wechat_pay.py` | 149 | focused owner for transaction list/detail, export, and refund APIs |
| `wecom_ability_service/http/admin_questionnaire_console.py` | 131 | external push-log list/retry handlers have been split into `admin_questionnaire_push_logs.py` |
| `wecom_ability_service/http/admin_questionnaire_push_logs.py` | 215 | new focused owner for external push-log list/retry handlers |
| `wecom_ability_service/http/automation_conversion_page_actions.py` | 241 | agent orchestration and auto-reply monitor page actions have been split into focused child controllers |
| `wecom_ability_service/http/automation_conversion_agent_page_actions.py` | 113 | focused owner for agent orchestration page save/review/replay actions |
| `wecom_ability_service/http/automation_conversion_auto_reply_actions.py` | 103 | focused owner for auto-reply monitor toggle/capture/run-due page actions |
| `wecom_ability_service/http/sidebar.py` | 166 | lead-pool handlers have been split into `sidebar_lead_pool.py`; base sidebar keeps binding, JSSDK, and signup-tag actions |
| `wecom_ability_service/http/sidebar_lead_pool.py` | 72 | focused owner for `/api/sidebar/lead-pool*` user-ops handlers |
| `wecom_ability_service/http/sidebar_marketing.py` | 103 | route owner only; adapter/presenter assembly moved to `sidebar_marketing_support.py` |
| `wecom_ability_service/http/public_questionnaires.py` | 260 | diagnostics/debug session handlers have been split into `public_questionnaire_diagnostics.py` |
| `wecom_ability_service/http/public_questionnaire_diagnostics.py` | 60 | focused owner for client diagnostics and debug session endpoint |
| `wecom_ability_service/http/cloud_orchestrator_campaigns.py` | 189 | campaign member/step handlers have been split into `cloud_orchestrator_campaign_details.py` |
| `wecom_ability_service/http/cloud_orchestrator_campaign_details.py` | 87 | focused owner for campaign member and step APIs |
| `wecom_ability_service/http/automation_conversion_agent_api.py` | 222 | router callback handlers have been split into `automation_conversion_router_callback_api.py` |
| `wecom_ability_service/http/automation_conversion_router_callback_api.py` | 49 | focused owner for router callback replay/check APIs |
| `wecom_ability_service/http/image_library_endpoint.py` | 153 | image creation handlers have been split into `image_library_create.py` |
| `wecom_ability_service/http/image_library_create.py` | 53 | focused owner for upload/from-url/from-base64 create APIs |

Large helper/runtime modules that should not be split just to reduce line count:

| File | Lines | Note |
| --- | ---: | --- |
| `wecom_ability_service/http/__init__.py` | 291 | route registry hub; keep centralized so registry/placement contracts stay inspectable |
| `wecom_ability_service/http/admin_support.py` | 616 | shared admin rendering/action-token helpers; split only by stable helper responsibility |
| `wecom_ability_service/http/automation_conversion_workspaces.py` | 595 | page payload assembly; better next target is domain/application payload ownership, not more HTTP files |
| `wecom_ability_service/http/background_jobs.py` | 431 | callback/background runtime; treat separately from route-owner cleanup |
| `wecom_ability_service/http/sync_support.py` | 379 | sync helper surface; split only with sync-job ownership tests |
| `wecom_ability_service/http/automation_conversion_render.py` | 353 | render adapter helpers; keep out of the route aggregator |
| `wecom_ability_service/http/questionnaire_support.py` | 282 | questionnaire helper surface; split only with questionnaire-focused regression tests |
| `wecom_ability_service/http/sidebar_marketing_support.py` | 264 | sidebar marketing query/command adapter and display payload assembly |
| `wecom_ability_service/http/image_library_support.py` | 46 | image-library request parsing helpers reused by create and owner controllers |

## Current Read

Priority 1-2 is effectively in final-hardening mode: the route registry, ownership contracts, placement documentation, and route export all line up.
The `admin_questionnaire_console.py` external push-log surface is split into `admin_questionnaire_push_logs.py`.
The `automation_conversion_page_actions.py` agent orchestration and auto-reply monitor actions are split into focused child controllers.
The `sidebar.py` lead-pool handlers are split into `sidebar_lead_pool.py`.
The `sidebar_marketing.py` controller is now a thin HTTP adapter backed by `sidebar_marketing_support.py`.
The `public_questionnaires.py` diagnostics/debug handlers are split into `public_questionnaire_diagnostics.py`.
The `cloud_orchestrator_campaigns.py` member/step handlers are split into `cloud_orchestrator_campaign_details.py`.
The `automation_conversion_agent_api.py` router callback handlers are split into `automation_conversion_router_callback_api.py`.
The `image_library_endpoint.py` image creation handlers are split into `image_library_create.py`.
The WeChat Pay product and transaction admin route owners are now split from the public H5/JSAPI owner.
The remaining route-owner files are either already under guardrail or need a separate product-area pass.
