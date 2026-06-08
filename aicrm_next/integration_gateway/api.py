from __future__ import annotations

from fastapi import APIRouter

from aicrm_next.shared.typing import JsonDict

from .mcp import McpJsonRpcApplication

router = APIRouter()


@router.get("/mcp")
def mcp_metadata() -> dict:
    return {"ok": True, "transport": "jsonrpc", "methods": ["initialize", "tools/list", "tools/call"]}


@router.post("/mcp")
def mcp_rpc(payload: JsonDict) -> dict:
    return McpJsonRpcApplication().handle(payload)
