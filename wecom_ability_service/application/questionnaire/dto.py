from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


ListQuestionnairesResultDTO = list[dict[str, Any]]
ListAvailableWeComTagsResultDTO = list[dict[str, Any]]
BuildQuestionnairePreflightResultDTO = dict[str, Any]
GetLatestQuestionnaireSubmitDebugResultDTO = dict[str, Any] | None
GetQuestionnaireDetailResultDTO = dict[str, Any] | None
ExportQuestionnaireSubmissionsResultDTO = dict[str, Any]
GetPublicQuestionnaireBySlugResultDTO = dict[str, Any] | None
GetQuestionnaireAssessmentResultByTokenResultDTO = dict[str, Any] | None
ResolveQuestionnaireSubmitIdentityResultDTO = dict[str, Any] | None
CheckQuestionnaireSubmissionStatusResultDTO = bool
ValidateQuestionnaireAnswersResultDTO = list[dict[str, Any]]
ComputeQuestionnaireSubmissionOutcomeResultDTO = dict[str, Any]
CreateQuestionnaireCommandResultDTO = dict[str, Any]
UpdateQuestionnaireCommandResultDTO = dict[str, Any] | None
CreateOrUpdateQuestionnaireCommandResultDTO = dict[str, Any] | None
DisableQuestionnaireCommandResultDTO = dict[str, Any] | None
DeleteQuestionnaireSubmissionsBySlugCommandResultDTO = dict[str, Any]
DeleteQuestionnaireCommandResultDTO = bool
SaveQuestionnaireSubmissionCommandResultDTO = dict[str, Any]
ApplyQuestionnaireMobileBindingCommandResultDTO = dict[str, Any]
ApplyQuestionnaireSubmissionTagsCommandResultDTO = dict[str, Any]
ApplyQuestionnaireResultToScrmCommandResultDTO = dict[str, Any]
SubmitQuestionnaireCommandResultDTO = dict[str, Any]
RetryQuestionnaireExternalPushLogCommandResultDTO = dict[str, Any]
RetryQuestionnaireExternalPushLogsCommandResultDTO = dict[str, Any]
RetryQuestionnaireExternalPushCommandResultDTO = dict[str, Any]


@dataclass(slots=True)
class ListQuestionnairesQueryDTO:
    include_disabled: bool = False
    include_stats: bool = True


@dataclass(slots=True)
class ListAvailableWeComTagsQueryDTO:
    pass


@dataclass(slots=True)
class BuildQuestionnairePreflightQueryDTO:
    config_snapshot: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class GetLatestQuestionnaireSubmitDebugQueryDTO:
    questionnaire_id: int


@dataclass(slots=True)
class GetQuestionnaireDetailQueryDTO:
    questionnaire_id: int


@dataclass(slots=True)
class ExportQuestionnaireSubmissionsQueryDTO:
    questionnaire_id: int


@dataclass(slots=True)
class GetPublicQuestionnaireBySlugQueryDTO:
    slug: str


@dataclass(slots=True)
class GetQuestionnaireAssessmentResultByTokenQueryDTO:
    slug: str
    result_token: str


@dataclass(slots=True)
class ResolveQuestionnaireSubmitIdentityQueryDTO:
    openid: str = ""
    unionid: str = ""
    external_userid: str = ""
    corp_id: str = ""
    respondent_key: str = ""
    session_identity: dict[str, Any] = field(default_factory=dict)
    request_meta: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CheckQuestionnaireSubmissionStatusQueryDTO:
    questionnaire_id: int
    identity: dict[str, Any] | None = None


@dataclass(slots=True)
class HasQuestionnaireSubmissionQueryDTO:
    questionnaire_id: int
    identity: dict[str, Any] | None = None


@dataclass(slots=True)
class ValidateQuestionnaireAnswersQueryDTO:
    questionnaire: dict[str, Any]
    answers: Any


@dataclass(slots=True)
class ComputeQuestionnaireSubmissionOutcomeQueryDTO:
    questionnaire: dict[str, Any]
    answers: Any


@dataclass(slots=True)
class CreateQuestionnaireCommandDTO:
    payload: dict[str, Any] = field(default_factory=dict)
    operator: str = ""


@dataclass(slots=True)
class UpdateQuestionnaireCommandDTO:
    questionnaire_id: int
    payload: dict[str, Any] = field(default_factory=dict)
    operator: str = ""


@dataclass(slots=True)
class CreateOrUpdateQuestionnaireCommandDTO:
    questionnaire_id: int | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    operator: str = ""


@dataclass(slots=True)
class DisableQuestionnaireCommandDTO:
    questionnaire_id: int
    is_disabled: bool = True
    operator: str = ""


@dataclass(slots=True)
class DeleteQuestionnaireSubmissionsBySlugCommandDTO:
    slug: str
    operator: str = ""


@dataclass(slots=True)
class DeleteQuestionnaireCommandDTO:
    questionnaire_id: int
    operator: str = ""


@dataclass(slots=True)
class SaveQuestionnaireSubmissionCommandDTO:
    questionnaire: dict[str, Any]
    identity: dict[str, Any] | None
    computed_result: dict[str, Any]
    answers: Any
    request_meta: dict[str, Any] | None = None


@dataclass(slots=True)
class ApplyQuestionnaireMobileBindingCommandDTO:
    submission_id: int = 0
    submission_snapshot: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ApplyQuestionnaireSubmissionTagsCommandDTO:
    submission_id: int
    operator: str = ""


@dataclass(slots=True)
class ApplyQuestionnaireResultToScrmCommandDTO:
    submission_id: int
    operator: str = ""


@dataclass(slots=True)
class SubmitQuestionnaireCommandDTO:
    slug: str
    payload: dict[str, Any] = field(default_factory=dict)
    answers: Any = None
    hidden_identity: dict[str, Any] = field(default_factory=dict)
    source_params: dict[str, Any] = field(default_factory=dict)
    request_meta: dict[str, Any] | None = None


@dataclass(slots=True)
class RetryQuestionnaireExternalPushLogCommandDTO:
    push_log_id: int
    operator: str = ""


@dataclass(slots=True)
class RetryQuestionnaireExternalPushLogsCommandDTO:
    push_log_ids: list[int] = field(default_factory=list)
    operator: str = ""


@dataclass(slots=True)
class RetryQuestionnaireExternalPushCommandDTO:
    push_log_id: int = 0
    push_log_ids: list[int] = field(default_factory=list)
    operator: str = ""


__all__ = [
    "ApplyQuestionnaireMobileBindingCommandDTO",
    "ApplyQuestionnaireMobileBindingCommandResultDTO",
    "ApplyQuestionnaireResultToScrmCommandDTO",
    "ApplyQuestionnaireResultToScrmCommandResultDTO",
    "ApplyQuestionnaireSubmissionTagsCommandDTO",
    "ApplyQuestionnaireSubmissionTagsCommandResultDTO",
    "BuildQuestionnairePreflightQueryDTO",
    "BuildQuestionnairePreflightResultDTO",
    "CheckQuestionnaireSubmissionStatusQueryDTO",
    "CheckQuestionnaireSubmissionStatusResultDTO",
    "ComputeQuestionnaireSubmissionOutcomeQueryDTO",
    "ComputeQuestionnaireSubmissionOutcomeResultDTO",
    "CreateOrUpdateQuestionnaireCommandDTO",
    "CreateOrUpdateQuestionnaireCommandResultDTO",
    "CreateQuestionnaireCommandDTO",
    "CreateQuestionnaireCommandResultDTO",
    "DeleteQuestionnaireCommandDTO",
    "DeleteQuestionnaireCommandResultDTO",
    "DeleteQuestionnaireSubmissionsBySlugCommandDTO",
    "DeleteQuestionnaireSubmissionsBySlugCommandResultDTO",
    "DisableQuestionnaireCommandDTO",
    "DisableQuestionnaireCommandResultDTO",
    "ExportQuestionnaireSubmissionsQueryDTO",
    "ExportQuestionnaireSubmissionsResultDTO",
    "HasQuestionnaireSubmissionQueryDTO",
    "GetLatestQuestionnaireSubmitDebugQueryDTO",
    "GetLatestQuestionnaireSubmitDebugResultDTO",
    "GetPublicQuestionnaireBySlugQueryDTO",
    "GetPublicQuestionnaireBySlugResultDTO",
    "GetQuestionnaireAssessmentResultByTokenQueryDTO",
    "GetQuestionnaireAssessmentResultByTokenResultDTO",
    "GetQuestionnaireDetailQueryDTO",
    "GetQuestionnaireDetailResultDTO",
    "ListAvailableWeComTagsQueryDTO",
    "ListAvailableWeComTagsResultDTO",
    "ListQuestionnairesQueryDTO",
    "ListQuestionnairesResultDTO",
    "ResolveQuestionnaireSubmitIdentityQueryDTO",
    "ResolveQuestionnaireSubmitIdentityResultDTO",
    "RetryQuestionnaireExternalPushCommandDTO",
    "RetryQuestionnaireExternalPushCommandResultDTO",
    "RetryQuestionnaireExternalPushLogCommandDTO",
    "RetryQuestionnaireExternalPushLogCommandResultDTO",
    "RetryQuestionnaireExternalPushLogsCommandDTO",
    "RetryQuestionnaireExternalPushLogsCommandResultDTO",
    "SaveQuestionnaireSubmissionCommandDTO",
    "SaveQuestionnaireSubmissionCommandResultDTO",
    "SubmitQuestionnaireCommandDTO",
    "SubmitQuestionnaireCommandResultDTO",
    "UpdateQuestionnaireCommandDTO",
    "UpdateQuestionnaireCommandResultDTO",
    "ValidateQuestionnaireAnswersQueryDTO",
    "ValidateQuestionnaireAnswersResultDTO",
]
