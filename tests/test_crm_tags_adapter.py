from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from openclaw_service.integrations.crm.adapters.tags import TagsAdapter
from openclaw_service.integrations.crm.client import CrmApiClient
from openclaw_service.integrations.crm.config import CrmApiConfig
from openclaw_service.integrations.crm.errors import CrmHttpError


@dataclass
class FakeResponse:
    status_code: int
    payload: Any
    headers: dict[str, str] | None = None
    text: str = ""

    def json(self) -> Any:
        return self.payload


class FakeSession:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"method": method, "url": url, **kwargs})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def make_adapter(*responses: Any) -> tuple[TagsAdapter, FakeSession]:
    session = FakeSession(list(responses))
    client = CrmApiClient(
        CrmApiConfig(
            base_url="https://crm.example.com",
            api_token="crm-token",
            mcp_bearer_token="mcp-token",
        ),
        session=session,
    )
    return TagsAdapter(client), session


def test_list_tags_flattens_groups() -> None:
    adapter, session = make_adapter(
        FakeResponse(
            200,
            {
                "ok": True,
                "result": {
                    "tag_group": [
                        {
                            "group_id": "group-001",
                            "group_name": "客户分层",
                            "tag": [
                                {"id": "tag-001", "name": "高意向"},
                                {"id": "tag-002", "name": "已报名3999"},
                            ],
                        }
                    ]
                },
            },
            {"Content-Type": "application/json"},
        )
    )

    payload = adapter.list_tags()

    assert session.calls[0]["method"] == "GET"
    assert session.calls[0]["url"] == "https://crm.example.com/api/tags"
    assert payload == [
        {
            "tag_id": "tag-001",
            "tag_name": "高意向",
            "group_id": "group-001",
            "group_name": "客户分层",
        },
        {
            "tag_id": "tag-002",
            "tag_name": "已报名3999",
            "group_id": "group-001",
            "group_name": "客户分层",
        },
    ]


def test_mark_tags_posts_expected_payload() -> None:
    adapter, session = make_adapter(FakeResponse(200, {"ok": True, "result": {"marked": 1}}, {"Content-Type": "application/json"}))

    payload = adapter.mark_tags("sales_01", "wm_ext_001", ["tag-001", "tag-002"])

    assert payload == {"ok": True, "result": {"marked": 1}}
    assert session.calls[0]["method"] == "POST"
    assert session.calls[0]["url"] == "https://crm.example.com/api/tags/mark"
    assert session.calls[0]["json"] == {
        "userid": "sales_01",
        "external_userid": "wm_ext_001",
        "add_tag": ["tag-001", "tag-002"],
    }


def test_unmark_tags_posts_expected_payload() -> None:
    adapter, session = make_adapter(FakeResponse(200, {"ok": True, "result": {"unmarked": 1}}, {"Content-Type": "application/json"}))

    payload = adapter.unmark_tags("sales_01", "wm_ext_001", ["tag-009"])

    assert payload == {"ok": True, "result": {"unmarked": 1}}
    assert session.calls[0]["url"] == "https://crm.example.com/api/tags/unmark"
    assert session.calls[0]["json"] == {
        "userid": "sales_01",
        "external_userid": "wm_ext_001",
        "remove_tag": ["tag-009"],
    }


def test_mark_tags_propagates_crm_http_error() -> None:
    adapter, _ = make_adapter(FakeResponse(502, {"error": "bad gateway"}, {"Content-Type": "application/json"}, text="bad gateway"))

    with pytest.raises(CrmHttpError, match="CRM returned HTTP error"):
        adapter.mark_tags("sales_01", "wm_ext_001", ["bad-tag"])
