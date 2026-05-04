# User Ops Test Freeze Plan

## 目标

- 在真正拆 `domains/user_ops/service.py` 之前，先冻结 user_ops 的高风险行为。
- 拆分期间优先依赖现有测试；只有现有覆盖明显不足时，才补最小冻结测试，不顺手扩功能。

## 高风险行为与冻结口径

| 行为 | 当前覆盖现状 | 建议主测试文件 | 备注 |
| --- | --- | --- | --- |
| lead pool current/history 一致性 | 已有 direct helper 测试覆盖 insert、mobile-only、external-only、history 写入、activation patch | `tests/test_user_ops_lead_pool_helpers.py` | 这是 pool primitive 拆分的第一道红线 |
| deferred jobs 调度与执行 | 已有 schedule、single match、conflict、no match、console count/run 覆盖 | `tests/test_user_ops_api.py`、`tests/test_admin_jobs_console.py`、`tests/test_api.py` | 需要同时冻结 DB 状态与 console payload |
| sidebar class-term patch | 已覆盖创建 external-only member、status 查询、explicit owner、cross-owner stale snapshot cleanup | `tests/test_user_ops_api.py` | 这块会同时碰 sidebar、tag snapshot、lead-pool history |
| owner 班期回填 | 已覆盖 candidate 枚举、class-term range、conflict、dry-run、apply current/history、owner pinning | `tests/test_user_ops_api.py` | class-term / tag-refresh PR 前必须保持全绿 |
| `import_experience_leads` / `import_mobile_class_term_source` / `import_activation_status_source` | mobile/activation 覆盖较强；experience 目前只有 deprecated endpoint 断言，真实 import 路径覆盖偏弱 | `tests/test_user_ops_api.py`，建议新增 `tests/test_user_ops_import_pipeline.py` | `import_experience_leads` 是当前明显 gap |
| contact tag refresh 对 user_ops 视图的影响 | 已覆盖 full/scoped refresh；owner-level sweep 和 refresh 后视图一致性覆盖偏弱 | `tests/test_user_ops_api.py`，建议新增 `tests/test_user_ops_tag_refresh.py` | 真拆 `tag_refresh` 前应补 owner-sweep 最小回归 |

## 现有可直接依赖的测试面

### lead pool primitive

- `tests/test_user_ops_lead_pool_helpers.py`
  - `test_user_ops_lead_pool_current_allows_mobile_only_member`
  - `test_user_ops_lead_pool_current_allows_external_only_member`
  - `test_user_ops_lead_pool_upsert_writes_history`
  - `test_huangxiaocan_activation_source_patches_existing_member_only`

### sidebar / import / deferred / backfill / refresh

- `tests/test_user_ops_api.py`
  - refresh：
    - `test_refresh_contact_tags_for_external_userid_writes_all_tags_when_scope_is_none`
    - `test_refresh_contact_tags_for_external_userid_only_refreshes_scoped_tags`
  - sidebar：
    - `test_sidebar_lead_pool_upsert_class_term_creates_external_only_member`
    - `test_sidebar_lead_pool_status_returns_current_member`
    - `test_sidebar_lead_pool_status_does_not_fallback_to_other_owner_member`
    - `test_sidebar_lead_pool_upsert_class_term_replaces_old_tag_and_returns_success`
    - `test_sidebar_lead_pool_upsert_class_term_respects_explicit_owner_context`
    - `test_sidebar_lead_pool_upsert_class_term_cleans_cross_owner_stale_tag_snapshots`
  - imports：
    - `test_import_mobile_class_terms_from_pasted_text_updates_pool`
    - `test_import_mobile_class_terms_matching_binding_marks_wecom_bound`
    - `test_import_mobile_class_terms_keeps_latest_row_for_same_mobile`
    - `test_import_mobile_class_terms_does_not_trigger_legacy_reload`
    - `test_import_activation_status_from_pasted_text_updates_pool`
    - `test_import_activation_status_from_excel_updates_pool`
    - `test_import_activation_status_accepts_not_activated_label`
    - `test_import_activation_status_accepts_legacy_activated_label`
    - `test_import_activation_status_rejects_invalid_value`
    - `test_import_activation_status_source_keeps_latest_row`
    - `test_activation_status_survives_lead_pool_reads`
  - deferred jobs：
    - `test_schedule_user_ops_auto_assign_class_term_job`
    - `test_due_deferred_job_writes_class_term_for_single_match`
    - `test_due_deferred_job_conflict_is_skipped`
    - `test_due_deferred_job_without_match_is_skipped`
  - owner backfill：
    - `test_owner_backfill_candidate_enumeration_uses_active_follow_and_contact_fallback`
    - `test_owner_backfill_only_matches_class_terms_in_requested_range`
    - `test_owner_backfill_conflict_candidate_is_not_written`
    - `test_owner_backfill_apply_uses_mobile_bound_merge`
    - `test_owner_backfill_apply_allows_external_only_member`
    - `test_owner_backfill_reports_missing_term_two_mapping_when_real_tag_absent`
    - `test_owner_backfill_discovers_term_two_from_live_tags`
    - `test_owner_backfill_dry_run_does_not_write_tables`
    - `test_owner_backfill_apply_writes_current_and_history`
    - `test_owner_backfill_invalid_test_candidate_is_skipped_without_error`
    - `test_owner_backfill_apply_pins_target_owner_and_audits_owner_mismatch`
    - `test_backfill_class_term_for_owner_dry_run_routes_through_application_owner`

### caller / console / runtime 集成面

- `tests/test_admin_jobs_console.py`
  - deferred jobs console summary 与 run 行为
- `tests/test_api.py -k "user_ops or sidebar or ops_status or admin_user_ops"`
  - user_ops / sidebar / ops runtime 综合 contract
- `tests/test_user_ops_application_contract.py`
  - application owner 与 services shim delegation 不回退
- `tests/test_service_layer_layout.py`
  - caller 必须继续走 `application.user_ops`
- `tests/test_refactor_guardrails.py`
  - background / sidebar / admin jobs 不能回流到 `services.py` 或 `domains.user_ops.service`

## 建议补齐的冻结缺口

### 缺口 1：`import_experience_leads`

- 现状
  - 当前只有 `test_import_experience_leads_endpoint_is_deprecated_internal_only`
  - 真正的导入逻辑没有一条稳定的 happy-path regression
- 建议
  - 在开始 `user_ops_import` 拆分前，新增一个命令级或 legacy delegate 级测试
  - 推荐文件：`tests/test_user_ops_import_pipeline.py`
- 最小断言
  - pasted text 能被解析
  - 导入后会写 lead-pool current/history
  - 相同 mobile 的重复行不会写出重复 current member

### 缺口 2：`refresh_user_ops_contact_tags_for_owner`

- 现状
  - full/scoped external_userid refresh 已有覆盖
  - owner sweep 级别缺少独立冻结
- 建议
  - 在真正拆 `user_ops_tag_refresh` 前，补一条 owner 级 sweep regression
  - 推荐文件：`tests/test_user_ops_tag_refresh.py`
- 最小断言
  - owner 下多个 external_userid 都会被扫描
  - 只清理 cross-owner stale snapshots，不误删当前 owner snapshot
  - refresh 后 user_ops 列表/状态视图保持一致

## PR 期间最小回归集

### Pool / Primitive PR

```bash
PYTHONPATH=. ./.venv311/bin/pytest tests/test_user_ops_lead_pool_helpers.py -q
PYTHONPATH=. ./.venv311/bin/pytest tests/test_user_ops_api.py -k "lead_pool or activation_status_source or migrate_legacy_user_ops_pool_to_lead_pool" -q
PYTHONPATH=. ./.venv311/bin/pytest tests/test_user_ops_application_contract.py tests/test_service_layer_layout.py tests/test_refactor_guardrails.py -q
```

### Deferred Jobs / Sidebar PR

```bash
PYTHONPATH=. ./.venv311/bin/pytest tests/test_admin_jobs_console.py -q
PYTHONPATH=. ./.venv311/bin/pytest tests/test_user_ops_api.py -k "sidebar_lead_pool or due_deferred_job or schedule_user_ops_auto_assign_class_term_job" -q
PYTHONPATH=. ./.venv311/bin/pytest tests/test_api.py -k "user_ops or sidebar or ops_status or admin_user_ops" -q
PYTHONPATH=. ./.venv311/bin/pytest tests/test_service_layer_layout.py tests/test_refactor_guardrails.py -q
```

### Class-Term / Tag Refresh PR

```bash
PYTHONPATH=. ./.venv311/bin/pytest tests/test_user_ops_api.py -k "refresh_contact_tags_for_external_userid or owner_backfill or backfill_class_term_for_owner or sync_user_ops_class_term_tag_definitions" -q
PYTHONPATH=. ./.venv311/bin/pytest tests/test_identity_application_contract.py tests/test_http_registration_contract.py -q
PYTHONPATH=. ./.venv311/bin/pytest tests/test_service_layer_layout.py tests/test_refactor_guardrails.py -q
```

### Import PR

```bash
PYTHONPATH=. ./.venv311/bin/pytest tests/test_user_ops_api.py -k "import_mobile_class_terms or import_activation_status or activation_status_survives_lead_pool_reads" -q
PYTHONPATH=. ./.venv311/bin/pytest tests/test_user_ops_lead_pool_helpers.py -q
PYTHONPATH=. ./.venv311/bin/pytest tests/test_user_ops_application_contract.py tests/test_service_layer_layout.py tests/test_refactor_guardrails.py -q
```

## 仓库级最小总回归

在任何一个 user_ops 内部拆分 PR 合并前，建议至少补跑一次：

```bash
PYTHONPATH=. ./.venv311/bin/pytest \
  tests/test_user_ops_lead_pool_helpers.py \
  tests/test_user_ops_api.py \
  tests/test_admin_jobs_console.py \
  tests/test_user_ops_application_contract.py \
  tests/test_http_registration_contract.py \
  tests/test_service_layer_layout.py \
  tests/test_refactor_guardrails.py \
  -q
```

如果 PR 动到了 runtime / console 读面，再加：

```bash
PYTHONPATH=. ./.venv311/bin/pytest tests/test_api.py -k "user_ops or sidebar or ops_status or admin_user_ops" -q
```
