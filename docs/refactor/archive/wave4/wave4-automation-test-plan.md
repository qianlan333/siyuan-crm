# Wave 4 Automation Engine Test Plan

日期：2026-04-21

## 1. 目标

Wave 4 的测试计划不是“把 automation 所有测试都跑一遍”，而是先冻结最容易在 caller cutover 中回归的高风险行为。

本轮高风险面有 5 类：

1. signup conversion / feedback / ack
2. outbound webhook / retry / activation
3. member state / qrcode callback
4. workflow runtime / audience / execution
5. SOP / focus send / reply monitor

同时要提前识别哪些现有 guardrail / compatibility tests 会在 formal owner 收口后需要跟着升级，而不是让测试反过来锁死 legacy import。

## 2. 现有关键测试资产

当前仓库里与 automation 强相关的测试资产主要有：

- `tests/test_marketing_automation.py`
- `tests/test_conversion_service.py`
- `tests/test_admin_config.py`
- `tests/test_admin_jobs_console.py`
- `tests/test_automation_conversion_v1.py`
- `tests/test_automation_state_contract.py`
- `tests/test_automation_state_shared.py`
- `tests/test_automation_facade_guards.py`
- `tests/test_mcp_business_tools.py`
- `tests/test_service_layer_layout.py`
- `tests/test_refactor_guardrails.py`
- `tests/test_http_registration_contract.py`
- `tests/test_run_automation_conversion_due_jobs_script.py`
- `tests/test_run_automation_sop_script.py`
- `tests/test_api.py` 中 tasks / admin / webhook / callback 相关用例

## 3. 冻结矩阵

### 3.1 Signup Conversion / Feedback / Ack

| 需要冻结的行为 | 风险原因 | 现有测试 | 备注 |
| --- | --- | --- | --- |
| signup conversion config save/read round-trip | admin_config caller 会最先 cutover，最容易因 DTO 映射丢字段 | `tests/test_marketing_automation.py::test_signup_conversion_config_api_saves_and_reads_back` | Wave 4 PR 早期必跑 |
| invalid auto-start window / invalid question option | config validation 很容易在 command wrapper 中静默漂移 | `tests/test_marketing_automation.py::test_signup_conversion_config_api_rejects_invalid_auto_start_window`、`test_signup_conversion_config_api_rejects_invalid_question_and_option` | PR 切 admin_config 前先冻住 |
| preview current state / mobile-only person | preview 依赖 customer/questionnaire truth，caller cutover 易丢兼容字段 | `tests/test_marketing_automation.py::test_admin_marketing_automation_preview_returns_current_state_and_hits`、`test_admin_marketing_automation_preview_supports_mobile_only_person` | PR 1/2 期间必须保持 |
| recompute refreshes current/history | write owner 改变后最容易只更新 current 不写 history | `tests/test_marketing_automation.py::test_admin_marketing_automation_recompute_refreshes_current_and_history` | Wave 4 核心冻结点 |
| conversion batch detail / filter / customer context | batch detail 当前仍有 `_candidate_context` 混合读路径 | `tests/test_marketing_automation.py::test_signup_conversion_batch_api_filters_candidates_and_attaches_customer_context` | 未来切 controller 聚合时要回归 |
| MCP feedback mark/unmark consistency | feedback 目前从 `tasks.service` 反向写 marketing truth | `tests/test_conversion_service.py::test_mcp_mark_and_unmark_enrolled_tools_use_unified_conversion_service`、`test_mcp_record_conversion_feedback_mark_enrolled_matches_manual_mark` | formal contract 后仍要兼容 |
| end-to-end questionnaire hit -> enrolled exit | signup conversion 横跨 questionnaire / marketing / class_user | `tests/test_marketing_automation.py::test_signup_conversion_e2e_chain_from_questionnaire_hit_to_enrolled_exit` | Wave 4 中后期必跑 |

### 3.2 Outbound Webhook / Retry / Activation

| 需要冻结的行为 | 风险原因 | 现有测试 | 备注 |
| --- | --- | --- | --- |
| focus pool inbound message triggers openclaw webhook | 发送链与 delivery 记录、event_type 强耦合 | `tests/test_marketing_automation.py::test_focus_pool_inbound_message_triggers_openclaw_webhook_with_customer_context` | 关联 `process_inbound_messages_for_openclaw` |
| normal pool inbound message must not trigger webhook | caller cutover 后容易误发 | `tests/test_marketing_automation.py::test_normal_pool_inbound_message_does_not_trigger_openclaw_webhook` | 保底冻结 |
| webhook URL fallback / unified config | runtime config fallback 很容易在 application command 中丢掉 | `tests/test_marketing_automation.py::test_openclaw_webhook_prefers_unified_url_config`、`test_openclaw_webhook_keeps_legacy_url_as_fallback` | Wave 4 retry line要保留 |
| webhook failure schedules retry / manual retry succeeds | retry policy 是 Wave 4 核心主线 | `tests/test_marketing_automation.py::test_focus_pool_webhook_failure_schedules_retry_and_manual_retry_succeeds` | 切 `admin_jobs` / `customer_automation` 前必跑 |
| retry exhausted / failed list filter | list/count/query cutover 容易改坏状态过滤 | `tests/test_marketing_automation.py::test_focus_pool_webhook_retry_exhausted_and_list_endpoint_filters_failed_items` | admin jobs 和 customer automation 同线 |
| missing URL records unconfigured delivery | command wrapper 最容易把 skip 和 failed 混淆 | `tests/test_marketing_automation.py::test_focus_pool_webhook_missing_url_records_unconfigured_delivery` | 继续保留 |
| activation webhook moves pools and refreshes active pool | activation 是 customer_automation 主线的一部分 | `tests/test_marketing_automation.py::test_activation_webhook_moves_inactive_pools_and_refreshes_active_pool` | Wave 4 早期必跑 |
| activation webhook errors / invalid token | controller-only 收口后错误语义不能漂移 | `tests/test_marketing_automation.py::test_activation_webhook_returns_error_when_mobile_not_found`、`test_activation_webhook_rejects_invalid_internal_token` | PR 早期必跑 |
| admin jobs webhook deliveries and run retries | admin jobs 当前仍绕 legacy surface | `tests/test_admin_jobs_console.py::test_api_admin_jobs_webhook_deliveries_and_run_retries`、`test_admin_jobs_retry_webhook_delivery_action_writes_audit` | PR 1 首批切换验证 |

### 3.3 Member State / Callback

| 需要冻结的行为 | 风险原因 | 现有测试 | 备注 |
| --- | --- | --- | --- |
| qrcode callback success path | callback 直连 legacy service，最容易在 formal command 后丢 side effect | `tests/test_automation_conversion_v1.py` 中 qrcode callback 相关用例，包括 `test_qrcode_callback_continues_welcome_and_tag_when_sop_progress_sync_fails` | Wave 4 P1 主冻结点 |
| qrcode callback failure path on automation raise | callback 链要 fail-closed 但不污染其他处理 | `tests/test_user_ops_api.py::test_external_contact_event_marks_failed_when_qrcode_automation_raises` | 已在 Wave 2 closeout 清绿，继续保留 |
| overview/stage detail payload stability | `http/automation_conversion.py` 大量页面直接消费这些 payload | `tests/test_automation_conversion_v1.py::test_automation_conversion_home_stage_cards_show_view_and_send_actions`、`test_automation_conversion_stage_detail_keeps_only_total_and_today_new_metrics` | PR 3 先跑 |
| member put/remove/focus/normal/won transitions | member-state write 最容易在 command action 收口时漏历史写入 | `tests/test_automation_conversion_v1.py` 中 member ops / stage send / push 相关用例 | 如果覆盖不足，先补最小行为冻结再切 caller |
| push-openclaw from member page | push command 同时碰 delivery log 和 member state | `tests/test_automation_conversion_v1.py` 中 `push_openclaw` / focus send 相关用例 | Wave 4 member-state PR 里必跑 |

### 3.4 Workflow Runtime / Audience / Execution

| 需要冻结的行为 | 风险原因 | 现有测试 | 备注 |
| --- | --- | --- | --- |
| workflow create/edit/detail round-trip | CRUD 后台切 formal owner 时最容易 payload 漂移 | `tests/test_api.py::test_automation_conversion_agent_create_and_edit_flow` 只覆盖一部分；workflow 需依赖 `tests/test_automation_conversion_v1.py` 里的 workflow CRUD/execution 用例 | 若现有 workflow CRUD 冻结不够，PR 前先补最小 contract 测试 |
| due jobs API runs registered workflow job | `run_registered_due_jobs` 是 multiplexer，容易漏 job code | `tests/test_automation_conversion_v1.py::test_due_jobs_api_runs_registered_conversion_workflow_job` | Wave 4 workflow PR 必跑 |
| run due script posts canonical body | script/endpoint 合约不能因 command DTO 调整而漂移 | `tests/test_run_automation_conversion_due_jobs_script.py` | script 级冻结 |
| audience sync derived from questionnaire / marketing state | runtime 直接读 questionnaire + services recent messages | 当前主要由 `tests/test_automation_conversion_v1.py` 的 workflow runtime 用例覆盖 | 若不足，先补 audience sync contract 测试 |
| execution list/detail/item payload stability | admin execution pages高度依赖 legacy payload | `tests/test_automation_conversion_v1.py` execution 相关用例 | workflow PR 必跑 |

### 3.5 SOP / Focus Send / Reply Monitor

| 需要冻结的行为 | 风险原因 | 现有测试 | 备注 |
| --- | --- | --- | --- |
| SOP natural day progression / anchor date / reentry | due runner 极易在 command 封装时改变日期语义 | `tests/test_automation_conversion_v1.py` 中 `test_sop_run_due_uses_natural_calendar_day_two_after_entry`、`test_sop_run_due_reentry_keeps_anchor_and_does_not_backfill` 等 | Wave 4 SOP PR 必跑 |
| SOP no duplicate empty batch / lock held skip | due runner 幂等和锁逻辑不能回归 | `tests/test_automation_conversion_v1.py::test_sop_run_due_second_pass_does_not_create_duplicate_empty_batch`、`test_sop_run_due_skips_pool_when_lock_is_held` | 高风险 |
| focus send batch create / run due / item failure isolation | focus send 关联 batch/item state 和 push side effect | `tests/test_automation_conversion_v1.py::test_focus_send_batch_can_be_created_for_inactive_focus_stage`、`test_focus_send_batch_runner_item_failure_does_not_block_batch` | 高风险 |
| reply monitor quiet hours / capture merge / 30-second gap / disabled behavior | reply monitor 是 runtime 行为最复杂的一段 | `tests/test_automation_conversion_v1.py` reply-monitor 相关整段用例 | 需要完整保留 |
| due jobs API registered SOP job | multiplexer 切 formal command 时最容易丢 SOP 任务 | `tests/test_automation_conversion_v1.py::test_due_jobs_api_runs_registered_sop_job` | 与 workflow job 同时冻结 |
| run_automation_sop script internal endpoint contract | script 是 production job 入口之一 | `tests/test_run_automation_sop_script.py` | Wave 4 后半段必跑 |

## 4. 需要特别注意的过渡性测试

### 4.1 `tests/test_automation_facade_guards.py`

当前这个 suite 里有两类断言：

- 应继续保留的断言
  - `domains.automation_conversion.__all__` re-export 稳定
  - monkeypatch seam 稳定
- 后续必须迁移的断言
  - `customer_automation.sync_member_activation is automation_service.sync_member_activation`
  - `background_jobs.handle_qrcode_enter_from_callback is automation_service.handle_qrcode_enter_from_callback`

原因：

- 这两条是“caller 仍直接绑定 legacy service symbol”的旧阶段保护
- 一旦 Wave 4 真正做 caller cutover，它们就应该被新 guardrail 取代，而不是继续锁死 legacy import

因此，Wave 4 实施时必须先补新的 application-owner 断言，再删除这类旧绑定断言。

### 4.2 `tests/test_service_layer_layout.py`

当前这个 suite 仍冻结了若干 automation service alias，例如：

- `apply_activation_webhook`
- `list_outbound_webhook_deliveries`
- `list_signup_conversion_batches`
- `get_signup_conversion_batch`
- `retry_outbound_webhook_delivery`
- `run_due_outbound_webhook_retries`

Wave 4 不应该直接删这些 shim，而应先把 caller 切走，再逐步把这类测试改成“services.py 只保留 compatibility wrapper”。

### 4.3 `tests/test_refactor_guardrails.py`

当前 guardrail 已经明确：

- `http/automation_conversion.py` 是 `requests` 历史例外
- `http/admin_config.py` 仍允许 import `services`
- `http/customer_automation.py` 仍允许 import `services`

Wave 4 每切掉一批 caller，都应该同步缩小 allowlist，而不是最后一次性全改。

## 5. 建议的最小回归集

### 5.1 PR 1 / PR 2 之后

- `tests/test_http_registration_contract.py`
- `tests/test_service_layer_layout.py`
- `tests/test_refactor_guardrails.py`
- `tests/test_marketing_automation.py -k "signup_conversion_config or activation_webhook"`
- `tests/test_admin_jobs_console.py -k "webhook"`

### 5.2 切 marketing truth / member-state caller 之后

- `tests/test_marketing_automation.py -k "preview or recompute or batch or enrolled or webhook"`
- `tests/test_automation_conversion_v1.py -k "member or stage or qrcode or due_jobs_api_runs_registered"`
- `tests/test_user_ops_api.py -k "qrcode_automation_raises"`
- `tests/test_refactor_guardrails.py`

### 5.3 切 workflow runtime / audience / execution 之后

- `tests/test_automation_conversion_v1.py -k "workflow or execution or dashboard or profile_segment"`
- `tests/test_run_automation_conversion_due_jobs_script.py`
- `tests/test_http_registration_contract.py`
- `tests/test_refactor_guardrails.py`

### 5.4 切 SOP / focus / reply monitor 之后

- `tests/test_automation_conversion_v1.py -k "sop or focus_send or reply_monitor or due_jobs_api_runs_registered"`
- `tests/test_run_automation_sop_script.py`
- `tests/test_run_automation_conversion_due_jobs_script.py`
- `tests/test_http_registration_contract.py`
- `tests/test_refactor_guardrails.py`

### 5.5 仓库级 closeout 回归

- `tests/test_marketing_automation.py`
- `tests/test_automation_conversion_v1.py`
- `tests/test_admin_jobs_console.py`
- `tests/test_admin_config.py -k "marketing_automation or automation_conversion"`
- `tests/test_mcp_business_tools.py -k "conversion or marketing"`
- `tests/test_http_registration_contract.py`
- `tests/test_service_layer_layout.py`
- `tests/test_refactor_guardrails.py`

## 6. 当前测试缺口判断

按现有仓库状态，automation 的核心行为测试并不缺“数量”，真正的缺口在于：

- formal application owner 建立后，缺少与 application contract 对齐的 import / owner guardrail
- `tests/test_automation_facade_guards.py` 里仍有旧阶段的 direct-binding 断言
- workflow audience / execution cutover 缺少显式“application contract”冻结层

因此，Wave 4 实施期的原则应该是：

1. 先补最小 contract / owner 冻结
2. 再切 caller
3. 最后再收紧 legacy import allowlist

## 7. 结论

Wave 4 的测试策略不能只依赖大而全的 `tests/test_automation_conversion_v1.py`。

真正有效的策略是：

- 用现有大套件冻结行为
- 用新的 contract / guardrail 测试冻结 owner 和调用方向
- 每切一批 caller，就同步缩 allowlist

否则测试只会继续帮 legacy 结构“保鲜”，而不是帮 formal owner 落地。
