from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from aicrm_next.frontend_compat.legacy_routes import LEGACY_FRONTEND_ROUTES
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


def test_automation_project_pages_are_served_by_next_native_bundle(monkeypatch) -> None:
    client = _client(monkeypatch)
    urls = [
        "/admin/automation-conversion",
        "/admin/automation-conversion/programs/1/setup?step=basic",
        "/admin/automation-conversion/programs/1/setup?step=entry",
        "/admin/automation-conversion/programs/1/overview",
        "/admin/automation-conversion/programs/1/members",
        "/admin/automation-conversion/programs/1/copy",
        "/admin/automation-conversion/programs/1/entry-channels",
    ]

    for url in urls:
        response = client.get(url)
        assert response.status_code == 200, url
        assert response.headers.get("X-AICRM-Compatibility-Facade") is None, url
        assert "客户管理后台" in response.text
        assert "Not Found" not in response.text

    entry_response = client.get("/admin/automation-conversion/programs/1/setup?step=entry")
    basic_response = client.get("/admin/automation-conversion/programs/1/setup?step=basic")
    assert "/static/automation-engine/admin_console/automation_conversion_workspace.css" in entry_response.text
    assert "/static/automation-engine/admin_console/channel_admission_pages.js" in entry_response.text
    assert 'href="/admin/automation-conversion/programs/1/overview"' in entry_response.text
    assert 'action="/admin/automation-conversion/programs/1/update"' in basic_response.text


def test_automation_project_routes_are_removed_from_frontend_compat_inventory() -> None:
    migrated_routes = {
        "/admin/automation-conversion",
        "/admin/automation-conversion/programs/{program_id}/setup",
        "/admin/automation-conversion/programs/{program_id}/overview",
        "/admin/automation-conversion/programs/{program_id}/members",
        "/admin/automation-conversion/programs/{program_id}/copy",
        "/admin/automation-conversion/programs/{program_id}/entry-channels",
    }
    migrated_group_ops_routes = {
        "/admin/automation-conversion/group-ops/ui",
        "/admin/automation-conversion/group-ops/plans/{plan_id}",
        "/admin/automation-conversion/group-ops/groups/ui",
    }

    assert migrated_routes.isdisjoint(LEGACY_FRONTEND_ROUTES)
    assert migrated_group_ops_routes.isdisjoint(LEGACY_FRONTEND_ROUTES)


def test_automation_project_templates_and_static_are_owned_by_automation_engine() -> None:
    native_templates = {
        "base.html",
        "placeholder.html",
        "automation_program_list.html",
        "automation_program_setup_next.html",
        "automation_program_overview_next.html",
        "automation_program_members.html",
        "automation_program_copy_next.html",
        "automation_conversion_entry_channels.html",
        "_automation_operation_orchestration_panel.html",
    }
    native_static = {
        "automation_conversion_workspace.css",
        "automation_operation_orchestration_panel.js",
    }

    for filename in native_templates:
        assert (AUTOMATION_TEMPLATES / filename).exists()
    for filename in native_static:
        assert (AUTOMATION_STATIC / filename).exists()
        assert not (FRONTEND_STATIC / filename).exists()

    assert not (FRONTEND_TEMPLATES / "automation_program_list.html").exists()
    assert not (FRONTEND_TEMPLATES / "automation_program_setup_next.html").exists()
    assert not (FRONTEND_TEMPLATES / "automation_program_overview_next.html").exists()
    assert not (FRONTEND_TEMPLATES / "automation_program_members.html").exists()
    assert not (FRONTEND_TEMPLATES / "automation_program_copy_next.html").exists()
    assert not (FRONTEND_TEMPLATES / "automation_conversion_entry_channels.html").exists()
    assert not (FRONTEND_TEMPLATES / "_automation_operation_orchestration_panel.html").exists()


def test_automation_native_static_mount_serves_page_assets(monkeypatch) -> None:
    client = _client(monkeypatch)

    response = client.get("/static/automation-engine/admin_console/automation_conversion_workspace.css")

    assert response.status_code == 200
    assert "ac-workspace-tabs" in response.text
