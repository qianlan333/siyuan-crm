# Frontend Parity Plan

## Non-Negotiable Rule

The frontend is not being redesigned. The old AI-CRM frontend is the product baseline.

New backend architecture must support the current user experience: pages, navigation, interaction paths, table fields, filters, drawers, modals, button placement, visual style, and information density. Backend rewrite work must not simplify or reshape the frontend.

## Copied Baseline Sources

This slice copies the legacy frontend baseline into:

- `../../aicrm_next/frontend_compat/templates/`
- `../../aicrm_next/frontend_compat/static/`

Copied sources:

- `historical retired wecom_ability_service reference (base.html)`
- `aicrm_next/frontend_compat/templates/admin_console/customers.html`
- `aicrm_next/frontend_compat/templates/admin_console/customer_detail.html`
- `aicrm_next/frontend_compat/templates/admin_user_ops.html`
- `aicrm_next/questionnaire/templates/admin_questionnaires.html`
- `aicrm_next/frontend_compat/templates/questionnaire_h5_page.html`
- `aicrm_next/frontend_compat/templates/questionnaire_h5_submitted.html`
- `aicrm_next/frontend_compat/templates/questionnaire_h5_result.html`
- `wecom_ability_service/templates/admin_console/*`
- `wecom_ability_service/static/admin_console/*`

The copied files are the baseline. Any future edits must be limited to compatibility variables, static paths, or API adapter wiring.

## Page Inventory

| Page | first-slice status | parity action |
| --- | --- | --- |
| `/admin` | copied | copied admin shell and dashboard template; fixture context adapter supplies shell data |
| `/admin/customers` | partial | copied customers template; customer read-model adapter now supplies list filters and detail/timeline/recent-message API support |
| `/admin/questionnaires` | partial | copied questionnaire console/list template and root editor template; fixture context adapter supplies preflight and questionnaire list |
| `/admin/user-ops/ui` | copied | copied `admin_user_ops.html`; support existing drawer/modal JS contract through API adapters |
| `/admin/automation-conversion` | next-native | retired old program list; route now renders the AI Audience package list from `ai_audience_ops` |
| `/admin/jobs` | planned | copy jobs page; keep action confirmation flow |
| `/admin/wechat-pay/transactions` | planned | copy transaction admin page and adapters |
| `/admin/wechat-pay/products` | planned | copy product management page and editor interactions |
| `/admin/alipay/transactions` | planned | copy Alipay transaction page |
| `/admin/image-library` | planned | copy image library page and upload controls |
| `/admin/miniprogram-library` | planned | copy miniprogram library page |
| `/admin/attachment-library` | planned | keep navigation target; copy page when current source is finalized |
| `/admin/config` | planned | copy config overview and subpages |
| `/admin/api-docs` | planned | copy human-readable API docs page |

## Adapter Strategy

- Preserve old path names whenever the frontend calls JSON APIs.
- Preserve old response envelopes and core field names.
- Add FastAPI adapters when new application DTOs differ from legacy JSON.
- Keep frontend shell compatibility in `historical removed reference (legacy_routes.py)` while copied templates are being wired one page at a time.
- Do not import old Flask services or old backend packages.

Current legacy route support:

- `GET /admin`
- `GET /admin/customers`
- `GET /admin/questionnaires`
- `GET /admin/questionnaires/ui`
- `GET /admin/user-ops/ui`

Current Customer Center adapter support:

- `GET /api/customers`
- `GET /api/customers/{external_userid}`
- `GET /api/customers/{external_userid}/timeline`
- `GET /api/messages/{external_userid}/recent`

Customer Center status:

- `/admin/customers` uses the copied legacy customers template and no new UI redesign.
- The backend adapter is `partial`: it supports owner/tag/status/is_bound/mobile/keyword filters, drawer-support detail fields, timeline pagination/type filters, and recent messages.
- The data source remains fixture/in-memory and is not connected to the production customer database yet.
- Missing or unknown `external_userid` returns 404; the detail adapter does not fallback from mobile to customer detail.

Current User Ops adapter support:

- `GET /api/admin/user-ops/overview`
- `GET /api/admin/user-ops/list`
- `POST /api/admin/user-ops/do-not-disturb`
- `POST /api/admin/user-ops/batch-send/preview`
- `POST /api/admin/user-ops/batch-send/execute`
- `GET /api/admin/user-ops/send-records`
- `GET /api/admin/user-ops/send-records/{record_id}`
- `POST /api/admin/user-ops/send-records/{record_id}/refresh`
- `GET /api/admin/user-ops/export`
- `GET /api/admin/miniprogram-library`

Current backend depth:

- User Ops pool/list/overview, do-not-disturb, batch-send preview/execute, and send records are `partial`.
- The old User Ops frontend remains unchanged as the baseline.
- Execute uses a fake `integration_gateway` dispatch adapter; it does not call real Enterprise WeChat.
- The default repository remains fixture/in-memory. A PostgreSQL-ready SQLAlchemy repository and Alembic schema now exist for User Ops, but they are not wired to a production PostgreSQL database yet.

Current Questionnaire adapter support:

- `GET /admin/questionnaires`
- `GET /admin/questionnaires/ui`
- `GET /s/{slug}`

Questionnaire status:

- The admin questionnaire page uses the copied legacy `aicrm_next/questionnaire/templates/admin_console/questionnaires.html` template with a minimal `questionnaire_payload` context adapter.
- The legacy root editor template and public H5 templates are copied into `frontend_compat/templates/` for parity baseline.
- The backend adapter is `partial`: it supports fixture-backed admin list/detail/create/update/enable/disable/delete/export/debug contracts, public H5 get/submit/result contracts, and fake OAuth start/callback contracts.
- Real WeChat OAuth, real WeCom tagging/contact calls, external webhook push, and production database persistence are not connected.

Current Automation Conversion / AI Audience status:

- `GET /admin/automation-conversion` is no longer part of the experiment frontend-compat smoke manifest.
- In the main application, the first-level route is owned by `ai_audience_ops` and renders the AI Audience package list.
- Old automation program overview, pool, member, state-transition, activation-webhook, fake OpenClaw push, execution-record, setup, workspace, and Runtime V2 routes are retired and must not be restored as frontend parity targets.
- The frontend baseline for this route is intentionally narrow: page title `AI 自动化运营`, card title `人群包列表`, and the four-column AI audience package table.

## Forbidden UI Changes

- Do not change navigation information architecture.
- Do not change table fields or filter names.
- Do not remove drawers, modals, or action buttons.
- Do not convert dense operational pages into marketing/landing layouts.
- Do not move User Ops batch-send, send-records, detail drawer, or timeline drawer interactions.
- Do not rename visible labels merely because backend contexts changed.

## Commerce / Media Frontend Baseline

Current first-slice support:

- `GET /admin/wechat-pay/products`
- `GET /admin/wechat-pay/transactions`
- `GET /admin/alipay/transactions`
- `GET /admin/image-library`
- `GET /admin/attachment-library`
- `GET /admin/miniprogram-library`

Parity status:

- WeChat transaction page uses the copied `aicrm_next/frontend_compat/templates/admin_console/wechat_pay_transactions.html` template with a minimal context adapter.
- Image library uses the copied `aicrm_next/frontend_compat/templates/admin_console/image_library.html` template and static dependencies.
- Mini-program library uses the copied `aicrm_next/frontend_compat/templates/admin_console/miniprogram_library.html` template and static dependencies.
- Product management, Alipay transactions, and attachment library currently use the copied admin shell partial adapter until exact old templates are available.

No commerce or media page may be redesigned in this migration. The new backend must keep supporting old labels, filters, table density, and action entry points through compatible APIs.

## Route-Level Smoke / Screenshot Baseline

Current evidence:

- Route manifest: `docs/archive/experiments_ai_crm_next/docs/frontend_route_manifest.md`
- Baseline report: `docs/archive/experiments_ai_crm_next/docs/frontend_screenshot_baseline.md`
- Tool and smoke test: retired; see `docs/archive/experiments_ai_crm_next/retired_tools.md`.

Latest local result:

- 13 routes checked through AI-CRM Next TestClient.
- 13 routes returned expected status and required text.
- Forbidden placeholder text was absent.
- HTML snapshots were generated under `artifacts/frontend_screenshots/html/`.
- PNG screenshots were generated under `artifacts/frontend_screenshots/png/`.
- Screenshot dependency installed in the experiment venv: Playwright `1.60.0` with Chromium `v1223` / Chrome for Testing `148.0.7778.96`.

This baseline is `baseline_available` for route-level smoke and screenshot evidence. It does not mark any frontend module `production_ready`, and ordinary pytest does not require Playwright/browser availability.
