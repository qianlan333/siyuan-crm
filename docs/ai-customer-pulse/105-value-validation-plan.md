# Customer Pulse 首批灰度业务价值验证计划

更新日期：2026-04-11

## 1. 7 天验证目标

7 天的目标不是证明 AI“很聪明”，而是验证它是否能稳定改变一线动作：

- 有稳定的卡片曝光和草稿预览
- `summary / whyNow / evidence` 能被业务方理解并接受
- 单卡 draft 能进入真实预览和确认链路
- 写回记录稳定，不破坏客户详情、任务、阶段/标签、提醒主流程
- 安全边界稳定：
  - 无跨 tenant 泄露
  - 无 evidence 越权泄露
  - 无自动发送

7 天内每天至少沉淀：

- `ai_success`
- `ai_error`
- `fallback_count`
- `draft_preview_started`
- `draft_confirmed`
- `writeback_success`
- `unauthorized_denied`
- `cross_tenant_denied`

## 2. 14 天验证目标

14 天目标是判断是否值得扩到下一批 tenant，并为后续团队编排器提供依据：

- 至少 1 到 2 个 tenant 形成稳定使用习惯
- 草稿确认率和写回成功率在两周内保持稳定
- fallback 波动可控，不依赖大量人工兜底
- handoff / manager explanation 在协同场景下被实际使用
- 能明确看出 AI 卡片是否比纯规则卡更容易被采纳

## 3. 重点观察的行为变化

重点不是总量，而是动作质量变化：

- 从“看到卡片”到“点击预览”的转化是否稳定
- 从“预览草稿”到“确认草稿”的转化是否提高
- owner 是否更快完成下一步动作
- 经理 / ops 是否更愿意使用 handoffSummary 做接力判断
- 低置信度建议关闭后，是否明显减少误判反馈

## 4. 日报与周报口径

建议日报：

- 窗口：`1` 天
- 命令：
  - `./.venv310/bin/python scripts/render_customer_pulse_rollout_report.py --days 1 --format markdown`

建议周报：

- 窗口：`7` 天
- 命令：
  - `./.venv310/bin/python scripts/render_customer_pulse_rollout_report.py --days 7 --format markdown`

日报 / 周报至少包含：

- 使用量：`draft_preview_started`
- 草稿确认率：`draft_confirm_rate`
- fallback 率：`fallback_rate`
- 写回成功率：`writeback_success_rate`
- 安全拒绝事件：`unauthorized_denied / cross_tenant_denied`

## 5. 可扩容判定

满足以下条件，可建议扩到下一批 tenant：

- 连续 7 天 `ai_error_rate <= 10%`
- 连续 7 天 `fallback_rate <= 20%`
- `draft_confirm_rate >= 20%`
- `writeback_success_rate >= 95%`
- 没有未解决安全事件
- 业务侧没有明确要求关闭 AI 卡片入口

## 6. 维持当前规模判定

满足以下情况时，继续维持当前 1 到 2 个 tenant，不扩不回：

- 核心安全链路稳定
- 但 `draft_confirm_rate` 仍在磨合期，尚未稳定到扩容阈值
- 或 `fallback_rate` 偶发偏高，需要继续观察 provider 与提示词稳定性
- 或 tenant policy / owner scope 仍在小范围调整

## 7. 立即回滚判定

任一情况成立，直接回滚：

- 跨 tenant 数据泄露
- evidence 越权泄露
- 自动发送外部消息
- request-scoped 外部强约束失效
- audit / execution log 丢失导致无法追责

## 8. 哪些数据足以支持下一步做 AI 团队跟进编排器

以下数据成立，才说明值得把个人级卡片升级到团队编排：

- 至少两个 tenant 中，卡片到执行的链路稳定
- handoffSummary 有真实使用，不是只停留在展示
- 草稿确认率、写回成功率和 fallback 率已经稳定
- 能看出 owner / ops / manager 在不同角色下的使用差异
- 能识别“哪些卡片适合转派、接力、打包处理”，而不是所有卡都只适合个人处理

如果这些数据不足，就不应急着推进 AI 团队跟进编排器。

