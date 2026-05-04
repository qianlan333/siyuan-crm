# Wave 2 Class User Contracts

日期：2026-04-20

## 1. 现状与约束

Gate 0 已经放行进入 `class_user` 阶段，但当前仓库里 `class_user` 写路径仍然存在 3 类 legacy owner 混用：

- `wecom_ability_service/domains/class_user/service.py` 是当前主实现。
- `wecom_ability_service/services.py` 仍暴露一组兼容符号与 shim。
- `wecom_ability_service/domains/user_ops/service.py` 还保留了 `apply_class_user_status_change`、`migrate_class_user_status_from_contact_tags` 两份重复实现。

Wave 2 的 class_user 主线先不改业务逻辑，只先把正式 application owner 与 caller cutover 顺序定清楚。

正式 owner 统一约定为：

- `wecom_ability_service/application/class_user/queries.py`
- `wecom_ability_service/application/class_user/commands.py`

兼容原则：

- 先建 contract，再切 caller。
- application 层初期只允许 delegate 旧实现，不重写规则。
- 不允许把新逻辑重新塞回 `services.py`、`http/*`、`domains/user_ops/service.py` 的 class_user 重复实现。
- `user_ops`、`marketing_automation`、`admin_support` 上仍存在的跨 context 副作用，本轮只显式列出，不提前并入 class_user command。

## 2. Contract 清单

### 2.1 `GetClassUserStatusDefinitionQuery`

| 项目 | 内容 |
| --- | --- |
| contract 名称 | `GetClassUserStatusDefinitionQuery` |
| 输入 DTO | `GetClassUserStatusDefinitionQueryDTO { signup_status: str }` |
| 输出 DTO | `GetClassUserStatusDefinitionResultDTO { signup_status: str, label: str, description?: str, order?: int, requires_wecom_tag?: bool, active?: bool } \| None` |
| 当前 legacy 入口 | `wecom_ability_service/services.py::get_class_user_status_definition` -> `wecom_ability_service/domains/class_user/service.py::get_class_user_status_definition` |
| 直接调用方 | `wecom_ability_service/domains/marketing_automation/service.py`、`wecom_ability_service/domains/user_ops/service.py` |
| 跨 context 副作用 | 无；只读常量定义 |
| 禁止绕过的旧入口 | `services.get_class_user_status_definition`、`domains.class_user.service.get_class_user_status_definition`、直接读取 `infra.constants.CLASS_USER_ALLOWED_STATUSES` 扩散规则 |
| 兼容策略 | 继续保持“未知 `signup_status` 返回 `None`”的兼容语义，不新增兜底状态 |
| 推荐切换顺序 | PR 2 建 query skeleton；PR 4/PR 5 再切 `marketing_automation` / `user_ops` |

### 2.2 `GetClassUserStatusCurrentQuery`

| 项目 | 内容 |
| --- | --- |
| contract 名称 | `GetClassUserStatusCurrentQuery` |
| 输入 DTO | `GetClassUserStatusCurrentQueryDTO { external_userid: str }` |
| 输出 DTO | `GetClassUserStatusCurrentResultDTO { external_userid: str, signup_status: str, signup_label_name: str, customer_name_snapshot: str, owner_userid_snapshot: str, mobile_snapshot: str, set_by_userid: str, set_at: str, wecom_tag_sync_status: str, wecom_tag_sync_error: str, status_flags_json?: str } \| None` |
| 当前 legacy 入口 | `wecom_ability_service/services.py::get_class_user_status_current` -> `wecom_ability_service/domains/class_user/service.py::get_class_user_status_current` |
| 直接调用方 | `wecom_ability_service/http/sidebar.py`、`wecom_ability_service/http/admin_support.py`、`wecom_ability_service/domains/marketing_automation/service.py`、`wecom_ability_service/customer_center/customer_profile_service.py`、`wecom_ability_service/domains/user_ops/service.py` |
| 跨 context 副作用 | 无；但该 query 的结果会被 `sidebar`、customer read model、marketing automation 当作后续逻辑条件 |
| 禁止绕过的旧入口 | `services.get_class_user_status_current`、`domains.class_user.service.get_class_user_status_current`、`domains.customer_pulse.repo.get_class_user_status_current` 风格的跨 context repo 直读继续扩散 |
| 兼容策略 | 继续返回当前行的扁平 dict 结构，`None` 语义保持不变 |
| 推荐切换顺序 | PR 2 建 query skeleton；PR 3 先切只读 caller；PR 4/PR 5 再切写 caller 的前置读取 |

### 2.3 `GetClassUserSnapshotQuery`

| 项目 | 内容 |
| --- | --- |
| contract 名称 | `GetClassUserSnapshotQuery` |
| 输入 DTO | `GetClassUserSnapshotQueryDTO { external_userid: str, owner_userid?: str }` |
| 输出 DTO | `GetClassUserSnapshotResultDTO { external_userid: str, customer_name_snapshot: str, owner_userid_snapshot: str, mobile_snapshot: str }` |
| 当前 legacy 入口 | `wecom_ability_service/services.py::get_class_user_snapshot` -> `wecom_ability_service/domains/class_user/service.py::get_class_user_snapshot`；`wecom_ability_service/http/admin_support.py::_get_class_user_snapshot`；`wecom_ability_service/domains/marketing_automation/service.py::_build_class_user_snapshot_for_conversion` |
| 直接调用方 | `wecom_ability_service/http/admin_support.py`、`wecom_ability_service/domains/marketing_automation/service.py` |
| 跨 context 副作用 | 无写副作用；会读取 contact profile 与 identity 解析结果，属于 `class_user` 对 `customer_read_model` + `identity_contact` 的正式只读依赖 |
| 禁止绕过的旧入口 | `services.get_class_user_snapshot`、`domains.class_user.service.get_class_user_snapshot`、`http/admin_support.py::_get_class_user_snapshot`、`domains/marketing_automation/service.py::_build_class_user_snapshot_for_conversion` |
| 兼容策略 | 保持 owner fallback 顺序不变：显式 owner -> contact owner -> identity owner -> identity follow-user |
| 推荐切换顺序 | PR 2 建 query skeleton；PR 4 切 `admin_support` / `marketing_automation` |

### 2.4 `ListClassUserStatusHistoryQuery`

| 项目 | 内容 |
| --- | --- |
| contract 名称 | `ListClassUserStatusHistoryQuery` |
| 输入 DTO | `ListClassUserStatusHistoryQueryDTO { limit?: int }` |
| 输出 DTO | `ListClassUserStatusHistoryResultDTO { items: list[object], total: int, limit: int }` |
| 当前 legacy 入口 | `wecom_ability_service/services.py::list_class_user_status_history` -> `wecom_ability_service/domains/class_user/service.py::list_class_user_status_history` |
| 直接调用方 | `wecom_ability_service/http/admin_class_user.py`、`wecom_ability_service/domains/admin_console/service.py`、`wecom_ability_service/http/admin_operations.py`（经 `domains/admin_console/service.py` 间接调用） |
| 跨 context 副作用 | 无；只读 history 表 |
| 禁止绕过的旧入口 | `services.list_class_user_status_history`、`domains.class_user.service.list_class_user_status_history`、controller 直连 repo |
| 兼容策略 | 保持 `items/total/limit` 三个顶层 key，不在本轮增加筛选语义 |
| 推荐切换顺序 | PR 2 建 query skeleton；PR 3 切 admin read shell |

### 2.5 `ApplyClassUserStatusChangeCommand`

| 项目 | 内容 |
| --- | --- |
| contract 名称 | `ApplyClassUserStatusChangeCommand` |
| 输入 DTO | `ApplyClassUserStatusChangeCommandDTO { external_userid: str, signup_status: str, set_by_userid: str, customer_name_snapshot: str, owner_userid_snapshot: str, mobile_snapshot: str, request_meta?: { source?: str, operator?: str, request_id?: str } }` |
| 输出 DTO | `ApplyClassUserStatusChangeResultDTO { external_userid: str, signup_status: str, signup_label_name: str, customer_name_snapshot: str, owner_userid_snapshot: str, mobile_snapshot: str, set_by_userid: str, set_at: str, wecom_tag_sync_status: str, wecom_tag_sync_error: str }` |
| 当前 legacy 入口 | `wecom_ability_service/services.py::apply_class_user_status_change` -> `wecom_ability_service/domains/class_user/service.py::apply_class_user_status_change`；`wecom_ability_service/domains/user_ops/service.py::apply_class_user_status_change` 重复实现 |
| 直接调用方 | `wecom_ability_service/http/admin_support.py`、`wecom_ability_service/domains/marketing_automation/service.py` |
| 跨 context 副作用 | command 本体只应写 `class_user_status_current` + `class_user_status_history`；`admin_support` 的 WeCom 打标、`marketing_automation` 的营销态重算、`user_ops` 的 lead pool 补偿应继续留在 caller |
| 禁止绕过的旧入口 | `services.apply_class_user_status_change`、`domains.class_user.service.apply_class_user_status_change`、`domains/user_ops/service.py::apply_class_user_status_change`、caller 自己拼 current/history 双写 |
| 兼容策略 | 保持写入后默认 `wecom_tag_sync_status="pending"`，异常语义仍以当前 `ValueError("signup_status is invalid")` 为准 |
| 推荐切换顺序 | PR 2 建 command skeleton；PR 4 切 `admin_support` + `marketing_automation`；PR 5 清 `user_ops` 重复实现 |

### 2.6 `UpdateClassUserStatusSyncResultCommand`

| 项目 | 内容 |
| --- | --- |
| contract 名称 | `UpdateClassUserStatusSyncResultCommand` |
| 输入 DTO | `UpdateClassUserStatusSyncResultCommandDTO { external_userid: str, wecom_tag_sync_status: str, wecom_tag_sync_error?: str, request_meta?: { source?: str, operator?: str, request_id?: str } }` |
| 输出 DTO | `UpdateClassUserStatusSyncResultResultDTO { ok: bool, external_userid: str, wecom_tag_sync_status: str, wecom_tag_sync_error: str }` |
| 当前 legacy 入口 | `wecom_ability_service/services.py::update_class_user_status_sync_result` -> `wecom_ability_service/domains/class_user/service.py::update_class_user_status_sync_result` |
| 直接调用方 | `wecom_ability_service/http/admin_support.py` |
| 跨 context 副作用 | 无；只更新 current + latest history 上的 WeCom tag sync 结果字段 |
| 禁止绕过的旧入口 | `services.update_class_user_status_sync_result`、`domains.class_user.service.update_class_user_status_sync_result`、controller/transport 直写 sync 结果列 |
| 兼容策略 | 继续保持“只写同步结果，不改 signup_status”的语义 |
| 推荐切换顺序 | PR 2 建 command skeleton；PR 4 切 `admin_support` |

### 2.7 `ListClassUserManagementRecordsQuery`

| 项目 | 内容 |
| --- | --- |
| contract 名称 | `ListClassUserManagementRecordsQuery` |
| 输入 DTO | `ListClassUserManagementRecordsQueryDTO { signup_status?: str }` |
| 输出 DTO | `ListClassUserManagementRecordsResultDTO { filter: str, status_definitions: list[object], stats: list[object], items: list[object], total: int, meta: object }` |
| 当前 legacy 入口 | `wecom_ability_service/services.py::list_class_user_management_records` -> `wecom_ability_service/domains/class_user/service.py::list_class_user_management_records` |
| 直接调用方 | `wecom_ability_service/http/admin_class_user.py`、`wecom_ability_service/domains/admin_console/service.py`、`wecom_ability_service/http/admin_operations.py`（经 `domains/admin_console/service.py` 间接调用） |
| 跨 context 副作用 | 无写副作用；但 query 会依赖 tags 侧状态定义与 identity/binding 读模型拼装出的 mobile/follow-user 展示 |
| 禁止绕过的旧入口 | `services.list_class_user_management_records`、`domains.class_user.service.list_class_user_management_records`、`http/admin_support.py::_list_class_user_management_records_live` 被误当正式 owner 继续扩散 |
| 兼容策略 | 保持 `status_fields`、`stats`、`meta.reserved_filters` 结构不变；`tag_initialization` 与 `live_refresh` 仍由 controller/shell 补充 |
| 推荐切换顺序 | PR 2 建 query skeleton；PR 3 切 admin list shell |

### 2.8 `ExportClassUserManagementRecordsQuery`

| 项目 | 内容 |
| --- | --- |
| contract 名称 | `ExportClassUserManagementRecordsQuery` |
| 输入 DTO | `ExportClassUserManagementRecordsQueryDTO { signup_status?: str }` |
| 输出 DTO | `ExportClassUserManagementRecordsResultDTO { headers: list[str], rows: list[list[object]], filename: str }` |
| 当前 legacy 入口 | `wecom_ability_service/services.py::export_class_user_management_records` -> `wecom_ability_service/domains/class_user/service.py::export_class_user_management_records` |
| 直接调用方 | `wecom_ability_service/http/admin_class_user.py` |
| 跨 context 副作用 | 无 |
| 禁止绕过的旧入口 | `services.export_class_user_management_records`、`domains.class_user.service.export_class_user_management_records`、controller 重新手写导出列顺序 |
| 兼容策略 | 保持 Excel 列顺序、文件名命名规则与 `application/vnd.ms-excel` 输出契约不变 |
| 推荐切换顺序 | PR 2 建 query skeleton；PR 3 切 admin export |

### 2.9 `MigrateClassUserStatusFromContactTagsCommand`

| 项目 | 内容 |
| --- | --- |
| contract 名称 | `MigrateClassUserStatusFromContactTagsCommand` |
| 输入 DTO | `MigrateClassUserStatusFromContactTagsCommandDTO { request_meta?: { operator?: str, source?: str, request_id?: str } }` |
| 输出 DTO | `MigrateClassUserStatusFromContactTagsResultDTO { migrated_count: int }` |
| 当前 legacy 入口 | `wecom_ability_service/services.py::migrate_class_user_status_from_contact_tags` -> `wecom_ability_service/domains/class_user/service.py::migrate_class_user_status_from_contact_tags`；`wecom_ability_service/domains/user_ops/service.py::migrate_class_user_status_from_contact_tags` 重复实现 |
| 直接调用方 | `wecom_ability_service/http/admin_class_user.py`、`wecom_ability_service/domains/admin_console/service.py::execute_operations_action`、`wecom_ability_service/http/admin_operations.py`（经 `domains/admin_console/service.py` 间接调用） |
| 跨 context 副作用 | 读取 `contact_tags` + `signup_tag_rules`，并写 current/history；不应在 command 内顺手追加 `user_ops` 或 routing 补偿 |
| 禁止绕过的旧入口 | `services.migrate_class_user_status_from_contact_tags`、`domains.class_user.service.migrate_class_user_status_from_contact_tags`、`domains/user_ops/service.py::migrate_class_user_status_from_contact_tags` |
| 兼容策略 | 保持“按最新 tag_created_at + tag_id 选中候选标签”的选择规则，以及 `wecom_tag_sync_status="migrated"` 的写入语义 |
| 推荐切换顺序 | PR 2 建 command skeleton；PR 3 切 admin shell / admin route；PR 5 清 `user_ops` 重复实现 |

## 3. 推荐 contract 分层

建议正式 application owner 如下：

- `application/class_user/queries.py`
  - `GetClassUserStatusDefinitionQuery`
  - `GetClassUserStatusCurrentQuery`
  - `GetClassUserSnapshotQuery`
  - `ListClassUserStatusHistoryQuery`
  - `ListClassUserManagementRecordsQuery`
  - `ExportClassUserManagementRecordsQuery`
- `application/class_user/commands.py`
  - `ApplyClassUserStatusChangeCommand`
  - `UpdateClassUserStatusSyncResultCommand`
  - `MigrateClassUserStatusFromContactTagsCommand`

## 4. 本轮明确不做的事

- 不把 `marketing_automation` 的营销态重算并进 class_user command。
- 不把 `admin_support` 的企微打标与 tag snapshot 清理并进 class_user command。
- 不把 `user_ops` 的 lead pool 写逻辑并进 class_user command。
- 不进入 `routing_config`、`questionnaire`、`automation_conversion` 内部实现。

## 5. 结论

class_user 的正式 contract 应该先把“状态定义 / 当前态 / snapshot / 管理台读模型 / current+history 双写 / tag sync 回写 / contact-tags 迁移”这 9 个稳定入口固定下来，然后再按 caller 分批切换。

最关键的 legacy 债务是：

- `services.py` 上的 class_user 兼容符号仍是默认入口。
- `domains/user_ops/service.py` 还保留 class_user 写面的重复实现。

后续 PR 必须优先把 owner 收到 `application/class_user/*`，再清重复实现，而不是继续在 caller 层扩散 current/history 双写。
