from __future__ import annotations

from wecom_ability_service.domains.admin_auth import admin_role_can_access_module
from wecom_ability_service.domains.admin_dashboard.service import ADMIN_NAV_ITEMS
from wecom_ability_service.http.internal_auth import _module_for_admin_api_path, _module_for_admin_path


def test_non_super_admin_roles_can_see_current_sidebar_modules():
    roles = ["automation_admin", "questionnaire_admin", "config_admin", "viewer"]
    hidden = [
        item["key"]
        for item in ADMIN_NAV_ITEMS
        if not admin_role_can_access_module(roles, str(item["key"]))
    ]
    assert hidden == []


def test_new_admin_routes_map_to_specific_rbac_modules_before_admin_fallback():
    assert _module_for_admin_path("/admin/cloud-orchestrator/campaigns") == "cloud_orchestrator"
    assert _module_for_admin_path("/admin/hxc-dashboard") == "user_ops_funnel"
    assert _module_for_admin_path("/admin/image-library") == "image_library"
    assert _module_for_admin_path("/admin/jobs") == "jobs"
    assert _module_for_admin_api_path("/api/admin/hxc-dashboard/refresh") == "user_ops_funnel"
    assert _module_for_admin_api_path("/api/admin/image-library/upload") == "image_library"
    assert _module_for_admin_api_path("/api/admin/jobs/summary") == "jobs"
