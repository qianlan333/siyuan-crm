# Wave 4 Automation Engine Contracts

日期：2026-04-21

## 1. 目标

本文只定义 Automation Engine 的正式 contract 草案，不改业务代码。

正式 contract 的目标：

- 让 admin / callback / retry / member-state / workflow runtime caller 有唯一 formal owner
- 让 controller、admin console、MCP dispatch 不再直接依赖 `services.py` 或 legacy domain service
- 让 automation 对 `identity` / `user_ops` / `questionnaire` / `customer read model` 的依赖变成显式 application port

建议命名空间：

- `wecom_ability_service/application/automation_engine/queries.py`
- `wecom_ability_service/application/automation_engine/commands.py`
- `wecom_ability_service/application/automation_engine/dto.py`
- `wecom_ability_service/application/automation_engine/_legacy_delegate.py`

其中，Wave 1 已存在的 contract 继续保留并扩展，不推翻已有命名。

## 2. Signup Conversion / Marketing Truth

| Contract | 输入 DTO | 输出 DTO | 当前 legacy 入口 | 直接调用方 | 跨 context 副作用 | 禁止继续绕过的旧入口 | 兼容策略 | 推荐切换顺序 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GetSignupConversionConfigQuery` | `SignupConversionConfigQueryDTO { request_meta }` | `SignupConversionConfigResultDTO { config }` | `services.get_signup_conversion_config` -> `domains.marketing_automation.service.get_signup_conversion_config` | `http/admin_config.py` | 无写副作用 | `services.get_signup_conversion_config` | 先建 formal read，再切 admin config | 1 |
| `SaveSignupConversionConfigCommand` | `SignupConversionConfigCommandDTO { payload, operator, request_meta }` | `SignupConversionConfigCommandResultDTO { ok, config }` | `services.save_signup_conversion_config` -> `domains.marketing_automation.service.save_signup_conversion_config` | `http/admin_config.py` | 读取 questionnaire 定义；更新 config / rules | `services.save_signup_conversion_config` | 保持现有 UI payload 与错误语义 | 1 |
| `PreviewSignupConversionCustomerQuery` | `SignupConversionPreviewQueryDTO { external_userid?, phone?, request_meta }` | `SignupConversionPreviewResultDTO { preview }` | `services.preview_signup_conversion_customer` -> `domains.marketing_automation.service.preview_signup_conversion_customer` | `http/admin_config.py`、`http/sidebar.py` | 读取 customer/questionnaire truth；无写副作用 | `services.preview_signup_conversion_customer` | 先切 preview，冻结当前 preview payload | 1 |
| `RecomputeSignupConversionCustomersCommand` | `SignupConversionRecomputeCommandDTO { external_userid?, limit?, operator, request_meta }` | `SignupConversionRecomputeResultDTO { ok, updated_count, warnings[] }` | `services.recompute_signup_conversion_customers` -> `domains.marketing_automation.service.recompute_signup_conversion_customers` | `http/admin_config.py` | 写 marketing truth/history | `services.recompute_signup_conversion_customers` | 保持结果 summary 和 audit 语义 | 1 |
| `ListSignupConversionBatchesQuery` | `SignupConversionBatchListQueryDTO { limit, cursor?, scenario_key?, request_meta }` | `SignupConversionBatchListResultDTO { rows[], next_cursor?, count }` | `services.list_signup_conversion_batches` -> `domains.marketing_automation.service.list_signup_conversion_batches` | `http/customer_automation.py`、MCP tool | 读 batch read model；可依赖 customer read model | `services.list_signup_conversion_batches` | 保持 Wave 1 已建立 contract | 1 |
| `GetSignupConversionBatchQuery` | `SignupConversionBatchDetailQueryDTO { batch_id, scenario_key?, include_customer_context?, request_meta }` | `SignupConversionBatchDetailResultDTO { batch }` | `services.get_signup_conversion_batch` -> `domains.marketing_automation.service.get_signup_conversion_batch` | `http/customer_automation.py`、MCP tool | 读 batch detail；可消费 customer read model | `services.get_signup_conversion_batch`、`http/customer_automation.py::_candidate_context` | 维持 Wave 1 contract，后续把 customer context 聚合下沉 | 1 |
| `RecordConversionFeedbackCommand` | `ConversionFeedbackCommandDTO { batch_id, action, operator, notes?, request_meta }` | `ConversionFeedbackResultDTO { ok, batch_status, audit_ref }` | `services.record_conversion_feedback` -> `domains.tasks.service.record_conversion_feedback` | MCP、admin console、未来 admin ops | 通过 tasks 反馈回写 marketing truth；可能触发 enrolled / unenrolled | `services.record_conversion_feedback`、`domains.tasks.service.record_conversion_feedback` | 保留当前反馈结果结构 | 2 |
| `AcknowledgeConversionBatchCommand` | `ConversionBatchAckCommandDTO { batch_id, operator, request_meta }` | `ConversionBatchAckResultDTO { ok, batch_status }` | `services.ack_conversion_batch` -> `domains.marketing_automation.service.ack_conversion_batch` | MCP / OpenClaw 兼容入口、admin jobs | 写 dispatch log ack 状态 | `services.ack_conversion_batch` | 先收口 tool/admin caller，不动 batch schema | 2 |
| `GetCustomerMarketingProfileQuery` | `CustomerMarketingProfileQueryDTO { external_userid, request_meta }` | `CustomerMarketingProfileResultDTO { profile }` | `services.get_customer_marketing_profile` -> `domains.marketing_automation.service.get_customer_marketing_profile` | `http/sidebar.py`、MCP tool | 读 customer/questionnaire/value-segment truth | `services.get_customer_marketing_profile`、`domains.marketing_automation.service.get_customer_marketing_profile` | 保留 sidebar JSON key | 2 |
| `MarkEnrolledCommand` | `MarkEnrolledCommandDTO { external_userid, operator, source?, request_meta }` | `MarkEnrolledResultDTO { ok, conversion, class_user_sync }` | `services.mark_enrolled` -> `domains.marketing_automation.service.mark_enrolled` | `http/sidebar.py`、`http/admin_support.py`、MCP tool、`domains/tasks.service.record_conversion_feedback` | 调 `application/class_user/*`，并清理 pending conversion dispatch | `services.mark_enrolled`、`domains.marketing_automation.service.mark_enrolled` | 保持 class-user 副作用与历史写入行为 | 2 |
| `UnmarkEnrolledCommand` | `UnmarkEnrolledCommandDTO { external_userid, operator, source?, request_meta }` | `UnmarkEnrolledResultDTO { ok, conversion, class_user_sync }` | `services.unmark_enrolled` -> `domains.marketing_automation.service.unmark_enrolled` | `http/sidebar.py`、`http/admin_support.py`、MCP tool、`domains/tasks.service.record_conversion_feedback` | 调 `application/class_user/*` 回退 truth | `services.unmark_enrolled`、`domains.marketing_automation.service.unmark_enrolled` | 保持 manual rollback 行为 | 2 |
| `SetManualFollowupSegmentCommand` | `ManualFollowupSegmentCommandDTO { external_userid, segment, operator, request_meta }` | `ManualFollowupSegmentResultDTO { ok, profile }` | `services.set_manual_followup_segment` -> `domains.marketing_automation.service.set_manual_followup_segment` | `http/sidebar.py` | 写 marketing truth/history | `services.set_manual_followup_segment` | 保持 sidebar 展示字段不变 | 2 |

## 3. Member State / Callback / Lifecycle Bridge

| Contract | 输入 DTO | 输出 DTO | 当前 legacy 入口 | 直接调用方 | 跨 context 副作用 | 禁止继续绕过的旧入口 | 兼容策略 | 推荐切换顺序 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GetAutomationOverviewQuery` | `AutomationOverviewQueryDTO { request_meta }` | `AutomationOverviewResultDTO { overview }` | `domains.automation_conversion.service.get_overview_payload` | `http/automation_conversion.py` | 读 member stage board / counters | `domains.automation_conversion.service.get_overview_payload` | 保持 overview payload 与 stage cards 不变 | 3 |
| `GetAutomationStageDetailQuery` | `AutomationStageDetailQueryDTO { route_key, keyword?, limit?, offset?, request_meta }` | `AutomationStageDetailResultDTO { route, rows[], summary }` | `domains.automation_conversion.service.get_stage_detail_payload` | `http/automation_conversion.py` | 读 stage read model | `domains.automation_conversion.service.get_stage_detail_payload` | 保持 stage detail filter / paging 结构 | 3 |
| `GetAutomationMemberDetailQuery` | `AutomationMemberDetailQueryDTO { external_contact_id?, phone?, request_meta }` | `AutomationMemberDetailResultDTO { member }` | `domains.automation_conversion.service.get_member_detail` | `http/automation_conversion.py` | 读 questionnaire truth / marketing truth / recent activity | `domains.automation_conversion.service.get_member_detail` | 保持 member payload 结构 | 3 |
| `ChangeAutomationMemberPoolStateCommand` | `AutomationMemberPoolStateCommandDTO { action, external_contact_id?, phone?, operator_id, request_meta }` | `AutomationMemberPoolStateResultDTO { ok, member, transition }` | `domains.automation_conversion.service.put_in_pool`、`remove_from_pool`、`set_follow_type`、`mark_won`、`unmark_won` | `http/automation_conversion.py` | 写 member current/history；可能影响 workflow audience / SOP | 直接 import `put_in_pool`、`remove_from_pool`、`set_follow_type`、`mark_won`、`unmark_won` | 用 `action` 收口多条 member mutation，但保留旧 symbol shim | 3 |
| `PushOpenClawCommand` | `PushOpenClawCommandDTO { external_contact_id?, phone?, operator_id, request_meta }` | `PushOpenClawResultDTO { ok, delivery, push_log }` | `domains.automation_conversion.service.push_openclaw` | `http/automation_conversion.py` | outbound webhook send / push log write | `domains.automation_conversion.service.push_openclaw` | 保持 push result 与失败语义 | 3 |
| `HandleQrCodeEnterCallbackCommand` | `QrCodeEnterCallbackCommandDTO { corp_id, external_userid, state?, channel?, operator_id, request_meta }` | `QrCodeEnterCallbackResultDTO { ok, member, warnings[] }` | `domains.automation_conversion.service.handle_qrcode_enter_from_callback` | `http/background_jobs.py` | member mutation、welcome / tag / SOP bridge | `domains.automation_conversion.service.handle_qrcode_enter_from_callback` | 先切 callback caller，不重写内部规则 | 3 |
| `ApplyActivationWebhookCommand` | `ActivationWebhookCommandDTO { mobile, activated_at?, operator?, source?, request_meta }` | `ActivationWebhookResultDTO { ok, customer, warnings[] }` | `services.apply_activation_webhook` -> `domains.marketing_automation.service.apply_activation_webhook` | `http/customer_automation.py` | identity resolve + marketing truth update + member sync | `services.apply_activation_webhook` | 保持 Wave 1 已建 contract；补齐 caller map | 3 |
| `SyncAutomationMemberActivationCommand` | `AutomationMemberActivationCommandDTO { external_contact_id?, phone?, operator_id, request_meta }` | `AutomationMemberActivationResultDTO { ok, member_id?, sync_status, warnings[] }` | `domains.automation_conversion.service.sync_member_activation` | `http/customer_automation.py`、activation webhook bridge | member current/history sync | `domains.automation_conversion.service.sync_member_activation` | 保持 Wave 1 contract；后续让 activation caller 只经过 application | 3 |
| `SyncQuestionnaireAutomationMemberCommand` | `QuestionnaireAutomationMemberSyncCommandDTO { external_contact_id?, phone?, operator_id, request_meta }` | `QuestionnaireAutomationMemberSyncResultDTO { ok, member_id?, sync_status, warnings[] }` | `domains.automation_conversion.service.sync_member_from_questionnaire_submission` | `application/questionnaire/*` / legacy questionnaire bridge | questionnaire -> automation member sync | `domains.automation_conversion.service.sync_member_from_questionnaire_submission` | 显式化 questionnaire bridge，不再靠 lazy import | 4 |

## 4. Outbound Webhook / Retry / Due Runner

| Contract | 输入 DTO | 输出 DTO | 当前 legacy 入口 | 直接调用方 | 跨 context 副作用 | 禁止继续绕过的旧入口 | 兼容策略 | 推荐切换顺序 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `ListOutboundWebhookDeliveriesQuery` | `OutboundWebhookListQueryDTO { event_type?, status?, limit?, request_meta }` | `OutboundWebhookListResultDTO { items[], summary }` | `services.list_outbound_webhook_deliveries` -> `domains.outbound_webhook.service.list_outbound_webhook_deliveries` | `http/customer_automation.py`、`domains/admin_jobs/service.py` | 无写副作用 | `services.list_outbound_webhook_deliveries` | 保持 Wave 1 contract；切 admin jobs / customer automation | 1 |
| `GetOutboundWebhookDeliveryCountsQuery` | `OutboundWebhookCountQueryDTO { request_meta }` | `OutboundWebhookCountResultDTO { counts }` | `services.get_outbound_webhook_delivery_counts` -> `domains.outbound_webhook.service.get_outbound_webhook_delivery_counts` | `domains/admin_jobs/service.py` | 无写副作用 | `services.get_outbound_webhook_delivery_counts` | 配合 admin jobs read model 一起切 | 1 |
| `RetryOutboundWebhookDeliveryCommand` | `OutboundWebhookRetryCommandDTO { delivery_id, operator, request_meta }` | `OutboundWebhookRetryResultDTO { ok, delivery, warnings[] }` | `services.retry_outbound_webhook_delivery` -> `domains.outbound_webhook.service.retry_outbound_webhook_delivery` | `http/customer_automation.py`、`domains/admin_jobs/service.py` | 写 delivery retry 状态 | `services.retry_outbound_webhook_delivery` | 保持 Wave 1 contract；切 admin jobs / customer automation | 1 |
| `RunDueOutboundWebhookRetriesCommand` | `OutboundWebhookRetryBatchCommandDTO { limit=20, operator?, request_meta }` | `OutboundWebhookRetryBatchResultDTO { ok, scanned_count?, retried_count, warnings[] }` | `services.run_due_outbound_webhook_retries` -> `domains.outbound_webhook.service.run_due_outbound_webhook_retries` | `http/customer_automation.py`、`domains/admin_jobs/service.py` | 写 due retry 结果 | `services.run_due_outbound_webhook_retries` | 保持 Wave 1 contract；把 due runner caller 一起切 | 1 |
| `DispatchAutomationOutboundWebhookCommand` | `AutomationOutboundWebhookCommandDTO { event_type, payload, operator?, request_meta }` | `AutomationOutboundWebhookResultDTO { ok, delivery }` | `domains.outbound_webhook.service.send_outbound_webhook` | `domains.marketing_automation.service`、`domains.automation_conversion.service` | 对外 HTTP transport / delivery log 写入 | `domains.outbound_webhook.service.send_outbound_webhook` | 作为 automation 内部稳定 command，不直接暴露给 controller | 4 |

## 5. Workflow Runtime / Audience / Execution

| Contract | 输入 DTO | 输出 DTO | 当前 legacy 入口 | 直接调用方 | 跨 context 副作用 | 禁止继续绕过的旧入口 | 兼容策略 | 推荐切换顺序 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `ListConversionWorkflowsQuery` | `ConversionWorkflowListQueryDTO { include_archived?=false, status?, request_meta }` | `ConversionWorkflowListResultDTO { items[] }` | `domains.automation_conversion.workflow_service.list_conversion_workflows` | `http/automation_conversion.py` | 无写副作用 | `domains.automation_conversion.workflow_service.list_conversion_workflows` | 先切 workflow list/detail reader | 4 |
| `GetConversionWorkflowBundleQuery` | `ConversionWorkflowBundleQueryDTO { workflow_id, request_meta }` | `ConversionWorkflowBundleResultDTO { workflow, registry, related }` | `domains.automation_conversion.workflow_service.get_conversion_workflow_model_bundle` | `http/automation_conversion.py` | 无写副作用 | `domains.automation_conversion.workflow_service.get_conversion_workflow_model_bundle` | 保持 workflow editor payload | 4 |
| `SaveConversionWorkflowCommand` | `SaveConversionWorkflowCommandDTO { workflow_id?, payload, operator_id, request_meta }` | `SaveConversionWorkflowResultDTO { workflow }` | `domains.automation_conversion.workflow_service.create_conversion_workflow`、`update_conversion_workflow` | `http/automation_conversion.py` | 写 workflow model | 直接 import `create_conversion_workflow`、`update_conversion_workflow` | 用一个 save command 收口 create/update | 4 |
| `ChangeConversionWorkflowStatusCommand` | `ChangeConversionWorkflowStatusCommandDTO { workflow_id, action, operator_id, request_meta }` | `ChangeConversionWorkflowStatusResultDTO { workflow }` | `activate_conversion_workflow`、`pause_conversion_workflow`、`delete_conversion_workflow` | `http/automation_conversion.py` | 写 workflow status | 直接 import activate/pause/delete legacy functions | 用 `action` 收口状态流转，但保留旧 symbol | 4 |
| `ListConversionWorkflowNodesQuery` | `ConversionWorkflowNodesQueryDTO { workflow_id, request_meta }` | `ConversionWorkflowNodesResultDTO { nodes[] }` | `domains.automation_conversion.workflow_service.list_conversion_workflow_nodes` | `http/automation_conversion.py` | 无写副作用 | `domains.automation_conversion.workflow_service.list_conversion_workflow_nodes` | 保持 node builder payload | 4 |
| `SaveConversionWorkflowNodeCommand` | `SaveConversionWorkflowNodeCommandDTO { workflow_id?, node_id?, payload, operator_id, request_meta }` | `SaveConversionWorkflowNodeResultDTO { node }` | `create_conversion_workflow_node`、`update_conversion_workflow_node` | `http/automation_conversion.py` | 写 workflow node | 直接 import create/update node legacy functions | 收口 node create/update | 4 |
| `DeleteConversionWorkflowNodeCommand` | `DeleteConversionWorkflowNodeCommandDTO { node_id, request_meta }` | `DeleteConversionWorkflowNodeResultDTO { deleted }` | `domains.automation_conversion.workflow_service.delete_conversion_workflow_node` | `http/automation_conversion.py` | 删除 workflow node | `domains.automation_conversion.workflow_service.delete_conversion_workflow_node` | 保持 delete 语义 | 4 |
| `ListConversionProfileSegmentTemplatesQuery` | `ConversionProfileSegmentTemplateListQueryDTO { request_meta }` | `ConversionProfileSegmentTemplateListResultDTO { items[], catalog }` | `list_conversion_profile_segment_templates`、`list_conversion_profile_segment_catalog` | `http/automation_conversion.py`、MCP | 无写副作用 | workflow_service template legacy functions | profile segment template 先按读面收口 | 4 |
| `SaveConversionProfileSegmentTemplateCommand` | `ConversionProfileSegmentTemplateCommandDTO { template_id?, payload, operator_id, request_meta }` | `ConversionProfileSegmentTemplateCommandResultDTO { template }` | `create_conversion_profile_segment_template`、`update_conversion_profile_segment_template` | `http/automation_conversion.py` | 写 profile segment template | legacy template create/update | 保持 admin template editor 结构 | 4 |
| `ListConversionWorkflowExecutionsQuery` | `ConversionWorkflowExecutionListQueryDTO { workflow_id?, node_id?, limit?, request_meta }` | `ConversionWorkflowExecutionListResultDTO { items[] }` | `list_conversion_workflow_executions`、`list_conversion_workflow_execution_records` | `http/automation_conversion.py` | 无写副作用 | workflow execution list legacy functions | 先切 execution 列表 / records | 5 |
| `GetConversionWorkflowExecutionDetailQuery` | `ConversionWorkflowExecutionDetailQueryDTO { execution_id, request_meta }` | `ConversionWorkflowExecutionDetailResultDTO { execution, items, detail }` | `get_conversion_workflow_execution_bundle`、`get_conversion_workflow_execution_detail`、`list_conversion_workflow_execution_items`、`get_conversion_workflow_execution_item_detail` | `http/automation_conversion.py` | 无写副作用 | direct workflow execution detail legacy functions | 保持 execution detail / item detail payload | 5 |
| `GetConversionDashboardQuery` | `ConversionDashboardQueryDTO { request_meta }` | `ConversionDashboardResultDTO { dashboard }` | `domains.automation_conversion.workflow_service.get_conversion_dashboard_payload` | `http/automation_conversion.py` | 无写副作用 | `domains.automation_conversion.workflow_service.get_conversion_dashboard_payload` | 保持 dashboard cards 与 summary | 5 |
| `RunDueConversionWorkflowsCommand` | `RunDueConversionWorkflowsCommandDTO { operator_id, request_meta }` | `RunDueConversionWorkflowsResultDTO { ok, run_summary }` | `domains.automation_conversion.workflow_runtime.run_due_conversion_workflows` | `http/automation_conversion.py` internal jobs endpoint、scripts | audience sync、task dispatch、execution write | `domains.automation_conversion.workflow_runtime.run_due_conversion_workflows` | 保持 due job 主结果结构 | 5 |
| `SyncConversionMemberAudienceCommand` | `ConversionAudienceSyncCommandDTO { member, operator_id?, request_meta }` | `ConversionAudienceSyncResultDTO { ok, audience_state }` | `domains.automation_conversion.workflow_runtime.sync_conversion_member_audience` | workflow runtime internal、future callback bridges | 写 audience current/history | `domains.automation_conversion.workflow_runtime.sync_conversion_member_audience` | 初期 internal-only command | 5 |
| `SyncAllConversionMemberAudiencesCommand` | `ConversionAudienceSweepCommandDTO { operator_id?, request_meta }` | `ConversionAudienceSweepResultDTO { ok, updated_count }` | `domains.automation_conversion.workflow_runtime.sync_all_conversion_member_audiences` | internal jobs / admin ops | 写 audience sweep 结果 | `domains.automation_conversion.workflow_runtime.sync_all_conversion_member_audiences` | 初期 internal-only command | 5 |

## 6. SOP / Focus Send / Reply Monitor

| Contract | 输入 DTO | 输出 DTO | 当前 legacy 入口 | 直接调用方 | 跨 context 副作用 | 禁止继续绕过的旧入口 | 兼容策略 | 推荐切换顺序 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GetSopManagementPayloadQuery` | `SopManagementQueryDTO { request_meta }` | `SopManagementResultDTO { config, templates, batches }` | `get_sop_v1_management_payload`、`get_sop_v1_config_payload`、`get_sop_v1_templates_payload`、`get_sop_v1_batches_payload` | `http/automation_conversion.py` | 无写副作用 | SOP payload legacy readers | 先 formalize SOP admin read | 6 |
| `SaveSopPoolConfigCommand` | `SopPoolConfigCommandDTO { pool_key, payload, operator_id, request_meta }` | `SopPoolConfigResultDTO { config }` | `domains.automation_conversion.service.save_sop_v1_pool_config` | `http/automation_conversion.py` | 写 SOP pool config | `domains.automation_conversion.service.save_sop_v1_pool_config` | 保持现有 pool config editor 结构 | 6 |
| `SaveSopTemplateCommand` | `SopTemplateCommandDTO { pool_key, day_index, payload, operator_id, request_meta }` | `SopTemplateResultDTO { template }` | `domains.automation_conversion.service.save_sop_v1_template` | `http/automation_conversion.py` | 写 SOP template | `domains.automation_conversion.service.save_sop_v1_template` | 保持模板保存 payload | 6 |
| `DeleteSopTemplateDayCommand` | `SopTemplateDeleteCommandDTO { pool_key, day_index, operator_id, request_meta }` | `SopTemplateDeleteResultDTO { deleted, templates }` | `domains.automation_conversion.service.delete_sop_v1_template_day` | `http/automation_conversion.py` | 删除并重排 template day | `domains.automation_conversion.service.delete_sop_v1_template_day` | 保持 delete 后返回结构 | 6 |
| `RunDueSopCommand` | `SopRunDueCommandDTO { operator_id, request_meta }` | `SopRunDueResultDTO { ok, batches, summary }` | `domains.automation_conversion.service.run_due_sop` | `http/automation_conversion.py`、scripts | dispatch task、write SOP progress / locks | `domains.automation_conversion.service.run_due_sop` | 保持 due runner 结果与锁语义 | 6 |
| `CreateFocusSendBatchCommand` | `FocusSendBatchCommandDTO { stage_key, payload, operator_id, request_meta }` | `FocusSendBatchCommandResultDTO { batch }` | `domains.automation_conversion.service.create_focus_send_batch` | `http/automation_conversion.py` | 写 focus batch / items | `domains.automation_conversion.service.create_focus_send_batch` | 保持 focus send 创建结果结构 | 6 |
| `GetFocusSendBatchDetailQuery` | `FocusSendBatchDetailQueryDTO { batch_id, item_limit?, request_meta }` | `FocusSendBatchDetailResultDTO { batch }` | `domains.automation_conversion.service.get_focus_send_batch_detail` | `http/automation_conversion.py` | 无写副作用 | `domains.automation_conversion.service.get_focus_send_batch_detail` | 保持 batch detail 页面结构 | 6 |
| `RunDueFocusSendBatchesCommand` | `FocusSendRunDueCommandDTO { operator_id, request_meta }` | `FocusSendRunDueResultDTO { ok, batches, summary }` | `domains.automation_conversion.service.run_due_focus_send_batches` | `http/automation_conversion.py` | dispatch task、write batch/item status | `domains.automation_conversion.service.run_due_focus_send_batches` | 保持 partial failure 语义 | 6 |
| `SetReplyMonitorEnabledCommand` | `ReplyMonitorToggleCommandDTO { enabled, operator_id, request_meta }` | `ReplyMonitorToggleResultDTO { ok, enabled }` | `domains.automation_conversion.service.save_reply_monitor_enabled` | `http/automation_conversion.py` | 写 reply monitor config | `domains.automation_conversion.service.save_reply_monitor_enabled` | 保持 toggle 结果结构 | 6 |
| `CaptureReplyMonitorQueueCommand` | `ReplyMonitorCaptureCommandDTO { operator_id, request_meta }` | `ReplyMonitorCaptureResultDTO { ok, captured_count, warnings[] }` | `domains.automation_conversion.service.run_reply_monitor_capture` | `http/automation_conversion.py` | 读 archive/inbound message、写 pending queue | `domains.automation_conversion.service.run_reply_monitor_capture` | 保持 capture quiet-hours / cursor 语义 | 6 |
| `RunDueReplyMonitorCommand` | `ReplyMonitorRunDueCommandDTO { operator_id, request_meta }` | `ReplyMonitorRunDueResultDTO { ok, dispatched_count, warnings[] }` | `domains.automation_conversion.service.run_due_reply_monitor` | `http/automation_conversion.py` | router dispatch / async callback / queue status write | `domains.automation_conversion.service.run_due_reply_monitor` | 保持 due dispatch 节流与 shadow-mode 语义 | 6 |
| `RunRegisteredAutomationDueJobsCommand` | `AutomationDueJobsCommandDTO { operator_id, jobs[], request_meta }` | `AutomationDueJobsResultDTO { ok, jobs[] }` | `domains.automation_conversion.service.run_registered_due_jobs` | `http/automation_conversion.py` internal jobs endpoint、scripts | fan-out 到 SOP / workflow runtime | `domains.automation_conversion.service.run_registered_due_jobs` | 先保留 multiplexer，再逐步把子 job 收口到 formal command | 6 |

## 7. 当前不纳入第一批 formal contract 的相邻面

以下内容当前仍在 `http/automation_conversion.py` / `domains/automation_conversion/orchestration_service.py`，但不纳入 Wave 4 第一批 formal contract：

- agent orchestration
- agent prompt draft / publish
- review output / router callback replay
- model infra / default channel / provider settings

这些内容仍属于 automation 邻接能力，但不应和 member-state / workflow runtime / retry 主线混在同一批 caller cutover 里。

## 8. 禁止绕过的旧入口

从 Wave 4 开始，下列入口应视为 legacy bypass：

- `services.get_signup_conversion_config`
- `services.save_signup_conversion_config`
- `services.preview_signup_conversion_customer`
- `services.recompute_signup_conversion_customers`
- `services.list_signup_conversion_batches`
- `services.get_signup_conversion_batch`
- `services.record_conversion_feedback`
- `services.ack_conversion_batch`
- `services.get_customer_marketing_profile`
- `services.mark_enrolled`
- `services.unmark_enrolled`
- `services.set_manual_followup_segment`
- `domains.automation_conversion.service.handle_qrcode_enter_from_callback`
- `domains.automation_conversion.service.get_overview_payload`
- `domains.automation_conversion.service.get_stage_detail_payload`
- `domains.automation_conversion.service.get_member_detail`
- `domains.automation_conversion.service.put_in_pool`
- `domains.automation_conversion.service.remove_from_pool`
- `domains.automation_conversion.service.set_follow_type`
- `domains.automation_conversion.service.mark_won`
- `domains.automation_conversion.service.unmark_won`
- `domains.automation_conversion.service.push_openclaw`
- `domains.automation_conversion.workflow_service.*`
- `domains.automation_conversion.workflow_runtime.*`
- `domains.outbound_webhook.service.retry_outbound_webhook_delivery`
- `domains.outbound_webhook.service.run_due_outbound_webhook_retries`

历史兼容 wrapper 可以暂时保留，但新的 caller 不应再直接引入它们。

## 9. 推荐切换顺序

1. `GetSignupConversionConfigQuery`
2. `SaveSignupConversionConfigCommand`
3. `PreviewSignupConversionCustomerQuery`
4. `RecomputeSignupConversionCustomersCommand`
5. `ListSignupConversionBatchesQuery`
6. `GetSignupConversionBatchQuery`
7. `ListOutboundWebhookDeliveriesQuery`
8. `GetOutboundWebhookDeliveryCountsQuery`
9. `RetryOutboundWebhookDeliveryCommand`
10. `RunDueOutboundWebhookRetriesCommand`
11. `RecordConversionFeedbackCommand`
12. `AcknowledgeConversionBatchCommand`
13. `GetCustomerMarketingProfileQuery`
14. `MarkEnrolledCommand`
15. `UnmarkEnrolledCommand`
16. `SetManualFollowupSegmentCommand`
17. `GetAutomationOverviewQuery`
18. `GetAutomationStageDetailQuery`
19. `GetAutomationMemberDetailQuery`
20. `ChangeAutomationMemberPoolStateCommand`
21. `PushOpenClawCommand`
22. `HandleQrCodeEnterCallbackCommand`
23. `ApplyActivationWebhookCommand`
24. `SyncAutomationMemberActivationCommand`
25. `SyncQuestionnaireAutomationMemberCommand`
26. `ListConversionWorkflowsQuery`
27. `GetConversionWorkflowBundleQuery`
28. `SaveConversionWorkflowCommand`
29. `ChangeConversionWorkflowStatusCommand`
30. `ListConversionWorkflowNodesQuery`
31. `SaveConversionWorkflowNodeCommand`
32. `DeleteConversionWorkflowNodeCommand`
33. `ListConversionProfileSegmentTemplatesQuery`
34. `SaveConversionProfileSegmentTemplateCommand`
35. `ListConversionWorkflowExecutionsQuery`
36. `GetConversionWorkflowExecutionDetailQuery`
37. `GetConversionDashboardQuery`
38. `RunDueConversionWorkflowsCommand`
39. `SyncConversionMemberAudienceCommand`
40. `SyncAllConversionMemberAudiencesCommand`
41. `GetSopManagementPayloadQuery`
42. `SaveSopPoolConfigCommand`
43. `SaveSopTemplateCommand`
44. `DeleteSopTemplateDayCommand`
45. `RunDueSopCommand`
46. `CreateFocusSendBatchCommand`
47. `GetFocusSendBatchDetailQuery`
48. `RunDueFocusSendBatchesCommand`
49. `SetReplyMonitorEnabledCommand`
50. `CaptureReplyMonitorQueueCommand`
51. `RunDueReplyMonitorCommand`
52. `RunRegisteredAutomationDueJobsCommand`

## 10. 结论

Wave 4 的关键不是先拆内部大文件，而是先让 Automation Engine 拥有一套完整、显式、可被 caller 依赖的 formal contract。

没有这套 contract，后续任何“拆 `automation_conversion/service.py`”都会把风险直接转移到 controller 和 admin console。
