from __future__ import annotations

from tests.test_admin_config_next import _prepare_client


def _client(monkeypatch, tmp_path):
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("SECRET_KEY", "admin-config-legacy-forwarding-test")
    return _prepare_client(monkeypatch, tmp_path)


def test_admin_config_routes_are_served_by_next_admin_config(monkeypatch, tmp_path):
    import aicrm_next.frontend_compat.legacy_routes as legacy_routes

    class ExplodingRuntimeConfigQuery:
        def __call__(self):
            raise AssertionError("/admin/config must not render real_data_page runtime config")

    async def fake_forward_to_legacy_flask(request):
        raise AssertionError(f"{request.url.path} must not forward to legacy Flask")

    monkeypatch.setattr(legacy_routes, "GetAdminConfigPageQuery", ExplodingRuntimeConfigQuery)
    monkeypatch.setattr(legacy_routes, "forward_to_legacy_flask", fake_forward_to_legacy_flask, raising=False)

    client = _client(monkeypatch, tmp_path)

    expectations = [
        ("get", "/admin/config", 200, "配置中心"),
        ("get", "/admin/config/app-settings", 200, "系统设置"),
        ("get", "/admin/config/login-access", 200, "登录与权限"),
        ("get", "/admin/config/checklist", 200, "配置检查清单"),
        ("get", "/admin/config/mcp-tools", 302, ""),
        ("get", "/admin/config/wecom-tags", 302, ""),
        ("post", "/admin/config/app-settings/save", 302, ""),
        ("post", "/admin/config/login-access/save", 302, ""),
        ("post", "/admin/config/mcp-tools/save", 302, ""),
        ("get", "/setup/wizard", 200, "系统配置向导"),
        ("post", "/setup/wizard/save", 200, "admin_action_token"),
        ("get", "/api/admin/config/app-settings", 200, "next_read_model"),
        ("get", "/api/admin/config/mcp-tools", 200, "next_read_model"),
        ("get", "/api/admin/config/marketing-automation/signup-conversion", 200, "next_read_model"),
        ("put", "/api/admin/config/app-settings", 400, "confirm is required"),
        ("get", "/api/admin/config/routing", 404, "retired"),
        ("post", "/api/admin/config/routing/owner-role", 404, "retired"),
        ("post", "/api/admin/config/routing/rule", 404, "retired"),
        ("get", "/api/admin/config/signup-tags", 404, "retired"),
        ("post", "/api/admin/config/signup-tags", 404, "retired"),
        ("get", "/api/admin/config/class-term-tags", 404, "retired"),
        ("post", "/api/admin/config/class-term-tags", 404, "retired"),
    ]
    for method, path, status_code, marker in expectations:
        request = getattr(client, method)
        response = request(path, json={"settings": {"WECOM_CORP_ID": "ww"}}) if method == "put" else request(path, follow_redirects=False)
        assert response.status_code == status_code, path
        assert "X-AICRM-Compatibility-Facade" not in response.headers
        if marker:
            assert marker in response.text


def test_admin_config_manifest_no_longer_lists_config_center_as_legacy(monkeypatch, tmp_path):
    routes = _client(monkeypatch, tmp_path).get("/api/frontend-compat/legacy-routes").json()["routes"]

    for route in [
        "/admin/config",
        "/admin/config/app-settings",
        "/admin/config/login-access",
        "/admin/config/checklist",
        "/admin/config/mcp-tools",
        "/admin/config/wecom-tags",
        "/setup/wizard",
    ]:
        assert route not in routes
