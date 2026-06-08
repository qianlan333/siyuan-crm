from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.hxc_dashboard.safe_mode import reset_hxc_safe_mode_fixture_state
from aicrm_next.main import create_app
from tools import check_production_route_resolution as route_checker


def _client(monkeypatch) -> TestClient:
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.delenv("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://hxc:hxc@127.0.0.1:1/hxc")
    monkeypatch.setenv("SECRET_KEY", "hxc-dashboard-route-precedence-test")
    reset_hxc_safe_mode_fixture_state()
    return TestClient(create_app(), raise_server_exceptions=False)


def test_hxc_routes_precede_production_compat_facade(monkeypatch) -> None:

    async def forbidden_forward(request):
        raise AssertionError(f"legacy facade should not handle {request.method} {request.url.path}")
    client = _client(monkeypatch)

    responses = [
        client.get("/admin/hxc-dashboard"),
        client.get("/admin/hxc-send-config"),
        client.get("/api/admin/hxc-dashboard"),
        client.post("/api/admin/hxc-dashboard/refresh", json={"trigger_source": "precedence"}),
        client.post("/api/admin/hxc-dashboard/refresh-directory", json={}),
        client.get("/api/admin/hxc-dashboard/send-config"),
        client.post("/api/admin/hxc-dashboard/broadcast", json={"external_userids": ["wx_ext_001"], "content": "hello"}),
        client.get("/api/admin/hxc-dashboard/unowned"),
    ]

    for response in responses:
        assert response.status_code in {200, 404}
        assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
        assert "X-AICRM-Compatibility-Facade" not in response.headers


def test_route_resolution_samples_lock_hxc_to_next(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "hxc-dashboard-route-resolution-test")
    result = route_checker.run_check()

    assert result["ok"] is True
    samples = {(item["method"], item["path"]): item for item in result["resolution_samples"]}
    for key in (
        ("GET", "/admin/hxc-dashboard"),
        ("GET", "/admin/hxc-send-config"),
        ("GET", "/api/admin/hxc-dashboard"),
        ("POST", "/api/admin/hxc-dashboard/refresh"),
        ("POST", "/api/admin/hxc-dashboard/refresh-directory"),
        ("GET", "/api/admin/hxc-dashboard/send-config"),
        ("POST", "/api/admin/hxc-dashboard/send-config"),
        ("DELETE", "/api/admin/hxc-dashboard/send-config/hxc_sender_fixture"),
        ("POST", "/api/admin/hxc-dashboard/broadcast"),
        ("GET", "/api/admin/hxc-dashboard/unknown"),
    ):
        assert samples[key]["route_owner"] == "next"
        assert samples[key]["endpoint_module"] == "aicrm_next.hxc_dashboard.api"
