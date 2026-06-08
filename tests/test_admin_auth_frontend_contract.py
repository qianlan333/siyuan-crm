from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from aicrm_next.main import create_app


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "aicrm_next/frontend_compat/templates/admin_console/login.html"


def test_login_template_keeps_next_form_and_wecom_links() -> None:
    source = TEMPLATE.read_text(encoding="utf-8")

    assert "api.admin_login" in source
    assert "login_type" in source
    assert "break_glass" in source
    assert "login_links.qr" in source
    assert "login_links.oauth" in source
    assert "forward_to_legacy_flask" not in source


def test_rendered_login_form_action_points_to_next_login(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    monkeypatch.setenv("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.setenv("SECRET_KEY", "admin-auth-frontend-contract-test")
    monkeypatch.setenv("ADMIN_BREAK_GLASS_LOGIN_ENABLED", "true")
    response = TestClient(create_app(), raise_server_exceptions=False).get("/login")

    assert response.status_code == 200
    assert 'method="post" action="/login"' in response.text
    assert "/auth/wecom/start?mode=qr" in response.text
