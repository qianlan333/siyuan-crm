# Automation Engine Primitive Boundary

日期：2026-04-21

## 目标

从本文件开始，automation engine 相关 helper / primitive 分成 3 类：

1. formal application API
2. internal owner module
3. compatibility shim / legacy façade

只有第 1 类可以作为新的外层 caller 入口。第 2、3 类都不应再被外层 caller 当作业务入口直接依赖。

## 1. Formal application API

以下入口是当前唯一正式 owner：

- `wecom_ability_service/application/automation_engine/queries.py`
  - `ListSignupConversionBatchesQuery`
  - `GetSignupConversionBatchQuery`
  - `GetSignupConversionConfigQuery`
  - `PreviewSignupConversionCustomerQuery`
  - `ListOutboundWebhookDeliveriesQuery`
  - `GetOutboundWebhookDeliveryCountsQuery`
  - `GetCustomerMarketingProfileQuery`
- `wecom_ability_service/application/automation_engine/commands.py`
  - `SaveSignupConversionConfigCommand`
  - `RecomputeSignupConversionCustomersCommand`
  - `RecordConversionFeedbackCommand`
  - `AcknowledgeConversionBatchCommand`
  - `RetryOutboundWebhookDeliveryCommand`
  - `RunDueOutboundWebhookRetriesCommand`
  - `ApplyActivationWebhookCommand`
  - `SyncAutomationMemberActivationCommand`
  - `HandleQrcodeEnterFromCallbackCommand`
  - `MarkEnrolledCommand`
  - `UnmarkEnrolledCommand`
  - `SetManualFollowupSegmentCommand`

## 2. Internal owner modules

以下模块已经是 automation engine 的内部 owner，但不应被外层 caller 直接 import：

| 模块 / symbol | 允许调用范围 | 禁止调用范围 | 备注 |
| --- | --- | --- | --- |
| `wecom_ability_service/domains/automation_conversion/member_state_service.py::{get_member_detail,apply_router_target_pool,put_in_pool,remove_from_pool,set_follow_type,mark_won,unmark_won,sync_member_activation,handle_qrcode_enter_from_callback}` | `application/automation_engine/*`、`domains/automation_conversion/*` 内部 | `http/*`、`domains/admin_jobs/service.py`、`domains/admin_console/service.py`、`application/integration_gateway/mcp_dispatch.py` 的新代码 | member state / callback internal owner |
| `wecom_ability_service/domains/automation_conversion/signup_conversion_service.py::{list_signup_conversion_batches,get_signup_conversion_batch,record_conversion_feedback,ack_conversion_batch}` | `application/automation_engine/*`、automation domain 内部 | 同上 | signup conversion internal owner |
| `wecom_ability_service/domains/outbound_webhook/message_dispatch_service.py::{_attempt_delivery,send_outbound_webhook,retry_outbound_webhook_delivery,run_due_outbound_webhook_retries,list_outbound_webhook_deliveries,get_outbound_webhook_delivery_counts}` | `application/automation_engine/*`、`domains/outbound_webhook/*` 内部、automation domain internal glue | `http/*`、admin console / MCP / external caller | outbound retry / delivery internal owner |
| `wecom_ability_service/domains/automation_conversion/workflow_runtime_service.py::{run_due_conversion_workflows,sync_conversion_member_audience,sync_all_conversion_member_audiences}` | `domains/automation_conversion/*` 内部、后续正式 application runtime command | `http/*`、MCP / admin console 外层 caller | workflow runtime internal owner |
| `wecom_ability_service/domains/automation_conversion/workflow_execution_service.py::{get_conversion_dashboard_payload,list_conversion_workflow_executions,get_conversion_workflow_execution_detail,get_conversion_workflow_execution_item_detail,get_conversion_workflow_execution_bundle}` | `domains/automation_conversion/*` 内部、后续正式 execution query | `http/*` 新代码直接 import | workflow execution read internal owner |
| `wecom_ability_service/domains/automation_conversion/router_dispatch_service.py::{validate_router_callback_signature,backfill_missing_child_agent_replies,run_agent_router_shadow_decision,handle_agent_router_callback,record_agent_output_outcome,review_agent_reply_output}` | `domains/automation_conversion/*` 内部 | `http/*`、`application/integration_gateway/*`、外部 admin/console caller | router dispatch / review internal owner |
| `wecom_ability_service/domains/marketing_automation/message_dispatch_service.py::{send_pool_private_message,trigger_openclaw_focus_message_webhook,process_inbound_messages_for_openclaw}` | automation domain 内部 | `http/*`、MCP / admin console 新 caller | marketing message dispatch internal owner |

## 3. Compatibility shim / legacy façade

下列 symbol 当前仍存在，但从现在开始只视为 compatibility façade 或 legacy delegate：

### 3.1 `services.py` compatibility-only

- `list_outbound_webhook_deliveries`
- `retry_outbound_webhook_delivery`
- `run_due_outbound_webhook_retries`
- `apply_activation_webhook`
- `list_signup_conversion_batches`
- `get_signup_conversion_batch`
- `get_outbound_webhook_delivery_counts`
- `get_signup_conversion_config`
- `save_signup_conversion_config`
- `preview_signup_conversion_customer`
- `recompute_signup_conversion_customers`
- `record_conversion_feedback`
- `ack_conversion_batch`
- `get_customer_marketing_profile`
- `mark_enrolled`
- `unmark_enrolled`
- `set_manual_followup_segment`

允许范围：

- 旧调用方兼容
- tool registry / monkeypatch / 历史测试稳定面

禁止范围：

- 新增 `http/*` caller
- 新增 MCP / admin console 业务入口
- 新增跨 context bridge

### 3.2 Domain façade-only

下列文件中的这些 symbol 继续存在，但只应被视为同 context façade：

- `wecom_ability_service/domains/automation_conversion/service.py`
  - `get_member_detail`
  - `apply_router_target_pool`
  - `put_in_pool`
  - `remove_from_pool`
  - `set_follow_type`
  - `mark_won`
  - `unmark_won`
  - `sync_member_activation`
  - `handle_qrcode_enter_from_callback`
- `wecom_ability_service/domains/automation_conversion/orchestration_service.py`
  - `validate_router_callback_signature`
  - `backfill_missing_child_agent_replies`
  - `run_agent_router_shadow_decision`
  - `handle_agent_router_callback`
  - `record_agent_output_outcome`
  - `review_agent_reply_output`
- `wecom_ability_service/domains/marketing_automation/service.py`
  - `send_pool_private_message`
  - `trigger_openclaw_focus_message_webhook`
  - `process_inbound_messages_for_openclaw`
  - `get_signup_conversion_config`
  - `save_signup_conversion_config`
  - `preview_signup_conversion_customer`
  - `recompute_signup_conversion_customers`
  - `mark_enrolled`
  - `unmark_enrolled`
  - `set_manual_followup_segment`
  - `get_customer_marketing_profile`
  - `ack_conversion_batch`
  - `get_signup_conversion_batch`
  - `list_signup_conversion_batches`
- `wecom_ability_service/domains/outbound_webhook/service.py`
  - `_attempt_delivery`
  - `send_outbound_webhook`
  - `retry_outbound_webhook_delivery`
  - `run_due_outbound_webhook_retries`
  - `list_outbound_webhook_deliveries`
  - `get_outbound_webhook_delivery_counts`

这些 façade 的允许范围：

- automation domain 内部渐进迁移
- 同 context transport 仍未切完的历史界面

这些 façade 的禁止范围：

- 新增外层 caller
- 新增跨 context write/read owner
- 新增 direct primitive import

## 4. 结论

对 automation engine 来说，新的调用方向应当永远是：

`caller -> application/automation_engine/* -> internal owner / legacy delegate`

而不是：

`caller -> services.py`

或：

`caller -> domains/automation_conversion/* / domains/marketing_automation/* / domains/outbound_webhook/*`

更不应是：

`caller -> 新拆出的 internal owner module`
