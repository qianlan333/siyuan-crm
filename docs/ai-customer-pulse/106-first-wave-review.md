# Customer Pulse 首批 tenant 7 天灰度复盘

更新日期：2026-04-11

## 1. 复盘范围

本报告基于现有 rollout report 脚本新增的 `review` 模式生成，口径保持不变，只补充：

- 7 天累计
- 日均
- 趋势变化
- `ai_error_rate`
- `fallback_rate`
- `draft_confirm_rate`
- `writeback_success_rate`
- tenant 分类
- 是否满足扩容门槛

本轮不修改扩容或回滚硬门槛。

## 2. 执行命令

```bash
./.venv310/bin/python scripts/render_customer_pulse_rollout_report.py --mode review --days 7 --format markdown
```

## 3. 当前脚本输出

本次在当前工作区直接执行，得到的复盘输出如下：

```markdown
# Customer Pulse 首批 tenant 7 天灰度复盘

- 生成时间：2026-04-11 20:09:51
- 复盘窗口：7 天
- 数据源类型：workspace_local_sqlite
- 数据源说明：当前使用本地 SQLite 数据源，不能自动视为已验证的 7 天真实生产数据。
- production_evidence_verified：False
- 白名单 tenant：(none)

## 最终结论

继续维持当前灰度规模
```

## 4. 当前数据结论

当前仓库内可验证的是：

- 复盘口径、趋势计算和 tenant 分类逻辑已落地
- 脚本可正常运行
- 当数据源不是已验证生产数据时，结论会自动被压到保守档位

当前仓库内**不可验证**的是：

- 首批 1 到 2 个 tenant 的真实生产 7 天连续数据
- 基于真实生产数据的 tenant 级扩容结论

因此，本轮报告不能把任何结论提升到“可扩到下一批 tenant”。

## 5. tenant 复盘口径

### 每个 tenant 输出项

- 7 天累计：
  - `ai_success`
  - `ai_error`
  - `fallback_count`
  - `draft_preview_started`
  - `draft_confirmed`
  - `writeback_success`
  - `writeback_failed`
  - `unauthorized_denied`
  - `cross_tenant_denied`
- 日均：
  - 上述核心事件按 7 天平均
- 趋势：
  - `draft_preview_started`
  - `draft_confirmed`
  - `fallback_count`
- 比率：
  - `ai_error_rate = ai_error / (ai_success + ai_error)`
  - `fallback_rate = fallback_count / (ai_success + fallback_count)`
  - `draft_confirm_rate = draft_confirmed / draft_preview_started`
  - `writeback_success_rate = writeback_success / (writeback_success + writeback_failed)`

### tenant 分类规则

- `健康，可扩容参考`
  - 仅在有已验证生产数据，且连续 7 天满足全部扩容门槛时成立
- `观察中，继续当前灰度`
  - 默认保守档位
  - 当前数据源不是已验证生产数据时，一律落在这一类
- `风险，建议暂停或回滚`
  - 命中严重安全或越权风险时成立

## 6. 扩容门槛复核

扩容门槛维持不变：

- 连续 7 天 `ai_error_rate <= 10%`
- 连续 7 天 `fallback_rate <= 20%`
- `draft_confirm_rate >= 20%`
- `writeback_success_rate >= 95%`
- 无未解决安全事件

## 7. 回滚门槛复核

立即回滚条件维持不变：

- 跨租户泄露
- evidence 越权泄露
- 外部消息绕过草稿预览直接发送
- 外部环境可绕过 `request-scoped`
- audit / execution log 丢失导致无法追责

## 8. 当前判断

当前脚本和口径已经足以在真实生产环境做首批 tenant 的 7 天灰度复盘。

但基于当前工作区可访问的数据，只能得出一个结论：

- 当前没有可验证的 7 天真实生产样本
- 当前结论**仅可维持当前灰度规模**

## 9. 下一步

需要在真实首批白名单 tenant 的生产数据源上，连续观察至少 7 天，并重新执行：

```bash
./.venv310/bin/python scripts/render_customer_pulse_rollout_report.py --mode review --days 7 --format markdown
```

只有在该输出基于已验证生产数据，且满足全部扩容门槛时，才允许把结论提升为“可扩到下一批 tenant”。

## 10. 最终结论

继续维持当前灰度规模

