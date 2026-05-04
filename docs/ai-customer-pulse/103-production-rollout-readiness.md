# Customer Pulse DeepSeek 生产灰度上线就绪报告

更新日期：2026-04-11

## 1. 结论

**结论：可正式按租户灰度开启**

成立前提：

- 外部环境必须显式配置 `CUSTOMER_PULSE_TENANT_MODE=request_scoped`
- 外部环境必须显式配置 `CUSTOMER_PULSE_EXTERNAL_ENFORCE_REQUEST_SCOPED=true`
- 全局开关 `ai_customer_pulse=true` 只作为总开关；正式灰度必须同时配置 `CUSTOMER_PULSE_FLAG_POLICY_JSON`，并将 `default_enabled=false`
- 正式灰度默认只开启：
  - `summary`
  - `whyNow`
  - `evidence-backed explanation`
  - 单卡 `draftText`
  - `handoffSummary / manager explanation`
- 正式灰度默认关闭：
  - 自动发送外部消息
  - `deepseek-reasoner`
  - 低置信度建议展示
  - 大批量 AI 草稿

## 2. 本轮结论依据

### 配置与安全读取

已验证 Customer Pulse 可以通过现有系统配置链路安全读取：

- `DEEPSEEK_ENABLED`
- `DEEPSEEK_API_KEY`
- `DEEPSEEK_BASE_URL`
- `DEEPSEEK_EXECUTION_MODEL`
- `DEEPSEEK_REASONER_MODEL`
- `DEEPSEEK_TIMEOUT_SECONDS`
- `CUSTOMER_PULSE_TENANT_MODE`
- `CUSTOMER_PULSE_EXTERNAL_ENFORCE_REQUEST_SCOPED`
- `CUSTOMER_PULSE_TENANT_ACCESS_POLICY_JSON`
- `CUSTOMER_PULSE_FLAG_POLICY_JSON`
- `CUSTOMER_PULSE_DEEPSEEK_USE_REASONER`
- `CUSTOMER_PULSE_SHOW_LOW_CONFIDENCE_SUGGESTIONS`

校验结果：

- `DEEPSEEK_API_KEY` 在 settings snapshot 中被掩码，不会页面回显明文
- `DEEPSEEK_EXECUTION_MODEL` 读取为 `deepseek-chat`
- `CUSTOMER_PULSE_DEEPSEEK_USE_REASONER=false`
- 没有发现 `api_key / base_url / model` 的硬编码

### 部署级 smoke

本轮使用隔离的临时 SQLite 配置库模拟正式部署配置，不污染当前工作区本地数据库；真实模型调用使用一次性测试 key，未打印 secret。

关键结果：

- `config.masked_api_key=True`
- `config.execution_model=deepseek-chat`
- `config.reasoner_enabled=false`
- `request_scoped.missing_tenant_status=403`
- `request_scoped.missing_tenant_code=tenant_context_required`
- `live.recompute_status=200`
- `live.ai_status=accepted`
- `live.provider=deepseek`
- `live.model=deepseek-chat`
- `live.has_summary=True`
- `live.has_why_now=True`
- `live.has_evidence_refs=True`
- `live.has_draft=True`
- `live.has_handoff=True`
- `preview.status=200`
- `execute.status=200`
- `fallback.status=200`
- `fallback.ai_status=fallback`
- `fallback.reason=provider_error`
- `guard.misconfigured_status=503`
- `guard.misconfigured_code=tenant_mode_misconfigured`
- `tenant_c.status=403`
- `tenant_c.code=feature_disabled`
- `kill_switch.status=403`
- `kill_switch.code=feature_disabled`

这说明：

- 真实 DeepSeek 已可在部署配置下接管 Customer Pulse 生成链路
- provider 不可用时能自动回退，不阻塞主流程
- 外部环境误配成 `legacy_internal` 时，不会静默回落，而是显式拒绝
- tenant 级灰度名单与 tenant 级 kill switch 已可用

## 3. 最小灰度方案

推荐首批灰度策略：

- 全局：
  - `ai_customer_pulse=true`
  - `CUSTOMER_PULSE_TENANT_MODE=request_scoped`
  - `CUSTOMER_PULSE_EXTERNAL_ENFORCE_REQUEST_SCOPED=true`
  - `CUSTOMER_PULSE_DEEPSEEK_USE_REASONER=false`
  - `CUSTOMER_PULSE_SHOW_LOW_CONFIDENCE_SUGGESTIONS=false`
- 灰度名单：
  - `CUSTOMER_PULSE_FLAG_POLICY_JSON.default_enabled=false`
  - 仅在 `tenants` 节点中为目标 tenant 配 `enabled=true`
- 推荐首批 tenant 数量：
  - 1 到 2 个 tenant
- 推荐首批能力：
  - 卡片 `summary / whyNow / evidence-backed explanation`
  - 单卡回复草稿 `draftText`
  - `handoffSummary / manager explanation`
- 明确不启用：
  - 自动发送
  - reasoner
  - 低置信度建议展示
  - 大批量 AI 草稿

示例策略：

```json
{
  "default_enabled": false,
  "tenants": {
    "tenant-a": { "enabled": true },
    "tenant-b": { "enabled": true }
  }
}
```

## 4. Kill Switch 与回滚

### 一级回滚：tenant 级 kill switch

- 在 `CUSTOMER_PULSE_FLAG_POLICY_JSON` 中将目标 tenant 设为 `enabled=false`
- 验证结果：本轮 smoke 中 `kill_switch.status=403`，`kill_switch.code=feature_disabled`

### 二级回滚：全局关闭

- 将 `ai_customer_pulse=false`
- 所有 tenant 立即停止入口与 API 能力

### 三级回滚：保留规则层，关闭真实模型

- 将 `DEEPSEEK_ENABLED=false`
- 系统保留 rule-based snapshot / action card 能力，AI 生成退回 fallback

### 环境防错保护

- 将 `CUSTOMER_PULSE_EXTERNAL_ENFORCE_REQUEST_SCOPED=true`
- 如果外部环境仍误配为 `legacy_internal`，系统返回：
  - `503`
  - `tenant_mode_misconfigured`

## 5. 监控项与阈值建议

已确认 stats API 可观测以下最小指标：

- `ai_success`
- `ai_error`
- `fallback_count`
- `unauthorized_denied`
- `cross_tenant_denied`
- `draft_preview_started`
- `draft_confirmed`
- `writeback_success`

本轮 smoke 结果：

- `stats_a.ai_success=1`
- `stats_a.ai_error=1`
- `stats_a.fallback_count=1`
- `stats_a.unauthorized_denied=1`
- `stats_a.draft_preview_started=2`
- `stats_a.draft_confirmed=1`
- `stats_a.writeback_success=1`
- `stats_b.cross_tenant_denied=1`

建议阈值：

- `ai_error_rate > 10%`：告警
- `fallback_rate > 20%`：人工排查 provider / prompt / 网络
- `unauthorized_denied` 持续增长：排查 RBAC 配置或错误接入
- `cross_tenant_denied > 0`：安全关注，确认是否存在越权探测
- `draft_preview_started` 高但 `draft_confirmed` 低：排查建议质量与话术可信度
- `writeback_success_rate < 95%`：暂停扩大灰度

## 6. 运行命令

质量门：

```bash
./.venv310/bin/python scripts/run_lint.py
./.venv310/bin/python scripts/run_typecheck.py
./.venv310/bin/python scripts/run_build.py
./.venv310/bin/python -m pytest -q tests/test_customer_pulse_inbox.py
make check
```

部署级 smoke：

```bash
DEEPSEEK_SMOKE_KEY=*** ./.venv310/bin/python - <<'PY'
# 使用隔离临时数据库写入 app_settings
# 验证配置读取、tenant 灰度、request-scoped 强约束、
# 真实 DeepSeek 调用、fallback、kill switch、stats 计数
PY
```

## 7. 测试结果

- `lint`：通过
- `typecheck`：通过
- `build`：通过
- `tests/test_customer_pulse_inbox.py`：`42 passed`
- `tests/test_customer_pulse_quality_gates.py`：`1 passed`
- `make check`：通过
- 真实 DeepSeek 部署级 smoke：通过

## 8. 本轮改动文件

- `wecom_ability_service/domains/customer_pulse/access.py`
- `wecom_ability_service/domains/customer_pulse/service.py`
- `wecom_ability_service/infra/settings.py`
- `wecom_ability_service/domains/admin_config/service.py`
- `tests/test_customer_pulse_inbox.py`
- `docs/ai-customer-pulse/103-production-rollout-readiness.md`

## 9. 关键实现变化

### 外部环境强制 request-scoped

新增配置：

- `CUSTOMER_PULSE_EXTERNAL_ENFORCE_REQUEST_SCOPED`

行为：

- 当该开关为 `true` 且 `CUSTOMER_PULSE_TENANT_MODE != request_scoped` 时
- 所有 Customer Pulse 请求显式失败
- 不再允许外部环境偷偷落回 `legacy_internal`

### 生产期监控补齐

新增 / 暴露指标：

- `ai_success`
- `fallback_count`
- `draft_preview_started`

这些指标已进入 Customer Pulse stats API，并在 smoke 中得到实测计数。

### 安全默认值

将低置信度建议展示的代码默认值改为关闭：

- `CUSTOMER_PULSE_SHOW_LOW_CONFIDENCE_SUGGESTIONS=false`

这样即使部署时漏配，也不会默认把低置信度建议暴露给外部 tenant。

## 10. 风险清单

### 风险 1：目标正式环境仍需写入自己的持久化配置

本轮 smoke 使用的是隔离临时配置库，验证的是代码和配置链路，不是直接修改正式环境。

影响：

- 上线前仍需在目标环境的 `app_settings` 或等价配置源中写入真实的 `DEEPSEEK_*` 与 Customer Pulse 灰度配置

### 风险 2：tenant policy 配置错误会导致访问被拒绝

如果 `owner_userids / member_userids / internal_roles` 配错，表现会是：

- recompute 被拒绝
- 列表页被拒绝
- internal API 被拒绝

这属于安全拒绝，不属于静默越权；但实施时要准备标准模板。

### 风险 3：provider 波动会抬高 fallback

当前 fallback 已成立，不会卡死主流程；但如果正式环境网络抖动或 provider 配额异常，`fallback_count` 会升高。

建议：

- 首批 tenant 先盯 3 到 5 天
- 以 `ai_success / fallback_count / draft_confirmed` 联合判断是否扩容

## 11. 默认开启项 / 默认关闭项

正式灰度默认开启：

- `summary`
- `whyNow`
- `evidence-backed explanation`
- 单卡 `draftText`
- `handoffSummary / manager explanation`

正式灰度默认关闭：

- 自动发送任何外部消息
- `deepseek-reasoner`
- 低置信度建议展示
- 大批量 AI 草稿

