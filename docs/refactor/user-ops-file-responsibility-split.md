# User Ops File Responsibility Split

## 说明

- 目标文件：`wecom_ability_service/domains/user_ops/service.py`
- 目标不是一次删空 `service.py`，而是逐步把实现迁到更小的内部模块，再由 `service.py` 保留 facade wrapper。
- “后续可见性”定义：
  - `facade wrapper`：函数名继续保留在 `service.py`
  - `module-private`：迁到目标子模块后只做内部 helper，不再给 caller 层显式访问
  - `internal primitive`：仍可能保留临时 wrapper，但只允许 application command 或兼容测试使用
  - `bridge wrapper`：短期仍保留跨 context 桥接，稳定后应迁出 user_ops
  - `page_service facade`：保留在 `service.py`，内部仅转调 `domains/user_ops/page_service.py`

## `user_ops_pool`

| 行号 / 函数 | 未来归位 | 后续可见性 | 说明 |
| --- | --- | --- | --- |
| `37` `_db_bool` | `user_ops_pool` | `module-private` | 仅供 legacy pool / current row 写入辅助 |
| `45` `_normalize_legacy_user_ops_current_status` | `user_ops_pool` | `module-private` | legacy current_status 向 lead-pool 语义归一 |
| `54` `_legacy_user_ops_status_rank` | `user_ops_pool` | `module-private` | legacy 状态排序规则 |
| `58` `_user_ops_merge_key` | `user_ops_pool` | `module-private` | reload 合并键 |
| `344` `_list_user_ops_crm_source_rows` | `user_ops_pool` | `module-private` | legacy reload 数据源读取 |
| `394` `_list_user_ops_experience_lead_rows` | `user_ops_pool` | `module-private` | legacy reload 体验课数据源读取 |
| `436` `_materialize_user_ops_crm_candidate` | `user_ops_pool` | `module-private` | reload 候选投影 |
| `477` `_materialize_user_ops_experience_candidate` | `user_ops_pool` | `module-private` | reload 候选投影 |
| `518` `_materialize_user_ops_candidate` | `user_ops_pool` | `module-private` | 统一投影入口 |
| `524` `_merge_user_ops_candidate` | `user_ops_pool` | `module-private` | reload 候选 merge |
| `540` `_list_user_ops_activation_source_rows` | `user_ops_pool` | `module-private` | activation source 读 |
| `559` `_apply_user_ops_activation_sources` | `user_ops_pool` | `module-private` | activation source 覆盖到候选集 |
| `594` `_overlay_user_ops_previous_projection` | `user_ops_pool` | `module-private` | reload 时保留旧投影字段 |
| `615` `_serialize_user_ops_current_row` | `user_ops_pool` | `module-private` | current row 序列化 |
| `632` `_load_existing_user_ops_pool_map` | `user_ops_pool` | `module-private` | reload 对比旧池子 |
| `663` `reload_user_ops_pool` | `user_ops_pool` | `facade wrapper` | 已属 deprecated internal-only，继续保留兼容 |
| `2462` `_user_ops_owner_options` | `user_ops_pool` | `module-private` | overview/list 辅助字段 |
| `2484` `list_user_ops_pool` | `service.py -> page_service` | `page_service facade` | 不再在新模块里复制 read 逻辑 |
| `2598` `get_user_ops_overview` | `service.py -> page_service` | `page_service facade` | admin read owner 应继续偏向 `page_service.py` |
| `2653` `list_user_ops_history` | `user_ops_pool` | `facade wrapper` | application query 当前仍经该函数读取 history |
| `2696` `export_user_ops_pool` | `service.py -> page_service` | `page_service facade` | 继续只做兼容转调 |
| `2766` `_normalize_user_ops_lead_pool_activation_state` | `user_ops_pool` | `module-private` | activation 状态统一 |
| `2777` `_serialize_user_ops_lead_pool_current_row` | `user_ops_pool` | `module-private` | lead-pool current row 序列化 |
| `2796` `_get_user_ops_lead_pool_current_row_by_id` | `user_ops_pool` | `module-private` | row 读取 helper |
| `2829` `_list_user_ops_lead_pool_matches` | `user_ops_pool` | `module-private` | 以 mobile/external_userid 做匹配 |
| `2873` `write_user_ops_lead_pool_history` | `user_ops_pool` | `internal primitive` | 对外只保留临时 shim，不允许 caller 新增依赖 |
| `2904` `_insert_user_ops_lead_pool_member_row` | `user_ops_pool` | `module-private` | current row insert primitive |
| `2943` `_update_user_ops_lead_pool_member_row` | `user_ops_pool` | `module-private` | current row update primitive |
| `2979` `_delete_user_ops_lead_pool_duplicate_rows` | `user_ops_pool` | `module-private` | duplicate cleanup |
| `2989` `_user_ops_lead_pool_history_remark` | `user_ops_pool` | `module-private` | history remark 拼装 |
| `2998` `upsert_user_ops_lead_pool_member` | `user_ops_pool` | `internal primitive` | Wave 2 已收口 owner，但 shim 还需保留 |
| `3063` `apply_user_ops_huangxiaocan_activation_source_to_existing_member` | `user_ops_pool` | `module-private` | activation patch 只应由 pool/import 调用 |
| `3111` `upsert_user_ops_huangxiaocan_activation_source` | `user_ops_pool` | `facade wrapper` | 兼容入口保留，真实实现迁到 pool |

## `user_ops_class_term`

| 行号 / 函数 | 未来归位 | 后续可见性 | 说明 |
| --- | --- | --- | --- |
| `72` `_normalize_user_ops_strategy_tag_groups` | `user_ops_class_term` | `module-private` | corp tag payload 预处理 |
| `110` `_ensure_class_term_tag_mapping_seed` | `user_ops_class_term` | `module-private` | seed 写入底层 helper |
| `189` `ensure_class_term_tag_mapping_seed` | `user_ops_class_term` | `facade wrapper` | `domains/user_ops/__init__.py` 已导出 |
| `193` `sync_user_ops_class_term_tag_definitions` | `user_ops_class_term` | `facade wrapper` | 测试和维护入口仍需要 |
| `788` `_user_ops_class_term_options` | `user_ops_class_term` | `module-private` | 班期选项辅助 |
| `808` `_list_active_class_term_mappings` | `user_ops_class_term` | `module-private` | 当前启用 mapping 读取 |
| `834` `_get_active_class_term_mapping_by_no` | `user_ops_class_term` | `module-private` | 单个 mapping 读取 |
| `844` `_confirmed_class_term_mappings_by_no` | `user_ops_class_term` | `module-private` | 确认态 mapping 读 |
| `859` `_infer_user_ops_class_term_no_from_tag_name` | `user_ops_class_term` | `module-private` | 从 tag 名反推班期 |
| `874` `_list_live_user_ops_class_term_tags` | `user_ops_class_term` | `module-private` | 线上标签候选筛选 |
| `902` `_resolve_owner_backfill_class_term_mappings` | `user_ops_class_term` | `module-private` | owner backfill 主规划逻辑 |
| `999` `_list_owner_backfill_candidate_external_userids` | `user_ops_class_term` | `module-private` | owner backfill 候选扫描 |
| `1038` `_get_owner_scoped_live_contact_tags` | `user_ops_class_term` | `module-private` | owner 范围内 live tags 读取 |
| `1089` `_persist_owner_scoped_live_contact_tags` | `user_ops_class_term` | `module-private` | owner 范围内 live tags 落地 |
| `1111` `_plan_user_ops_lead_pool_member_upsert` | `user_ops_class_term` | `module-private` | backfill -> pool upsert 规划 |
| `1207` `_default_owner_class_term_backfill_entry_source` | `user_ops_class_term` | `facade wrapper` | 仍有兼容 helper 依赖 |
| `1216` `_is_owner_backfill_invalid_test_candidate` | `user_ops_class_term` | `module-private` | 测试例外保护 |
| `1221` `backfill_owner_class_terms_into_lead_pool` | `user_ops_class_term` | `facade wrapper` | 当前正式 command owner 的 legacy delegate |
| `1827` `_build_user_ops_backfill_preview` | `user_ops_class_term` | `module-private` | preview 列表构建 |
| `1937` `_build_backfill_class_term_summary` | `user_ops_class_term` | `module-private` | preview/apply 汇总 |
| `1961` `_log_backfill_class_term_conflict` | `user_ops_class_term` | `module-private` | 冲突审计 |
| `1995` `_apply_backfill_class_term_update` | `user_ops_class_term` | `module-private` | apply 写 current/history |
| `2050` `backfill_class_term_for_owner` | `user_ops_class_term` | `facade wrapper` | 兼容入口，后续仍应保留一段时间 |
| `2272` `_list_class_term_matches_for_external_contact` | `user_ops_class_term` | `module-private` | deferred job 依赖的 class-term 匹配逻辑 |
| `2737` `migrate_class_user_status_from_contact_tags` | `user_ops_class_term` | `bridge wrapper` | 临时 bridge，稳定后迁出到 class_user 侧 |
| `2743` `apply_class_user_status_change` | `user_ops_class_term` | `bridge wrapper` | 不应长期留在 user_ops |

## `user_ops_tag_refresh`

| 行号 / 函数 | 未来归位 | 后续可见性 | 说明 |
| --- | --- | --- | --- |
| `1555` `_list_user_ops_pool_external_userids_for_owner` | `user_ops_tag_refresh` | `module-private` | owner sweep 的 external_userid 枚举 |
| `1569` `refresh_contact_tags_for_external_userid` | `user_ops_tag_refresh` | `facade wrapper` | identity / customer_center 仍有兼容依赖 |
| `1654` `refresh_user_ops_contact_tags_for_external_userid` | `user_ops_tag_refresh` | `facade wrapper` | owner 入口下钻到 external_userid refresh |
| `1675` `refresh_user_ops_contact_tags_for_owner` | `user_ops_tag_refresh` | `facade wrapper` | owner sweep 兼容入口 |
| `1699` `_list_other_ownerids_with_scoped_tag_snapshots` | `user_ops_tag_refresh` | `module-private` | cross-owner snapshot cleanup |

## `user_ops_deferred_job`

| 行号 / 函数 | 未来归位 | 后续可见性 | 说明 |
| --- | --- | --- | --- |
| `41` `get_user_ops_deferred_job_counts` | `user_ops_deferred_job` | `facade wrapper` | `http/ops_runtime.py` / `domains/admin_dashboard/repo.py` 仍在读 |
| `2099` `schedule_user_ops_auto_assign_class_term_job` | `user_ops_deferred_job` | `facade wrapper` | application command 当前 owner |
| `2156` `_list_due_user_ops_deferred_jobs` | `user_ops_deferred_job` | `module-private` | due job 扫描 |
| `2178` `_get_user_ops_deferred_job` | `user_ops_deferred_job` | `module-private` | 单 job 读取 |
| `2193` `_mark_user_ops_deferred_job_running` | `user_ops_deferred_job` | `module-private` | 状态切换 |
| `2211` `_finish_user_ops_deferred_job` | `user_ops_deferred_job` | `module-private` | 完成态写回 |
| `2229` `_insert_user_ops_history_record` | `user_ops_deferred_job` | `module-private` | job 侧 history 写辅助 |
| `2262` `_find_user_ops_backfill_preview_item` | `user_ops_deferred_job` | `module-private` | 将 due job 与 preview 结果对齐 |
| `2330` `_upsert_lead_pool_from_verified_class_term_tag` | `user_ops_deferred_job` | `module-private` | due job 成功路径写 pool + refresh |
| `2397` `_execute_auto_assign_class_term_job` | `user_ops_deferred_job` | `module-private` | 单 job 主执行逻辑 |
| `2409` `run_due_user_ops_deferred_jobs` | `user_ops_deferred_job` | `facade wrapper` | admin jobs / background 已经切到 application owner |

## `user_ops_import`

| 行号 / 函数 | 未来归位 | 后续可见性 | 说明 |
| --- | --- | --- | --- |
| `3190` `_current_user_ops_operator` | `user_ops_import` | `module-private` | 导入默认 operator |
| `3199` `_is_experience_lead_header` | `user_ops_import` | `module-private` | experience 表头识别 |
| `3204` `_is_activation_status_header` | `user_ops_import` | `module-private` | activation 表头识别 |
| `3214` `_collect_experience_lead_mobiles` | `user_ops_import` | `module-private` | experience 手机号收集 |
| `3243` `_parse_experience_leads_from_text` | `user_ops_import` | `module-private` | pasted text 解析 |
| `3250` `_extract_xlsx_shared_strings` | `user_ops_import` | `module-private` | xlsx 解析 |
| `3261` `_parse_xlsx_rows` | `user_ops_import` | `module-private` | xlsx 解析 |
| `3291` `_parse_experience_leads_from_file` | `user_ops_import` | `module-private` | 文件入口解析 |
| `3307` `_is_class_term_header` | `user_ops_import` | `module-private` | class-term 表头识别 |
| `3317` `_normalize_class_term_value` | `user_ops_import` | `module-private` | class-term 值归一 |
| `3324` `_extract_class_term_no` | `user_ops_import` | `module-private` | 导入值提取班期号 |
| `3331` `_parse_class_term_import_line` | `user_ops_import` | `module-private` | 单行解析 |
| `3343` `_parse_class_term_source_from_text` | `user_ops_import` | `module-private` | pasted text 解析 |
| `3372` `_parse_class_term_source_from_file` | `user_ops_import` | `module-private` | 文件解析 |
| `3394` `_normalize_activation_status_value` | `user_ops_import` | `module-private` | activation 文本归一 |
| `3407` `_normalize_legacy_user_ops_activation_for_lead_pool` | `user_ops_import` | `module-private` | 兼容老 activation 语义 |
| `3416` `_resolve_lead_pool_binding_by_mobile` | `user_ops_import` | `module-private` | 导入时查绑定 |
| `3451` `_get_user_ops_pool_current_member_by_identity` | `user_ops_import` | `module-private` | 导入更新前读 current |
| `3505` `_upsert_user_ops_pool_current_import_member` | `user_ops_import` | `module-private` | 导入写 current/history |
| `3590` `_apply_activation_status_to_user_ops_pool_current_member` | `user_ops_import` | `module-private` | activation 写 current |
| `3615` `_parse_activation_status_line` | `user_ops_import` | `module-private` | 单行解析 |
| `3629` `_parse_activation_status_from_text` | `user_ops_import` | `module-private` | pasted text 解析 |
| `3658` `_parse_activation_status_from_file` | `user_ops_import` | `module-private` | 文件解析 |
| `3680` `_create_user_ops_import_batch` | `user_ops_import` | `module-private` | import batch 记录写入 |
| `3711` `import_experience_leads` | `user_ops_import` | `facade wrapper` | 正式 command owner 已建立，但真实逻辑还在此处 |
| `3822` `_dedupe_user_ops_import_rows_by_mobile` | `user_ops_import` | `module-private` | mobile 去重 |
| `3831` `import_mobile_class_term_source` | `user_ops_import` | `facade wrapper` | admin / service shim 当前都依赖 |
| `3930` `import_activation_status_source` | `user_ops_import` | `facade wrapper` | admin / service shim 当前都依赖 |
| `4011` `migrate_legacy_user_ops_pool_to_lead_pool` | `user_ops_import` | `facade wrapper` | 兼容迁移入口，不作为新 caller 默认入口 |

## `user_ops_sidebar`

| 行号 / 函数 | 未来归位 | 后续可见性 | 说明 |
| --- | --- | --- | --- |
| `66` `_user_ops_contact_client` | `user_ops_sidebar` | `bridge wrapper` | 真正稳定 patch 点已在 `infra/user_ops_runtime.py` |
| `1726` `_sync_sidebar_lead_pool_class_term_tag` | `user_ops_sidebar` | `module-private` | sidebar class-term patch 专用 tag 同步 |
| `4058` `_extract_third_party_user_id` | `user_ops_sidebar` | `module-private` | 第三方用户 ID 提取 |
| `4076` `_resolve_third_party_user_id_by_mobile` | `user_ops_sidebar` | `bridge wrapper` | 需继续保留给 `infra/user_ops_runtime.py` / identity legacy delegate |
| `4115` `_sidebar_contact_profile` | `user_ops_sidebar` | `bridge wrapper` | identity bind 流程当前仍直接依赖 |
| `4185` `_resolve_binding_owner_userid` | `user_ops_sidebar` | `bridge wrapper` | identity bind 流程当前仍直接依赖 |
| `4203` `_select_user_ops_lead_pool_member_for_sidebar` | `user_ops_sidebar` | `module-private` | sidebar 当前成员选择 |
| `4226` `get_sidebar_lead_pool_status` | `user_ops_sidebar` | `facade wrapper` | sidebar query 正式 owner 已切到 application |
| `4268` `upsert_sidebar_lead_pool_class_term` | `user_ops_sidebar` | `facade wrapper` | sidebar class-term patch 正式 owner 已切到 application |
| `4315` `_merge_lead_pool_after_mobile_bind` | `user_ops_sidebar` | `bridge wrapper` | identity bind mobile 成功后仍需调用 |

## 特别说明

- `write_user_ops_lead_pool_history` 和 `upsert_user_ops_lead_pool_member`
  - 两者都必须保留兼容 shim
  - 但拆分后应明确放到 `user_ops_pool`，并在文档与注释里继续标记为 internal primitive
- `migrate_class_user_status_from_contact_tags` 和 `apply_class_user_status_change`
  - 这两个函数不是 user_ops 长期 owner
  - 内部拆分时只允许临时放到 `user_ops_class_term` 或 bridge 文件
  - 后续应再从 user_ops 迁出
