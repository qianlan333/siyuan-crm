# Wave 5 AI Assist Callers Map

日期：2026-04-21

## 1. 目的

本文件只回答 3 个问题：

1. 现在哪些 caller 还在直接使用 AI Assist legacy 入口。
2. 每个 caller 未来应该切到哪个正式 `application/ai_assist/*` contract。
3. 哪些跨 context 副作用本轮必须显式保留，不应悄悄并回 caller 或 controller。

## 2. 调用方总表

| 调用方 | 当前 direct import / direct call | 当前职责 | 目标正式入口 | 暂时保留在 caller 侧的跨 context glue | 推荐切换 PR |
| --- | --- | --- | --- | --- | --- |
| `wecom_ability_service/application/ai_assist/queries.py` | 直接 import `customer_center.pulse_service`、`domains.customer_pulse.*`、`domains.customer_pulse.access.*` | 当前唯一 formal query，负责 pulse detail widget | `_legacy_delegate` + `GetCustomerPulseDetailQuery` 稳定 seam | 无；这是 application owner 本身，不应再反向 import domain internals | PR 1 |
| `wecom_ability_service/http/admin_customer_pulse.py` | `build_customer_pulse_inbox_payload`、`build_customer_pulse_customer_detail_payload`、`build_customer_pulse_ops_dashboard_payload`、`refresh_customer_pulse_cards`、`preview_customer_pulse_card_action`、`execute_customer_pulse_card_action`、`undo_customer_pulse_card_action_execution`、`submit_customer_pulse_feedback`、`run_due_customer_pulse_snapshot_job` 等 direct domain import | customer pulse page / admin API / internal API / action / feedback / metrics / run-due | `GetCustomerPulseFeatureGateQuery`、`ListCustomerPulseInboxQuery`、`GetCustomerPulseStatsQuery`、`GetCustomerPulseCardQuery`、`GetCustomerPulseCardEvidenceQuery`、`RefreshCustomerPulseCardsCommand`、`EnqueueCustomerPulseRecomputeCommand`、`RunDueCustomerPulseSnapshotJobCommand`、`PreviewCustomerPulseCardActionCommand`、`ExecuteCustomerPulseCardActionCommand`、`UndoCustomerPulseCardActionCommand`、`SubmitCustomerPulseFeedbackCommand` | admin action token、internal token、request parse、response build、audit / security metric transport glue 继续留在 controller | PR 2 |
| `wecom_ability_service/domains/admin_console/customer_profile_service.py` | 已调 `GetCustomerPulseDetailQuery`，但仍 direct import `domains.customer_pulse.is_customer_pulse_inbox_enabled` 和 `domains.customer_pulse.access.current_customer_pulse_request_access_context` | admin customer profile 中 pulse widget view-model | `GetCustomerPulseFeatureGateQuery`、`GetCustomerPulseDetailQuery` | customer profile 页面自身的 section 组装和 URL 暴露仍留在 admin console glue | PR 2 |
| `wecom_ability_service/http/admin_console.py` | direct import `domains.customer_pulse.is_customer_pulse_inbox_enabled`、`domains.followup_orchestrator.is_followup_orchestrator_enabled` 和 pulse access helper | admin home quick link / page visible 控制 | `GetCustomerPulseFeatureGateQuery`、`GetFollowupOrchestratorFeatureGateQuery` | 只保留模板渲染和 quick link 组装 | PR 2/3 |
| `wecom_ability_service/http/admin_customers.py` | direct import `domains.followup_orchestrator.is_followup_orchestrator_enabled` 和 pulse access helper | customer profile page 模板里暴露 pulse / followup API URL 与 access payload | `GetCustomerPulseFeatureGateQuery`、`GetFollowupOrchestratorFeatureGateQuery`、`GetCustomerPulseDetailQuery` | 页面 URL 暴露和模板渲染继续留在 controller | PR 2/3 |
| `wecom_ability_service/http/admin_followup_orchestrator.py` | `build_followup_orchestrator_overview_payload`、`build_followup_orchestrator_customer_payload`、`build_followup_orchestrator_my_missions_payload`、`build_followup_orchestrator_team_board_payload`、`get_followup_orchestrator_mission_detail_payload`、`sync_followup_orchestrator_missions`、`apply_followup_orchestrator_mission_action`、`preview_followup_orchestrator_mission_item_action`、`execute_followup_orchestrator_mission_item_action`、`undo_followup_orchestrator_mission_item_action` | followup page / admin API / internal API / mission action | `GetFollowupOrchestratorFeatureGateQuery`、`GetFollowupOrchestratorOverviewQuery`、`GetFollowupOrchestratorCustomerQuery`、`ListFollowupMyMissionsQuery`、`GetFollowupTeamBoardQuery`、`GetFollowupMissionDetailQuery`、`SyncFollowupMissionsCommand`、`ApplyFollowupMissionActionCommand`、`PreviewFollowupMissionItemActionCommand`、`ExecuteFollowupMissionItemActionCommand`、`UndoFollowupMissionItemActionCommand` | admin action token、internal token、request parse、response build、audit transport glue 继续留在 controller | PR 3 |
| `wecom_ability_service/domains/followup_orchestrator/service.py` | direct import `domains.customer_pulse.build_customer_pulse_inbox_payload`、`get_customer_pulse_card_payload`、`preview_customer_pulse_card_action`、`execute_customer_pulse_card_action`、`undo_customer_pulse_card_action_execution` | mission source / mission item action 实现依赖 pulse | 未来内部 bridge：followup 只消费 `application/ai_assist/*` 提供的 pulse read/action seam，或内部 ai_assist delegate adapter | 作为 domain 内部实现，本轮可暂时保留，但必须在后续 internal split 里改掉 | PR 4/5 |
| `wecom_ability_service/domains/customer_pulse/ai_recommendation.py` | direct import `domains.automation_conversion.repo` 和 LLM provider | pulse AI recommendation、agent run/output log、PII guardrail | 未来通过 `application/automation_engine/*` 或 runtime adapter 读取 / 写入 AI run | 当前 AI generation / sanitization 逻辑先保留在 pulse 内部 owner，不在 caller 层处理 | PR 4 |
| `wecom_ability_service/domains/followup_orchestrator/ai_enhancement.py` | direct import `domains.automation_conversion.repo`、`domains.automation_conversion.agents.llm_client`、`customer_pulse.ai_recommendation` helper | followup AI enhancement success / fallback / low-confidence degrade | 未来通过 `application/automation_engine/*` 或 runtime adapter 调 agent / log output；guardrail helper 仍可复用 ai_assist 内部模块 | 作为 followup 内部 owner，本轮只盘点不切 caller | PR 5 |

## 3. 逐调用方说明

### 3.1 `application/ai_assist/queries.py`

当前问题：

- 现在只有 `GetCustomerPulseDetailQuery`
- 但它不是稳定 delegate seam，而是直接 import：
  - `customer_center.pulse_service.build_customer_pulse`
  - `domains.customer_pulse.build_customer_pulse_customer_detail_payload`
  - `domains.customer_pulse.is_customer_pulse_inbox_enabled`
  - `domains.customer_pulse.refresh_customer_pulse_cards`
  - `domains.customer_pulse.access.*`

切换口径：

- PR 1 先补 `dto.py` / `queries.py` / `commands.py` / `_legacy_delegate.py`
- application 层 public query / command 统一经 `_legacy_delegate`
- application 层不再直接 import `domains.customer_pulse.*` 或 `domains.followup_orchestrator.*`

### 3.2 `http/admin_customer_pulse.py`

当前 AI Assist 相关入口：

- page / HTML
- inbox API
- stats API
- card detail / evidence API
- refresh / recompute / run-due
- preview / execute / undo
- feedback

切换口径：

- controller 只做 parse request -> 组 DTO -> 调 `application/ai_assist/*` -> build response
- feature gate / action token / internal token 仍留在 controller
- business owner 迁到 application，不再 direct import customer pulse domain

### 3.3 `domains/admin_console/customer_profile_service.py`

当前 AI Assist 相关职责：

- profile API 中返回 pulse widget payload
- 把 `customer_pulse` detail 转成旧 `pulse` widget payload
- 判断当前 access context 下是否展示 pulse

切换口径：

- customer profile 仍保留 view-model 组装
- 但它只消费：
  - `GetCustomerPulseFeatureGateQuery`
  - `GetCustomerPulseDetailQuery`
- 不能继续自己摸 pulse feature gate / access helper

### 3.4 `http/admin_followup_orchestrator.py`

当前职责：

- team board / my missions / mission detail
- mission action
- item preview / execute / undo
- sync
- page visible / feature disabled page

切换口径：

- controller 只做 transport glue
- mission / action owner 统一进入 `application/ai_assist/*`
- `FOLLOWUP_ORCHESTRATOR_MISSION_ACTIONS` 这类稳定枚举可以继续作为 domain constant 保留，但 caller 不应再直接调 service

### 3.5 `http/admin_console.py` 与 `http/admin_customers.py`

这两个文件不是 AI Assist 的主业务 caller，但它们目前承担：

- quick link 是否可见
- customer profile 模板里 followup / pulse URL 暴露
- feature gate / access payload 决策

切换口径：

- `admin_console.py` 只消费 feature gate query
- `admin_customers.py` 只消费 feature gate query 和 profile glue 返回的结果
- 不再直连 pulse / followup domain helper

### 3.6 `domains/followup_orchestrator/service.py`

这是 Wave 5 中最关键的内部 legacy 直连点。

当前 followup service 会直接：

- 从 `build_customer_pulse_inbox_payload()` 生成 mission source
- 通过 `preview_customer_pulse_card_action()` / `execute_customer_pulse_card_action()` / `undo_customer_pulse_card_action_execution()` 复用 pulse action

结论：

- Wave 5 caller cutover 不先动这里
- 但在 PR 4 / PR 5 的 internal split 中，必须把这条 direct domain 依赖改成 AI Assist 内部 bridge 或 application delegate seam

## 4. 当前最重要的 Legacy 旁路

从本调用方地图开始，禁止新增以下旁路：

1. `http/admin_customer_pulse.py` 新增 direct import `domains.customer_pulse.service`
2. `http/admin_followup_orchestrator.py` 新增 direct import `domains.followup_orchestrator.service`
3. `domains/admin_console/customer_profile_service.py` 新增对 pulse / followup domain service 的 direct import
4. `application/ai_assist/*` 新增 direct import `http/*`
5. 新的 admin/customer/profile caller 继续绕过 application contract，直接调 pulse / followup domain 函数

## 5. 切换顺序结论

推荐顺序固定为：

1. PR 1：先把 `application/ai_assist/*` 补成 formal owner。
2. PR 2：切 `admin_customer_pulse.py` + admin customer profile pulse boundary。
3. PR 3：切 `admin_followup_orchestrator.py` + admin shell followup visibility boundary。
4. PR 4：再处理 `domains/customer_pulse/*` 内部 owner。
5. PR 5：最后处理 `domains/followup_orchestrator/*` 内部 owner 和 AI enhancement 边界。

原因：

- pulse widget / inbox 是 AI Assist 最靠近 admin shell 的读面，先切可以把 customer profile 边界稳住
- followup 当前直接依赖 pulse cards 作为输入源，必须在 pulse formal owner 已稳定后再切

## 6. 结论

Wave 5 的主线不是回到 `services.py` 做 shim，而是把 controller / admin glue / domain 间的 direct dependency 改成：

- caller -> `application/ai_assist/*`
- `application/ai_assist/*` -> `_legacy_delegate`
- internal split 再逐步缩小 pulse / followup domain owner
