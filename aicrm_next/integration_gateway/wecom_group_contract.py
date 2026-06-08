from __future__ import annotations

from typing import Any, Protocol


Json = dict[str, Any]


class WeComGroupMessageAdapterContract(Protocol):
    def create_group_message_task(self, payload: dict[str, Any], *, idempotency_key: str = "") -> Json: ...


class WeComGroupChatSyncAdapterContract(Protocol):
    def list_group_chats(self, *, owner_userid: str, limit: int = 100, cursor: str = "") -> Json: ...
    def get_group_chat(self, chat_id: str, *, owner_userid: str = "") -> Json: ...


class WeComGroupAssetAdapterContract(Protocol):
    def list_group_chats(self, *, owner_userid: str, cursor: str = "", limit: int = 100) -> Json: ...
    def get_group_chat(self, *, chat_id: str, need_name: int = 1, owner_userid: str = "") -> Json: ...


class GroupOpsQueueGatewayContract(Protocol):
    def enqueue_group_message(
        self,
        *,
        plan_id: int,
        source_id: str,
        scheduled_at: str | None,
        owner_userid: str,
        chat_ids: list[str],
        content_payload: dict[str, Any],
        content_summary: str,
        created_by: str = "group_ops_webhook",
    ) -> int: ...


class GroupOpsQueueStatsGatewayContract(Protocol):
    def count_group_ops_queue(self) -> int: ...
