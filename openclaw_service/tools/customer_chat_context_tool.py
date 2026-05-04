from __future__ import annotations

from typing import Any

from openclaw_service.services.customer_chat_context_service import get_customer_chat_context

TOOL_NAME = "get_customer_chat_context"

TOOL_DEF = {
    "name": TOOL_NAME,
    "description": "Load CRM-backed customer chat context for a single external_userid.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "external_userid": {
                "type": "string",
                "description": "CRM external_userid for the customer to load.",
            },
            "recent_message_limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 200,
                "default": 20,
            },
            "timeline_limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 200,
                "default": 20,
            },
        },
        "required": ["external_userid"],
    },
    "output": {
        "type": "object",
        "description": "Customer detail, recent messages, recent timeline events, and degraded/fallback status.",
    },
}


def get_tool_def() -> dict[str, Any]:
    return TOOL_DEF


def call_tool(arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    arguments = arguments or {}
    external_userid = _require_external_userid(arguments.get("external_userid"))
    recent_message_limit = _parse_limit(arguments.get("recent_message_limit", 20), field_name="recent_message_limit")
    timeline_limit = _parse_limit(arguments.get("timeline_limit", 20), field_name="timeline_limit")
    return get_customer_chat_context(
        external_userid,
        recent_message_limit=recent_message_limit,
        timeline_limit=timeline_limit,
    )


def _require_external_userid(value: Any) -> str:
    external_userid = str(value or "").strip()
    if not external_userid:
        raise ValueError("external_userid is required")
    return external_userid


def _parse_limit(value: Any, *, field_name: str) -> int:
    try:
        limit = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer") from exc
    if limit < 1:
        raise ValueError(f"{field_name} must be >= 1")
    if limit > 200:
        raise ValueError(f"{field_name} must be <= 200")
    return limit
