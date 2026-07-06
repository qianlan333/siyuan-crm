from __future__ import annotations

from fastapi.testclient import TestClient
from starlette.routing import Match

from aicrm_next.main import create_app


def _client(monkeypatch) -> TestClient:
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("SECRET_KEY", "admin-shell-native-test")
    return TestClient(create_app())


def _route_owner(client: TestClient, path: str, method: str = "GET") -> str:
    scope = {"type": "http", "path": path, "method": method, "root_path": "", "query_string": b""}
    for route in client.app.routes:
        match, _ = route.matches(scope)
        if match is Match.FULL:
            endpoint = getattr(route, "endpoint", None)
            if endpoint is None:
                for candidate in getattr(route, "_effective_candidates", ()):
                    if getattr(candidate, "path", "") == path:
                        endpoint = getattr(candidate, "endpoint", None)
                        break
            return getattr(endpoint, "__module__", "")
    return ""


def test_admin_shell_family_routes_resolve_to_native_module(monkeypatch) -> None:
    client = _client(monkeypatch)

    assert _route_owner(client, "/admin") == "aicrm_next.admin_shell.routes"
    assert _route_owner(client, "/admin/data-health") == "aicrm_next.admin_shell.routes"
    assert _route_owner(client, "/admin/data-quality") == "aicrm_next.admin_shell.routes"
    assert _route_owner(client, "/admin/delivery-lineage") == "aicrm_next.admin_shell.routes"
    assert _route_owner(client, "/admin/growth-orchestration") == "aicrm_next.admin_shell.routes"
    assert _route_owner(client, "/api/admin/dashboard/shell-context") == "aicrm_next.admin_shell.routes"
    assert _route_owner(client, "/admin/logout") == "aicrm_next.admin_shell.routes"


def test_admin_dashboard_page_uses_native_shell_template(monkeypatch) -> None:
    response = _client(monkeypatch).get("/admin")
    html = response.text

    assert response.status_code == 200
    assert "X-AICRM-Compatibility-Facade" not in response.headers
    assert "客户管理后台" in html
    assert 'data-admin-shell-source="next_admin_shell"' in html
    assert "Frontend parity" in html
    assert "后台 shell 已切换为分组导航与生产数据入口。" in html
    assert 'data-shell-context-url="/api/admin/dashboard/shell-context"' in html
    assert 'href="/admin/data-health"' in html
    assert 'href="/admin/data-quality"' in html
    assert 'href="/admin/delivery-lineage"' in html
    assert 'href="/admin/growth-orchestration"' in html
    assert "数据健康" in html
    assert "数据质量规则" in html
    assert "投递排障" in html
    assert "增长运营" in html
    assert 'href="/admin/automation-conversion"' in html
    assert 'href="/admin/customers"' in html


def test_admin_shell_context_api_exposes_native_states(monkeypatch) -> None:
    response = _client(monkeypatch).get("/api/admin/dashboard/shell-context")
    payload = response.json()

    assert response.status_code == 200
    assert "X-AICRM-Compatibility-Facade" not in response.headers
    assert payload["ok"] is True
    assert payload["source_status"] == "next_admin_shell"
    assert payload["fallback_used"] is False
    assert payload["real_external_call_executed"] is False
    assert payload["shell_status"]["health"]["detail"] == "next_admin_shell"
    assert payload["loading_state"]["label"]
    assert payload["empty_state"]["title"]
    assert payload["error_state"]["title"]
    assert any(
        item["href"] == "/admin/automation-conversion"
        for group in payload["nav_groups"]
        for item in group["items"]
    )
    assert any(
        item["href"] == "/admin/data-health"
        for group in payload["nav_groups"]
        for item in group["items"]
    )
    assert any(
        item["href"] == "/admin/data-quality"
        for group in payload["nav_groups"]
        for item in group["items"]
    )
    assert any(
        item["href"] == "/admin/delivery-lineage"
        for group in payload["nav_groups"]
        for item in group["items"]
    )
    assert any(
        item["href"] == "/admin/growth-orchestration"
        for group in payload["nav_groups"]
        for item in group["items"]
    )


def test_admin_data_health_page_renders_summary_cards(monkeypatch) -> None:
    response = _client(monkeypatch).get("/admin/data-health")
    html = response.text

    assert response.status_code == 200
    assert "X-AICRM-Compatibility-Facade" not in response.headers
    assert "健康概况" in html
    assert "schema_drift_guard" in html
    assert "待接入" in html
    assert 'href="/api/admin/data-health/summary"' in html


def test_admin_data_quality_page_renders_registry_dashboard(monkeypatch) -> None:
    response = _client(monkeypatch).get("/admin/data-quality")
    html = response.text

    assert response.status_code == 200
    assert "X-AICRM-Compatibility-Facade" not in response.headers
    assert "规则概况" in html
    assert "identity_pending_queue_threshold" in html
    assert "payment_paid_order_missing_identity" in html
    assert "customer_projection_timeline_missing_recent_activity" in html
    assert "待接探针" in html
    assert 'href="/api/admin/data-quality/summary"' in html
    assert "raw_payload_json" not in html
    assert "external_userid_value" not in html


def test_admin_delivery_lineage_page_renders_query_form(monkeypatch) -> None:
    response = _client(monkeypatch).get("/admin/delivery-lineage?trace_id=trace-1")
    html = response.text

    assert response.status_code == 200
    assert "X-AICRM-Compatibility-Facade" not in response.headers
    assert "查询条件" in html
    assert "broadcast_job_id" in html
    assert "external_effect_job_id" in html
    assert "trace-1" in html
    assert "payload_json" not in html
    assert 'href="/api/admin/delivery-lineage"' in html


def test_admin_growth_orchestration_page_renders_read_model_sections(monkeypatch) -> None:
    response = _client(monkeypatch).get("/admin/growth-orchestration")
    html = response.text

    assert response.status_code == 200
    assert "X-AICRM-Compatibility-Facade" not in response.headers
    assert "增长运营" in html
    assert "Programs" in html
    assert "Members" in html
    assert "Tasks" in html
    assert "Touchpoints" in html
    assert "只展示 read model" in html
    assert 'href="/api/admin/growth-orchestration/programs"' in html
    assert "external_userid" not in html


def test_admin_growth_orchestration_detail_page_renders_program_key(monkeypatch) -> None:
    response = _client(monkeypatch).get("/admin/growth-orchestration/campaign:c-1")
    html = response.text

    assert response.status_code == 200
    assert "X-AICRM-Compatibility-Facade" not in response.headers
    assert "campaign:c-1" in html
    assert 'href="/admin/growth-orchestration"' in html


def test_admin_logout_legacy_url_redirects_to_canonical_logout(monkeypatch) -> None:
    response = _client(monkeypatch).get("/admin/logout", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/logout"
    assert "X-AICRM-Compatibility-Facade" not in response.headers


def test_frontend_compat_legacy_inventory_endpoint_removed(monkeypatch) -> None:
    response = _client(monkeypatch).get("/api/frontend-compat/legacy-routes")

    assert response.status_code == 404
