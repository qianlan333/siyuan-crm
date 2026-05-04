# Wave 4 Automation Engine Callers Map

日期：2026-04-21

## 1. 目标

本文只盘点当前 automation 相关 caller，不改业务代码。

重点不是“列出所有出现过 automation import 的文件”，而是识别：

- 哪些入口在直接写 automation truth
- 哪些入口在直接读 automation read model
- 哪些入口把 callback / retry / due runner 直接绑在 legacy service 上
- 哪些 caller 是 Wave 4 第一批必须优先切换的面

## 2. Caller 总览

### 2.1 Signup Conversion / Activation / Retry 入口

| Caller 文件 | 入口 / 路径 | 当前 legacy 调用 | 目标 formal contract | 说明 | 优先级 |
| --- | --- | --- | --- | --- | --- |
| `wecom_ability_service/http/admin_config.py` | `/api/admin/marketing-automation/config` | `services.get_signup_conversion_config`、`services.save_signup_conversion_config` | `GetSignupConversionConfigQuery`、`SaveSignupConversionConfigCommand` | signup conversion config admin owner 仍停在 `services.py` | P0 |
| `wecom_ability_service/http/admin_config.py` | `/api/admin/marketing-automation/config/preview` | `services.preview_signup_conversion_customer` | `PreviewSignupConversionCustomerQuery` | preview 当前仍用 legacy reader | P0 |
| `wecom_ability_service/http/admin_config.py` | `/api/admin/marketing-automation/recompute` | `services.recompute_signup_conversion_customers` | `RecomputeSignupConversionCustomersCommand` | recompute 直接落 legacy write owner | P0 |
| `wecom_ability_service/http/customer_automation.py` | `/api/customers/automation/signup-conversion/batches` | `application.automation_engine.ListSignupConversionBatchesQuery` | 保持现有 | Wave 1 已收口，但仍是 Wave 4 batch line 基线 | P0 |
| `wecom_ability_service/http/customer_automation.py` | `/api/customers/automation/signup-conversion/batches/<batch_id>` | `application.automation_engine.GetSignupConversionBatchQuery` + controller 内 `_candidate_context` | `GetSignupConversionBatchQuery` + customer read model query | batch detail 已部分 formalize，但 customer context 聚合仍在 caller | P0 |
| `wecom_ability_service/http/customer_automation.py` | `/api/customers/automation/activation-webhook` | `ApplyActivationWebhookCommand` + 直调 `sync_member_activation` | `ApplyActivationWebhookCommand`、`SyncAutomationMemberActivationCommand` | activation webhook 还存在 controller 到 legacy member sync 的旁路 | P0 |
| `wecom_ability_service/http/customer_automation.py` | `/api/customers/automation/webhook-deliveries` | `ListOutboundWebhookDeliveriesQuery` | 保持现有并补齐 admin jobs 同线收口 | Wave 1 已有 formal query | P0 |
| `wecom_ability_service/http/customer_automation.py` | `/api/customers/automation/webhook-deliveries/<delivery_id>/retry` | `RetryOutboundWebhookDeliveryCommand` | 保持现有 | Wave 1 已有 formal command | P0 |
| `wecom_ability_service/http/customer_automation.py` | `/api/customers/automation/webhook-deliveries/retry-due` | `RunDueOutboundWebhookRetriesCommand` | 保持现有 | Wave 1 已有 formal command | P0 |
| `wecom_ability_service/domains/admin_jobs/service.py` | webhook deliveries / retry / run-due 面板与 action | `services.list_outbound_webhook_deliveries`、`retry_outbound_webhook_delivery`、`run_due_outbound_webhook_retries` | `ListOutboundWebhookDeliveriesQuery`、`GetOutboundWebhookDeliveryCountsQuery`、`RetryOutboundWebhookDeliveryCommand`、`RunDueOutboundWebhookRetriesCommand` | admin jobs 仍绕 legacy retry owner | P0 |

### 2.2 Marketing Truth / Manual State 入口

| Caller 文件 | 入口 / 路径 | 当前 legacy 调用 | 目标 formal contract | 说明 | 优先级 |
| --- | --- | --- | --- | --- | --- |
| `wecom_ability_service/http/sidebar.py` | `/api/sidebar/marketing-status` | `domains.marketing_automation.service.get_customer_marketing_profile` | `GetCustomerMarketingProfileQuery` | sidebar 当前直接读 legacy marketing truth | P1 |
| `wecom_ability_service/http/sidebar.py` | `/api/sidebar/marketing-status/set-followup-segment` | `services.set_manual_followup_segment` | `SetManualFollowupSegmentCommand` | 手工 followup segment 改写入口 | P1 |
| `wecom_ability_service/http/sidebar.py` | `/api/sidebar/marketing-status/mark-enrolled` | `services.mark_enrolled` | `MarkEnrolledCommand` | 还会同步 class_user truth | P1 |
| `wecom_ability_service/http/sidebar.py` | `/api/sidebar/marketing-status/unmark-enrolled` | `services.unmark_enrolled` | `UnmarkEnrolledCommand` | manual rollback 入口 | P1 |
| `wecom_ability_service/http/admin_support.py` | support sidebar tag / mark enrolled actions | `domains.marketing_automation.service.mark_enrolled`、`unmark_enrolled` | `MarkEnrolledCommand`、`UnmarkEnrolledCommand` | admin support 仍直接命中 legacy write owner | P1 |
| `wecom_ability_service/application/integration_gateway/mcp_dispatch.py` | MCP tools `record_conversion_feedback`、`get_signup_conversion_batches`、`ack_conversion_batch`、`mark_enrolled`、`unmark_enrolled` 等 | 直接 import `domains.automation_conversion` + `services.*automation*` | 后续统一切到 `application/automation_engine/*` | MCP 是 automation 最大的 caller bypass 之一 | P2 |
| `wecom_ability_service/domains/admin_console/service.py` | admin tool registry / preview / examples | `service_paths` 仍指向 `wecom_ability_service.services.record_conversion_feedback` 等 | 后续 registry 只指向 formal automation API | tool metadata 仍在加固 legacy surface | P2 |

### 2.3 Member State / Callback 入口

| Caller 文件 | 入口 / 路径 | 当前 legacy 调用 | 目标 formal contract | 说明 | 优先级 |
| --- | --- | --- | --- | --- | --- |
| `wecom_ability_service/http/background_jobs.py` | external contact callback -> qrcode enter bridge | `domains.automation_conversion.service.handle_qrcode_enter_from_callback` | `HandleQrCodeEnterCallbackCommand` | callback 仍直连 member-state legacy service | P1 |
| `wecom_ability_service/http/automation_conversion.py` | `/api/admin/automation-conversion/member` | `get_member_detail` | `GetAutomationMemberDetailQuery` | member detail 读面还在 legacy domain | P1 |
| `wecom_ability_service/http/automation_conversion.py` | `/api/admin/automation-conversion/member/put-in-pool` | `put_in_pool` | `ChangeAutomationMemberPoolStateCommand(action=put_in_pool)` | member-state write 入口 | P1 |
| `wecom_ability_service/http/automation_conversion.py` | `/api/admin/automation-conversion/member/remove-from-pool` | `remove_from_pool` | `ChangeAutomationMemberPoolStateCommand(action=remove_from_pool)` | member-state write 入口 | P1 |
| `wecom_ability_service/http/automation_conversion.py` | `/api/admin/automation-conversion/member/set-focus`、`set-normal` | `set_follow_type` | `ChangeAutomationMemberPoolStateCommand(action=set_follow_type)` | focus/normal 切换 | P1 |
| `wecom_ability_service/http/automation_conversion.py` | `/api/admin/automation-conversion/member/mark-won`、`unmark-won` | `mark_won`、`unmark_won` | `ChangeAutomationMemberPoolStateCommand(action=mark_won|unmark_won)` | won 状态变更 | P1 |
| `wecom_ability_service/http/automation_conversion.py` | `/api/admin/automation-conversion/member/push-openclaw` | `push_openclaw` | `PushOpenClawCommand` | member push 仍直连 legacy write | P1 |
| `wecom_ability_service/http/automation_conversion.py` | `/admin/automation-conversion`、`/overview`、`/stage/<stage_key>` | `get_overview_payload`、`get_stage_detail_payload` | `GetAutomationOverviewQuery`、`GetAutomationStageDetailQuery` | overview/stage detail 读面还没 formalize | P1 |

### 2.4 Workflow Runtime / Audience / Execution 入口

| Caller 文件 | 入口 / 路径 | 当前 legacy 调用 | 目标 formal contract | 说明 | 优先级 |
| --- | --- | --- | --- | --- | --- |
| `wecom_ability_service/http/automation_conversion.py` | `/api/admin/automation-conversion/workflows` | `list_conversion_workflows`、`create_conversion_workflow` | `ListConversionWorkflowsQuery`、`SaveConversionWorkflowCommand` | workflow CRUD 仍直连 legacy workflow_service | P2 |
| `wecom_ability_service/http/automation_conversion.py` | `/api/admin/automation-conversion/workflows/<workflow_id>` | `get_conversion_workflow_model_bundle`、`update_conversion_workflow`、`delete_conversion_workflow` | `GetConversionWorkflowBundleQuery`、`SaveConversionWorkflowCommand`、`ChangeConversionWorkflowStatusCommand` | workflow editor / delete / update | P2 |
| `wecom_ability_service/http/automation_conversion.py` | `/api/admin/automation-conversion/workflows/<workflow_id>/activate`、`pause` | `activate_conversion_workflow`、`pause_conversion_workflow` | `ChangeConversionWorkflowStatusCommand` | 状态流转仍直连 legacy write | P2 |
| `wecom_ability_service/http/automation_conversion.py` | `/api/admin/automation-conversion/workflows/<workflow_id>/nodes` 等 | `list_conversion_workflow_nodes`、`create_conversion_workflow_node`、`update_conversion_workflow_node`、`delete_conversion_workflow_node` | `ListConversionWorkflowNodesQuery`、`SaveConversionWorkflowNodeCommand`、`DeleteConversionWorkflowNodeCommand` | node CRUD 仍无 formal owner | P2 |
| `wecom_ability_service/http/automation_conversion.py` | `/api/admin/automation-conversion/executions*` | execution list/detail/item legacy functions | `ListConversionWorkflowExecutionsQuery`、`GetConversionWorkflowExecutionDetailQuery` | execution read model 仍散落在 workflow_service | P2 |
| `wecom_ability_service/http/automation_conversion.py` | `/api/admin/automation-conversion/dashboard` | `get_conversion_dashboard_payload` | `GetConversionDashboardQuery` | dashboard 仍走 legacy reader | P2 |
| `wecom_ability_service/http/automation_conversion.py` | `/api/admin/automation-conversion/jobs/run-due` | `run_registered_due_jobs` | `RunRegisteredAutomationDueJobsCommand` | multiplexer 仍在 legacy service | P2 |
| `wecom_ability_service/domains/automation_conversion/service.py` | internal due-job fan-out | `workflow_runtime.run_due_conversion_workflows` | `RunDueConversionWorkflowsCommand` | internal bridge 仍是 service-to-runtime call | P2 |

### 2.5 SOP / Focus Send / Reply Monitor 入口

| Caller 文件 | 入口 / 路径 | 当前 legacy 调用 | 目标 formal contract | 说明 | 优先级 |
| --- | --- | --- | --- | --- | --- |
| `wecom_ability_service/http/automation_conversion.py` | `/api/admin/automation-conversion/sop/config*`、`templates*` | `save_sop_v1_pool_config`、`save_sop_v1_template`、`delete_sop_v1_template_day` | `GetSopManagementPayloadQuery`、`SaveSopPoolConfigCommand`、`SaveSopTemplateCommand`、`DeleteSopTemplateDayCommand` | SOP config/template 仍直连 legacy service | P3 |
| `wecom_ability_service/http/automation_conversion.py` | `/api/admin/automation-conversion/sop/run-due` | `run_due_sop` | `RunDueSopCommand` | due runner 仍在 legacy domain | P3 |
| `wecom_ability_service/http/automation_conversion.py` | `/admin/automation-conversion/programs/<program_id>/member-ops/stage/<stage_key>/send` | `send_stage_manual_message`、`create_focus_send_batch` | `SendStageManualMessageCommand`、`CreateFocusSendBatchCommand` | member-ops no-JS form POST 兜底入口；旧 `/admin/automation-conversion/stage/<stage_key>/send` 已下线 | P3 |
| `wecom_ability_service/http/automation_conversion.py` | `/api/admin/automation-conversion/stage/<stage_key>/focus-send-batches` | `create_focus_send_batch` | `CreateFocusSendBatchCommand` | focus-send batch create 入口 | P3 |
| `wecom_ability_service/http/automation_conversion.py` | `/api/admin/automation-conversion/focus-send-batches/<batch_id>` | `get_focus_send_batch_detail` | `GetFocusSendBatchDetailQuery` | focus-send detail 读面 | P3 |
| `wecom_ability_service/http/automation_conversion.py` | `/api/admin/automation-conversion/focus-send-batches/run-due` | `run_due_focus_send_batches` | `RunDueFocusSendBatchesCommand` | focus-send due runner | P3 |
| `wecom_ability_service/http/automation_conversion.py` | `/admin/automation-conversion/auto-reply/reply-monitor/*`、`/api/admin/automation-conversion/reply-monitor/*` | `save_reply_monitor_enabled`、`run_reply_monitor_capture`、`run_due_reply_monitor` | `SetReplyMonitorEnabledCommand`、`CaptureReplyMonitorQueueCommand`、`RunDueReplyMonitorCommand` | reply monitor 全链仍直连 legacy service；旧浏览器路径 `/admin/automation-conversion/reply-monitor/*` 已下线 | P3 |
| `wecom_ability_service/http/tasks.py` | `/api/tasks/private-message` 等 | `domains.tasks.service.dispatch_wecom_task` | 长期应由 integration/transport owner 收口；Wave 4 只盘 automation caller 依赖 | `tasks` 自身不是 automation owner，但 automation runtime 强依赖它 | P3 |

## 3. 当前跨 context 直连点

### 3.1 Questionnaire -> Automation

当前直连：

- `domains/questionnaire/service.py::submit_questionnaire`
  - lazy import `sync_member_from_questionnaire_submission`

Wave 4 目标：

- 改为 `application/questionnaire/* -> application/automation_engine.SyncQuestionnaireAutomationMemberCommand`

### 3.2 Identity / External Contact Callback -> Automation

当前直连：

- `http/background_jobs.py` 直接调 `handle_qrcode_enter_from_callback`
- `http/customer_automation.py` activation webhook 后直接补 `sync_member_activation`

Wave 4 目标：

- callback / activation caller 统一只调 `application/automation_engine/*`

### 3.3 User Ops / Task Dispatch -> Automation

当前直连：

- `marketing_automation.service` 和 `workflow_runtime.py` 直接依赖 `user_ops.page_service`
- `workflow_runtime.py`、`automation_conversion.service` 直接依赖 `dispatch_wecom_task`

Wave 4 目标：

- caller 层不再知道 `user_ops.page_service` 和 task payload 内部细节
- 这些依赖收敛到 automation implementation / adapter，不再暴露到 controller

### 3.4 Customer Read Model -> Automation

当前直连：

- `http/customer_automation.py::_candidate_context`
- MCP / admin console 里仍有 customer context 自拼逻辑

Wave 4 目标：

- customer context 只通过 `application/customer_read_model/*`
- 任何 candidate context 聚合都不再留在 controller

## 4. 当前不作为第一批 cutover 的邻接点

以下 caller 虽然位于 automation 页面或包内，但不进入 Wave 4 第一批收口：

- `http/automation_conversion.py` 里的 agent orchestration / review output / router callback / model infra 相关路径
- `domains/automation_conversion/orchestration_service.py`
- `application/integration_gateway/mcp_dispatch.py` 中与 agent orchestration 直接相关的 tool surface

这些内容需要在 automation base owner 稳定后单独评估，不应与 signup conversion / member state / workflow runtime 混在同一批。

## 5. 结论

Wave 4 caller cutover 应按下面的顺序推进：

1. `admin_config` + `customer_automation` + `admin_jobs`
2. `sidebar` + `admin_support` + `background_jobs`
3. `http/automation_conversion.py` 的 member-state / overview-stage
4. `http/automation_conversion.py` 的 workflow runtime / audience / execution
5. `http/automation_conversion.py` 的 SOP / focus send / reply monitor
6. `domains/admin_console/service.py` + `application/integration_gateway/mcp_dispatch.py` 的残余 bypass

不按这个顺序做，风险会重新回到 `http/automation_conversion.py` 这个超大入口上。
