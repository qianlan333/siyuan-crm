from __future__ import annotations

import json
import os
from copy import deepcopy
from datetime import datetime, timezone
from typing import Protocol

from sqlalchemy import Text, bindparam, cast, delete, func, insert, or_, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from aicrm_next.shared.config import Settings, get_settings
from aicrm_next.shared.db_session import get_session_factory
from aicrm_next.shared.repository_provider import assert_repository_allowed
from aicrm_next.shared.runtime import database_mode
from aicrm_next.shared.typing import JsonDict

from .models import (
    customer_detail_snapshot_next,
    customer_list_index_next,
    customer_recent_message_next,
    customer_timeline_event_next,
)

_DEFAULT_LIVE_SOURCE_LIST_LIMIT = 200


class CustomerReadRepository(Protocol):
    def list_customers(
        self,
        filters: JsonDict | None = None,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[JsonDict]: ...

    def count_customers(self, filters: JsonDict | None = None) -> int: ...

    def get_customer_detail(self, external_userid: str) -> JsonDict | None: ...

    def get_customer(self, external_userid: str) -> JsonDict | None: ...

    def get_customer_timeline(
        self,
        external_userid: str,
        filters: JsonDict | None = None,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[JsonDict]: ...

    def list_timeline(
        self,
        external_userid: str,
        filters: JsonDict | None = None,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[JsonDict]: ...

    def get_recent_messages(self, external_userid: str, *, limit: int | None = None) -> list[JsonDict]: ...

    def list_recent_messages(self, external_userid: str, *, limit: int | None = None) -> list[JsonDict]: ...

    def customer_exists(self, external_userid: str) -> bool: ...


class FixtureCustomerReadRepository:
    """Fixture read repository shaped for the future PostgreSQL projection repo."""

    def __init__(self) -> None:
        self._customers: list[JsonDict] = [
            {
                "person_id": "person_001",
                "external_userid": "wx_ext_001",
                "customer_name": "张小蓝",
                "remark": "小蓝",
                "description": "9.9 试用后关注正式课安排",
                "owner_userid": "ZhaoYanFang",
                "owner_display_name": "赵艳芳",
                "mobile": "13800138000",
                "tags": ["付费意向", "黄小璨", "重点跟进"],
                "class_user_status": {
                    "current_status": "lead_trial",
                    "signup_status": "trial_9_9",
                    "signup_label_name": "9.9 试用",
                    "activation_bucket": "activated",
                    "updated_at": "2026-05-18T10:20:00+08:00",
                },
                "last_message_at": "2026-05-18T10:15:00+08:00",
                "last_touch_at": "2026-05-18T10:20:00+08:00",
                "updated_at": "2026-05-18T10:20:00+08:00",
                "binding": {"is_bound": True, "mobile": "13800138000", "binding_status": "bound"},
                "identity": {"person_id": "person_001", "external_userid": "wx_ext_001", "mobile": "13800138000"},
                "follow_users": [{"userid": "ZhaoYanFang", "display_name": "赵艳芳", "is_primary": True}],
                "marketing_summary": {
                    "main_stage": "trial",
                    "sub_stage": "activated_focus",
                    "value_segment": "high_intent",
                    "last_dispatch_at": "2026-05-18T09:00:00+08:00",
                },
                "marketing_profile": {
                    "stage_key": "trial/activated_focus",
                    "recommended_action": "跟进正式课报名",
                    "signals": ["recent_reply", "high_intent_tag"],
                    "matched_questions": [
                        {
                            "questionnaire_id": "questionnaire_fixture_001",
                            "questionnaire_title": "黄小璨报名问卷",
                            "submission_id": "submission_fixture_001",
                            "submitted_at": "2026-05-18T09:30:00+08:00",
                            "question_id": "q_goal",
                            "question": "孩子当前英语学习目标是什么？",
                            "answer": "希望提升表达自信",
                        }
                    ],
                },
                "contact": {
                    "external_userid": "wx_ext_001",
                    "name": "张小蓝",
                    "remark": "小蓝",
                    "description": "9.9 试用后关注正式课安排",
                },
                "sidebar_context": {
                    "can_open_sidebar": True,
                    "marketing_stage": "activated_focus",
                    "customer_profile_url": "/admin/customers/wx_ext_001",
                },
            },
            {
                "person_id": "person_002",
                "external_userid": "wx_ext_002",
                "customer_name": "李未绑",
                "remark": "未绑手机号客户",
                "description": "已加微但尚未绑定手机号",
                "owner_userid": "LiuXiao",
                "owner_display_name": "刘晓",
                "mobile": None,
                "tags": ["新用户"],
                "class_user_status": {
                    "current_status": "new_user",
                    "signup_status": "",
                    "signup_label_name": "",
                    "activation_bucket": "pending_input",
                    "updated_at": "2026-05-17T18:05:00+08:00",
                },
                "last_message_at": "2026-05-17T18:00:00+08:00",
                "last_touch_at": "2026-05-17T18:05:00+08:00",
                "updated_at": "2026-05-17T18:05:00+08:00",
                "binding": {"is_bound": False, "mobile": None, "binding_status": "unbound"},
                "identity": {"person_id": "person_002", "external_userid": "wx_ext_002", "mobile": None},
                "follow_users": [{"userid": "LiuXiao", "display_name": "刘晓", "is_primary": True}],
                "marketing_summary": {"main_stage": "new_user", "sub_stage": "pending_input", "value_segment": "unknown"},
                "marketing_profile": {
                    "stage_key": "new_user/pending_input",
                    "recommended_action": "补录手机号和激活状态",
                    "signals": ["missing_mobile"],
                },
                "contact": {
                    "external_userid": "wx_ext_002",
                    "name": "李未绑",
                    "remark": "未绑手机号客户",
                    "description": "已加微但尚未绑定手机号",
                },
                "sidebar_context": {
                    "can_open_sidebar": True,
                    "marketing_stage": "new_user",
                    "customer_profile_url": "/admin/customers/wx_ext_002",
                },
            },
            {
                "person_id": "person_003",
                "external_userid": "",
                "customer_name": "王缺失",
                "remark": "缺外部联系人",
                "description": "导入线索，尚未形成 external_userid",
                "owner_userid": "",
                "owner_display_name": "",
                "mobile": "13900139000",
                "tags": ["导入线索"],
                "class_user_status": {
                    "current_status": "lead_imported",
                    "signup_status": "",
                    "signup_label_name": "导入线索",
                    "activation_bucket": "not_activated",
                    "updated_at": "2026-05-16T12:00:00+08:00",
                },
                "last_message_at": None,
                "last_touch_at": None,
                "updated_at": "2026-05-16T12:00:00+08:00",
                "binding": {"is_bound": True, "mobile": "13900139000", "binding_status": "bound_no_external_userid"},
                "identity": {"person_id": "person_003", "external_userid": "", "mobile": "13900139000"},
                "follow_users": [],
                "marketing_summary": {"main_stage": "lead", "sub_stage": "imported", "value_segment": "unknown"},
                "marketing_profile": {"stage_key": "lead/imported", "recommended_action": "等待加微", "signals": []},
                "contact": {"external_userid": "", "name": "王缺失", "remark": "缺外部联系人", "description": "导入线索"},
                "sidebar_context": {"can_open_sidebar": False, "marketing_stage": "lead_imported"},
            },
            {
                "person_id": "person_004",
                "external_userid": "wx_ext_004",
                "customer_name": "陈复访",
                "remark": "复访客户",
                "description": "黄小璨未激活，需要再次触达",
                "owner_userid": "ZhaoYanFang",
                "owner_display_name": "赵艳芳",
                "mobile": "13700137000",
                "tags": ["黄小璨", "复访"],
                "class_user_status": {
                    "current_status": "followup",
                    "signup_status": "",
                    "signup_label_name": "复访",
                    "activation_bucket": "not_activated",
                    "updated_at": "2026-05-15T11:30:00+08:00",
                },
                "last_message_at": "2026-05-15T11:10:00+08:00",
                "last_touch_at": "2026-05-15T11:30:00+08:00",
                "updated_at": "2026-05-15T11:30:00+08:00",
                "binding": {"is_bound": True, "mobile": "13700137000", "binding_status": "bound"},
                "identity": {"person_id": "person_004", "external_userid": "wx_ext_004", "mobile": "13700137000"},
                "follow_users": [{"userid": "ZhaoYanFang", "display_name": "赵艳芳", "is_primary": True}],
                "marketing_summary": {"main_stage": "followup", "sub_stage": "not_activated", "value_segment": "medium"},
                "marketing_profile": {
                    "stage_key": "followup/not_activated",
                    "recommended_action": "发送激活提醒",
                    "signals": ["not_activated"],
                },
                "contact": {
                    "external_userid": "wx_ext_004",
                    "name": "陈复访",
                    "remark": "复访客户",
                    "description": "黄小璨未激活，需要再次触达",
                },
                "sidebar_context": {
                    "can_open_sidebar": True,
                    "marketing_stage": "followup",
                    "customer_profile_url": "/admin/customers/wx_ext_004",
                },
            },
            {
                "person_id": "person_masked_001",
                "external_userid": "external_user_masked_001",
                "customer_name": "customer_masked_001",
                "remark": "remark_masked_001",
                "description": "description_masked_001",
                "owner_userid": "owner_masked_001",
                "owner_display_name": "owner_masked_display_001",
                "mobile": "mobile_masked_001",
                "tags": [],
                "class_user_status": {
                    "current_status": "activated",
                    "signup_status": "activated",
                    "signup_label_name": "tag_masked_001",
                    "activation_bucket": "activated",
                    "updated_at": "2026-05-20T08:43:12+00:00",
                    "wecom_tag_sync_status": "skipped_fake_seed",
                    "wecom_tag_sync_error": "",
                },
                "last_message_at": "2026-05-20T08:43:12+00:00",
                "last_touch_at": "2026-05-20T08:43:12+00:00",
                "updated_at": "2026-05-20T08:43:12+00:00",
                "binding": {
                    "is_bound": True,
                    "person_id": 1,
                    "mobile": "mobile_masked_001",
                    "binding_status": "bound",
                    "third_party_user_id": "third_party_user_masked_001",
                },
                "identity": {
                    "person_id": 1,
                    "external_userid": "external_user_masked_001",
                    "mobile": "mobile_masked_001",
                    "unionid": "unionid_masked_001",
                    "openid": "openid_masked_001",
                    "status": "active",
                },
                "follow_users": [{"userid": "owner_masked_001", "display_name": "owner_masked_display_001", "is_primary": True}],
                "marketing_summary": {"main_stage": "activated", "sub_stage": "masked_sample", "value_segment": "fixture"},
                "marketing_profile": {
                    "stage_key": "activated/masked_sample",
                    "recommended_action": "masked sample only",
                    "signals": ["masked_sample"],
                },
                "contact": {
                    "external_userid": "external_user_masked_001",
                    "name": "customer_masked_001",
                    "remark": "remark_masked_001",
                    "description": "description_masked_001",
                },
                "sidebar_context": {
                    "can_open_sidebar": True,
                    "marketing_stage": "activated",
                    "customer_profile_url": "/admin/customers/external_user_masked_001",
                },
            },
        ]
        self._timeline: dict[str, list[JsonDict]] = {
            "wx_ext_001": [
                {
                    "event_id": "evt_001",
                    "event_type": "message",
                    "event_time": "2026-05-18T10:15:00+08:00",
                    "title": "客户发送新消息",
                    "summary": "想了解 9.9 试用后的正式课安排。",
                    "source_table": "archive_messages",
                    "source_id": "msg_001",
                    "metadata": {"msgtype": "text", "owner_userid": "ZhaoYanFang"},
                },
                {
                    "event_id": "evt_002",
                    "event_type": "tag",
                    "event_time": "2026-05-18T10:20:00+08:00",
                    "title": "标签更新",
                    "summary": "新增重点跟进标签。",
                    "source_table": "contact_tags",
                    "source_id": "tag_evt_001",
                    "metadata": {"tags": ["重点跟进"]},
                },
            ],
            "wx_ext_002": [
                {
                    "event_id": "evt_003",
                    "event_type": "contact_added",
                    "event_time": "2026-05-17T18:00:00+08:00",
                    "title": "客户已加微",
                    "summary": "客户进入新用户池，尚未绑定手机号。",
                    "source_table": "contacts",
                    "source_id": "wx_ext_002",
                    "metadata": {"binding_status": "unbound"},
                }
            ],
            "wx_ext_004": [
                {
                    "event_id": "evt_004",
                    "event_type": "message",
                    "event_time": "2026-05-15T11:10:00+08:00",
                    "title": "客户回复复访消息",
                    "summary": "客户询问激活入口是否还有效。",
                    "source_table": "archive_messages",
                    "source_id": "msg_004",
                    "metadata": {"msgtype": "text", "owner_userid": "ZhaoYanFang"},
                }
            ],
            "external_user_masked_001": [
                {
                    "event_id": "message:masked_001",
                    "event_type": "message",
                    "event_time": "2026-05-20T08:43:12+00:00",
                    "title": "消息 · text",
                    "summary": "masked message content 001",
                    "source_table": "archived_messages",
                    "source_id": "msg_masked_001",
                    "metadata": {"msgtype": "text", "owner_userid": "owner_masked_001"},
                },
                {
                    "event_id": "status_change:masked_001",
                    "event_type": "status_change",
                    "event_time": "2026-05-20T08:43:12+00:00",
                    "title": "状态变更",
                    "summary": "- -> activated",
                    "source_table": "class_user_status_history",
                    "source_id": "status_masked_001",
                    "metadata": {"signup_label_name": "tag_masked_001"},
                },
            ],
        }
        self._messages: dict[str, list[JsonDict]] = {
            "wx_ext_001": [
                {
                    "msgid": "msg_001",
                    "msgtype": "text",
                    "content": "我想了解正式课怎么报名",
                    "send_time": "2026-05-18T10:15:00+08:00",
                    "external_userid": "wx_ext_001",
                    "chat_type": "single",
                    "owner_userid": "ZhaoYanFang",
                    "sender": "customer",
                },
                {
                    "msgid": "msg_002",
                    "msgtype": "text",
                    "content": "老师什么时候方便介绍一下",
                    "send_time": "2026-05-18T10:10:00+08:00",
                    "external_userid": "wx_ext_001",
                    "chat_type": "single",
                    "owner_userid": "ZhaoYanFang",
                    "sender": "customer",
                }
            ],
            "wx_ext_002": [],
            "wx_ext_004": [
                {
                    "msgid": "msg_004",
                    "msgtype": "text",
                    "content": "激活入口还有效吗",
                    "send_time": "2026-05-15T11:10:00+08:00",
                    "external_userid": "wx_ext_004",
                    "chat_type": "single",
                    "owner_userid": "ZhaoYanFang",
                    "sender": "customer",
                }
            ],
            "external_user_masked_001": [
                {
                    "msgid": "msg_masked_001",
                    "msgtype": "text",
                    "content": "masked message content 001",
                    "send_time": "2026-05-20T08:43:12+00:00",
                    "external_userid": "external_user_masked_001",
                    "chat_type": "single",
                    "owner_userid": "owner_masked_001",
                    "sender": "customer",
                }
            ],
        }

    def list_customers(
        self,
        filters: JsonDict | None = None,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[JsonDict]:
        rows = _apply_customer_filters([deepcopy(item) for item in self._customers], filters or {})
        return _apply_page(rows, limit=limit, offset=offset)

    def count_customers(self, filters: JsonDict | None = None) -> int:
        return len(_apply_customer_filters([deepcopy(item) for item in self._customers], filters or {}))

    def replace_all(
        self,
        *,
        customers: list[JsonDict],
        timeline_by_external_userid: dict[str, list[JsonDict]] | None = None,
        messages_by_external_userid: dict[str, list[JsonDict]] | None = None,
    ) -> None:
        self._customers = [deepcopy(item) for item in customers]
        self._timeline = {
            str(external_userid): [deepcopy(item) for item in items]
            for external_userid, items in (timeline_by_external_userid or {}).items()
        }
        self._messages = {
            str(external_userid): [deepcopy(item) for item in items]
            for external_userid, items in (messages_by_external_userid or {}).items()
        }

    seed = replace_all

    def get_customer(self, external_userid: str) -> JsonDict | None:
        item = next((item for item in self._customers if item.get("external_userid") == external_userid), None)
        return deepcopy(item) if item else None

    get_customer_detail = get_customer

    def list_timeline(
        self,
        external_userid: str,
        filters: JsonDict | None = None,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[JsonDict]:
        rows = [deepcopy(item) for item in self._timeline.get(external_userid, [])]
        event_type = str((filters or {}).get("event_type") or "").strip()
        if event_type:
            rows = [item for item in rows if item.get("event_type") == event_type]
        return _apply_page(rows, limit=limit, offset=offset)

    get_customer_timeline = list_timeline

    def list_recent_messages(self, external_userid: str, *, limit: int | None = None) -> list[JsonDict]:
        return _apply_page([deepcopy(item) for item in self._messages.get(external_userid, [])], limit=limit, offset=0)

    get_recent_messages = list_recent_messages

    def customer_exists(self, external_userid: str) -> bool:
        return self.get_customer(external_userid) is not None


class SqlAlchemyCustomerReadModelRepository:
    """PostgreSQL-ready Customer Read Model repository backed by SQLAlchemy Core tables."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def close(self) -> None:
        try:
            self._session.rollback()
        finally:
            self._session.close()

    def reset(self) -> None:
        self.clear()
        self.seed_from_fixture()
        self._session.commit()

    def clear(self) -> None:
        self._session.execute(delete(customer_recent_message_next))
        self._session.execute(delete(customer_timeline_event_next))
        self._session.execute(delete(customer_detail_snapshot_next))
        self._session.execute(delete(customer_list_index_next))

    def replace_all(
        self,
        *,
        customers: list[JsonDict],
        timeline_by_external_userid: dict[str, list[JsonDict]] | None = None,
        messages_by_external_userid: dict[str, list[JsonDict]] | None = None,
    ) -> None:
        self.clear()
        self.seed(
            customers=customers,
            timeline_by_external_userid=timeline_by_external_userid,
            messages_by_external_userid=messages_by_external_userid,
        )
        self._session.commit()

    def seed_from_fixture(self, fixture: FixtureCustomerReadRepository | None = None) -> None:
        fixture = fixture or FixtureCustomerReadRepository()
        self.seed(
            customers=fixture.list_customers(),
            timeline_by_external_userid={row["external_userid"]: fixture.list_timeline(row["external_userid"]) for row in fixture.list_customers() if row.get("external_userid")},
            messages_by_external_userid={row["external_userid"]: fixture.list_recent_messages(row["external_userid"]) for row in fixture.list_customers() if row.get("external_userid")},
        )

    def seed(
        self,
        *,
        customers: list[JsonDict],
        timeline_by_external_userid: dict[str, list[JsonDict]] | None = None,
        messages_by_external_userid: dict[str, list[JsonDict]] | None = None,
    ) -> None:
        timeline_by_external_userid = timeline_by_external_userid or {}
        messages_by_external_userid = messages_by_external_userid or {}
        for index, customer in enumerate(customers, start=1):
            external_userid = str(customer.get("external_userid") or "")
            created_at = _coerce_datetime(customer.get("created_at") or customer.get("updated_at"))
            updated_at = _coerce_datetime(customer.get("updated_at"))
            binding = dict(customer.get("binding") or {})
            self._session.execute(
                insert(customer_list_index_next).values(
                    id=index,
                    person_id=customer.get("person_id") or "",
                    external_userid=external_userid,
                    customer_name=customer.get("customer_name") or "",
                    owner_userid=customer.get("owner_userid") or "",
                    owner_display_name=customer.get("owner_display_name") or "",
                    remark=customer.get("remark") or "",
                    description=customer.get("description") or "",
                    mobile=customer.get("mobile") or "",
                    is_bound=bool(binding.get("is_bound")),
                    binding_status=binding.get("binding_status") or customer.get("binding_status") or "unbound",
                    tags_json=list(customer.get("tags") or []),
                    class_user_status_json=dict(customer.get("class_user_status") or {}),
                    last_message_at=_coerce_optional_datetime(customer.get("last_message_at")),
                    last_touch_at=_coerce_optional_datetime(customer.get("last_touch_at")),
                    updated_at=updated_at,
                    created_at=created_at,
                )
            )
            self._session.execute(
                insert(customer_detail_snapshot_next).values(
                    id=index,
                    person_id=customer.get("person_id") or "",
                    external_userid=external_userid,
                    customer_json=dict(customer),
                    binding_json=dict(customer.get("binding") or {}),
                    identity_json=dict(customer.get("identity") or {}),
                    follow_users_json=list(customer.get("follow_users") or []),
                    marketing_summary_json=dict(customer.get("marketing_summary") or {}),
                    marketing_profile_json=dict(customer.get("marketing_profile") or {}),
                    contact_json=dict(customer.get("contact") or {}),
                    sidebar_context_json=dict(customer.get("sidebar_context") or {}),
                    updated_at=updated_at,
                    created_at=created_at,
                )
            )
            for event_index, item in enumerate(timeline_by_external_userid.get(external_userid, []), start=1):
                self._session.execute(
                    insert(customer_timeline_event_next).values(
                        id=index * 1000 + event_index,
                        event_id=item.get("event_id") or f"evt_{index}_{event_index}",
                        person_id=customer.get("person_id") or "",
                        external_userid=external_userid,
                        event_type=item.get("event_type") or "",
                        event_time=_coerce_datetime(item.get("event_time")),
                        title=item.get("title") or "",
                        summary=item.get("summary") or "",
                        source_table=item.get("source_table") or "",
                        source_id=item.get("source_id") or "",
                        metadata_json=dict(item.get("metadata") or {}),
                        created_at=created_at,
                    )
                )
            for message_index, item in enumerate(messages_by_external_userid.get(external_userid, []), start=1):
                metadata = {key: value for key, value in item.items() if key not in {"msgid", "external_userid", "msgtype", "content", "send_time", "owner_userid", "chat_type"}}
                self._session.execute(
                    insert(customer_recent_message_next).values(
                        id=index * 1000 + message_index,
                        msgid=item.get("msgid") or f"msg_{index}_{message_index}",
                        external_userid=external_userid,
                        msgtype=item.get("msgtype") or "text",
                        content=item.get("content") or "",
                        send_time=_coerce_datetime(item.get("send_time")),
                        owner_userid=item.get("owner_userid") or "",
                        chat_type=item.get("chat_type") or "single",
                        metadata_json=metadata,
                        created_at=created_at,
                    )
                )

    def list_customers(
        self,
        filters: JsonDict | None = None,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[JsonDict]:
        stmt = self._customer_list_stmt(filters or {})
        stmt = stmt.order_by(customer_list_index_next.c.id.asc())
        if limit is not None:
            stmt = stmt.limit(max(1, int(limit))).offset(max(0, int(offset or 0)))
        elif offset:
            stmt = stmt.offset(max(0, int(offset or 0)))
        rows = self._session.execute(stmt).mappings()
        customers = [self._list_row_to_customer(row) for row in rows]
        return customers

    def count_customers(self, filters: JsonDict | None = None) -> int:
        stmt = select(func.count()).select_from(self._customer_list_stmt(filters or {}).subquery())
        return int(self._session.execute(stmt).scalar_one() or 0)

    def get_customer(self, external_userid: str) -> JsonDict | None:
        row = self._session.execute(
            select(customer_detail_snapshot_next)
            .where(customer_detail_snapshot_next.c.external_userid == external_userid)
            .limit(1)
        ).mappings().first()
        if not row:
            return None
        customer = dict(row["customer_json"] or {})
        customer.update(
            {
                "binding": dict(row["binding_json"] or {}),
                "identity": dict(row["identity_json"] or {}),
                "follow_users": list(row["follow_users_json"] or []),
                "marketing_summary": dict(row["marketing_summary_json"] or {}),
                "marketing_profile": dict(row["marketing_profile_json"] or {}),
                "contact": dict(row["contact_json"] or {}),
                "sidebar_context": dict(row["sidebar_context_json"] or {}),
                "updated_at": _iso(customer.get("updated_at") or row["updated_at"]),
            }
        )
        return customer

    get_customer_detail = get_customer

    def list_timeline(
        self,
        external_userid: str,
        filters: JsonDict | None = None,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[JsonDict]:
        stmt = select(customer_timeline_event_next).where(customer_timeline_event_next.c.external_userid == external_userid)
        event_type = str((filters or {}).get("event_type") or "").strip()
        if event_type:
            stmt = stmt.where(customer_timeline_event_next.c.event_type == event_type)
        stmt = stmt.order_by(customer_timeline_event_next.c.id.asc())
        rows = [self._timeline_row_to_dict(row) for row in self._session.execute(stmt).mappings()]
        return _apply_page(rows, limit=limit, offset=offset)

    get_customer_timeline = list_timeline

    def list_recent_messages(self, external_userid: str, *, limit: int | None = None) -> list[JsonDict]:
        stmt = (
            select(customer_recent_message_next)
            .where(customer_recent_message_next.c.external_userid == external_userid)
            .order_by(customer_recent_message_next.c.send_time.desc(), customer_recent_message_next.c.id.asc())
        )
        rows = [self._message_row_to_dict(row) for row in self._session.execute(stmt).mappings()]
        return _apply_page(rows, limit=limit, offset=0)

    get_recent_messages = list_recent_messages

    def customer_exists(self, external_userid: str) -> bool:
        return self.get_customer(external_userid) is not None

    def _customer_list_stmt(self, filters: JsonDict):
        stmt = select(customer_list_index_next)
        table = customer_list_index_next.c
        owner_userid = str(filters.get("owner_userid") or "").strip()
        if owner_userid:
            stmt = stmt.where(table.owner_userid == owner_userid)
        tag = str(filters.get("tag") or "").strip()
        if tag:
            stmt = stmt.where(cast(table.tags_json, Text).like(f"%{tag}%"))
        status = str(filters.get("status") or "").strip()
        if status:
            stmt = stmt.where(
                or_(
                    table.binding_status == status,
                    cast(table.class_user_status_json, Text).like(f"%{status}%"),
                )
            )
        is_bound = _normalize_bool_filter(filters.get("is_bound"))
        if is_bound is not None:
            stmt = stmt.where(table.is_bound.is_(is_bound))
        mobile = str(filters.get("mobile") or "").strip()
        if mobile:
            stmt = stmt.where(table.mobile.like(f"%{mobile}%"))
        keyword = str(filters.get("keyword") or "").strip().lower()
        if keyword:
            pattern = f"%{keyword}%"
            stmt = stmt.where(
                or_(
                    func.lower(table.external_userid).like(pattern),
                    func.lower(table.customer_name).like(pattern),
                    func.lower(table.owner_userid).like(pattern),
                    func.lower(table.owner_display_name).like(pattern),
                    func.lower(table.remark).like(pattern),
                    func.lower(table.description).like(pattern),
                    func.lower(table.mobile).like(pattern),
                    func.lower(table.binding_status).like(pattern),
                    func.lower(cast(table.tags_json, Text)).like(pattern),
                    func.lower(cast(table.class_user_status_json, Text)).like(pattern),
                )
            )
        return stmt

    def _list_row_to_customer(self, row) -> JsonDict:
        data = dict(row)
        return {
            "person_id": data.get("person_id") or "",
            "external_userid": data.get("external_userid") or "",
            "customer_name": data.get("customer_name") or "",
            "remark": data.get("remark") or "",
            "description": data.get("description") or "",
            "owner_userid": data.get("owner_userid") or "",
            "owner_display_name": data.get("owner_display_name") or "",
            "mobile": data.get("mobile") or None,
            "tags": list(data.get("tags_json") or []),
            "class_user_status": dict(data.get("class_user_status_json") or {}),
            "last_message_at": _iso(data.get("last_message_at")),
            "last_touch_at": _iso(data.get("last_touch_at")),
            "updated_at": _iso(data.get("updated_at")),
            "created_at": _iso(data.get("created_at")),
            "binding": {
                "is_bound": bool(data.get("is_bound")),
                "mobile": data.get("mobile") or None,
                "binding_status": data.get("binding_status") or "unbound",
            },
        }

    def _timeline_row_to_dict(self, row) -> JsonDict:
        data = dict(row)
        return {
            "event_id": data.get("event_id") or "",
            "event_type": data.get("event_type") or "",
            "event_time": _iso(data.get("event_time")),
            "title": data.get("title") or "",
            "summary": data.get("summary") or "",
            "source_table": data.get("source_table") or "",
            "source_id": data.get("source_id") or "",
            "metadata": dict(data.get("metadata_json") or {}),
        }

    def _message_row_to_dict(self, row) -> JsonDict:
        data = dict(row)
        payload = {
            "msgid": data.get("msgid") or "",
            "msgtype": data.get("msgtype") or "text",
            "content": data.get("content") or "",
            "send_time": _iso(data.get("send_time")),
            "external_userid": data.get("external_userid") or "",
            "owner_userid": data.get("owner_userid") or "",
            "chat_type": data.get("chat_type") or "single",
        }
        payload.update(dict(data.get("metadata_json") or {}))
        return payload


class LiveSourceCustomerReadRepository:
    """Read live customer data from production source tables when projections are not ready."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def close(self) -> None:
        try:
            self._session.rollback()
        finally:
            self._session.close()

    def list_customers(
        self,
        filters: JsonDict | None = None,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[JsonDict]:
        rows = self._customer_rows(filters or {}, limit=limit, offset=offset)
        return self._decorate_customer_rows(rows)

    def count_customers(self, filters: JsonDict | None = None) -> int:
        where, params = self._customer_where(filters or {})
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        sql = self._customer_decorated_sql(where_sql, "COUNT(*) AS total")
        return int(self._session.execute(text(sql), params).scalar_one() or 0)

    def get_customer(self, external_userid: str) -> JsonDict | None:
        rows = self._customer_rows({"external_userid": str(external_userid or "").strip()}, limit=1, offset=0)
        customers = self._decorate_customer_rows(rows)
        return customers[0] if customers else None

    get_customer_detail = get_customer

    def list_timeline(
        self,
        external_userid: str,
        filters: JsonDict | None = None,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[JsonDict]:
        event_type = str((filters or {}).get("event_type") or "").strip()
        messages = [
            {
                "event_id": f"message:{item.get('source_id') or item.get('msgid')}",
                "event_type": "message",
                "event_time": item.get("send_time"),
                "title": f"消息 · {item.get('msgtype') or 'unknown'}",
                "summary": item.get("content") or "",
                "source_table": "archived_messages",
                "source_id": str(item.get("source_id") or ""),
                "metadata": dict(item),
            }
            for item in self.list_recent_messages(external_userid, limit=(limit or 50) + offset)
        ]
        if event_type:
            messages = [item for item in messages if item.get("event_type") == event_type]
        return _apply_page(messages, limit=limit, offset=offset)

    get_customer_timeline = list_timeline

    def list_recent_messages(self, external_userid: str, *, limit: int | None = None) -> list[JsonDict]:
        rows = self._session.execute(
            text(
                """
                SELECT id, msgid, chat_type, external_userid, owner_userid, sender, receiver,
                       msgtype, content, send_time, raw_payload, created_at
                FROM archived_messages
                WHERE external_userid = :external_userid
                ORDER BY send_time DESC, id DESC
                LIMIT :limit
                """
            ),
            {"external_userid": str(external_userid or "").strip(), "limit": max(1, int(limit or 20))},
        ).mappings()
        return [
            {
                "msgid": row.get("msgid") or "",
                "external_userid": row.get("external_userid") or "",
                "msgtype": row.get("msgtype") or "text",
                "content": row.get("content") or "",
                "send_time": _iso(row.get("send_time")),
                "owner_userid": row.get("owner_userid") or "",
                "chat_type": row.get("chat_type") or "single",
                "sender": row.get("sender") or "",
                "receiver": row.get("receiver") or "",
                "source_id": str(row.get("id") or ""),
                "raw_payload": row.get("raw_payload") or "",
            }
            for row in rows
        ]

    get_recent_messages = list_recent_messages

    def customer_exists(self, external_userid: str) -> bool:
        return self.get_customer(external_userid) is not None

    def _customer_rows(self, filters: JsonDict, *, limit: int | None, offset: int) -> list[JsonDict]:
        where, params = self._customer_where(filters)
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        sql = self._customer_decorated_sql(where_sql, "*") + """
            ORDER BY sort_updated_at DESC, external_userid DESC
            LIMIT :limit OFFSET :offset
        """
        effective_limit = _DEFAULT_LIVE_SOURCE_LIST_LIMIT if limit is None else int(limit)
        params.update({"limit": max(1, effective_limit), "offset": max(0, int(offset or 0))})
        return [dict(row) for row in self._session.execute(text(sql), params).mappings()]

    def _customer_decorated_sql(self, where_sql: str, select_sql: str) -> str:
        return f"""
            WITH scope AS (
                SELECT external_userid FROM contacts
                UNION
                SELECT external_userid FROM external_contact_bindings
                UNION
                SELECT external_userid FROM wecom_external_contact_identity_map
                UNION
                SELECT external_userid FROM wecom_external_contact_follow_users
                UNION
                SELECT external_userid FROM contact_tags
                UNION
                SELECT external_userid FROM class_user_status_current
                UNION
                SELECT external_userid FROM archived_messages
            ),
            latest_messages AS (
                SELECT external_userid, MAX(send_time) AS last_message_at
                FROM archived_messages
                WHERE external_userid IS NOT NULL AND external_userid <> ''
                GROUP BY external_userid
            ),
            decorated AS (
                SELECT
                    scope.external_userid,
                    COALESCE(
                        NULLIF(class_status.owner_userid_snapshot, ''),
                        NULLIF(contact.owner_userid, ''),
                        NULLIF(binding.last_owner_userid, ''),
                        NULLIF(binding.first_owner_userid, ''),
                        NULLIF((
                            SELECT identity.follow_user_userid
                            FROM wecom_external_contact_identity_map identity
                            WHERE identity.external_userid = scope.external_userid
                              AND identity.follow_user_userid IS NOT NULL
                              AND identity.follow_user_userid <> ''
                            ORDER BY identity.updated_at DESC, identity.id DESC
                            LIMIT 1
                        ), ''),
                        NULLIF((
                            SELECT follow_user.user_id
                            FROM wecom_external_contact_follow_users follow_user
                            WHERE follow_user.external_userid = scope.external_userid
                              AND follow_user.user_id IS NOT NULL
                              AND follow_user.user_id <> ''
                            ORDER BY follow_user.is_primary DESC, follow_user.updated_at DESC, follow_user.id DESC
                            LIMIT 1
                        ), ''),
                        ''
                    ) AS owner_userid,
                    COALESCE(
                        NULLIF(class_status.customer_name_snapshot, ''),
                        NULLIF(contact.customer_name, ''),
                        NULLIF((
                            SELECT identity.name
                            FROM wecom_external_contact_identity_map identity
                            WHERE identity.external_userid = scope.external_userid
                              AND identity.name IS NOT NULL
                              AND identity.name <> ''
                            ORDER BY identity.updated_at DESC, identity.id DESC
                            LIMIT 1
                        ), ''),
                        scope.external_userid
                    ) AS customer_name,
                    COALESCE(NULLIF(people.mobile, ''), NULLIF(class_status.mobile_snapshot, ''), '') AS mobile,
                    COALESCE(contact.remark, '') AS remark,
                    COALESCE(contact.description, '') AS description,
                    COALESCE(class_status.signup_status, '') AS signup_status,
                    COALESCE(class_status.signup_label_name, '') AS signup_label_name,
                    COALESCE(CAST(class_status.status_flags_json AS TEXT), '{{}}') AS status_flags_json,
                    CASE WHEN binding.external_userid IS NULL THEN 0 ELSE 1 END AS is_bound,
                    binding.person_id AS person_id,
                    people.third_party_user_id AS third_party_user_id,
                    contact.updated_at AS contact_updated_at,
                    binding.updated_at AS binding_updated_at,
                    class_status.updated_at AS class_status_updated_at,
                    latest_messages.last_message_at AS last_message_at,
                    COALESCE(
                        CAST(class_status.updated_at AS TEXT),
                        CAST(contact.updated_at AS TEXT),
                        CAST(binding.updated_at AS TEXT),
                        latest_messages.last_message_at,
                        ''
                    ) AS sort_updated_at
                FROM scope
                LEFT JOIN contacts contact ON contact.external_userid = scope.external_userid
                LEFT JOIN external_contact_bindings binding ON binding.external_userid = scope.external_userid
                LEFT JOIN people people ON people.id = binding.person_id
                LEFT JOIN class_user_status_current class_status ON class_status.external_userid = scope.external_userid
                LEFT JOIN latest_messages ON latest_messages.external_userid = scope.external_userid
                WHERE scope.external_userid IS NOT NULL AND scope.external_userid <> ''
            )
            SELECT {select_sql}
            FROM decorated
            {where_sql}
        """

    def _customer_where(self, filters: JsonDict) -> tuple[list[str], JsonDict]:
        where: list[str] = []
        params: JsonDict = {}
        external_userid = str(filters.get("external_userid") or "").strip()
        if external_userid:
            where.append("decorated.external_userid = :external_userid")
            params["external_userid"] = external_userid
        owner_userid = str(filters.get("owner_userid") or "").strip()
        if owner_userid:
            where.append(
                """
                (
                    decorated.owner_userid = :owner_userid
                    OR EXISTS (
                        SELECT 1
                        FROM owner_role_map owner_role
                        WHERE owner_role.userid = decorated.owner_userid
                          AND owner_role.display_name = :owner_userid
                    )
                )
                """
            )
            params["owner_userid"] = owner_userid
        tag = str(filters.get("tag") or "").strip()
        if tag:
            where.append(
                """
                (
                    decorated.signup_label_name = :tag
                    OR EXISTS (
                        SELECT 1
                        FROM contact_tags tag
                        WHERE tag.external_userid = decorated.external_userid
                          AND (tag.tag_id = :tag OR tag.tag_name = :tag)
                    )
                )
                """
            )
            params["tag"] = tag
        status = str(filters.get("status") or "").strip()
        if status:
            where.append(
                """
                (
                    decorated.signup_status = :status
                    OR (:status = 'bound' AND decorated.is_bound = 1)
                    OR (:status = 'unbound' AND decorated.is_bound = 0)
                )
                """
            )
            params["status"] = status
        is_bound = _normalize_bool_filter(filters.get("is_bound"))
        if is_bound is not None:
            where.append("decorated.is_bound = :is_bound")
            params["is_bound"] = 1 if is_bound else 0
        mobile = str(filters.get("mobile") or "").strip()
        if mobile:
            where.append("decorated.mobile LIKE :mobile")
            params["mobile"] = f"%{mobile}%"
        keyword = str(filters.get("keyword") or "").strip().lower()
        if keyword:
            where.append(
                """
                (
                    LOWER(decorated.external_userid) LIKE :keyword
                    OR LOWER(decorated.customer_name) LIKE :keyword
                    OR LOWER(decorated.owner_userid) LIKE :keyword
                    OR LOWER(decorated.remark) LIKE :keyword
                    OR LOWER(decorated.description) LIKE :keyword
                    OR LOWER(decorated.mobile) LIKE :keyword
                    OR LOWER(decorated.signup_status) LIKE :keyword
                    OR LOWER(decorated.signup_label_name) LIKE :keyword
                    OR EXISTS (
                        SELECT 1
                        FROM owner_role_map owner_role
                        WHERE owner_role.userid = decorated.owner_userid
                          AND LOWER(owner_role.display_name) LIKE :keyword
                    )
                    OR EXISTS (
                        SELECT 1
                        FROM contact_tags tag
                        WHERE tag.external_userid = decorated.external_userid
                          AND (LOWER(tag.tag_id) LIKE :keyword OR LOWER(tag.tag_name) LIKE :keyword)
                    )
                )
                """
            )
            params["keyword"] = f"%{keyword}%"
        return where, params

    def _decorate_customer_rows(self, rows: list[JsonDict]) -> list[JsonDict]:
        external_userids = [str(row.get("external_userid") or "").strip() for row in rows if str(row.get("external_userid") or "").strip()]
        tag_map = self._tag_map(external_userids)
        follow_users_map = self._follow_users_map(external_userids)
        identity_map = self._identity_map(external_userids)
        owner_display_map = self._owner_display_map(
            [
                str(row.get("owner_userid") or "").strip()
                for row in rows
                if str(row.get("owner_userid") or "").strip()
            ]
        )
        customers: list[JsonDict] = []
        for row in rows:
            external_userid = str(row.get("external_userid") or "").strip()
            owner_userid = str(row.get("owner_userid") or "").strip()
            mobile = str(row.get("mobile") or "").strip() or None
            is_bound = bool(row.get("is_bound"))
            class_user_status = {
                "current_status": row.get("signup_status") or "",
                "signup_status": row.get("signup_status") or "",
                "signup_label_name": row.get("signup_label_name") or "",
                "activation_bucket": _json_dict(row.get("status_flags_json")).get("activation_bucket", ""),
                "updated_at": _iso(row.get("class_status_updated_at")),
            }
            identity = identity_map.get(external_userid) or {}
            customers.append(
                {
                    "person_id": str(row.get("person_id") or identity.get("person_id") or ""),
                    "external_userid": external_userid,
                    "customer_name": row.get("customer_name") or external_userid,
                    "remark": row.get("remark") or "",
                    "description": row.get("description") or "",
                    "owner_userid": owner_userid,
                    "owner_display_name": owner_display_map.get(owner_userid) or owner_userid,
                    "mobile": mobile,
                    "tags": tag_map.get(external_userid, []),
                    "class_user_status": class_user_status,
                    "last_message_at": _iso(row.get("last_message_at")),
                    "last_touch_at": _iso(row.get("class_status_updated_at") or row.get("contact_updated_at") or row.get("binding_updated_at")),
                    "updated_at": _iso(row.get("sort_updated_at")),
                    "created_at": _iso(row.get("contact_updated_at") or row.get("binding_updated_at") or row.get("class_status_updated_at")),
                    "binding": {
                        "is_bound": is_bound,
                        "mobile": mobile,
                        "binding_status": "bound" if is_bound else "unbound",
                        "person_id": row.get("person_id"),
                        "third_party_user_id": row.get("third_party_user_id") or "",
                    },
                    "identity": {
                        "person_id": row.get("person_id"),
                        "external_userid": external_userid,
                        "mobile": mobile,
                        "unionid": identity.get("unionid") or "",
                        "openid": identity.get("openid") or "",
                        "status": identity.get("status") or "",
                    },
                    "follow_users": follow_users_map.get(external_userid, []),
                    "marketing_summary": {},
                    "marketing_profile": {},
                    "contact": {
                        "external_userid": external_userid,
                        "name": row.get("customer_name") or external_userid,
                        "remark": row.get("remark") or "",
                        "description": row.get("description") or "",
                    },
                    "sidebar_context": {
                        "can_open_sidebar": bool(external_userid),
                        "customer_profile_url": f"/admin/customers/{external_userid}" if external_userid else "",
                    },
                }
            )
        return customers

    def _tag_map(self, external_userids: list[str]) -> dict[str, list[str]]:
        rows = self._execute_in_query(
            """
            SELECT external_userid, COALESCE(NULLIF(tag_name, ''), tag_id) AS tag
            FROM contact_tags
            WHERE external_userid IN :external_userids
            ORDER BY external_userid ASC, tag ASC
            """,
            external_userids,
        )
        result: dict[str, list[str]] = {}
        for row in rows:
            external_userid = str(row.get("external_userid") or "").strip()
            tag = str(row.get("tag") or "").strip()
            if external_userid and tag and tag not in result.setdefault(external_userid, []):
                result[external_userid].append(tag)
        return result

    def _follow_users_map(self, external_userids: list[str]) -> dict[str, list[JsonDict]]:
        rows = self._execute_in_query(
            """
            SELECT external_userid, user_id, relation_status, is_primary, remark, description, updated_at
            FROM wecom_external_contact_follow_users
            WHERE external_userid IN :external_userids
            ORDER BY external_userid ASC, is_primary DESC, updated_at DESC, id DESC
            """,
            external_userids,
        )
        result: dict[str, list[JsonDict]] = {}
        for row in rows:
            external_userid = str(row.get("external_userid") or "").strip()
            userid = str(row.get("user_id") or "").strip()
            if not external_userid or not userid:
                continue
            result.setdefault(external_userid, []).append(
                {
                    "userid": userid,
                    "display_name": userid,
                    "relation_status": str(row.get("relation_status") or "").strip(),
                    "is_primary": bool(row.get("is_primary")),
                    "remark": str(row.get("remark") or "").strip(),
                    "description": str(row.get("description") or "").strip(),
                    "updated_at": _iso(row.get("updated_at")),
                }
            )
        return result

    def _identity_map(self, external_userids: list[str]) -> dict[str, JsonDict]:
        rows = self._execute_in_query(
            """
            SELECT external_userid, unionid, openid, follow_user_userid, name, status, updated_at, id
            FROM wecom_external_contact_identity_map
            WHERE external_userid IN :external_userids
            ORDER BY external_userid ASC, updated_at DESC, id DESC
            """,
            external_userids,
        )
        result: dict[str, JsonDict] = {}
        for row in rows:
            external_userid = str(row.get("external_userid") or "").strip()
            if external_userid and external_userid not in result:
                result[external_userid] = dict(row)
        return result

    def _owner_display_map(self, userids: list[str]) -> dict[str, str]:
        rows = self._execute_in_query(
            """
            SELECT userid, display_name
            FROM owner_role_map
            WHERE userid IN :external_userids
            """,
            userids,
        )
        return {
            str(row.get("userid") or "").strip(): str(row.get("display_name") or "").strip()
            for row in rows
            if str(row.get("userid") or "").strip()
        }

    def _execute_in_query(self, sql: str, values: list[str]) -> list[JsonDict]:
        normalized = [str(value or "").strip() for value in values if str(value or "").strip()]
        if not normalized:
            return []
        stmt = text(sql).bindparams(bindparam("external_userids", expanding=True))
        return [dict(row) for row in self._session.execute(stmt, {"external_userids": normalized}).mappings()]


def _apply_customer_filters(rows: list[JsonDict], filters: JsonDict) -> list[JsonDict]:
    owner_userid = str(filters.get("owner_userid") or "").strip()
    tag = str(filters.get("tag") or "").strip()
    status = str(filters.get("status") or "").strip()
    mobile = str(filters.get("mobile") or "").strip()
    keyword = str(filters.get("keyword") or "").strip()
    is_bound = _normalize_bool_filter(filters.get("is_bound"))
    if owner_userid:
        rows = [item for item in rows if item.get("owner_userid") == owner_userid]
    if tag:
        rows = [item for item in rows if tag in item.get("tags", [])]
    if status:
        rows = [
            item
            for item in rows
            if status
            in {
                str(item.get("class_user_status", {}).get("current_status") or ""),
                str(item.get("class_user_status", {}).get("signup_status") or ""),
                str(item.get("class_user_status", {}).get("activation_bucket") or ""),
                str(item.get("binding", {}).get("binding_status") or ""),
                str(item.get("binding_status") or ""),
            }
        ]
    if is_bound is not None:
        rows = [item for item in rows if bool(item.get("binding", {}).get("is_bound", item.get("is_bound"))) is is_bound]
    if mobile:
        rows = [item for item in rows if mobile in str(item.get("mobile") or "")]
    if keyword:
        rows = [
            item
            for item in rows
            if keyword in str(item.get("customer_name") or "")
            or keyword in str(item.get("external_userid") or "")
            or keyword in str(item.get("mobile") or "")
            or keyword in str(item.get("owner_userid") or "")
            or keyword in str(item.get("owner_display_name") or "")
        ]
    return rows


def _apply_page(rows: list[JsonDict], *, limit: int | None, offset: int = 0) -> list[JsonDict]:
    if limit is None:
        return rows[offset:] if offset else rows
    return rows[offset : offset + limit]


def _normalize_bool_filter(value: object) -> bool | None:
    normalized = str(value or "").strip().lower()
    if normalized in {"", "all"}:
        return None
    if normalized in {"1", "true", "yes", "y", "on", "bound"}:
        return True
    if normalized in {"0", "false", "no", "n", "off", "unbound"}:
        return False
    return None


def _coerce_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if value:
        return datetime.fromisoformat(str(value))
    return datetime.now(timezone.utc)


def _coerce_optional_datetime(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    return _coerce_datetime(value)


def _iso(value: object) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _json_dict(value: object) -> JsonDict:
    if isinstance(value, dict):
        return dict(value)
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
    except Exception:
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def build_customer_live_source_repository(
    settings: Settings | None = None,
    *,
    session: Session | None = None,
    engine: Engine | None = None,
) -> CustomerReadRepository:
    settings = settings or get_settings()
    if session is not None:
        return assert_repository_allowed(
            LiveSourceCustomerReadRepository(session),
            capability_owner="customer_read_model",
        )
    owned_session = get_session_factory(settings=settings)() if engine is None else Session(bind=engine, future=True)
    return assert_repository_allowed(
        LiveSourceCustomerReadRepository(owned_session),
        capability_owner="customer_read_model",
    )


def build_customer_read_model_repository(
    settings: Settings | None = None,
    *,
    session: Session | None = None,
    engine: Engine | None = None,
) -> CustomerReadRepository:
    settings = settings or get_settings()
    configured_backend = str(os.getenv("CUSTOMER_READ_MODEL_REPO_BACKEND", "") or "").strip().lower()
    backend = configured_backend or settings.customer_read_model_repo_backend.strip().lower()
    if not configured_backend and database_mode() == "postgres":
        backend = "sqlalchemy"
    if backend in {"sql", "sqlalchemy", "postgres", "postgresql"}:
        if session is not None:
            return assert_repository_allowed(
                SqlAlchemyCustomerReadModelRepository(session),
                capability_owner="customer_read_model",
            )
        owned_session = get_session_factory(settings=settings)() if engine is None else Session(bind=engine, future=True)
        return assert_repository_allowed(
            SqlAlchemyCustomerReadModelRepository(owned_session),
            capability_owner="customer_read_model",
        )
    return assert_repository_allowed(InMemoryCustomerReadModelRepository(), capability_owner="customer_read_model")


InMemoryCustomerReadModelRepository = FixtureCustomerReadRepository
