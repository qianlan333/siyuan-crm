# PR Splitting Plan

日期：2026-04-17

范围：

- 只拆 Wave 1
- 不进入 `user_ops` / `questionnaire` / `automation_conversion` / `customer_pulse` / `followup_orchestrator` 的模块内部大拆

拆分原则：

- 每个 PR 只碰一个主要入口面
- 每个 PR 最多碰一个冻结文件
- schema / db 与入口收口不混在同一个 PR
- 旧入口先保留为 wrapper，再切调用方

## PR 1. Governance Baseline

目标：

- 先把 fat-file、merge hotspot、single-entry、cache runbook、smoke script、清理脚本和 guardrail 基线补齐

涉及文件：

- `docs/refactor/fat-file-inventory.md`
- `docs/refactor/merge-hotspots.md`
- `docs/refactor/single-entry-map.md`
- `docs/refactor/cache-reset-runbook.md`
- `docs/refactor/pr-splitting-plan.md`
- `scripts/clean_dev_state.sh`
- `scripts/test_wave1_smoke.sh`
- `tests/test_refactor_guardrails.py`

不涉及文件：

- `wecom_ability_service/services.py`
- `wecom_ability_service/mcp_adapter.py`
- `wecom_ability_service/customer_center/service.py`
- `wecom_ability_service/customer_timeline/service.py`

风险：

- 文档和脚本口径不一致

回滚方式：

- 直接回滚文档 / 脚本 / guardrail 文件

必跑测试：

- `tests/test_refactor_guardrails.py`
- `./scripts/test_wave1_smoke.sh`

## PR 2. Application Skeleton

目标：

- 建立 Wave 1 需要的正式命名空间，但不切任何调用方

涉及文件：

- `wecom_ability_service/application/__init__.py`
- `wecom_ability_service/application/customer_read_model/__init__.py`
- `wecom_ability_service/application/customer_read_model/dto.py`
- `wecom_ability_service/application/customer_read_model/queries.py`
- `wecom_ability_service/application/integration_gateway/__init__.py`
- `wecom_ability_service/application/integration_gateway/mcp_dispatch.py`
- `wecom_ability_service/application/platform_foundation/__init__.py`
- `wecom_ability_service/application/platform_foundation/auth_queries.py`
- `wecom_ability_service/application/platform_foundation/mcp_runtime_queries.py`
- `wecom_ability_service/application/automation_engine/__init__.py`
- `wecom_ability_service/application/automation_engine/queries.py`

不涉及文件：

- `wecom_ability_service/http/*`
- `wecom_ability_service/mcp_adapter.py`
- `wecom_ability_service/services.py`
- `wecom_ability_service/domains/admin_console/*`

风险：

- application 层写成第二个 `services.py`

回滚方式：

- 纯新增文件，整体回滚即可

必跑测试：

- `tests/test_service_layer_layout.py`
- `tests/test_http_registration_contract.py`
- `tests/test_refactor_guardrails.py`

## PR 3. Customer Read Wrappers

目标：

- 把 customer list / detail / timeline / chat context / recent messages 统一包到正式 read model 入口后面

涉及文件：

- `wecom_ability_service/customer_center/service.py`
- `wecom_ability_service/customer_center/__init__.py`
- `wecom_ability_service/customer_timeline/service.py`
- `wecom_ability_service/customer_timeline/__init__.py`
- `wecom_ability_service/customer_center/pulse_service.py`
- `wecom_ability_service/application/customer_read_model/queries.py`

不涉及文件：

- `wecom_ability_service/http/customer_center.py`
- `wecom_ability_service/http/customer_timeline.py`
- `wecom_ability_service/http/customer_automation.py`
- `wecom_ability_service/mcp_adapter.py`

风险：

- customer detail / timeline 字段漂移

回滚方式：

- 保留旧函数名，仅把内部转发改回旧实现

必跑测试：

- `tests/test_customer_center_api.py`
- `tests/test_customer_timeline_api.py`
- `tests/contract/test_crm_contract.py`

## PR 4. Customer HTTP Controllers

目标：

- 把 customer list / detail / timeline 三个 HTTP controller 改成只调正式 query

涉及文件：

- `wecom_ability_service/http/customer_center.py`
- `wecom_ability_service/http/customer_timeline.py`
- `wecom_ability_service/customer_center/routes.py`
- `wecom_ability_service/customer_timeline/routes.py`
- `wecom_ability_service/application/customer_read_model/queries.py`

不涉及文件：

- `wecom_ability_service/http/customer_automation.py`
- `wecom_ability_service/mcp_adapter.py`
- `wecom_ability_service/services.py`

风险：

- controller 错误码或响应结构意外变化

回滚方式：

- 只回滚 controller wiring，不回滚 read wrapper

必跑测试：

- `tests/test_customer_center_api.py`
- `tests/test_customer_timeline_api.py`
- `tests/test_http_registration_contract.py`

## PR 5. Automation Read Entry Cleanup

目标：

- 只收口 `http/customer_automation.py` 里的 read / auth / retry / activation 入口，不碰 automation 内部大拆

涉及文件：

- `wecom_ability_service/http/customer_automation.py`
- `wecom_ability_service/http/internal_auth.py`
- `wecom_ability_service/application/customer_read_model/queries.py`
- `wecom_ability_service/application/automation_engine/queries.py`
- `wecom_ability_service/application/platform_foundation/auth_queries.py`

不涉及文件：

- `wecom_ability_service/domains/automation_conversion/service.py`
- `wecom_ability_service/domains/marketing_automation/service.py`
- `wecom_ability_service/domains/outbound_webhook/service.py`
- `wecom_ability_service/mcp_adapter.py`

风险：

- signup conversion batch detail 的 candidate context 字段丢失

回滚方式：

- 只回滚 `http/customer_automation.py` 和对应 application wiring

必跑测试：

- `tests/test_mcp_business_tools.py`
- `tests/test_http_registration_contract.py`
- `tests/test_customer_center_api.py`
- `tests/test_customer_timeline_api.py`

## PR 6. Admin Customer Shell

目标：

- 把 admin customer profile / shell 从 read model implementation 和 MCP 私有函数上摘下来

涉及文件：

- `wecom_ability_service/domains/admin_console/service.py`
- `wecom_ability_service/domains/admin_console/customer_profile_service.py`
- `wecom_ability_service/http/admin_customers.py`
- `wecom_ability_service/http/admin_mcp.py`
- `wecom_ability_service/application/customer_read_model/queries.py`
- `wecom_ability_service/application/ai_assist/*` 仅在必要时补 adapter

不涉及文件：

- `wecom_ability_service/mcp_adapter.py`
- `wecom_ability_service/http/customer_center.py`
- `wecom_ability_service/http/customer_timeline.py`

风险：

- admin customer 页面与 marketing / automation monkeypatch 测试联动失败

回滚方式：

- 保留旧函数签名，仅回滚内部实现

必跑测试：

- `tests/test_admin_customer_profile_console.py`
- `tests/test_mcp_business_tools.py`
- `tests/test_service_layer_layout.py`

## PR 7. MCP Transport Only

目标：

- 把 `mcp_adapter.py` 缩成 transport，只保留 auth、JSON-RPC、tool schema 和 dispatch 调用

涉及文件：

- `wecom_ability_service/mcp_adapter.py`
- `wecom_ability_service/application/integration_gateway/mcp_dispatch.py`
- `wecom_ability_service/application/platform_foundation/auth_queries.py`
- `wecom_ability_service/application/platform_foundation/mcp_runtime_queries.py`
- `wecom_ability_service/http/internal_auth.py`

不涉及文件：

- `wecom_ability_service/domains/automation_conversion/*`
- `wecom_ability_service/domains/customer_pulse/*`
- `wecom_ability_service/domains/user_ops/*`
- `wecom_ability_service/schema*.sql`

风险：

- MCP tool 行为在 transport 与 dispatch 拆开后出现 schema 或 fallback 回归

回滚方式：

- 只回滚 dispatch 映射或 `mcp_adapter.py` transport wiring

必跑测试：

- `tests/test_mcp_business_tools.py`
- `tests/contract/test_crm_contract.py`
- `tests/test_http_registration_contract.py`

## 推荐执行顺序

1. PR 1 `Governance Baseline`
2. PR 2 `Application Skeleton`
3. PR 3 `Customer Read Wrappers`
4. PR 4 `Customer HTTP Controllers`
5. PR 5 `Automation Read Entry Cleanup`
6. PR 6 `Admin Customer Shell`
7. PR 7 `MCP Transport Only`

这样拆的目的不是追求“完美架构”，而是把 Wave 1 变成一串可回滚、可合并、可验证的小变更。
