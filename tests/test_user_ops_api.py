from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.main import create_app
from aicrm_next.ops_enrollment.application import reset_user_ops_fixture_state


def _client(monkeypatch) -> TestClient:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)
    reset_user_ops_fixture_state()
    return TestClient(create_app(), raise_server_exceptions=False)


def _assert_next(payload: dict) -> None:
    assert payload["route_owner"] == "ai_crm_next"
    assert payload["fallback_used"] is False
    assert payload["real_external_call_executed"] is False


def test_user_ops_read_routes_use_next_fixtures(monkeypatch):
    client = _client(monkeypatch)

    overview = client.get("/api/admin/user-ops/overview")
    cards = client.get("/api/admin/user-ops/cards")
    filters = client.get("/api/admin/user-ops/filters")
    customers = client.get("/api/admin/user-ops/customers?limit=5")

    for response in (overview, cards, filters, customers):
        assert response.status_code == 200
        _assert_next(response.json())
        assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"

    assert overview.json()["cards"]
    assert cards.json()["cards"]
    assert filters.json()["filter_options"]["wecom_status"]
    assert customers.json()["items"]


def test_user_ops_customer_detail_and_timeline_are_next_owned(monkeypatch):
    client = _client(monkeypatch)
    first = client.get("/api/admin/user-ops/customers?limit=1").json()["items"][0]
    external_userid = first["external_userid"]

    detail = client.get(f"/api/admin/user-ops/customers/{external_userid}")
    timeline = client.get(f"/api/admin/user-ops/customers/{external_userid}/timeline")

    for response in (detail, timeline):
        assert response.status_code == 200
        _assert_next(response.json())

    assert detail.json()["customer"]["external_userid"] == external_userid
    assert timeline.json()["items"]


def test_user_ops_preview_routes_plan_without_real_external_calls(monkeypatch):
    client = _client(monkeypatch)
    first = client.get("/api/admin/user-ops/customers?limit=1").json()["items"][0]

    batch = client.post(
        "/api/admin/user-ops/batch-send/preview",
        json={"selection_mode": "manual", "selected_ids": [first["id"]], "content": "hello"},
    )
    broadcast = client.post(
        "/api/admin/user-ops/broadcast/preview",
        json={"message": {"text": "hello"}, "selection_mode": "manual", "selected_ids": [first["id"]]},
    )
    export = client.post(
        "/api/admin/user-ops/export/preview",
        json={"filters": {}, "fields": ["customer_name", "mobile"]},
    )

    for response in (batch, broadcast, export):
        assert response.status_code == 200
        payload = response.json()
        assert payload["ok"] is True
        assert payload.get("real_external_call_executed", False) is False
        safety = payload.get("side_effect_safety") or {}
        assert safety.get("side_effect_executed", False) is False
        assert payload.get("fallback_used", False) is False
