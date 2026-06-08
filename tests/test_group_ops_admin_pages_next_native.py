from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from aicrm_next.frontend_compat.legacy_routes import LEGACY_FRONTEND_ROUTES
from aicrm_next.main import create_app

ROOT = Path(__file__).resolve().parents[1]
FRONTEND_COMPAT = ROOT / "aicrm_next" / "frontend_compat"
GROUP_OPS_BUNDLE = ROOT / "aicrm_next" / "automation_engine" / "group_ops"


def test_group_ops_admin_pages_render_from_next_native_bundle(monkeypatch) -> None:
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    client = TestClient(create_app())

    list_response = client.get("/admin/automation-conversion/group-ops/ui")
    detail_response = client.get("/admin/automation-conversion/group-ops/plans/7")
    groups_response = client.get("/admin/automation-conversion/group-ops/groups/ui")

    assert list_response.status_code == 200
    assert detail_response.status_code == 200
    assert groups_response.status_code == 200
    assert 'id="group-ops-app"' in list_response.text
    assert 'data-page-mode="list"' in list_response.text
    assert 'data-page-mode="detail"' in detail_response.text
    assert 'data-plan-id="7"' in detail_response.text
    assert 'data-page-mode="groups"' in groups_response.text
    assert "/static/group-ops/admin_console/group_ops.css" in list_response.text
    assert "/static/group-ops/admin_console/group_ops.js" in list_response.text
    assert "admin_console/material_picker.js" in list_response.text
    assert "admin_console/send_content_composer.js" in list_response.text


def test_group_ops_admin_routes_are_removed_from_frontend_compat() -> None:
    retired_routes = {
        "/admin/automation-conversion/group-ops/ui",
        "/admin/automation-conversion/group-ops/plans/{plan_id}",
        "/admin/automation-conversion/group-ops/groups/ui",
    }

    assert retired_routes.isdisjoint(set(LEGACY_FRONTEND_ROUTES))
    assert (GROUP_OPS_BUNDLE / "admin_pages.py").exists()
    assert (GROUP_OPS_BUNDLE / "templates/admin_console/group_ops.html").exists()
    assert (GROUP_OPS_BUNDLE / "static/admin_console/group_ops.css").exists()
    assert (GROUP_OPS_BUNDLE / "static/admin_console/group_ops.js").exists()
    assert not (FRONTEND_COMPAT / "templates/admin_console/group_ops.html").exists()
    assert not (FRONTEND_COMPAT / "static/admin_console/group_ops.css").exists()
    assert not (FRONTEND_COMPAT / "static/admin_console/group_ops.js").exists()

    legacy_source = (FRONTEND_COMPAT / "legacy_routes.py").read_text(encoding="utf-8")
    assert "def admin_group_ops_ui" not in legacy_source
    assert "def admin_group_ops_plan_detail" not in legacy_source
    assert "def admin_group_ops_groups_ui" not in legacy_source
