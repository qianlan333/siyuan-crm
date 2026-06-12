from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.main import create_app


def _client() -> TestClient:
    return TestClient(create_app())


def _endpoint_module(path: str) -> str:
    app = create_app()
    for route in app.routes:
        if getattr(route, "path", "") == path and "GET" in getattr(route, "methods", set()):
            return route.endpoint.__module__
    raise AssertionError(f"missing route for {path}")


def test_user_ops_ui_page_renders_from_native_shell(monkeypatch) -> None:
    from aicrm_next.ops_enrollment import admin_pages

    class FakeAdminFunnelPageQuery:
        def __call__(self) -> dict:
            return {
                "ok": True,
                "source_status": "test_read_model",
                "cards": [{"label": "生产客户", "value": "3", "description": "fixture"}],
                "sections": [{"title": "客户统计", "headers": ["项目", "值"], "rows": [["客户", "3"]]}],
            }

    monkeypatch.setattr(admin_pages, "GetAdminFunnelPageQuery", FakeAdminFunnelPageQuery)

    response = _client().get("/admin/user-ops/ui")

    assert response.status_code == 200
    assert "客户激活 / 客户列表" in response.text
    assert "生产客户、问卷、订单和自动化成员统计" in response.text
    assert "test_read_model" in response.text
    assert "X-AICRM-Compatibility-Facade" not in response.headers


def test_user_ops_workspace_page_renders_from_native_shell() -> None:
    response = _client().get("/admin/user-ops")

    assert response.status_code == 200
    assert "运营管理" in response.text
    for marker in (
        "overview-cards",
        "filter-class-term",
        "filter-keyword",
        "filter-mobile",
        "list-body",
        "batch-send-modal-backdrop",
        "send-records-backdrop",
        "customer-detail-backdrop",
        "preview-batch-send-btn",
        "execute-batch-send-btn",
        "include-dnd-toggle",
        "include-dnd-confirm-toggle",
    ):
        assert marker in response.text
    assert "X-AICRM-Compatibility-Facade" not in response.headers


def test_user_ops_workspace_api_string_contract_is_preserved() -> None:
    response = _client().get("/admin/user-ops")

    assert response.status_code == 200
    for marker in (
        "/api/admin/user-ops/overview",
        "/api/admin/user-ops/list",
        "/api/admin/user-ops/do-not-disturb",
        "/api/admin/user-ops/batch-send/preview",
        "/api/admin/user-ops/batch-send/execute",
        "/api/admin/user-ops/send-records",
        "/api/admin/user-ops/export",
        "/api/admin/miniprogram-library",
        "/api/customers/",
        "/timeline?limit=20",
    ):
        assert marker in response.text


def test_user_ops_admin_page_routes_are_owned_by_native_module() -> None:
    assert _endpoint_module("/admin/user-ops/ui") == "aicrm_next.ops_enrollment.admin_pages"
    assert _endpoint_module("/admin/user-ops") == "aicrm_next.ops_enrollment.admin_pages"


def test_user_ops_pages_removed_from_frontend_compat_inventory() -> None:
    response = _client().get("/api/frontend-compat/legacy-routes")

    assert response.status_code == 404


def test_user_ops_write_like_routes_remain_no_real_side_effect() -> None:
    client = _client()

    preview = client.post(
        "/api/admin/user-ops/batch-send/preview",
        json={"selected_ids": [1], "content": "测试消息"},
    )
    assert preview.status_code == 200
    preview_body = preview.json()
    assert preview_body["side_effect_safety"]["real_wecom_dispatch_executed"] is False
    assert preview_body["side_effect_safety"]["side_effect_executed"] is False

    execute = client.post(
        "/api/admin/user-ops/batch-send/execute",
        json={"selected_ids": [1], "content": "测试消息", "confirm": True},
    )
    assert execute.status_code == 200
    execute_body = execute.json()
    assert execute_body["side_effect_safety"]["real_batch_send_executed"] is False
    assert execute_body["side_effect_safety"]["real_wecom_dispatch_executed"] is False
    assert execute_body["side_effect_safety"]["side_effect_executed"] is False
    assert execute_body["execution_summary"]["side_effect_safety"]["side_effect_executed"] is False

    dnd = client.post(
        "/api/admin/user-ops/do-not-disturb",
        json={"external_userid": "wx_ext_001", "reason_code": "manual_set", "reason_text": "运营设置"},
    )
    assert dnd.status_code == 200
    dnd_body = dnd.json()
    assert dnd_body["side_effect_safety"]["real_dnd_write_executed"] is False
    assert dnd_body["side_effect_safety"]["side_effect_executed"] is False

    refresh = client.post(f"/api/admin/user-ops/send-records/{execute_body['record_id']}/refresh")
    assert refresh.status_code == 200
    refresh_body = refresh.json()
    assert refresh_body["refreshed"] is False
    assert refresh_body["real_external_call_executed"] is False
