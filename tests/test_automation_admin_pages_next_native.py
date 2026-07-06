from __future__ import annotations

from pathlib import Path
from time import time

from fastapi.testclient import TestClient

from aicrm_next.admin_auth.service import SESSION_COOKIE, sign_session
from aicrm_next.main import create_app


ROOT = Path(__file__).resolve().parents[1]
AUTOMATION_TEMPLATES = ROOT / "aicrm_next" / "automation_engine" / "templates" / "admin_console"
AUTOMATION_STATIC = ROOT / "aicrm_next" / "automation_engine" / "static" / "admin_console"
FRONTEND_TEMPLATES = ROOT / "aicrm_next" / "frontend_compat" / "templates" / "admin_console"
FRONTEND_STATIC = ROOT / "aicrm_next" / "frontend_compat" / "static" / "admin_console"


def _client(monkeypatch) -> TestClient:
    monkeypatch.setenv("SECRET_KEY", "automation-admin-pages-next-native-test")
    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    return TestClient(create_app(), raise_server_exceptions=False)


def _admin_cookies() -> dict[str, str]:
    return {
        SESSION_COOKIE: sign_session(
            {
                "auth_source": "break_glass",
                "login_type": "break_glass",
                "username": "admin",
                "display_name": "admin",
                "roles": ["super_admin"],
                "iat": int(time()),
            }
        )
    }


def test_retired_automation_project_pages_return_gone(monkeypatch) -> None:
    client = _client(monkeypatch)
    urls = [
        "/admin/automation-conversion/programs/1/setup?step=basic",
        "/admin/automation-conversion/programs/1/setup?step=entry",
        "/admin/automation-conversion/programs/1/overview",
        "/admin/automation-conversion/programs/1/members",
        "/admin/automation-conversion/programs/1/copy",
        "/admin/automation-conversion/programs/1/entry-channels",
    ]

    for url in urls:
        response = client.get(url, cookies=_admin_cookies())
        assert response.status_code == 410, url
        assert "旧自动化运营方案页面已下架，请使用 AI 自动化运营人群包" in response.text

    list_response = client.get("/admin/automation-conversion", cookies=_admin_cookies())
    assert list_response.status_code == 200
    assert "AI 自动化运营" in list_response.text
    assert "人群包列表" in list_response.text
    assert "人群包名称" in list_response.text
    assert "最后一次刷新时间" in list_response.text
    assert "刷新方式" in list_response.text
    assert "方案列表" not in list_response.text
    assert "数据概览" not in list_response.text
    assert "/api/admin/ai-audience/packages" in list_response.text
    assert "AICRM_AI_AUDIENCE_API_TOKEN" not in list_response.text
    assert "/api/ai/audience/packages" not in list_response.text

    legacy_response = client.get("/admin/automation-conversion/legacy", cookies=_admin_cookies())
    assert legacy_response.status_code == 404


def test_retired_automation_project_pages_require_admin_session(monkeypatch) -> None:
    client = _client(monkeypatch)

    response = client.get("/admin/automation-conversion/programs/1/setup", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/login?next=/admin/automation-conversion/programs/1/setup"


def test_ai_audience_admin_pages_require_admin_session(monkeypatch) -> None:
    client = _client(monkeypatch)

    page_response = client.get("/admin/automation-conversion", follow_redirects=False)
    legacy_response = client.get("/admin/automation-conversion/legacy", follow_redirects=False)

    assert page_response.status_code == 302
    assert page_response.headers["location"] == "/login?next=/admin/automation-conversion"
    assert legacy_response.status_code == 404


def test_automation_project_routes_are_removed_from_frontend_compat_inventory() -> None:
    assert not (ROOT / "aicrm_next/frontend_compat/legacy_routes.py").exists()


def test_retired_automation_project_templates_and_static_are_removed() -> None:
    retained_templates = {
        "base.html",
        "placeholder.html",
    }
    retired_templates = {
        "automation_program_list.html",
        "automation_program_setup_next.html",
        "automation_program_overview_next.html",
        "automation_program_members.html",
        "automation_program_copy_next.html",
        "automation_conversion_entry_channels.html",
    }
    retired_static = {"automation_conversion_workspace.css"}

    for filename in retained_templates:
        assert (AUTOMATION_TEMPLATES / filename).exists()

    for filename in retired_templates:
        assert not (AUTOMATION_TEMPLATES / filename).exists()
        assert not (FRONTEND_TEMPLATES / filename).exists()

    for filename in retired_static:
        assert not (AUTOMATION_STATIC / filename).exists()
        assert not (FRONTEND_STATIC / filename).exists()


def test_retired_action_template_modules_are_removed() -> None:
    retired_modules = {
        ROOT / "aicrm_next" / "automation_engine" / "action_templates.py",
        ROOT / "aicrm_next" / "automation_engine" / "action_template_repository.py",
        ROOT / "aicrm_next" / "automation_engine" / "action_template_sqlalchemy_repository.py",
    }

    for module in retired_modules:
        assert not module.exists()

    dto_source = (ROOT / "aicrm_next" / "automation_engine" / "dto.py").read_text(encoding="utf-8")
    api_docs_source = (ROOT / "aicrm_next" / "admin_config" / "api_docs_view_model.py").read_text(encoding="utf-8")

    assert "ActionTemplateListRequest" not in dto_source
    assert "ActionTemplateCreateRequest" not in dto_source
    assert "ActionTemplateValidationError" not in dto_source
    assert '"action-templates"' not in api_docs_source


def test_retired_automation_workspace_static_asset_is_gone(monkeypatch) -> None:
    client = _client(monkeypatch)

    response = client.get("/static/automation-engine/admin_console/automation_conversion_workspace.css")

    assert response.status_code == 404
