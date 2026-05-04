# Wave 2 Class User Test Plan

日期：2026-04-20

## 1. 目标

本测试计划只服务于 Wave 2 的 `class_user` 主线，目标是先冻结合同，再切 wiring。

本轮重点冻结 6 类行为：

- 同一 `external_userid` 的 current/history 更新顺序
- sidebar 手工改状态的兼容行为
- marketing automation 触发状态变化的兼容行为
- user_ops 触发状态变化的兼容行为
- WeCom tag sync 结果写回行为
- contact-tags 初始化迁移行为

本文件不新增测试代码，只说明：

- 当前已有哪些覆盖
- 哪些覆盖不足
- 建议在后续 class_user PR 里先补哪些护栏再切 wiring

## 2. 现有覆盖盘点

| 冻结主题 | 当前已有测试 | 现状判断 |
| --- | --- | --- |
| class_user 读 contract 基础面 | `tests/contract/test_crm_contract.py::test_contract_class_user_read` | 只冻结了 sidebar signup-tag status 的只读 contract，还没有 application contract 级测试 |
| sidebar 手工改状态兼容行为 | `tests/test_api.py::test_sidebar_signup_tag_mark_is_mutually_exclusive` | 已覆盖“互斥打标 + local tag snapshot 更新 + path/JSON 不变”，但还没有显式断言 current/history 顺序 |
| 管理后台 list/export/UI contract | `tests/test_api.py::test_class_user_management_list_export_and_ui` | 已覆盖列表、导出、shell 跳转与核心 JSON/Excel 结构 |
| admin operations 迁移入口与审计 | `tests/test_admin_console_phase4.py::test_admin_operations_page_and_migrate_action_are_audited` | 已覆盖 `/admin/user-ops/actions` 的 migrate action 与 admin audit log，但没有冻结迁移写 current/history 的细节 |
| marketing automation 触发状态变化 | `tests/test_conversion_service.py::test_mark_enrolled_cancels_pending_candidate_and_unmark_recomputes_to_activated`、`test_unmark_enrolled_recomputes_to_wecom_connected_without_activation`、`test_unmark_enrolled_recomputes_to_mobile_only_without_live_external_facts`、`test_unmark_enrolled_without_restore_status_does_not_default_class_user_to_lead` | 已覆盖 mark/unmark 对 class_user 状态结果的兼容面，但没有 application contract 级断言 |
| MCP/营销反馈路径与 class_user 联动 | `tests/test_conversion_service.py::test_mcp_mark_and_unmark_enrolled_tools_use_unified_conversion_service`、`test_mcp_record_conversion_feedback_mark_enrolled_matches_manual_mark`、`tests/contract/test_crm_contract.py::test_contract_conversion_feedback_record` | 已覆盖通过 conversion service 间接写 class_user 的兼容行为 |
| user_ops 触发 class_user 兼容行为 | 当前没有直接冻结 `domains/user_ops/service.py` 内 class_user 重复实现的专门测试 | 明显缺口，需要在切 user_ops caller 前补测试 |
| WeCom tag sync 结果写回 | `tests/test_api.py::test_sidebar_signup_tag_mark_is_mutually_exclusive` 间接覆盖成功分支；`tests/test_api.py` 中 class-user management 相关用例也会读取 `wecom_tag_sync_status` | 已有部分成功态覆盖，但失败态和“current/history 同时回写”缺少显式断言 |
| contact-tags 初始化与迁移 | `tests/test_api.py::test_class_user_management_bootstrap_creates_missing_lead_tag`、`tests/test_admin_console_phase4.py::test_admin_operations_page_and_migrate_action_are_audited` | bootstrap 已覆盖，真正的迁移 current/history 写入结果仍需单独冻结 |

## 3. 关键风险与缺口

### 3.1 current/history 更新顺序还没有被显式冻结

当前实现约束是：

- `ApplyClassUserStatusChangeCommand` 对应的 legacy 实现会先 upsert current，再 append history。
- `UpdateClassUserStatusSyncResultCommand` 对应的 legacy 实现会同时更新 current 和 latest history 的 sync 字段。
- `MigrateClassUserStatusFromContactTagsCommand` 对应的 legacy 实现也会同时写 current/history。

当前缺口：

- 没有一组测试明确断言同一 `external_userid` 的 current/history 先后与最终字段一致性。
- history endpoint 本身还没有独立 route/contract 断言。

### 3.2 sidebar 手工改状态只冻住了结果，没有冻住内部写面

当前已覆盖：

- 互斥移除旧标签
- 新标签打标成功
- 返回 `signup_status/current_tag/removed_tag_ids`

当前缺口：

- 没有显式断言 `apply_class_user_status_change` 与 `update_class_user_status_sync_result` 两段写路径对 current/history 的最终一致性。
- 失败分支的 `wecom_tag_sync_status="failed"` 与错误回写缺少冻结。

### 3.3 user_ops 还是 class_user 写面的最大盲区

当前现状：

- `domains/user_ops/service.py` 里保留了 class_user 写面的重复实现。
- 现有 `tests/test_user_ops_api.py` 主要覆盖 lead pool current/history，不是 class_user current/history。

当前缺口：

- 还没有专门测试冻结 `user_ops` 触发 class_user 状态变更与迁移时的兼容行为。

## 4. PR 2 测试计划

PR 2 目标是建立 `application/class_user/*` skeleton 与 services shim delegation，不切 caller。

建议新增测试文件：

- `tests/test_class_user_application_contract.py`

建议冻结的最小 contract：

1. `GetClassUserStatusDefinitionQuery`
   - 有效 `signup_status` 返回定义
   - 无效 `signup_status` 返回 `None`
2. `GetClassUserStatusCurrentQuery`
   - 已存在 current 行时返回兼容结构
   - 缺 current 行时返回 `None`
3. `GetClassUserSnapshotQuery`
   - owner fallback 顺序保持兼容
   - mobile / customer_name snapshot 取值顺序保持兼容
4. `ListClassUserManagementRecordsQuery`
   - `stats/items/meta` 顶层 key 兼容
5. `ExportClassUserManagementRecordsQuery`
   - headers 顺序与 filename 命名保持兼容
6. `ApplyClassUserStatusChangeCommand`
   - 只验证 delegate 结果与 legacy 保持一致
7. `UpdateClassUserStatusSyncResultCommand`
   - 只验证 success/failed 回写结构与 legacy 保持一致
8. `MigrateClassUserStatusFromContactTagsCommand`
   - 只验证 `migrated_count` 与 legacy 保持一致

PR 2 必跑：

- `tests/test_class_user_application_contract.py`
- `tests/test_http_registration_contract.py`
- `tests/test_service_layer_layout.py`
- `tests/test_refactor_guardrails.py`

## 5. PR 3 测试计划

PR 3 目标是切 admin read shell 与 admin route。

建议补强的冻结断言：

1. `/api/admin/class-user-management/history`
   - `items/total/limit` 不变
   - `limit` 非法时仍保持当前 400 语义
2. `admin_console` shell
   - `/admin/class-users?tab=class-users`
   - `/admin/user-ops?tab=class-history`
   - 两条 shell 仍然拿到兼容的 class-user list/history payload
3. `migrate-class-user` admin action
   - action 成功后 admin audit log 不变
   - `migrated_count` 不变

PR 3 主要依赖现有测试文件：

- `tests/test_api.py`
- `tests/test_admin_console_phase4.py`
- `tests/contract/test_crm_contract.py`

建议重点回归：

- `tests/test_api.py::test_class_user_management_list_export_and_ui`
- `tests/test_api.py::test_class_user_backoffice_ui_redirects_to_shell`
- `tests/test_admin_console_phase4.py::test_admin_operations_page_and_migrate_action_are_audited`
- `tests/contract/test_crm_contract.py::test_contract_class_user_read`

建议补的新测试：

- `tests/test_class_user_application_contract.py::test_list_class_user_status_history_contract_matches_legacy`
- `tests/test_api.py::test_admin_class_user_history_endpoint_contract`
- `tests/test_admin_console_phase4.py::test_admin_operations_class_history_tab_uses_class_user_query_contract`

## 6. PR 4 测试计划

PR 4 目标是切 `http/admin_support.py` 与 `domains/marketing_automation/service.py` 的 class_user 写入口。

必须冻结的行为：

1. sidebar 手工改状态兼容
   - 新状态写 current/history
   - 企微打标成功后 sync result 写回 success
   - 企微打标失败后 sync result 写回 failed + error
2. marketing automation 兼容
   - `mark_enrolled` 仍写出当前 `signed_*`
   - `unmark_enrolled` 仍按现有规则恢复到 `lead` 或清空
   - 营销态重算与 dispatch cancel 结果不变
3. snapshot 兼容
   - admin_support / marketing automation 都通过正式 `GetClassUserSnapshotQuery`
   - customer_name / owner / mobile snapshot 不串字段

PR 4 重点回归：

- `tests/test_api.py::test_sidebar_signup_tag_mark_is_mutually_exclusive`
- `tests/test_conversion_service.py::test_mark_enrolled_cancels_pending_candidate_and_unmark_recomputes_to_activated`
- `tests/test_conversion_service.py::test_unmark_enrolled_recomputes_to_wecom_connected_without_activation`
- `tests/test_conversion_service.py::test_unmark_enrolled_recomputes_to_mobile_only_without_live_external_facts`
- `tests/test_conversion_service.py::test_unmark_enrolled_without_restore_status_does_not_default_class_user_to_lead`

建议补的新测试：

- `tests/test_api.py::test_sidebar_signup_tag_mark_updates_class_user_current_and_history_in_order`
- `tests/test_api.py::test_sidebar_signup_tag_mark_failed_sync_updates_class_user_sync_result`
- `tests/test_conversion_service.py::test_mark_enrolled_uses_class_user_snapshot_contract`

## 7. PR 5 测试计划

PR 5 目标是切 `domains/user_ops/service.py` 中残留的 class_user 重复实现，不重构整个 `user_ops` 模块。

必须冻结的行为：

1. `user_ops` 调 class_user 写面时不再自己拼 current/history 双写
2. owner backfill / 导入链路在保留 lead pool 兼容行为的同时，不破坏 class_user 状态一致性
3. `migrate_class_user_status_from_contact_tags` 的 caller 若来自 `user_ops`，结果与正式 command 一致

现有依赖测试：

- `tests/test_user_ops_api.py::test_owner_backfill_apply_writes_current_and_history`
- `tests/test_user_ops_api.py::test_history_contains_activation_patch_records_for_existing_member`

现状判断：

- 这两条测试主要冻住的是 `user_ops_lead_pool_*`，不是 class_user current/history。
- PR 5 前必须新增 class_user 专项测试，否则无法证明 duplicate removal 没有破坏兼容。

建议补的新测试：

- `tests/test_user_ops_api.py::test_user_ops_class_user_status_change_matches_application_command`
- `tests/test_user_ops_api.py::test_user_ops_migrate_class_user_status_uses_formal_command_result`

## 8. 建议新增测试清单

以下是当前最值得补的 6 条冻结测试：

1. `test_class_user_application_contract_apply_status_change_matches_legacy`
   - 文件：`tests/test_class_user_application_contract.py`
   - PR：2
2. `test_class_user_application_contract_migrate_from_contact_tags_matches_legacy`
   - 文件：`tests/test_class_user_application_contract.py`
   - PR：2
3. `test_admin_class_user_history_endpoint_contract`
   - 文件：`tests/test_api.py`
   - PR：3
4. `test_sidebar_signup_tag_mark_updates_class_user_current_and_history_in_order`
   - 文件：`tests/test_api.py`
   - PR：4
5. `test_sidebar_signup_tag_mark_failed_sync_updates_class_user_sync_result`
   - 文件：`tests/test_api.py`
   - PR：4
6. `test_user_ops_class_user_status_change_matches_application_command`
   - 文件：`tests/test_user_ops_api.py`
   - PR：5

## 9. 结论

现有测试已经覆盖了 class_user 的读管理台、sidebar 手工打标结果、marketing automation 的 mark/unmark 主路径，但还没有把 “application contract + current/history 一致性 + user_ops duplicate removal” 冻结成独立测试层。

因此推荐顺序固定为：

1. PR 2 先补 application contract tests。
2. PR 3 再切 admin read shell。
3. PR 4 再切 admin_support / marketing automation 写入口。
4. PR 5 最后切 user_ops duplicate removal。
