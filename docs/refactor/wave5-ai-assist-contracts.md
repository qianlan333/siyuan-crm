# Wave 5 AI Assist Contracts

日期：2026-04-21

## 1. 目标

本文只定义 AI Assist 的正式 contract 草案，不改业务代码。

正式 contract 的目标：

- 让 customer pulse / followup orchestrator 有唯一 application owner
- 让 `http/admin_customer_pulse.py`、`http/admin_followup_orchestrator.py`、admin customer profile glue 不再直接依赖 `domains.customer_pulse/*` / `domains.followup_orchestrator/*`
- 让 pulse action / feedback / recompute / mission action / undo 变成显式 command
- 让 AI Assist 对 `customer read model` / `automation engine` / `platform foundation` 的边界变成显式依赖，而不是隐式 import

建议命名空间：

- `wecom_ability_service/application/ai_assist/queries.py`
- `wecom_ability_service/application/ai_assist/commands.py`
- `wecom_ability_service/application/ai_assist/dto.py`
- `wecom_ability_service/application/ai_assist/_legacy_delegate.py`

## 2. 合同总览

| Contract | 输入 DTO | 输出 DTO | 当前 legacy 入口 | 直接调用方 | 跨 context 读取 / 副作用 | 禁止继续绕过的旧入口 | 兼容策略 | 推荐切换 PR |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GetCustomerPulseFeatureGateQuery` | `GetCustomerPulseFeatureGateQueryDTO { access_context }` | `GetCustomerPulseFeatureGateResultDTO { enabled, feature_gate, permissions, template_access }` | `domains.customer_pulse.is_customer_pulse_inbox_enabled` + `customer_pulse_feature_gate_summary` + `customer_pulse_template_access_payload` | `http/admin_console.py`、`http/admin_customers.py`、`domains/admin_console/customer_profile_service.py` | 只读 access / feature policy；无写副作用 | `domains.customer_pulse.is_customer_pulse_inbox_enabled`、`domains.customer_pulse.access.customer_pulse_template_access_payload` | 先保留返回结构兼容，再把 page-visible glue 收回 query | 2 |
| `ListCustomerPulseInboxQuery` | `ListCustomerPulseInboxQueryDTO { filters, access_context, metric_source }` | `ListCustomerPulseInboxResultDTO { inbox, feature_gate }` | `domains.customer_pulse.build_customer_pulse_inbox_payload` | `http/admin_customer_pulse.py`、`domains/followup_orchestrator/service.py` | 读取 customer summary / recent messages / questionnaire rows / latest AI output；无直接写副作用 | `domains.customer_pulse.build_customer_pulse_inbox_payload` | 保持 inbox cards / filters / summary_cards / metrics_summary 结构不变 | 2 |
| `GetCustomerPulseStatsQuery` | `GetCustomerPulseStatsQueryDTO { days, access_context }` | `GetCustomerPulseStatsResultDTO { stats, feature_gate }` | `domains.customer_pulse.build_customer_pulse_ops_dashboard_payload` | `http/admin_customer_pulse.py` | 只读 metrics / security counters / rollout summary | `domains.customer_pulse.build_customer_pulse_ops_dashboard_payload` | 保持 stats API JSON key 不变 | 2 |
| `GetCustomerPulseDetailQuery` | `GetCustomerPulseDetailQueryDTO { external_userid, access_context }` | `GetCustomerPulseDetailResultDTO { external_userid, pulse, customer_pulse }` | 当前 `application.ai_assist.GetCustomerPulseDetailQuery` + `domains.customer_pulse.build_customer_pulse_customer_detail_payload` | `domains/admin_console/customer_profile_service.py`、未来 `http/admin_customers.py` | 读取 customer read model + pulse snapshot/card；必要时可触发一次 refresh | `domains.customer_pulse.build_customer_pulse_customer_detail_payload`、`customer_center.pulse_service.build_customer_pulse` | 保留现有 widget payload 和 `pulse` / `customer_pulse` 双结构 | 2 |
| `GetCustomerPulseCardQuery` | `GetCustomerPulseCardQueryDTO { card_id, access_context }` | `GetCustomerPulseCardResultDTO { card, latest_execution, activity_logs, feedback, permissions }` | `domains.customer_pulse.get_customer_pulse_card_payload` | `http/admin_customer_pulse.py` | 读取 snapshot / feedback / execution logs / activity logs | `domains.customer_pulse.get_customer_pulse_card_payload` | 保持 detail API card payload 不变 | 2 |
| `GetCustomerPulseCardEvidenceQuery` | `GetCustomerPulseCardEvidenceQueryDTO { card_id, access_context }` | `GetCustomerPulseCardEvidenceResultDTO { evidence, permissions, snapshot }` | `domains.customer_pulse.get_customer_pulse_card_evidence_payload` | `http/admin_customer_pulse.py` | 读取 signal events / evidence refs；无写副作用 | `domains.customer_pulse.get_customer_pulse_card_evidence_payload` | 保持 evidence API 返回结构和敏感信息 mask 语义不变 | 2 |
| `RefreshCustomerPulseCardsCommand` | `RefreshCustomerPulseCardsCommandDTO { external_userids?, limit, operator, access_context }` | `RefreshCustomerPulseCardsCommandResultDTO { processed, refreshed, skipped, feature_gate }` | `domains.customer_pulse.refresh_customer_pulse_cards` | `http/admin_customer_pulse.py` | 写 snapshot / cards / metric events | `domains.customer_pulse.refresh_customer_pulse_cards` | 保持 refresh API 和 action page 结果结构不变 | 2 |
| `EnqueueCustomerPulseRecomputeCommand` | `EnqueueCustomerPulseRecomputeCommandDTO { external_userids, operator, access_context }` | `EnqueueCustomerPulseRecomputeCommandResultDTO { queued, jobs, feature_gate }` | `domains.customer_pulse.enqueue_customer_pulse_recompute` | `http/admin_customer_pulse.py` internal API | 写 recompute jobs | `domains.customer_pulse.enqueue_customer_pulse_recompute` | 先 formalize internal job enqueue，再切 internal endpoints | 2 |
| `RunDueCustomerPulseSnapshotJobCommand` | `RunDueCustomerPulseSnapshotJobCommandDTO { limit, operator, access_context }` | `RunDueCustomerPulseSnapshotJobCommandResultDTO { queue_result, refresh_result, feature_gate }` | `domains.customer_pulse.run_due_customer_pulse_snapshot_job` | `http/admin_customer_pulse.py` internal API | 运行 recompute + refresh due jobs | `domains.customer_pulse.run_due_customer_pulse_snapshot_job`、`run_due_customer_pulse_recompute_jobs` | 保持 internal due-runner payload 不变 | 2 |
| `PreviewCustomerPulseCardActionCommand` | `PreviewCustomerPulseCardActionCommandDTO { card_id, action_type, action_payload, operator, access_context }` | `PreviewCustomerPulseCardActionResultDTO { preview, feature_gate }` | `domains.customer_pulse.preview_customer_pulse_card_action` | `http/admin_customer_pulse.py`、未来 followup item bridge | 读取 card / snapshot / permissions；无落库写 | `domains.customer_pulse.preview_customer_pulse_card_action` | 保持 preview JSON、guardrail hits、permission denial 语义不变 | 2 |
| `ExecuteCustomerPulseCardActionCommand` | `ExecuteCustomerPulseCardActionCommandDTO { card_id, action_type, action_payload, operator, admin_action_token?, access_context }` | `ExecuteCustomerPulseCardActionResultDTO { execution, card, activity, feature_gate }` | `domains.customer_pulse.execute_customer_pulse_card_action` | `http/admin_customer_pulse.py`、未来 followup item execute bridge | 会写 execution log / card state / task dispatch / tags / followup reminder | `domains.customer_pulse.execute_customer_pulse_card_action` | 保持 execute 结果结构和 undo window 语义不变 | 2 |
| `UndoCustomerPulseCardActionCommand` | `UndoCustomerPulseCardActionCommandDTO { execution_id, operator, access_context }` | `UndoCustomerPulseCardActionResultDTO { result, card, execution }` | `domains.customer_pulse.undo_customer_pulse_card_action_execution` | `http/admin_customer_pulse.py`、未来 followup item undo bridge | 写 execution rollback / activity log / state restore | `domains.customer_pulse.undo_customer_pulse_card_action_execution` | 保持 undo 语义和返回结构不变 | 2 |
| `SubmitCustomerPulseFeedbackCommand` | `SubmitCustomerPulseFeedbackCommandDTO { card_id, feedback_type, feedback_payload, operator, access_context }` | `SubmitCustomerPulseFeedbackCommandResultDTO { feedback, card, metrics }` | `domains.customer_pulse.submit_customer_pulse_feedback` | `http/admin_customer_pulse.py` | 写 feedback / update card / metric events | `domains.customer_pulse.submit_customer_pulse_feedback` | 保持 feedback API key 和 metrics summary 不变 | 2 |
| `GetFollowupOrchestratorFeatureGateQuery` | `GetFollowupOrchestratorFeatureGateQueryDTO { access_context }` | `GetFollowupOrchestratorFeatureGateResultDTO { enabled, feature_gate, permissions }` | `domains.followup_orchestrator.is_followup_orchestrator_enabled` + `followup_orchestrator_feature_gate_summary` | `http/admin_console.py`、`http/admin_customers.py`、`http/admin_followup_orchestrator.py` | 只读 access / feature policy；无写副作用 | `domains.followup_orchestrator.is_followup_orchestrator_enabled`、`domains.followup_orchestrator.followup_orchestrator_feature_gate_summary` | 保持页面入口可见性和 disabled page 语义不变 | 3 |
| `GetFollowupOrchestratorOverviewQuery` | `GetFollowupOrchestratorOverviewQueryDTO { filters, access_context }` | `GetFollowupOrchestratorOverviewResultDTO { orchestrator, feature_gate }` | `domains.followup_orchestrator.build_followup_orchestrator_overview_payload` | `http/admin_followup_orchestrator.py` | 读取 latest missions / unresolved counts / pulse-derived summary | `domains.followup_orchestrator.build_followup_orchestrator_overview_payload` | 保持 page/API overview payload 不变 | 3 |
| `GetFollowupOrchestratorCustomerQuery` | `GetFollowupOrchestratorCustomerQueryDTO { external_userid, access_context }` | `GetFollowupOrchestratorCustomerResultDTO { customer, missions, feature_gate }` | `domains.followup_orchestrator.build_followup_orchestrator_customer_payload` | `http/admin_followup_orchestrator.py` | 读 customer-level missions / pulse handoff snapshot | `domains.followup_orchestrator.build_followup_orchestrator_customer_payload` | 保持 customer payload 结构不变 | 3 |
| `ListFollowupMyMissionsQuery` | `ListFollowupMyMissionsQueryDTO { actor_userid, filters, access_context }` | `ListFollowupMyMissionsResultDTO { my_missions, feature_gate }` | `domains.followup_orchestrator.build_followup_orchestrator_my_missions_payload` | `http/admin_followup_orchestrator.py` internal API | 只读 actor mission list | `domains.followup_orchestrator.build_followup_orchestrator_my_missions_payload` | 保持 internal my-missions payload 不变 | 3 |
| `GetFollowupTeamBoardQuery` | `GetFollowupTeamBoardQueryDTO { filters, access_context }` | `GetFollowupTeamBoardResultDTO { team_board, feature_gate }` | `domains.followup_orchestrator.build_followup_orchestrator_team_board_payload` | `http/admin_followup_orchestrator.py` internal API | 读 team workload / candidates / AI enhancement decorate | `domains.followup_orchestrator.build_followup_orchestrator_team_board_payload` | 保持 internal team-board payload 不变 | 3 |
| `GetFollowupMissionDetailQuery` | `GetFollowupMissionDetailQueryDTO { mission_key, access_context }` | `GetFollowupMissionDetailResultDTO { mission, feature_gate }` | `domains.followup_orchestrator.get_followup_orchestrator_mission_detail_payload` | `http/admin_followup_orchestrator.py` | 读 mission items / decisions / latest execution / AI summary | `domains.followup_orchestrator.get_followup_orchestrator_mission_detail_payload` | 保持 mission detail 返回结构不变 | 3 |
| `SyncFollowupMissionsCommand` | `SyncFollowupMissionsCommandDTO { scope, actor_userid?, operator, access_context }` | `SyncFollowupMissionsCommandResultDTO { synced, created, updated, stale, feature_gate }` | `domains.followup_orchestrator.sync_followup_orchestrator_missions` | `http/admin_followup_orchestrator.py` internal sync API | 写 mission / item / decision；读取 customer pulse inbox cards 作为输入源 | `domains.followup_orchestrator.sync_followup_orchestrator_missions` | 保持 sync payload 和 scope 语义不变 | 3 |
| `ApplyFollowupMissionActionCommand` | `ApplyFollowupMissionActionCommandDTO { mission_key, action_type, actor_userid?, operator, access_context }` | `ApplyFollowupMissionActionResultDTO { result, mission, feature_gate }` | `domains.followup_orchestrator.apply_followup_orchestrator_mission_action` | `http/admin_followup_orchestrator.py` | 写 mission / item status / assignment decision / activity | `domains.followup_orchestrator.apply_followup_orchestrator_mission_action` | 保持 claim / accept / complete / request_manager_approval 主语义不变 | 3 |
| `PreviewFollowupMissionItemActionCommand` | `PreviewFollowupMissionItemActionCommandDTO { mission_key, mission_item_key, action_type?, action_payload, actor_userid?, operator, access_context }` | `PreviewFollowupMissionItemActionResultDTO { preview, mission_item, feature_gate }` | `domains.followup_orchestrator.preview_followup_orchestrator_mission_item_action` | `http/admin_followup_orchestrator.py` | 读 mission item 对应 pulse card action preview | `domains.followup_orchestrator.preview_followup_orchestrator_mission_item_action` | 保持 preview 结果结构不变 | 3 |
| `ExecuteFollowupMissionItemActionCommand` | `ExecuteFollowupMissionItemActionCommandDTO { mission_key, mission_item_key, action_type?, action_payload, actor_userid?, operator, admin_action_token?, access_context }` | `ExecuteFollowupMissionItemActionResultDTO { result, mission_item, pulse_execution?, feature_gate }` | `domains.followup_orchestrator.execute_followup_orchestrator_mission_item_action` | `http/admin_followup_orchestrator.py` | 通过 pulse action 写执行结果、orchestrator log、handoff artifacts | `domains.followup_orchestrator.execute_followup_orchestrator_mission_item_action` | 保持 mission item execute / pulse execution 结果结构不变 | 3 |
| `UndoFollowupMissionItemActionCommand` | `UndoFollowupMissionItemActionCommandDTO { mission_key, mission_item_key, execution_id?, actor_userid?, operator, access_context }` | `UndoFollowupMissionItemActionResultDTO { result, mission_item, execution, feature_gate }` | `domains.followup_orchestrator.undo_followup_orchestrator_mission_item_action` | `http/admin_followup_orchestrator.py` | 通过 pulse undo 写回滚结果与 orchestrator log | `domains.followup_orchestrator.undo_followup_orchestrator_mission_item_action` | 保持 undo 结果和 restored state 语义不变 | 3 |

## 3. 跨 Context 边界口径

### 3.1 Customer Read Model

AI Assist 的 read contract 可以依赖：

- `GetCustomerDetailQuery`
- `GetCustomerTimelineQuery`
- `GetCustomerChatContextQuery`
- `ListRecentMessagesQuery`

但这些依赖只能发生在 application / domain delegate 层，不能回流到 controller。

### 3.2 Automation Engine

以下内容不再允许由 AI Assist caller 或 domain 直接 owner：

- agent run / output repo 写入
- message dispatch / outbound retry primitive
- workflow runtime / member state truth

这些未来要通过 `application/automation_engine/*` 或 automation runtime adapter 提供稳定 port。

### 3.3 Platform Foundation

以下内容继续留在 transport / foundation：

- internal token 校验
- admin action token 校验
- request / header / session 解析
- audit actor 的 transport glue

AI Assist contract 只接受结构化 `access_context` / `operator` / `request_meta`，不直接 import `flask.request` / `session`。

## 4. 禁止绕过的旧入口

从 Wave 5 开始，以下入口应视为 legacy bypass：

- `domains.customer_pulse.build_customer_pulse_inbox_payload`
- `domains.customer_pulse.build_customer_pulse_customer_detail_payload`
- `domains.customer_pulse.get_customer_pulse_card_payload`
- `domains.customer_pulse.get_customer_pulse_card_evidence_payload`
- `domains.customer_pulse.refresh_customer_pulse_cards`
- `domains.customer_pulse.enqueue_customer_pulse_recompute`
- `domains.customer_pulse.run_due_customer_pulse_snapshot_job`
- `domains.customer_pulse.preview_customer_pulse_card_action`
- `domains.customer_pulse.execute_customer_pulse_card_action`
- `domains.customer_pulse.undo_customer_pulse_card_action_execution`
- `domains.customer_pulse.submit_customer_pulse_feedback`
- `domains.followup_orchestrator.build_followup_orchestrator_overview_payload`
- `domains.followup_orchestrator.build_followup_orchestrator_customer_payload`
- `domains.followup_orchestrator.build_followup_orchestrator_my_missions_payload`
- `domains.followup_orchestrator.build_followup_orchestrator_team_board_payload`
- `domains.followup_orchestrator.get_followup_orchestrator_mission_detail_payload`
- `domains.followup_orchestrator.sync_followup_orchestrator_missions`
- `domains.followup_orchestrator.apply_followup_orchestrator_mission_action`
- `domains.followup_orchestrator.preview_followup_orchestrator_mission_item_action`
- `domains.followup_orchestrator.execute_followup_orchestrator_mission_item_action`
- `domains.followup_orchestrator.undo_followup_orchestrator_mission_item_action`

历史兼容 wrapper 可以暂时保留，但新的 controller / admin caller / widget glue 不应继续直接依赖这些入口。

## 5. 推荐切换顺序

1. `GetCustomerPulseFeatureGateQuery`
2. `GetCustomerPulseDetailQuery`
3. `ListCustomerPulseInboxQuery`
4. `GetCustomerPulseCardQuery`
5. `GetCustomerPulseCardEvidenceQuery`
6. `GetCustomerPulseStatsQuery`
7. `RefreshCustomerPulseCardsCommand`
8. `EnqueueCustomerPulseRecomputeCommand`
9. `RunDueCustomerPulseSnapshotJobCommand`
10. `PreviewCustomerPulseCardActionCommand`
11. `ExecuteCustomerPulseCardActionCommand`
12. `UndoCustomerPulseCardActionCommand`
13. `SubmitCustomerPulseFeedbackCommand`
14. `GetFollowupOrchestratorFeatureGateQuery`
15. `GetFollowupOrchestratorOverviewQuery`
16. `GetFollowupOrchestratorCustomerQuery`
17. `ListFollowupMyMissionsQuery`
18. `GetFollowupTeamBoardQuery`
19. `GetFollowupMissionDetailQuery`
20. `SyncFollowupMissionsCommand`
21. `ApplyFollowupMissionActionCommand`
22. `PreviewFollowupMissionItemActionCommand`
23. `ExecuteFollowupMissionItemActionCommand`
24. `UndoFollowupMissionItemActionCommand`

这个顺序的含义：

- 先稳住 pulse widget / feature gate / inbox 这些最靠近 admin shell 的读面
- 再切 pulse action / feedback / due runner
- 最后切 followup orchestrator，因为它当前直接依赖 pulse cards 作为 mission source

## 6. 结论

Wave 5 不应再新增“controller -> domains.customer_pulse/service.py”或“controller -> domains.followup_orchestrator/service.py”这种链路。

后续所有小 PR 都应该围绕本文定义的 contract 切换 caller，而不是在 legacy domain service 中继续扩展新的 admin glue。
