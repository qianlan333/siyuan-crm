# Wave 2 Class User Callers Map

日期：2026-04-20

## 1. 目的

本文件只回答 3 个问题：

1. 现在哪些 caller 还在直接使用 legacy `class_user` 入口。
2. 每个 caller 后续应该切到哪个正式 application contract。
3. 哪些跨 context 副作用仍必须显式留在 caller 侧，不能悄悄并进 class_user command。

## 2. 调用方总表

| 调用方 | 当前 direct import / direct call | 当前职责 | 目标正式入口 | 暂时保留在 caller 侧的跨 context 副作用 | 推荐切换 PR |
| --- | --- | --- | --- | --- | --- |
| `wecom_ability_service/http/admin_support.py` | `get_class_user_status_current`、`apply_class_user_status_change`、`update_class_user_status_sync_result`；本地 `_get_class_user_snapshot` | sidebar 手工改状态时写 current/history，并回写 WeCom tag sync 结果 | `GetClassUserStatusCurrentQuery`、`GetClassUserSnapshotQuery`、`ApplyClassUserStatusChangeCommand`、`UpdateClassUserStatusSyncResultCommand` | 企微打标、`save_tag_snapshot`、`remove_tag_snapshot`、`build_class_user_tag_view` 继续留在 admin support | PR 4 |
| `wecom_ability_service/domains/marketing_automation/service.py` | `get_class_user_status_definition`、`get_class_user_status_current`、`apply_class_user_status_change`；本地 `_build_class_user_snapshot_for_conversion` | `mark_enrolled` / `unmark_enrolled` 时调整班级状态 | `GetClassUserStatusDefinitionQuery`、`GetClassUserStatusCurrentQuery`、`GetClassUserSnapshotQuery`、`ApplyClassUserStatusChangeCommand` | 营销态重算、候选批次取消、dispatch log 补偿继续留在 marketing automation | PR 4 |
| `wecom_ability_service/domains/user_ops/service.py` | 本地重复实现 `apply_class_user_status_change`、`migrate_class_user_status_from_contact_tags`；同时调用 `get_class_user_status_definition`、`get_class_user_status_current`、`upsert_class_user_status_current`、`append_class_user_status_history` | `user_ops` 导入/回填链路里顺手维护班级状态 | `GetClassUserStatusDefinitionQuery`、`GetClassUserStatusCurrentQuery`、`ApplyClassUserStatusChangeCommand`、`MigrateClassUserStatusFromContactTagsCommand` | lead pool current/history 写入、导入批次审计、deferred jobs 继续留在 user_ops | PR 5 |
| `wecom_ability_service/http/admin_class_user.py` | `services.py` 上的 `list_class_user_management_records`、`export_class_user_management_records`、`list_class_user_status_history`、`migrate_class_user_status_from_contact_tags` | 管理后台班级状态列表、导出、history、迁移接口 | `ListClassUserManagementRecordsQuery`、`ExportClassUserManagementRecordsQuery`、`ListClassUserStatusHistoryQuery`、`MigrateClassUserStatusFromContactTagsCommand` | HTTP 层只保留参数解析、Excel response build、错误响应包装 | PR 3 |
| `wecom_ability_service/http/admin_operations.py` | 无 direct import；通过 `domains/admin_console/service.py::build_operations_payload` / `execute_operations_action` 间接触发 class_user 列表、history、迁移 | 运营后台 transport shell | 间接依赖 `ListClassUserManagementRecordsQuery`、`ListClassUserStatusHistoryQuery`、`MigrateClassUserStatusFromContactTagsCommand`；`admin_operations.py` 自己不应持有 class_user 业务逻辑 | 页面渲染、表单回跳与 admin shell glue 继续留在 transport | PR 3 |
| `wecom_ability_service/domains/admin_console/service.py` | `list_class_user_management_records`、`list_class_user_status_history`、`migrate_class_user_status_from_contact_tags` | operations shell 的 overview/class-users/class-history 页面拼装与动作转发 | `ListClassUserManagementRecordsQuery`、`ListClassUserStatusHistoryQuery`、`MigrateClassUserStatusFromContactTagsCommand` | admin audit log、tab/shell view-model 继续留在 admin_console | PR 3 |
| `wecom_ability_service/http/sidebar.py` | `services.get_class_user_status_current`；写路径经 `admin_support._apply_signup_sidebar_tag` 间接进入 class_user | sidebar 读当前班级状态，并触发手工状态变更入口 | `GetClassUserStatusCurrentQuery`；写路径仍通过 `admin_support` 在 PR 4 收口 | sidebar 营销态展示、绑定状态展示继续留在 sidebar | PR 3 读；PR 4 写 |
| `wecom_ability_service/customer_center/customer_profile_service.py` | `get_class_user_status_current` | customer profile 读班级状态展示 | `GetClassUserStatusCurrentQuery` | customer profile view-model 继续留在 customer read model | 后续 read cleanup，不在本轮 class_user 主线 |

## 3. 逐调用方说明

### 3.1 `http/admin_support.py`

当前 class_user 写链：

- `_apply_signup_sidebar_tag()` 先读 `get_class_user_status_current()`
- 再通过 `_get_class_user_snapshot()` 拼 snapshot
- 再执行 `apply_class_user_status_change()`
- 最后执行 `update_class_user_status_sync_result()`

切换口径：

- `http/admin_support.py` 未来只负责 parse request、企微打标、tag snapshot 与 response build。
- class_user current/history 双写和 sync result 回写统一进 `application/class_user/*`。
- `_list_class_user_management_records_live()` 是 admin-support 的 live tag 视图，不是正式 class_user read model owner。

### 3.2 `domains/marketing_automation/service.py`

当前 class_user 写链：

- `mark_enrolled()` / `unmark_enrolled()` 先读 `get_class_user_status_current()`
- 再通过本地 `_build_class_user_snapshot_for_conversion()` 组装 snapshot
- 再执行 `apply_class_user_status_change()`

切换口径：

- marketing automation 继续保有“营销态重算、候选取消、dispatch log 补偿”的 owner。
- 但 class_user 状态定义、current 读取、snapshot 组装、current/history 写入要切到 `application/class_user/*`。

### 3.3 `domains/user_ops/service.py`

当前问题不是单纯 caller，而是“caller + 重复实现”混在一起：

- 文件内直接保留了 `migrate_class_user_status_from_contact_tags()` 重复实现。
- 文件内直接保留了 `apply_class_user_status_change()` 重复实现。
- 还直接依赖 `upsert_class_user_status_current()`、`append_class_user_status_history()`。

切换口径：

- `user_ops` 未来只保留自己的 lead pool 业务与导入补偿。
- class_user 写面必须统一收回 `application/class_user/*`。
- PR 5 的目标是清掉这两份重复实现，而不是重构整个 `user_ops` 模块。

### 3.4 `http/admin_class_user.py`

当前路由职责偏薄，但 owner 还在 `services.py`：

- 列表：`list_class_user_management_records()`
- 导出：`export_class_user_management_records()`
- history：`list_class_user_status_history()`
- 迁移：`migrate_class_user_status_from_contact_tags()`

切换口径：

- route 只保留 request parse、response build 与错误码兼容。
- 正式 owner 统一改成 `application/class_user/*`。

### 3.5 `http/admin_operations.py` + `domains/admin_console/service.py`

`http/admin_operations.py` 自己不 direct import class_user，但它通过 `domains/admin_console/service.py` 间接消费：

- `build_operations_payload()` -> `list_class_user_management_records()` + `list_class_user_status_history()`
- `execute_operations_action(action="migrate-class-user")` -> `migrate_class_user_status_from_contact_tags()`

切换口径：

- transport 仍然只做 admin page shell。
- `domains/admin_console/service.py` 后续作为 admin view-model adapter，转调正式 application query/command。
- 不允许 `http/admin_operations.py` 直接新增 class_user 业务 import。

### 3.6 `http/sidebar.py`

`sidebar` 当前只有读 current 的 direct import，真正的写动作走 `admin_support._apply_signup_sidebar_tag()`。

切换口径：

- PR 3 可先把 `get_class_user_status_current` 的读入口改成正式 query。
- 写入口的真正收口点是 `admin_support.py`，放在 PR 4 处理。

## 4. 禁止新增的旁路

从本调用方地图开始，禁止新增以下旁路：

- `http/admin_class_user.py` 新增 direct import `services.*class_user*`
- `http/admin_support.py` 继续自己拼 current/history 双写
- `domains/marketing_automation/service.py` 继续扩张 `_build_class_user_snapshot_for_conversion()` 成为事实 owner
- `domains/user_ops/service.py` 继续保留或新增 class_user 写面的重复实现
- `http/admin_operations.py` 新增 direct import `domains.class_user.service` 或 repo

## 5. 切换顺序结论

推荐顺序固定为：

1. PR 2：先建 `application/class_user/*` skeleton 与 services shim delegation。
2. PR 3：先切 admin read shell 与 admin route，包括 `admin_class_user.py`、`admin_console/service.py`、`admin_operations.py` 的间接链路。
3. PR 4：再切 `admin_support.py` 与 `marketing_automation/service.py` 的 class_user 写入口。
4. PR 5：最后清 `domains/user_ops/service.py` 的 class_user 重复实现与剩余绕行。

原因：

- admin read shell 风险最低，先切可以固定 read contract。
- admin_support / marketing automation 写链副作用更重，需要在 read contract 稳住后单独切。
- `user_ops` 里是“重复实现 + 其他上下文逻辑”混合最深的一层，必须最后拆，避免把 class_user PR 做成 user_ops 重构。
