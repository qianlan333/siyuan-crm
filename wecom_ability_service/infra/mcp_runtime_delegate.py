from __future__ import annotations

from typing import Any


def execute_mcp_tool_runtime(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """Legacy-compatible MCP runtime delegate extracted out of the transport module for Wave 1."""

    from ..mcp_adapter import _call_tool

    return _call_tool(str(name or "").strip(), arguments or {})


__all__ = ["execute_mcp_tool_runtime"]
