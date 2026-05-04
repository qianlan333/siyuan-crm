# 自动化转化验收修复日志

## 初始化说明

- 当前阶段：真实业务验收阶段
- 当前策略：只修阻塞业务验收的问题
- 修复原则：最小改动、最小回归、不顺手扩需求、不顺手重构
- 每次阻塞性问题修复后，必须同步更新：
  - `docs/automation_conversion_acceptance_issues.md`
  - `docs/automation_conversion_acceptance_fix_log.md`

## 修复记录

| 问题编号 | 修复时间 | 改动文件 | 改动范围 | 为什么这样修 | 补了哪些测试 | 怎么回归验证 |
| --- | --- | --- | --- | --- | --- | --- |
| INIT | 2026-04-06 | `docs/automation_conversion_acceptance_issues.md`、`docs/automation_conversion_acceptance_fix_log.md` | 初始化验收陪跑台账 | 先把验收问题台账和修复日志建好，保证后续每个问题都可追踪 | 无 | 检查两份文档已创建，并已录入当前 v1 限制项 |
| ACPT-001 | 2026-04-06 | `wecom_ability_service/domains/marketing_automation/service.py`、`wecom_ability_service/domains/marketing_automation/repo.py`、`tests/test_marketing_automation.py`、`scripts/seed_automation_conversion_demo.py`、`docs/automation_conversion_*.md` | 去掉第 4/5 块单负责人限制，补多负责人 seed、测试和文档 | 这是当前最明显的 v1 业务限制，升级成多负责人后才能让第 4/5 块在不同 owner 场景下直接可用 | 池子群发多负责人回归、重点消息 webhook 多负责人回归、jobs webhook 面板回归 | 执行 `tests/test_marketing_automation.py` 的多负责人用例和 `tests/test_admin_jobs_console.py` 的 webhook 面板用例，确认 5 条测试通过 |
| ACPT-002 | 2026-04-06 | `wecom_ability_service/mcp_adapter.py`、`wecom_ability_service/domains/tasks/private_message.py`、`wecom_ability_service/domains/user_ops/page_service.py`、`tests/test_marketing_automation.py`、`tests/test_api.py`、`docs/automation_conversion_*.md` | 放开池子群发图片与附件输入，补 MCP schema、attachment 校验、池子群发回归和文档 | 底层私聊发送链路已经支持图片与 attachments，这次继续沿用原链路，只把 MCP 暴露层、空消息体校验和回归覆盖补齐，避免重造发送系统 | 纯文本兼容、纯图片、纯附件、文本 + 附件、图片 + 附件、文本 + 图片 + 附件、非法 attachment、沉默池不发送回归 | 执行 `tests/test_marketing_automation.py` 与 `tests/test_api.py` 的池子群发/私聊任务用例，确认文本、图片、附件及组合能力都通过 |
