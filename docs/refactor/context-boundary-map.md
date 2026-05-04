# Context Boundary Map

日期：2026-04-17

状态：Draft for execution

适用范围：

- `wecom_ability_service/`
- `openclaw_service/`
- 与 `docs/architecture/2026-04-17-platform-refactor-blueprint-v1.md` 保持一致

## 1. 使用说明

这份文档不是新的宏观设计，而是把现有蓝图落成可以执行的边界清单。

本文件约束三件事：

1. 每个目录 / 包属于哪个 context
2. 每个目录 / 包处于哪一层
3. 允许和禁止的 import 方向是什么

额外统一口径：

- Wave 1 先收口入口，不先拆大模块
- 文中提到的 `application/*` 包是目标正式入口，当前可先通过兼容 wrapper 逐步落地
- 旧目录可以保留，但只允许“搬运、转调、兼容”，不允许继续堆新业务

## 2. 六层定义

| 层 | 作用 | 允许做的事 | 禁止做的事 |
| --- | --- | --- | --- |
| `api` | HTTP / JSON-RPC / CLI / bot transport | 解析请求、鉴权、参数校验、返回响应 | 直接写 SQL、直接打第三方 HTTP、内联业务编排 |
| `application` | use case 编排层 | 调用本 context domain / read model，并通过正式 application API 调其他 context | 持有协议细节、直接依赖 Flask request/session/current_app |
| `domain` | 领域规则层 | 维护本 context 事实、状态机、规则与写逻辑 | import controller、import 其他 context 的 repo/service 实现 |
| `infrastructure` | 平台和底层支撑 | DB runtime、settings、auth、audit、scheduler、runtime client | 持有业务语义、拼装读模型 |
| `read model` | 读投影层 | 只读聚合、分页、过滤、投影视图 | 承接写逻辑、外发第三方请求、回写业务判断 |
| `integration` | 外部协议与适配 | 调第三方 API、转换 payload、重试、幂等、防抖 | 决定业务规则、拼业务领域状态 |

## 3. Context 依赖总矩阵

| Context | 允许依赖的 context |
| --- | --- |
| `Integration Gateway` | `Platform Foundation`、`Identity & Contact Graph`、`Customer Read Model`、`Automation Engine` |
| `Identity & Contact Graph` | `Platform Foundation`、`Integration Gateway` 的稳定 integration port |
| `Customer Read Model` | `Identity & Contact Graph`、`Ops & Enrollment`、`Automation Engine`、`Integration Gateway`、`Platform Foundation` |
| `Ops & Enrollment` | `Identity & Contact Graph`、`Integration Gateway`、`Platform Foundation` |
| `Questionnaire` | `Identity & Contact Graph`、`Ops & Enrollment`、`Integration Gateway`、`Platform Foundation` |
| `Automation Engine` | `Identity & Contact Graph`、`Ops & Enrollment`、`Customer Read Model`、`Integration Gateway`、`Platform Foundation` |
| `AI Assist` | `Customer Read Model`、`Automation Engine`、`Identity & Contact Graph`、`Platform Foundation` |
| `Platform Foundation` | 不反向依赖业务 context |

全局硬规则：

- 跨 context 访问一律走正式 application API，不允许直接 import 对方 `repo.py` / `service.py`
- `read model` 只能读，不承担写
- `api` 只能调 `application`

## 4. Boundary Map

### 4.1 Platform Foundation

| 目录 / 包 | Context | 层 | allowed imports | forbidden imports | 对外公开 API | 禁止继续新增逻辑的历史文件 |
| --- | --- | --- | --- | --- | --- | --- |
| `app.py` | Platform Foundation | `api` | `wecom_ability_service.__init__`、CLI 初始化脚本、`db.py` | 任何 domain 细节、第三方业务 API 调用 | `init-db`、`run` | 无 |
| `wecom_ability_service/__init__.py` | Platform Foundation | `api` | `http/__init__.py`、`mcp_adapter.py`、`db.py`、`observability.py`、`infra/*` | 直接 import 业务 domain repo / service 细节 | `create_app()` | 无 |
| `wecom_ability_service/routes.py` | Platform Foundation | `api` | `http.bp`、必要 bootstrap helper | `customer_center.service`、`customer_timeline.service`、`domains/*/service.py` | HTTP 蓝图装配 | `wecom_ability_service/routes.py` 只允许保留装配和 bootstrap glue |
| `wecom_ability_service/db.py` | Platform Foundation | `infrastructure` | 标准库、数据库驱动、`infra/*` | `http/*`、业务 `service.py` | `get_db()`、schema 初始化 | 无 |
| `wecom_ability_service/schema.sql` / `schema_postgres.sql` | Platform Foundation | `infrastructure` | SQL DDL | 业务逻辑说明式修补 | schema 契约 | 无 |
| `wecom_ability_service/infra/` | Platform Foundation | `infrastructure` | 标准库、数据库 / runtime client、`observability.py` | `http/*`、业务 domain service | `settings`、`helpers`、`wecom_runtime`、`wechat_oauth` | 无 |
| `wecom_ability_service/application/platform_foundation/` | Platform Foundation | `application` | `infra/*`、`domains/admin_*`、稳定 application API | `http/*`、`customer_center/repo.py`、`customer_timeline/repo.py` | `GetAppSettingsQuery`、`SaveAppSettingsCommand`、`AuthorizeInternalRequestQuery`、`ListMcpRuntimeToolsQuery`、`RecordAdminAuditCommand`、`GetOpsRuntimeStatusQuery` | 目标新包，不在旧文件堆逻辑 |
| `wecom_ability_service/domains/admin_config/`、`admin_dashboard/`、`admin_jobs/`、`admin_audit/` | Platform Foundation | `domain` | 同包 `repo.py`、`infra/*`、`application/platform_foundation/*` | `http/*`、`customer_center.service`、`customer_timeline.service`、`mcp_adapter.py` | 后台配置、dashboard、jobs、audit 的领域规则 | 现有文件只允许整理边界，不允许新增跨 context 编排 |
| `wecom_ability_service/domains/admin_console/` | Platform Foundation | `application` | `application/customer_read_model/*`、`application/platform_foundation/*`、`application/ai_assist/*` | `customer_center.service`、`customer_timeline.service`、`mcp_adapter.*` 私有函数、`services.py` | admin shell payload、customer profile 页面拼装 | `wecom_ability_service/domains/admin_console/service.py`、`wecom_ability_service/domains/admin_console/customer_profile_service.py` |

### 4.2 Customer Read Model

| 目录 / 包 | Context | 层 | allowed imports | forbidden imports | 对外公开 API | 禁止继续新增逻辑的历史文件 |
| --- | --- | --- | --- | --- | --- | --- |
| `wecom_ability_service/application/customer_read_model/` | Customer Read Model | `application` | `customer_center/*`、`customer_timeline/*`、`application/identity_contact/*`、`application/ops_enrollment/*`、`application/automation_engine/*`、`application/integration_gateway/*`、`application/platform_foundation/*` | `http/*`、`mcp_adapter.py`、`services.py`、直接第三方 client | `ListCustomersQuery`、`GetCustomerDetailQuery`、`GetCustomerTimelineQuery`、`GetCustomerChatContextQuery`、`ListRecentMessagesQuery` | 目标新包，不在旧文件堆逻辑 |
| `wecom_ability_service/http/customer_center.py` | Customer Read Model | `api` | `application/customer_read_model/*`、`customer_center/routes.py`、Flask | `customer_center.service`、`services.py`、任何 repo、`requests` | `GET /api/customers`、`GET /api/customers/<external_userid>` | 允许继续保留文件，但只做 controller |
| `wecom_ability_service/http/customer_timeline.py` | Customer Read Model | `api` | `application/customer_read_model/*`、`application/platform_foundation/*`、`customer_timeline/routes.py`、Flask | `customer_timeline.service`、`customer_timeline.repo`、`services.py`、`requests` | `GET /api/customers/<external_userid>/timeline` | 允许继续保留文件，但只做 controller |
| `wecom_ability_service/customer_center/` | Customer Read Model | `read model` | 同包 `repo.py` / `dto.py` / `routes.py`，以及 `application/*` 暴露的正式 query port | `http/*`、`mcp_adapter.py`、`services.py`、`requests`、写域 repo | 客户列表 / 详情读投影 | `wecom_ability_service/customer_center/service.py`、`wecom_ability_service/customer_center/pulse_service.py`、`wecom_ability_service/customer_center/customer_profile_service.py` |
| `wecom_ability_service/customer_timeline/` | Customer Read Model | `read model` | 同包 `repo.py` / `dto.py` / `routes.py`，以及 `application/*` 暴露的正式 query port | `http/*`、`mcp_adapter.py`、`services.py`、写域 repo、第三方 client | 客户 timeline 读投影 | `wecom_ability_service/customer_timeline/service.py` |

补充说明：

- `http/customer_automation.py` 只是 `Customer Read Model` query contract 的调用方，不属于本 context 的文件归属
- `ListRecentMessagesQuery` 继续归属 `Customer Read Model`；它消费 `Integration Gateway` 暴露的消息能力，但对外仍作为客户聚合读契约提供

### 4.3 Integration Gateway

| 目录 / 包 | Context | 层 | allowed imports | forbidden imports | 对外公开 API | 禁止继续新增逻辑的历史文件 |
| --- | --- | --- | --- | --- | --- | --- |
| `wecom_ability_service/application/integration_gateway/` | Integration Gateway | `application` | `domains/callbacks`、`domains/archive`、`domains/tasks`、`application/customer_read_model/*`、`application/identity_contact/*`、`application/automation_engine/*`、`application/platform_foundation/*` | `http/*`、`customer_center.repo`、`customer_timeline.repo` | `HandleWeComExternalContactCallbackCommand`、`SyncWeComContactsCommand`、`GetArchivedMessagesQuery`、`DispatchWeComTaskCommand`、`DispatchMcpToolCommand` | 目标新包，不在旧文件堆逻辑 |
| `wecom_ability_service/mcp_adapter.py` | Integration Gateway | `api` | Flask、`http/internal_auth.py`、`application/integration_gateway/*`、`application/platform_foundation/*` | `customer_center.service`、`customer_timeline.service`、`services.py`、`domains/automation_conversion/*`、`requests` | `/mcp` transport、`initialize`、`tools/list`、`tools/call` | `wecom_ability_service/mcp_adapter.py` |
| `wecom_ability_service/http/callbacks.py`、`callback_runtime.py`、`background_jobs.py` | Integration Gateway | `api` | `application/integration_gateway/*`、`application/platform_foundation/*`、Flask | 直接 SQL、`requests`、写业务规则 | callback 入口与后台调度 | 仅允许 transport / job glue |
| `wecom_ability_service/http/archive.py`、`contacts.py`、`group_chats.py`、`tasks.py` | Integration Gateway | `api` | 对应 `application/*`、Flask、`http/common.py` | 直接 repo、`requests`、`WeComClient.from_*` | 企微同步、消息、任务入口 | 不允许继续内联业务编排 |
| `wecom_ability_service/domains/archive/`、`callbacks/`、`group_chats/`、`tasks/` | Integration Gateway | `domain` | 同包 `repo.py`、`infra/*` | `http/*`、`customer_center.service`、`customer_timeline.service` | 归档消息、回调、群聊、任务领域规则 | 允许内部重构，不允许扩展为跨 context 总线 |
| `wecom_ability_service/wecom_client.py`、`wecom_callback.py`、`archive_sdk.py`、`archive_adapter.py` | Integration Gateway | `integration` | 标准库、`infra/*`、第三方 SDK / HTTP client | `http/*`、读模型 repo、业务规则模块 | 企微与会话存档协议适配 | `archive_adapter.py` 仅允许兼容 glue |
| `openclaw_service/integrations/crm/` | Integration Gateway | `integration` | `requests`、本包 `config` / `models` / `errors` | `wecom_ability_service.mcp_adapter`、`customer_center.service`、`db.py`、任何 Flask app internals | `CrmApiClient`、CRM adapters | 无 |
| `openclaw_service/services/` | Integration Gateway | `application` | `openclaw_service/integrations/crm/*`、稳定 tool / service port | 直接 import `wecom_ability_service/*` | `get_customer_context`、`update_customer_tags`、`get_customer_chat_context` | `crm_operator_service.py` 当前 registry 兼容路径只允许收敛，不允许扩写 |
| `openclaw_service/tools/` | Integration Gateway | `api` | `openclaw_service/services/*` | 直接 import `wecom_ability_service/*` | `call_tool_by_name`、tool defs | 无 |
| `openclaw_service/feishu/`、`cli/` | Integration Gateway | `api` | `openclaw_service/services/*`、Feishu transport | 直接 import `wecom_ability_service/*` | 飞书命令 / CLI | 无 |

### 4.4 Identity & Contact Graph

| 目录 / 包 | Context | 层 | allowed imports | forbidden imports | 对外公开 API | 禁止继续新增逻辑的历史文件 |
| --- | --- | --- | --- | --- | --- | --- |
| `wecom_ability_service/application/identity_contact/` | Identity & Contact Graph | `application` | `domains/identity`、`domains/contacts`、`domains/tags`、`application/integration_gateway/*`、`application/platform_foundation/*` | `http/*`、`customer_center.repo`、`customer_timeline.repo` | `ResolvePersonIdentityQuery`、`GetContactSnapshotQuery`、`GetContactBindingStatusQuery`、`BindExternalContactIdentityCommand`、`ReplaceFollowUsersCommand`、`ListContactTagsQuery`、`CreateContactTagCommand`、`MarkContactTagsCommand`、`UnmarkContactTagsCommand` | 目标新包，不在旧文件堆逻辑 |
| `wecom_ability_service/domains/identity/` | Identity & Contact Graph | `domain` | 同包 `repo.py`、`infra/*` | `http/*`、`customer_center.service`、`services.py`、`mcp_adapter.py` | people / bindings / identity map / follow users | 允许领域内整理，不允许再承担 controller glue |
| `wecom_ability_service/domains/contacts/` | Identity & Contact Graph | `domain` | 同包 `repo.py`、`infra/wecom_runtime.py` | `http/*`、`customer_center.service`、`customer_timeline.service` | contact snapshot / 描述更新 / 读取 | 不允许继续作为跨域 helper 集合 |
| `wecom_ability_service/domains/tags/` | Identity & Contact Graph | `domain` | 同包 `repo.py`、`infra/*`、本 context 的稳定 tag sync adapter | `http/*`、`customer_center.service`、`customer_timeline.service`、`mcp_adapter.py`、`wecom_client.py` 直连 | contact tag snapshot、tag mutation policy、signup tag rule、owner-scoped tag view | 历史上混合了企微标签同步与报名标签规则；Wave 1 统一按 Identity & Contact Graph 约束，不再扩写职责 |
| `wecom_ability_service/http/identity.py` | Identity & Contact Graph | `api` | `application/identity_contact/*`、Flask | `domains/identity/service.py` 直连、`db.py`、`requests` | `/api/identity/resolve` | 允许保留，仅做 controller |
| `wecom_ability_service/http/tags.py` | Identity & Contact Graph | `api` | `application/identity_contact/*`、`application/platform_foundation/*`、Flask、`http/common.py` | `domains/tags/service.py` 直连、`wecom_client.py`、`requests`、直接 SQL | `GET /api/tags`、`POST /api/tags`、`POST /api/tags/mark`、`POST /api/tags/unmark` | 允许保留，仅做 controller；标签读写统一收口到 `Identity & Contact Graph` |

### 4.5 Ops & Enrollment

| 目录 / 包 | Context | 层 | allowed imports | forbidden imports | 对外公开 API | 禁止继续新增逻辑的历史文件 |
| --- | --- | --- | --- | --- | --- | --- |
| `wecom_ability_service/application/ops_enrollment/` | Ops & Enrollment | `application` | `domains/user_ops`、`domains/class_user`、`domains/routing_config`、`application/identity_contact/*`、`application/integration_gateway/*`、`application/platform_foundation/*` | `http/*`、`customer_center.repo`、`mcp_adapter.py` | `GetUserOpsOverviewQuery`、`ListLeadPoolQuery`、`ApplyClassUserStatusChangeCommand`、`ImportActivationStatusCommand`、`ImportMobileClassTermCommand` | 目标新包，不在旧文件堆逻辑 |
| `wecom_ability_service/domains/user_ops/` | Ops & Enrollment | `domain` | 同包 `repo.py` / `page_service.py`、`infra/*`、`application/identity_contact/*` | `http/*`、`customer_center.service`、`customer_timeline.service`、`mcp_adapter.py` | lead pool、导入、激活同步、deferred jobs | 现阶段不做大拆，禁止扩大职责 |
| `wecom_ability_service/domains/class_user/` | Ops & Enrollment | `domain` | 同包 `repo.py`、`infra/*` | `http/*`、`customer_center.service` | class user 状态机 | 不允许新增跨域聚合 |
| `wecom_ability_service/domains/routing_config/` | Ops & Enrollment | `domain` | 同包 `repo.py` / `definitions.py` | `http/*`、`customer_center.service` | owner role / routing config | 不允许变成 settings 杂糅层 |
| `wecom_ability_service/http/admin_user_ops.py`、`admin_class_user.py`、`admin_operations.py` | Ops & Enrollment | `api` | `application/ops_enrollment/*`、`application/platform_foundation/*` | `services.py`、直接 domain repo / service、`requests` | 后台 user ops / class user / operations 入口 | 仅允许做 transport |

### 4.6 Questionnaire

| 目录 / 包 | Context | 层 | allowed imports | forbidden imports | 对外公开 API | 禁止继续新增逻辑的历史文件 |
| --- | --- | --- | --- | --- | --- | --- |
| `wecom_ability_service/application/questionnaire/` | Questionnaire | `application` | `domains/questionnaire`、`application/identity_contact/*`、`application/ops_enrollment/*`、`application/integration_gateway/*`、`application/platform_foundation/*` | `http/*`、`customer_center.repo`、`mcp_adapter.py` | `ListQuestionnairesQuery`、`GetQuestionnaireDetailQuery`、`CreateOrUpdateQuestionnaireCommand`、`SubmitQuestionnaireCommand`、`RetryQuestionnaireExternalPushCommand` | 目标新包，不在旧文件堆逻辑 |
| `wecom_ability_service/domains/questionnaire/` | Questionnaire | `domain` | 同包 `repo.py` / `preflight_service.py`、`infra/wechat_oauth.py` | `http/*`、`customer_center.service`、`customer_timeline.service` | 问卷定义、公开读取、提交、外发 webhook | Wave 1 不拆大模块，禁止继续加横向聚合 |
| `wecom_ability_service/http/public_questionnaires.py`、`admin_questionnaires.py`、`admin_questionnaire_console.py`、`questionnaire_support.py` | Questionnaire | `api` | `application/questionnaire/*`、Flask | `domains/questionnaire/service.py` 直连、`requests`、直接 SQL | 公开问卷与后台问卷入口 | controller only |

### 4.7 Automation Engine

| 目录 / 包 | Context | 层 | allowed imports | forbidden imports | 对外公开 API | 禁止继续新增逻辑的历史文件 |
| --- | --- | --- | --- | --- | --- | --- |
| `wecom_ability_service/application/automation_engine/` | Automation Engine | `application` | `domains/automation_conversion`、`domains/automation_state`、`domains/marketing_automation`、`domains/outbound_webhook`、`application/identity_contact/*`、`application/ops_enrollment/*`、`application/customer_read_model/*`、`application/integration_gateway/*`、`application/platform_foundation/*` | `http/*`、`customer_center.repo`、`mcp_adapter.py` | `ListSignupConversionBatchesQuery`、`GetSignupConversionBatchQuery`、`RecordConversionFeedbackCommand`、`AcknowledgeConversionBatchCommand`、`RetryOutboundWebhookDeliveryCommand`、`RunDueOutboundWebhookRetriesCommand`、`ApplyActivationWebhookCommand`、`SyncAutomationMemberActivationCommand` | 目标新包，不在旧文件堆逻辑 |
| `wecom_ability_service/domains/automation_conversion/` | Automation Engine | `domain` | 同包子模块、`infra/*`、稳定 application port | `http/*`、`customer_center.service`、`customer_timeline.service`、`mcp_adapter.py` | workflow / audience / member / agent / execution | Wave 1 不进入大拆，只允许改成通过 application API 读客户上下文 |
| `wecom_ability_service/domains/automation_state/`、`marketing_automation/`、`outbound_webhook/` | Automation Engine | `domain` | 同包 `repo.py`、`infra/*` | `http/*`、`customer_center.service`、`mcp_adapter.py` | 营销状态、转化状态、webhook delivery | Wave 1 不扩面 |
| `wecom_ability_service/http/automation_conversion.py`、`customer_automation.py` | Automation Engine | `api` | `application/automation_engine/*`、`application/customer_read_model/*`、Flask | `services.py`、直接 domain repo / service、`requests` | 自动化后台、转化批次、激活 webhook、delivery retry | `http/customer_automation.py` 内禁止继续加聚合 |

### 4.8 AI Assist

| 目录 / 包 | Context | 层 | allowed imports | forbidden imports | 对外公开 API | 禁止继续新增逻辑的历史文件 |
| --- | --- | --- | --- | --- | --- | --- |
| `wecom_ability_service/application/ai_assist/` | AI Assist | `application` | `domains/customer_pulse`、`domains/followup_orchestrator`、`application/customer_read_model/*`、`application/automation_engine/*`、`application/identity_contact/*`、`application/platform_foundation/*` | `http/*`、`customer_center.repo`、`customer_timeline.repo` | `GetCustomerPulseInboxQuery`、`GetCustomerPulseDetailQuery`、`ListFollowupCandidatesQuery`、`PreviewCustomerActionCommand`、`ExecuteCustomerActionCommand` | 目标新包，不在旧文件堆逻辑 |
| `wecom_ability_service/domains/customer_pulse/` | AI Assist | `domain` | 同包 `repo.py` / `access.py` / `ai_recommendation.py`、`infra/*` | `http/*`、`customer_center.service`、`customer_timeline.service` 作为默认读入口 | customer pulse 规则、快照、AI 推荐 | Wave 1 不做大拆，只允许消费正式 read model API |
| `wecom_ability_service/domains/followup_orchestrator/` | AI Assist | `domain` | 同包 `repo.py` / `ai_enhancement.py`、`infra/*` | `http/*`、`customer_center.service`、`customer_timeline.service` | 跟进任务编排 | Wave 1 不做大拆 |
| `wecom_ability_service/http/admin_customer_pulse.py`、`admin_followup_orchestrator.py` | AI Assist | `api` | `application/ai_assist/*`、`application/platform_foundation/*`、Flask | `domains/customer_pulse/service.py` 直连、`domains/followup_orchestrator/service.py` 直连、`requests` | AI inbox / followup admin 入口 | controller only |

## 5. 全局冻结文件清单

以下文件保留兼容职责，但从现在起禁止继续追加新业务逻辑：

- `wecom_ability_service/services.py`
- `wecom_ability_service/mcp_adapter.py`
- `wecom_ability_service/customer_center/service.py`
- `wecom_ability_service/customer_center/pulse_service.py`
- `wecom_ability_service/customer_center/customer_profile_service.py`
- `wecom_ability_service/customer_timeline/service.py`
- `wecom_ability_service/http/customer_automation.py`
- `wecom_ability_service/domains/admin_console/service.py`
- `wecom_ability_service/domains/admin_console/customer_profile_service.py`

允许做的只有：

- 提取到正式 application API
- 保持旧函数签名的兼容 wrapper
- 删除重复逻辑
- 增加 deprecation 注释或 test guardrail

不允许做的包括：

- 新增跨 context 聚合
- 新增业务规则
- 新增 SQL
- 新增第三方 HTTP 调用

## 6. Wave 1 边界收口目标

Wave 1 的边界收口只针对下列入口：

- `customer_center`
- `customer_timeline`
- `services.py`
- `mcp_adapter.py`
- `http/customer_center.py`
- `http/customer_timeline.py`
- `http/customer_automation.py`
- `domains/admin_console/customer_profile_service.py`
- `domains/admin_console/service.py`

Wave 1 完成后必须满足：

1. HTTP controller 只调正式 application API
2. `mcp_adapter.py` 只保留 transport
3. `services.py` 只保留兼容导出
4. `customer_center` / `customer_timeline` 明确为 read model
5. admin shell 不再直接 import read model implementation
