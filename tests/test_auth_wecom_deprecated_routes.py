from __future__ import annotations

from fastapi.testclient import TestClient


def test_unknown_auth_wecom_and_h5_oauth_routes_are_explicit_deprecated_responses() -> None:
    from aicrm_next.main import create_app

    client = TestClient(create_app())

    expected_replacements = {
        "/api/h5/wechat/oauth/unknown": "/api/h5/wechat/oauth/start",
        "/auth/wecom/unknown": "/auth/wecom/start",
    }
    for path, replacement_route in expected_replacements.items():
        response = client.get(path)
        payload = response.json()

        assert response.status_code == 410
        assert response.headers.get("X-AICRM-Compatibility-Facade") is None
        assert payload["error_code"] == "auth_route_deprecated"
        assert payload["source_status"] == "deprecated"
        assert payload["replacement_route"] == replacement_route
        assert payload["route_owner"] == "ai_crm_next"
        assert payload["fallback_used"] is False
        assert payload["real_external_call_executed"] is False


def test_unknown_deprecated_options_do_not_fall_to_wildcard() -> None:
    from aicrm_next.main import create_app

    client = TestClient(create_app())

    for path in ["/api/h5/wechat/oauth/unknown", "/auth/wecom/unknown"]:
        response = client.options(path)
        payload = response.json()

        assert response.status_code == 200
        assert payload["source_status"] == "next_auth_wecom_exact"
        assert payload["fallback_used"] is False


def test_random_auth_wecom_and_h5_oauth_subpaths_do_not_legacy_forward(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    from aicrm_next.main import create_app

    client = TestClient(create_app())

    for path in ["/api/h5/wechat/oauth/random-not-registered", "/auth/wecom/random-not-registered"]:
        response = client.get(path)

        assert response.status_code == 404
        assert response.headers.get("X-AICRM-Compatibility-Facade") is None
