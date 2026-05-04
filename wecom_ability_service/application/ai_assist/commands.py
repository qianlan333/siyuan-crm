from __future__ import annotations

from . import _legacy_delegate
from .dto import (
    ApplyFollowupMissionActionCommandDTO,
    AssignFollowupMissionCommandDTO,
    AssignFollowupMissionResultDTO,
    CustomerPulseActionExecuteResultDTO,
    CustomerPulseActionPreviewResultDTO,
    CustomerPulseActionUndoResultDTO,
    CustomerPulseFeedbackResultDTO,
    CustomerPulseRecomputeEnqueueResultDTO,
    CustomerPulseRefreshResultDTO,
    CustomerPulseRunDueResultDTO,
    EnqueueCustomerPulseRecomputeCommandDTO,
    ExecuteCustomerActionCommandDTO,
    ExecuteCustomerActionResultDTO,
    ExecuteCustomerPulseCardActionCommandDTO,
    ExecuteFollowupMissionItemActionCommandDTO,
    FollowupMissionActionResultDTO,
    FollowupMissionItemExecuteResultDTO,
    FollowupMissionItemPreviewResultDTO,
    FollowupMissionItemUndoResultDTO,
    PreviewCustomerActionCommandDTO,
    PreviewCustomerActionResultDTO,
    PreviewCustomerPulseCardActionCommandDTO,
    PreviewFollowupMissionItemActionCommandDTO,
    RefreshCustomerPulseCardsCommandDTO,
    RunDueCustomerPulseSnapshotJobCommandDTO,
    SubmitCustomerPulseFeedbackCommandDTO,
    SyncFollowupMissionsCommandDTO,
    UndoCustomerActionCommandDTO,
    UndoCustomerActionResultDTO,
    UndoCustomerPulseCardActionCommandDTO,
    UndoFollowupMissionItemActionCommandDTO,
)


class RefreshCustomerPulseCardsCommand:
    """Wave 5 AI Assist skeleton that delegates to ``domains.customer_pulse.refresh_customer_pulse_cards`` via ``_legacy_delegate`` for pulse admin refresh callers that will cut over in PR 2."""

    def __call__(self, dto: RefreshCustomerPulseCardsCommandDTO) -> CustomerPulseRefreshResultDTO:
        return _legacy_delegate.refresh_customer_pulse_cards_legacy(dto)

    execute = __call__


class EnqueueCustomerPulseRecomputeCommand:
    """Wave 5 AI Assist skeleton that delegates to ``domains.customer_pulse.enqueue_customer_pulse_recompute`` via ``_legacy_delegate`` for internal recompute callers that will cut over in PR 2."""

    def __call__(self, dto: EnqueueCustomerPulseRecomputeCommandDTO) -> CustomerPulseRecomputeEnqueueResultDTO:
        return _legacy_delegate.enqueue_customer_pulse_recompute_legacy(dto)

    execute = __call__


class RunDueCustomerPulseSnapshotJobCommand:
    """Wave 5 AI Assist skeleton that delegates to ``domains.customer_pulse.run_due_customer_pulse_snapshot_job`` via ``_legacy_delegate`` for internal due-runner callers that will cut over in PR 2."""

    def __call__(self, dto: RunDueCustomerPulseSnapshotJobCommandDTO) -> CustomerPulseRunDueResultDTO:
        return _legacy_delegate.run_due_customer_pulse_snapshot_job_legacy(dto)

    execute = __call__


class PreviewCustomerPulseCardActionCommand:
    """Wave 5 AI Assist skeleton that delegates to ``domains.customer_pulse.preview_customer_pulse_card_action`` via ``_legacy_delegate`` for pulse preview callers and future followup item bridges."""

    def __call__(self, dto: PreviewCustomerPulseCardActionCommandDTO) -> CustomerPulseActionPreviewResultDTO:
        return _legacy_delegate.preview_customer_pulse_card_action_legacy(dto)

    execute = __call__


class PreviewCustomerActionCommand:
    """Wave 5 AI Assist skeleton that delegates to ``domains.customer_pulse.preview_customer_pulse_card_action`` via ``_legacy_delegate`` for pulse-action preview callers that will cut over in PR 2."""

    def __call__(self, dto: PreviewCustomerActionCommandDTO) -> PreviewCustomerActionResultDTO:
        return _legacy_delegate.preview_customer_pulse_card_action_legacy(dto)

    execute = __call__


class ExecuteCustomerPulseCardActionCommand:
    """Wave 5 AI Assist skeleton that delegates to ``domains.customer_pulse.execute_customer_pulse_card_action`` via ``_legacy_delegate`` for pulse execute callers and future followup item bridges."""

    def __call__(self, dto: ExecuteCustomerPulseCardActionCommandDTO) -> CustomerPulseActionExecuteResultDTO:
        return _legacy_delegate.execute_customer_pulse_card_action_legacy(dto)

    execute = __call__


class ExecuteCustomerActionCommand:
    """Wave 5 AI Assist skeleton that delegates to ``domains.customer_pulse.execute_customer_pulse_card_action`` via ``_legacy_delegate`` for pulse-action execute callers that will cut over in PR 2."""

    def __call__(self, dto: ExecuteCustomerActionCommandDTO) -> ExecuteCustomerActionResultDTO:
        return _legacy_delegate.execute_customer_pulse_card_action_legacy(dto)

    execute = __call__


class UndoCustomerPulseCardActionCommand:
    """Wave 5 AI Assist skeleton that delegates to ``domains.customer_pulse.undo_customer_pulse_card_action_execution`` via ``_legacy_delegate`` for pulse undo callers and future followup item bridges."""

    def __call__(self, dto: UndoCustomerPulseCardActionCommandDTO) -> CustomerPulseActionUndoResultDTO:
        return _legacy_delegate.undo_customer_pulse_card_action_legacy(dto)

    execute = __call__


class UndoCustomerActionCommand:
    """Wave 5 AI Assist skeleton that delegates to ``domains.customer_pulse.undo_customer_pulse_card_action_execution`` via ``_legacy_delegate`` for pulse-action undo callers that will cut over in PR 2."""

    def __call__(self, dto: UndoCustomerActionCommandDTO) -> UndoCustomerActionResultDTO:
        return _legacy_delegate.undo_customer_pulse_card_action_legacy(dto)

    execute = __call__


class SubmitCustomerPulseFeedbackCommand:
    """Wave 5 AI Assist skeleton that delegates to ``domains.customer_pulse.submit_customer_pulse_feedback`` via ``_legacy_delegate`` for pulse feedback callers that will cut over in PR 2."""

    def __call__(self, dto: SubmitCustomerPulseFeedbackCommandDTO) -> CustomerPulseFeedbackResultDTO:
        return _legacy_delegate.submit_customer_pulse_feedback_legacy(dto)

    execute = __call__


class SyncFollowupMissionsCommand:
    """Wave 5 AI Assist skeleton that delegates to ``domains.followup_orchestrator.sync_followup_orchestrator_missions`` via ``_legacy_delegate`` for followup sync callers that will cut over in PR 3."""

    def __call__(self, dto: SyncFollowupMissionsCommandDTO) -> dict:
        return _legacy_delegate.sync_followup_missions_legacy(dto)

    execute = __call__


class ApplyFollowupMissionActionCommand:
    """Wave 5 AI Assist skeleton that delegates to ``domains.followup_orchestrator.apply_followup_orchestrator_mission_action`` via ``_legacy_delegate`` for followup mission-action callers that will cut over in PR 3."""

    def __call__(self, dto: ApplyFollowupMissionActionCommandDTO) -> FollowupMissionActionResultDTO:
        return _legacy_delegate.apply_followup_mission_action_legacy(dto)

    execute = __call__


class AssignFollowupMissionCommand:
    """Wave 5 AI Assist skeleton that delegates to ``domains.followup_orchestrator.apply_followup_orchestrator_mission_action`` via ``_legacy_delegate`` for mission-assignment callers that will cut over in PR 3."""

    def __call__(self, dto: AssignFollowupMissionCommandDTO) -> AssignFollowupMissionResultDTO:
        return _legacy_delegate.apply_followup_mission_action_legacy(dto)

    execute = __call__


class PreviewFollowupMissionItemActionCommand:
    """Wave 5 AI Assist skeleton that delegates to ``domains.followup_orchestrator.preview_followup_orchestrator_mission_item_action`` via ``_legacy_delegate`` for followup mission-item preview callers that will cut over in PR 3."""

    def __call__(self, dto: PreviewFollowupMissionItemActionCommandDTO) -> FollowupMissionItemPreviewResultDTO:
        return _legacy_delegate.preview_followup_mission_item_action_legacy(dto)

    execute = __call__


class ExecuteFollowupMissionItemActionCommand:
    """Wave 5 AI Assist skeleton that delegates to ``domains.followup_orchestrator.execute_followup_orchestrator_mission_item_action`` via ``_legacy_delegate`` for followup mission-item execute callers that will cut over in PR 3."""

    def __call__(self, dto: ExecuteFollowupMissionItemActionCommandDTO) -> FollowupMissionItemExecuteResultDTO:
        return _legacy_delegate.execute_followup_mission_item_action_legacy(dto)

    execute = __call__


class UndoFollowupMissionItemActionCommand:
    """Wave 5 AI Assist skeleton that delegates to ``domains.followup_orchestrator.undo_followup_orchestrator_mission_item_action`` via ``_legacy_delegate`` for followup mission-item undo callers that will cut over in PR 3."""

    def __call__(self, dto: UndoFollowupMissionItemActionCommandDTO) -> FollowupMissionItemUndoResultDTO:
        return _legacy_delegate.undo_followup_mission_item_action_legacy(dto)

    execute = __call__


__all__ = [
    "ApplyFollowupMissionActionCommand",
    "AssignFollowupMissionCommand",
    "EnqueueCustomerPulseRecomputeCommand",
    "ExecuteCustomerActionCommand",
    "ExecuteCustomerPulseCardActionCommand",
    "ExecuteFollowupMissionItemActionCommand",
    "PreviewCustomerActionCommand",
    "PreviewCustomerPulseCardActionCommand",
    "PreviewFollowupMissionItemActionCommand",
    "RefreshCustomerPulseCardsCommand",
    "RunDueCustomerPulseSnapshotJobCommand",
    "SubmitCustomerPulseFeedbackCommand",
    "SyncFollowupMissionsCommand",
    "UndoCustomerActionCommand",
    "UndoCustomerPulseCardActionCommand",
    "UndoFollowupMissionItemActionCommand",
]
