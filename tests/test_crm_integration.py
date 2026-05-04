from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
import requests

from openclaw_service.integrations.crm.client import CrmApiClient
from openclaw_service.integrations.crm.config import CrmApiConfig
from openclaw_service.integrations.crm.errors import CrmBusinessError, CrmHttpError, CrmTransportError
from openclaw_service.integrations.crm.adapters.batches import BatchesAdapter
from openclaw_service.integrations.crm.adapters.customers import CustomersAdapter
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


def make_client(*responses: Any, **config_overrides: Any) -> tuple[CrmApiClient, FakeSession]:
    session = FakeSession(list(responses))
    config = CrmApiConfig(
        base_url="https://crm.example.com",
        api_token="crm-token",
        mcp_bearer_token="mcp-token",
        **config_overrides,
    )
    return CrmApiClient(config, session=session), session


def test_crm_client_sets_auth_headers_and_request_id() -> None:
    client, session = make_client(FakeResponse(200, {"ok": True}, {"Content-Type": "application/json"}))

    payload = client.get("/api/contacts")

    assert payload == {"ok": True}
    headers = session.calls[0]["headers"]
    assert headers["Authorization"] == "Bearer crm-token"
    assert headers["X-OpenClaw-Source"] == "openclaw-cloud"
    assert headers["X-Request-Id"]


def test_crm_client_retries_retryable_http_errors_for_get() -> None:
    client, session = make_client(
        FakeResponse(503, {"error": "busy"}, {"Content-Type": "application/json"}, text="busy"),
        FakeResponse(200, {"items": []}, {"Content-Type": "application/json"}),
    )

    payload = client.get("/api/customers")

    assert payload == {"items": []}
    assert len(session.calls) == 2


def test_crm_client_raises_transport_error() -> None:
    client, _ = make_client(requests.Timeout("boom"), max_retries=0)

    with pytest.raises(CrmTransportError):
        client.get("/api/customers")


def test_crm_client_raises_http_error() -> None:
    client, _ = make_client(FakeResponse(404, {"error": "missing"}, {"Content-Type": "application/json"}, text="missing"))

    with pytest.raises(CrmHttpError):
        client.get("/api/customers/abc")


def test_crm_client_raises_business_error() -> None:
    client, _ = make_client(FakeResponse(200, {"ok": False, "error": "denied"}, {"Content-Type": "application/json"}))

    with pytest.raises(CrmBusinessError):
        client.get("/api/customers")


def test_customers_adapter_falls_back_to_contacts() -> None:
    client, _ = make_client(
        FakeResponse(503, {"error": "busy"}, {"Content-Type": "application/json"}, text="busy"),
        FakeResponse(
            200,
            {
                "items": [
                    {
                        "external_userid": "wm_ext_001",
                        "customer_name": "Alice",
                        "owner_userid": "sales_01",
                        "tags": [{"tag_name": "vip"}],
                        "is_bound": True,
                        "updated_at": "2026-03-24 10:00:00",
                    }
                ]
            },
            {"Content-Type": "application/json"},
        ),
        prefer_customer_endpoints=True,
    )

    adapter = CustomersAdapter(client)
    customers = adapter.list_customers({"owner_userid": "sales_01"})

    assert len(customers) == 1
    assert customers[0].external_userid == "wm_ext_001"
    assert customers[0].tags == ["vip"]


def test_timeline_adapter_falls_back_to_recent_messages() -> None:
    client, _ = make_client(
        FakeResponse(404, {"error": "missing"}, {"Content-Type": "application/json"}, text="missing"),
        FakeResponse(
            200,
            {
                "messages": [
                    {
                        "msgid": "m-1",
                        "send_time": "2026-03-24 11:00:00",
                        "content": "hello",
                    }
                ]
            },
            {"Content-Type": "application/json"},
        ),
        prefer_timeline_endpoint=True,
    )

    adapter = TimelineAdapter(client)
    events = adapter.get_customer_timeline("wm_ext_001", limit=10)

    assert len(events) == 1
    assert events[0].event_type == "message"
    assert events[0].source == "legacy_messages"


def test_batches_adapter_uses_mcp_transport() -> None:
    client, session = make_client(
        FakeResponse(
            200,
            {
                "result": {
                    "structuredContent": {
                        "batch": {
                            "id": 123,
                            "status": "pending",
                            "created_at": "2026-03-24 12:00:00",
                        },
                        "messages": [{"msgid": "m-1"}],
                    }
                }
            },
            {"Content-Type": "application/json"},
        )
    )

    adapter = BatchesAdapter(client)
    batch = adapter.get_message_batch(123)

    assert batch.batch_id == "123"
    assert batch.status == "pending"
    assert batch.items == [{"msgid": "m-1"}]
    assert session.calls[0]["headers"]["Authorization"] == "Bearer mcp-token"


def test_batches_adapter_reads_signup_conversion_payloads() -> None:
    client, _ = make_client(
        FakeResponse(
            200,
            {
                "result": {
                    "structuredContent": {
                        "items": [{"batch_id": 11, "candidate_count": 1}],
                        "count": 1,
                    }
                }
            },
            {"Content-Type": "application/json"},
        ),
        FakeResponse(
            200,
            {
                "result": {
                    "structuredContent": {
                        "batch": {"batch_id": 11},
                        "candidate_count": 1,
                        "candidates": [{"external_userid": "wm_ext_001", "marketing_profile": {"routing": {"reason": "pending_text_message_batch"}}}],
                    }
                }
            },
            {"Content-Type": "application/json"},
        ),
        FakeResponse(
            200,
            {
                "result": {
                    "structuredContent": {
                        "customer": {"external_userid": "wm_ext_001"},
                        "routing": {"reason": "eligible_by_router"},
                    }
                }
            },
            {"Content-Type": "application/json"},
        ),
        FakeResponse(
            200,
            {
                "result": {
                    "structuredContent": {
                        "batch_id": 11,
                        "acknowledged_count": 1,
                        "dispatch_logs": [{"external_userid": "wm_ext_001", "dispatch_status": "acked"}],
                    }
                }
            },
            {"Content-Type": "application/json"},
        ),
    )

    adapter = BatchesAdapter(client)
    batches = adapter.get_pending_conversion_batches(limit=10)
    detail = adapter.get_conversion_batch(11)
    profile = adapter.get_customer_marketing_profile(external_userid="wm_ext_001")
    acked = adapter.ack_conversion_batch(11, acked_by="openclaw")

    assert batches["count"] == 1
    assert batches["items"][0]["batch_id"] == 11
    assert detail["candidate_count"] == 1
    assert detail["candidates"][0]["external_userid"] == "wm_ext_001"
    assert detail["candidates"][0]["marketing_profile"]["routing"]["reason"] == "pending_text_message_batch"
    assert profile["customer"]["external_userid"] == "wm_ext_001"
    assert acked["acknowledged_count"] == 1
    assert acked["dispatch_logs"][0]["dispatch_status"] == "acked"
