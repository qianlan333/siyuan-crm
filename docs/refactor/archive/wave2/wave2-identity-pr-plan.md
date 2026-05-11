# Wave 2 Identity PR Plan

日期：2026-04-19

## 1. 目标

Wave 2 当前只做 `identity` 主线，且必须严格串行推进。

本计划把 identity 收口拆成 3 个 PR：

- PR 2：Identity Application Skeleton
- PR 3：Identity Caller Cutover A
- PR 4：Identity Caller Cutover B

不把 `class_user` / `user_ops` / `routing_config` 混进来。

## 2. 切分原则

切分原则固定为：

1. 先建正式 application contract 与 tests。
2. 先切绑定兼容面最重的 caller。
3. 再切 callback / sync / admin support 这些副作用更多的链路。
4. 每个 PR 都必须可回滚，且不依赖后续 PR 才能保持现网行为。

## 3. PR 2：Identity Application Skeleton

### 3.1 目标

只建立 `application/identity_contact/*` 的最小可导入骨架，把 identity 的读写合同正式命名出来。

### 3.2 范围

建议改动：

- `wecom_ability_service/application/identity_contact/__init__.py`
- `wecom_ability_service/application/identity_contact/queries.py`
- `wecom_ability_service/application/identity_contact/commands.py`
- `tests/test_identity_application_contract.py`

可选最小文档同步：

- `docs/refactor/application-contract-catalog.md`
- `docs/refactor/context-boundary-map.md`

### 3.3 不进入的内容

- 不切 `http/sidebar.py`
- 不切 `domains/questionnaire/service.py`
- 不切 `http/background_jobs.py`
- 不切 `http/sync_support.py`
- 不切 `http/admin_support.py`
- 不改 schema / SQL

### 3.4 交付标准

- contract 名称、输入 DTO、输出 DTO 固化
- application 层可 import、可调用
- 仅 delegate 旧实现，不重写业务逻辑
- contract tests 能证明 skeleton 与 legacy 结果兼容

### 3.5 必跑测试

- `tests/test_identity_application_contract.py`
- `tests/test_http_registration_contract.py`
- `tests/test_service_layer_layout.py`
- `tests/test_refactor_guardrails.py`

### 3.6 回滚方式

- 回滚 application skeleton 文件
- 因为未切 caller，回滚不会影响线上行为

## 4. PR 3：Identity Caller Cutover A

### 4.1 目标

把绑定与身份识别相关 caller 切到正式 application contract，但不碰 callback / sync / admin support。

### 4.2 范围

建议改动：

- `wecom_ability_service/http/sidebar.py`
- `wecom_ability_service/http/identity.py`
- `wecom_ability_service/domains/questionnaire/service.py`
- `wecom_ability_service/application/identity_contact/queries.py`（如需极小签名适配）
- `wecom_ability_service/application/identity_contact/commands.py`（如需极小签名适配）
- `tests/test_api.py`
- `tests/contract/test_crm_contract.py`
- `tests/test_customer_center_api.py`（如需补“不串人”回归）

### 4.3 本 PR 内要完成的切换

- `ResolvePersonIdentityQuery`
- `GetContactBindingStatusQuery`
- `GetPrimaryFollowUserUseridQuery`
- `ResolveExternalContactIdentityQuery`
- `BindExternalContactIdentityCommand`

### 4.4 明确不做

- 不改 `http/background_jobs.py`
- 不改 `http/sync_support.py`
- 不改 `http/admin_support.py`
- 不拆 questionnaire 内部模块
- 不处理 class-user / user-ops 的内部 write owner

### 4.5 风险点

- mobile bind 当前自带 owner 解析、third-party user id 同步、lead-pool merge
- questionnaire 同时存在 mobile bind 与 openid backfill 两条 identity 路径
- rebind 后 customer center 若读到旧 person，将出现“串人”风险

### 4.6 必跑测试

- `tests/test_api.py::test_sidebar_bind_mobile_fills_missing_owner_from_contacts`
- `tests/test_api.py::test_sidebar_bind_mobile_succeeds_when_third_party_sync_fails`
- `tests/test_api.py::test_sidebar_bind_mobile_force_rebind_updates_binding`
- `tests/test_api.py::test_identity_resolve_supports_external_userid_and_mobile`
- `tests/test_api.py::test_identity_resolve_supports_unionid`
- `tests/test_api.py::test_questionnaire_mobile_submission_binds_contact_and_overwrites_old_mobile`
- `tests/test_api.py::test_external_contact_full_sync_and_identity_bind`
- `tests/contract/test_crm_contract.py`

### 4.7 回滚方式

- 保留 legacy symbol wrapper
- 若 query/command wiring 异常，可直接回滚 caller 改动，不影响 PR 2 skeleton 存在

## 5. PR 4：Identity Caller Cutover B

### 5.1 目标

把后台与同步侧的 identity 写入口收口到正式 application API。

### 5.2 范围

建议改动：

- `wecom_ability_service/http/background_jobs.py`
- `wecom_ability_service/http/sync_support.py`
- `wecom_ability_service/http/admin_support.py`
- `wecom_ability_service/application/identity_contact/queries.py`（如需微调）
- `wecom_ability_service/application/identity_contact/commands.py`（如需微调）
- `tests/test_identity_application_contract.py`（如需补强）
- `tests/test_api.py`
- `tests/test_http_registration_contract.py`（如需冻结 registration）

### 5.3 本 PR 内要完成的切换

- `UpsertExternalContactIdentityCommand`
- `ReplaceFollowUsersCommand`
- `RefreshExternalContactIdentityOwnerCommand`
- `MarkExternalContactIdentityStatusCommand`
- `MarkExternalContactFollowUserStatusCommand`
- `CountExternalContactIdentityMapsQuery`
- `GetPrimaryFollowUserUseridQuery`（admin support 仍在读 primary owner 时）

### 5.4 明确允许暂留的 caller 侧副作用

- `background_jobs.py`
  - `upsert_contacts`
  - `customer_pulse` 重算
  - `automation_conversion` 二维码处理
  - `schedule_user_ops_auto_assign_class_term_job`
- `sync_support.py`
  - contacts upsert
  - tag snapshot 更新/清理
- `admin_support.py`
  - tag snapshot 更新/清理
  - class-user management 读模型拼装

### 5.5 风险点

- callback / sync / admin support 3 条链路对 owner refresh 的依赖口径必须保持一致
- 如果在 PR 4 内顺手把非 identity 副作用并进 command，会把 PR 做成不可回滚的大改

### 5.6 必跑测试

- `tests/test_identity_application_contract.py`
- `tests/test_http_registration_contract.py`
- `tests/test_service_layer_layout.py`
- `tests/test_refactor_guardrails.py`
- `tests/test_api.py` 中 callback / sync / admin support 的 identity 用例

### 5.7 回滚方式

- 各 caller 文件独立回滚
- application contract 保留不动，只回滚 caller cutover

## 6. 不进入的范围

整个 identity 三个 PR 都不进入：

- `class_user` 写路径改造
- `user_ops` lead pool / deferred jobs 改造
- `routing_config` 保存链路改造
- `questionnaire`、`automation_conversion`、`customer_pulse` 内部模块拆分
- schema / SQL migration

## 7. 推荐边界结论

推荐边界固定为：

1. PR 2 只建 contract 和 tests，不切 caller。
2. PR 3 只切 `sidebar` / `questionnaire` / `http/identity.py`。
3. PR 4 只切 `background_jobs` / `sync_support` / `admin_support`。

这个边界的好处是：

- PR 2 可零风险落地。
- PR 3 专注处理“绑定兼容行为”。
- PR 4 专注处理“callback / sync / admin support 一致性”。

不建议把 PR 3 和 PR 4 合并，否则绑定兼容问题和 callback/sync 副作用问题会同时爆开，排查成本过高。
