# Service Layer Layout

This document defines the service-layer contract for `wecom_ability_service`.

## Rules

Only two domain layout modes are allowed:

1. `simple`
- a primary `service.py`
- declared persistence modules such as `repo.py`
- optional declared companion service modules such as `product_service.py` or `admin_service.py`
- optional declared domain-local support modules such as `client.py` or `exceptions.py`

2. `complex`
- `service.py`
- `queries.py`
- `writers.py`
- optional `repo.py` as an aggregation entry

Companion files are allowed only when they are declared in `DOMAIN_LAYOUTS`, stay inside one of those two modes, and do not create a third layering style.
Examples:
- `definitions.py` for domain-owned rules
- `preflight_service.py` for a small domain-local application assembly helper

## Direction Of Dependencies

- HTTP controller -> domain `service.py`
- Domain service modules -> same-domain persistence modules or declared domain service adapters
- Domain code -> `infra/*` for shared constants, settings, runtime clients, and low-level helpers
- `wecom_ability_service/services.py` -> compatibility facade only

Forbidden directions:
- controller -> raw SQL
- controller -> direct `requests` / `WeComClient.from_*`
- domain -> Flask response objects
- new business implementation -> `services.py`

## HTTP Controller Placement

The current registry, ownership, test matrix, and remaining large-file checkpoint is tracked in
`docs/architecture/http_route_consolidation_check.md`.

`wecom_ability_service/http/automation_conversion.py` is a route aggregator only.
It should register URL rules and import handlers from focused child controllers, but it should not parse requests, call domain services, render templates, or import Flask helpers directly.

Automation-conversion handlers are split by surface:

- `automation_conversion_pages.py`: page entry points and program CRUD form handlers
- `automation_conversion_page_actions.py`: page form actions and redirects
- `automation_conversion_agent_page_actions.py`: agent orchestration page form actions
- `automation_conversion_auto_reply_actions.py`: auto-reply monitor page actions
- `automation_conversion_member_api.py`: member action and manual-send JSON APIs
- `automation_conversion_segments.py`: member segment search and segment broadcast APIs
- `automation_conversion_setup.py`: program setup, publish, and customer-acquisition APIs
- `automation_conversion_templates.py`: action templates and profile-segment template APIs
- `automation_conversion_workflows.py`: workflow, node, dashboard, and execution APIs
- `automation_conversion_agent_api.py`: agent output, agent config, and router callback APIs
- `automation_conversion_router_callback_api.py`: router callback replay and pending-check APIs
- `automation_conversion_review.py`: auto-reply review-output APIs
- `automation_conversion_runtime_api.py`: internal runtime trigger and callback APIs
- `automation_conversion_delivery.py`: focus-send and SOP v1 delivery APIs
- `automation_conversion_settings.py`: settings, default channel, and model infra APIs

Automation-conversion helper modules are not route owners:

- `_routes_helpers.py`: request parsing, program route helpers, and response-shape helpers
- `automation_conversion_render.py`: admin template render functions
- `automation_conversion_workspaces.py`: page workspace payload assembly
- `automation_conversion_uploads.py`: form upload parsing for manual-send images
- `automation_conversion_form_helpers.py`: program form payload and redirect helpers

`wecom_ability_service/http/cloud_orchestrator_endpoint.py` follows the same route-aggregator pattern.
It registers Cloud Orchestrator routes only; handlers are split by surface:

- `cloud_orchestrator_pages.py`: admin page entry points
- `cloud_orchestrator_plans.py`: plan, audit, and observability APIs
- `cloud_orchestrator_segments.py`: segment list/detail/preview APIs
- `cloud_orchestrator_campaigns.py`: campaign lifecycle, member, and step APIs
- `cloud_orchestrator_campaign_details.py`: campaign member and step APIs
- `cloud_orchestrator_media.py`: media upload HTTP adapter

`wecom_ability_service/http/admin_api_docs.py` is a page adapter only.
Static API documentation metadata, quick reference assembly, and Markdown export generation belong to `wecom_ability_service/domains/admin_api_docs/service.py`.

`wecom_ability_service/http/admin_config.py` owns the general configuration center pages and form actions.
Config JSON APIs are isolated in `admin_config_api.py` so API response shaping and request-body validation do not inflate the page controller.
Login access and account-management actions are isolated in `admin_config_login_access.py` so admin-auth account payloads and role-guarded WeCom directory refreshes do not inflate the general config controller.
Marketing-automation / signup-conversion compatibility routes are isolated in `admin_config_marketing_automation.py` so automation-engine application commands do not inflate the general config controller.

`wecom_ability_service/http/sidebar.py` owns the base sidebar surface: mobile binding, JSSDK config, and signup-tag actions.
Lead-pool status and class-term upsert handlers are isolated in `sidebar_lead_pool.py` so user-ops application commands do not inflate the base sidebar controller.
Marketing status and enrollment/followup overrides are isolated in `sidebar_marketing.py` so automation-engine application commands do not inflate the base sidebar controller.
`sidebar_marketing_support.py` holds the sidebar marketing query/command adapter and display payload assembly used by both sidebar controllers.

`wecom_ability_service/http/public_questionnaires.py` owns public questionnaire pages and definition/submit/result APIs.
WeChat OAuth start/callback handlers are isolated in `public_questionnaire_oauth.py` so OAuth exchange and session-write handling do not inflate the public questionnaire controller.
Client diagnostics and debug session handlers are isolated in `public_questionnaire_diagnostics.py` so diagnostics logging does not inflate the public questionnaire controller.

`wecom_ability_service/http/internal_auth.py` owns request guards, RBAC checks, action tokens, and sunset interception.
Login, logout, and Enterprise WeChat SSO route handlers are isolated in `admin_auth_routes.py` so route-level authentication flow does not inflate the guard module.

`wecom_ability_service/http/admin_user_ops.py` owns lead-pool list, import, export, and maintenance APIs plus the user-ops UI shell.
Do-not-disturb, one-time batch send, and send-record APIs are isolated in `admin_user_ops_delivery.py` so message-send upload parsing and WeCom media validation do not inflate the lead-pool controller.

`wecom_ability_service/http/admin_jobs.py` owns the sync/task console and `/api/admin/jobs*` operational APIs.
Broadcast queue page and `/api/admin/broadcast-jobs*` handlers are isolated in `admin_broadcast_jobs.py` so broadcast queue operations do not inflate the general jobs controller.

`wecom_ability_service/http/admin_questionnaire_console.py` owns questionnaire shell and editor pages.
External push-log list and retry handlers are isolated in `admin_questionnaire_push_logs.py` so push-log query/retry orchestration does not inflate the questionnaire editor controller.

`wecom_ability_service/http/image_library_endpoint.py` owns the image-library page, listing, details, update, delete, references, and resolve-test APIs.
Image creation handlers are isolated in `image_library_create.py` so upload/from-url/from-base64 request handling does not inflate the image-library owner.

WeChat Pay HTTP handlers are split by product surface:

- `wechat_pay.py`: H5/JSAPI checkout, public product intro pages, order creation/status, and payment notification callbacks.
- `admin_wechat_pay.py`: admin transaction list/detail, export, and refund request APIs.
- `admin_wechat_pay_products.py`: admin product CRUD, product sharing, lead-plan binding, and long-image slice APIs.

WeChat Pay business rules stay in `wecom_ability_service/domains/wechat_pay/*`.
`service.py` owns checkout, paid re-entry, and payment notification reconciliation.
`product_service.py` owns product lifecycle, public product page state, long-image slices, sharing QR data, and lead-plan QR binding.
`admin_service.py` owns admin transaction read models, status labels, export jobs, and refund request orchestration.
`repo.py` owns order/refund/export persistence, `product_repo.py` owns product and product-slice persistence, and `client.py` is the domain-local WeChat Pay API client.

## Current Domain Modes

| Domain | Mode | Primary responsibility | Notes |
| --- | --- | --- | --- |
| `admin_api_docs` | `simple` | API documentation metadata, quick reference, Markdown export view model | `repo.py` is an empty persistence placeholder |
| `archive` | `simple` | archived messages, sync runs, message batches | `service.py + repo.py` |
| `callbacks` | `simple` | external-contact callback business orchestration | `service.py + repo.py` |
| `class_user` | `simple` | signup status state machine and history | `service.py + repo.py` |
| `contacts` | `simple` | contact snapshot, description sync, WeCom contact reads | `service.py + repo.py` |
| `group_chats` | `simple` | group-chat snapshot and persistence | `service.py + repo.py` |
| `identity` | `simple` | people, bindings, identity map, resolve flow | `service.py + repo.py` |
| `questionnaire` | `simple` | questionnaire definition, submit, export, SCRM apply | `preflight_service.py` is a narrow companion helper |
| `routing_config` | `simple` | owner role map, signup routing, mapping rules | `definitions.py` keeps domain-owned rules |
| `tags` | `simple` | tag snapshot, signup tag rules, tag refresh | `service.py + repo.py` |
| `tasks` | `simple` | outbound task dispatch and persistence | `service.py + repo.py` |
| `user_ops` | `simple` | lead pool, imports, activation, deferred jobs, class-term mapping | `service.py + repo.py` |
| `wechat_pay` | `simple` | WeChat Pay H5/JSAPI checkout, product management, transaction admin, refunds, and payment notification handling | `service.py + product_service.py + admin_service.py + repo.py + product_repo.py`; `client.py` stays a domain-local third-party API client |

## Shared Infra

`wecom_ability_service/infra/` is the only shared layer for cross-domain support:

- `constants.py`: cross-domain constants and enumerations
- `settings.py`: app-setting storage helpers
- `helpers.py`: low-level shared helpers
- `wechat_oauth.py`: WeChat OAuth HTTP client helpers
- `wecom_runtime.py`: runtime wrappers around WeCom clients

## `services.py`

`wecom_ability_service/services.py` stays as a thin compatibility facade.
It may only contain:

- re-exports for old import paths
- a small number of wrappers for backward-compatible call signatures
- monkeypatch / dependency injection glue needed by existing tests

It must not contain:

- new domain implementation
- raw SQL
- direct third-party HTTP calls
- domain-owned business rules
