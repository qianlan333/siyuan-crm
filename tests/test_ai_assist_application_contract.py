from __future__ import annotations

import ast
from pathlib import Path

from wecom_ability_service.application.ai_assist import (
    ApplyFollowupMissionActionCommand,
    ApplyFollowupMissionActionCommandDTO,
    AssignFollowupMissionCommand,
    AssignFollowupMissionCommandDTO,
    CustomerPulseCardEvidenceQueryDTO,
    CustomerPulseCardQueryDTO,
    CustomerPulseDetailQueryDTO,
    CustomerPulseFeatureGateQueryDTO,
    CustomerPulseInboxQueryDTO,
    CustomerPulseMetricsQueryDTO,
    CustomerPulseStatsQueryDTO,
    EnqueueCustomerPulseRecomputeCommand,
    EnqueueCustomerPulseRecomputeCommandDTO,
    ExecuteCustomerActionCommand,
    ExecuteCustomerActionCommandDTO,
    ExecuteCustomerPulseCardActionCommand,
    ExecuteCustomerPulseCardActionCommandDTO,
    ExecuteFollowupMissionItemActionCommand,
    ExecuteFollowupMissionItemActionCommandDTO,
    FollowupCandidatesQueryDTO,
    FollowupCustomerQueryDTO,
    FollowupFeatureGateQueryDTO,
    FollowupMissionBoardQueryDTO,
    FollowupMissionDetailQueryDTO,
    FollowupMyMissionsQueryDTO,
    FollowupOverviewQueryDTO,
    FollowupTeamBoardQueryDTO,
    GetCustomerPulseInboxQuery,
    GetCustomerPulseMetricsQuery,
    GetCustomerPulseCardEvidenceQuery,
    GetCustomerPulseCardQuery,
    GetCustomerPulseDetailQuery,
    GetCustomerPulseFeatureGateQuery,
    GetCustomerPulseStatsQuery,
    GetFollowupMissionBoardQuery,
    GetFollowupMissionDetailQuery,
    GetFollowupOrchestratorCustomerQuery,
    GetFollowupOrchestratorFeatureGateQuery,
    GetFollowupOrchestratorOverviewQuery,
    GetFollowupTeamBoardQuery,
    ListCustomerPulseInboxQuery,
    ListFollowupCandidatesQuery,
    ListFollowupMyMissionsQuery,
    PreviewCustomerActionCommand,
    PreviewCustomerActionCommandDTO,
    PreviewCustomerPulseCardActionCommand,
    PreviewCustomerPulseCardActionCommandDTO,
    PreviewFollowupMissionItemActionCommand,
    PreviewFollowupMissionItemActionCommandDTO,
    RefreshCustomerPulseCardsCommand,
    RefreshCustomerPulseCardsCommandDTO,
    RunDueCustomerPulseSnapshotJobCommand,
    RunDueCustomerPulseSnapshotJobCommandDTO,
    SubmitCustomerPulseFeedbackCommand,
    SubmitCustomerPulseFeedbackCommandDTO,
    SyncFollowupMissionsCommand,
    SyncFollowupMissionsCommandDTO,
    UndoCustomerActionCommand,
    UndoCustomerActionCommandDTO,
    UndoCustomerPulseCardActionCommand,
    UndoCustomerPulseCardActionCommandDTO,
    UndoFollowupMissionItemActionCommand,
    UndoFollowupMissionItemActionCommandDTO,
)
from wecom_ability_service.application.ai_assist import commands as ai_assist_commands
from wecom_ability_service.application.ai_assist import queries as ai_assist_queries


def test_ai_assist_application_api_is_importable():
    assert GetCustomerPulseFeatureGateQuery
    assert GetCustomerPulseInboxQuery
    assert ListCustomerPulseInboxQuery
    assert GetCustomerPulseMetricsQuery
    assert GetCustomerPulseStatsQuery
    assert GetCustomerPulseDetailQuery
    assert GetCustomerPulseCardQuery
    assert GetCustomerPulseCardEvidenceQuery
    assert RefreshCustomerPulseCardsCommand
    assert EnqueueCustomerPulseRecomputeCommand
    assert RunDueCustomerPulseSnapshotJobCommand
    assert PreviewCustomerActionCommand
    assert PreviewCustomerPulseCardActionCommand
    assert ExecuteCustomerActionCommand
    assert ExecuteCustomerPulseCardActionCommand
    assert UndoCustomerActionCommand
    assert UndoCustomerPulseCardActionCommand
    assert SubmitCustomerPulseFeedbackCommand
    assert GetFollowupOrchestratorFeatureGateQuery
    assert GetFollowupOrchestratorOverviewQuery
    assert ListFollowupCandidatesQuery
    assert GetFollowupOrchestratorCustomerQuery
    assert ListFollowupMyMissionsQuery
    assert GetFollowupMissionBoardQuery
    assert GetFollowupTeamBoardQuery
    assert GetFollowupMissionDetailQuery
    assert SyncFollowupMissionsCommand
    assert AssignFollowupMissionCommand
    assert ApplyFollowupMissionActionCommand
    assert PreviewFollowupMissionItemActionCommand
    assert ExecuteFollowupMissionItemActionCommand
    assert UndoFollowupMissionItemActionCommand


def test_ai_assist_application_public_modules_delegate_via_legacy_delegate_only():
    root = Path(__file__).resolve().parents[1]
    for relative_path in (
        "wecom_ability_service/application/ai_assist/queries.py",
        "wecom_ability_service/application/ai_assist/commands.py",
    ):
        source = (root / relative_path).read_text(encoding="utf-8")
        tree = ast.parse(source, filename=relative_path)
        assert "from . import _legacy_delegate" in source
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = ("." * node.level + (node.module or "")).lstrip(".")
                assert module != "http", f"{relative_path} must not import http modules"
                assert module != "domains.customer_pulse", (
                    f"{relative_path} must delegate through _legacy_delegate instead of importing domains.customer_pulse"
                )
                assert module != "domains.followup_orchestrator", (
                    f"{relative_path} must delegate through _legacy_delegate instead of importing domains.followup_orchestrator"
                )


def test_ai_assist_application_skeleton_delegates_to_legacy_module(monkeypatch):
    calls: dict[str, object] = {}

    def _record(name: str, result):
        def _inner(dto=None):
            calls[name] = dto
            return result

        return _inner

    monkeypatch.setattr(
        "wecom_ability_service.application.ai_assist._legacy_delegate.get_customer_pulse_feature_gate_legacy",
        _record("get_customer_pulse_feature_gate", {"enabled": True}),
    )
    monkeypatch.setattr(
        "wecom_ability_service.application.ai_assist._legacy_delegate.list_customer_pulse_inbox_legacy",
        _record("list_customer_pulse_inbox", {"inbox": {}}),
    )
    monkeypatch.setattr(
        "wecom_ability_service.application.ai_assist._legacy_delegate.get_customer_pulse_stats_legacy",
        _record("get_customer_pulse_stats", {"stats": {}}),
    )
    monkeypatch.setattr(
        "wecom_ability_service.application.ai_assist._legacy_delegate.get_customer_pulse_detail_legacy",
        _record("get_customer_pulse_detail", {"customer_pulse": {}}),
    )
    monkeypatch.setattr(
        "wecom_ability_service.application.ai_assist._legacy_delegate.get_customer_pulse_card_legacy",
        _record("get_customer_pulse_card", {"card": {}}),
    )
    monkeypatch.setattr(
        "wecom_ability_service.application.ai_assist._legacy_delegate.get_customer_pulse_card_evidence_legacy",
        _record("get_customer_pulse_card_evidence", {"evidence": []}),
    )
    monkeypatch.setattr(
        "wecom_ability_service.application.ai_assist._legacy_delegate.refresh_customer_pulse_cards_legacy",
        _record("refresh_customer_pulse_cards", {"processed": 1}),
    )
    monkeypatch.setattr(
        "wecom_ability_service.application.ai_assist._legacy_delegate.enqueue_customer_pulse_recompute_legacy",
        _record("enqueue_customer_pulse_recompute", {"queued": 1}),
    )
    monkeypatch.setattr(
        "wecom_ability_service.application.ai_assist._legacy_delegate.run_due_customer_pulse_snapshot_job_legacy",
        _record("run_due_customer_pulse_snapshot_job", {"done": True}),
    )
    monkeypatch.setattr(
        "wecom_ability_service.application.ai_assist._legacy_delegate.preview_customer_pulse_card_action_legacy",
        _record("preview_customer_pulse_card_action", {"preview": {}}),
    )
    monkeypatch.setattr(
        "wecom_ability_service.application.ai_assist._legacy_delegate.execute_customer_pulse_card_action_legacy",
        _record("execute_customer_pulse_card_action", {"execution": {}}),
    )
    monkeypatch.setattr(
        "wecom_ability_service.application.ai_assist._legacy_delegate.undo_customer_pulse_card_action_legacy",
        _record("undo_customer_pulse_card_action", {"result": {}}),
    )
    monkeypatch.setattr(
        "wecom_ability_service.application.ai_assist._legacy_delegate.submit_customer_pulse_feedback_legacy",
        _record("submit_customer_pulse_feedback", {"feedback": {}}),
    )
    monkeypatch.setattr(
        "wecom_ability_service.application.ai_assist._legacy_delegate.get_followup_feature_gate_legacy",
        _record("get_followup_feature_gate", {"enabled": True}),
    )
    monkeypatch.setattr(
        "wecom_ability_service.application.ai_assist._legacy_delegate.get_followup_overview_legacy",
        _record("get_followup_overview", {"orchestrator": {}}),
    )
    monkeypatch.setattr(
        "wecom_ability_service.application.ai_assist._legacy_delegate.get_followup_customer_legacy",
        _record("get_followup_customer", {"customer": {}}),
    )
    monkeypatch.setattr(
        "wecom_ability_service.application.ai_assist._legacy_delegate.list_followup_my_missions_legacy",
        _record("list_followup_my_missions", {"my_missions": []}),
    )
    monkeypatch.setattr(
        "wecom_ability_service.application.ai_assist._legacy_delegate.get_followup_team_board_legacy",
        _record("get_followup_team_board", {"team_board": {}}),
    )
    monkeypatch.setattr(
        "wecom_ability_service.application.ai_assist._legacy_delegate.get_followup_mission_detail_legacy",
        _record("get_followup_mission_detail", {"mission": {}}),
    )
    monkeypatch.setattr(
        "wecom_ability_service.application.ai_assist._legacy_delegate.sync_followup_missions_legacy",
        _record("sync_followup_missions", {"synced": True}),
    )
    monkeypatch.setattr(
        "wecom_ability_service.application.ai_assist._legacy_delegate.apply_followup_mission_action_legacy",
        _record("apply_followup_mission_action", {"result": {}}),
    )
    monkeypatch.setattr(
        "wecom_ability_service.application.ai_assist._legacy_delegate.preview_followup_mission_item_action_legacy",
        _record("preview_followup_mission_item_action", {"preview": {}}),
    )
    monkeypatch.setattr(
        "wecom_ability_service.application.ai_assist._legacy_delegate.execute_followup_mission_item_action_legacy",
        _record("execute_followup_mission_item_action", {"result": {}}),
    )
    monkeypatch.setattr(
        "wecom_ability_service.application.ai_assist._legacy_delegate.undo_followup_mission_item_action_legacy",
        _record("undo_followup_mission_item_action", {"result": {}}),
    )

    assert GetCustomerPulseFeatureGateQuery()(CustomerPulseFeatureGateQueryDTO()) == {"enabled": True}
    assert GetCustomerPulseInboxQuery()(CustomerPulseInboxQueryDTO()) == {"inbox": {}}
    assert ListCustomerPulseInboxQuery()(CustomerPulseInboxQueryDTO()) == {"inbox": {}}
    assert GetCustomerPulseMetricsQuery()(CustomerPulseMetricsQueryDTO()) == {"stats": {}}
    assert GetCustomerPulseStatsQuery()(CustomerPulseStatsQueryDTO()) == {"stats": {}}
    assert GetCustomerPulseDetailQuery()(CustomerPulseDetailQueryDTO(external_userid="ext-1")) == {"customer_pulse": {}}
    assert GetCustomerPulseCardQuery()(CustomerPulseCardQueryDTO(card_id=1)) == {"card": {}}
    assert GetCustomerPulseCardEvidenceQuery()(CustomerPulseCardEvidenceQueryDTO(card_id=1)) == {"evidence": []}
    assert RefreshCustomerPulseCardsCommand()(RefreshCustomerPulseCardsCommandDTO()) == {"processed": 1}
    assert EnqueueCustomerPulseRecomputeCommand()(EnqueueCustomerPulseRecomputeCommandDTO()) == {"queued": 1}
    assert RunDueCustomerPulseSnapshotJobCommand()(RunDueCustomerPulseSnapshotJobCommandDTO()) == {"done": True}
    assert PreviewCustomerActionCommand()(PreviewCustomerActionCommandDTO(card_id=1)) == {"preview": {}}
    assert PreviewCustomerPulseCardActionCommand()(
        PreviewCustomerPulseCardActionCommandDTO(card_id=1)
    ) == {"preview": {}}
    assert ExecuteCustomerActionCommand()(ExecuteCustomerActionCommandDTO(card_id=1)) == {"execution": {}}
    assert ExecuteCustomerPulseCardActionCommand()(
        ExecuteCustomerPulseCardActionCommandDTO(card_id=1)
    ) == {"execution": {}}
    assert UndoCustomerActionCommand()(UndoCustomerActionCommandDTO(execution_id=1)) == {"result": {}}
    assert UndoCustomerPulseCardActionCommand()(
        UndoCustomerPulseCardActionCommandDTO(execution_id=1)
    ) == {"result": {}}
    assert SubmitCustomerPulseFeedbackCommand()(
        SubmitCustomerPulseFeedbackCommandDTO(card_id=1)
    ) == {"feedback": {}}
    assert GetFollowupOrchestratorFeatureGateQuery()(FollowupFeatureGateQueryDTO()) == {"enabled": True}
    assert ListFollowupCandidatesQuery()(FollowupCandidatesQueryDTO()) == {"orchestrator": {}}
    assert GetFollowupOrchestratorOverviewQuery()(FollowupOverviewQueryDTO()) == {"orchestrator": {}}
    assert GetFollowupOrchestratorCustomerQuery()(
        FollowupCustomerQueryDTO(external_userid="ext-1")
    ) == {"customer": {}}
    assert ListFollowupMyMissionsQuery()(FollowupMyMissionsQueryDTO(actor_userid="sales_01")) == {"my_missions": []}
    assert GetFollowupMissionBoardQuery()(FollowupMissionBoardQueryDTO()) == {"team_board": {}}
    assert GetFollowupTeamBoardQuery()(FollowupTeamBoardQueryDTO()) == {"team_board": {}}
    assert GetFollowupMissionDetailQuery()(
        FollowupMissionDetailQueryDTO(mission_key="mission-1")
    ) == {"mission": {}}
    assert SyncFollowupMissionsCommand()(SyncFollowupMissionsCommandDTO()) == {"synced": True}
    assert AssignFollowupMissionCommand()(
        AssignFollowupMissionCommandDTO(mission_key="mission-1", action_type="claim")
    ) == {"result": {}}
    assert ApplyFollowupMissionActionCommand()(
        ApplyFollowupMissionActionCommandDTO(mission_key="mission-1", action_type="claim")
    ) == {"result": {}}
    assert PreviewFollowupMissionItemActionCommand()(
        PreviewFollowupMissionItemActionCommandDTO(mission_key="mission-1", mission_item_key="item-1")
    ) == {"preview": {}}
    assert ExecuteFollowupMissionItemActionCommand()(
        ExecuteFollowupMissionItemActionCommandDTO(mission_key="mission-1", mission_item_key="item-1")
    ) == {"result": {}}
    assert UndoFollowupMissionItemActionCommand()(
        UndoFollowupMissionItemActionCommandDTO(mission_key="mission-1", mission_item_key="item-1")
    ) == {"result": {}}

    assert isinstance(calls["get_customer_pulse_feature_gate"], CustomerPulseFeatureGateQueryDTO)
    assert isinstance(calls["list_customer_pulse_inbox"], CustomerPulseInboxQueryDTO)
    assert isinstance(calls["get_customer_pulse_stats"], CustomerPulseStatsQueryDTO)
    assert isinstance(calls["get_customer_pulse_detail"], CustomerPulseDetailQueryDTO)
    assert isinstance(calls["get_customer_pulse_card"], CustomerPulseCardQueryDTO)
    assert isinstance(calls["get_customer_pulse_card_evidence"], CustomerPulseCardEvidenceQueryDTO)
    assert isinstance(calls["refresh_customer_pulse_cards"], RefreshCustomerPulseCardsCommandDTO)
    assert isinstance(calls["enqueue_customer_pulse_recompute"], EnqueueCustomerPulseRecomputeCommandDTO)
    assert isinstance(calls["run_due_customer_pulse_snapshot_job"], RunDueCustomerPulseSnapshotJobCommandDTO)
    assert isinstance(calls["preview_customer_pulse_card_action"], PreviewCustomerPulseCardActionCommandDTO)
    assert isinstance(calls["execute_customer_pulse_card_action"], ExecuteCustomerPulseCardActionCommandDTO)
    assert isinstance(calls["undo_customer_pulse_card_action"], UndoCustomerPulseCardActionCommandDTO)
    assert isinstance(calls["submit_customer_pulse_feedback"], SubmitCustomerPulseFeedbackCommandDTO)
    assert isinstance(calls["get_followup_feature_gate"], FollowupFeatureGateQueryDTO)
    assert isinstance(calls["get_followup_overview"], FollowupOverviewQueryDTO)
    assert isinstance(calls["get_followup_customer"], FollowupCustomerQueryDTO)
    assert isinstance(calls["list_followup_my_missions"], FollowupMyMissionsQueryDTO)
    assert isinstance(calls["get_followup_team_board"], FollowupTeamBoardQueryDTO)
    assert isinstance(calls["get_followup_mission_detail"], FollowupMissionDetailQueryDTO)
    assert isinstance(calls["sync_followup_missions"], SyncFollowupMissionsCommandDTO)
    assert isinstance(calls["apply_followup_mission_action"], ApplyFollowupMissionActionCommandDTO)
    assert isinstance(calls["preview_followup_mission_item_action"], PreviewFollowupMissionItemActionCommandDTO)
    assert isinstance(calls["execute_followup_mission_item_action"], ExecuteFollowupMissionItemActionCommandDTO)
    assert isinstance(calls["undo_followup_mission_item_action"], UndoFollowupMissionItemActionCommandDTO)
