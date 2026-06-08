from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.main import create_app


def _client() -> TestClient:
    return TestClient(create_app())


def test_user_ops_admin_page_opens_without_legacy_redirect() -> None:
    response = _client().get("/admin/user-ops", follow_redirects=False)

    assert response.status_code == 200
    assert response.headers.get("location") is None
    assert "客户激活" in response.text
    assert "/api/admin/user-ops/overview" in response.text


def test_user_ops_readonly_queries_are_next_native() -> None:
    client = _client()

    overview = client.get("/api/admin/user-ops/overview?tag=黄小璨").json()
    customers = client.get("/api/admin/user-ops/customers?tag=黄小璨&limit=10").json()
    filters = client.get("/api/admin/user-ops/filters").json()
    send_records = client.get("/api/admin/user-ops/send-records").json()

    for payload in [overview, customers, filters]:
        assert payload["ok"] is True
        assert payload["route_owner"] == "ai_crm_next"
        assert payload["fallback_used"] is False
        assert payload["real_external_call_executed"] is False

    assert overview["metrics"]["filtered_total"] == 3
    assert customers["total"] == 3
    assert customers["items"][0]["external_userid"] == "wx_ext_001"
    assert "黄小璨" in filters["filter_options"]["tag"]
    assert send_records["ok"] is True
    assert send_records["records"]
