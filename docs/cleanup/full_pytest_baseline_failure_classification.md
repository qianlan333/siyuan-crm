# Full Pytest Baseline Failure Classification

## Issue #67 R00 baseline at 5b1f0d47

Baseline commit: `5b1f0d47f10bd74d4570f1613883dd31f9c7f93e`

Authoritative run: [Full Regression 29065227354](https://github.com/qianlan333/AI-CRM-ID-refactor/actions/runs/29065227354)

The baseline run produced `57 failed, 2683 passed`. All 57 failures are retained
below and are classified by root cause. Twenty-two selector failures share one
code defect, so the run contains 36 root-cause groups and 35 failures after that
single selector defect is removed.

| Classification | Raw failures | Root cause | Resolution |
|---|---:|---|---|
| 代码缺陷 | 22 | `workflow_dispatch` may serialize `inputs` as JSON `null`; the selector called `.get()` on it and every selector subprocess exited 1. | Normalize a null/non-mapping `inputs` value before reading `full`; add a null-payload regression test. |
| 测试过期 | 16 | Callback objective coverage still looked for the retired `channel_entry_profile_update` marker after profile updates moved to identity synchronization. | Point the objective proof to the active channel-entry external-effect wakeup contract. No runtime callback behavior changed. |
| 测试过期 | 10 | External-order diagnostic fixtures omitted the registered `service_period_entitlement_consumer`, so complete evidence was misclassified as a missing consumer. | Add the existing consumer to both diagnostic fixtures; keep the production expected-consumer set unchanged. |
| 测试过期 | 3 | Admin-auth tests expected redirects but did not opt in to `AICRM_ADMIN_AUTH_ENFORCED=true`, as required by the global pytest contract. | Enable auth in the three auth-specific tests and assert the unified redirect for the protected legacy URL. |
| 代码缺陷 | 1 | Repository hardening scanned raw response text, so the safe key `fixture_used=false` was treated as fixture data leakage. | Inspect only string values in non-degraded success payloads; degraded controlled responses and boolean field names cannot create false positives. |
| 测试过期 | 1 | WeCom tag inventory still asserted that no tag/group CRUD existed after production CRUD had been explicitly enabled and documented. | Assert the current scoped CRUD/read/sync boundary instead of the retired sentence. |
| 测试过期 | 1 | WeCom tag degraded-read test expected the pre-standardization `production_unavailable` error code. | Assert canonical `production_read_unavailable` while preserving `source_status=production_unavailable`. |
| 代码缺陷 | 1 | Group Ops `application.py` grew to 1597 lines, above its frozen 1545-line budget. | Extract plan response projection into `projections.py`; application logic is now 1506 lines with unchanged response contracts. |
| 测试过期 | 1 | The retired channel-entry page test expected an auth redirect while auth enforcement was disabled for that test process. | Enable auth for the protected-page request, then restore the fixture-mode setting for the remaining API assertions. |
| 代码缺陷 | 1 | `service_period_entitlements.mobile_snapshot` violated the final unionid-only business schema. | Add `0097_service_period_unionid_cleanup`, remove runtime reads/writes of the column, and resolve mobile through `crm_user_identity` by unionid. |

Classification totals: `代码缺陷=25`, `测试过期=32`, `环境缺失=0`,
`能力已退休=0`; total `57`.

Additional environment evidence discovered during local reproduction is not
part of those 57 failures:

- A previously reused local PostgreSQL database pointed at a removed Alembic
  revision; it is classified as `环境缺失` and was replaced with an isolated
  PostgreSQL 16 database.
- This repository's `0001` migration stamps an existing product baseline, so a
  completely blank database needs the standard test/bootstrap schema before
  `alembic upgrade head`. The GitHub and pytest bootstrap path does this today;
  standalone blank-database installation remains explicit R10/R15 work rather
  than being hidden as an R00 pass.
- The local Python 3.10.5 runtime links an older SQLite that does not implement
  PostgreSQL-compatible `->>` JSON extraction. Four injected-SQLite live-source
  tests exposed that portability defect even though the GitHub runner passed
  them. The repository now emits `json_extract` for SQLite sessions and keeps
  `->>` for PostgreSQL; the four existing contracts pass without weakening.
- Re-running the PostgreSQL suite against an existing worker database used to
  recreate two retired baseline tables before noticing Alembic was already at
  head. The test bootstrap now runs only when no `alembic_version` state exists;
  a two-pass bootstrap check finishes at `0097` with both retired-table count
  and forbidden service-period mobile-column count equal to zero.

R00 focused reconciliation after the fixes: `103 passed, 1 skipped`; the skip is
the PostgreSQL-only final-schema guard in fixture mode. The same final-schema
guard plus service-period migration contracts passed `3 passed` against an
isolated PostgreSQL 16 database. Full architecture mode passed, including route,
admin-auth, repository, DB access, lifecycle, SQL, Alembic, module, external
effect, background-job, runtime-inventory, and high-risk-contract gates.

Final local R00 verification on a fresh PostgreSQL 16 base with four isolated
xdist workers: `2754 passed, 0 failed, 292 warnings in 951.04s`. Frontend
verification also passed `npm ci`, TypeScript typecheck, deterministic build,
and all seven frontend contract suites; `npm audit` reported zero
vulnerabilities. The generated runtime inventory remained unchanged after the
build and its final drift check passed.

All 21 declared high-risk success/failure/replay-concurrency nodes passed with
`real_external_call_expected=false`. The `0097` rollback rehearsal restored the
deprecated column at Alembic `0096` (column count `1`) and upgrading back to
head removed it again (column count `0`). Changed-file Ruff checks and the final
architecture/full drift gates passed.

## Historical closed baseline at d30ecc56

Baseline commit: `d30ecc560fd014c938ae24d2d6c8641d2b189d89`

Scope: narrow follow-up after PR #1568. This report classifies and closes only
the 28 `scripts/run_tests.sh` failures observed on current `origin/main`.
No deploy, nginx, systemd, schema migration, external-call enablement, or new
product capability is included.

## Classification

| Category | Failures | Fix summary | Contract coverage |
|---|---:|---|---|
| route-owner drift | 20 | Materialized FastAPI 0.139 included routers into concrete app routes while preserving app dependency overrides; made API docs route scanning recurse into nested routers; updated route inventory count from 688 to current 689; materialized callback ingress routes. | `tests/test_router_registry_contract.py`, `tests/test_next_api_docs_page.py`, route-owner/admin-page tests, `tests/test_customer_read_model_request_scope.py` |
| contract drift | 3 | Restored the HuangXiaoCan usage migration timestamp-cast contract and aligned payment internal-event fake contracts with notify payer-openid persistence. | `tests/test_ai_audience_runtime_hotfixes.py`, `tests/test_internal_events_single_consumer_run.py`, `tests/test_internal_events_payment_slice.py`, `tests/test_unionid_runtime_breakage_hotfix.py` |
| payment drift | 3 | Reused paid H5 orders by payment openid before sidebar context, persisted notify payer openid, and kept product-code alias lookup. | `tests/test_public_product_frontend_contract.py`, `tests/test_unionid_runtime_breakage_hotfix.py` |
| customer projection drift | 2 | Added a SQLite-only identity lookup branch for test projection repositories while preserving Postgres JSONB exact membership checks in runtime SQL. | `tests/test_customer_live_source_repository.py`, `tests/test_external_orders_customer_projection.py`, `tests/test_unionid_runtime_breakage_hotfix.py` |

## Failure Mapping

### Route-owner drift

- `tests/test_auth_wecom_exact_routes.py::test_auth_wecom_exact_routes_are_registered_before_production_compat_wildcard`
- `tests/test_channel_entry_next_retirement_contract.py::test_channel_entry_callbacks_are_next_owned_with_legacy_fallback_disabled`
- `tests/test_channel_radar_tag_admin_pages_next_native.py::test_channel_radar_and_tag_pages_are_served_by_next_native_routers`
- `tests/test_cloud_orchestrator_admin_pages_native.py::test_cloud_root_redirect_is_owned_by_native_cloud_module`
- `tests/test_cloud_orchestrator_admin_pages_native.py::test_cloud_observability_page_renders_from_native_cloud_module`
- `tests/test_commerce_admin_transaction_detail.py::test_admin_transaction_pages_resolve_to_commerce_not_frontend_compat`
- `tests/test_commerce_admin_transaction_detail.py::test_wechat_shop_transaction_page_and_detail_are_next_routes`
- `tests/test_group_ops_plans_api.py::test_group_ops_admin_api_routes_are_registered_on_existing_contracts`
- `tests/test_media_library_admin_pages_native.py::test_media_library_admin_pages_render_from_native_shell`
- `tests/test_media_library_admin_pages_native.py::test_media_library_admin_pages_removed_from_frontend_compat_inventory`
- `tests/test_next_api_docs_page.py::test_api_docs_view_model_scans_current_fastapi_routes`
- `tests/test_next_api_docs_page.py::test_admin_api_docs_page_renders_rich_docs_not_real_data_table`
- `tests/test_next_channel_entry_callback_owner.py::test_callback_routes_are_next_owner_not_legacy_facade`
- `tests/test_router_registry_contract.py::test_router_registry_preserves_route_inventory_count_and_static_order`
- `tests/test_sidebar_profile_next_owner_readiness.py::test_sidebar_profile_readiness_checker_passes_current_repo`
- `tests/test_sidebar_profile_next_owner_readiness.py::test_route_probes_have_explicit_owner_and_no_fixture_markers`
- `tests/test_support_admin_pages_native.py::test_runtime_config_page_renders_from_native_admin_config`
- `tests/test_support_admin_pages_native.py::test_api_docs_page_renders_from_native_admin_config`
- `tests/test_user_ops_admin_pages_native.py::test_user_ops_admin_page_routes_are_owned_by_native_module`
- `tests/test_wecom_callback_ingress_runtime.py::test_wecom_callback_ingress_runtime_only_exposes_callback_and_health_routes`

### Contract drift

- `tests/test_ai_audience_runtime_hotfixes.py::test_huangxiaocan_member_usage_migration_casts_text_timestamps_before_coalesce`
- `tests/test_internal_events_single_consumer_run.py::test_webhook_single_consumer_reuses_shadow_external_effect_without_external_attempt`
- `tests/test_internal_events_single_consumer_run.py::test_repeated_webhook_single_consumer_does_not_duplicate_external_effect_job`

### Payment drift

- `tests/test_public_product_frontend_contract.py::test_public_h5_create_order_returns_existing_paid_order`
- `tests/test_public_product_frontend_contract.py::test_public_h5_paid_order_lookup_accepts_product_code_alias`
- `tests/test_public_product_frontend_contract.py::test_public_h5_paid_order_lookup_prefers_payment_identity_over_sidebar_external_userid`

### Customer projection drift

- `tests/test_customer_live_source_repository.py::test_live_source_repository_reads_existing_customer_source_tables`
- `tests/test_external_orders_customer_projection.py::test_channel_contact_linkage_can_feed_customer_read_model_projection`

## Verification

- Baseline: `scripts/run_tests.sh` on `origin/main` at
  `d30ecc560fd014c938ae24d2d6c8641d2b189d89` produced `28 failed, 2398 passed,
  88 skipped`.
- Focused fixed-failure suite: `93 passed`.
- Full suite after fixes: `2426 passed, 88 skipped, 55 warnings`.
- Architecture boundary: passed.
- Python lint: passed.
- Python typecheck: passed after installing `requirements-dev.txt` into the
  isolated worktree venv.
