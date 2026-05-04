from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


ResolvePersonIdentityResultDTO = dict[str, Any]
GetContactBindingStatusResultDTO = dict[str, Any]
ResolveExternalContactIdentityResultDTO = dict[str, Any] | None
CountExternalContactIdentityMapsResultDTO = int
GetPrimaryFollowUserUseridResultDTO = str
BindExternalContactIdentityResultDTO = dict[str, Any] | None
UpsertExternalContactIdentityResultDTO = int
ReplaceFollowUsersResultDTO = None
RefreshExternalContactIdentityOwnerResultDTO = None
MarkExternalContactIdentityStatusResultDTO = None
MarkExternalContactFollowUserStatusResultDTO = None


@dataclass(slots=True)
class ResolvePersonIdentityQueryDTO:
    external_userid: str = ""
    mobile: str = ""
    unionid: str = ""
    corp_id: str = ""


@dataclass(slots=True)
class GetContactBindingStatusQueryDTO:
    external_userid: str
    owner_userid: str = ""


@dataclass(slots=True)
class ResolveExternalContactIdentityQueryDTO:
    corp_id: str = ""
    unionid: str = ""
    openid: str = ""
    external_userid: str = ""


@dataclass(slots=True)
class CountExternalContactIdentityMapsQueryDTO:
    pass


@dataclass(slots=True)
class GetPrimaryFollowUserUseridQueryDTO:
    external_userid: str
    corp_id: str = ""


@dataclass(slots=True)
class BindExternalContactIdentityCommandDTO:
    external_userid: str
    mobile: str = ""
    openid: str = ""
    unionid: str = ""
    owner_userid: str = ""
    bind_by_userid: str = ""
    force_rebind: bool = False
    corp_id: str = ""


@dataclass(slots=True)
class UpsertExternalContactIdentityCommandDTO:
    record: dict[str, Any]


@dataclass(slots=True)
class ReplaceFollowUsersCommandDTO:
    corp_id: str
    external_userid: str
    follow_users: list[dict[str, object]] = field(default_factory=list)
    preferred_userid: str = ""


@dataclass(slots=True)
class RefreshExternalContactIdentityOwnerCommandDTO:
    corp_id: str
    external_userid: str


@dataclass(slots=True)
class MarkExternalContactIdentityStatusCommandDTO:
    corp_id: str
    external_userid: str
    status: str
    follow_user_userid: str = ""


@dataclass(slots=True)
class MarkExternalContactFollowUserStatusCommandDTO:
    corp_id: str
    external_userid: str
    status: str
    user_id: str = ""


__all__ = [
    "BindExternalContactIdentityCommandDTO",
    "BindExternalContactIdentityResultDTO",
    "CountExternalContactIdentityMapsQueryDTO",
    "CountExternalContactIdentityMapsResultDTO",
    "GetContactBindingStatusQueryDTO",
    "GetContactBindingStatusResultDTO",
    "GetPrimaryFollowUserUseridQueryDTO",
    "GetPrimaryFollowUserUseridResultDTO",
    "MarkExternalContactFollowUserStatusCommandDTO",
    "MarkExternalContactFollowUserStatusResultDTO",
    "MarkExternalContactIdentityStatusCommandDTO",
    "MarkExternalContactIdentityStatusResultDTO",
    "RefreshExternalContactIdentityOwnerCommandDTO",
    "RefreshExternalContactIdentityOwnerResultDTO",
    "ReplaceFollowUsersCommandDTO",
    "ReplaceFollowUsersResultDTO",
    "ResolveExternalContactIdentityQueryDTO",
    "ResolveExternalContactIdentityResultDTO",
    "ResolvePersonIdentityQueryDTO",
    "ResolvePersonIdentityResultDTO",
    "UpsertExternalContactIdentityCommandDTO",
    "UpsertExternalContactIdentityResultDTO",
]
