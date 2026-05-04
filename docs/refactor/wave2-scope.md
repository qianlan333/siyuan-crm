# Wave 2 Scope

日期：2026-04-19

## 1. Wave 2 目标

Wave 2 的目标不是继续收口 read 入口，而是把仍然散落在 legacy domain / `services.py` / controller / callback job 中的 write path 重新归边。

本轮只聚焦 4 条主线：

1. `identity`
   - 统一 `person_id` / `external_userid` / `openid` / `unionid` / follow-user 绑定写路径
2. `class_user`
   - 统一 `class_user_status_*` 当前状态、历史、同步结果写路径
3. `user_ops`
   - 统一 `user_ops_lead_pool_*`、deferred jobs、批量导入、class-term 回填等写路径
4. `routing_config`
   - 统一 `owner_role_map`、`routing_rule_config` 的写入口和审计入口

Wave 2 交付的核心成果应该是：

- 为上述 4 个 context 建立正式 application write/read API
- 把 controller / callback / admin action / background job 从 direct domain / `services.py` 写入口上摘下来
- 把跨 context 副作用从“散落的 service 调用链”变成“显式 application command”
- 缩小 `services.py` 的剩余兼容面

## 2. 涉及 context

### 2.1 Identity

关注的数据和动作：

- `external_contact_bindings`
- `wecom_external_contact_identity_map`
- `wecom_external_contact_follow_users`
- `person_id` / `mobile` / `openid` / `unionid` 绑定
- owner 刷新与 follow-user 主从关系

### 2.2 User Ops

关注的数据和动作：

- `user_ops_lead_pool_current`
- `user_ops_lead_pool_history`
- `user_ops_deferred_jobs`
- 体验课导入、激活状态导入、手机号班期导入
- class-term 回填与自动分配

### 2.3 Class User

关注的数据和动作：

- `class_user_status_current`
- `class_user_status_history`
- `wecom_tag_sync_status` / `wecom_tag_sync_error`
- sidebar 手工改状态
- marketing automation 对班级状态的变更

### 2.4 Routing Config

关注的数据和动作：

- `owner_role_map`
- `routing_rule_config`
- admin config 保存动作
- routing 决策所依赖的 owner-role / rule 读模型

## 3. 不进入的范围

Wave 2 明确不进入：

- `questionnaire` 内部拆分
- `automation_conversion` 内部拆分
- `customer_pulse` 内部拆分
- `followup_orchestrator` 内部拆分
- `mcp_adapter.py` 再次收口
- `http/customer_center.py` / `http/customer_timeline.py` / `http/customer_automation.py` 的 Wave 1 read contract 重新调整
- schema / SQL migration
- UI 设计或页面重做

说明：

- 如果某个 Wave 2 command 暂时还要调用 `questionnaire` / `automation_conversion` / `customer_pulse` / `followup_orchestrator` 的 legacy domain service，可以保留，但那不是本轮要拆的内部边界。
- 本轮要解决的是“写入口归谁管、跨 context 怎么调用”，不是“一次性拆干净所有内部模块”。

## 4. 风险清单

### 4.1 Binding 副作用过多

`bind_mobile_to_external_contact` 目前不只是 identity 绑定，还会：

- 解析 owner
- 同步 third-party user id
- 合并 lead pool

这意味着 Wave 2 若直接把它视作单一 domain 写函数，会继续保留跨 context 隐耦合。

### 4.2 Class User 写路径跨 context 触发

`apply_class_user_status_change` 当前来自：

- admin sidebar 手工改标签
- marketing automation 转化流
- user_ops 相关流程

如果不先定义正式 application command，很容易继续出现“任何模块都能直接改班级状态”的情况。

### 4.3 User Ops 写入口既多又杂

`user_ops` 目前既有：

- 单条写
- 批量导入
- deferred jobs
- callback 驱动调度
- sidebar class-term patch

这类写入口如果不先分类，就会把 application 层写成第二个 `services.py`。

### 4.4 Routing 写入口 owner 不清

当前 `owner_role_map` / `routing_rule_config` 的保存动作落在 `domains/admin_config/service.py`，实际 owner 又在 `domains/routing_config/`。

如果 Wave 2 不先把“配置 UI 上下文”和“routing domain owner”分开，后续边界仍会混。

### 4.5 兼容测试和 monkeypatch 锚点

`services.py` 里仍有：

- `_user_ops_contact_client`
- `_resolve_third_party_user_id_by_mobile`

这类符号是现有测试与 DI 的锚点。Wave 2 迁移时必须先给新 adapter 层留替代锚点，再缩 shim。

## 5. 建议拆分顺序

建议顺序：

1. `identity` write API
   - 先收 `bind_mobile_to_external_contact`
   - 再收 callback/sync 用的 identity map / follow-users 写入口
2. `class_user` write API
   - 先收 `apply_class_user_status_change`
   - 再收 `update_class_user_status_sync_result`
3. `routing_config` write/read API
   - 先把 `save_owner_role_setting` / `save_routing_rule_setting` 从 `admin_config` 提升到正式 application API
4. `user_ops` write API
   - 先收 `upsert_user_ops_lead_pool_member` / `write_user_ops_lead_pool_history`
   - 再收 deferred job / backfill / import / sidebar class-term patch
5. 调用方切换与 `services.py` 缩面
   - controller
   - background job
   - admin action
   - callback runtime

这个顺序的原因：

- `user_ops` 依赖 `identity` 与 `class_user` 的副作用最重，放在后面能减少返工。
- `routing_config` 相对独立，适合作为中间一个低风险切面。
- 等 application write API 稳定后，再回头继续缩 `services.py`，不会把兼容层改来改去。

## 6. Wave 2 建议完成标准

Wave 2 完成时至少应满足：

- `identity` / `class_user` / `user_ops` / `routing_config` 都有正式 application write/read API
- 相关 controller / callback / admin action 不再直接调用这些 context 的 legacy domain write 函数
- `services.py` 不再承担这 4 个 context 的主要写入口
- 新增 guardrail 能阻止这些 context 的新写逻辑继续从 shim 或 controller 旁路进入
