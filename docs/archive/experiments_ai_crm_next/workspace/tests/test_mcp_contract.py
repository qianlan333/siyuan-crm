from __future__ import annotations

from pathlib import Path

from conftest import make_client

REPO_ROOT = Path(__file__).resolve().parents[3]


def _rpc(method: str, params: dict | None = None, request_id: int = 1) -> dict:
    response = make_client().post("/mcp", json={"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}})
    assert response.status_code == 200
    return response.json()


def test_mcp_initialize_works() -> None:
    payload = _rpc("initialize")
    assert payload["result"]["serverInfo"]["name"] == "aicrm-next"


def test_mcp_tools_list_works() -> None:
    payload = _rpc("tools/list")
    names = {tool["name"] for tool in payload["result"]["tools"]}
    assert {"resolve_customer", "get_customer_context", "get_recent_messages"} <= names


def test_mcp_resolve_customer_by_mobile_works() -> None:
    payload = _rpc(
        "tools/call",
        {"name": "resolve_customer", "arguments": {"customer_ref": "13800138000"}},
    )
    content = payload["result"]["structuredContent"]
    assert content["external_userid"] == "wx_ext_001"
    assert content["customer"]["mobile"] == "13800138000"


def test_mcp_mobile_not_found_is_explicit() -> None:
    payload = _rpc(
        "tools/call",
        {"name": "resolve_customer", "arguments": {"customer_ref": "18800000000"}},
    )
    assert "error" in payload
    assert "customer not found for mobile: 18800000000" in payload["error"]["message"]


def test_mcp_get_customer_context_works() -> None:
    payload = _rpc(
        "tools/call",
        {"name": "get_customer_context", "arguments": {"external_userid": "wx_ext_001", "timeline_limit": 2}},
    )
    context = payload["result"]["structuredContent"]
    assert context["external_userid"] == "wx_ext_001"
    assert context["customer"]["external_userid"] == "wx_ext_001"
    assert "recent_messages" in context
    assert "recent_timeline_events" in context


def test_mcp_get_customer_context_includes_openclaw_read_sections() -> None:
    payload = _rpc(
        "tools/call",
        {"name": "get_customer_context", "arguments": {"external_userid": "wx_ext_001", "recent_message_limit": 1, "timeline_limit": 1}},
    )
    context = payload["result"]["structuredContent"]
    assert context["customer"]["marketing_summary"]
    assert context["customer"]["marketing_profile"]
    assert context["recent_messages"][0]["external_userid"] == "wx_ext_001"
    assert context["recent_timeline_events"][0]["external_userid"] if "external_userid" in context["recent_timeline_events"][0] else True


def test_mcp_get_recent_messages_still_works() -> None:
    payload = _rpc(
        "tools/call",
        {"name": "get_recent_messages", "arguments": {"external_userid": "wx_ext_001", "limit": 1}},
    )
    content = payload["result"]["structuredContent"]
    assert content["ok"] is True
    assert len(content["messages"]) == 1
    assert content["messages"][0]["msgid"]


def test_mcp_dispatcher_does_not_import_customer_repo_directly() -> None:
    text = (REPO_ROOT / "aicrm_next" / "integration_gateway" / "dispatch.py").read_text(encoding="utf-8")
    assert "customer_read_model.repo" not in text
    assert "FixtureCustomerReadRepository" not in text
