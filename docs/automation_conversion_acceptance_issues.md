# 自动化转化验收问题台账

## 使用说明

- 只记录业务验收阶段的问题和限制项。
- 阻塞问题进入“待复现 / 已复现 / 已修复”流程。
- 不阻塞验收的 v1 限制先记账，默认状态为“暂不处理”。

## 问题列表

| 编号 | 日期 | 提出人 | 场景 | 复现步骤 | 实际结果 | 预期结果 | 是否阻塞验收 | 当前状态 | 对应修复 commit 或本地改动说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ACPT-001 | 2026-04-06 | 系统预录 | v1 限制：负责人范围 | 业务验收时尝试让 `QianLan` 以外负责人使用池子群发或重点消息 webhook | 第 4/5 块曾只支持 `owner_userid=QianLan` | 现已支持多个负责人 | 否 | 已修复 | 第 10 块已落地，多负责人支持已覆盖池子群发和重点消息 webhook |
| ACPT-002 | 2026-04-06 | 系统预录 | v1 限制：池子群发能力 | OpenClaw 或验收方尝试发送图片/附件 | 第 12 块前，MCP 暴露的池子群发只支持文本 `content` | 当前已支持纯文本、纯图片、纯附件、文本 + 图片、文本 + 附件、图片 + 附件、文本 + 图片 + 附件 | 否 | 已修复 | 第 12/13 块已完成图片与附件开放，当前剩余限制见 `docs/automation_conversion_open_issues.md` |
| ACPT-003 | 2026-04-06 | 系统预录 | v1 限制：webhook 稳定性 | 模拟 OpenClaw webhook 或问卷 webhook 失败 | 当前只记录日志，不做自动重试 | 后续版本可接重试队列 | 否 | 暂不处理 | 当前实现为 v1 业务边界，见 `docs/automation_conversion_open_issues.md` |
| ACPT-004 | 2026-04-06 | 系统预录 | v1 限制：激活回写匹配方式 | 外部系统尝试用 external_userid / unionid 回写激活 | 当前只按手机号匹配客户 | 后续版本可支持更多匹配方式 | 否 | 暂不处理 | 当前实现为 v1 业务边界，见 `docs/automation_conversion_open_issues.md` |
| ACPT-005 | 2026-04-06 | 系统预录 | v1 限制：沉默池经营 | 验收方尝试对沉默池做主动经营 | 当前只记录沉默池，不开放群发和经营动作 | 后续版本可扩沉默池经营策略 | 否 | 暂不处理 | 当前实现为 v1 业务边界，见 `docs/automation_conversion_open_issues.md` |
| ACPT-006 | 2026-04-06 | 系统预录 | v1 限制：trial_opened 事实源 | 追问 trial_opened 数据来源和上游事件链 | 当前复用 `user_ops_pool_current.current_status='lead_trial'` 作为最小落地事实源 | 后续版本可升级为更完整事件体系 | 否 | 暂不处理 | 当前实现为 v1 业务边界，见 `docs/automation_conversion_open_issues.md` |
| ACPT-007 | 2026-04-06 | 系统预录 | v1 限制：内部兼容命名 | 代码审查时检索旧命名 | 仍有少量内部兼容命名，例如 `signup_conversion_v1`、`top_threshold` | 不影响当前业务验收，但后续可逐步清理 | 否 | 暂不处理 | 当前实现为兼容保留，不对业务页面暴露 |
