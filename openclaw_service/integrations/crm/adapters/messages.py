from __future__ import annotations

from typing import Any

from ..client import CrmApiClient
from ..errors import CrmMappingError


class MessagesAdapter:
    def __init__(self, client: CrmApiClient) -> None:
        self.client = client

    def get_messages(self, external_userid: str, *, chat_type: str | None = None) -> list[dict[str, Any]]:
        params = {"chat_type": chat_type} if chat_type else None
        payload = self.client.get(f"/api/messages/{external_userid}", params=params)
        return self._extract_messages(payload)

    def get_recent_messages(
        self,
        external_userid: str,
        *,
        limit: int = 20,
        chat_type: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit}
        if chat_type:
            params["chat_type"] = chat_type
        payload = self.client.get(f"/api/messages/{external_userid}/recent", params=params)
        return self._extract_messages(payload)

    def search_messages(self, external_userid: str, *, keyword: str) -> list[dict[str, Any]]:
        payload = self.client.get("/api/messages/search", params={"external_userid": external_userid, "keyword": keyword})
        return self._extract_messages(payload)

    @staticmethod
    def _extract_messages(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            if isinstance(payload.get("recent_messages"), list):
                return [item for item in payload["recent_messages"] if isinstance(item, dict)]
            for key in ("messages", "items", "data"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
        raise CrmMappingError("message payload must contain a list of message objects", response_payload=payload)
