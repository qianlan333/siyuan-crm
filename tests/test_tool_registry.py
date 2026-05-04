from __future__ import annotations

import pytest

from openclaw_service.tools.registry import call_tool_by_name, get_tool_defs, list_tools


def test_registry_lists_customer_chat_context_tool() -> None:
    assert "get_customer_chat_context" in list_tools()


def test_registry_returns_tool_def_for_customer_chat_context() -> None:
    tool_defs = get_tool_defs()

    assert any(tool_def["name"] == "get_customer_chat_context" for tool_def in tool_defs)


def test_registry_dispatches_to_customer_chat_context_tool(monkeypatch) -> None:
    captured: dict = {}

    def fake_call_tool(arguments: dict | None = None) -> dict:
        captured["arguments"] = arguments
        return {"external_userid": "wm_ext_001", "source_status": "live", "degraded": False, "warnings": []}

    monkeypatch.setattr(
        "openclaw_service.tools.registry._TOOL_CALLS",
        {"get_customer_chat_context": fake_call_tool},
    )

    result = call_tool_by_name("get_customer_chat_context", {"external_userid": "wm_ext_001"})

    assert result["external_userid"] == "wm_ext_001"
    assert captured["arguments"] == {"external_userid": "wm_ext_001"}


@pytest.mark.parametrize(
    ("name", "message"),
    [
        ("", "tool name is required"),
        ("missing_tool", "unknown tool: missing_tool"),
    ],
)
def test_registry_rejects_unknown_tool_names(name: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        call_tool_by_name(name, {})
