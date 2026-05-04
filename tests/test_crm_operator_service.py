from __future__ import annotations

import pytest

from openclaw_service.services.crm_operator_service import get_customer_context, update_customer_tags


def test_get_customer_context_dispatches_through_registry(monkeypatch) -> None:
    captured: dict = {}

    def fake_call_tool_by_name(name: str, arguments: dict | None = None) -> dict:
        captured["name"] = name
        captured["arguments"] = arguments
        return {"external_userid": "wm_ext_001", "source_status": "live", "degraded": False, "warnings": []}

    monkeypatch.setattr(
        "openclaw_service.services.crm_operator_service.call_tool_by_name",
        fake_call_tool_by_name,
    )

    result = get_customer_context("wm_ext_001", recent_message_limit=7, timeline_limit=9)

    assert result["external_userid"] == "wm_ext_001"
    assert captured["name"] == "get_customer_chat_context"
    assert captured["arguments"] == {
        "external_userid": "wm_ext_001",
        "recent_message_limit": 7,
        "timeline_limit": 9,
    }


def test_update_customer_tags_marks_tags(monkeypatch) -> None:
    class FakeTagsAdapter:
        def __init__(self, client) -> None:
            self.client = client

        def mark_tags(self, userid: str, external_userid: str, add_tags: list[str]) -> dict:
            return {
                "ok": True,
                "userid": userid,
                "external_userid": external_userid,
                "add_tag": add_tags,
            }

    monkeypatch.setattr("openclaw_service.services.crm_operator_service.CrmApiConfig.from_env", classmethod(lambda cls: object()))
    monkeypatch.setattr("openclaw_service.services.crm_operator_service.TagsAdapter", FakeTagsAdapter)

    result = update_customer_tags("wm_ext_001", userid="sales_01", add_tags=["tag-001", "tag-001", " "])

    assert result["ok"] is True
    assert result["external_userid"] == "wm_ext_001"
    assert result["userid"] == "sales_01"
    assert result["add_tags"] == ["tag-001"]
    assert result["remove_tags"] == []
    assert result["results"]["mark"]["ok"] is True
    assert result["results"]["mark"]["response"]["add_tag"] == ["tag-001"]


def test_update_customer_tags_unmarks_tags(monkeypatch) -> None:
    class FakeTagsAdapter:
        def __init__(self, client) -> None:
            self.client = client

        def unmark_tags(self, userid: str, external_userid: str, remove_tags: list[str]) -> dict:
            return {
                "ok": True,
                "userid": userid,
                "external_userid": external_userid,
                "remove_tag": remove_tags,
            }

    monkeypatch.setattr("openclaw_service.services.crm_operator_service.CrmApiConfig.from_env", classmethod(lambda cls: object()))
    monkeypatch.setattr("openclaw_service.services.crm_operator_service.TagsAdapter", FakeTagsAdapter)

    result = update_customer_tags("wm_ext_001", userid="sales_01", add_tags=[], remove_tags=["tag-009"])

    assert result["ok"] is True
    assert result["add_tags"] == []
    assert result["remove_tags"] == ["tag-009"]
    assert result["results"]["unmark"]["ok"] is True
    assert result["results"]["unmark"]["response"]["remove_tag"] == ["tag-009"]


def test_update_customer_tags_requires_at_least_one_operation() -> None:
    with pytest.raises(ValueError, match="at least one of add_tags or remove_tags is required"):
        update_customer_tags("wm_ext_001", userid="sales_01")


def test_update_customer_tags_returns_partial_results_when_one_operation_fails(monkeypatch) -> None:
    class FakeTagsAdapter:
        def __init__(self, client) -> None:
            self.client = client

        def mark_tags(self, userid: str, external_userid: str, add_tags: list[str]) -> dict:
            return {"ok": True, "add_tag": add_tags}

        def unmark_tags(self, userid: str, external_userid: str, remove_tags: list[str]) -> dict:
            raise RuntimeError("crm unmark failed")

    monkeypatch.setattr("openclaw_service.services.crm_operator_service.CrmApiConfig.from_env", classmethod(lambda cls: object()))
    monkeypatch.setattr("openclaw_service.services.crm_operator_service.TagsAdapter", FakeTagsAdapter)

    result = update_customer_tags(
        "wm_ext_001",
        userid="sales_01",
        add_tags=["tag-001"],
        remove_tags=["tag-002"],
    )

    assert result["ok"] is False
    assert result["results"]["mark"]["ok"] is True
    assert result["results"]["unmark"]["ok"] is False
    assert result["results"]["unmark"]["error"] == "crm unmark failed"
    assert result["results"]["unmark"]["error_type"] == "RuntimeError"
