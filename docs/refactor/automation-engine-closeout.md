# Automation Engine Closeout

日期：2026-04-21

## 正式结论

按 2026-04-21 最新两份回单合并判断，Wave 4 的唯一阻塞 gate 已清绿。`automation_engine` 这一轮收口已达到正式 closeout 条件：formal application owner 已建立，primary caller 已切到 `wecom_ability_service/application/automation_engine/*`，`services.py` 已退为 compatibility shim，workflow/runtime 兼容回归与 application delegate seam 回归均已恢复为绿灯。

本文件用于固化 automation engine 维度的最终 closeout 口径；Wave 4 的全局结论见 [wave4-closeout.md](/Users/qianlan/Downloads/CRM%20开发/AI-CRM%20开发/docs/refactor/wave4-closeout.md)。

## 已完成的主线

### 1. admin/read-write caller cutover

- 当前 owner 文件
  - `wecom_ability_service/application/automation_engine/queries.py`
  - `wecom_ability_service/application/automation_engine/commands.py`
  - `wecom_ability_service/http/admin_config.py`
  - `wecom_ability_service/http/customer_automation.py`
  - `wecom_ability_service/http/background_jobs.py`
  - `wecom_ability_service/http/sidebar.py`
  - `wecom_ability_service/domains/admin_jobs/service.py`
- 当前已完成
  - signup conversion config 的读取、保存、preview、recompute 已进入正式 query / command
  - customer automation 的 batch list / detail、activation webhook、outbound webhook list / retry / run-due 已进入正式 query / command
  - background callback 的 qrcode enter 写入口已进入 `HandleQrcodeEnterFromCallbackCommand`
  - sidebar 的 marketing profile / manual segment / enrolled / unenrolled 已进入正式 query / command
  - admin jobs 的 outbound webhook count / list / retry / due runner 已进入正式 query / command
  - admin config 的 automation dispatch-history read 面已补齐 formal query seam，不再由 caller 直接依赖 domain helper
- 仍保留的 compatibility shim
  - `wecom_ability_service/services.py::{list_outbound_webhook_deliveries,retry_outbound_webhook_delivery,run_due_outbound_webhook_retries,apply_activation_webhook,list_signup_conversion_batches,get_signup_conversion_batch,get_outbound_webhook_delivery_counts,get_signup_conversion_config,save_signup_conversion_config,preview_signup_conversion_customer,recompute_signup_conversion_customers,record_conversion_feedback,ack_conversion_batch,get_customer_marketing_profile,mark_enrolled,unmark_enrolled,set_manual_followup_segment}`
- 已知技术债
  - `wecom_ability_service/http/customer_automation.py::_candidate_context` 仍在 controller 侧组装 customer chat context
  - `wecom_ability_service/domains/admin_console/service.py` 的 tool registry 仍用 `service_paths` 指向 `services.py` automation wrappers
  - `wecom_ability_service/application/integration_gateway/mcp_dispatch.py` 仍保留 automation 的 legacy bridge，不属于本轮 caller cutover 阻塞

### 2. member state

- 当前 owner 文件
  - formal owner: `wecom_ability_service/application/automation_engine/commands.py`
  - internal owner: `wecom_ability_service/domains/automation_conversion/member_state_service.py`
- 当前已完成
  - member detail / pool state mutation / won state mutation / follow type mutation 已抽到 `member_state_service.py`
  - activation sync 与 qrcode callback 已落到同一内部 owner
  - 外层 callback / activation 写入口已不再直连 legacy member-state 实现
- 仍保留的 compatibility shim
  - `wecom_ability_service/domains/automation_conversion/service.py::{get_member_detail,apply_router_target_pool,put_in_pool,remove_from_pool,set_follow_type,mark_won,unmark_won,sync_member_activation,handle_qrcode_enter_from_callback}`
- 已知技术债
  - `http/automation_conversion.py` 仍属于同 context admin transport façade，尚未整体切成 application-only
  - member-state live context / snapshot 仍复用 `domains/automation_conversion/service.py` 中的 shared helper

### 3. signup conversion

- 当前 owner 文件
  - formal owner: `wecom_ability_service/application/automation_engine/queries.py` 与 `commands.py`
  - internal owner: `wecom_ability_service/domains/automation_conversion/signup_conversion_service.py`
- 当前已完成
  - batch list / detail read 已进入独立内部 owner
  - conversion feedback / ack 已进入独立内部 owner
  - 外层 caller 已不再把 `services.py` 视为默认 owner
- 仍保留的 compatibility shim
  - `wecom_ability_service/services.py::{list_signup_conversion_batches,get_signup_conversion_batch,record_conversion_feedback,ack_conversion_batch}`
  - `wecom_ability_service/domains/marketing_automation/service.py::{list_signup_conversion_batches,get_signup_conversion_batch,ack_conversion_batch}`
- 已知技术债
  - config 保存、preview、recompute 仍在 `wecom_ability_service/domains/marketing_automation/service.py` 中，尚未拆成更细的内部 owner
  - admin console / MCP 的 conversion tools 仍通过 compatibility shim 暴露

### 4. outbound webhook / retry

- 当前 owner 文件
  - formal owner: `wecom_ability_service/application/automation_engine/queries.py` 与 `commands.py`
  - internal owner: `wecom_ability_service/domains/outbound_webhook/message_dispatch_service.py`
- 当前已完成
  - delivery send / retry / run-due / list / count 已收敛到 `message_dispatch_service.py`
  - customer automation 与 admin jobs 的 retry / count / list caller 已走正式 application owner
- 仍保留的 compatibility shim
  - `wecom_ability_service/services.py::{list_outbound_webhook_deliveries,get_outbound_webhook_delivery_counts,retry_outbound_webhook_delivery,run_due_outbound_webhook_retries}`
  - `wecom_ability_service/domains/outbound_webhook/service.py::{_attempt_delivery,send_outbound_webhook,retry_outbound_webhook_delivery,run_due_outbound_webhook_retries,list_outbound_webhook_deliveries,get_outbound_webhook_delivery_counts}`
- 已知技术债
  - runtime config、Flask config、`requests` transport helper 仍留在 `wecom_ability_service/domains/outbound_webhook/service.py`
  - questionnaire submit webhook 与 automation delivery 仍共享同一 outbound webhook 基础设施，但 formal owner 已分离

### 5. workflow runtime

- 当前 owner 文件
  - `wecom_ability_service/domains/automation_conversion/workflow_runtime_service.py`
  - `wecom_ability_service/domains/automation_conversion/workflow_execution_service.py`
  - `wecom_ability_service/domains/automation_conversion/router_dispatch_service.py`
- 当前已完成
  - workflow due runner / audience sync 已进入 `workflow_runtime_service.py`
  - workflow execution dashboard / list / detail 已进入 `workflow_execution_service.py`
  - router callback / review / replay decision 已进入 `router_dispatch_service.py`
  - manual-layered 节点内容 masking、dirty standard content 清理、dashboard questionnaire truth source、recent execution summary 挂载等兼容回归已修复
- 仍保留的 compatibility shim
  - `wecom_ability_service/domains/automation_conversion/orchestration_service.py::{validate_router_callback_signature,backfill_missing_child_agent_replies,run_agent_router_shadow_decision,handle_agent_router_callback,record_agent_output_outcome,review_agent_reply_output}`
  - `wecom_ability_service/domains/automation_conversion/workflow_runtime.py`
  - `wecom_ability_service/domains/automation_conversion/workflow_service.py`
- 已知技术债
  - `http/automation_conversion.py` 仍直接面向同 context workflow / router façade
  - workflow runtime 仍依赖 task dispatch、recent-messages、user-ops page payload 等 shared runtime bridge

### 6. message dispatch

- 当前 owner 文件
  - `wecom_ability_service/domains/marketing_automation/message_dispatch_service.py`
  - `wecom_ability_service/domains/outbound_webhook/message_dispatch_service.py`
- 当前已完成
  - pool private message / focus webhook / inbound openclaw processing 已从 `marketing_automation/service.py` 抽离
  - outbound delivery send / retry runtime 已从 `outbound_webhook/service.py` 抽离
- 仍保留的 compatibility shim
  - `wecom_ability_service/domains/marketing_automation/service.py::{send_pool_private_message,trigger_openclaw_focus_message_webhook,process_inbound_messages_for_openclaw}`
  - `wecom_ability_service/domains/outbound_webhook/service.py::{send_outbound_webhook,retry_outbound_webhook_delivery,run_due_outbound_webhook_retries}`
- 已知技术债
  - `domains/tasks/service.py::dispatch_wecom_task` 仍是 workflow / message dispatch 的下游 transport 依赖
  - 这一层还没有继续向更细的 integration adapter 演进，但不阻塞 Wave 4 closeout

## 最终测试口径

### 1. closeout gate 关键绿灯

- `./.venv311/bin/python -m pytest -q tests/test_automation_engine_application_contract.py`
  - `3 passed`
- `./.venv311/bin/python -m pytest -q tests/test_automation_conversion_v1.py -k "workflow or execution or dashboard"`
  - `44 passed, 143 deselected`

### 2. 合并两份回单后的最终回归

- `./.venv311/bin/python -m pytest -q tests/test_http_registration_contract.py`
  - `5 passed`
- `./.venv311/bin/python -m pytest -q tests/test_refactor_guardrails.py`
  - `10 passed`
- `./.venv311/bin/python -m pytest -q tests/test_marketing_automation.py`
  - `39 passed`
- `./.venv311/bin/python -m pytest -q tests/test_admin_jobs_console.py`
  - `15 passed`
- `./.venv311/bin/python -m pytest -q tests/test_api.py -k "automation_conversion or sidebar_signup_tag_mark or questionnaire_submit_webhook"`
  - `7 passed, 110 deselected`
- `./.venv311/bin/python -m pytest -q tests/test_api.py -k "marketing_automation or automation_conversion or activation_webhook or webhook_deliveries"`
  - `2 passed, 115 deselected`

### 3. 结果判断

上面两组结果共同覆盖了：

- formal application delegate seam
- workflow/runtime 兼容回归
- HTTP 注册契约
- refactor guardrails
- marketing automation 主回归
- admin jobs console automation 回归
- automation 相关 API 子集回归

因此，Wave 4 当前已不存在新的唯一红灯。

## 当前非阻塞例外

以下例外仍保留，但都已经被限制在 compatibility / bridge / legacy delegate 范围内，不再阻塞 closeout：

- `wecom_ability_service/services.py` 的 automation wrappers
- `wecom_ability_service/application/integration_gateway/mcp_dispatch.py` 中的 automation tool bridge
- `wecom_ability_service/domains/admin_console/service.py` 的 automation `service_paths`
- `wecom_ability_service/http/customer_automation.py::_candidate_context`
- `wecom_ability_service/http/automation_conversion.py` 的同 context legacy façade
- `wecom_ability_service/domains/marketing_automation/service.py` 中尚未继续下沉的 config / preview / recompute / truth logic
- `wecom_ability_service/domains/automation_conversion/orchestration_service.py` 中尚未继续细拆的 agent orchestration / review façade
- `wecom_ability_service/domains/automation_conversion/workflow_runtime.py` 与 `workflow_service.py` 作为 legacy delegate target
- `wecom_ability_service/domains/outbound_webhook/service.py` 中尚未继续抽走的 runtime / transport helper
- `wecom_ability_service/domains/tasks/service.py::dispatch_wecom_task` 作为 automation 运行时的下游 transport 依赖

详细说明见：

- [automation-engine-remaining-exceptions-ledger.md](/Users/qianlan/Downloads/CRM%20开发/AI-CRM%20开发/docs/refactor/automation-engine-remaining-exceptions-ledger.md)
- [automation-engine-primitive-boundary.md](/Users/qianlan/Downloads/CRM%20开发/AI-CRM%20开发/docs/refactor/automation-engine-primitive-boundary.md)

## Closeout 判断

从 formal owner、primary caller cutover、internal owner 拆分、compatibility gate、workflow/runtime 回归 5 个维度看，`automation_engine` 已满足本轮正式 closeout 条件。

正式结论：`automation_engine` 已 completed and closed。
