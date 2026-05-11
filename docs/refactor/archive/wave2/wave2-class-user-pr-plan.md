# Wave 2 Class User PR Plan

日期：2026-04-20

## 1. 目标

Wave 2 当前只做 `class_user` 主线，且必须严格串行推进。

本计划把 class_user 收口拆成 4 个 PR：

- PR 2：Class User Application Skeleton
- PR 3：Class User Admin Read Cutover
- PR 4：Class User Write Caller Cutover A
- PR 5：Class User Write Caller Cutover B

不把 `user_ops` / `routing_config` 的内部模块重构混进来。

## 2. 切分原则

切分原则固定为：

1. 先建正式 application contract 与 contract tests。
2. 先切 admin read shell 和低风险读路径。
3. 再切 `admin_support` / `marketing_automation` 这种有副作用但边界仍清楚的写 caller。
4. 最后清 `user_ops` 里 class_user 的重复实现。
5. 每个 PR 都必须可回滚，且不依赖后续 PR 才能保持现网行为。

## 3. PR 2：Class User Application Skeleton

### 3.1 目标

只建立 `application/class_user/*` 的最小可导入骨架，把 class_user 的读写 contract 正式命名出来，并让 `services.py` 上的兼容符号先指向正式 application owner。

### 3.2 范围

建议改动：

- `wecom_ability_service/application/class_user/__init__.py`
- `wecom_ability_service/application/class_user/dto.py`
- `wecom_ability_service/application/class_user/queries.py`
- `wecom_ability_service/application/class_user/commands.py`
- `wecom_ability_service/application/class_user/_legacy_delegate.py`
- `wecom_ability_service/services.py`
- `tests/test_class_user_application_contract.py`

### 3.3 本 PR 内要完成的 contract

- `GetClassUserStatusDefinitionQuery`
- `GetClassUserStatusCurrentQuery`
- `GetClassUserSnapshotQuery`
- `ListClassUserStatusHistoryQuery`
- `ListClassUserManagementRecordsQuery`
- `ExportClassUserManagementRecordsQuery`
- `ApplyClassUserStatusChangeCommand`
- `UpdateClassUserStatusSyncResultCommand`
- `MigrateClassUserStatusFromContactTagsCommand`

### 3.4 不进入的内容

- 不切 `http/admin_class_user.py`
- 不切 `domains/admin_console/service.py`
- 不切 `http/admin_support.py`
- 不切 `domains/marketing_automation/service.py`
- 不切 `domains/user_ops/service.py`
- 不改 schema / SQL

### 3.5 交付标准

- application 层可 import、可调用
- 初期只 delegate legacy 实现，不重写业务规则
- `services.py` 中 class_user 兼容符号不再继续直接绑 domain/service 细节
- contract tests 能证明 skeleton 与 legacy 结果兼容

### 3.6 必跑测试

- `tests/test_class_user_application_contract.py`
- `tests/test_http_registration_contract.py`
- `tests/test_service_layer_layout.py`
- `tests/test_refactor_guardrails.py`

### 3.7 回滚方式

- 回滚 application skeleton 文件与 `services.py` shim
- 因为未切 caller，回滚不会影响线上行为

## 4. PR 3：Class User Admin Read Cutover

### 4.1 目标

把 admin 相关的 class_user 读入口和 migrate 入口切到正式 application contract，但不碰写 caller。

### 4.2 范围

建议改动：

- `wecom_ability_service/http/admin_class_user.py`
- `wecom_ability_service/domains/admin_console/service.py`
- `wecom_ability_service/http/admin_operations.py`（仅在必要时做极小适配）
- `wecom_ability_service/application/class_user/queries.py`（如需极小签名适配）
- `wecom_ability_service/application/class_user/commands.py`（如需极小签名适配）
- `tests/test_api.py`
- `tests/test_admin_console_phase4.py`

### 4.3 本 PR 内要完成的切换

- `ListClassUserManagementRecordsQuery`
- `ExportClassUserManagementRecordsQuery`
- `ListClassUserStatusHistoryQuery`
- `MigrateClassUserStatusFromContactTagsCommand`

### 4.4 明确不做

- 不改 `http/admin_support.py`
- 不改 `domains/marketing_automation/service.py`
- 不改 `domains/user_ops/service.py`
- 不切 sidebar 手工改状态的写路径

### 4.5 风险点

- `admin_console` 同时承担 overview/class-users/class-history shell 组装，不能把 view-model adapter 和 class_user query 混成一个超大改动
- migrate action 需要保持 admin audit log 不变

### 4.6 必跑测试

- `tests/test_api.py::test_class_user_management_list_export_and_ui`
- `tests/test_api.py::test_class_user_backoffice_ui_redirects_to_shell`
- `tests/test_admin_console_phase4.py::test_admin_operations_page_and_migrate_action_are_audited`
- `tests/contract/test_crm_contract.py::test_contract_class_user_read`
- `tests/test_http_registration_contract.py`
- `tests/test_service_layer_layout.py`
- `tests/test_refactor_guardrails.py`

### 4.7 回滚方式

- 保留 PR 2 skeleton 不动
- 单独回滚 admin route / admin console cutover

## 5. PR 4：Class User Write Caller Cutover A

### 5.1 目标

把 `admin_support` 与 `marketing_automation` 的 class_user 写入口切到正式 application command/query。

### 5.2 范围

建议改动：

- `wecom_ability_service/http/admin_support.py`
- `wecom_ability_service/domains/marketing_automation/service.py`
- `wecom_ability_service/application/class_user/queries.py`（如需极小签名适配）
- `wecom_ability_service/application/class_user/commands.py`（如需极小签名适配）
- `tests/test_api.py`
- `tests/test_conversion_service.py`

### 5.3 本 PR 内要完成的切换

- `GetClassUserStatusCurrentQuery`
- `GetClassUserSnapshotQuery`
- `ApplyClassUserStatusChangeCommand`
- `UpdateClassUserStatusSyncResultCommand`
- `GetClassUserStatusDefinitionQuery`

### 5.4 明确允许暂留的 caller 侧副作用

- `http/admin_support.py`
  - WeCom 标签加删
  - `save_tag_snapshot` / `remove_tag_snapshot`
  - `build_class_user_tag_view`
- `domains/marketing_automation/service.py`
  - 营销态重算
  - 候选批次取消
  - conversion dispatch log 补偿

### 5.5 风险点

- sidebar 手工打标的业务结果同时依赖 class_user current/history 与 WeCom tag sync result
- `marketing_automation` 的 `mark_enrolled` / `unmark_enrolled` 还牵着营销态与 dispatch side effect，不能顺手并进 class_user command

### 5.6 必跑测试

- `tests/test_api.py::test_sidebar_signup_tag_mark_is_mutually_exclusive`
- `tests/test_conversion_service.py::test_mark_enrolled_cancels_pending_candidate_and_unmark_recomputes_to_activated`
- `tests/test_conversion_service.py::test_unmark_enrolled_recomputes_to_wecom_connected_without_activation`
- `tests/test_conversion_service.py::test_unmark_enrolled_recomputes_to_mobile_only_without_live_external_facts`
- `tests/test_conversion_service.py::test_unmark_enrolled_without_restore_status_does_not_default_class_user_to_lead`
- `tests/test_http_registration_contract.py`
- `tests/test_service_layer_layout.py`
- `tests/test_refactor_guardrails.py`

### 5.7 回滚方式

- `admin_support.py` 与 `marketing_automation/service.py` 分开回滚
- application contract 保留不动，只回滚 caller cutover

## 6. PR 5：Class User Write Caller Cutover B

### 6.1 目标

清掉 `domains/user_ops/service.py` 中残留的 class_user 重复实现和绕行调用，只保留对正式 application contract 的调用。

### 6.2 范围

建议改动：

- `wecom_ability_service/domains/user_ops/service.py`
- `wecom_ability_service/application/class_user/queries.py`（如需极小签名适配）
- `wecom_ability_service/application/class_user/commands.py`（如需极小签名适配）
- `tests/test_user_ops_api.py`

### 6.3 本 PR 内要完成的切换

- 删除或退化 `domains/user_ops/service.py::apply_class_user_status_change`
- 删除或退化 `domains/user_ops/service.py::migrate_class_user_status_from_contact_tags`
- `user_ops` 内 remaining class_user 读取统一走：
  - `GetClassUserStatusDefinitionQuery`
  - `GetClassUserStatusCurrentQuery`
- `user_ops` 内 remaining class_user 写入统一走：
  - `ApplyClassUserStatusChangeCommand`
  - `MigrateClassUserStatusFromContactTagsCommand`

### 6.4 明确不做

- 不重构 `user_ops` lead pool 内部模块
- 不进入 `routing_config`
- 不改 schema / SQL

### 6.5 风险点

- `user_ops` 文件体量大，class_user 重复实现和 lead-pool 行为交织严重
- 如果在 PR 5 内顺手改 `user_ops` 其他 write path，会把 class_user 收口 PR 变成 user_ops 重构

### 6.6 必跑测试

- `tests/test_user_ops_api.py::test_owner_backfill_apply_writes_current_and_history`
- `tests/test_user_ops_api.py::test_history_contains_activation_patch_records_for_existing_member`
- 新增的 class_user/user_ops contract 冻结测试
- `tests/test_http_registration_contract.py`
- `tests/test_service_layer_layout.py`
- `tests/test_refactor_guardrails.py`

### 6.7 回滚方式

- 只回滚 `domains/user_ops/service.py` 的 caller cutover
- 不回滚 PR 2~PR 4 已稳定的 application/class_user owner

## 7. 不进入的范围

整个 class_user 四个 PR 都不进入：

- `user_ops` 业务规则重构
- `routing_config` 保存链路
- `identity_contact` 主线追加改造
- `questionnaire`、`automation_conversion`、`customer_pulse` 内部模块拆分
- schema / SQL migration

## 8. 推荐边界结论

推荐边界固定为：

1. PR 2 只建 class_user contract 和 tests，不切 caller。
2. PR 3 只切 admin read shell 与 migrate 入口。
3. PR 4 只切 `admin_support` / `marketing_automation` 写 caller。
4. PR 5 只清 `user_ops` 里的 class_user 重复实现。

这个边界的好处是：

- PR 2 可以零业务风险落地。
- PR 3 先固定管理台与 admin shell 的读 contract。
- PR 4 专门处理 sidebar/admin_support/marketing automation 这组写兼容。
- PR 5 最后单独面对 `user_ops` 这个高耦合文件，避免一次 PR 把 read shell、write caller、duplicate removal 全混在一起。
