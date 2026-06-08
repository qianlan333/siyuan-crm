from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.main import create_app
from tools import check_production_route_resolution as route_checker


def test_login_logout_precede_production_compat_facade(monkeypatch) -> None:

    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.delenv("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://auth:auth@127.0.0.1:1/auth")
    monkeypatch.setenv("SECRET_KEY", "admin-auth-route-precedence-test")

    async def forbidden_forward(request):
        raise AssertionError(f"legacy facade should not handle {request.method} {request.url.path}")
    client = TestClient(create_app(), raise_server_exceptions=False)

    for response in [
        client.get("/login"),
        client.post("/login", data={"login_type": "break_glass", "username": "bad", "password": "bad"}),
        client.options("/login"),
        client.get("/logout", follow_redirects=False),
        client.options("/logout"),
    ]:
        assert response.status_code in {200, 302, 401}
        assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
        assert "X-AICRM-Compatibility-Facade" not in response.headers


def test_route_resolution_samples_lock_admin_auth_to_next(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "admin-auth-route-resolution-test")
    result = route_checker.run_check()
    samples = {(item["method"], item["path"]): item for item in result["resolution_samples"]}

    for key in (("GET", "/login"), ("POST", "/login"), ("OPTIONS", "/login"), ("GET", "/logout"), ("OPTIONS", "/logout")):
        assert samples[key]["route_owner"] == "next"
        assert samples[key]["endpoint_module"] == "aicrm_next.admin_auth.api"
    assert samples[("GET", "/auth/wecom/start")]["endpoint_module"] == "aicrm_next.auth_wecom.api"
