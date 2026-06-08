from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.main import create_app


def test_user_ops_cards_are_built_by_next_query_service() -> None:
    response = TestClient(create_app()).get("/api/admin/user-ops/cards?tag=黄小璨")

    assert response.status_code == 200
    payload = response.json()
    assert payload["route_owner"] == "ai_crm_next"
    assert payload["fallback_used"] is False
    cards = {card["key"]: card["value"] for card in payload["cards"]}
    assert cards["lead_pool_total_count"] == 3
    assert cards["wecom_added_count"] == 3
    assert cards["pending_input_count"] == 1
