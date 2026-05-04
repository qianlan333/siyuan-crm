from __future__ import annotations

from typing import cast

from ..customer_read_model.dto import McpRuntimeToolListQueryDTO, McpRuntimeToolListResultDTO


class ListMcpRuntimeToolsQuery:
    """Wave 1 skeleton that delegates to ``domains.admin_config.list_mcp_runtime_tools``."""

    def __call__(self, dto: McpRuntimeToolListQueryDTO | None = None) -> McpRuntimeToolListResultDTO:
        # Wave 1 skeleton: preserve legacy admin-config-backed tool exposure.
        # ``enabled_only`` is accepted now as a forward-compatible placeholder.
        from ...domains.admin_config import list_mcp_runtime_tools

        _ = dto or McpRuntimeToolListQueryDTO()
        return cast(McpRuntimeToolListResultDTO, list_mcp_runtime_tools())

    execute = __call__


__all__ = ["ListMcpRuntimeToolsQuery"]
