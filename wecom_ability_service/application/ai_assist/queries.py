from __future__ import annotations

from . import _legacy_delegate
from .dto import (
    CustomerPulseCardEvidenceQueryDTO,
    CustomerPulseCardEvidenceResultDTO,
    CustomerPulseCardQueryDTO,
    CustomerPulseCardResultDTO,
    CustomerPulseCustomerDetailQueryDTO,
    CustomerPulseCustomerDetailResultDTO,
    CustomerPulseDetailQueryDTO,
    CustomerPulseDetailResultDTO,
    CustomerPulseFeatureGateQueryDTO,
    CustomerPulseFeatureGateResultDTO,
    CustomerPulseInboxQueryDTO,
    CustomerPulseInboxResultDTO,
    CustomerPulseMetricsQueryDTO,
    CustomerPulseMetricsResultDTO,
    CustomerPulseStatsQueryDTO,
    CustomerPulseStatsResultDTO,
    FollowupCandidatesQueryDTO,
    FollowupCandidatesResultDTO,
    FollowupCustomerQueryDTO,
    FollowupCustomerResultDTO,
    FollowupFeatureGateQueryDTO,
    FollowupFeatureGateResultDTO,
    FollowupMissionBoardQueryDTO,
    FollowupMissionBoardResultDTO,
    FollowupMissionDetailQueryDTO,
    FollowupMissionDetailResultDTO,
    FollowupMyMissionsQueryDTO,
    FollowupMyMissionsResultDTO,
    FollowupOverviewQueryDTO,
    FollowupOverviewResultDTO,
    FollowupTeamBoardQueryDTO,
    FollowupTeamBoardResultDTO,
)


class GetCustomerPulseFeatureGateQuery:
    """Wave 5 AI Assist skeleton that delegates to customer-pulse feature/access resolution via ``_legacy_delegate`` for admin shell, customer profile, and pulse page callers that will cut over in PR 2."""

    def __call__(
        self,
        dto: CustomerPulseFeatureGateQueryDTO | None = None,
    ) -> CustomerPulseFeatureGateResultDTO:
        return _legacy_delegate.get_customer_pulse_feature_gate_legacy(dto or CustomerPulseFeatureGateQueryDTO())

    execute = __call__


class ListCustomerPulseInboxQuery:
    """Wave 5 AI Assist skeleton that delegates to ``domains.customer_pulse.build_customer_pulse_inbox_payload`` via ``_legacy_delegate`` for pulse inbox readers and future mission-source bridges."""

    def __call__(self, dto: CustomerPulseInboxQueryDTO) -> CustomerPulseInboxResultDTO:
        return _legacy_delegate.list_customer_pulse_inbox_legacy(dto)

    execute = __call__


class GetCustomerPulseInboxQuery:
    """Wave 5 AI Assist skeleton that delegates to ``domains.customer_pulse.build_customer_pulse_inbox_payload`` via ``_legacy_delegate`` for admin pulse inbox callers that will cut over in PR 2."""

    def __call__(self, dto: CustomerPulseInboxQueryDTO) -> CustomerPulseInboxResultDTO:
        return _legacy_delegate.list_customer_pulse_inbox_legacy(dto)

    execute = __call__


class GetCustomerPulseStatsQuery:
    """Wave 5 AI Assist skeleton that delegates to ``domains.customer_pulse.build_customer_pulse_ops_dashboard_payload`` via ``_legacy_delegate`` for pulse stats readers that will cut over in PR 2."""

    def __call__(self, dto: CustomerPulseStatsQueryDTO) -> CustomerPulseStatsResultDTO:
        return _legacy_delegate.get_customer_pulse_stats_legacy(dto)

    execute = __call__


class GetCustomerPulseMetricsQuery:
    """Wave 5 AI Assist skeleton that delegates to ``domains.customer_pulse.build_customer_pulse_ops_dashboard_payload`` via ``_legacy_delegate`` for metrics/dashboard callers that will cut over in PR 2."""

    def __call__(self, dto: CustomerPulseMetricsQueryDTO) -> CustomerPulseMetricsResultDTO:
        return _legacy_delegate.get_customer_pulse_stats_legacy(dto)

    execute = __call__


class GetCustomerPulseDetailQuery:
    """Wave 5 AI Assist skeleton that delegates to customer-pulse detail/widget adapters via ``_legacy_delegate`` for admin customer profile callers that will cut over in PR 2."""

    def __call__(self, dto: CustomerPulseDetailQueryDTO) -> CustomerPulseDetailResultDTO:
        return _legacy_delegate.get_customer_pulse_detail_legacy(dto)

    execute = __call__


class GetCustomerPulseCustomerDetailQuery:
    """Wave 5 AI Assist skeleton that delegates to ``domains.customer_pulse.build_customer_pulse_customer_detail_payload`` via ``_legacy_delegate`` for internal pulse detail readers that will cut over in PR 2."""

    def __call__(self, dto: CustomerPulseCustomerDetailQueryDTO) -> CustomerPulseCustomerDetailResultDTO:
        return _legacy_delegate.get_customer_pulse_customer_detail_legacy(dto)

    execute = __call__


class GetCustomerPulseCardQuery:
    """Wave 5 AI Assist skeleton that delegates to ``domains.customer_pulse.get_customer_pulse_card_payload`` via ``_legacy_delegate`` for pulse card-detail readers that will cut over in PR 2."""

    def __call__(self, dto: CustomerPulseCardQueryDTO) -> CustomerPulseCardResultDTO:
        return _legacy_delegate.get_customer_pulse_card_legacy(dto)

    execute = __call__


class GetCustomerPulseCardEvidenceQuery:
    """Wave 5 AI Assist skeleton that delegates to ``domains.customer_pulse.get_customer_pulse_card_evidence_payload`` via ``_legacy_delegate`` for pulse evidence readers that will cut over in PR 2."""

    def __call__(self, dto: CustomerPulseCardEvidenceQueryDTO) -> CustomerPulseCardEvidenceResultDTO:
        return _legacy_delegate.get_customer_pulse_card_evidence_legacy(dto)

    execute = __call__


class GetFollowupOrchestratorFeatureGateQuery:
    """Wave 5 AI Assist skeleton that delegates to followup feature/access resolution via ``_legacy_delegate`` for admin shell and orchestrator callers that will cut over in PR 3."""

    def __call__(
        self,
        dto: FollowupFeatureGateQueryDTO | None = None,
    ) -> FollowupFeatureGateResultDTO:
        return _legacy_delegate.get_followup_feature_gate_legacy(dto or FollowupFeatureGateQueryDTO())

    execute = __call__


class GetFollowupOrchestratorOverviewQuery:
    """Wave 5 AI Assist skeleton that delegates to ``domains.followup_orchestrator.build_followup_orchestrator_overview_payload`` via ``_legacy_delegate`` for followup overview callers that will cut over in PR 3."""

    def __call__(self, dto: FollowupOverviewQueryDTO) -> FollowupOverviewResultDTO:
        return _legacy_delegate.get_followup_overview_legacy(dto)

    execute = __call__


class ListFollowupCandidatesQuery:
    """Wave 5 AI Assist skeleton that delegates to ``domains.followup_orchestrator.build_followup_orchestrator_overview_payload`` via ``_legacy_delegate`` for candidate-list callers that will cut over in PR 3."""

    def __call__(self, dto: FollowupCandidatesQueryDTO) -> FollowupCandidatesResultDTO:
        return _legacy_delegate.get_followup_overview_legacy(dto)

    execute = __call__


class GetFollowupOrchestratorCustomerQuery:
    """Wave 5 AI Assist skeleton that delegates to ``domains.followup_orchestrator.build_followup_orchestrator_customer_payload`` via ``_legacy_delegate`` for customer-level mission readers that will cut over in PR 3."""

    def __call__(self, dto: FollowupCustomerQueryDTO) -> FollowupCustomerResultDTO:
        return _legacy_delegate.get_followup_customer_legacy(dto)

    execute = __call__


class ListFollowupMyMissionsQuery:
    """Wave 5 AI Assist skeleton that delegates to ``domains.followup_orchestrator.build_followup_orchestrator_my_missions_payload`` via ``_legacy_delegate`` for actor mission readers that will cut over in PR 3."""

    def __call__(self, dto: FollowupMyMissionsQueryDTO) -> FollowupMyMissionsResultDTO:
        return _legacy_delegate.list_followup_my_missions_legacy(dto)

    execute = __call__


class GetFollowupTeamBoardQuery:
    """Wave 5 AI Assist skeleton that delegates to ``domains.followup_orchestrator.build_followup_orchestrator_team_board_payload`` via ``_legacy_delegate`` for team-board readers that will cut over in PR 3."""

    def __call__(self, dto: FollowupTeamBoardQueryDTO) -> FollowupTeamBoardResultDTO:
        return _legacy_delegate.get_followup_team_board_legacy(dto)

    execute = __call__


class GetFollowupMissionBoardQuery:
    """Wave 5 AI Assist skeleton that delegates to ``domains.followup_orchestrator.build_followup_orchestrator_team_board_payload`` via ``_legacy_delegate`` for mission-board callers that will cut over in PR 3."""

    def __call__(self, dto: FollowupMissionBoardQueryDTO) -> FollowupMissionBoardResultDTO:
        return _legacy_delegate.get_followup_team_board_legacy(dto)

    execute = __call__


class GetFollowupMissionDetailQuery:
    """Wave 5 AI Assist skeleton that delegates to ``domains.followup_orchestrator.get_followup_orchestrator_mission_detail_payload`` via ``_legacy_delegate`` for mission-detail readers that will cut over in PR 3."""

    def __call__(self, dto: FollowupMissionDetailQueryDTO) -> FollowupMissionDetailResultDTO:
        return _legacy_delegate.get_followup_mission_detail_legacy(dto)

    execute = __call__


from .commands import (  # noqa: E402
    ApplyFollowupMissionActionCommand,
    EnqueueCustomerPulseRecomputeCommand,
    ExecuteCustomerPulseCardActionCommand,
    ExecuteFollowupMissionItemActionCommand,
    PreviewCustomerPulseCardActionCommand,
    PreviewFollowupMissionItemActionCommand,
    RefreshCustomerPulseCardsCommand,
    RunDueCustomerPulseSnapshotJobCommand,
    SubmitCustomerPulseFeedbackCommand,
    SyncFollowupMissionsCommand,
    UndoCustomerPulseCardActionCommand,
    UndoFollowupMissionItemActionCommand,
)


__all__ = [
    "ApplyFollowupMissionActionCommand",
    "EnqueueCustomerPulseRecomputeCommand",
    "ExecuteCustomerPulseCardActionCommand",
    "ExecuteFollowupMissionItemActionCommand",
    "GetCustomerPulseCardEvidenceQuery",
    "GetCustomerPulseCardQuery",
    "GetCustomerPulseCustomerDetailQuery",
    "GetCustomerPulseDetailQuery",
    "GetCustomerPulseFeatureGateQuery",
    "GetCustomerPulseInboxQuery",
    "GetCustomerPulseMetricsQuery",
    "GetCustomerPulseStatsQuery",
    "GetFollowupMissionBoardQuery",
    "GetFollowupMissionDetailQuery",
    "GetFollowupOrchestratorCustomerQuery",
    "GetFollowupOrchestratorFeatureGateQuery",
    "GetFollowupOrchestratorOverviewQuery",
    "GetFollowupTeamBoardQuery",
    "ListCustomerPulseInboxQuery",
    "ListFollowupCandidatesQuery",
    "ListFollowupMyMissionsQuery",
    "PreviewCustomerPulseCardActionCommand",
    "PreviewFollowupMissionItemActionCommand",
    "RefreshCustomerPulseCardsCommand",
    "RunDueCustomerPulseSnapshotJobCommand",
    "SubmitCustomerPulseFeedbackCommand",
    "SyncFollowupMissionsCommand",
    "UndoCustomerPulseCardActionCommand",
    "UndoFollowupMissionItemActionCommand",
]
