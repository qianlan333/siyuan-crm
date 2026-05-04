# Single Entry Map

日期：2026-04-17

范围：

- 仅覆盖 Wave 1 入口收口
- 不展开到 `user_ops` / `questionnaire` / `customer_pulse` / `followup_orchestrator` 的模块内部分裂

使用原则：

- 新调用方只能接到“新正式入口”
- 旧入口可以暂时保留，但只允许做 wrapper / shim / 兼容转发
- 标注为“已禁止新增调用”的旧入口，不允许再作为新代码依赖

## Wave 1 映射表

| 能力 | 旧入口 | 当前直接调用方 | 新正式入口 | 目标模块 | 旧入口状态 |
| --- | --- | --- | --- | --- | --- |
| Customer List | `wecom_ability_service/customer_center/service.py::list_customers`<br>`wecom_ability_service/customer_center/customer_profile_service.py::list_customers` | `wecom_ability_service/http/customer_center.py`<br>`wecom_ability_service/domains/admin_console/customer_profile_service.py` | `ListCustomersQuery` | `wecom_ability_service/application/customer_read_model/queries.py` | `customer_center/service.py` 已禁止新增调用 |
| Customer Detail | `wecom_ability_service/customer_center/service.py::get_customer_detail`<br>`wecom_ability_service/customer_center/customer_profile_service.py::get_customer_detail` | `wecom_ability_service/http/customer_center.py`<br>`wecom_ability_service/http/customer_automation.py`<br>`wecom_ability_service/mcp_adapter.py::_build_customer_context_payload` | `GetCustomerDetailQuery` | `wecom_ability_service/application/customer_read_model/queries.py` | `customer_center/service.py` 已禁止新增调用；`mcp_adapter` 私有函数已禁止新增依赖 |
| Customer Timeline | `wecom_ability_service/customer_timeline/service.py::get_customer_timeline` | `wecom_ability_service/http/customer_timeline.py`<br>`wecom_ability_service/http/customer_automation.py`<br>`wecom_ability_service/mcp_adapter.py::_get_customer_timeline_payload` | `GetCustomerTimelineQuery` | `wecom_ability_service/application/customer_read_model/queries.py` | `customer_timeline/service.py` 已禁止新增调用；`mcp_adapter` 私有函数已禁止新增依赖 |
| Customer Chat Context | `openclaw_service/services/customer_chat_context_service.py::get_customer_chat_context`<br>`openclaw_service/tools/customer_chat_context_tool.py`<br>`wecom_ability_service/mcp_adapter.py::_build_customer_context_payload` | `openclaw_service/services/crm_operator_service.py`<br>`openclaw_service/tools/customer_chat_context_tool.py`<br>`mcp get_customer_context` | `GetCustomerChatContextQuery` | `wecom_ability_service/application/customer_read_model/queries.py` | 旧 OpenClaw service 可保留为 wrapper；新增读取逻辑禁止旁路拼装 customer detail + timeline + messages |
| Recent Messages | `wecom_ability_service/services.py::get_recent_messages_by_user`<br>`wecom_ability_service/domains/archive/service.py::get_recent_messages_by_user` | `wecom_ability_service/http/archive.py`<br>`wecom_ability_service/http/customer_automation.py`<br>`wecom_ability_service/mcp_adapter.py` | `ListRecentMessagesQuery` | `wecom_ability_service/application/customer_read_model/queries.py` | `services.py` 已禁止新增调用；domain read helper 只允许被正式 query 包起来 |
| MCP Dispatch | `wecom_ability_service/mcp_adapter.py::_call_business_task`<br>`wecom_ability_service/mcp_adapter.py::_call_wecom_task`<br>`wecom_ability_service/mcp_adapter.py` 内联 `tools/call` 分支 | `wecom_ability_service/mcp_adapter.py` | `DispatchMcpToolCommand` | `wecom_ability_service/application/integration_gateway/mcp_dispatch.py` | `mcp_adapter.py` 私有函数已禁止新增依赖 |
| Internal Auth | `wecom_ability_service/http/internal_auth.py::require_internal_api_token` | `wecom_ability_service/mcp_adapter.py`<br>`wecom_ability_service/http/customer_automation.py`<br>`wecom_ability_service/http/admin_customer_pulse.py`<br>`wecom_ability_service/http/admin_followup_orchestrator.py`<br>`wecom_ability_service/http/admin_jobs.py` | `AuthorizeInternalRequestQuery` | `wecom_ability_service/application/platform_foundation/auth_queries.py` | 部分禁止：禁止新增散用为隐式策略；现有 transport/controller 可暂时透传 |
| Signup Conversion Batch List | `wecom_ability_service/services.py::list_signup_conversion_batches`<br>`wecom_ability_service/domains/marketing_automation/service.py::list_signup_conversion_batches` | `wecom_ability_service/http/customer_automation.py`<br>`wecom_ability_service/mcp_adapter.py` | `ListSignupConversionBatchesQuery` | `wecom_ability_service/application/automation_engine/queries.py` | `services.py` 已禁止新增调用；controller 禁止继续直连 domain/service |
| Signup Conversion Batch Detail | `wecom_ability_service/services.py::get_signup_conversion_batch`<br>`wecom_ability_service/domains/marketing_automation/service.py::get_signup_conversion_batch` | `wecom_ability_service/http/customer_automation.py`<br>`wecom_ability_service/mcp_adapter.py` | `GetSignupConversionBatchQuery` | `wecom_ability_service/application/automation_engine/queries.py` | `services.py` 已禁止新增调用；`http/customer_automation.py` 只允许切到 query，不允许继续内联 `_candidate_context` |
| Outbound Webhook Retry | `wecom_ability_service/services.py::retry_outbound_webhook_delivery`<br>`wecom_ability_service/domains/outbound_webhook/service.py::retry_outbound_webhook_delivery` | `wecom_ability_service/http/customer_automation.py`<br>`wecom_ability_service/domains/admin_jobs/service.py` | `RetryOutboundWebhookDeliveryCommand` | `wecom_ability_service/application/automation_engine/queries.py` | `services.py` 已禁止新增调用；controller / jobs 需要统一走 command |
| Automation Member Activation | `wecom_ability_service/domains/automation_conversion/service.py::sync_member_activation` | `wecom_ability_service/http/customer_automation.py` | `SyncAutomationMemberActivationCommand` | `wecom_ability_service/application/automation_engine/queries.py` | 旧 domain service 不应再成为新 controller 的直接依赖 |

## 已经明确禁止新增调用的旧入口

- `wecom_ability_service/services.py`
- `wecom_ability_service/customer_center/service.py`
- `wecom_ability_service/customer_timeline/service.py`
- `wecom_ability_service/mcp_adapter.py` 的私有函数

## Wave 1 落地时的切换顺序

1. 先新增正式入口，不切调用方
2. 再切 `http/customer_center.py`
3. 再切 `http/customer_timeline.py`
4. 再切 `http/customer_automation.py`
5. 再切 `domains/admin_console/customer_profile_service.py`
6. 最后切 `mcp_adapter.py`

这个顺序的核心目的是：让每次回滚都只需要回滚一个调用面，而不是回滚整个 read / MCP / automation 组合。
