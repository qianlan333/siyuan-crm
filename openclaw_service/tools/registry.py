from __future__ import annotations

from typing import Any, Callable

from .customer_chat_context_tool import TOOL_NAME, call_tool, get_tool_def

ToolCallable = Callable[[dict[str, Any] | None], dict[str, Any]]

_TOOL_CALLS: dict[str, ToolCallable] = {
    TOOL_NAME: call_tool,
}

_TOOL_DEFS_BY_NAME: dict[str, dict[str, Any]] = {
    TOOL_NAME: get_tool_def(),
}

TOOL_DEFS = list(_TOOL_DEFS_BY_NAME.values())


def get_tool_defs() -> list[dict[str, Any]]:
    return [dict(tool_def) for tool_def in TOOL_DEFS]


def list_tools() -> list[str]:
    return list(_TOOL_CALLS.keys())


def call_tool_by_name(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    tool_name = str(name or "").strip()
    if not tool_name:
        raise ValueError("tool name is required")
    tool = _TOOL_CALLS.get(tool_name)
    if tool is None:
        raise ValueError(f"unknown tool: {tool_name}")
    return tool(arguments or {})
