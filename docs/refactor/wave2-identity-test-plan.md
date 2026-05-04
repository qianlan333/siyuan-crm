# Wave 2 Identity Test Plan

日期：2026-04-19

## 1. 目标

本测试计划只服务于 Wave 2 的 identity 主线，目标是先冻结合同，再切 wiring。

冻结重点：

- `person_id` / `external_userid` / `mobile` / `unionid` / `openid` 的解析与回填优先级
- 解绑 / 重绑后的 customer center 不串人
- 绑定时 owner / follow-user / third-party user id 的兼容行为
- questionnaire 身份回填不重复建记录
- callback / sync 写 follow-user 与 owner refresh 的一致性

本文件不新增测试代码，只说明：

- 当前已有哪些覆盖
- 哪些覆盖不足
- 建议在 PR 2 / PR 3 / PR 4 分别补哪些冻结测试

## 2. 现有覆盖盘点

| 冻结主题 | 当前已有测试 | 现状判断 |
| --- | --- | --- |
| `/api/identity/resolve` 基础 contract | `tests/contract/test_crm_contract.py::test_contract_contacts_and_identity`、`test_contract_identity_requires_locator` | 已有基础 contract 覆盖，但还没有 application contract 级测试 |
| `external_userid` / `mobile` / `unionid` 解析 | `tests/test_api.py::test_identity_resolve_supports_external_userid_and_mobile`、`test_identity_resolve_supports_unionid`、`test_identity_resolve_requires_external_userid_mobile_or_unionid` | 已覆盖 3 个 locator 的基础读路径，但没有统一优先级矩阵 |
| sidebar mobile bind 兼容行为 | `tests/test_api.py::test_sidebar_bind_mobile_fills_missing_owner_from_contacts`、`test_sidebar_bind_mobile_succeeds_when_third_party_sync_fails`、`test_sidebar_bind_mobile_force_rebind_updates_binding` | 已覆盖 owner 回退、third-party sync 降级、force rebind 三个关键兼容点 |
| questionnaire identity 回填 | `tests/test_api.py::test_external_contact_full_sync_and_identity_bind`、`test_questionnaire_mobile_submission_binds_contact_and_overwrites_old_mobile`、`test_questionnaire_mobile_submission_without_identity_still_saves_snapshot` | 已覆盖 mobile bind 和 openid 回填主路径，但未显式冻结“去重不重复建 identity map” |
| callback identity 写链 | `tests/test_api.py::test_external_contact_callback_logs_and_processes_event` | 已覆盖 callback 主路径，但 follow-user / owner refresh 一致性断言仍偏弱 |
| sync identity 写链 | `tests/test_api.py::test_external_contact_full_sync_and_identity_bind` | 已覆盖 sync 主流程，但缺“只新增/增量判断/计数 contract”冻结 |

## 3. 关键风险与缺口

### 3.1 解析优先级还没有完整冻结

当前已覆盖：

- `ResolvePersonIdentity` 的 `external_userid` / `mobile` / `unionid`
- questionnaire submit 流程里存在 `unionid` 优先于 `openid` / `external_userid` 的实际实现

当前缺口：

- 没有一组显式测试把 identity 主线的 locator 顺序写成合同
- `openid` 目前主要通过 questionnaire submit 间接覆盖，没有独立 contract test

### 3.2 “不串人”还缺一条 end-to-end 冻结

当前已覆盖：

- force rebind 会更新 binding

当前缺口：

- 没有显式断言“重绑后 customer center list/detail 看到的是新 person 绑定，而不是旧 person 残留”

### 3.3 callback / sync / admin support 的 owner refresh 一致性覆盖不足

当前已覆盖：

- callback 与 sync 主路径都在跑

当前缺口：

- 缺少统一断言：
  - follow-user 替换后 primary owner 是否刷新
  - inactive 标记后 owner 是否回退一致
  - admin support live refresh 是否与 sync/callback 口径一致

## 4. PR 2 测试计划

PR 2 目标是建立 application skeleton 与 contract tests，不切 caller。

建议新增测试文件：

- `tests/test_identity_application_contract.py`

建议冻结的最小 contract：

1. `ResolvePersonIdentityQuery`
   - 至少覆盖 `external_userid`、`mobile`、`unionid` 三类 locator
   - 明确缺 locator 时抛出与 legacy 一致的错误
2. `GetContactBindingStatusQuery`
   - 未绑定 / 已绑定两类返回结构
   - `owner_userid` 缺省时仍保留 sidebar owner fallback 行为
3. `BindExternalContactIdentityCommand`
   - mobile bind 模式委托 legacy bind
   - openid backfill 模式委托 legacy openid bind
   - 保持 `third_party_sync_status`、`lead_pool_merge` 等兼容 key
4. `ResolveExternalContactIdentityQuery`
   - `unionid` / `openid` / `external_userid` 三种 locator 至少各有一条
5. `UpsertExternalContactIdentityCommand` / `ReplaceFollowUsersCommand` / `RefreshExternalContactIdentityOwnerCommand`
   - 只验证 delegate target 与基础返回，不重写业务逻辑

PR 2 必跑：

- `tests/test_identity_application_contract.py`
- `tests/test_http_registration_contract.py`
- `tests/test_service_layer_layout.py`
- `tests/test_refactor_guardrails.py`

## 5. PR 3 测试计划

PR 3 目标是切 `sidebar`、`questionnaire`、`http/identity.py`。

建议新增或补强的冻结断言：

1. 解析优先级
   - questionnaire submit identity 查找顺序固定为：
     - `unionid`
     - `openid`
     - `external_userid`
2. 绑定兼容行为
   - owner 缺省时仍能从 contact / primary follow-user 补齐
   - third-party user id 同步失败不打断绑定主流程
   - `force_rebind=True` 时可以重绑到新 mobile / person
3. 不串人
   - 执行 rebind 后，再访问 customer center list/detail
   - 断言 person 绑定、mobile 展示、owner/follow-user 展示不会残留旧人信息
4. questionnaire 去重
   - 同一 `unionid` / `openid` 重复提交，不会重复创建 identity map
   - questionnaire submission 的 `identity_map_id` / `matched_by` 保持稳定

PR 3 主要依赖现有测试文件：

- `tests/test_api.py`
- `tests/test_customer_center_api.py`
- `tests/contract/test_crm_contract.py`

建议重点回归：

- `tests/test_api.py::test_sidebar_bind_mobile_fills_missing_owner_from_contacts`
- `tests/test_api.py::test_sidebar_bind_mobile_succeeds_when_third_party_sync_fails`
- `tests/test_api.py::test_sidebar_bind_mobile_force_rebind_updates_binding`
- `tests/test_api.py::test_identity_resolve_supports_external_userid_and_mobile`
- `tests/test_api.py::test_identity_resolve_supports_unionid`
- `tests/test_api.py::test_questionnaire_mobile_submission_binds_contact_and_overwrites_old_mobile`
- `tests/test_api.py::test_external_contact_full_sync_and_identity_bind`

## 6. PR 4 测试计划

PR 4 目标是切 `background_jobs`、`sync_support`、`admin_support`。

必须冻结的行为：

1. callback identity 写链一致性
   - `upsert identity` -> `replace follow users` -> `refresh owner`
   - 删除场景下 `mark identity status` / `mark follow-user status` / `refresh owner` 顺序不变
2. sync summary 一致性
   - `identity_map_total` 仍在输出中
   - 只新增 / 增量 sync 的 inserted / updated 统计口径不变
3. admin support live refresh 一致性
   - primary follow-user owner 回退规则不变
   - tag snapshot 清理仍跟随当前 admin support 路径
4. callback/sync/admin support 三条链路 owner refresh 口径一致

PR 4 推荐补强：

- `tests/test_api.py` 中 callback / sync / admin support 对应 identity 用例
- `tests/test_http_registration_contract.py` 如新增 route wiring 需要冻结注册不变

建议重点回归：

- `tests/test_api.py::test_external_contact_full_sync_and_identity_bind`
- `tests/test_api.py::test_external_contact_callback_logs_and_processes_event`
- 与 admin support live refresh 相关的现有用例
- `tests/test_service_layer_layout.py`
- `tests/test_refactor_guardrails.py`

## 7. 建议新增测试清单

以下是当前最值得补的 5 条冻结测试：

1. `test_identity_application_contract_resolve_person_identity_matches_legacy`
   - 文件：`tests/test_identity_application_contract.py`
   - PR：2
2. `test_questionnaire_identity_resolution_prefers_unionid_then_openid_then_external_userid`
   - 文件：`tests/test_api.py`
   - PR：3
3. `test_sidebar_rebind_does_not_leak_old_person_into_customer_center`
   - 文件：`tests/test_api.py` 或 `tests/test_customer_center_api.py`
   - PR：3
4. `test_sync_identity_refresh_keeps_owner_and_follow_user_consistent`
   - 文件：`tests/test_api.py`
   - PR：4
5. `test_admin_support_identity_refresh_matches_sync_owner_selection`
   - 文件：`tests/test_api.py`
   - PR：4

## 8. 结论

现有测试已经覆盖了 identity 主线的大部分业务主路径，但还没有把“application contract + locator 优先级 + callback/sync/admin support 一致性”冻结成独立测试层。

因此建议顺序固定为：

1. PR 2 先补 application contract tests。
2. PR 3 再切 `sidebar` / `questionnaire` / `http/identity.py`。
3. PR 4 最后切 `background_jobs` / `sync_support` / `admin_support`。
