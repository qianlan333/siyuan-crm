# AI-CRM / siyuan-crm Core Runtime Parity - 2026-06-12

## 1. Summary

Conclusion: **CORE_RUNTIME_PARITY_WITH_OVERLAYS**

PR-11 aligns the siyuan-crm core Next runtime with `AI-CRM@main` for app router startup, background worker packages, external push service code, and remaining compatibility route ownership that had still been mounted through `frontend_compat` or `post_legacy_deferred`.

No production operation was executed. This PR does not change production env, systemd, nginx, deploy files, migrations, or database state.

## 2. Baselines

- AI-CRM repo: `qianlan333/AI-CRM`
- AI-CRM main SHA: `6feb8c9daa7170ef4b260cb1610f15ef6510e1e6`
- siyuan-crm repo: `qianlan333/siyuan-crm`
- siyuan-crm main SHA: `511bfc25715436548c019c5bd0e894e5d640b997`
- Audit source: `docs/reports/aicrm_siyuan_parity_audit_20260612.md`
- Compare artifacts:
  - `/tmp/pr11_core_runtime_name_status.txt`
  - `/tmp/pr11_core_runtime_diff_stat.txt`

## 3. Runtime / Router Changes

- Removed `frontend_compat_router` import and include from `aicrm_next/main.py`.
- Removed `post_legacy_deferred_router` import and include from `aicrm_next/main.py`.
- Removed `reset_post_legacy_deferred_fixture_state` from runtime fixture reset.
- Kept the static mount for `aicrm_next/frontend_compat/static` because existing Next-owned pages still reuse static assets.
- Moved `/admin/api-docs` ownership to `aicrm_next.admin_config.api`.
- Moved `/admin/runtime-config` ownership to `aicrm_next.admin_config.api`.
- Added the AI-CRM style `/admin/cloud-orchestrator` redirect to the Next cloud plans workspace.
- Moved cloud audit and observability APIs to `aicrm_next.cloud_orchestrator.api`.
- Moved WeCom customer acquisition link safe-mode APIs to `aicrm_next.automation_engine.channels_api`.
- Left `/api/admin/class-user-management/export` on the PR-1 Next-native `aicrm_next.class_user_management.api` owner.

## 4. Background Jobs / External Push

Synced AI-CRM Next-native background job and external push code:

- `aicrm_next/background_jobs/*`
- `aicrm_next/external_push/*`
- Next worker runner scripts:
  - `scripts/run_automation_member_backfill.py`
  - `scripts/run_automation_ops_scheduler.py`
  - `scripts/run_broadcast_queue_worker.py`
  - `scripts/run_external_contact_sync.py`
  - `scripts/run_external_push_worker.py`
  - `scripts/run_reply_monitor_capture.py`
  - `scripts/run_reply_monitor_run_due.py`

These changes do not enable timers, systemd units, or real external calls. They only align code paths and import contracts.

## 5. Preserved siyuan Overlays

- `app.py` operational overlay is retained:
  - `python3 app.py init-next-schema-safe`
  - `python3 app.py sync-customer-read-model`
  - `python3 app.py init-db`
- `scripts/siyuan_migration/*` is unchanged and retained.
- Production readiness, cutover, observation, and parity reports are retained.
- Deployment/env/systemd/nginx overlays are unchanged.
- `scripts/check_no_new_legacy.py`, `tools/generate_legacy_replacement_backlog.py`, and route registry files are retained as siyuan audit guard overlays.
- `aicrm_next/post_legacy_deferred/*` is no longer runtime-mounted; the files remain only as historical guard source until the checker/inventory layer is retired in a separate cleanup.
- `aicrm_next/frontend_compat/legacy_routes.py` is no longer mounted by `main.py`; its exact legacy route list is empty and it remains only as historical metadata/template-adapter source.

## 6. Deferred

- PR-12: sidebar / identity / customer parity.
- PR-13: channel multi-staff assignment, QR semantics, channel center actions, and welcome message parity.
- PR-14: commerce/admin payment and external API docs final parity.
- Physical retirement of route registry and post-legacy guard source is deferred until the checker layer no longer depends on those files.

## 7. Validation

Executed during PR-11 implementation:

- `python3 -m pytest tests/test_pr11_core_runtime_parity.py tests/test_pr1_core_next_routes.py tests/test_pr2_external_orders_routes.py -q` -> passed.
- `python3 scripts/check_no_new_legacy.py --strict` -> passed; `legacy_fallback_routes_count=0`.
- `python3 tools/generate_legacy_replacement_backlog.py --check` -> passed.
- Optional route/freeze tests that exist:
  - `tests/test_production_route_resolution.py`
  - `tests/test_route_registry_final_freeze.py`
  - `tests/test_deploy_workflow_contract.py`
  - `tests/test_external_push_worker_next_native.py`
  -> passed.
- API docs and post-legacy handoff tests:
  - `tests/test_next_api_docs_page.py`
  - `tests/test_production_compat_removed.py`
  - `tests/test_auth_wecom_route_inventory.py`
  - `tests/test_user_ops_admin_pages_native.py`
  - `tests/test_admin_pages_real_data_binding.py`
  - `tests/test_post_legacy_deferred_api_routes.py`
  - `tests/test_post_legacy_deferred_route_ownership.py`
  - `tests/test_http_registration_contract.py`
  -> passed.

Final pre-PR validation is recorded in the PR description.

## 8. Production Boundary

- No production DB writes.
- No Alembic execution.
- No restore, safe-init, or customer projection command execution against production.
- No production service restart.
- No systemd/nginx/env/deploy changes.
- No env, dump, uploads, instance, pem/key, token, secret, AESKey, AppSecret, database URL, or raw business identifier committed.
