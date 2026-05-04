from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class CustomerTagDTO:
    tag_id: str = ""
    tag_name: str = ""
    userid: str = ""
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CustomerFollowUserDTO:
    userid: str = ""
    remark: str = ""
    description: str = ""
    is_primary: bool = False
    relation_status: str = ""
    add_way: int | None = None
    oper_userid: str = ""
    createtime: int | None = None
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CustomerBindingDTO:
    is_bound: bool = False
    person_id: int | None = None
    mobile: str = ""
    third_party_user_id: str = ""
    first_bound_by_userid: str = ""
    first_owner_userid: str = ""
    last_owner_userid: str = ""
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CustomerIdentityDTO:
    person_id: int | None = None
    unionid: str = ""
    openid: str = ""
    follow_user_userid: str = ""
    status: str = ""
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CustomerClassStatusDTO:
    signup_status: str = ""
    signup_label_name: str = ""
    set_by_userid: str = ""
    set_at: str = ""
    wecom_tag_sync_status: str = ""
    wecom_tag_sync_error: str = ""
    status_flags_json: str = "{}"
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CustomerMarketingSummaryDTO:
    main_stage: str = ""
    sub_stage: str = ""
    segment: str = "unknown"
    hit_count: int = 0
    eligible_for_conversion: bool = False
    last_activation_at: str = ""
    last_conversion_marked_at: str = ""
    last_dispatch_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CustomerListItemDTO:
    external_userid: str = ""
    customer_name: str = ""
    owner_userid: str = ""
    owner_display_name: str = ""
    remark: str = ""
    description: str = ""
    mobile: str = ""
    is_bound: bool = False
    binding_status: str = ""
    follow_user_userids: list[str] = field(default_factory=list)
    tags: list[CustomerTagDTO] = field(default_factory=list)
    class_user_status: CustomerClassStatusDTO = field(default_factory=CustomerClassStatusDTO)
    last_message_at: str = ""
    last_touch_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["tags"] = [item.to_dict() for item in self.tags]
        data["class_user_status"] = self.class_user_status.to_dict()
        data["signup_status"] = self.class_user_status.signup_status
        data["signup_label_name"] = self.class_user_status.signup_label_name
        return data


@dataclass
class CustomerDetailDTO:
    external_userid: str = ""
    customer_name: str = ""
    owner_userid: str = ""
    owner_display_name: str = ""
    remark: str = ""
    description: str = ""
    mobile: str = ""
    is_bound: bool = False
    binding_status: str = ""
    follow_user_userids: list[str] = field(default_factory=list)
    tags: list[CustomerTagDTO] = field(default_factory=list)
    class_user_status: CustomerClassStatusDTO = field(default_factory=CustomerClassStatusDTO)
    last_message_at: str = ""
    last_touch_at: str = ""
    updated_at: str = ""
    follow_users: list[CustomerFollowUserDTO] = field(default_factory=list)
    binding: CustomerBindingDTO = field(default_factory=CustomerBindingDTO)
    identity: CustomerIdentityDTO = field(default_factory=CustomerIdentityDTO)
    marketing_summary: CustomerMarketingSummaryDTO = field(default_factory=CustomerMarketingSummaryDTO)
    marketing_profile: dict[str, Any] = field(default_factory=dict)
    sidebar_context: dict[str, Any] = field(default_factory=dict)
    contact: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["tags"] = [item.to_dict() for item in self.tags]
        data["follow_users"] = [item.to_dict() for item in self.follow_users]
        data["binding"] = self.binding.to_dict()
        data["identity"] = self.identity.to_dict()
        data["class_user_status"] = self.class_user_status.to_dict()
        data["marketing_summary"] = self.marketing_summary.to_dict()
        data["class_status"] = self.class_user_status.to_dict()
        return data
