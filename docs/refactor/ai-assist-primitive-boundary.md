# AI Assist Primitive Boundary

日期：2026-04-22

## 目标

明确 customer pulse 与 followup orchestrator 当前哪些 helper / primitive 只允许留在 AI Assist 内部 owner 使用，不应再被 caller 直接依赖。

## Formal Owner 边界

从现在开始，AI Assist 的外层调用方如果要读取或执行 pulse / followup 行为，只允许通过：

- `wecom_ability_service/application/ai_assist/queries.py`
- `wecom_ability_service/application/ai_assist/commands.py`

不允许继续新增：

- controller 直接 import `domains.customer_pulse.service`
- controller 直接 import `domains.followup_orchestrator.service`
- admin console glue 直接 import AI Assist 新拆出的 internal owner 文件
- 其他 context 直接把 AI Assist primitive 当作稳定集成入口

## Customer Pulse

### 视为 internal primitive 的 helper / owner

- `wecom_ability_service/domains/customer_pulse/customer_pulse_signal_service.py`
  - `_load_context`
  - `_build_rule_signals`
- `wecom_ability_service/domains/customer_pulse/customer_pulse_snapshot_service.py`
  - `_persist_signals`
  - `_build_scoring`
  - `_build_action_candidates`
  - `_merge_ai_recommendation_into_candidates`
  - `_materialize_customer_pulse`
- `wecom_ability_service/domains/customer_pulse/service.py`
  - `_present_card`
  - `_present_signal`
  - `_present_snapshot`
  - `_resolve_card_action_candidate`
  - `_customer_pulse_evidence_source_allowed`
  - 以及其他未公开的 `_internal_*` / `_build_*` / `_resolve_*` helper

### 允许调用范围

- `wecom_ability_service/application/ai_assist/*`
- `wecom_ability_service/domains/customer_pulse/*` 内部 owner 文件

### 禁止调用范围

- `wecom_ability_service/http/*`
- `wecom_ability_service/domains/admin_console/*`
- 其他 context caller

## Followup Orchestrator

### 视为 internal primitive 的 helper / owner

- `wecom_ability_service/domains/followup_orchestrator/mission_sync_service.py`
  - `_collect_evidence_refs`
  - `_build_owner_workload`
  - `_team_candidate_owners`
  - `_card_signals`
  - `_batch_group_key`
- `wecom_ability_service/domains/followup_orchestrator/mission_assignment_service.py`
  - `_determine_assignment`
  - `_escalation_reason`
  - `_mission_type_for_card`
  - `_mission_key_for_card`
  - `_mission_payload`
- `wecom_ability_service/domains/followup_orchestrator/mission_board_service.py`
  - `_current_item_execution_state`
  - `_decorate_mission`
  - `_decorate_item`
- `wecom_ability_service/domains/followup_orchestrator/mission_action_service.py`
  - `_resolved_mission_item_context`
  - `_execute_followup_orchestrator_item_action`
  - `_with_item_runtime_payload`
  - `_build_handoff_packet`
  - `_record_orchestrator_activity`
- `wecom_ability_service/domains/followup_orchestrator/ai_enhancement.py`
  - provider/runtime 内部 helper
- `wecom_ability_service/domains/followup_orchestrator/service.py`
  - 仍保留但仅作 compatibility delegate seam 的 `_load_followup_internal_delegate(...)` 和同名 facade helper

### 允许调用范围

- `wecom_ability_service/application/ai_assist/*`
- `wecom_ability_service/domains/followup_orchestrator/*` 内部 owner 文件

### 禁止调用范围

- `wecom_ability_service/http/*`
- `wecom_ability_service/domains/admin_console/*`
- 其他 context caller

## Compatibility Surface 说明

以下 surface 可以继续存在，但只应作为 compatibility facade，不应成为新默认入口：

- `wecom_ability_service/domains/customer_pulse/service.py`
- `wecom_ability_service/domains/customer_pulse/__init__.py`
- `wecom_ability_service/domains/followup_orchestrator/service.py`
- `wecom_ability_service/domains/followup_orchestrator/__init__.py`

这类 surface 可以服务于同 context 内部兼容或渐进式重构，但不能让新的 caller 再绕开 `application/ai_assist/*`。

## 结论

这些 primitive boundary 的目的不是隐藏实现，而是防止 Wave 5 刚完成的 formal owner 与 internal owner 再被 caller 旁路。
