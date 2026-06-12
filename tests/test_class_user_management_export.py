from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.main import create_app


def test_class_user_management_export_returns_local_csv_without_external_storage(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("SECRET_KEY", "class-user-management-export-test")
    client = TestClient(create_app())

    response = client.get("/api/admin/class-user-management/export?signup_status=signed")

    assert response.status_code == 200
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert response.headers["X-AICRM-External-Storage-Executed"] == "false"
    assert 'filename="class-user-management.csv"' in response.headers["content-disposition"]
    assert "客户昵称" in response.text
    assert "Class User Local" in response.text
    assert "signed" in response.text
