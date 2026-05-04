from __future__ import annotations

import pytest

from openclaw_service.cli.customer_chat_context import load_customer_chat_context


def test_runtime_bridge_calls_registry(monkeypatch) -> None:
    captured: dict = {}

    def fake_dispatch(name: str, arguments: dict | None = None) -> dict:
        captured["name"] = name
        captured["arguments"] = arguments
        return {"external_userid": "wm_ext_001", "source_status": "live", "degraded": False, "warnings": []}

    monkeypatch.setattr(
        "openclaw_service.cli.customer_chat_context.call_tool_by_name",
        fake_dispatch,
    )

    result = load_customer_chat_context("wm_ext_001", recent_message_limit=5, timeline_limit=7)

    assert result["external_userid"] == "wm_ext_001"
    assert captured["name"] == "get_customer_chat_context"
    assert captured["arguments"] == {
        "external_userid": "wm_ext_001",
        "recent_message_limit": 5,
        "timeline_limit": 7,
    }


def test_runtime_bridge_preserves_degraded_result(monkeypatch) -> None:
    monkeypatch.setattr(
        "openclaw_service.cli.customer_chat_context.call_tool_by_name",
        lambda name, arguments=None: {
            "external_userid": arguments["external_userid"],
            "source_status": "fallback",
            "degraded": True,
            "warnings": ["timeline fallback in use"],
        },
    )

    result = load_customer_chat_context("wm_ext_003")

    assert result["degraded"] is True
    assert result["source_status"] == "fallback"


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (ValueError("unknown tool: missing_tool"), "unknown tool: missing_tool"),
        (ValueError("external_userid is required"), "external_userid is required"),
    ],
)
def test_runtime_bridge_surfaces_registry_errors(monkeypatch, error: Exception, message: str) -> None:
    def fail(name: str, arguments: dict | None = None) -> dict:
        raise error

    monkeypatch.setattr(
        "openclaw_service.cli.customer_chat_context.call_tool_by_name",
        fail,
    )

    with pytest.raises(type(error), match=message):
        load_customer_chat_context("wm_ext_004")
