# User Ops Split Closeout

日期：2026-04-20

## 结论

`wecom_ability_service/domains/user_ops/service.py` 的主写路径内部 owner 已完成第一轮拆分。当前 `application/user_ops/*` 的正式 contract 保持稳定，`service.py` 主要承担 facade / compatibility wrapper / runtime 组装职责，不再继续承载新的主写实现。

## 已完成的内部子模块

### 1. deferred_job

- 当前 owner 文件
  - `wecom_ability_service/domains/user_ops/user_ops_deferred_job_service.py`
- 仍保留在 `domains/user_ops/service.py` 的 facade
  - `get_user_ops_deferred_job_counts`
  - `schedule_user_ops_auto_assign_class_term_job`
  - `run_due_user_ops_deferred_jobs`
  - `_user_ops_deferred_job_runtime`
- 仍依赖的 runtime / shared helper
  - `current_operator_resolver`
  - `stringify_db_timestamp`
  - `build_user_ops_backfill_preview`
  - `list_class_term_matches_for_external_contact`
  - `sync_user_ops_class_term_tag_definitions`
  - `refresh_user_ops_contact_tags_for_external_userid`
  - `resolve_person_identity`
  - `upsert_user_ops_lead_pool_member`
- 已知技术债
  - 仍通过 runtime 串联 `class_term`、`tag_refresh`、`pool_core`，尚未形成更细的 orchestration adapter。
  - console summary / ops runtime 仍通过 facade 读取计数。

### 2. sidebar

- 当前 owner 文件
  - `wecom_ability_service/domains/user_ops/user_ops_sidebar_service.py`
- 仍保留在 `domains/user_ops/service.py` 的 facade
  - `_sidebar_contact_profile`
  - `_resolve_binding_owner_userid`
  - `_select_user_ops_lead_pool_member_for_sidebar`
  - `get_sidebar_lead_pool_status`
  - `upsert_sidebar_lead_pool_class_term`
  - `_merge_lead_pool_after_mobile_bind`
  - `_sync_sidebar_lead_pool_class_term_tag`
  - `_user_ops_sidebar_runtime`
- 仍依赖的 runtime / shared helper
  - `normalize_mobile`
  - `get_contact_binding_status`
  - `list_user_ops_lead_pool_matches`
  - `serialize_user_ops_lead_pool_current_row`
  - `upsert_user_ops_lead_pool_member`
  - `write_user_ops_lead_pool_history`
  - `list_other_ownerids_with_scoped_tag_snapshots`
  - tag snapshot 存取 helper
  - `class_term_runtime`
- 已知技术债
  - identity legacy bind 流程仍直接依赖 `_sidebar_contact_profile`、`_resolve_binding_owner_userid`、`_merge_lead_pool_after_mobile_bind` 这组 bridge wrapper。
  - third-party user id 解析仍通过 runtime adapter 注入，不是纯 user_ops 内部依赖。

### 3. class_term

- 当前 owner 文件
  - `wecom_ability_service/domains/user_ops/user_ops_class_term_service.py`
- 仍保留在 `domains/user_ops/service.py` 的 facade
  - `ensure_class_term_tag_mapping_seed`
  - `sync_user_ops_class_term_tag_definitions`
  - `_list_class_term_matches_for_external_contact`
  - `_build_user_ops_backfill_preview`
  - `backfill_owner_class_terms_into_lead_pool`
  - `backfill_class_term_for_owner`
  - `_default_owner_class_term_backfill_entry_source`
  - `_user_ops_class_term_runtime`
- 仍依赖的 runtime / shared helper
  - `db_bool`
  - `current_operator_resolver`
  - `contact_client_loader`
  - `list_contact_tag_ids_for_user`
  - tag snapshot helper
  - `get_owner_class_term_backfill_entry_source_override`
  - `resolve_person_identity`
  - `plan_lead_pool_member_upsert`
  - `upsert_user_ops_lead_pool_member`
  - `refresh_user_ops_contact_tags_for_owner`
- 已知技术债
  - 仍保留 class-user bridge 依赖，`service.py` 中的 `migrate_class_user_status_from_contact_tags` / `apply_class_user_status_change` 仍是过渡性桥接。
  - owner backfill 仍跨 `routing_config`、`identity`、`tags`、`pool_core` 多个 context。

### 4. import

- 当前 owner 文件
  - `wecom_ability_service/domains/user_ops/user_ops_import_service.py`
- 仍保留在 `domains/user_ops/service.py` 的 facade
  - `upsert_user_ops_huangxiaocan_activation_source`
  - `import_experience_leads`
  - `import_mobile_class_term_source`
  - `import_activation_status_source`
  - `migrate_legacy_user_ops_pool_to_lead_pool`
  - `_user_ops_import_runtime`
- 仍依赖的 runtime / shared helper
  - `db_bool`
  - `normalize_mobile`
  - `current_operator_resolver`
  - `normalize_lead_pool_activation_state`
  - `apply_activation_source_to_existing_member`
  - `upsert_user_ops_lead_pool_member`
- 已知技术债
  - xlsx/text parse、import batch 写入、legacy projection 兼容逻辑仍集中在一个模块里，后续若要再瘦身应拆 parser 与 executor。
  - 仍保留 `user_ops_pool_current` 兼容投影维护，不属于本轮 closeout 的阻塞项。

### 5. tag_refresh

- 当前 owner 文件
  - `wecom_ability_service/domains/user_ops/user_ops_tag_refresh_service.py`
- 仍保留在 `domains/user_ops/service.py` 的 facade
  - `_list_user_ops_pool_external_userids_for_owner`
  - `refresh_contact_tags_for_external_userid`
  - `refresh_user_ops_contact_tags_for_external_userid`
  - `refresh_user_ops_contact_tags_for_owner`
  - `_list_other_ownerids_with_scoped_tag_snapshots`
  - `_user_ops_tag_refresh_runtime`
- 仍依赖的 runtime / shared helper
  - `contact_client_loader`
  - `list_active_class_term_mappings`
  - `list_contact_tag_ids_for_user`
  - tag snapshot save/remove helper
  - `remove_all_tag_snapshots_for_other_users`
- 已知技术债
  - owner sweep 仍读 `user_ops_lead_pool_current` 作为扫描基准。
  - cross-owner stale snapshot cleanup 仍直接依赖 `contact_tags` 快照表结构。

### 6. pool_core

- 当前 owner 文件
  - `wecom_ability_service/domains/user_ops/user_ops_pool_core_service.py`
- 仍保留在 `domains/user_ops/service.py` 的 facade
  - `_plan_user_ops_lead_pool_member_upsert`
  - `list_user_ops_history`
  - `_normalize_user_ops_lead_pool_activation_state`
  - `_serialize_user_ops_lead_pool_current_row`
  - `_get_user_ops_lead_pool_current_row_by_id`
  - `_list_user_ops_lead_pool_matches`
  - `write_user_ops_lead_pool_history`
  - `upsert_user_ops_lead_pool_member`
  - `apply_user_ops_huangxiaocan_activation_source_to_existing_member`
  - `_user_ops_pool_core_runtime`
- 仍依赖的 runtime / shared helper
  - `db_bool`
  - `normalize_mobile`
  - `stringify_db_timestamp`
  - `current_operator_resolver`
- 已知技术债
  - `reload_user_ops_pool` 及其 legacy projection helper 仍留在 `service.py`，尚未继续下沉到 pool core owner。
  - `application/user_ops/*` 仍保留 primitive-shaped command 以兼容旧调用面，尚未完全隐藏 primitive。

## `domains/user_ops/service.py` 当前定位

- compatibility facade
- legacy import surface
- runtime 组装点
- 少量 read / maintenance / bridge 入口

当前不建议再继续向 `service.py` 塞新的写逻辑。后续如果还有 user_ops 相关改动，默认应优先落到：

- `application/user_ops/*`
- 已拆出的 `domains/user_ops/user_ops_*_service.py`

