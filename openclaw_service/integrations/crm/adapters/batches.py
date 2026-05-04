from __future__ import annotations

from typing import Any

from ..client import CrmApiClient
from ..errors import CrmMappingError
from ..models import MessageBatch


class BatchesAdapter:
    """Compatibility adapter for current batch APIs via CRM-exposed MCP HTTP."""

    def __init__(self, client: CrmApiClient) -> None:
        self.client = client

    def get_pending_message_batches(self, *, limit: int = 20, cursor: str = "") -> list[MessageBatch]:
        payload = self._call_mcp_tool("get_pending_message_batches", {"limit": limit, "cursor": cursor})
        items = payload.get("items") or []
        return [self._map_batch(item) for item in items if isinstance(item, dict)]

    def get_message_batch(self, batch_id: int | str, *, limit: int = 200, cursor: str = "") -> MessageBatch:
        payload = self._call_mcp_tool("get_message_batch", {"batch_id": int(batch_id), "limit": limit, "cursor": cursor})
        return self._map_batch(payload)

    def ack_message_batch(self, batch_id: int | str, *, acked_by: str = "", ack_note: str = "") -> MessageBatch:
        payload = self._call_mcp_tool(
            "ack_message_batch",
            {"batch_id": int(batch_id), "acked_by": acked_by, "ack_note": ack_note},
        )
        return self._map_batch(payload)

    def get_customer_marketing_profile(
        self,
        *,
        external_userid: str = "",
        person_id: int | None = None,
        recent_message_limit: int = 3,
    ) -> dict[str, Any]:
        return self._call_mcp_tool(
            "get_customer_marketing_profile",
            {
                "external_userid": external_userid,
                "person_id": person_id,
                "recent_message_limit": recent_message_limit,
            },
        )

    def get_pending_conversion_batches(self, *, limit: int = 20, cursor: str = "") -> dict[str, Any]:
        return self._call_mcp_tool("get_pending_conversion_batches", {"limit": limit, "cursor": cursor})

    def get_conversion_batch(
        self,
        batch_id: int | str,
        *,
        recent_message_limit: int = 3,
    ) -> dict[str, Any]:
        return self._call_mcp_tool(
            "get_conversion_batch",
            {
                "batch_id": int(batch_id),
                "recent_message_limit": recent_message_limit,
            },
        )

    def ack_conversion_batch(self, batch_id: int | str, *, acked_by: str = "", ack_note: str = "") -> dict[str, Any]:
        return self._call_mcp_tool(
            "ack_conversion_batch",
            {"batch_id": int(batch_id), "acked_by": acked_by, "ack_note": ack_note},
        )

    def get_signup_conversion_batches(self, *, limit: int = 20, cursor: str = "") -> dict[str, Any]:
        return self.get_pending_conversion_batches(limit=limit, cursor=cursor)

    def get_signup_conversion_batch(
        self,
        batch_id: int | str,
        *,
        recent_message_limit: int = 20,
        timeline_limit: int = 20,
    ) -> dict[str, Any]:
        return self.get_conversion_batch(batch_id, recent_message_limit=recent_message_limit)

    def _call_mcp_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        payload = self.client.post(
            "/mcp",
            headers=self.client.config.mcp_headers(),
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments},
            },
        )
        if not isinstance(payload, dict):
            raise CrmMappingError("MCP batch payload must be a JSON object", response_payload=payload)
        result = payload.get("result") if isinstance(payload.get("result"), dict) else payload
        structured = result.get("structuredContent") if isinstance(result.get("structuredContent"), dict) else None
        if structured is not None:
            return structured
        content = result.get("content")
        if isinstance(content, list) and content and isinstance(content[0], dict):
            text = content[0].get("text")
            if isinstance(text, str) and text.strip():
                import json

                return json.loads(text)
        raise CrmMappingError("unable to decode MCP batch payload", response_payload=payload)

    @staticmethod
    def _map_batch(payload: dict[str, Any]) -> MessageBatch:
        if not isinstance(payload, dict):
            raise CrmMappingError("message batch payload must be a JSON object", response_payload=payload)
        batch_meta = payload.get("batch") if isinstance(payload.get("batch"), dict) else payload
        batch_id = str(batch_meta.get("id") or batch_meta.get("batch_id") or payload.get("batch_id") or "").strip()
        if not batch_id:
            raise CrmMappingError("missing batch id in CRM message batch payload", response_payload=payload)
        acked_by = str(batch_meta.get("acked_by") or "").strip()
        ack_status = "acked" if acked_by else str(batch_meta.get("ack_status") or "").strip()
        return MessageBatch(
            batch_id=batch_id,
            status=str(batch_meta.get("status") or "").strip(),
            created_at=str(batch_meta.get("created_at") or batch_meta.get("window_start") or "").strip(),
            ack_status=ack_status,
            items=[item for item in (payload.get("messages") or payload.get("items") or []) if isinstance(item, dict)],
            raw=payload,
        )
