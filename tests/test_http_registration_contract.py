from __future__ import annotations

import ast
import importlib
from pathlib import Path

from flask import Blueprint

from wecom_ability_service.http import HTTP_ROUTE_MODULES, HTTP_ROUTE_PLACEMENT, bp, register_http_routes


ROOT = Path(__file__).resolve().parents[1]
HTTP_REQUESTS_ALLOWLIST = {
    "wecom_ability_service.http.automation_conversion",
}


def test_routes_py_has_no_direct_bp_route_decorators():
    route_file = Path(__file__).resolve().parents[1] / "wecom_ability_service" / "routes.py"
    module = ast.parse(route_file.read_text(encoding="utf-8"))

    for node in ast.walk(module):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute):
            continue
        if func.attr != "route":
            continue
        owner = func.value
        if isinstance(owner, ast.Name) and owner.id == "bp":
            raise AssertionError("routes.py must not register routes directly")


def test_http_registration_exports_single_registry_contract():
    assert isinstance(bp, Blueprint)
    assert bp.name == "api"
    assert callable(register_http_routes)
    assert {
        "sidebar",
        "identity",
        "ops",
        "settings",
        "customer_center",
        "customer_timeline",
        "archive",
        "contacts",
        "group_chats",
        "callbacks",
        "tasks",
        "tags",
        "admin_user_ops",
        "admin_class_user",
        "admin_questionnaires",
        "public_questionnaires",
    }.issubset(HTTP_ROUTE_MODULES.keys())
    assert {"customer", "admin", "callbacks", "ops_settings"} == set(HTTP_ROUTE_PLACEMENT.keys())


def test_http_controller_modules_do_not_import_raw_sql_or_http_clients():
    forbidden_import_targets = {
        ("requests", None),
        ("wecom_ability_service.wecom_client", "WeComClient"),
    }

    for module_path in HTTP_ROUTE_MODULES.values():
        module = importlib.import_module(module_path)
        source_path = Path(module.__file__).resolve()
        parsed = ast.parse(source_path.read_text(encoding="utf-8"))
        allow_requests = module_path in HTTP_REQUESTS_ALLOWLIST

        for node in ast.walk(parsed):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if (alias.name, None) == ("requests", None) and allow_requests:
                        continue
                    if (alias.name, None) in forbidden_import_targets:
                        raise AssertionError(f"{module_path} must not import {alias.name} directly")
            if isinstance(node, ast.ImportFrom):
                module_name = node.module or ""
                for alias in node.names:
                    if alias.name == "get_db" and module_name.endswith("db"):
                        raise AssertionError(f"{module_path} must not import get_db directly")
                    if module_name == "requests" or module_name.startswith("requests."):
                        if allow_requests:
                            continue
                        raise AssertionError(f"{module_path} must not import {alias.name} from {module_name}")
                    if (module_name, alias.name) in forbidden_import_targets:
                        raise AssertionError(f"{module_path} must not import {alias.name} from {module_name}")


def test_http_package_contains_no_raw_sql_calls():
    http_dir = Path(__file__).resolve().parents[1] / "wecom_ability_service" / "http"
    for path in http_dir.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "get_db(" not in source, f"{path} must not call get_db() directly"
        assert ".execute(" not in source, f"{path} must not execute raw SQL directly"


def test_http_package_contains_no_direct_third_party_runtime_calls():
    http_dir = ROOT / "wecom_ability_service" / "http"
    for path in http_dir.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        relative_path = path.relative_to(ROOT).as_posix().replace("/", ".")[:-3]
        if relative_path not in HTTP_REQUESTS_ALLOWLIST:
            assert "import requests" not in source, f"{path} must not import requests directly"
            assert "requests." not in source, f"{path} must not call requests directly"
        assert "WeComClient.from_app(" not in source, f"{path} must not instantiate WeComClient.from_app() directly"
        assert "WeComClient.from_contact_app(" not in source, f"{path} must not instantiate WeComClient.from_contact_app() directly"


def test_automation_conversion_legacy_routes_and_endpoints_remain_removed():
    from wecom_ability_service import create_app

    app = create_app({"TESTING": True})
    rules = {rule.rule for rule in app.url_map.iter_rules()}
    endpoints = set(app.view_functions.keys())

    removed_routes = {
        "/admin/automation-conversion/settings",
        "/admin/automation-conversion/sop",
        "/admin/automation-conversion/stage/<stage_key>",
        "/admin/automation-conversion/model-infra",
        "/admin/automation-conversion/debug",
        "/admin/automation-conversion/preview",
        "/admin/automation-conversion/agent-config",
        "/admin/automation-conversion/run-center",
        "/admin/automation-conversion/operations/workflows/new",
        "/admin/automation-conversion/operations/workflows/<int:workflow_id>/edit",
        "/admin/automation-conversion/operations/workflows/<int:workflow_id>/nodes",
        "/admin/automation-conversion/operations/executions",
        "/admin/automation-conversion/overview",
        "/admin/automation-conversion/operations",
        "/admin/automation-conversion/flow-design",
        "/admin/automation-conversion/member-ops",
        "/admin/automation-conversion/overview/signup-tag/apply",
        "/admin/automation-conversion/message-activity-sync/run",
        "/admin/automation-conversion/reply-monitor/toggle",
        "/admin/automation-conversion/reply-monitor/capture",
        "/admin/automation-conversion/reply-monitor/run-due",
        "/admin/automation-conversion/stage/<stage_key>/send",
        "/api/admin/automation-conversion/model-infra/settings",
    }
    removed_endpoints = {
        "admin_automation_conversion_settings",
        "admin_automation_conversion_sop",
        "admin_automation_conversion_stage",
        "admin_automation_conversion_model_infra",
        "admin_automation_conversion_debug",
        "admin_automation_conversion_preview",
        "admin_automation_conversion_agent_config",
        "admin_automation_conversion_run_center",
        "admin_automation_conversion_workflow_new",
        "admin_automation_conversion_workflow_edit",
        "admin_automation_conversion_workflow_nodes",
        "admin_automation_conversion_execution_records",
        "admin_automation_conversion_overview",
        "admin_automation_conversion_operations",
        "admin_automation_conversion_flow_design",
        "admin_automation_conversion_member_ops",
        "admin_automation_conversion_apply_overview_signup_tag",
        "admin_automation_conversion_run_message_activity_sync",
        "admin_automation_conversion_reply_monitor_toggle",
        "admin_automation_conversion_reply_monitor_capture",
        "admin_automation_conversion_reply_monitor_run_due",
        "admin_automation_conversion_stage_send",
        "api_admin_automation_conversion_model_infra_settings_save_legacy",
    }
    kept_routes = {
        "/admin/automation-conversion",
        "/admin/automation-conversion/programs/<int:program_id>/overview",
        "/admin/automation-conversion/programs/<int:program_id>/operations",
        "/admin/automation-conversion/programs/<int:program_id>/flow-design",
        "/admin/automation-conversion/programs/<int:program_id>/member-ops",
        "/admin/automation-conversion/programs/<int:program_id>/executions",
        "/admin/automation-conversion/programs/<int:program_id>/member-ops/stage/<stage_key>/send",
        "/admin/automation-conversion/programs/<int:program_id>/overview/signup-tag/apply",
        "/admin/automation-conversion/programs/<int:program_id>/overview/message-activity-sync/run",
        "/admin/automation-conversion/auto-reply/reply-monitor/toggle",
        "/admin/automation-conversion/auto-reply/reply-monitor/capture",
        "/admin/automation-conversion/auto-reply/reply-monitor/run-due",
        "/admin/automation-conversion/shared/agents",
        "/admin/automation-conversion/shared/model-infra",
        "/admin/automation-conversion/runtime/debug",
        "/api/admin/automation-conversion/model-settings",
        "/api/admin/automation-conversion/stage/<stage_key>/manual-send/preview",
        "/api/admin/automation-conversion/stage/<stage_key>/manual-send",
        "/api/admin/automation-conversion/stage/<stage_key>/focus-send-batches",
        "/api/admin/automation-conversion/message-activity-sync/run",
        "/api/admin/automation-conversion/reply-monitor/capture",
        "/api/admin/automation-conversion/reply-monitor/run-due",
    }

    restored_routes = removed_routes & rules
    missing_routes = kept_routes - rules
    restored_endpoints = {
        name
        for name in removed_endpoints
        if name in endpoints or f"api.{name}" in endpoints
    }

    assert not restored_routes, f"legacy automation conversion routes were restored: {sorted(restored_routes)}"
    assert not restored_endpoints, f"legacy automation conversion endpoints were restored: {sorted(restored_endpoints)}"
    assert not missing_routes, f"current automation conversion routes are missing: {sorted(missing_routes)}"
