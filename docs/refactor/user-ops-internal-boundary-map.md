# User Ops Internal Boundary Map

## 目标与范围

- 正式调用 owner 已经收敛到 `wecom_ability_service/application/user_ops/*`。
- 本文只处理 `wecom_ability_service/domains/user_ops/service.py` 的内部实现拆分准备，不改 caller，不改 schema，不改 SQL。
- 目标不是立刻大拆，而是先把单文件里的职责边界画清，后续按小 PR 做“提取实现 + 保留 facade wrapper”。
- `wecom_ability_service/domains/user_ops/page_service.py` 的 admin read-model / batch-send 逻辑不在本轮内部拆分范围内。

## 当前文件现状

- 当前主文件：`wecom_ability_service/domains/user_ops/service.py`
- 当前规模：约 `4403` 行
- 当前问题：
  - 同时承载 lead-pool current/history、导入、sidebar patch、deferred jobs、owner backfill、tag refresh、class_user bridge
  - 既有公开 API，也有内部 primitive，还混着大量跨 context helper
  - `service.py` 内部已经出现“读包装 + 写实现 + maintenance + sync”叠加，继续直接改会放大冲突面

## 拆分原则

- `service.py` 后续只保留 facade / compatibility wrapper，不再继续吸收实现。
- 新实现优先落到 `domains/user_ops/` 下的内部子模块，不动 `application/user_ops/*` 的正式 contract。
- `write_user_ops_lead_pool_history` / `upsert_user_ops_lead_pool_member` 视为 internal primitive。
- `list_user_ops_pool` / `get_user_ops_overview` / `export_user_ops_pool` 的正式读 owner 仍应偏向 `domains/user_ops/page_service.py`；`service.py` 中的同名函数后续只保留兼容 wrapper。

## 目标边界总览

| 目标子模块 | 当前职责 | 直接调用方 | 依赖的外部 context | 类型 | 风险 |
| --- | --- | --- | --- | --- | --- |
| `user_ops_pool` | lead-pool current/history 持久化、去重、激活状态 patch、legacy pool reload、history 写入、current row 序列化 | `application/user_ops/commands.py` 中的 `UpsertLeadPoolMemberCommand`、`WriteLeadPoolHistoryCommand`、`UpsertUserOpsHuangxiaocanActivationSourceCommand`；`application/user_ops/queries.py` 中的 history 读取；`services.py` 兼容 wrapper；导入/sidebar/deferred job 内部实现 | `identity_contact`、`class_user`、数据库 | 读 + 写 + maintenance | 高 |
| `user_ops_import` | experience/mobile class-term/activation 三类导入解析、批次创建、导入行归并、legacy pool 迁移 | `application/user_ops/commands.py` 中的 `ImportExperienceLeadsCommand`、`ImportMobileClassTermCommand`、`ImportActivationStatusCommand`、`MigrateLegacyUserOpsPoolToLeadPoolCommand`；`services.py` 兼容 wrapper | `identity_contact`、`user_ops_pool`、文件解析（xlsx/text）、数据库 | 写 + maintenance + sync | 高 |
| `user_ops_class_term` | 班期标签映射 seed/sync、owner backfill 规划与落库、class-term 匹配、owner scoped live tags 解析、class_user bridge 临时桥接 | `application/user_ops/commands.py` 中的 `BackfillOwnerClassTermsCommand`、`BackfillClassTermForOwnerCommand`；`services.py` 中 `sync_user_ops_class_term_tag_definitions`；deferred job 执行链内部调用 | `tags`、`identity_contact`、`class_user`、`routing_config`、数据库 | 写 + maintenance + sync | 高 |
| `user_ops_sidebar` | sidebar contact profile、绑定 owner 解析、sidebar lead-pool status、class-term patch、mobile bind 后 lead-pool merge、third-party userid 解析 | `application/user_ops/queries.py` 中的 `GetSidebarLeadPoolStatusQuery`；`application/user_ops/commands.py` 中的 `UpsertSidebarLeadPoolClassTermCommand`；`application/identity_contact/_legacy_delegate.py` 的绑定桥接；`services.py` 兼容 wrapper | `identity_contact`、`tags`、WeCom contact runtime | 读 + 写 + sync | 高 |
| `user_ops_deferred_job` | deferred job counts、job schedule/list/run/status 流程、auto-assign class-term 执行、preview item 关联、run summary | `application/user_ops/commands.py` 中的 `ScheduleUserOpsAutoAssignClassTermJobCommand`、`RunDueUserOpsDeferredJobsCommand`；`application/user_ops/queries.py` 中的 `GetUserOpsDeferredJobCountsQuery`；`http/background_jobs.py`、`domains/admin_jobs/service.py`、`http/ops_runtime.py`、`domains/admin_dashboard/repo.py` 经 facade 或 application 进入 | `user_ops_class_term`、`user_ops_pool`、WeCom contact runtime、数据库 | 写 + maintenance + sync + 读计数 | 高 |
| `user_ops_tag_refresh` | full/scoped contact tag refresh、owner sweep、跨 owner snapshot 清理、refresh 对 class_user sync result 的联动 | `application/user_ops/commands.py` 中的 `RefreshContactTagsForExternalUseridCommand`、`RefreshUserOpsContactTagsCommand`；`application/identity_contact/_legacy_delegate.py`；`services.py` 兼容 wrapper；`customer_center/service.py` 刷 tag 场景 | `tags`、`identity_contact`、`class_user`、数据库 | maintenance + sync + 写 | 高 |

## facade-only 例外

这些函数不建议继续沉到新的写模块里，而应保留为 `service.py` facade，内部转调已有 read owner：

| 现有函数 | 后续归位 | 说明 |
| --- | --- | --- |
| `list_user_ops_pool` | `service.py` facade -> `domains/user_ops/page_service.py` | 当前正式 query 已优先走 `page_service.py`；拆分时不再复制一份 read 实现 |
| `get_user_ops_overview` | `service.py` facade -> `domains/user_ops/page_service.py` | 与 admin read model 同步收口 |
| `export_user_ops_pool` | `service.py` facade -> `domains/user_ops/page_service.py` | 保持导出 contract，不在新写模块里继续扩张 |
| `reload_user_ops_pool` | `service.py` facade -> `user_ops_pool` | 仅保留兼容/内部维护能力，不作为新入口 |

## 子模块边界细化

### `user_ops_pool`

- 包含：
  - current/history row upsert、duplicate merge、activation patch、legacy reload projection
  - 对外只暴露内部 primitive 或 facade wrapper，不直接给 caller 层开放数据库细节
- 允许依赖：
  - `identity_contact` 提供 mobile / binding 归一化能力
  - `class_user` 提供 signup status current / history sync result
- 不应继续承载：
  - xlsx / pasted text 导入解析
  - sidebar 绑定 owner 解析
  - deferred job orchestration

### `user_ops_import`

- 包含：
  - xlsx/text 解析
  - import batch 创建
  - 导入行去重、按 mobile 回填到 lead-pool current/history
- 允许依赖：
  - `user_ops_pool`
  - `identity_contact` 读绑定状态
- 不应继续承载：
  - owner backfill
  - sidebar patch
  - deferred job schedule/run

### `user_ops_class_term`

- 包含：
  - class-term tag mapping seed / sync
  - owner backfill preview / apply
  - class-term 匹配与来源推断
- 允许依赖：
  - `tags`
  - `routing_config`
  - `class_user`
  - `identity_contact`
- 额外说明：
  - `migrate_class_user_status_from_contact_tags` / `apply_class_user_status_change` 只是临时 bridge，拆稳后应再迁出到 class_user 侧桥接层

### `user_ops_sidebar`

- 包含：
  - sidebar lead-pool status query
  - sidebar class-term patch write
  - mobile bind 后 lead-pool merge
  - third-party user id adapter hook
- 允许依赖：
  - `identity_contact`
  - `infra/user_ops_runtime.py`
  - `tags`
- 不应继续承载：
  - import pipeline
  - owner backfill 扫描
  - deferred job 列表/状态流转

### `user_ops_deferred_job`

- 包含：
  - deferred job count / enqueue / run / finish
  - auto-assign class-term 执行 orchestration
- 允许依赖：
  - `user_ops_class_term`
  - `user_ops_pool`
  - `user_ops_tag_refresh`
- 不应继续承载：
  - sidebar status
  - 导入解析

### `user_ops_tag_refresh`

- 包含：
  - full/scoped tag refresh
  - owner sweep
  - snapshot 清理
  - refresh 后对 class_user sync result 的落地
- 允许依赖：
  - `tags`
  - `identity_contact`
  - `class_user`
- 不应继续承载：
  - lead-pool upsert primitive
  - import batch 创建

## 当前已知跨 context 耦合

- `application/identity_contact/_legacy_delegate.py`
  - 仍会借用 `user_ops` 的 `_sidebar_contact_profile`、`_resolve_binding_owner_userid`、`_merge_lead_pool_after_mobile_bind`
- `infra/user_ops_runtime.py`
  - 已提供新的稳定 adapter 锚点 `get_user_ops_contact_client` / `resolve_third_party_user_id_by_mobile`
- `http/ops_runtime.py`
  - 仍直接读 `get_user_ops_deferred_job_counts`
- `domains/admin_dashboard/repo.py`
  - 仍直接读 `get_user_ops_deferred_job_counts` 与 `get_user_ops_overview`

这些都不是本轮 caller cutover 的阻塞项，但拆分时必须保留 facade，不允许直接拔掉老符号。

## 拆分落地约束

- 第一轮内部拆分不改 `application/user_ops/*` 的正式 contract。
- 第一轮内部拆分不改 `http/admin_user_ops.py`、`http/background_jobs.py`、`http/sidebar.py` 的 wiring。
- 每提取一个子模块，都要让 `domains/user_ops/service.py` 退化成“import + forward”。
- 只有当 facade wrapper 仍完整保留时，才允许移动实现文件。
