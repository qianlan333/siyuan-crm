from __future__ import annotations

from copy import deepcopy
from typing import Protocol

from aicrm_next.shared.repository_provider import assert_repository_allowed
from aicrm_next.shared.typing import JsonDict


class MessageArchiveRepository(Protocol):
    def list_messages(
        self,
        external_userid: str,
        *,
        chat_type: str = "",
        limit: int | None = None,
        offset: int = 0,
    ) -> list[JsonDict]: ...

    def search_messages(
        self,
        *,
        external_userid: str,
        keyword: str,
        chat_type: str = "",
        limit: int | None = None,
        offset: int = 0,
    ) -> list[JsonDict]: ...


class FixtureMessageArchiveRepository:
    def __init__(self) -> None:
        self._messages: list[JsonDict] = [
            {
                "seq": 11,
                "msgid": "msg-001",
                "chat_type": "private",
                "external_userid": "wm_ext_001",
                "owner_userid": "sales_01",
                "sender": "wm_ext_001",
                "from": "wm_ext_001",
                "tolist": ["sales_01"],
                "roomid": "",
                "chat_id": "",
                "group_name": "",
                "msgtype": "text",
                "content": "我想了解真实落地案例",
                "send_time": "2026-03-15 09:30:00",
            },
            {
                "seq": 12,
                "msgid": "msg-002",
                "chat_type": "private",
                "external_userid": "wm_ext_001",
                "owner_userid": "sales_01",
                "sender": "sales_01",
                "from": "sales_01",
                "tolist": ["wm_ext_001"],
                "roomid": "",
                "chat_id": "",
                "group_name": "",
                "msgtype": "text",
                "content": "这里是方案和报名说明",
                "send_time": "2026-03-15 09:35:00",
            },
            {
                "seq": 13,
                "msgid": "msg-003",
                "chat_type": "group",
                "external_userid": "wm_ext_001",
                "owner_userid": "sales_01",
                "sender": "sales_01",
                "from": "sales_01",
                "tolist": [],
                "roomid": "wr_group_001",
                "chat_id": "wr_group_001",
                "group_name": "测试群",
                "msgtype": "text",
                "content": "群内跟进记录",
                "send_time": "2026-03-15 09:40:00",
            },
        ]

    def list_messages(
        self,
        external_userid: str,
        *,
        chat_type: str = "",
        limit: int | None = None,
        offset: int = 0,
    ) -> list[JsonDict]:
        rows = [deepcopy(row) for row in self._messages if row.get("external_userid") == external_userid]
        if chat_type:
            rows = [row for row in rows if row.get("chat_type") == chat_type]
        return _page(rows, limit=limit, offset=offset)

    def search_messages(
        self,
        *,
        external_userid: str,
        keyword: str,
        chat_type: str = "",
        limit: int | None = None,
        offset: int = 0,
    ) -> list[JsonDict]:
        rows = [
            row
            for row in self.list_messages(external_userid, chat_type=chat_type, limit=None, offset=0)
            if keyword in str(row.get("content") or "")
        ]
        return _page(rows, limit=limit, offset=offset)


def build_message_archive_repository() -> MessageArchiveRepository:
    return assert_repository_allowed(FixtureMessageArchiveRepository(), capability_owner="message_archive")


def _page(rows: list[JsonDict], *, limit: int | None, offset: int) -> list[JsonDict]:
    if limit is None:
        return rows[offset:] if offset else rows
    return rows[offset : offset + limit]

