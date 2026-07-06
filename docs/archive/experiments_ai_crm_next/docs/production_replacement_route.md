# AI-CRM Next Production Replacement Route

The replacement route must keep old Flask production safe until AI-CRM Next has real database, real external adapter, dual-run, smoke, backup, and rollback evidence. Passing fixture parity is necessary but not sufficient.

## Phase 0: Continue Experiment Isolation

- Keep old Flask production service unchanged.
- Keep AI-CRM Next in `experiments/ai_crm_next/`.
- Run ordinary pytest, fixture parity, and optional test PostgreSQL only.
- Keep external adapters in fake mode.
- Do not connect production PostgreSQL or production provider credentials.

Exit criteria:

- Ordinary pytest passes.
- Six parity CLIs pass.
- Architecture boundary scan shows no old backend imports.
- Old production entrypoints are clean.

## Phase 1: Real PostgreSQL Test Database Validation

- Prepare a local or isolated `aicrm_next_test` database.
- Set `AICRM_NEXT_TEST_DATABASE_URL` with a localhost/test database URL.
- Run Alembic `upgrade head` and downgrade tests.
- Run User Ops SQL repo integration tests.
- Run Customer Read Model SQL repo integration tests.
- Capture and archive PG integration results.

Exit criteria:

- Migrations upgrade/downgrade cleanly.
- User Ops and Customer Read Model SQL repos pass on real PostgreSQL test DB.
- Safety guard rejects non-test database URLs.

Current evidence:

- 2026-05-20 14:34 CST: local PostgreSQL test database `aicrm_next_test` on `127.0.0.1:5432` passed safety guard validation.
- `docs/archive/experiments_ai_crm_next/workspace/scripts/run_postgres_integration_tests.sh` passed with `3 passed, 166 deselected`.
- `.venv/bin/python -m pytest -q -m postgres_integration` passed with `3 passed, 166 deselected`.
- Alembic `upgrade head` / `downgrade base`, User Ops SQL repo integration, and Customer Read Model SQL repo integration all executed on the real local test database.
- Phase 1 local test database evidence is available in `docs/archive/experiments_ai_crm_next/docs/real_postgres_integration_run.md`. This is not production PostgreSQL evidence and does not change any module to `production_ready`.

## Phase 2: Readonly Dual-Run

Run old Flask and AI-CRM Next side by side. Compare only read endpoints:

- `/api/customers`
- `/api/customers/{external_userid}`
- `/api/customers/{external_userid}/timeline`
- `/api/messages/{external_userid}/recent`
- `/api/admin/user-ops/overview`
- `/api/admin/user-ops/list`
- questionnaire admin/public read endpoints
- product read and transaction list endpoints
- media library read endpoints

Do not run old production writes during this phase.

Tooling:

- `retired readonly HTTP dual-run helper; see docs/archive/experiments_ai_crm_next/retired_tools.md` is the preferred first dual-run harness for Customer Read Model and User Ops.
- The tool sends only `GET` requests to old Flask and refuses old-service write methods.
- Current tooling status: executed against local old Flask on 2026-05-20; the latest report passed with one User Ops overview legacy drift warning and customer sample-dependent routes covered by masked local test data.
- Strategy doc: `docs/archive/experiments_ai_crm_next/docs/readonly_http_dual_run_strategy.md`.
- Latest evidence: `docs/archive/experiments_ai_crm_next/docs/real_readonly_http_dual_run.md`.

Exit criteria:

- Parity reports show no blockers.
- Known accepted differences are documented.
- Frontend smoke passes against AI-CRM Next adapters.

Frontend smoke evidence:

- `docs/archive/experiments_ai_crm_next/docs/frontend_route_manifest.md` lists the 14 current admin/public routes.
- `docs/archive/experiments_ai_crm_next/docs/frontend_screenshot_baseline.md` records the latest TestClient smoke result.
- Current status: route smoke passed with HTML snapshots and PNG screenshots generated through Playwright/Chromium.
- Media Library gray-release preparation evidence is available in `docs/archive/experiments_ai_crm_next/docs/media_library_gray_release_plan.md`, `docs/archive/experiments_ai_crm_next/docs/media_library_route_cutover_manifest.md`, and `retired experiment wrapper; see docs/archive/experiments_ai_crm_next/retired_tools.md`. Default smoke is read-only; fake writes are Next TestClient only and do not switch production traffic.
- Product Management gray-release preparation evidence is available in `docs/archive/experiments_ai_crm_next/docs/product_management_gray_release_plan.md`, `docs/archive/experiments_ai_crm_next/docs/product_management_route_cutover_manifest.md`, and `retired experiment wrapper; see docs/archive/experiments_ai_crm_next/retired_tools.md`. Default smoke is read-only; fake product writes are explicit opt-in and Next TestClient only. Checkout/payment routes are documented as no-production and excluded from gray smoke.
- Customer Read Model readonly gray-release preparation evidence is available in `docs/archive/experiments_ai_crm_next/docs/customer_read_model_gray_release_plan.md`, `docs/archive/experiments_ai_crm_next/docs/customer_read_model_route_cutover_manifest.md`, `docs/archive/experiments_ai_crm_next/docs/customer_read_model_sample_data_checklist.md`, `retired customer sample seed helper; see docs/archive/experiments_ai_crm_next/retired_tools.md`, and `retired experiment wrapper; see docs/archive/experiments_ai_crm_next/retired_tools.md`. Default smoke is GET-only; optional old-base-url dual mode also sends only GET. The latest local masked sample run covered detail/timeline/recent messages with `skipped=0`.
- User Ops readonly gray-release preparation evidence is available in `docs/archive/experiments_ai_crm_next/docs/user_ops_readonly_gray_release_plan.md`, `docs/archive/experiments_ai_crm_next/docs/user_ops_readonly_route_cutover_manifest.md`, `docs/archive/experiments_ai_crm_next/docs/user_ops_readonly_sample_and_drift_checklist.md`, and `retired experiment wrapper; see docs/archive/experiments_ai_crm_next/retired_tools.md`. Default smoke is GET-only; optional old-base-url dual mode also sends only GET. DND, batch-send preview/execute, deferred jobs, internal writes, and real WeCom dispatch are excluded.
- Questionnaire readonly gray-release preparation evidence is available in `docs/archive/experiments_ai_crm_next/docs/questionnaire_readonly_gray_release_plan.md`, `docs/archive/experiments_ai_crm_next/docs/questionnaire_readonly_route_cutover_manifest.md`, `docs/archive/experiments_ai_crm_next/docs/questionnaire_readonly_sample_and_fake_checklist.md`, `retired questionnaire sample seed helper; see docs/archive/experiments_ai_crm_next/retired_tools.md`, and `retired experiment wrapper; see docs/archive/experiments_ai_crm_next/retired_tools.md`. Default smoke is GET-only; fake submit is explicit opt-in and Next TestClient only. The latest local masked sample run passed with `blockers=0`; old WeChat-gate/public-result route differences are recorded as legacy drift. Real OAuth, WeCom tag mutation, external webhook push/retry, and admin writes are excluded.
- Automation readonly gray-release preparation is retired. `/admin/automation-conversion`
  now belongs to AI Audience, and the old automation_program/runtime-v2
  smoke/parity artifacts were removed instead of carried forward.

Current known gaps:

- `user_ops / overview.default` recorded legacy drift because old local Flask response lacked the required `激活待录入` overview card label while Next satisfied the current product contract.
- Old `/admin/customers` returns `302 /login?next=/admin/customers` in unauthenticated local checks; this is recorded as `legacy_admin_auth_redirect` and does not block API dual-run evidence.
- Browser PNG screenshots are available for the current 14-route baseline, but this remains route-level evidence only and does not prove production auth or real data rendering.
- Media Library still uses fake/in-memory storage. Real cloud storage and WeCom media upload are not connected.
- Product Management still uses fake/in-memory product storage and fake payment boundaries. Real WeChat Pay, Alipay, production product publishing, and production checkout are not connected.
- Customer Read Model now has representative masked old test data for local detail/timeline/recent-message dual-run coverage. Real WeCom contact sync, message archive sync, tag refresh, OpenClaw webhook, production data backfill, and production route cutover are still not connected.
- User Ops readonly gray preparation keeps the old `激活待录入` missing-card mismatch as accepted legacy drift only when Next satisfies the current 8-card contract. DND, batch-send, deferred jobs, and real WeCom dispatch are not connected.
- Questionnaire readonly gray preparation has Next-only read evidence, optional Next-only fake-submit evidence, and local old Flask masked-sample dual evidence. Accepted legacy drift remains: old public API can require WeChat browser context, and old result rendering uses `/s/{slug}/result/{result_token}` rather than Next's JSON result API path. This does not authorize production submit, OAuth, WeCom tag, or webhook cutover.
- Automation readonly gray preparation has Next-only read evidence, optional Next-only fake state-machine write evidence, and local old-test route-alias dual evidence after masked sample seeding. Accepted legacy drift remains: old exact Next-style read route names return 404, old aliases use legacy payload shapes, and the old admin page redirects unauthenticated requests. This does not authorize activation webhook, OpenClaw push, WeCom dispatch, external webhook, workflow runtime, agent runtime, production data backfill, or production route cutover.

## Phase 3: Shadow Writes / Fake External

- Route write requests only to AI-CRM Next test PostgreSQL.
- Keep WeCom, OAuth, payment, OpenClaw, webhook, and cloud storage fake.
- Compare resulting records against expected old-system semantics.
- Verify idempotency and audit logs.

Exit criteria:

- Write-side reports have no blockers.
- Fake external payload previews are safe and audited.
- Rollback remains trivial because no production external effects occur.

## Phase 4: Single-Module Gray Release

Recommended order:

1. Media Library.
2. Product Management.
3. Customer Read Model readonly.
4. User Ops readonly.
5. Questionnaire admin.
6. Automation Conversion readonly.
7. Questionnaire public submit.
8. Commerce fake provider to real provider.
9. WeCom / OpenClaw real external adapters.

Rules:

- Promote one module at a time.
- Keep route-level feature switches.
- Keep module rollback independent.
- Disable fake mode only after real provider tests pass.
- User Ops readonly promotion requires `retired experiment wrapper; see docs/archive/experiments_ai_crm_next/retired_tools.md` to pass, with old-service writes disabled and only accepted legacy drift recorded.
- Questionnaire readonly promotion requires `retired experiment wrapper; see docs/archive/experiments_ai_crm_next/retired_tools.md` to pass, with old-service writes disabled, fake submit disabled by default, and real OAuth/WeCom/webhook calls disabled.
- Automation readonly promotion is retired; validate the AI Audience page and API instead.

Controlled execution materials:

- `docs/archive/experiments_ai_crm_next/docs/route_level_gray_release_batches.md` defines Batch 0-6 and the included/excluded routes.
- `docs/archive/experiments_ai_crm_next/docs/route_level_gray_release_runbook.md` defines preflight, execution, smoke, rollback, and forbidden actions.
- `docs/archive/experiments_ai_crm_next/docs/route_level_proxy_template.md` provides pseudo-only route flag and proxy examples. It must not be applied directly.
- `docs/archive/experiments_ai_crm_next/docs/gray_release_signoff_template.md` records operator signoff, adapter modes, rollback owner, and Go/No-Go decision.
- `docs/archive/experiments_ai_crm_next/docs/gray_release_acceptance_checklist.md` lists the required commands and safety checks.
- `retired gray-release report helper; see docs/archive/experiments_ai_crm_next/retired_tools.md` aggregates smoke/parity JSON into a markdown/json signoff report without making requests or changing systems.

Current controlled-execution status: ready for runbook acceptance. Production route cutover has not been executed, no production Nginx/deployment file has been changed, no production PostgreSQL is connected, and all external adapters remain fake/disabled unless separately approved.

Batch 1 local rehearsal evidence:

- `docs/archive/experiments_ai_crm_next/docs/gray_rehearsal_batch_1_media_readonly.md`
- `docs/archive/experiments_ai_crm_next/docs/gray_rehearsal_batch_1_route_flags.md`
- `retired experiment tool wrapper; see docs/archive/experiments_ai_crm_next/retired_tools.md`
- `/tmp/gray_rehearsal_batch_1_media_readonly.json`

The rehearsal passed in Next TestClient mode and did not modify production proxy configuration, switch real traffic, execute old-system writes, upload to cloud storage, or call WeCom media APIs.

Staging-simulated canary evidence:

- Batch 1 Media readonly: `docs/archive/experiments_ai_crm_next/docs/batch_1_media_readonly_canary_execution_report.md` and `docs/archive/experiments_ai_crm_next/docs/batch_1_media_readonly_canary_signoff.md`.
- Batch 2 Product readonly: `docs/archive/experiments_ai_crm_next/docs/batch_2_product_readonly_canary_execution_report.md` and `docs/archive/experiments_ai_crm_next/docs/batch_2_product_readonly_canary_signoff.md`.
- Batch 3 Customer readonly: `docs/archive/experiments_ai_crm_next/docs/batch_3_customer_readonly_canary_execution_report.md` and `docs/archive/experiments_ai_crm_next/docs/batch_3_customer_readonly_canary_signoff.md`.
- Batch 4 User Ops readonly: `docs/archive/experiments_ai_crm_next/docs/batch_4_user_ops_readonly_canary_execution_report.md` and `docs/archive/experiments_ai_crm_next/docs/batch_4_user_ops_readonly_canary_signoff.md`.
- Batch 5 Questionnaire readonly: `docs/archive/experiments_ai_crm_next/docs/batch_5_questionnaire_readonly_canary_execution_report.md` and `docs/archive/experiments_ai_crm_next/docs/batch_5_questionnaire_readonly_canary_signoff.md`.
- Batch 6 Automation readonly: retired with the old automation_program/runtime-v2
  migration artifacts.

All six records are staging-simulated or local rehearsal evidence only. They do not approve production rollout, do not modify production proxy/deploy config, and keep module-specific write/external adapters disabled.

Production canary approval package:

- `docs/archive/experiments_ai_crm_next/docs/production_canary_approval_package.md`
- `docs/archive/experiments_ai_crm_next/docs/production_canary_change_request_template.md`
- `docs/archive/experiments_ai_crm_next/docs/production_canary_observability_plan.md`
- `docs/archive/experiments_ai_crm_next/docs/production_canary_rollback_runbook.md`
- `retired production canary approval helper; see docs/archive/experiments_ai_crm_next/retired_tools.md`

Current approval-package status: `ready_for_human_review` / `pending_human_signoff`. This package can support a human-reviewed readonly production canary request, starting with Batch 1 Media readonly, but it does not execute or authorize a route change by itself.

Batch 1 Media production canary human signoff packet:

- `docs/archive/experiments_ai_crm_next/docs/batch_1_media_readonly_production_canary_signoff_packet.md`
- `docs/archive/experiments_ai_crm_next/docs/batch_1_media_readonly_production_execution_checklist.md`
- `retired Batch 1 media production signoff helper; see docs/archive/experiments_ai_crm_next/retired_tools.md`

Current Batch 1 production signoff status: `pending_human_signoff`. These materials organize target routes, evidence, proposed route flags, stop conditions, rollback steps, and final decision fields for human review only. They do not modify production configuration, enable production route flags, switch traffic, upload to cloud storage, call WeCom media, or authorize Media write routes.

## Phase 5: Production Cutover

- Configure Nginx or application routing for route-level cutover.
- Back up old and new databases.
- Freeze risky writes during switch windows.
- Run route-level smoke checklist.
- Monitor health, logs, audit events, and external adapter status.
- Keep rollback route mapping ready.

Rollback:

- Restore old route mapping.
- Stop AI-CRM Next write path.
- Preserve AI-CRM Next audit/export logs for diagnosis.
- Reconcile any shadow writes before retry.

## Phase 6: Old System Sunset

- Freeze old write entrypoints.
- Keep old Flask read-only archive until reconciliation completes.
- Remove or archive old code only after business owner sign-off.
- Preserve migration reports, parity reports, and smoke evidence.
