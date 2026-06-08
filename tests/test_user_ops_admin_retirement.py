from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_user_ops_admin_page_and_api_routes_are_retired_from_url_map():
    from wecom_ability_service import create_app

    app = create_app({"TESTING": True})
    registered_routes = {rule.rule for rule in app.url_map.iter_rules()}

    assert "/admin/user-ops/ui" not in registered_routes
    assert "/api/admin/user-ops/overview" not in registered_routes
    assert "/api/admin/user-ops/list" not in registered_routes
    assert "/api/admin/user-ops/send-records" not in registered_routes


def test_user_ops_admin_page_is_no_longer_exempt_from_sunset_guard():
    from wecom_ability_service.http import internal_auth

    assert internal_auth._is_sunset_admin_path("/admin/user-ops") is True
    assert internal_auth._is_sunset_admin_path("/admin/user-ops/ui") is True
    assert internal_auth._is_sunset_admin_path("/admin/user-ops/legacy") is True


def test_user_ops_admin_api_prefix_is_retired_before_route_dispatch():
    from wecom_ability_service import create_app

    app = create_app({"TESTING": True})
    client = app.test_client()

    response = client.get("/api/admin/user-ops/overview")
    payload = response.get_json()

    assert response.status_code == 410
    assert payload == {
        "ok": False,
        "error": "gone",
        "message": "user-ops admin page APIs have been retired",
    }


def test_user_ops_admin_frontend_templates_are_deleted():
    assert not (ROOT / "wecom_ability_service" / "templates" / "admin_console" / "user_ops.html").exists()
    assert not (ROOT / "wecom_ability_service" / "templates" / "admin_user_ops.html").exists()
