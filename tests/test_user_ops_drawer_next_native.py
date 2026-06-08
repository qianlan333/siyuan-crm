from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.main import create_app


def test_user_ops_customer_drawer_and_timeline_are_next_native() -> None:
    client = TestClient(create_app())

    detail_response = client.get("/api/admin/user-ops/customers/wx_ext_001")
    timeline_response = client.get("/api/admin/user-ops/customers/wx_ext_001/timeline?limit=10")

    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["route_owner"] == "ai_crm_next"
    assert detail["fallback_used"] is False
    assert detail["customer"]["external_userid"] == "wx_ext_001"
    assert detail["customer"]["mobile_masked"] == "138****8000"
    assert detail["drawer"]["sections"]

    assert timeline_response.status_code == 200
    timeline = timeline_response.json()
    assert timeline["route_owner"] == "ai_crm_next"
    assert timeline["fallback_used"] is False
    assert timeline["timeline"]
    assert {item["event_type"] for item in timeline["timeline"]} >= {"lead_pool.created", "activation.status"}
