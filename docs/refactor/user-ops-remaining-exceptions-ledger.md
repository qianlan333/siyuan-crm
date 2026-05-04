# User Ops Remaining Exceptions Ledger

日期：2026-04-20

## 说明

本台账只记录 `wecom_ability_service/domains/user_ops/service.py` 里仍保留、但在本轮 closeout 不再继续拆的剩余职责。它们大多已经不是主写 owner，而是 read / maintenance / shim facade。

## 剩余职责台账

| 入口 | 本轮不拆原因 | 类型 | 是否阻塞 Wave 2 closeout | 后续归位建议 |
| --- | --- | --- | --- | --- |
| `reload_user_ops_pool` | 这是 legacy projection maintenance helper，当前不再是主流程 owner，继续拆只会把兼容表重构拉进本轮 | maintenance | 否 | 保留 deprecated facade，后续如仍需保留，显式归到 `user_ops_pool_core_service.py` 或单列 legacy maintenance 模块 |
| `list_user_ops_pool` | 当前正式 admin read owner 更接近 `domains/user_ops/page_service.py`，不应在 closeout 阶段再复制 read-model 拆分 | read | 否 | 逐步收成 `service.py -> page_service.py` 的纯 facade，最终由 `application/user_ops/ListLeadPoolQuery` 统一暴露 |
| `get_user_ops_overview` | 同上，属于 admin overview read-model，不属于主写路径 | read | 否 | 收成 `service.py -> page_service.py` facade；后续只保留 application query |
| `export_user_ops_pool` | 导出 contract 已稳定，本轮不改它的 read/export 结构 | read | 否 | 收成 `service.py -> page_service.py` facade 或独立 export read owner |
| `get_user_ops_deferred_job_counts` | 已有内部 owner，但 console / ops runtime 仍经 `service.py` facade 读 | read | 否 | 逐步让外层只走 `application/user_ops/GetUserOpsDeferredJobCountsQuery` |
| `ensure_class_term_tag_mapping_seed` | 初始化/测试 hook 仍有兼容价值，本轮不需要再拆 facade | maintenance | 否 | 保留 facade；长期看只留给 maintenance job 或 test fixture 使用 |
| `sync_user_ops_class_term_tag_definitions` | maintenance 入口已稳定，继续拆 facade 收益低 | maintenance | 否 | 外层统一走 application maintenance command；`service.py` 仅保留兼容壳 |
| `backfill_owner_class_terms_into_lead_pool` | 已有 class-term owner，当前剩余只是兼容 facade | maintenance | 否 | 长期仅保留 application command；`service.py` wrapper 可继续缩薄 |
| `backfill_class_term_for_owner` | 同上，是 owner 维度兼容入口，不应在 closeout 阶段继续重排 | maintenance | 否 | 长期只保留 application command |
| `refresh_contact_tags_for_external_userid` | 已有 tag_refresh owner，但 customer / admin 兼容面仍可能通过 facade 进入 | maintenance | 否 | 长期统一由 `RefreshContactTagsForExternalUseridCommand` 承接 |
| `refresh_user_ops_contact_tags_for_external_userid` | 同上，当前只是兼容 facade | maintenance | 否 | 长期统一由 `RefreshUserOpsContactTagsCommand` 承接 |
| `refresh_user_ops_contact_tags_for_owner` | owner-sweep 仍通过 facade 保持兼容 | maintenance | 否 | 长期统一由 `RefreshUserOpsContactTagsCommand` 承接 |
| `schedule_user_ops_auto_assign_class_term_job` | 已有 deferred-job owner，当前 facade 只负责兼容层延续 | maintenance / shim | 否 | 长期只保留 application command |
| `run_due_user_ops_deferred_jobs` | 已有 deferred-job owner，当前 facade 只负责兼容层延续 | maintenance / shim | 否 | 长期只保留 application command |
| `list_user_ops_history` | history read owner 已在 pool core，但仍需兼容 old import surface | read / shim | 否 | 长期只保留 `application/user_ops/ListUserOpsHistoryQuery` |
| `get_sidebar_lead_pool_status` | sidebar query 已有内部 owner，当前 facade 主要是兼容桥接 | read / shim | 否 | 长期只保留 `GetSidebarLeadPoolStatusQuery` |
| `upsert_sidebar_lead_pool_class_term` | sidebar write owner 已明确，当前 facade 只是兼容桥接 | shim | 否 | 长期只保留 `UpsertSidebarLeadPoolClassTermCommand` |
| `upsert_user_ops_huangxiaocan_activation_source` | import owner 已明确，但历史兼容入口仍在 | shim | 否 | 长期只保留 application command 或 import module 内部调用 |
| `import_experience_leads` | import pipeline 已拆出，当前 facade 仅保留兼容 surface | shim | 否 | 长期只保留 `ImportExperienceLeadsCommand` |
| `import_mobile_class_term_source` | 同上 | shim | 否 | 长期只保留 `ImportMobileClassTermCommand` |
| `import_activation_status_source` | 同上 | shim | 否 | 长期只保留 `ImportActivationStatusCommand` |
| `migrate_legacy_user_ops_pool_to_lead_pool` | 兼容迁移入口仍保留，但不是日常主流程 | maintenance / shim | 否 | 后续按是否仍需历史迁移决定保留或归档 |
| `_sidebar_contact_profile` / `_resolve_binding_owner_userid` / `_merge_lead_pool_after_mobile_bind` | 这组 bridge 仍被 identity legacy delegate 使用，当前不能直接拔掉 | compatibility bridge | 否 | 等 identity legacy bridge 全部撤除后，再把这些 facade 收回 `user_ops_sidebar_service.py` 内部 |

## closeout 判断

- 上述剩余项都不再是 `user_ops` 主写 owner。
- 它们主要属于 read / maintenance / shim / bridge。
- 它们不会阻塞 Wave 2 closeout，但会影响后续若要继续缩 `service.py` 的工作量。

