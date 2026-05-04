# Customer Pulse 首批 tenant 7 天灰度观察 Runbook

更新日期：2026-04-11

## 1. 观察周期开始方式

当前仓库已提供观察周期状态文件：

- [observation-state.json](/Users/qianlan/Downloads/aicrm-new-codex-1/docs/ai-customer-pulse/observation-state.json)

当前状态：

- `status=awaiting_real_whitelist_tenants`
- 尚未绑定真实白名单 tenant

绑定真实白名单 tenant 并开始观察：

```bash
./.venv310/bin/python scripts/run_customer_pulse_observation.py start --tenant <tenant_a> --tenant <tenant_b>
```

要求：

- 只允许绑定 1 到 2 个真实白名单 tenant
- tenant 必须已经出现在 `CUSTOMER_PULSE_FLAG_POLICY_JSON.tenants` 且 `enabled=true`
- 未绑定真实 tenant 前，不得把观察周期视为已经开始

## 2. 白名单 tenant 名单记录方式

名单记录在状态文件：

- `observed_tenants`

开始观察后会同时记录：

- `observation_started_at`
- `days_observed`
- `last_daily_run_at`
- `last_daily_report_path`
- `rollback_incident_detected`
- `rollback_incident_notes`

## 3. 每日执行命令

### 每日观察

```bash
./.venv310/bin/python scripts/run_customer_pulse_observation.py daily
```

执行结果：

- 生成当日 tenant 级日报
- 保存到 `docs/ai-customer-pulse/observation-daily/YYYY-MM-DD.md`
- 更新状态文件中的累计天数与最后执行时间
- 到第 7 天时自动触发 verdict 生成

### 查看当前状态

```bash
./.venv310/bin/python scripts/run_customer_pulse_observation.py status
```

### 手动生成第 7 天结论

```bash
./.venv310/bin/python scripts/run_customer_pulse_observation.py verdict
```

## 4. 每日检查项

每日必须检查：

- `ai_error_rate`
- `fallback_rate`
- `draft_confirm_rate`
- `writeback_success_rate`
- `unauthorized_denied`
- `cross_tenant_denied`

日报脚本会输出 tenant 维度累计计数；7 天 review 脚本会输出：

- 7 天累计
- 日均
- 趋势
- 是否满足扩容门槛
- tenant 分类

## 5. 异常升级路径

### 一般异常

满足任一条件，进入观察但不扩容：

- `ai_error_rate > 10%`
- `fallback_rate > 20%`
- `writeback_success_rate < 95%`
- `draft_confirm_rate < 10%`

### 回滚级事故

满足任一条件，必须记录事故并直接输出回滚结论：

- 跨租户泄露
- evidence 越权泄露
- 外部消息绕过草稿预览直接发送
- 外部环境可绕过 `request-scoped`
- audit / execution log 丢失导致无法追责

记录回滚级事故：

```bash
./.venv310/bin/python scripts/run_customer_pulse_observation.py incident --set --note "具体事故说明"
```

清除误报：

```bash
./.venv310/bin/python scripts/run_customer_pulse_observation.py incident --clear --note "误报已排除"
```

## 6. 第 7 天复盘方式

第 7 天自动或手动执行：

```bash
./.venv310/bin/python scripts/run_customer_pulse_observation.py verdict
```

输出文件：

- [108-seven-day-verdict.md](/Users/qianlan/Downloads/aicrm-new-codex-1/docs/ai-customer-pulse/108-seven-day-verdict.md)

复盘内容包括：

- 每个 tenant 的 7 天累计
- 日均
- 趋势
- 是否达成扩容门槛
- 是否触发暂停 / 回滚门槛
- 最终结论

## 7. 结论上限规则

必须遵守：

- 如果数据源不是已验证生产数据，结论上限只能是 `继续维持当前灰度规模`
- 只有真实白名单 tenant 且连续 7 天满足门槛，才允许输出 `可扩到下一批 tenant`
- 一旦记录回滚级事故，最终结论必须为 `立即回滚`

