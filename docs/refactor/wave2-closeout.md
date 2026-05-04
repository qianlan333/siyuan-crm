# Wave 2 Closeout

日期：2026-04-20

## 总结

Wave 2 的目标是把 write path 从 legacy domain / `services.py` / caller 层重新归边到正式 application API。按当前仓库状态，`identity`、`class_user`、`routing_config`、`user_ops` 四条主线都已经完成 formal application owner 建立与主要 caller cutover。

## 主线验收

| 主线 | formal application API 是否已建立 | caller 是否已切走 legacy domain write | `services.py` 是否已不再承担主要写入口 | guardrail 是否已覆盖 | 备注 |
| --- | --- | --- | --- | --- | --- |
| `identity` | 是，`wecom_ability_service/application/identity_contact/*` 已建立 | 是，`http/sidebar.py`、`domains/questionnaire/service.py`、`http/background_jobs.py`、`http/sync_support.py`、`http/admin_support.py` 已切到 application owner | 是，只保留 compatibility wrapper | 是，已有 identity contract / caller cutover 回归与 legacy import baseline | residual side effects 仍可留在 legacy delegate，但 caller 已不直连 |
| `class_user` | 是，`wecom_ability_service/application/class_user/*` 已建立 | 是，`http/admin_support.py`、`domains/marketing_automation/service.py`、`domains/user_ops/service.py` 的主调用面已走 application owner | 是，只保留 shim / primitive 兼容可见性 | 是，已有 class-user caller cutover 约束与 contract 回归 | `domains/user_ops/service.py` 中仍有 bridge wrapper，但不再是 caller 默认入口 |
| `routing_config` | 是，`wecom_ability_service/application/routing_config/*` 已建立 | 是，`http/admin_config.py` 与 `domains/admin_config/service.py` 已经通过 application owner 处理写入口 | 是，只保留 read/compat wrapper | 是，admin_config 注册/契约回归与 legacy import baseline 已覆盖 | admin_config 不再直写 routing domain primitive |
| `user_ops` | 是，`wecom_ability_service/application/user_ops/*` 已建立 | 是，`http/admin_user_ops.py`、`domains/admin_console/service.py`、`http/background_jobs.py`、`http/sidebar.py`、`domains/admin_jobs/service.py` 已切到 application owner | 是，只保留 compatibility shim 与 internal primitive facade | 是，已有 caller cutover guardrail，本次又补了 pool-core primitive 外泄 guardrail | `domains/user_ops/service.py` 已完成内部 owner 拆分第一轮 closeout |

## 分主线说明

### identity

- formal API
  - `ResolvePersonIdentityQuery`
  - `GetContactBindingStatusQuery`
  - `BindExternalContactIdentityCommand`
  - `ReplaceFollowUsersCommand`
  - `RefreshExternalContactIdentityOwnerCommand`
  - `MarkExternalContactIdentityStatusCommand`
  - `MarkExternalContactFollowUserStatusCommand`
  - `CountExternalContactIdentityMapsQuery`
  - `GetPrimaryFollowUserUseridQuery`
- caller 状态
  - 最靠近用户输入的 sidebar / questionnaire 已切换
  - callback / sync / admin support 侧 identity read/write 已切换
- shim 状态
  - `services.py` 仅保留兼容符号

### class_user

- formal API
  - `GetClassUserStatusDefinitionQuery`
  - `GetClassUserStatusCurrentQuery`
  - `GetClassUserSnapshotQuery`
  - `ListClassUserStatusHistoryQuery`
  - `ApplyClassUserStatusChangeCommand`
  - `UpdateClassUserStatusSyncResultCommand`
  - `ListClassUserManagementRecordsQuery`
  - `ExportClassUserManagementRecordsQuery`
  - `MigrateClassUserStatusFromContactTagsCommand`
- caller 状态
  - admin support、marketing automation、user_ops 主写调用方已不再直连 legacy class_user 写函数
- shim 状态
  - `services.py` 中仅保留兼容 wrapper 与 primitive visibility

### routing_config

- formal API
  - `GetOwnerRoleMapQuery`
  - `SaveOwnerRoleSettingCommand`
  - `GetRoutingRuleConfigQuery`
  - `SaveRoutingRuleSettingCommand`
  - `ResolveContactRoutingContextQuery`
- caller 状态
  - admin config UI 与 service glue 已通过 application owner 保存 `owner_role_map` / `routing_rule_config`
- shim 状态
  - `services.py` 只保留 routing 相关 read/compat wrapper

### user_ops

- formal API
  - `GetUserOpsOverviewQuery`
  - `ListLeadPoolQuery`
  - `ListUserOpsHistoryQuery`
  - `ExportUserOpsPoolQuery`
  - `UpsertLeadPoolMemberCommand`
  - `WriteLeadPoolHistoryCommand`
  - `ScheduleUserOpsAutoAssignClassTermJobCommand`
  - `RunDueUserOpsDeferredJobsCommand`
  - `ImportExperienceLeadsCommand`
  - `ImportMobileClassTermCommand`
  - `ImportActivationStatusCommand`
  - `BackfillOwnerClassTermsCommand`
  - `RefreshUserOpsContactTagsCommand`
  - 以及 sidebar / deferred-job 辅助 query/command
- caller 状态
  - admin / background / sidebar / admin jobs 的主要写入口已全部统一到 application owner
  - 内部实现又进一步拆成 `deferred_job`、`sidebar`、`class_term`、`import`、`tag_refresh`、`pool_core`
- shim 状态
  - `services.py` 不再承担主写入口，只保留兼容 surface 和 internal primitive shim

## 仍保留的非阻塞债务

- `services.py` 仍存在兼容 wrapper，但已不是任何主线的主要写入口
- `domains/user_ops/service.py` 仍保留 read / maintenance / bridge facade
- 若要进入下一轮工作，重点应转向后续 wave 或其它 domain，而不是继续在 Wave 2 中扩大改造面

## 结论

从 architecture owner、caller cutover、shim 缩面和 guardrail 覆盖这 4 个维度看，Wave 2 主线已经完成。

如果按仓库级严格验收执行最终关单，当前唯一阻塞项是：

- `tests/test_user_ops_api.py::test_external_contact_event_marks_failed_when_qrcode_automation_raises`
  - 当前失败原因是测试文件断言里直接调用了未导入的 `_contact_sync_retry_limit()`，表现为 `NameError`
  - 这是一个测试层红灯，不是本轮 Wave 2 closeout 文档或 guardrail 改动引入的业务回归

因此，Wave 2 的业务与工程收口已完成；正式仓库级 closeout 仍需先清掉这 1 个测试阻塞。
