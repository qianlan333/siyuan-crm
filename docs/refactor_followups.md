# 减法 / 重构跟进清单

记录这次本可以做但因为节制保留下来的"可清理项"，以及后续合并主线时建议处理的事项。

---

## 已经清理掉的（这次合并就生效）

| 删除项 | 原因 |
|---|---|
| `wecom_ability_service/domains/cloud_orchestrator/orchestrator.py` | CRM 不再做 LLM 调用（外部 Agent 接管），内置 Claude API client 失去意义 |
| `templates/admin_console/cloud_orchestrator_workspace.html` | 旧 AI 对话页已被 Campaigns 审阅页 + Integration 凭证页替代 |
| `POST /api/admin/cloud-orchestrator/sessions`（SSE 端点）| 同上 |
| `/admin/cloud-orchestrator` 路由 → 改 302 重定向到 `/admin/cloud-orchestrator/campaigns` | 减少入口冗余 |

---

## 第一波遗留 / 与新功能重叠（建议下次清）

### 1. `broadcast_planner` 是 Campaign 的 1 步特例
**现状**：`cloud_broadcast_plans` 表 + `propose_single_broadcast` 路径仍保留。
**建议**：合并主线 1-2 周后视使用情况，把单次广播的所有路径迁移到 `propose_campaign`（1 segment + 1 step），删除 `broadcast_planner.py` 和 `cloud_broadcast_plans` 表。这能省掉 ~400 行代码 + 1 张表。
**风险**：现有调用方需要迁移；迁移期间双写。

### 2. `automation_conversion/cadence_engine.py` 被 Campaign 替代
**现状**：cadence_engine（transition 评估器）原本是给老的 `automation_workflow_node_transition` 用的，但 Campaign 自己做 step 推进，没在用 transition 概念。
**建议**：如果新主线全部走 Campaign，可以把 cadence_engine 整个文件 + `automation_workflow_node_transition` 表删掉。如果还有客户在用老的 SOP-style workflow，保留。
**节省**：~280 行代码 + 1 张表。

### 3. `member_segment_search_service` 与 `segments` 部分重叠
**现状**：旧的多维筛选服务（用户在 PR #156 做的 `segment-search` / `segment-broadcast`）还在；新的 `segments` 是命名分层。两者底层都是查 `automation_member`。
**建议**：让旧的 `member_segment_search_service.search_members` 实现转发到 `segments_service.run_query`（用动态 SQL），最终把旧的 query builder 删掉。
**节省**：约 200 行 query builder 代码。

### 4. 历史 schema 双轨残留说明
**现状**：仓库已经进入 PG-only 运行形态，`schema.sql` 相关引用只应视为历史/归档上下文，不再作为新增表或新增字段的事实源。
**建议**：后续 schema 变更只走 PostgreSQL schema/migration 路径；不要重新引入 SQLite/PG 双 schema 维护。

### 5. 概览页 4 个 JS 文件可以合并
**现状**：`automation_overview_core.js / renderers.js / actions.js / automation_overview.js` 4 个文件，原意分层但现在边界很模糊。
**建议**：合并成 1-2 个，减少 HTTP 请求 + 简化加载顺序。

### 6. 系统默认分层 seed 暂未在 app 启动时自动跑
**现状**：`segments_service.seed_default_segments()` 需要手动调（或测试里调）。
**建议**：在 `wecom_ability_service/__init__.py` 的 app factory 启动 hook 里加一次性 seed（已存在则 noop）。当前用户必须自己跑一遍。

### 7. `frequency_budget_service.ensure_default_budgets` 同上
**建议**：和 segment seed 一起，启动期一次性写入。

### 8. `mcp_adapter.py` 1100+ 行，TOOL_DEFS 78 个
**现状**：所有 tool 定义堆在一个文件里。
**建议**：按 domain 拆分（`mcp_tools/customer.py`, `mcp_tools/agents.py`, `mcp_tools/cloud.py`...），让一个文件不要超过 300 行。

---

## 重构原则（合并主线时遵循）

1. **删一行胜过加十行**：每加一个新功能时，看一遍能不能借机删掉旧的等价物。
2. **新主路径 → 老路径**：新功能上线后给老路径设个**显式的 deprecation 标记**（注释 + 日志），下个版本再删。
3. **schema 改动配套清理**：每次加新表时检查有没有可以一起归并的旧表。
4. **不做"为了重用而重用"**：宁愿在 segment / campaign 里复制 30 行查询代码，也不抽 helper 给 1 个 caller 用。
5. **删代码必跑端到端**：删任何文件后必须跑：
   - `python3 -m alembic upgrade head`
   - `create_app()` import 通过
   - 关键 HTTP 端点 200

---

## 这次的取舍（为什么不一次做完）

用户原话："不想让这个产品在代码层面变得那么臃肿"。

这次本可以做更激进的清理（合并 broadcast_plan → campaign，删 cadence_engine 等），但保留它们的理由：
- 可能有现有数据 / 在跑的 SOP 依赖
- 一次性删太多会降低本次合并的安全性
- 留着观察 1-2 周后再清，比一次盲删更稳

所以：**这次清的是"明确没人用、且我自己刚加的"代码**（orchestrator / 旧助手页 / SSE）；老代码的清理留给下个版本。
