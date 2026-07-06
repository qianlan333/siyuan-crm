from __future__ import annotations

from aicrm_next.shared.errors import ApplicationError
from aicrm_next.shared.typing import JsonDict

from .dispatch import McpToolDispatcher
from .mcp_openclaw_adapters import build_mcp_tool_gateway

MCP_TOOLS = [
    {
        "name": "resolve_customer",
        "description": "Resolve a customer by customer_ref, mobile, or external_userid.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_ref": {"type": "string"},
                "external_userid": {"type": "string"},
                "include_context": {"type": "boolean"},
                "recent_message_limit": {"type": "integer"},
                "timeline_limit": {"type": "integer"},
            },
        },
    },
    {
        "name": "get_customer_context",
        "description": "Return customer detail, recent messages, and timeline context.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_ref": {"type": "string"},
                "external_userid": {"type": "string"},
                "recent_message_limit": {"type": "integer"},
                "timeline_limit": {"type": "integer"},
            },
        },
    },
    {
        "name": "get_recent_messages",
        "description": "Return recent single-customer archived messages.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_ref": {"type": "string"},
                "external_userid": {"type": "string"},
                "limit": {"type": "integer"},
            },
        },
    },
]


class McpJsonRpcApplication:
    def __init__(self, dispatcher: McpToolDispatcher | None = None, tool_gateway=None) -> None:
        self._dispatcher = dispatcher or McpToolDispatcher()
        self._tool_gateway = tool_gateway or build_mcp_tool_gateway()

    def handle(self, payload: JsonDict) -> JsonDict:
        request_id = payload.get("id")
        method = str(payload.get("method") or "")
        params = payload.get("params") or {}
        try:
            if method == "initialize":
                result = {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "aicrm-next", "version": "0.1.0"},
                    "capabilities": {"tools": {}},
                }
            elif method == "tools/list":
                adapter_result = self._tool_gateway.list_tools(request_id=str(request_id or ""))
                result = {"tools": MCP_TOOLS, "adapter_contract": {"mcp_tool": adapter_result}}
            elif method == "tools/call":
                name = str(params.get("name") or "")
                arguments = params.get("arguments") or {}
                content = self._dispatcher.dispatch(name, arguments)
                result = {"content": [{"type": "json", "json": content}], "structuredContent": content}
            else:
                raise ApplicationError(f"unknown MCP method: {method}")
            return {"jsonrpc": "2.0", "id": request_id, "result": result}
        except ApplicationError as exc:
            return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32000, "message": str(exc)}}
        except Exception as exc:
            return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32603, "message": str(exc)}}
