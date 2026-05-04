# Wave 5 AI Assist Test Plan

日期：2026-04-21

## 1. 目标

本测试计划只服务于 Wave 5 的 AI Assist 主线，目标是先冻结合同，再切 wiring。

冻结重点：

- customer pulse inbox / detail / evidence / widget / stats
- pulse refresh / recompute / preview / execute / undo / feedback / metrics
- request-scoped 多租户隔离与权限校验
- followup orchestrator 的 board / mission / assignment / action / undo
- AI enhancement success / fallback / low-confidence degrade
- admin customer profile 中 pulse / followup 边界不漂移

本文件不新增测试代码，只说明：

- 当前已有哪些覆盖
- 哪些覆盖不足
- 建议在后续 PR 1–PR 6 分别补哪些冻结测试

## 2. 现有覆盖盘点

| 冻结主题 | 当前已有测试 | 现状判断 |
| --- | --- | --- |
| admin customer profile pulse widget | `tests/test_admin_customer_profile_console.py::test_admin_customer_profile_page_and_pulse_api_render_ai_customer_pulse` | 已覆盖 profile 页面与 `/api/admin/customers/profile/pulse` 的主路径，但尚未冻结 application contract owner |
| customer pulse page / inbox / refresh / execute / feedback / undo | `tests/test_customer_pulse_inbox.py::test_customer_pulse_refresh_execute_and_feedback_flow` 等 | 已有较完整行为覆盖，是 Wave 5 最核心的冻结基线 |
| customer pulse card detail / evidence / widget consistency | `tests/test_customer_pulse_inbox.py::test_customer_pulse_card_exposes_why_now_and_evidence_refs`、`test_customer_pulse_customer_widget_payload_matches_inbox_card` | 已覆盖 detail/evidence/widget 三条线 |
| customer pulse request-scoped tenant isolation / cross-tenant denial / permission matrix | `tests/test_customer_pulse_inbox.py` 中 request-scoped 系列用例 | 多租户、权限、evidence access、cross-tenant denial 已有较强覆盖 |
| customer pulse stats / metrics / security counters | `tests/test_customer_pulse_inbox.py::test_customer_pulse_stats_api_reports_metrics_and_security_counters` | stats / metrics 主路径已有覆盖 |
| customer pulse rollout / review / quality gates | `tests/test_customer_pulse_inbox.py` rollout/report 用例、`tests/test_customer_pulse_quality_gates.py::test_customer_pulse_quality_gates_handle_bulk_multi_tenant_workloads` | 已覆盖 rollout 与 bulk multi-tenant quality gates |
| followup orchestrator page / overview / board / my missions / mission detail | `tests/test_followup_orchestrator_skeleton.py::test_followup_orchestrator_page_and_api_render_from_real_customer_pulse_cards`、`test_internal_team_board_generates_rule_based_missions_and_signals`、`test_internal_my_missions_filters_for_actor` | 已覆盖 page / read model / team board / actor mission 基线 |
| followup mission action / preview / execute / undo / handoff | `tests/test_followup_orchestrator_skeleton.py::test_internal_claim_action_updates_status_and_execution_log`、`test_admin_action_endpoint_executes_instead_of_returning_not_implemented`、`test_admin_mission_item_preview_execute_and_undo_flow`、`test_request_scoped_handoff_approval_generates_packet_and_new_owner_can_accept` | 已覆盖 mission 主动作与 approval/handoff |
| followup AI enhancement success / fallback / low-confidence degrade | `tests/test_followup_orchestrator_skeleton.py::test_followup_orchestrator_ai_enhancement_success_generates_handoff_and_batch_drafts`、`...falls_back_on_provider_error`、`...degrades_on_low_confidence` | AI enhancement 风险面已有关键冻结 |
| customer center 侧对 pulse 的回退语义 | `tests/test_api.py::test_customer_center_detail_customer_pulse_falls_back_to_rule_suggestion_when_ai_confidence_is_low` | 已冻结 pulse AI 低置信回退，不应在 Wave 5 回归 |

## 3. 关键风险与缺口

### 3.1 还没有 application contract 级测试

当前已覆盖：

- 大量 HTTP / integration / domain 行为测试

当前缺口：

- 没有一组显式测试把 `application/ai_assist/*` 的 formal contract 冻结下来
- `application/ai_assist/queries.py` 目前只有一条 detail query，也没有 delegate seam contract test

### 3.2 admin shell / page-visible 边界覆盖偏弱

当前已覆盖：

- profile 页面和 pulse widget

当前缺口：

- `http/admin_console.py` 的 quick link 可见性是否通过正式 query 驱动，没有独立冻结
- `http/admin_customers.py` 中 followup URL 暴露与 feature gate 组合没有独立 contract test

### 3.3 pulse 与 followup 之间的桥接还没有单独冻结

当前已覆盖：

- followup team board 可以从真实 pulse cards 渲染出来
- mission item execute / undo 能回写 pulse execution

当前缺口：

- 没有独立测试明确“followup 只能消费 pulse formal owner，而不是 domain direct import”
- 这是架构层缺口，不是行为层缺口，需要在 guardrail/application contract 测试里补

## 4. PR 1 测试计划

PR 1 目标是建立 `application/ai_assist/*` formal owner，不切 caller。

建议新增测试文件：

- `tests/test_ai_assist_application_contract.py`

建议冻结的最小 contract：

1. `GetCustomerPulseDetailQuery`
   - 委托到 `_legacy_delegate`
   - 保持 `pulse` / `customer_pulse` 双结构
2. `ListCustomerPulseInboxQuery`
   - 保持 inbox payload 主结构
3. `GetCustomerPulseCardQuery` / `GetCustomerPulseCardEvidenceQuery`
   - 保持 card detail / evidence 输出 key
4. `PreviewCustomerPulseCardActionCommand` / `ExecuteCustomerPulseCardActionCommand` / `UndoCustomerPulseCardActionCommand`
   - 只验证 delegate seam 和主结构，不重写业务逻辑
5. `GetFollowupOrchestratorOverviewQuery` / `GetFollowupTeamBoardQuery` / `GetFollowupMissionDetailQuery`
   - 保持 overview / board / mission detail 的 legacy delegate 兼容
6. `SyncFollowupMissionsCommand` / `ApplyFollowupMissionActionCommand` / `ExecuteFollowupMissionItemActionCommand`
   - 保持主返回结构与 legacy delegate 一致

PR 1 必跑：

- `tests/test_ai_assist_application_contract.py`
- `tests/test_http_registration_contract.py`
- `tests/test_service_layer_layout.py`
- `tests/test_refactor_guardrails.py`

## 5. PR 2 测试计划

PR 2 目标是切 customer pulse caller：

- `http/admin_customer_pulse.py`
- `domains/admin_console/customer_profile_service.py`
- 相关 admin shell / customer profile pulse 边界

必须冻结的行为：

1. pulse widget
   - `/api/admin/customers/profile/pulse` 仍返回 `pulse` 和 `customer_pulse`
2. inbox / stats / detail / evidence
   - path、核心 JSON key、错误主语义不变
3. refresh / preview / execute / feedback / undo
   - 行为和 side effect 不倒退
4. request-scoped tenant isolation
   - cross-tenant read/write denial 仍成立
5. stats / security counters
   - 统计口径不漂移

PR 2 主要依赖现有测试文件：

- `tests/test_customer_pulse_inbox.py`
- `tests/test_admin_customer_profile_console.py`
- `tests/test_api.py -k "customer_pulse"`
- `tests/test_http_registration_contract.py`
- `tests/test_refactor_guardrails.py`

## 6. PR 3 测试计划

PR 3 目标是切 followup orchestrator caller：

- `http/admin_followup_orchestrator.py`
- `http/admin_console.py` / `http/admin_customers.py` 中 followup 可见性与 URL boundary

必须冻结的行为：

1. followup page / overview / team board / my missions
2. mission detail
3. claim / accept / complete / request_manager_approval
4. item preview / execute / undo
5. AI enhancement success / fallback / low-confidence degrade
6. request-scoped mission access denial

PR 3 主要依赖现有测试文件：

- `tests/test_followup_orchestrator_skeleton.py`
- `tests/test_http_registration_contract.py`
- `tests/test_refactor_guardrails.py`

## 7. PR 4 / PR 5 测试计划

PR 4 目标是 customer pulse internal split。

必须冻结：

- signal / snapshot / card 物化不漂移
- feedback / metrics / security counters 不漂移
- recompute / due job 不漂移
- AI recommendation 回退和 low-confidence degrade 不漂移

重点回归：

- `tests/test_customer_pulse_inbox.py`
- `tests/test_customer_pulse_quality_gates.py`
- `tests/test_admin_customer_profile_console.py`
- `tests/test_api.py -k "customer_pulse"`

PR 5 目标是 followup internal split。

必须冻结：

- team board / my missions / mission detail
- mission action / item action / undo
- handoff / approval packet
- AI enhancement success / fallback / low-confidence degrade

重点回归：

- `tests/test_followup_orchestrator_skeleton.py`
- `tests/test_http_registration_contract.py`
- `tests/test_refactor_guardrails.py`

## 8. 建议新增测试清单

以下是当前最值得补的 6 条冻结测试：

1. `test_ai_assist_application_contract_delegates_customer_pulse_queries_to_legacy_delegate`
   - 文件：`tests/test_ai_assist_application_contract.py`
   - PR：1
2. `test_ai_assist_application_contract_delegates_followup_commands_to_legacy_delegate`
   - 文件：`tests/test_ai_assist_application_contract.py`
   - PR：1
3. `test_admin_console_home_uses_ai_assist_feature_gate_for_pulse_and_followup_visibility`
   - 文件：`tests/test_api.py` 或新增 admin shell contract test
   - PR：2/3
4. `test_admin_customer_profile_pulse_widget_stays_compatible_after_ai_assist_cutover`
   - 文件：`tests/test_admin_customer_profile_console.py`
   - PR：2
5. `test_followup_orchestrator_caller_cutover_preserves_team_board_and_item_execute_contract`
   - 文件：`tests/test_followup_orchestrator_skeleton.py`
   - PR：3
6. `test_customer_pulse_request_scoped_cross_tenant_denial_survives_application_cutover`
   - 文件：`tests/test_customer_pulse_inbox.py`
   - PR：2/4

## 9. 最小回归集建议

Wave 5 每个 PR 的最小回归集建议如下：

1. `tests/test_http_registration_contract.py`
2. `tests/test_refactor_guardrails.py`
3. `tests/test_admin_customer_profile_console.py`
4. `tests/test_customer_pulse_inbox.py`
5. `tests/test_customer_pulse_quality_gates.py`
6. `tests/test_followup_orchestrator_skeleton.py`
7. `tests/test_api.py -k "customer_pulse or followup_orchestrator"`

## 10. 结论

现有测试已经覆盖了 AI Assist 主线的大部分业务主路径，但还没有把“application contract + caller cutover + admin shell boundary”冻结成独立测试层。

因此建议顺序固定为：

1. PR 1 先补 application contract tests。
2. PR 2 再切 customer pulse caller。
3. PR 3 再切 followup caller。
4. PR 4 / PR 5 最后做内部 owner 拆分。
