from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.main import create_app


def test_user_ops_admin_page_shell_points_to_next_api_routes(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.get("/admin/user-ops")

    assert response.status_code == 200
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert "/api/admin/user-ops/overview" in response.text
    assert "/api/admin/user-ops/list" in response.text
    assert "X-AICRM-Compatibility-Facade" not in response.headers
