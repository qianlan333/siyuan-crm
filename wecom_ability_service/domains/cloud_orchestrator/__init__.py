"""Cloud orchestrator — CRM 暴露给外部 Agent（Claude Code 等）的策略层能力。

CRM 自己**不做 LLM 调用**；外部 Agent 通过 MCP HTTP 端点连接 CRM，按 prompt + tool use
自己编排。CRM 这一层只提供：
- ``broadcast_planner``  — 单次广播草稿（Campaign 1 步特例）
- ``audit``              — 审计日志 + trace_id
- ``approval_token``     — UI 签发的一次性 token（commit_broadcast_plan / start_campaign）
- ``mcp_tools``          — Tool catalog + dispatch router
- ``external_agent``     — 外部 Agent 的 tool-use loop（cron / UI worker / CLI 共用）

(2026-05-06) 删除：``orchestrator.py``（内置 Claude API client），定位由外部 Agent 接管。
(2026-05-09) 新增：``external_agent.py`` — 外部 Cloud Agent 的可复用 tool-use loop，
让 cron 脚本 / 未来 UI SSE worker / 测试共用同一段编排逻辑。
"""
