# Wave 5 AI Assist Scope

日期：2026-04-21

## 1. 目标

Wave 5 只处理 `AI Assist` 这个 context 的范围盘点和合同化设计，不改业务代码，不改测试，不进入 `customer read model` / `automation engine` / `user_ops` / `questionnaire` 的内部拆分。

本轮要解决的不是“再写一份宏观蓝图”，而是把当前已经混在一起的 4 条 AI Assist 主线先拆清：

1. customer pulse inbox / detail / signal / snapshot / card
2. customer pulse action / feedback / metrics / recompute
3. followup orchestrator mission / assignment / board / action / undo
4. admin customer profile 中 pulse / followup 的嵌入边界

同时要把这些主线与 `customer read model` / `automation engine` / `platform foundation` 的边界说清，明确哪些 caller 未来必须切到正式 `application/ai_assist/*`。

## 2. 当前现状

当前 AI Assist 的主要问题不是“某一个大文件太长”，而是 owner 被拆散在 2 个 domain 包、2 个 controller 文件、1 个 admin glue 文件和 1 个不完整的 application skeleton 里：

| 当前 owner 文件 | 当前承载职责 | 直接 caller | 当前问题 |
| --- | --- | --- | --- |
| `wecom_ability_service/application/ai_assist/queries.py` | 目前只有 `GetCustomerPulseDetailQuery` | `domains/admin_console/customer_profile_service.py` | formal owner 只有一条 detail query，而且还直接 import `domains.customer_pulse.*` / `customer_center.pulse_service`，没有稳定 delegate seam |
| `wecom_ability_service/domains/customer_pulse/service.py` | feature gate、read scope、signal / snapshot / card 物化、inbox/detail、action preview/execute/undo、feedback、metrics、run-due job | `http/admin_customer_pulse.py`、`application/ai_assist/queries.py`、`http/admin_console.py`、`http/admin_customers.py`、`domains/followup_orchestrator/service.py` | 同时做 read model、write action、tenant access、metrics、job runner、AI recommendation fallback，domain owner 过宽 |
| `wecom_ability_service/domains/followup_orchestrator/service.py` | mission sync、team board、my missions、mission detail、assignment decision、preview / execute / undo、handoff | `http/admin_followup_orchestrator.py`、`http/admin_console.py`、`http/admin_customers.py` | 直接把 customer pulse 当输入源，又自己承接 mission action / audit / AI enhancement glue，owner 混在一起 |
| `wecom_ability_service/http/admin_customer_pulse.py` | admin page、admin/internal APIs、action token、internal token、audit/security glue、直接 domain 调用 | 页面、API 和 internal endpoints 本身 | controller 同时做协议、权限、业务编排、metrics source 选择和 direct domain call，不是 controller-only |
| `wecom_ability_service/http/admin_followup_orchestrator.py` | admin page、internal APIs、mission action 路由、action token、internal token | 页面、API 和 internal endpoints 本身 | controller 同时做 feature gate、mission sync、mission item action、direct domain call，不是 controller-only |
| `wecom_ability_service/domains/admin_console/customer_profile_service.py` | admin customer profile 的 pulse widget glue | `http/admin_customers.py` | 虽然已开始使用 `GetCustomerPulseDetailQuery`，但仍直接 import `domains.customer_pulse.is_customer_pulse_inbox_enabled` 和 pulse access helper，边界未收紧 |

当前 Wave 1 遗留的 `application/ai_assist` 只覆盖：

- `CustomerPulseDetailQueryDTO`
- `GetCustomerPulseDetailQuery`

这说明 formal owner 已经起头，但 AI Assist 的大部分 read / action / mission / feedback / metrics caller 仍未正式收口。

## 3. AI Assist 的 4 条主线

### 3.1 Customer Pulse Read Surface

当前 owner：

- `wecom_ability_service/domains/customer_pulse/service.py`
- `wecom_ability_service/application/ai_assist/queries.py`（仅 detail widget）

当前职责：

- inbox 列表
- card detail / evidence
- customer detail widget
- stats / dashboard
- signal / snapshot / activity / execution read projection

直接 caller：

- `wecom_ability_service/http/admin_customer_pulse.py`
- `wecom_ability_service/domains/admin_console/customer_profile_service.py`
- `wecom_ability_service/http/admin_console.py`
- `wecom_ability_service/http/admin_customers.py`
- `wecom_ability_service/domains/followup_orchestrator/service.py`

类型：

- read model + admin read

风险等级：

- 高

### 3.2 Customer Pulse Action / Feedback / Metrics

当前 owner：

- `wecom_ability_service/domains/customer_pulse/service.py`

当前职责：

- refresh / recompute / run-due
- action preview / execute / undo
- feedback submit
- metrics / security counters / audit labels

直接 caller：

- `wecom_ability_service/http/admin_customer_pulse.py`
- `wecom_ability_service/domains/followup_orchestrator/service.py`（通过 pulse card action 间接复用）

外部依赖：

- `domains.tasks.service`
- `domains.tags.service`
- `domains.marketing_automation.service`
- Flask request/app context

类型：

- write + feedback + maintenance + security metrics

风险等级：

- 高

### 3.3 Followup Orchestrator Mission / Action

当前 owner：

- `wecom_ability_service/domains/followup_orchestrator/service.py`
- `wecom_ability_service/domains/followup_orchestrator/ai_enhancement.py`

当前职责：

- 从 customer pulse cards 同步 mission
- team board / my missions / customer payload / mission detail
- claim / accept / complete / request_manager_approval
- item preview / execute / undo
- assignment decision / execution log / handoff packet
- AI enhancement success / fallback / low-confidence degrade

直接 caller：

- `wecom_ability_service/http/admin_followup_orchestrator.py`
- `wecom_ability_service/http/admin_console.py`
- `wecom_ability_service/http/admin_customers.py`

外部依赖：

- `domains.customer_pulse.*`
- `domains.customer_pulse.access.*`
- `domains.automation_conversion.repo`
- `domains.automation_conversion.agents.llm_client`

类型：

- read + write + mission runtime + AI enhancement

风险等级：

- 高

### 3.4 Admin Customer Profile Pulse / Followup Boundary

当前 owner：

- `wecom_ability_service/domains/admin_console/customer_profile_service.py`
- `wecom_ability_service/http/admin_customers.py`

当前职责：

- profile page 中 pulse widget 的 payload 组装
- customer detail 页面暴露 pulse / followup 相关 API URL
- 根据 access context 控制 pulse / followup 可见性

当前问题：

- customer profile 应该只是 admin view-model glue，不应承担 pulse / followup 的业务 owner
- profile 页只应该消费正式 AI Assist query，不应该继续摸 `domains.customer_pulse.access` 或 feature gate helper
- `followup_orchestrator` 当前在 profile 页还只是“链接和入口”的边界，没有 formal query owner

类型：

- admin shell / view-model glue

风险等级：

- 中高

## 4. 与相邻 Context 的边界

## 4.1 与 Customer Read Model 的边界

`AI Assist` 可以依赖 `customer read model` 提供的稳定读面，但不应重新拥有客户基础资料、时间线和消息读取逻辑。

允许依赖的未来正式入口：

- `ListCustomersQuery`
- `GetCustomerDetailQuery`
- `GetCustomerTimelineQuery`
- `GetCustomerChatContextQuery`
- `ListRecentMessagesQuery`

边界要求：

- AI Assist 不应在 controller 层直接拼 customer detail / timeline / recent messages
- `domains/customer_pulse/service.py::_load_context()` 这类混合读取未来应逐步改成依赖 application read API 或内部 read adapter
- admin customer profile 只负责嵌入 pulse / followup 结果，不负责自己构造 AI Assist truth

## 4.2 与 Automation Engine 的边界

`AI Assist` 可以消费 automation runtime 提供的 agent output / dispatch / execution 结果，但不应继续直连 automation repo 或 dispatch primitive。

当前越界点：

- `domains/customer_pulse/ai_recommendation.py` 直接用 `domains.automation_conversion.repo`
- `domains/followup_orchestrator/ai_enhancement.py` 直接用 `domains.automation_conversion.repo` 和 `agents.llm_client`
- `domains/customer_pulse/service.py` 直接用 `domains.tasks.service`

未来边界要求：

- agent run / output / LLM provider 访问通过 `application/automation_engine/*` 或 automation runtime adapter
- message dispatch / followup task dispatch 通过 `DispatchAutomationMessageCommand` 一类正式 contract，而不是 `tasks.service` 直连
- AI Assist 不负责重写 automation member / workflow runtime truth

## 4.3 与 Platform Foundation 的边界

`platform foundation` 保留 transport / auth / internal token / action token / request metadata glue；`AI Assist` 只承接业务读写与 mission/action 编排。

平台层保留职责：

- `require_internal_api_token`
- admin action token 校验
- session / request / header 解析
- tenant / actor / auth mode 的 transport glue

AI Assist 不应拥有：

- Flask `request` / `session` / `current_app` 决策
- internal token transport 判断
- admin action token transport 判断

## 5. 当前 Legacy 直连点

当前最明确的 legacy 直连点如下：

1. `http/admin_customer_pulse.py` 直接 import `domains.customer_pulse.*` 和 `domains.customer_pulse.repo`
2. `http/admin_followup_orchestrator.py` 直接 import `domains.followup_orchestrator.*`
3. `application/ai_assist/queries.py` 直接 import `domains.customer_pulse.*` / `domains.customer_pulse.access.*`
4. `domains/admin_console/customer_profile_service.py` 直接 import `domains.customer_pulse.is_customer_pulse_inbox_enabled` 和 pulse access helper
5. `http/admin_console.py` / `http/admin_customers.py` 直接 import pulse / followup feature gate helper
6. `domains/followup_orchestrator/service.py` 直接 import `domains.customer_pulse` 的 inbox / card / action 接口
7. `domains/customer_pulse/ai_recommendation.py` 与 `domains/followup_orchestrator/ai_enhancement.py` 直接 import `domains.automation_conversion.repo`

需要特别说明：

- 本轮 AI Assist 并不存在一条类似 Wave 2/3 的 `services.py` 主写入口；问题不在 `services.py`，而在 controller / domain 直连
- 因此 Wave 5 的主线不是“先收缩 services shim”，而是“先建立完整 application owner，再切 caller”

## 6. 建议的正式命名空间

建议 Wave 5 形成以下正式命名空间：

- `wecom_ability_service/application/ai_assist/__init__.py`
- `wecom_ability_service/application/ai_assist/dto.py`
- `wecom_ability_service/application/ai_assist/queries.py`
- `wecom_ability_service/application/ai_assist/commands.py`
- `wecom_ability_service/application/ai_assist/_legacy_delegate.py`

其中：

- `queries.py` 只放 stable read API
- `commands.py` 只放 stable action / feedback / maintenance API
- `_legacy_delegate.py` 统一承接当前 `domains.customer_pulse/*` 与 `domains.followup_orchestrator/*` 的 legacy delegate
- 不把 `application/ai_assist/*` 写成第二个 `services.py`

## 7. 建议的内部 owner 切分方向

Wave 5 在 caller cutover 完成后，建议内部 owner 再拆成以下 6 块：

1. `pulse_read_service`
   - inbox / detail / card / evidence / stats / dashboard
2. `pulse_action_service`
   - refresh / recompute / preview / execute / undo
3. `pulse_feedback_metrics_service`
   - feedback / metrics / security counters / activity log presentation
4. `followup_mission_read_service`
   - overview / customer payload / my missions / team board / mission detail
5. `followup_mission_action_service`
   - sync / mission action / preview / execute / undo / handoff
6. `followup_ai_enhancement_service`
   - AI enhancement、provider fallback、low-confidence degrade、agent output bridge

这 6 块是内部 owner，不是这次 scoping pack 就要落代码的文件列表。

## 8. 本轮明确不做的事

- 不在 Wave 5 第一批里拆 `domains/customer_pulse/service.py` 和 `domains/followup_orchestrator/service.py`
- 不在 AI Assist PR 中顺手回收 `customer read model` 内部实现
- 不在 AI Assist PR 中深拆 `automation engine` 的 agent runtime / workflow runtime
- 不做 schema / SQL migration
- 不进入 `customer_pulse` / `followup_orchestrator` 之外的 `customer_pulse` 相邻 context，例如 `questionnaire` / `user_ops` / `automation_conversion` 内部大拆

## 9. 结论

Wave 5 AI Assist 的正确推进顺序应该是：

1. 先把 `application/ai_assist/*` 提升为 formal owner
2. 再切 `admin_customer_pulse` / `admin_followup_orchestrator` / `admin customer profile` 这些最明确 caller
3. 最后才做 pulse / followup 的内部 owner 拆分与 closeout

只有按这个顺序，才能在不破坏 Wave 1–4 已完成成果的前提下，把 AI Assist 从 controller / domain 直连拉回正式 application owner。
