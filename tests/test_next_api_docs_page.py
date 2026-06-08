from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.frontend_compat.api_docs_view_model import build_api_docs_view_model
from aicrm_next.frontend_compat.legacy_routes import router as frontend_compat_router
from aicrm_next.main import create_app


def _client(monkeypatch) -> TestClient:
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("SECRET_KEY", "next-api-docs-page-test")
    return TestClient(create_app())


def _endpoint_paths(view_model: dict) -> set[tuple[str, str]]:
    paths: set[tuple[str, str]] = set()
    for group in view_model["endpoint_groups"]:
        for endpoint in group.get("endpoints") or []:
            paths.add((endpoint["method"], endpoint["path"]))
        for subsection in group.get("subsections") or []:
            for endpoint in subsection.get("endpoints") or []:
                paths.add((endpoint["method"], endpoint["path"]))
    return paths


def test_api_docs_view_model_scans_current_fastapi_routes() -> None:
    view_model = build_api_docs_view_model(frontend_router=frontend_compat_router)
    paths = _endpoint_paths(view_model)
    group_titles = {group["title"] for group in view_model["endpoint_groups"]}

    assert view_model["source_status"] == "fastapi_route_registry"
    assert view_model["endpoint_count"] > 80
    assert {
        "系统 / MCP",
        "认证 / 回调",
        "客户 / 身份 / 侧边栏",
        "渠道码中心",
        "问卷",
        "用户运营 / 激活",
        "自动化运营",
        "群运营计划",
        "企微标签",
        "素材 / 发送内容",
        "交易 / 商品",
        "AI 助手 / 兼容代理",
    }.issubset(group_titles)
    for expected in [
        ("GET", "/health"),
        ("GET", "/api/system/health"),
        ("GET", "/mcp"),
        ("POST", "/mcp"),
        ("GET", "/api/admin/dashboard/shell-context"),
        ("GET", "/api/customers/{external_userid}/timeline"),
        ("GET", "/api/sidebar/contact-binding-status"),
        ("GET", "/api/admin/channels/{channel_id}/contacts"),
        ("GET", "/api/admin/questionnaires/{questionnaire_id}/latest-submit-debug"),
        ("POST", "/api/admin/user-ops/batch-send/execute"),
        ("GET", "/api/admin/automation-conversion/contract"),
        ("PUT", "/api/admin/automation-conversion/tasks/{task_id}/send-content/unified"),
        ("POST", "/api/admin/automation-conversion/group-ops/plans/{plan_id}/run-due"),
        ("POST", "/api/automation/group-ops/webhooks/{webhook_key}"),
        ("POST", "/api/admin/wecom/tags/live/mark"),
        ("POST", "/api/admin/image-library/upload"),
        ("GET", "/api/products/{page_slug}"),
        ("GET", "/p/{page_slug}"),
        ("POST", "/api/checkout/wechat"),
        ("GET", "/api/admin/ai-assist/contract"),
        ("POST", "/api/admin/cloud-orchestrator/campaigns/run-due"),
    ]:
        assert expected in paths


def test_admin_api_docs_page_renders_rich_docs_not_real_data_table(monkeypatch) -> None:
    response = _client(monkeypatch).get("/admin/api-docs")
    html = response.text

    assert response.status_code == 200
    assert "Agent 接入指南" in html
    assert "API 快速索引" in html
    assert "复制全部 API 文档" in html
    assert "复制此分组（MD）" in html
    assert "/api/admin/automation-conversion/contract" in html
    assert "/api/admin/automation-conversion/group-ops/plans" in html
    assert "/api/admin/image-library/upload" in html
    assert "/api/products/{page_slug}" in html
    assert "data-real-data-table" not in html
    assert "real-data-table" not in html
    assert "复制全部 219 个接口" not in html
