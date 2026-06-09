from __future__ import annotations

from fastapi.testclient import TestClient


def test_auth_wecom_start_is_exact_next_blocked_route_by_default(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    from aicrm_next.main import create_app

    client = TestClient(create_app())

    response = client.get("/auth/wecom/start?mode=qr&next=/admin/config")
    payload = response.json()

    assert response.status_code == 503
    assert response.headers.get("X-AICRM-Compatibility-Facade") is None
    assert payload["error_code"] == "auth_wecom_blocked"
    assert payload["auth_step"] == "wecom_sso_start"
    assert payload["route_owner"] == "ai_crm_next"
    assert payload["source_status"] == "auth_wecom_blocked"
    assert payload["adapter_mode"] == "blocked"
    assert payload["fallback_used"] is False
    assert payload["real_external_call_executed"] is False


def test_auth_wecom_callback_missing_code_is_bad_request(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    from aicrm_next.main import create_app

    client = TestClient(create_app())

    response = client.get("/auth/wecom/callback")
    payload = response.json()

    assert response.status_code == 400
    assert payload["error_code"] == "missing_wecom_code"
    assert payload["route_owner"] == "ai_crm_next"
    assert payload["fallback_used"] is False
    assert payload["real_external_call_executed"] is False


def test_auth_wecom_exact_options_return_next_owner_diagnostics() -> None:
    from aicrm_next.main import create_app

    client = TestClient(create_app())

    for path in ["/auth/wecom/start", "/auth/wecom/callback"]:
        response = client.options(path)
        payload = response.json()

        assert response.status_code == 200
        assert payload["source_status"] == "next_auth_wecom_exact"
        assert payload["route_owner"] == "ai_crm_next"
        assert payload["fallback_used"] is False
        assert payload["real_external_call_executed"] is False


def test_auth_wecom_exact_routes_are_registered_before_production_compat_wildcard(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    from aicrm_next.main import create_app

    app = create_app()
    by_path = {getattr(route, "path", ""): route for route in app.routes}

    for path in ["/auth/wecom/start", "/auth/wecom/callback"]:
        endpoint = getattr(by_path[path], "endpoint", None)
        assert getattr(endpoint, "__module__", "") == "aicrm_next.auth_wecom.api"
