from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from openclaw_service.integrations.crm.chat_context import build_customer_chat_context
from openclaw_service.integrations.crm.client import CrmApiClient
from openclaw_service.integrations.crm.config import CrmApiConfig
from openclaw_service.integrations.crm.adapters.customers import CustomersAdapter
from openclaw_service.integrations.crm.adapters.messages import MessagesAdapter
from openclaw_service.integrations.crm.adapters.timeline import TimelineAdapter


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


def make_client(*responses: Any, **config_overrides: Any) -> CrmApiClient:
    session = FakeSession(list(responses))
    config = CrmApiConfig(
        base_url="https://crm.example.com",
        api_token="crm-token",
        mcp_bearer_token="mcp-token",
        **config_overrides,
    )
    return CrmApiClient(config, session=session)


def test_customer_adapter_unwraps_customer_envelope() -> None:
    client = make_client(
        FakeResponse(
            200,
            {
                "ok": True,
                "customer": {
                    "external_userid": "wm_ext_001",
                    "customer_name": "Alice",
                    "owner_userid": "sales_01",
                },
            },
            {"Content-Type": "application/json"},
        )
    )

    customer = CustomersAdapter(client).get_customer("wm_ext_001")

    assert customer.external_userid == "wm_ext_001"
    assert customer.name == "Alice"


def test_timeline_adapter_unwraps_timeline_items_envelope() -> None:
    client = make_client(
        FakeResponse(
            200,
            {
                "ok": True,
                "timeline": {
                    "external_userid": "wm_ext_001",
                    "items": [
                        {
                            "event_id": "e-1",
                            "event_type": "message",
                            "occurred_at": "2026-03-24 10:00:00",
                            "summary": "hello",
                        }
                    ],
                },
            },
            {"Content-Type": "application/json"},
        )
    )

    events = TimelineAdapter(client).get_customer_timeline("wm_ext_001")

    assert len(events) == 1
    assert events[0].event_id == "e-1"
    assert events[0].summary == "hello"


def test_build_customer_chat_context_returns_live_when_all_sources_work() -> None:
    client = make_client(
        FakeResponse(
            200,
            {"ok": True, "customer": {"external_userid": "wm_ext_001", "customer_name": "Alice"}},
            {"Content-Type": "application/json"},
        ),
        FakeResponse(
            200,
            {"messages": [{"msgid": "m-1", "content": "hello"}]},
            {"Content-Type": "application/json"},
        ),
        FakeResponse(
            200,
            {"ok": True, "timeline": {"items": [{"event_id": "e-1", "event_type": "message", "summary": "hello"}]}},
            {"Content-Type": "application/json"},
        ),
    )

    context = build_customer_chat_context(
        "wm_ext_001",
        customers=CustomersAdapter(client),
        messages=MessagesAdapter(client),
        timeline=TimelineAdapter(client),
    )

    assert context["source_status"] == "live"
    assert context["degraded"] is False
    assert context["customer"]["external_userid"] == "wm_ext_001"
    assert len(context["recent_messages"]) == 1
    assert len(context["recent_timeline_events"]) == 1


def test_build_customer_chat_context_returns_fallback_when_timeline_degrades() -> None:
    client = make_client(
        FakeResponse(
            200,
            {"ok": True, "customer": {"external_userid": "wm_ext_001", "customer_name": "Alice"}},
            {"Content-Type": "application/json"},
        ),
        FakeResponse(
            200,
            {"messages": [{"msgid": "m-1", "content": "hello"}]},
            {"Content-Type": "application/json"},
        ),
        FakeResponse(
            200,
            {"ok": True, "timeline": {"items": "bad-shape"}},
            {"Content-Type": "application/json"},
        ),
        FakeResponse(
            200,
            {"messages": [{"msgid": "m-1", "send_time": "2026-03-24 11:00:00", "content": "hello"}]},
            {"Content-Type": "application/json"},
        ),
    )

    context = build_customer_chat_context(
        "wm_ext_001",
        customers=CustomersAdapter(client),
        messages=MessagesAdapter(client),
        timeline=TimelineAdapter(client),
    )

    assert context["source_status"] == "fallback"
    assert context["degraded"] is True
    assert len(context["recent_messages"]) == 1
    assert len(context["recent_timeline_events"]) == 1


def test_build_customer_chat_context_returns_degraded_when_customer_missing() -> None:
    client = make_client(
        FakeResponse(404, {"error": "missing"}, {"Content-Type": "application/json"}, text="missing"),
        FakeResponse(404, {"error": "missing"}, {"Content-Type": "application/json"}, text="missing"),
        FakeResponse(
            200,
            {"messages": [{"msgid": "m-1", "content": "hello"}]},
            {"Content-Type": "application/json"},
        ),
        FakeResponse(
            200,
            {"ok": True, "timeline": {"items": []}},
            {"Content-Type": "application/json"},
        ),
        prefer_customer_endpoints=True,
    )

    context = build_customer_chat_context(
        "wm_missing",
        customers=CustomersAdapter(client),
        messages=MessagesAdapter(client),
        timeline=TimelineAdapter(client),
    )

    assert context["degraded"] is True
    assert context["customer"] is None or context["customer"]["status"] == "degraded"
    assert context["recent_messages"] == [{"msgid": "m-1", "content": "hello"}]
    assert context["source_status"] == "fallback"
    assert context["warnings"]
