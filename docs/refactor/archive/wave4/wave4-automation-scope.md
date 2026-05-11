# Wave 4 Automation Engine Scope

日期：2026-04-21

## 1. 目标

Wave 4 只处理 `Automation Engine` 这个 context 的范围盘点和合同化设计，不改业务代码，不改测试，不进入 `user_ops` / `questionnaire` / `customer_pulse` / `followup_orchestrator` 内部拆分。

本轮要解决的不是“再写一份宏观蓝图”，而是把当前 automation 相关逻辑里已经混在一起的 5 条主线先拆清：

1. member state
2. signup conversion / feedback / ack
3. outbound webhook / retry / due runner
4. workflow runtime / audience / execution
5. SOP / focus send / reply monitor

同时要把这些主线与 `identity` / `user_ops` / `questionnaire` / `customer read model` 的边界说清，明确哪些 caller 未来必须切到正式 `application/automation_engine/*`。

## 2. 当前现状

当前 automation 的主要问题不是“某一个大文件太长”，而是 owner 被拆散在 4 个 domain 包和 1 个 transport/任务包里：

| 当前 owner 文件 | 当前承载职责 | 直接 caller | 当前问题 |
| --- | --- | --- | --- |
| `wecom_ability_service/domains/marketing_automation/service.py` | signup conversion config、candidate preview/recompute、conversion batch read/ack、marketing truth、activation webhook、focus webhook | `http/admin_config.py`、`http/customer_automation.py`、`http/sidebar.py`、`http/admin_support.py`、`application/integration_gateway/mcp_dispatch.py`、`domains/admin_console/service.py` | 同时做读、写、callback、integration、class_user side effect、user_ops payload 拼装 |
| `wecom_ability_service/domains/automation_conversion/service.py` | member state、overview/stage detail、SOP、focus send、reply monitor、qrcode callback、questionnaire bridge | `http/automation_conversion.py`、`http/background_jobs.py`、`http/customer_automation.py`、`tests/*` | 把 admin 页面、runtime、member mutation、bridge、due runner 都堆在一起 |
| `wecom_ability_service/domains/automation_conversion/workflow_service.py` + `workflow_runtime.py` | workflow CRUD、audience sync、execution read、run-due runtime | `http/automation_conversion.py`、`domains/automation_conversion/service.py` | workflow admin model、runtime、execution read model 仍紧耦合，且 runtime 直接摸 `services.py` / `tasks.service` / `user_ops.page_service` |
| `wecom_ability_service/domains/outbound_webhook/service.py` | delivery send、retry policy、due retry、list/count | `domains/marketing_automation/service.py`、`domains/questionnaire/service.py`、`domains/admin_jobs/service.py`、`http/customer_automation.py` | delivery transport 与业务 owner 没切开，admin retry caller 仍绕 legacy surface |
| `wecom_ability_service/domains/tasks/service.py` | WeCom task dispatch、conversion feedback write-back | `http/tasks.py`、`domains/marketing_automation/service.py`、`domains/automation_conversion/service.py` | transport task dispatch 和 automation truth write-back混在一起，caller 难以分辨 integration vs business owner |

当前仓库已经有一个 Wave 1 级别的 `application/automation_engine/queries.py` skeleton，但它只覆盖：

- `ListSignupConversionBatchesQuery`
- `GetSignupConversionBatchQuery`
- `RetryOutboundWebhookDeliveryCommand`
- `RunDueOutboundWebhookRetriesCommand`
- `ApplyActivationWebhookCommand`
- `SyncAutomationMemberActivationCommand`

这说明 formal owner 已经起头，但 automation 的大部分 admin / callback / workflow / member-state / SOP 链路仍未正式收口。

## 3. Automation Engine 的 5 条主线

### 3.1 Signup Conversion / Feedback / Ack

当前 owner：

- `wecom_ability_service/domains/marketing_automation/service.py`
- `wecom_ability_service/domains/tasks/service.py::record_conversion_feedback`

当前职责：

- signup conversion config 保存与读取
- questionnaire 命中规则 preview / recompute
- pending batch / batch detail / batch ack
- feedback 录入后同步 marketing truth
- marketing profile / segment 计算
- 手工 enrolled / unenrolled / followup segment 变更

直接 caller：

- `wecom_ability_service/http/admin_config.py`
- `wecom_ability_service/http/customer_automation.py`
- `wecom_ability_service/http/sidebar.py`
- `wecom_ability_service/http/admin_support.py`
- `wecom_ability_service/application/integration_gateway/mcp_dispatch.py`
- `wecom_ability_service/domains/admin_console/service.py`

外部依赖：

- `application/class_user/*`
- `domains/questionnaire/service.py`
- `domains/tasks/service.py`
- `domains/outbound_webhook/service.py`
- `domains/user_ops/page_service.py`

类型：

- 读 + 写 + callback + admin

风险等级：

- 高

### 3.2 Member State / Callback

当前 owner：

- `wecom_ability_service/domains/automation_conversion/service.py`

当前职责：

- member overview / stage detail / member detail
- `put_in_pool` / `remove_from_pool`
- `set_follow_type`
- `mark_won` / `unmark_won`
- `push_openclaw`
- `sync_member_activation`
- `sync_member_from_questionnaire_submission`
- `handle_qrcode_enter_from_callback`

直接 caller：

- `wecom_ability_service/http/automation_conversion.py`
- `wecom_ability_service/http/background_jobs.py`
- `wecom_ability_service/http/customer_automation.py`

外部依赖：

- `application/customer_read_model/*`
- `application/identity_contact/*`
- `application/class_user/*`
- `application/questionnaire/*`
- `domains/outbound_webhook/service.py`

类型：

- 读 + 写 + callback + sync

风险等级：

- 高

### 3.3 Outbound Webhook / Retry / Due Runner

当前 owner：

- `wecom_ability_service/domains/outbound_webhook/service.py`

当前职责：

- outbound delivery send
- retry scheduling / due runner
- delivery list / count
- retry result status machine

直接 caller：

- `wecom_ability_service/http/customer_automation.py`
- `wecom_ability_service/domains/admin_jobs/service.py`
- `wecom_ability_service/domains/marketing_automation/service.py`
- `wecom_ability_service/domains/questionnaire/service.py`

外部依赖：

- `requests`
- app settings / runtime config

类型：

- transport + retry runtime + admin read

风险等级：

- 中高

### 3.4 Workflow Runtime / Audience / Execution

当前 owner：

- `wecom_ability_service/domains/automation_conversion/workflow_service.py`
- `wecom_ability_service/domains/automation_conversion/workflow_runtime.py`

当前职责：

- workflow CRUD
- workflow node CRUD
- audience sync / full audience sweep
- execution batch / item read
- dashboard / summary read
- run-due workflow runtime
- profile segment templates

直接 caller：

- `wecom_ability_service/http/automation_conversion.py`
- `wecom_ability_service/domains/automation_conversion/service.py`

外部依赖：

- `wecom_ability_service/services.py::get_recent_messages_by_user`
- `domains/tasks/service.py::dispatch_wecom_task`
- `domains/user_ops/page_service.py`
- questionnaire submission read model

类型：

- admin read + admin write + due runtime + sync

风险等级：

- 高

### 3.5 SOP / Focus Send / Reply Monitor

当前 owner：

- `wecom_ability_service/domains/automation_conversion/service.py`

当前职责：

- SOP config / template / due runner
- focus send batch create / detail / due runner
- reply monitor toggle / capture / due dispatch
- registered due jobs multiplexer
- message activity sync

直接 caller：

- `wecom_ability_service/http/automation_conversion.py`
- `scripts/run_automation_sop.py`
- `scripts/run_automation_conversion_due_jobs.py`

外部依赖：

- `domains/tasks/service.py::dispatch_wecom_task`
- `domains/outbound_webhook/service.py::send_outbound_webhook`
- router callback / orchestration adapters

类型：

- admin write + due runtime + sync

风险等级：

- 高

## 4. 与其他 context 的边界

### 4.1 Identity & Contact Graph

当前边界：

- `apply_activation_webhook` 通过 mobile 反查 identity，再驱动 automation activation sync
- qrcode callback / member sync 依赖 `external_userid` / phone / identity map

Wave 4 口径：

- Automation Engine 可以消费 `application/identity_contact/*`
- Automation Engine 不应再直接写 identity repo 或回头 import identity domain/service

### 4.2 User Ops / Ops & Enrollment

当前边界：

- `marketing_automation.service.send_pool_private_message` 依赖 `user_ops.page_service`
- `workflow_runtime.py` 依赖 `user_ops.page_service` 组装发送 payload / record
- `mark_enrolled` / `unmark_enrolled` 会同步 class user truth

Wave 4 口径：

- Automation Engine 可以调用稳定的 ops / class-user application contract
- 不能继续在 caller 层直接依赖 `domains/user_ops/page_service.py`
- `dispatch_wecom_task` 相关 transport 也不应长期留在 automation domain implementation 里

### 4.3 Questionnaire

当前边界：

- `marketing_automation/service.py` 直接读 `domains/questionnaire/service.py::get_questionnaire_detail`
- `automation_conversion/service.py::sync_member_from_questionnaire_submission` 是显式 questionnaire bridge
- workflow audience 会读取 questionnaire submissions 作为 segment truth

Wave 4 口径：

- Automation Engine 可以消费 `application/questionnaire/*`
- 不能继续直接依赖 `domains/questionnaire/service.py`
- questionnaire submit 后触发 automation 的动作应变成显式 command，而不是 lazy import

### 4.4 Customer Read Model

当前边界：

- `http/customer_automation.py::_candidate_context` 仍拼 customer detail / timeline / recent messages
- MCP tool / admin tool 读 customer context 仍散落在 caller 层

Wave 4 口径：

- Automation Engine 只消费 `application/customer_read_model/*`
- customer context 只能作为 read dependency，不应在 automation controller 里继续扩成跨 context 聚合层

### 4.5 Integration Gateway / Tasks

当前边界：

- `domains/tasks/service.py::dispatch_wecom_task` 是 outbound task transport
- `record_conversion_feedback` 仍从 tasks domain 反向写 marketing truth
- `application/integration_gateway/mcp_dispatch.py` 仍直接 import automation legacy surface

Wave 4 口径：

- `tasks` 在这轮只作为 automation 强耦合 transport 依赖盘点，不整体重构为 automation owner
- automation caller 要逐步从 `services.py` / legacy domain surface 收口到 `application/automation_engine/*`
- 真正的 transport / task dispatch 边界长期应向 integration/application adapter 演进

## 5. 当前 legacy 直连点

下列文件是 Wave 4 必须关注的 direct legacy callers：

| 文件 | 当前直连点 | 说明 |
| --- | --- | --- |
| `wecom_ability_service/http/customer_automation.py` | `domains.automation_conversion.service.sync_member_activation`、现有 automation skeleton 只覆盖一部分 | Wave 1 已收过入口，但 automation owner 仍不完整 |
| `wecom_ability_service/http/admin_config.py` | `services.get_signup_conversion_config`、`save_signup_conversion_config`、`preview_signup_conversion_customer`、`recompute_signup_conversion_customers` | signup conversion config 仍未进 formal automation API |
| `wecom_ability_service/http/sidebar.py` | `domains.marketing_automation.service.get_customer_marketing_profile`、`services.mark_enrolled`、`services.unmark_enrolled` | sidebar 仍是 marketing truth 手工变更入口 |
| `wecom_ability_service/http/admin_support.py` | `domains.marketing_automation.service.mark_enrolled`、`unmark_enrolled` | 后台 support 仍直连 legacy write owner |
| `wecom_ability_service/http/background_jobs.py` | `domains.automation_conversion.service.handle_qrcode_enter_from_callback` | callback 仍直接命中 legacy service |
| `wecom_ability_service/http/automation_conversion.py` | 直接 import `domains.automation_conversion/*` 几乎全部 surface | Wave 4 最大的 admin/callback/runtime caller 面 |
| `wecom_ability_service/domains/admin_jobs/service.py` | `services.list_outbound_webhook_deliveries`、`retry_outbound_webhook_delivery`、`run_due_outbound_webhook_retries` | admin jobs console 仍未切 formal automation API |
| `wecom_ability_service/application/integration_gateway/mcp_dispatch.py` | 直接 import `domains.automation_conversion` 和 `services.*automation*` | MCP tooling 仍是绕过 automation formal owner 的大旁路 |
| `wecom_ability_service/domains/admin_console/service.py` | automation tool metadata 仍指向 `services.record_conversion_feedback` 等旧入口 | admin console 仍没从 legacy automation shim 摘下来 |
| `wecom_ability_service/http/tasks.py` | 直接调 `domains.tasks.service.dispatch_wecom_task` | task transport 和 automation sender 之间仍无 formal port |

## 6. Wave 4 第一批明确不做的事

以下内容虽然和 automation 同域相邻，但不进入本轮第一批 owner 收口：

- `wecom_ability_service/domains/automation_conversion/orchestration_service.py`
  - agent prompt draft / publish / router callback / review output
- `wecom_ability_service/domains/automation_conversion/model_infra`
  - model infra settings / connectivity 测试
- `wecom_ability_service/domains/customer_pulse/*`
- `wecom_ability_service/domains/followup_orchestrator/*`
- `user_ops` / `questionnaire` / `customer_pulse` / `followup_orchestrator` 的内部拆分

原因不是这些内容不重要，而是它们会把 Wave 4 从“Automation Engine formal owner 收口”扩成“整个自动化后台重构”，风险会失控。

## 7. Wave 4 的目标边界

Wave 4 完成时，automation 相关 caller 至少要满足：

1. admin / callback / retry / member-state / workflow runtime caller 不再直接依赖 `services.py` automation surface
2. `http/automation_conversion.py`、`http/customer_automation.py`、`http/admin_config.py`、`http/background_jobs.py`、`http/sidebar.py`、`http/admin_support.py` 只调正式 `application/automation_engine/*`
3. `domains/admin_jobs/service.py` 与 `application/integration_gateway/mcp_dispatch.py` 不再绕 legacy automation owner
4. outbound retry / activation / qrcode callback / workflow run-due / SOP run-due / reply monitor run-due 都有显式 formal command
5. `domains/marketing_automation/service.py`、`domains/automation_conversion/service.py`、`workflow_service.py`、`workflow_runtime.py` 继续保留实现，但对外入口 owner 迁到 application

## 8. 结论

Wave 4 不适合一次性大拆 `automation_conversion` 或 `marketing_automation` 内部模块。

正确顺序应该是：

1. 先把 Automation Engine 的 contract 面补齐
2. 再把最外围 caller 逐批切到 `application/automation_engine/*`
3. 最后才评估内部 owner 是否需要继续拆子模块

也就是说，Wave 4 的第一任务不是“继续拆大文件”，而是先建立一个可信的 application owner。
