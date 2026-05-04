from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


CustomerPulseFeatureGateResultDTO = dict[str, Any]
CustomerPulseInboxResultDTO = dict[str, Any]
CustomerPulseStatsResultDTO = dict[str, Any]
CustomerPulseDetailResultDTO = dict[str, Any]
CustomerPulseCustomerDetailResultDTO = dict[str, Any]
CustomerPulseCardResultDTO = dict[str, Any]
CustomerPulseCardEvidenceResultDTO = dict[str, Any]
CustomerPulseRefreshResultDTO = dict[str, Any]
CustomerPulseRecomputeEnqueueResultDTO = dict[str, Any]
CustomerPulseRunDueResultDTO = dict[str, Any]
CustomerPulseActionPreviewResultDTO = dict[str, Any]
CustomerPulseActionExecuteResultDTO = dict[str, Any]
CustomerPulseActionUndoResultDTO = dict[str, Any]
CustomerPulseFeedbackResultDTO = dict[str, Any]
FollowupFeatureGateResultDTO = dict[str, Any]
FollowupOverviewResultDTO = dict[str, Any]
FollowupCustomerResultDTO = dict[str, Any]
FollowupMyMissionsResultDTO = dict[str, Any]
FollowupTeamBoardResultDTO = dict[str, Any]
FollowupMissionDetailResultDTO = dict[str, Any]
FollowupMissionSyncResultDTO = dict[str, Any]
FollowupMissionActionResultDTO = dict[str, Any]
FollowupMissionItemPreviewResultDTO = dict[str, Any]
FollowupMissionItemExecuteResultDTO = dict[str, Any]
FollowupMissionItemUndoResultDTO = dict[str, Any]


@dataclass(slots=True)
class CustomerPulseFeatureGateQueryDTO:
    access_context: dict[str, Any] | None = None


@dataclass(slots=True)
class CustomerPulseInboxQueryDTO:
    filters: dict[str, Any] = field(default_factory=dict)
    access_context: dict[str, Any] | None = None
    metric_source: str = ""


@dataclass(slots=True)
class CustomerPulseStatsQueryDTO:
    days: int = 7
    owner_userids: list[str] = field(default_factory=list)
    access_context: dict[str, Any] | None = None


@dataclass(slots=True)
class CustomerPulseDetailQueryDTO:
    external_userid: str
    access_context: dict[str, Any] | None = None


@dataclass(slots=True)
class CustomerPulseCustomerDetailQueryDTO:
    external_userid: str
    tenant_key: str = ""
    allowed_owner_userids: list[str] = field(default_factory=list)
    track_metrics: bool = False
    access_context: dict[str, Any] | None = None


@dataclass(slots=True)
class CustomerPulseCardQueryDTO:
    card_id: int
    access_context: dict[str, Any] | None = None
    metric_source: str = ""


@dataclass(slots=True)
class CustomerPulseCardEvidenceQueryDTO:
    card_id: int
    access_context: dict[str, Any] | None = None
    event_source: str = ""


@dataclass(slots=True)
class RefreshCustomerPulseCardsCommandDTO:
    external_userids: list[str] = field(default_factory=list)
    limit: int = 50
    operator: str = ""
    allowed_owner_userids: list[str] = field(default_factory=list)
    access_context: dict[str, Any] | None = None


@dataclass(slots=True)
class EnqueueCustomerPulseRecomputeCommandDTO:
    external_userid: str = ""
    external_userids: list[str] = field(default_factory=list)
    owner_userid: str = ""
    delay_seconds: int = 0
    operator: str = ""
    trigger_source: str = ""
    trigger_ref_type: str = ""
    trigger_ref_id: str = ""
    access_context: dict[str, Any] | None = None


@dataclass(slots=True)
class RunDueCustomerPulseSnapshotJobCommandDTO:
    limit: int = 50
    rescan_limit: int = 20
    operator: str = ""
    allowed_owner_userids: list[str] = field(default_factory=list)
    access_context: dict[str, Any] | None = None


@dataclass(slots=True)
class PreviewCustomerPulseCardActionCommandDTO:
    card_id: int
    action_type: str = ""
    action_payload: dict[str, Any] = field(default_factory=dict)
    track_click: bool = False
    metric_source: str = ""
    operator: str = ""
    access_context: dict[str, Any] | None = None


@dataclass(slots=True)
class ExecuteCustomerPulseCardActionCommandDTO:
    card_id: int
    action_type: str = ""
    action_payload: dict[str, Any] = field(default_factory=dict)
    operator: str = ""
    admin_action_token: str = ""
    access_context: dict[str, Any] | None = None


@dataclass(slots=True)
class UndoCustomerPulseCardActionCommandDTO:
    execution_id: int
    operator: str = ""
    access_context: dict[str, Any] | None = None


@dataclass(slots=True)
class SubmitCustomerPulseFeedbackCommandDTO:
    card_id: int
    feedback_type: str = ""
    feedback_payload: dict[str, Any] = field(default_factory=dict)
    operator: str = ""
    access_context: dict[str, Any] | None = None


@dataclass(slots=True)
class FollowupFeatureGateQueryDTO:
    access_context: dict[str, Any] | None = None


@dataclass(slots=True)
class FollowupOverviewQueryDTO:
    scope: str = "team"
    owner_userid: str = ""
    external_userid: str = ""
    limit: int = 50
    auto_sync: bool = True
    access_context: dict[str, Any] | None = None


@dataclass(slots=True)
class FollowupCustomerQueryDTO:
    external_userid: str
    access_context: dict[str, Any] | None = None


@dataclass(slots=True)
class FollowupMyMissionsQueryDTO:
    actor_userid: str = ""
    limit: int = 50
    auto_sync: bool = True
    access_context: dict[str, Any] | None = None


@dataclass(slots=True)
class FollowupTeamBoardQueryDTO:
    limit: int = 50
    auto_sync: bool = True
    access_context: dict[str, Any] | None = None


@dataclass(slots=True)
class FollowupMissionDetailQueryDTO:
    mission_key: str
    access_context: dict[str, Any] | None = None
    tenant_key: str = ""


@dataclass(slots=True)
class SyncFollowupMissionsCommandDTO:
    scope: str = "team"
    owner_userid: str = ""
    external_userid: str = ""
    limit: int = 50
    access_context: dict[str, Any] | None = None


@dataclass(slots=True)
class ApplyFollowupMissionActionCommandDTO:
    mission_key: str
    action_type: str
    actor_userid: str = ""
    actor_role: str = ""
    operator: str = ""
    access_context: dict[str, Any] | None = None
    mission_item_key: str = ""
    note: str = ""


@dataclass(slots=True)
class PreviewFollowupMissionItemActionCommandDTO:
    mission_key: str
    mission_item_key: str
    action_type: str = ""
    actor_userid: str = ""
    operator: str = ""
    access_context: dict[str, Any] | None = None


@dataclass(slots=True)
class ExecuteFollowupMissionItemActionCommandDTO:
    mission_key: str
    mission_item_key: str
    action_type: str = ""
    actor_userid: str = ""
    actor_role: str = ""
    operator: str = ""
    note: str = ""
    action_payload: dict[str, Any] = field(default_factory=dict)
    admin_action_token: str = ""
    access_context: dict[str, Any] | None = None


@dataclass(slots=True)
class UndoFollowupMissionItemActionCommandDTO:
    mission_key: str
    mission_item_key: str
    execution_id: int = 0
    actor_userid: str = ""
    actor_role: str = ""
    operator: str = ""
    access_context: dict[str, Any] | None = None


# Wave 5 PR 1 formal-contract aliases. These reuse the existing legacy-compatible
# DTO shapes so caller cutovers can move to stable application names without
# changing payload contracts in this hardening step.
CustomerPulseMetricsQueryDTO = CustomerPulseStatsQueryDTO
CustomerPulseMetricsResultDTO = CustomerPulseStatsResultDTO
FollowupCandidatesQueryDTO = FollowupOverviewQueryDTO
FollowupCandidatesResultDTO = FollowupOverviewResultDTO
FollowupMissionBoardQueryDTO = FollowupTeamBoardQueryDTO
FollowupMissionBoardResultDTO = FollowupTeamBoardResultDTO
PreviewCustomerActionCommandDTO = PreviewCustomerPulseCardActionCommandDTO
PreviewCustomerActionResultDTO = CustomerPulseActionPreviewResultDTO
ExecuteCustomerActionCommandDTO = ExecuteCustomerPulseCardActionCommandDTO
ExecuteCustomerActionResultDTO = CustomerPulseActionExecuteResultDTO
UndoCustomerActionCommandDTO = UndoCustomerPulseCardActionCommandDTO
UndoCustomerActionResultDTO = CustomerPulseActionUndoResultDTO
AssignFollowupMissionCommandDTO = ApplyFollowupMissionActionCommandDTO
AssignFollowupMissionResultDTO = FollowupMissionActionResultDTO


__all__ = [
    "ApplyFollowupMissionActionCommandDTO",
    "AssignFollowupMissionCommandDTO",
    "AssignFollowupMissionResultDTO",
    "CustomerPulseCardEvidenceQueryDTO",
    "CustomerPulseCardEvidenceResultDTO",
    "CustomerPulseCardQueryDTO",
    "CustomerPulseCardResultDTO",
    "CustomerPulseMetricsQueryDTO",
    "CustomerPulseMetricsResultDTO",
    "CustomerPulseCustomerDetailQueryDTO",
    "CustomerPulseCustomerDetailResultDTO",
    "CustomerPulseDetailQueryDTO",
    "CustomerPulseDetailResultDTO",
    "CustomerPulseFeatureGateQueryDTO",
    "CustomerPulseFeatureGateResultDTO",
    "CustomerPulseFeedbackResultDTO",
    "CustomerPulseInboxQueryDTO",
    "CustomerPulseInboxResultDTO",
    "CustomerPulseRecomputeEnqueueResultDTO",
    "CustomerPulseRefreshResultDTO",
    "CustomerPulseRunDueResultDTO",
    "CustomerPulseStatsQueryDTO",
    "CustomerPulseStatsResultDTO",
    "CustomerPulseActionExecuteResultDTO",
    "CustomerPulseActionPreviewResultDTO",
    "CustomerPulseActionUndoResultDTO",
    "EnqueueCustomerPulseRecomputeCommandDTO",
    "ExecuteCustomerActionCommandDTO",
    "ExecuteCustomerActionResultDTO",
    "ExecuteCustomerPulseCardActionCommandDTO",
    "ExecuteFollowupMissionItemActionCommandDTO",
    "FollowupCandidatesQueryDTO",
    "FollowupCandidatesResultDTO",
    "FollowupCustomerQueryDTO",
    "FollowupCustomerResultDTO",
    "FollowupFeatureGateQueryDTO",
    "FollowupFeatureGateResultDTO",
    "FollowupMissionActionResultDTO",
    "FollowupMissionBoardQueryDTO",
    "FollowupMissionBoardResultDTO",
    "FollowupMissionDetailQueryDTO",
    "FollowupMissionDetailResultDTO",
    "FollowupMissionItemExecuteResultDTO",
    "FollowupMissionItemPreviewResultDTO",
    "FollowupMissionItemUndoResultDTO",
    "FollowupMyMissionsQueryDTO",
    "FollowupMyMissionsResultDTO",
    "FollowupOverviewQueryDTO",
    "FollowupOverviewResultDTO",
    "PreviewCustomerActionCommandDTO",
    "PreviewCustomerActionResultDTO",
    "FollowupTeamBoardQueryDTO",
    "FollowupTeamBoardResultDTO",
    "PreviewCustomerPulseCardActionCommandDTO",
    "PreviewFollowupMissionItemActionCommandDTO",
    "RefreshCustomerPulseCardsCommandDTO",
    "RunDueCustomerPulseSnapshotJobCommandDTO",
    "SubmitCustomerPulseFeedbackCommandDTO",
    "SyncFollowupMissionsCommandDTO",
    "FollowupMissionSyncResultDTO",
    "UndoCustomerActionCommandDTO",
    "UndoCustomerActionResultDTO",
    "UndoCustomerPulseCardActionCommandDTO",
    "UndoFollowupMissionItemActionCommandDTO",
]
