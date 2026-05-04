# Wave 1 Closeout

日期：2026-04-19

状态：Closed

## 1. Wave 1 完成项

已完成：

- 建立正式 application 命名空间：
  - `wecom_ability_service/application/customer_read_model/`
  - `wecom_ability_service/application/integration_gateway/`
  - `wecom_ability_service/application/platform_foundation/`
  - `wecom_ability_service/application/automation_engine/`
  - `wecom_ability_service/application/ai_assist/`
- Customer Read 入口已从 legacy `service.py` 收口到正式 query：
  - `ListCustomersQuery`
  - `GetCustomerDetailQuery`
  - `GetCustomerTimelineQuery`
  - `GetCustomerChatContextQuery`
  - `ListRecentMessagesQuery`
- legacy `customer_center/service.py`、`customer_timeline/service.py` 已退化为 compatibility wrapper，不再是默认新入口。
- `http/customer_center.py`、`http/customer_timeline.py` 已收口为 controller-only，正式读取入口统一走 `application/customer_read_model/*`。
- `http/customer_automation.py` 的 Wave 1 范围入口已收口到正式 application API：
  - signup conversion batch list/detail
  - internal auth
  - webhook retry
  - automation member activation sync
  - candidate context 中的 detail/timeline/recent messages 读取路径
- admin customer shell 已从 read model implementation 和 MCP 私有函数摘离：
  - `domains/admin_console/service.py`
  - `domains/admin_console/customer_profile_service.py`
- `mcp_adapter.py` 已缩成 transport：
  - 鉴权
  - JSON-RPC parse / response
  - tool schema 暴露
  - 调正式 application dispatch
- MCP tool 执行逻辑已集中到 `application/integration_gateway/mcp_dispatch.py`。
- `services.py` 已收敛成 compatibility shim：
  - re-export
  - backward-compatible wrapper
  - monkeypatch / DI glue
- Wave 1 guardrails 已落地并通过：
  - controller 禁止新增 `requests`
  - controller 禁止直接 SQL
  - 禁止新增 direct import legacy `service.py` / `services.py` / `mcp_adapter` 私有函数
- Wave 1 收尾脚本已落地：
  - `scripts/test_wave1_smoke.sh`
  - `scripts/clean_dev_state.sh`

## 2. 未完成项

无。

说明：

- 这里的“无”是指按 `docs/refactor/phase-1-execution-plan.md` 中 Wave 1 边界定义，没有遗留必须在 Wave 1 内闭合的入口收口项。
- 不包含 Wave 2 明确接手的内部模块拆分工作。

## 3. 已知例外 / 过渡债务

- `wecom_ability_service/application/integration_gateway/mcp_dispatch.py` 仍然偏大。
  - 原因：PR 7 先把 MCP 业务执行从 transport 挪出，优先保契约，再留待后续 context 内部继续拆。
- `wecom_ability_service/services.py` 仍保留较宽 compatibility surface。
  - 主要集中在 `identity` / `user_ops` / `class_user` / `questionnaire` / `archive` 等历史兼容符号。
- `wecom_ability_service/http/customer_automation.py` 虽然 Wave 1 范围入口已收口，但仍是兼容性较强的控制器文件。
  - 后续不应继续向里面增长新的跨 context 逻辑。
- 当前 guardrails 是“冻结现状、禁止新增”的基线策略，不是“历史依赖已全部清零”的状态。
- Wave 2 所需的 write-side formal application API 还未建立：
  - identity binding
  - class user status write path
  - user ops lead pool write path
  - routing / owner-role config write path

## 4. 关键收益

业务兼容收益：

- 现有 HTTP path、MCP tool name、核心 JSON key、主要错误码语义在 Wave 1 范围内保持兼容。
- legacy 公开符号仍可 import，旧调用方没有被一次性切断。
- admin customer、customer read、customer automation、MCP transport 的关键外部契约保持稳定。

工程收益：

- 新调用方已经有正式 application 入口，不需要再把逻辑塞进 `services.py`、`mcp_adapter.py` 或 legacy `service.py`。
- `customer_center` / `customer_timeline` / `mcp_adapter` / `services.py` 的职责边界清晰了，新增逻辑有固定落点。
- guardrails 和 smoke 脚本把“禁止新债继续进入”这件事自动化了。
- Wave 2 可以直接围绕 write path 盘点推进，而不需要再回头先收口 Wave 1 入口。

## 5. 手工验收结果汇总

收尾结论基于 2026-04-19 的本地回归与入口验收。

接口 / 契约回归：

- `tests/test_service_layer_layout.py`
- `tests/test_customer_center_api.py`
- `tests/test_customer_timeline_api.py`
- `tests/test_mcp_business_tools.py`
- `tests/test_admin_customer_profile_console.py`
- `tests/test_http_registration_contract.py`
- `tests/contract/test_crm_contract.py`
- 结果：`63 passed`

Wave 1 smoke：

- `./scripts/test_wave1_smoke.sh`
- 结果：`PASS`
- 汇总：`63 passed`

Wave 1 期间已单独冻结的高风险回归：

- `tests/test_mcp_recent_chat_dump.py`
- `tests/test_refactor_guardrails.py`
- `tests/test_conversion_service.py`
- `tests/test_admin_jobs_console.py`

入口层验收结论：

- customer list / detail / timeline 入口已切到正式 application read API。
- customer automation 的 Wave 1 范围入口已切到正式 application API。
- admin customer shell 已切到正式 application API。
- `/mcp` 的 `initialize`、`tools/list`、`tools/call` 契约已冻结并通过回归。

说明：

- 本 closeout 没有额外再做一轮浏览器级逐页点验。
- Wave 1 的“手工验收”以接口入口 smoke、契约回归、admin/customer/MCP 关键路径验证为主。

## 6. 最终结论

结论：Wave 1 已完成。

判断依据：

- `phase-1-execution-plan.md` 定义的交付物已经全部落地。
- 关键兼容入口已经收口到正式 application API。
- `mcp_adapter.py` 与 `services.py` 已被压回兼容层职责。
- guardrails 与 smoke 回归已经通过，当前代码基线可作为 Wave 2 起点。
