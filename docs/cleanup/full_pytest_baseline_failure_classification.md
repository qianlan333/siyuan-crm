# Full Pytest Baseline Failure Classification

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
