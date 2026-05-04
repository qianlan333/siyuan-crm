from __future__ import annotations

import pytest

from openclaw_service.tools.customer_chat_context_tool import TOOL_NAME, call_tool, get_tool_def


def test_tool_definition_exposes_name_and_required_input() -> None:
    tool_def = get_tool_def()

    assert tool_def["name"] == TOOL_NAME
    assert tool_def["inputSchema"]["required"] == ["external_userid"]


def test_tool_calls_service_with_external_userid_and_limits(monkeypatch) -> None:
    captured: dict = {}

    def fake_service(external_userid: str, *, recent_message_limit: int, timeline_limit: int) -> dict:
        captured["external_userid"] = external_userid
        captured["recent_message_limit"] = recent_message_limit
        captured["timeline_limit"] = timeline_limit
        return {"external_userid": external_userid, "source_status": "live", "degraded": False, "warnings": []}

    monkeypatch.setattr(
        "openclaw_service.tools.customer_chat_context_tool.get_customer_chat_context",
        fake_service,
    )

    result = call_tool({"external_userid": "wm_ext_001", "recent_message_limit": 8, "timeline_limit": 6})

    assert result["external_userid"] == "wm_ext_001"
    assert captured == {
        "external_userid": "wm_ext_001",
        "recent_message_limit": 8,
        "timeline_limit": 6,
    }


def test_tool_preserves_degraded_result(monkeypatch) -> None:
    monkeypatch.setattr(
        "openclaw_service.tools.customer_chat_context_tool.get_customer_chat_context",
        lambda external_userid, **kwargs: {
            "external_userid": external_userid,
            "source_status": "fallback",
            "degraded": True,
            "warnings": ["timeline fallback in use"],
        },
    )

    result = call_tool({"external_userid": "wm_ext_003"})

    assert result["degraded"] is True
    assert result["source_status"] == "fallback"


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({}, "external_userid is required"),
        ({"external_userid": "wm_ext_001", "recent_message_limit": 0}, "recent_message_limit must be >= 1"),
        ({"external_userid": "wm_ext_001", "timeline_limit": "bad"}, "timeline_limit must be an integer"),
    ],
)
def test_tool_rejects_invalid_arguments(arguments: dict, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        call_tool(arguments)
