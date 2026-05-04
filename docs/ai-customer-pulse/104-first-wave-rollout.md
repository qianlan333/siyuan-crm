# Customer Pulse 首批租户灰度执行方案

更新日期：2026-04-11

## 1. 首批灰度目标

目标不是追求覆盖面，而是验证以下三件事是否同时成立：

1. 真实 DeepSeek 在正式部署配置下可稳定产出 `summary / whyNow / evidence-backed explanation / 单卡 draft / handoff`
2. 首批 tenant 在真实业务场景下，草稿预览与写回链路可用，且不会削弱 tenant / RBAC / audit / draft preview 安全边界
3. 7 天内可拿到足以支撑下一批扩容的行为数据，而不是只看到“功能能跑”

## 2. 白名单 tenant 选择标准

首批只建议 1 到 2 个 tenant，且必须同时满足：

- 已完成 `request-scoped` 接入，不存在 legacy internal 依赖
- `tenant policy` 完整，至少包含：
  - `owner_userids`
  - `member_userids`
  - `viewer_roles`
  - `operator_roles`
  - `internal_roles`
- 有稳定的 owner / ops 使用人群，能在 7 天内产生足够卡片与草稿操作
- 能接受灰度期内以 `fallback` 和人工确认为主，不要求 AI 全量接管
- 能配合观察安全拒绝、误判与草稿确认率

不建议进入首批灰度的 tenant：

- owner / team 关系长期不稳定
- tenant policy 尚未定稿
- 当前会话/写回链路本身不稳定
- 希望默认开启低置信度建议或自动外发

## 3. 默认开启项

首批灰度仅开启：

- `summary`
- `whyNow`
- `evidence-backed explanation`
- 单卡 `draftText`
- `handoffSummary / manager explanation`

## 4. 默认关闭项

首批灰度默认关闭：

- 自动发送任何外部消息
- `CUSTOMER_PULSE_DEEPSEEK_USE_REASONER`
- `CUSTOMER_PULSE_SHOW_LOW_CONFIDENCE_SUGGESTIONS`
- 大批量 AI 草稿
- 任何绕过草稿预览/人工确认的动作

## 5. 白名单配置要求

正式环境必须满足：

```json
{
  "default_enabled": false,
  "tenants": {
    "tenant-a": { "enabled": true },
    "tenant-b": { "enabled": true },
    "tenant-c": { "enabled": false }
  }
}
```

要求：

- `default_enabled=false`
- 只对白名单 tenant 配 `enabled=true`
- 非白名单 tenant 默认不可见、不可调用
- 如果 tenant 需要角色级二次收敛，可在 tenant 节点下加 `roles / userids`

## 6. tenant policy 检查项

每个首批 tenant 上线前逐项确认：

- `CUSTOMER_PULSE_TENANT_MODE=request_scoped`
- `CUSTOMER_PULSE_EXTERNAL_ENFORCE_REQUEST_SCOPED=true`
- `CUSTOMER_PULSE_TENANT_ACCESS_POLICY_JSON` 中存在该 tenant
- `owner_userids` 覆盖实际 owner
- `member_userids` 覆盖实际页面访问人与 internal API 调用人
- `viewer_roles` 与 `operator_roles` 没有误放开
- `internal_roles` 只包含允许触发内部作业的角色
- 灰度 tenant 的 `enabled=true`
- 非白名单 tenant 的 `enabled` 缺省或显式为 `false`

## 7. 回滚方式

一级回滚：

- 在 `CUSTOMER_PULSE_FLAG_POLICY_JSON` 中把目标 tenant 设为 `enabled=false`

二级回滚：

- `DEEPSEEK_ENABLED=false`
- 保留 rule-based card，不再走真实模型

三级回滚：

- `ai_customer_pulse=false`

防错保护：

- 若外部环境误配 `legacy_internal`，系统应直接返回 `tenant_mode_misconfigured`

## 8. 首批 tenant 建议规则

建议首批 tenant 规则：

- 1 个以销售 owner 为主、会话量稳定的 tenant
- 1 个以 ops / 交付协同较多、handoff 场景明显的 tenant
- 两个 tenant 都必须能在 7 天内提供：
  - 真实卡片曝光
  - 草稿预览
  - 草稿确认
  - 至少一部分写回成功

## 9. 扩容门槛

满足以下条件，可从 1 到 2 个 tenant 扩到 5 到 10 个 tenant：

- 连续 7 天 `ai_error_rate <= 10%`
- 连续 7 天 `fallback_rate <= 20%`
- `draft_confirm_rate >= 20%`
- `writeback_success_rate >= 95%`
- 无持续增长的 `unauthorized_denied`
- 无新增真实越权事故；`cross_tenant_denied` 仅表现为拦截，不是数据泄露
- 首批 tenant 没有因 AI 输出导致业务方要求关闭入口

## 10. 暂停 / 回滚门槛

满足任一条件，暂停扩容：

- `ai_error_rate > 10%` 且连续 2 天不回落
- `fallback_rate > 20%` 且连续 2 天不回落
- `writeback_success_rate < 95%`
- `draft_confirm_rate < 10%` 且伴随明显负面反馈
- `unauthorized_denied` 或 `cross_tenant_denied` 出现异常增长，需要排查接入或权限配置

满足任一条件，立即回滚：

- 发现真实跨租户泄露
- 发现 evidence 越权泄露
- 发现外部消息绕过草稿预览直接发送
- 发现外部环境可绕过 `request-scoped`
- 发现 audit / execution log 丢失，无法追责

