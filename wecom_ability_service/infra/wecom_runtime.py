from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..wecom_client import WeComClient


@dataclass
class AppWeComRuntimeClient:
    _client: WeComClient

    def build_jsapi_signature(self, url: str, *, ticket_type: str) -> dict[str, Any]:
        return self._client.build_jsapi_signature(url, ticket_type=ticket_type)

    def list_follow_userids(self) -> dict[str, Any]:
        return self._client.list_follow_userids()

    def list_contacts(self, owner_userid: str) -> dict[str, Any]:
        return self._client.list_contacts(owner_userid)

    def get_contact(self, external_userid: str) -> dict[str, Any]:
        return self._client.get_contact(external_userid)

    def update_contact_description(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._client.update_contact_description(payload)

    def list_group_chats(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._client.list_group_chats(payload)

    def get_group_chat(self, chat_id: str, *, need_name: int = 1) -> dict[str, Any]:
        return self._client.get_group_chat(chat_id, need_name=need_name)

    def create_tag(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._client.create_tag(payload)

    def mark_external_contact_tags(
        self,
        *,
        external_userid: str,
        follow_user_userid: str,
        add_tags: list[str],
        remove_tags: list[str],
    ) -> dict[str, Any]:
        return self._client.mark_external_contact_tags(
            external_userid=external_userid,
            follow_user_userid=follow_user_userid,
            add_tags=add_tags,
            remove_tags=remove_tags,
        )


@dataclass
class ContactWeComRuntimeClient:
    _client: WeComClient

    def list_follow_userids(self) -> dict[str, Any]:
        return self._client.list_follow_userids()

    def list_contacts(self, owner_userid: str) -> dict[str, Any]:
        return self._client.list_contacts(owner_userid)

    def get_contact(self, external_userid: str) -> dict[str, Any]:
        return self._client.get_contact(external_userid)

    def update_contact_description(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._client.update_contact_description(payload)

    def create_contact_way(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._client.create_contact_way(payload)

    def send_welcome_msg(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._client.send_welcome_msg(payload)

    def list_external_contact_tags(self) -> dict[str, Any]:
        return self._client.list_external_contact_tags()

    def mark_external_contact_tags(
        self,
        *,
        external_userid: str,
        follow_user_userid: str,
        add_tags: list[str],
        remove_tags: list[str],
    ) -> dict[str, Any]:
        return self._client.mark_external_contact_tags(
            external_userid=external_userid,
            follow_user_userid=follow_user_userid,
            add_tags=add_tags,
            remove_tags=remove_tags,
        )


def get_app_runtime_client() -> AppWeComRuntimeClient:
    return AppWeComRuntimeClient(WeComClient.from_app())


def get_contact_runtime_client() -> ContactWeComRuntimeClient:
    return ContactWeComRuntimeClient(WeComClient.from_contact_app())


def build_jsapi_payload(*, url: str, corp_id: str, agent_id: str) -> dict[str, Any]:
    client = get_app_runtime_client()
    return {
        "corp_id": corp_id,
        "agent_id": str(agent_id or ""),
        "config": client.build_jsapi_signature(url, ticket_type="jsapi"),
        "agent_config": client.build_jsapi_signature(url, ticket_type="agent_config"),
    }
