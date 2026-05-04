# Application Contract Catalog

日期：2026-04-17

状态：Draft for execution

目标：

- 为每个 context 定义正式 application API
- 让跨 context 调用从“直接 import service/repo”收口为“调用稳定 contract”
- 为 Wave 1 入口收口提供统一替换表

## 1. 统一约定

### 1.1 命名

- 读操作统一命名为 `*Query`
- 写操作统一命名为 `*Command`
- 返回值统一使用 `*ResultDTO`

### 1.2 DTO 约定

- DTO 是跨 context 的稳定边界，不暴露底层 repo row
- DTO 可以兼容现有 HTTP / MCP contract，但不能直接等同于某个历史函数返回值
- DTO 允许新增字段，但不允许在未声明情况下删除现有稳定字段

### 1.3 调用规则

- `api` 层只能调 application API
- 跨 context 只能调 application API
- 旧入口仅允许作为兼容 shim 存在，不允许新增调用方

## 2. Context Catalog

### 2.1 Integration Gateway

| command/query 名称 | 输入 DTO | 输出 DTO | 调用方 | 可依赖的上下文 | 禁止绕过该 API 的旧入口 |
| --- | --- | --- | --- | --- | --- |
| `HandleWeComExternalContactCallbackCommand` | `ExternalContactCallbackCommandDTO { encrypted_payload, signature, timestamp, nonce, request_meta }` | `ExternalContactCallbackResultDTO { ok, event_log_id, status, background_job_id?, warnings[] }` | `http/callbacks.py`、`callback_runtime.py` | `Platform Foundation`、`Identity & Contact Graph`、`Automation Engine` | `wecom_ability_service.http.callbacks` 内联业务分支、`domains.callbacks.service` 被其他 context 直调 |
| `SyncWeComContactsCommand` | `ContactSyncCommandDTO { owner_userid?, mode, cursor?, batch_size?, request_meta }` | `ContactSyncResultDTO { ok, synced_count, next_cursor?, warnings[] }` | `http/contacts.py`、后台 jobs | `Platform Foundation`、`Identity & Contact Graph` | controller 直接调 `WeComClient`、controller 直接写 contacts SQL |
| `GetArchivedMessagesQuery` | `ArchivedMessageQueryDTO { external_userid, chat_type?, limit, offset, request_meta }` | `ArchivedMessageResultDTO { items[], count, total, filters }` | `http/archive.py`、`Customer Read Model` | `Platform Foundation` | `wecom_ability_service.services.get_messages_by_user`、`archive.repo` 被 controller 直连 |
| `DispatchWeComTaskCommand` | `WeComTaskCommandDTO { task_type, target, payload, dry_run?, request_meta }` | `WeComTaskResultDTO { ok, task_id?, preview?, delivery_status, warnings[] }` | `http/tasks.py`、`Automation Engine`、`AI Assist` | `Platform Foundation`、`Identity & Contact Graph` | `wecom_ability_service.services.save_outbound_task`、`domains.tasks.service.dispatch_wecom_task` 被跨 context 直调 |
| `DispatchMcpToolCommand` | `McpToolDispatchCommandDTO { tool_name, arguments, operator, permission_scope?, live_run?, request_meta }` | `McpToolDispatchResultDTO { ok, payload, structured_content?, audit_ref?, warnings[] }` | `wecom_ability_service.mcp_adapter` 仅此一处 | `Platform Foundation`、`Customer Read Model`、`Automation Engine`、`Identity & Contact Graph` | `mcp_adapter.py` 内的 `_build_customer_context_payload`、`_update_customer_tags`、`_call_business_task`、`_call_wecom_task` |

补充说明：

- `HandleWeComExternalContactCallbackCommand` 不再声明依赖 `Ops & Enrollment`，因为 callback 在 Wave 1 口径中只负责接入分发，不直接执行业务运营状态变更

### 2.2 Identity & Contact Graph

| command/query 名称 | 输入 DTO | 输出 DTO | 调用方 | 可依赖的上下文 | 禁止绕过该 API 的旧入口 |
| --- | --- | --- | --- | --- | --- |
| `ResolvePersonIdentityQuery` | `IdentityResolveQueryDTO { external_userid?, mobile?, unionid?, openid?, request_meta }` | `IdentityResolveResultDTO { person_id?, external_userid?, mobile?, unionid?, openid?, binding_status, owner_userid?, follow_users[] }` | `http/identity.py`、`Questionnaire`、`Customer Read Model`、`Ops & Enrollment` | `Platform Foundation` | `wecom_ability_service.domains.identity.service.resolve_external_contact_identity`、`wecom_ability_service.services.resolve_person_identity` |
| `GetContactSnapshotQuery` | `ContactSnapshotQueryDTO { external_userid, refresh_tags?=false, request_meta }` | `ContactSnapshotResultDTO { contact, tags[], owner_userid, follow_users[], updated_at }` | `Customer Read Model`、`Integration Gateway`、`Automation Engine` | `Platform Foundation`、`Integration Gateway` | `domains.contacts.service.*`、`domains.tags.repo.*` 被跨 context 直连 |
| `GetContactBindingStatusQuery` | `ContactBindingStatusQueryDTO { external_userid, request_meta }` | `ContactBindingStatusResultDTO { is_bound, person_id?, mobile?, third_party_user_id?, first_owner_userid?, last_owner_userid? }` | `Customer Read Model`、`Questionnaire`、sidebar 入口 | `Platform Foundation` | `wecom_ability_service.services.get_contact_binding_status`、`identity.repo` 被 controller 直连 |
| `BindExternalContactIdentityCommand` | `BindExternalContactIdentityCommandDTO { external_userid, openid?, unionid?, mobile?, operator, request_meta }` | `BindExternalContactIdentityResultDTO { ok, person_id, binding, warnings[] }` | `Questionnaire`、身份回填入口 | `Platform Foundation` | `bind_openid_to_external_contact`、`bind_mobile_to_external_contact` 的跨 context 直调 |
| `ReplaceFollowUsersCommand` | `ReplaceFollowUsersCommandDTO { external_userid, follow_users[], operator, request_meta }` | `ReplaceFollowUsersResultDTO { ok, updated_count, primary_userid? }` | callback / sync runtime | `Platform Foundation` | `identity.service.replace_external_contact_follow_users` 被 callback 以外模块直接调用 |
| `ListContactTagsQuery` | `ContactTagListQueryDTO { tag_id[]?, group_id[]?, owner_userid?, request_meta }` | `ContactTagListResultDTO { groups[], tags[], source_status, warnings[] }` | `http/tags.py`、admin tag picker | `Platform Foundation`、`Integration Gateway` | `domains.tags.service.list_wecom_tags`、controller 直接调企微标签读取 |
| `CreateContactTagCommand` | `ContactTagCreateCommandDTO { payload, operator, request_meta }` | `ContactTagCreateResultDTO { ok, tag_group?, tag?, warnings[] }` | `http/tags.py` | `Platform Foundation`、`Integration Gateway` | `domains.tags.service.create_wecom_tag`、controller 直接调企微标签创建 |
| `MarkContactTagsCommand` | `ContactTagMarkCommandDTO { userid, external_userid, add_tag[], operator?, request_meta }` | `ContactTagMarkResultDTO { ok, added[], skipped[], warnings[] }` | `http/tags.py`、后续 MCP / sidebar 写入口 | `Platform Foundation`、`Integration Gateway` | `domains.tags.service.mark_customer_tags`、`mcp_adapter._update_customer_tags` 风格旁路写入 |
| `UnmarkContactTagsCommand` | `ContactTagUnmarkCommandDTO { userid, external_userid, remove_tag[], operator?, request_meta }` | `ContactTagUnmarkResultDTO { ok, removed[], skipped[], warnings[] }` | `http/tags.py`、后续 MCP / sidebar 写入口 | `Platform Foundation`、`Integration Gateway` | `domains.tags.service.unmark_customer_tags`、controller 直接调标签移除 |

### 2.3 Customer Read Model

| command/query 名称 | 输入 DTO | 输出 DTO | 调用方 | 可依赖的上下文 | 禁止绕过该 API 的旧入口 |
| --- | --- | --- | --- | --- | --- |
| `ListCustomersQuery` | `CustomerListQueryDTO { owner_userid?, tag?, status?, is_bound?, marketing_segment?, marketing_main_stage?, marketing_sub_stage?, eligible_for_conversion?, mobile?, keyword?, limit=50, offset=0, access_context? }` | `CustomerListResultDTO { items[], customers[], count, total, limit, offset, filters }` | `http/customer_center.py`、`domains.admin_console.customer_profile_service`、admin customer 页面 | `Identity & Contact Graph`、`Ops & Enrollment`、`Automation Engine`、`Platform Foundation` | `customer_center.service.list_customers`、`customer_center.customer_profile_service.list_customers` |
| `GetCustomerDetailQuery` | `CustomerDetailQueryDTO { external_userid, refresh_tags?=false, access_context?, request_meta }` | `CustomerDetailResultDTO { customer }` | `http/customer_center.py`、`http/customer_automation.py`、admin customer profile、MCP customer lookup | `Identity & Contact Graph`、`Ops & Enrollment`、`Automation Engine`、`Integration Gateway`、`Platform Foundation` | `customer_center.service.get_customer_detail`、`customer_center.customer_profile_service.get_customer_detail`、`mcp_adapter._build_customer_context_payload` |
| `GetCustomerTimelineQuery` | `CustomerTimelineQueryDTO { external_userid, event_type?, limit=50, offset=0, access_context?, request_meta }` | `CustomerTimelineResultDTO { timeline }` | `http/customer_timeline.py`、`http/customer_automation.py`、admin customer profile、MCP customer context | `Identity & Contact Graph`、`Ops & Enrollment`、`Automation Engine`、`Integration Gateway`、`Platform Foundation` | `customer_timeline.service.get_customer_timeline`、`mcp_adapter._get_customer_timeline_payload` |
| `GetCustomerChatContextQuery` | `CustomerChatContextQueryDTO { external_userid, recent_message_limit=20, timeline_limit=20, refresh_tags?=false, access_context?, request_meta }` | `CustomerChatContextResultDTO { external_userid, customer, recent_messages[], recent_timeline_events[], source_status, degraded, warnings[] }` | `openclaw_service.services.customer_chat_context_service`、`openclaw_service.services.crm_operator_service`、`mcp get_customer_context` | `Identity & Contact Graph`、`Automation Engine`、`Integration Gateway`、`Platform Foundation` | `openclaw_service.tools.registry.call_tool_by_name("get_customer_chat_context", ...)`、`mcp_adapter._build_customer_context_payload` |
| `ListRecentMessagesQuery` | `RecentMessagesQueryDTO { external_userid, limit=20, chat_type?, request_meta }` | `RecentMessagesResultDTO { messages[] }` | OpenClaw HTTP adapter、MCP、admin customer profile | `Integration Gateway`、`Platform Foundation` | `wecom_ability_service.services.get_recent_messages_by_user`、`services.search_messages` 的旁路拼装 |

补充说明：

- `http/customer_automation.py` 是 `Customer Read Model` query contract 的调用方，不改变这些 query 的 owner
- `ListRecentMessagesQuery` 继续归属 `Customer Read Model`，因为它对外暴露的是客户聚合读取契约；底层消息来源仍通过 `Integration Gateway` 提供

### 2.4 Ops & Enrollment

| command/query 名称 | 输入 DTO | 输出 DTO | 调用方 | 可依赖的上下文 | 禁止绕过该 API 的旧入口 |
| --- | --- | --- | --- | --- | --- |
| `GetUserOpsOverviewQuery` | `UserOpsOverviewQueryDTO { request_meta }` | `UserOpsOverviewResultDTO { metrics, class_term_options[], routing_summary, deferred_job_summary }` | `http/admin_user_ops.py`、后台 operations 页面 | `Platform Foundation`、`Identity & Contact Graph` | `wecom_ability_service.services.get_user_ops_overview` |
| `ListLeadPoolQuery` | `LeadPoolQueryDTO { filters, limit, offset, request_meta }` | `LeadPoolResultDTO { items[], total, filters }` | `admin_operations.py`、后续 mission board | `Platform Foundation`、`Identity & Contact Graph` | `wecom_ability_service.services.list_user_ops_pool` |
| `ApplyClassUserStatusChangeCommand` | `ClassUserStatusChangeCommandDTO { external_userid, owner_userid?, signup_status, operator, source, request_meta }` | `ClassUserStatusChangeResultDTO { ok, current_status, history_row, tag_sync_status }` | sidebar / admin ops / Questionnaire 后续回填 | `Platform Foundation`、`Identity & Contact Graph` | `class_user.service.apply_class_user_status_change`、`services.apply_class_user_status_change` 风格的兼容函数 |
| `ImportActivationStatusCommand` | `ActivationImportCommandDTO { file_ref, operator, request_meta }` | `ActivationImportResultDTO { ok, imported_count, skipped_count, errors[] }` | `admin_operations.py` | `Platform Foundation`、`Identity & Contact Graph` | `wecom_ability_service.services.import_activation_status_source` |
| `ImportMobileClassTermCommand` | `MobileClassTermImportCommandDTO { file_ref, operator, request_meta }` | `MobileClassTermImportResultDTO { ok, imported_count, mapping_updates, errors[] }` | `admin_operations.py` | `Platform Foundation`、`Identity & Contact Graph` | `wecom_ability_service.services.import_mobile_class_term_source` |

### 2.5 Questionnaire

| command/query 名称 | 输入 DTO | 输出 DTO | 调用方 | 可依赖的上下文 | 禁止绕过该 API 的旧入口 |
| --- | --- | --- | --- | --- | --- |
| `ListQuestionnairesQuery` | `QuestionnaireListQueryDTO { status?, page?, page_size?, request_meta }` | `QuestionnaireListResultDTO { rows[], pagination }` | `http/admin_questionnaires.py`、admin console | `Platform Foundation` | `wecom_ability_service.services.list_questionnaires` |
| `GetQuestionnaireDetailQuery` | `QuestionnaireDetailQueryDTO { questionnaire_id?, slug?, request_meta }` | `QuestionnaireDetailResultDTO { questionnaire, questions[], external_push_config }` | `http/admin_questionnaires.py`、`public_questionnaires.py` | `Platform Foundation` | `wecom_ability_service.services.get_questionnaire_detail` |
| `CreateOrUpdateQuestionnaireCommand` | `QuestionnaireUpsertCommandDTO { questionnaire_id?, payload, operator, request_meta }` | `QuestionnaireUpsertResultDTO { ok, questionnaire_id, slug, warnings[] }` | `http/admin_questionnaires.py` | `Platform Foundation`、`Integration Gateway` | `wecom_ability_service.services.create_questionnaire`、`update_questionnaire` |
| `SubmitQuestionnaireCommand` | `QuestionnaireSubmitCommandDTO { questionnaire_slug, answers, respondent_identity, request_meta }` | `QuestionnaireSubmitResultDTO { ok, submission_id, external_userid?, person_id?, score, final_tags[] }` | `public_questionnaires.py` | `Identity & Contact Graph`、`Ops & Enrollment`、`Integration Gateway`、`Platform Foundation` | `domains.questionnaire.service.submit_*` 风格直调、controller 直接拼身份回填 |
| `RetryQuestionnaireExternalPushCommand` | `QuestionnaireExternalPushRetryDTO { push_log_id?, filters?, operator, request_meta }` | `QuestionnaireExternalPushRetryResultDTO { ok, retried_count, failed_ids[] }` | `http/admin_questionnaires.py` | `Platform Foundation`、`Integration Gateway` | `retry_questionnaire_external_push_log(s)` 被 controller 直调 |

### 2.6 Automation Engine

| command/query 名称 | 输入 DTO | 输出 DTO | 调用方 | 可依赖的上下文 | 禁止绕过该 API 的旧入口 |
| --- | --- | --- | --- | --- | --- |
| `ListSignupConversionBatchesQuery` | `SignupConversionBatchListQueryDTO { limit=20, cursor?, request_meta }` | `SignupConversionBatchListResultDTO { rows[], next_cursor?, count }` | `http/customer_automation.py`、后续 MCP read tool | `Platform Foundation`、`Customer Read Model` | `wecom_ability_service.services.list_signup_conversion_batches` |
| `GetSignupConversionBatchQuery` | `SignupConversionBatchDetailQueryDTO { batch_id, include_customer_context?=false, request_meta }` | `SignupConversionBatchDetailResultDTO { batch }` | `http/customer_automation.py` | `Platform Foundation`、`Customer Read Model` | `wecom_ability_service.services.get_signup_conversion_batch`、`http/customer_automation.py::_candidate_context` |
| `RecordConversionFeedbackCommand` | `ConversionFeedbackCommandDTO { batch_id, action, operator, notes?, request_meta }` | `ConversionFeedbackResultDTO { ok, batch_status, audit_ref }` | MCP、admin ops、自动化入口 | `Platform Foundation` | `wecom_ability_service.services.record_conversion_feedback` |
| `AcknowledgeConversionBatchCommand` | `ConversionBatchAckCommandDTO { batch_id, operator, request_meta }` | `ConversionBatchAckResultDTO { ok, batch_status }` | MCP / OpenClaw 兼容入口 | `Platform Foundation` | `wecom_ability_service.services.ack_conversion_batch` |
| `RetryOutboundWebhookDeliveryCommand` | `OutboundWebhookRetryCommandDTO { delivery_id?, filters?, limit?, operator, request_meta }` | `OutboundWebhookRetryResultDTO { ok, delivery?, retried_count?, warnings[] }` | `http/customer_automation.py` | `Platform Foundation`、`Integration Gateway` | `wecom_ability_service.services.retry_outbound_webhook_delivery`、`run_due_outbound_webhook_retries` |
| `RunDueOutboundWebhookRetriesCommand` | `OutboundWebhookRetryBatchCommandDTO { limit=20, operator?, request_meta }` | `OutboundWebhookRetryBatchResultDTO { ok, scanned_count?, retried_count, warnings[] }` | `http/customer_automation.py` | `Platform Foundation`、`Integration Gateway` | `wecom_ability_service.services.run_due_outbound_webhook_retries` |
| `ApplyActivationWebhookCommand` | `ActivationWebhookCommandDTO { mobile, activated_at?, operator?, source?, request_meta }` | `ActivationWebhookResultDTO { ok, customer, warnings[] }` | `http/customer_automation.py` | `Platform Foundation`、`Identity & Contact Graph`、`Automation Engine` | `wecom_ability_service.services.apply_activation_webhook`、controller 内联激活后补同步 |
| `SyncAutomationMemberActivationCommand` | `AutomationMemberActivationCommandDTO { external_contact_id?, phone?, operator_id, request_meta }` | `AutomationMemberActivationResultDTO { ok, member_id?, sync_status, warnings[] }` | `http/customer_automation.py` 激活 webhook 补同步 | `Platform Foundation`、`Identity & Contact Graph` | `domains.automation_conversion.service.sync_member_activation` 被 controller 直调 |

### 2.7 AI Assist

| command/query 名称 | 输入 DTO | 输出 DTO | 调用方 | 可依赖的上下文 | 禁止绕过该 API 的旧入口 |
| --- | --- | --- | --- | --- | --- |
| `GetCustomerPulseInboxQuery` | `CustomerPulseInboxQueryDTO { tenant_key?, filters, page, page_size, access_context, request_meta }` | `CustomerPulseInboxResultDTO { items[], summary, pagination }` | `http/admin_customer_pulse.py`、dashboard | `Customer Read Model`、`Automation Engine`、`Identity & Contact Graph`、`Platform Foundation` | `domains.customer_pulse.service.*inbox*` 被 controller 直调 |
| `GetCustomerPulseDetailQuery` | `CustomerPulseDetailQueryDTO { external_userid, access_context, request_meta }` | `CustomerPulseDetailResultDTO { card, latest_snapshot, evidence[], allowed_actions[] }` | `domains.admin_console.customer_profile_service`、`http/admin_customer_pulse.py` | `Customer Read Model`、`Automation Engine`、`Identity & Contact Graph`、`Platform Foundation` | `customer_center.pulse_service.build_customer_pulse` 作为跨 context 默认入口 |
| `ListFollowupCandidatesQuery` | `FollowupCandidatesQueryDTO { tenant_key?, owner_userid?, limit, access_context, request_meta }` | `FollowupCandidatesResultDTO { items[], count, warnings[] }` | `http/admin_followup_orchestrator.py`、MCP followup 工具 | `Customer Read Model`、`Automation Engine`、`Identity & Contact Graph`、`Platform Foundation` | `mcp_adapter._build_followup_candidates`、`followup_orchestrator.service` 被 transport 直调 |
| `PreviewCustomerActionCommand` | `CustomerActionPreviewCommandDTO { action_type, customer_ref, payload, access_context, request_meta }` | `CustomerActionPreviewResultDTO { ok, preview, risk_level, warnings[] }` | admin pulse action card、后续 MCP write tool | `Customer Read Model`、`Automation Engine`、`Identity & Contact Graph`、`Platform Foundation` | `domains.customer_pulse.service.preview_*` 的跨 context 直调 |
| `ExecuteCustomerActionCommand` | `CustomerActionExecuteCommandDTO { action_type, customer_ref, payload, operator, access_context, request_meta }` | `CustomerActionExecuteResultDTO { ok, execution_id, side_effects[], audit_ref }` | admin pulse / followup 行动 | `Customer Read Model`、`Automation Engine`、`Identity & Contact Graph`、`Integration Gateway`、`Platform Foundation` | `domains.customer_pulse.service.execute_*`、`followup_orchestrator.service` 的 controller 直调 |

### 2.8 Platform Foundation

| command/query 名称 | 输入 DTO | 输出 DTO | 调用方 | 可依赖的上下文 | 禁止绕过该 API 的旧入口 |
| --- | --- | --- | --- | --- | --- |
| `GetAppSettingsQuery` | `AppSettingsQueryDTO { keys?, request_meta }` | `AppSettingsResultDTO { settings, source }` | `http/admin_config.py`、jobs、integration runtime | 仅 `Platform Foundation` | `infra.settings.get_setting` 被 controller 大范围直读 |
| `SaveAppSettingsCommand` | `AppSettingsSaveCommandDTO { settings, operator, request_meta }` | `AppSettingsSaveResultDTO { ok, changed_keys[], audit_ref }` | `http/admin_config.py` | 仅 `Platform Foundation` | `save_admin_app_settings` 被 controller 分散直调 |
| `AuthorizeInternalRequestQuery` | `InternalAuthQueryDTO { headers, token_keys?, legacy_header_names?, request_meta }` | `InternalAuthResultDTO { ok, reason?, principal? }` | `mcp_adapter.py`、`http/customer_automation.py`、jobs action endpoint | 仅 `Platform Foundation` | `http/internal_auth.require_internal_api_token` 在业务 controller 中散用为隐式策略 |
| `ListMcpRuntimeToolsQuery` | `McpRuntimeToolListQueryDTO { request_meta }` | `McpRuntimeToolListResultDTO { tools[], flags, disabled_tools[] }` | `mcp_adapter.py`、`http/admin_mcp.py`、admin config | 仅 `Platform Foundation` | `domains.admin_config.list_mcp_runtime_tools` 被 transport 和 UI 多处直调 |
| `GetOpsRuntimeStatusQuery` | `OpsRuntimeStatusQueryDTO { request_meta }` | `OpsRuntimeStatusResultDTO { runtime, release_sha, database, async_flags }` | `http/ops.py`、`http/admin_dashboard.py` | 仅 `Platform Foundation` | `http/ops_runtime.py` 被各入口零散调用 |
| `RecordAdminAuditCommand` | `AuditRecordCommandDTO { action_type, target_type, target_id, operator, before?, after?, request_meta }` | `AuditRecordResultDTO { ok, audit_log_id }` | 所有 admin 写入口 | 仅 `Platform Foundation` | `domains.admin_audit.service.record_*` 被各域各写入口自定义调用 |

## 3. Wave 1 必须先落的正式 contract

Wave 1 只先正式落地以下 contract：

1. `ListCustomersQuery`
2. `GetCustomerDetailQuery`
3. `GetCustomerTimelineQuery`
4. `GetCustomerChatContextQuery`
5. `ListRecentMessagesQuery`
6. `DispatchMcpToolCommand`
7. `AuthorizeInternalRequestQuery`
8. `ListSignupConversionBatchesQuery`
9. `GetSignupConversionBatchQuery`
10. `RetryOutboundWebhookDeliveryCommand`
11. `SyncAutomationMemberActivationCommand`

其余 context 的 application API 先完成目录与命名固化，不在 Wave 1 进入大规模模块内拆分。

## 4. Wave 1 明确禁止的新调用方式

从现在开始，不允许新增下列调用：

- `from wecom_ability_service.customer_center.service import list_customers, get_customer_detail`
- `from wecom_ability_service.customer_timeline.service import get_customer_timeline`
- `from wecom_ability_service.services import ...` 作为新业务入口
- `from wecom_ability_service.mcp_adapter import _xxx`
- `from wecom_ability_service.customer_center.repo import ...` 被非 `customer_center/` 包调用
- `from wecom_ability_service.customer_timeline.repo import ...` 被非 `customer_timeline/` 包调用
- `openclaw_service.*` 直接 import `wecom_ability_service.*`

新增调用只能走：

- `wecom_ability_service/application/customer_read_model/*`
- `wecom_ability_service/application/integration_gateway/*`
- `wecom_ability_service/application/platform_foundation/*`
