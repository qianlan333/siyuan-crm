from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


GetUserOpsOverviewResultDTO = dict[str, Any]
ListLeadPoolResultDTO = dict[str, Any]
ListUserOpsHistoryResultDTO = dict[str, Any]
ExportUserOpsPoolResultDTO = dict[str, Any]
UpsertLeadPoolMemberResultDTO = dict[str, Any]
WriteLeadPoolHistoryResultDTO = None
ScheduleUserOpsAutoAssignClassTermJobResultDTO = dict[str, Any]
RunDueUserOpsDeferredJobsResultDTO = dict[str, Any]
ImportExperienceLeadsResultDTO = dict[str, Any]
ImportMobileClassTermResultDTO = dict[str, Any]
ImportActivationStatusResultDTO = dict[str, Any]
BackfillOwnerClassTermsResultDTO = dict[str, Any]
RefreshUserOpsContactTagsResultDTO = dict[str, Any]


@dataclass(slots=True)
class LeadPoolFiltersDTO:
    wecom_status: str = ""
    mobile_binding_status: str = ""
    activation_bucket: str = ""
    is_wecom_added: str = ""
    is_mobile_bound: str = ""
    huangxiaocan_activation_state: str = ""
    class_term_no: str = ""
    keyword: str = ""
    mobile: str = ""
    owner_userid: str = ""
    query: str = ""


@dataclass(slots=True)
class GetUserOpsOverviewQueryDTO:
    filters: LeadPoolFiltersDTO = field(default_factory=LeadPoolFiltersDTO)


@dataclass(slots=True)
class ListLeadPoolQueryDTO:
    filters: LeadPoolFiltersDTO = field(default_factory=LeadPoolFiltersDTO)


@dataclass(slots=True)
class ListUserOpsHistoryQueryDTO:
    limit: int = 100


@dataclass(slots=True)
class ExportUserOpsPoolQueryDTO:
    filters: LeadPoolFiltersDTO = field(default_factory=LeadPoolFiltersDTO)


@dataclass(slots=True)
class UpsertLeadPoolMemberCommandDTO:
    mobile: str = ""
    external_userid: str = ""
    customer_name: str = ""
    owner_userid: str = ""
    is_wecom_added: bool = False
    is_mobile_bound: bool = False
    huangxiaocan_activation_state: str = ""
    class_term_no: int | None = None
    class_term_label: str = ""
    entry_source: str = ""
    operator: str = ""
    remark: str = ""


@dataclass(slots=True)
class WriteLeadPoolHistoryCommandDTO:
    mobile: str = ""
    external_userid: str = ""
    action_type: str = ""
    source_type: str = ""
    operator: str = ""
    before_payload: dict[str, Any] | None = None
    after_payload: dict[str, Any] | None = None
    remark: str = ""


@dataclass(slots=True)
class ScheduleUserOpsAutoAssignClassTermJobCommandDTO:
    external_userid: str
    owner_userid: str
    delay_seconds: int | None = None
    run_after_seconds: int = 10
    operator: str = ""


@dataclass(slots=True)
class RunDueUserOpsDeferredJobsCommandDTO:
    limit: int = 20


@dataclass(slots=True)
class ImportExperienceLeadsCommandDTO:
    pasted_text: str = ""
    file_name: str = ""
    file_bytes: bytes | None = None
    created_by: str = ""


@dataclass(slots=True)
class ImportMobileClassTermCommandDTO:
    pasted_text: str = ""
    file_name: str = ""
    file_bytes: bytes | None = None
    created_by: str = ""


@dataclass(slots=True)
class ImportActivationStatusCommandDTO:
    pasted_text: str = ""
    file_name: str = ""
    file_bytes: bytes | None = None
    created_by: str = ""


@dataclass(slots=True)
class BackfillOwnerClassTermsCommandDTO:
    owner_userid: str
    class_term_min: int = 1
    class_term_max: int = 5
    dry_run: bool = True
    operator: str = ""
    entry_source: str = ""


@dataclass(slots=True)
class RefreshUserOpsContactTagsCommandDTO:
    external_userid: str = ""
    owner_userid: str = ""
    refresh_scope: str = "external_userid"
    scoped_tag_ids: list[str] = field(default_factory=list)


__all__ = [
    "BackfillOwnerClassTermsCommandDTO",
    "BackfillOwnerClassTermsResultDTO",
    "ExportUserOpsPoolQueryDTO",
    "ExportUserOpsPoolResultDTO",
    "GetUserOpsOverviewQueryDTO",
    "GetUserOpsOverviewResultDTO",
    "ImportActivationStatusCommandDTO",
    "ImportActivationStatusResultDTO",
    "ImportExperienceLeadsCommandDTO",
    "ImportExperienceLeadsResultDTO",
    "ImportMobileClassTermCommandDTO",
    "ImportMobileClassTermResultDTO",
    "LeadPoolFiltersDTO",
    "ListLeadPoolQueryDTO",
    "ListLeadPoolResultDTO",
    "ListUserOpsHistoryQueryDTO",
    "ListUserOpsHistoryResultDTO",
    "RefreshUserOpsContactTagsCommandDTO",
    "RefreshUserOpsContactTagsResultDTO",
    "RunDueUserOpsDeferredJobsCommandDTO",
    "RunDueUserOpsDeferredJobsResultDTO",
    "ScheduleUserOpsAutoAssignClassTermJobCommandDTO",
    "ScheduleUserOpsAutoAssignClassTermJobResultDTO",
    "UpsertLeadPoolMemberCommandDTO",
    "UpsertLeadPoolMemberResultDTO",
    "WriteLeadPoolHistoryCommandDTO",
    "WriteLeadPoolHistoryResultDTO",
]
