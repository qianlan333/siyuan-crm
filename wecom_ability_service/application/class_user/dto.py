from __future__ import annotations

from dataclasses import dataclass
from typing import Any


GetClassUserStatusDefinitionResultDTO = dict[str, Any] | None
GetClassUserStatusCurrentResultDTO = dict[str, Any] | None
GetClassUserSnapshotResultDTO = dict[str, str]
ListClassUserStatusHistoryResultDTO = dict[str, Any]
ListClassUserManagementRecordsResultDTO = dict[str, Any]
ExportClassUserManagementRecordsResultDTO = dict[str, Any]
ApplyClassUserStatusChangeResultDTO = dict[str, Any]
ClearClassUserStatusCurrentResultDTO = None
UpdateClassUserStatusSyncResultResultDTO = None
MigrateClassUserStatusFromContactTagsResultDTO = dict[str, Any]


@dataclass(slots=True)
class GetClassUserStatusDefinitionQueryDTO:
    signup_status: str


@dataclass(slots=True)
class GetClassUserStatusCurrentQueryDTO:
    external_userid: str


@dataclass(slots=True)
class GetClassUserSnapshotQueryDTO:
    external_userid: str
    owner_userid: str = ""


@dataclass(slots=True)
class ListClassUserStatusHistoryQueryDTO:
    limit: int = 100


@dataclass(slots=True)
class ListClassUserManagementRecordsQueryDTO:
    signup_status: str = ""


@dataclass(slots=True)
class ExportClassUserManagementRecordsQueryDTO:
    signup_status: str = ""


@dataclass(slots=True)
class ApplyClassUserStatusChangeCommandDTO:
    external_userid: str
    signup_status: str
    set_by_userid: str
    customer_name_snapshot: str
    owner_userid_snapshot: str
    mobile_snapshot: str


@dataclass(slots=True)
class ClearClassUserStatusCurrentCommandDTO:
    external_userid: str
    set_by_userid: str
    customer_name_snapshot: str
    owner_userid_snapshot: str
    mobile_snapshot: str


@dataclass(slots=True)
class UpdateClassUserStatusSyncResultCommandDTO:
    external_userid: str
    wecom_tag_sync_status: str
    wecom_tag_sync_error: str = ""


@dataclass(slots=True)
class MigrateClassUserStatusFromContactTagsCommandDTO:
    pass


__all__ = [
    "ApplyClassUserStatusChangeCommandDTO",
    "ApplyClassUserStatusChangeResultDTO",
    "ClearClassUserStatusCurrentCommandDTO",
    "ClearClassUserStatusCurrentResultDTO",
    "ExportClassUserManagementRecordsQueryDTO",
    "ExportClassUserManagementRecordsResultDTO",
    "GetClassUserSnapshotQueryDTO",
    "GetClassUserSnapshotResultDTO",
    "GetClassUserStatusCurrentQueryDTO",
    "GetClassUserStatusCurrentResultDTO",
    "GetClassUserStatusDefinitionQueryDTO",
    "GetClassUserStatusDefinitionResultDTO",
    "ListClassUserManagementRecordsQueryDTO",
    "ListClassUserManagementRecordsResultDTO",
    "ListClassUserStatusHistoryQueryDTO",
    "ListClassUserStatusHistoryResultDTO",
    "MigrateClassUserStatusFromContactTagsCommandDTO",
    "MigrateClassUserStatusFromContactTagsResultDTO",
    "UpdateClassUserStatusSyncResultCommandDTO",
    "UpdateClassUserStatusSyncResultResultDTO",
]
