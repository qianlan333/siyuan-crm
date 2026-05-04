from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


SignupConversionBatchListResultDTO = dict[str, Any]
SignupConversionBatchDetailResultDTO = dict[str, Any] | None
SignupConversionConfigResultDTO = dict[str, Any]
SignupConversionConfigCommandResultDTO = dict[str, Any]
SignupConversionPreviewResultDTO = dict[str, Any]
SignupConversionRecomputeResultDTO = dict[str, Any]
OutboundWebhookListResultDTO = dict[str, Any]
OutboundWebhookCountResultDTO = dict[str, int]
OutboundWebhookRetryResultDTO = dict[str, Any]
OutboundWebhookRetryBatchResultDTO = dict[str, Any]
AutomationMemberActivationResultDTO = dict[str, Any]
ActivationWebhookResultDTO = dict[str, Any]
ConversionFeedbackResultDTO = dict[str, Any]
ConversionBatchAckResultDTO = dict[str, Any] | None
CustomerMarketingProfileResultDTO = dict[str, Any]
MarkEnrolledResultDTO = dict[str, Any]
UnmarkEnrolledResultDTO = dict[str, Any]
ManualFollowupSegmentResultDTO = dict[str, Any]


@dataclass(slots=True)
class SignupConversionBatchListQueryDTO:
    limit: int = 20
    cursor: str = ""
    scenario_key: str = ""


@dataclass(slots=True)
class SignupConversionBatchDetailQueryDTO:
    batch_id: int
    scenario_key: str = ""


@dataclass(slots=True)
class SignupConversionConfigQueryDTO:
    automation_key: str = ""


@dataclass(slots=True)
class SignupConversionConfigCommandDTO:
    payload: dict[str, Any] = field(default_factory=dict)
    automation_key: str = ""
    operator: str = ""
    enforce_required_mobile_question: bool = False


@dataclass(slots=True)
class SignupConversionPreviewQueryDTO:
    external_userid: str = ""
    person_id: int | None = None
    automation_key: str = ""
    persist: bool = True


@dataclass(slots=True)
class SignupConversionRecomputeCommandDTO:
    external_userid: str = ""
    person_id: int | None = None
    external_userids: list[Any] = field(default_factory=list)
    person_ids: list[Any] = field(default_factory=list)
    automation_key: str = ""
    persist: bool = True
    operator: str = ""


@dataclass(slots=True)
class OutboundWebhookListQueryDTO:
    event_type: str = ""
    status: str = ""
    limit: int = 50


@dataclass(slots=True)
class OutboundWebhookCountQueryDTO:
    include_failed_only: bool = False


@dataclass(slots=True)
class OutboundWebhookRetryCommandDTO:
    delivery_id: int
    operator: str = ""


@dataclass(slots=True)
class OutboundWebhookRetryBatchCommandDTO:
    limit: int = 20
    operator: str = ""


@dataclass(slots=True)
class AutomationMemberActivationCommandDTO:
    external_contact_id: str = ""
    phone: str = ""
    operator_id: str = "system"


@dataclass(slots=True)
class ActivationWebhookCommandDTO:
    mobile: str
    activated_at: str = ""
    operator: str = ""
    source: str = "activation_webhook"


@dataclass(slots=True)
class ConversionFeedbackCommandDTO:
    feedback_type: str
    external_userid: str = ""
    chat_id: str = ""
    actor: str = ""
    feedback_payload: dict[str, Any] | None = None


@dataclass(slots=True)
class ConversionBatchAckCommandDTO:
    batch_id: int
    acked_by: str = ""
    ack_note: str = ""
    automation_key: str = ""


@dataclass(slots=True)
class CustomerMarketingProfileQueryDTO:
    external_userid: str
    scenario_key: str = ""
    batch_context: dict[str, Any] | None = None


@dataclass(slots=True)
class MarkEnrolledCommandDTO:
    external_userid: str
    owner_userid: str = ""
    operator: str = ""
    source: str = "manual"
    signup_status: str = ""
    automation_key: str = ""


@dataclass(slots=True)
class UnmarkEnrolledCommandDTO:
    external_userid: str
    owner_userid: str = ""
    operator: str = ""
    source: str = "manual"
    restore_signup_status: str = ""
    automation_key: str = ""


@dataclass(slots=True)
class ManualFollowupSegmentCommandDTO:
    external_userid: str
    followup_segment: str
    owner_userid: str = ""
    operator: str = ""
    source: str = "manual"
    automation_key: str = ""


__all__ = [
    "ActivationWebhookCommandDTO",
    "ActivationWebhookResultDTO",
    "AutomationMemberActivationCommandDTO",
    "AutomationMemberActivationResultDTO",
    "ConversionBatchAckCommandDTO",
    "ConversionBatchAckResultDTO",
    "ConversionFeedbackCommandDTO",
    "ConversionFeedbackResultDTO",
    "CustomerMarketingProfileQueryDTO",
    "CustomerMarketingProfileResultDTO",
    "ManualFollowupSegmentCommandDTO",
    "ManualFollowupSegmentResultDTO",
    "MarkEnrolledCommandDTO",
    "MarkEnrolledResultDTO",
    "OutboundWebhookCountQueryDTO",
    "OutboundWebhookCountResultDTO",
    "OutboundWebhookListQueryDTO",
    "OutboundWebhookListResultDTO",
    "OutboundWebhookRetryBatchCommandDTO",
    "OutboundWebhookRetryBatchResultDTO",
    "OutboundWebhookRetryCommandDTO",
    "OutboundWebhookRetryResultDTO",
    "SignupConversionBatchDetailQueryDTO",
    "SignupConversionBatchDetailResultDTO",
    "SignupConversionBatchListQueryDTO",
    "SignupConversionBatchListResultDTO",
    "SignupConversionConfigCommandDTO",
    "SignupConversionConfigCommandResultDTO",
    "SignupConversionConfigQueryDTO",
    "SignupConversionConfigResultDTO",
    "SignupConversionPreviewQueryDTO",
    "SignupConversionPreviewResultDTO",
    "SignupConversionRecomputeCommandDTO",
    "SignupConversionRecomputeResultDTO",
    "UnmarkEnrolledCommandDTO",
    "UnmarkEnrolledResultDTO",
]
