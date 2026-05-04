# AI Customer Pulse 外放灰度与运维说明

更新时间：2026-04-11

## 目标

这份文档面向产品、运营、实施、测试和发布负责人。目标不是解释功能，而是说明 Customer Pulse 现在如何灰度开启、如何验证、如何盯指标、如何止损回滚。

## 1. 开关体系

Customer Pulse 当前是三层开关，命中顺序固定：

1. `ai_customer_pulse`
   - 全局总开关。
   - `false` 时页面、API、后台任务全部停止。
2. `CUSTOMER_PULSE_FLAG_POLICY_JSON`
   - 在全局开启后继续做租户/角色/用户灰度。
   - 当前仓库没有独立“用户组”实体，所以本次外放支持 `tenant + role + userid`，不额外虚构 group 体系。
3. `CUSTOMER_PULSE_ALLOWED_ACTION_TYPES`
   - 在功能已开放时继续限制可执行动作类型。

### 推荐灰度配置

```json
{
  "default_enabled": false,
  "tenants": {
    "tenant-alpha": {
      "enabled": true,
      "roles": {
        "sales": true,
        "ops": true,
        "admin": true
      }
    },
    "tenant-beta": {
      "enabled": true,
      "roles": {
        "ops": true,
        "admin": true,
        "sales": false
      }
    }
  }
}
```

### 生效规则

- 全局开关优先级最高。
- tenant 级 `enabled` 决定当前租户是否进入灰度。
- tenant 内再按 `userids`、`roles` 覆盖。
- `userids` 优先级高于 `roles`。
- 不命中任何灰度规则时，回退到 `default_enabled`。
- `legacy_internal` 可单独配置，不会偷偷 fallback 到 request-scoped。

## 2. 依赖项清单

### Tenant Mode

- 必须明确 `CUSTOMER_PULSE_TENANT_MODE`
- 对外 SaaS 一律使用 `request_scoped`
- `legacy_internal` 只保留给内部兼容环境

### RBAC

- 必须配置 `CUSTOMER_PULSE_TENANT_ACCESS_POLICY_JSON`
- 页面、列表、widget、evidence、动作、反馈都继续复用现有 `owner_role_map + tenant policy`
- 对外外放前，至少确认租户 `owner_userids`、`member_userids`、`viewer_roles`、`operator_roles`、`internal_roles` 全部齐备

### Audit

- 依赖 `admin_operation_logs`
- 依赖 `customer_pulse_execution_logs`
- 依赖 `customer_pulse_activity_logs`
- evidence 查看、动作执行、反馈、越权拒绝、跨租户探测都必须留痕

### Metrics

- 依赖 `customer_pulse_metric_events`
- 当前统计接口：
  - `GET /api/admin/customer-pulse/stats?days=7`
  - `GET /api/internal/customer-pulse/stats?days=7`

### Seed / Demo Data

- 单租户 demo：
  - `python scripts/seed_customer_pulse_demo.py --init-db --write-settings`
- 双租户 demo：
  - `python scripts/seed_customer_pulse_demo.py --init-db --write-settings --dual-tenant`

### 告警

- 当前最小告警入口就是 stats API
- 建议外部监控周期拉取以下口径：
  - `card_exposed`
  - `action_executed`
  - `draft_confirmed`
  - `writeback_success`
  - `writeback_failed`
  - `ai_error`
  - `unauthorized_denied`
  - `cross_tenant_denied`

## 3. 最小运营看板

Customer Pulse 收件箱页已经内置最小看板，展示两组信息：

- 灰度与依赖
  - 灰度状态
  - tenant mode
  - RBAC 状态
  - 审计 / 指标状态
- 最近 7 天关键指标
  - 曝光
  - 执行率
  - 草稿确认率
  - 写回成功率
  - AI 错误率
  - 越权拒绝次数
  - 跨租户拒绝次数

## 4. 灰度顺序

推荐顺序：

1. 内部 `legacy_internal` 验证
   - 确认 lint/typecheck/test/build/check 全过
   - 确认 demo 数据能产卡、能执行、能回写
2. 单租户 request-scoped
   - 只开 `ops/admin`
   - 验证 tenant context、RBAC、audit、stats API
3. 单租户 request-scoped 扩到 `sales`
   - 先只开放 `generate_reply_draft`
   - 指标稳定后再放开任务/阶段/标签/提醒
4. 双租户并存验证
   - 确认跨租户卡片、evidence、execution log、timeline 全部拒绝
   - 确认 stats API 按 tenant 维度隔离
5. 小流量 SaaS 外放
   - 按 tenant 批次放量
   - 每次放量后至少观察 1 个工作日

## 5. Tenant 开通流程

实施或运维开通一个新 tenant 时，按这个顺序做：

1. 在 `CUSTOMER_PULSE_TENANT_ACCESS_POLICY_JSON` 中补 tenant 策略
2. 在 `CUSTOMER_PULSE_FLAG_POLICY_JSON` 中给 tenant 配 `enabled=true`
3. 先只放 `ops/admin` 角色
4. 使用 request-scoped 头验证：
   - `X-Tenant-Key`
   - `X-Admin-Userid`
   - `X-Admin-Role`
5. 调用：
   - `GET /api/admin/customer-pulse/stats?days=7`
   - `GET /api/admin/customer-pulse`
6. 确认：
   - 收件箱能打开
   - stats API 能返回 tenant scoped 数据
   - evidence 和动作按权限受控
7. 再逐步开放 `sales`

## 6. 风险开关

### 一级止损

- `ai_customer_pulse=false`
- 效果：全量关闭

### 二级止损

- 在 `CUSTOMER_PULSE_FLAG_POLICY_JSON` 里把目标 tenant `enabled=false`
- 效果：单租户快速摘流量

### 三级止损

- 收紧 `CUSTOMER_PULSE_ALLOWED_ACTION_TYPES`
- 推荐保底值：
  - `generate_reply_draft`
- 效果：只保留安全草稿，不允许直接落任务/阶段/标签/提醒

### 四级止损

- `CUSTOMER_PULSE_SHOW_LOW_CONFIDENCE_SUGGESTIONS=false`
- 效果：隐藏低置信度建议，减少误触达

## 7. 回滚方案

最小回滚路径：

1. 先关 tenant 灰度
2. 观察 stats API 中曝光、执行、拒绝计数是否回落
3. 如仍有异常，再关全局 `ai_customer_pulse`
4. 必要时把 `CUSTOMER_PULSE_TENANT_MODE` 切回 `legacy_internal`

数据层回滚说明：

- `customer_pulse_*` 日志表都是 append-only，关闭功能不要求删数据
- 已生成草稿仍留在 `outbound_tasks`，不会自动外发
- 已落地的阶段/标签/提醒/任务按业务现有流程人工修正或使用撤销窗口

## 8. 常见故障排查

### 页面入口消失

- 检查 `ai_customer_pulse`
- 检查 `CUSTOMER_PULSE_FLAG_POLICY_JSON`
- 检查当前角色是否命中 tenant policy 的 `viewer_roles`

### 页面 403

- 检查 `X-Tenant-Key`
- 检查 `X-Admin-Userid`
- 检查 `X-Admin-Role`
- 检查 `CUSTOMER_PULSE_TENANT_ACCESS_POLICY_JSON`

### API 返回 `feature_disabled`

- 全局开关未开，或 tenant / role / userid 没进灰度
- 用 stats API 中的 `feature_gate.reason` 定位

### 看得到卡片但不能执行

- 检查 `operator_roles`
- 检查细粒度权限是否覆盖动作：
  - `generate_reply_draft`
  - `create_followup_task`
  - `update_followup_segment`
  - `update_tags`
  - `set_followup_reminder`

### evidence 展不开

- 检查 `evidence_view`
- 检查 evidence 原始来源记录是否仍在访问边界内

### stats API 指标异常低

- 先确认是否走了 `/api/admin/customer-pulse`
- 再检查是否只用了 internal API
- internal API 默认 `track_metrics=false`，适合后台任务，不适合作为页面曝光口径

## 9. QA / 产品复验建议

双 tenant demo 数据建议至少复验这些路径：

1. `tenant-alpha` 销售能看到并执行自己的卡
2. `tenant-beta` 运营能看到自己的 tenant 卡
3. `tenant-beta` 无法读取 `tenant-alpha` 的卡片详情
4. 无权限角色会被拒绝，且 stats API 累加 `unauthorized_denied`
5. 跨租户探测会留下 `cross_tenant_denied`

## 10. 当前结论

在以下前提同时满足时，可判定达到“多租户 SaaS 外放最低标准”：

- `request_scoped` tenant mode 已开启
- tenant access policy 已配置
- `CUSTOMER_PULSE_FLAG_POLICY_JSON` 已配置并完成灰度验证
- stats API 能返回隔离后的 counts/rates
- 完整质量门通过

如果其中任一项不满足，只能算“内部灰度可用”，不能算可外放。
