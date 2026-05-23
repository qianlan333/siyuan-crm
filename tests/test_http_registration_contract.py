from __future__ import annotations

import ast
import importlib
from pathlib import Path

from flask import Blueprint

from wecom_ability_service.http import HTTP_ROUTE_MODULES, HTTP_ROUTE_PLACEMENT, HTTP_ROUTE_REGISTRARS, bp, register_http_routes


ROOT = Path(__file__).resolve().parents[1]
HTTP_REQUESTS_ALLOWLIST = set()

HTTP_WECOM_CLIENT_ALLOWLIST = set()
APP_LEVEL_VIEW_MODULE_ALLOWLIST = {
    "/favicon.ico": "wecom_ability_service",
    "/mcp": "wecom_ability_service.mcp_adapter",
}
HTTP_HELPER_MODULE_FILES = {
    "_routes_helpers.py",
    "admin_support.py",
    "automation_conversion_form_helpers.py",
    "automation_conversion_render.py",
    "automation_conversion_uploads.py",
    "automation_conversion_compat.py",
    "automation_conversion_workspaces.py",
    "background_jobs.py",
    "callback_runtime.py",
    "common.py",
    "image_library_support.py",
    "ops_runtime.py",
    "questionnaire_support.py",
    "sidebar_marketing_support.py",
    "sync_jobs.py",
    "sync_support.py",
}
HTTP_LARGE_ROUTE_OWNER_LINE_LIMITS = {
    "admin_config.py": 350,
    "automation_conversion.py": 350,
    "automation_conversion_channels.py": 360,
    "internal_auth.py": 360,
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


def test_every_registered_http_controller_is_in_route_module_contract():
    registered_keys = {key for key, _ in HTTP_ROUTE_REGISTRARS}
    missing_keys = registered_keys - set(HTTP_ROUTE_MODULES)
    assert not missing_keys, f"registered HTTP controllers missing from HTTP_ROUTE_MODULES: {sorted(missing_keys)}"


def test_http_route_placement_mentions_every_route_module_file():
    placement_text = "\n".join(
        description
        for descriptions in HTTP_ROUTE_PLACEMENT.values()
        for description in descriptions
    )
    missing_files = []
    for module_path in HTTP_ROUTE_MODULES.values():
        module_file = Path(module_path.replace("wecom_ability_service.http.", "").replace(".", "/") + ".py").name
        if module_file not in placement_text:
            missing_files.append(module_file)

    assert not missing_files, f"HTTP route modules missing from HTTP_ROUTE_PLACEMENT: {sorted(missing_files)}"


def test_unregistered_http_modules_are_explicit_helpers_only():
    http_dir = ROOT / "wecom_ability_service" / "http"
    route_module_files = {
        Path(module_path.replace("wecom_ability_service.http.", "").replace(".", "/") + ".py").name
        for module_path in HTTP_ROUTE_MODULES.values()
    }
    python_files = {
        path.name
        for path in http_dir.glob("*.py")
        if path.name != "__init__.py"
    }
    unregistered_files = python_files - route_module_files
    assert unregistered_files == HTTP_HELPER_MODULE_FILES


def test_large_http_route_owners_are_explicitly_capped():
    route_module_files = {
        Path(module_path.replace("wecom_ability_service.http.", "").replace(".", "/") + ".py").name
        for module_path in HTTP_ROUTE_MODULES.values()
    }
    large_route_owners = {}
    for file_name in route_module_files:
        source_path = ROOT / "wecom_ability_service" / "http" / file_name
        line_count = len(source_path.read_text(encoding="utf-8").splitlines())
        if line_count > 300:
            large_route_owners[file_name] = line_count

    unexpected = set(large_route_owners) - set(HTTP_LARGE_ROUTE_OWNER_LINE_LIMITS)
    over_limit = {
        file_name: line_count
        for file_name, line_count in large_route_owners.items()
        if line_count > HTTP_LARGE_ROUTE_OWNER_LINE_LIMITS.get(file_name, line_count)
    }
    assert not unexpected, f"large HTTP route owners must be explicitly capped: {unexpected}"
    assert not over_limit, f"large HTTP route owners exceeded their caps: {over_limit}"


def test_every_flask_view_module_is_covered_by_http_route_contract():
    from wecom_ability_service import create_app

    app = create_app({"TESTING": True})
    covered_modules = set(HTTP_ROUTE_MODULES.values())
    missing: dict[str, str] = {}
    for rule in app.url_map.iter_rules():
        if rule.endpoint == "static":
            continue
        module_name = getattr(app.view_functions[rule.endpoint], "__module__", "")
        if APP_LEVEL_VIEW_MODULE_ALLOWLIST.get(rule.rule) == module_name:
            continue
        if module_name not in covered_modules:
            missing[rule.rule] = module_name

    assert not missing, f"Flask routes missing from HTTP_ROUTE_MODULES: {missing}"


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
        if path.name in HTTP_WECOM_CLIENT_ALLOWLIST:
            continue
        assert "WeComClient.from_app(" not in source, f"{path} must not instantiate WeComClient.from_app() directly"
        assert "WeComClient.from_contact_app(" not in source, f"{path} must not instantiate WeComClient.from_contact_app() directly"


def test_automation_conversion_controller_stays_a_route_aggregator():
    source_path = ROOT / "wecom_ability_service" / "http" / "automation_conversion.py"
    source = source_path.read_text(encoding="utf-8")
    parsed = ast.parse(source)

    assert len(source.splitlines()) <= 350

    forbidden_imports = {
        "flask",
        "wecom_ability_service.domains",
        "wecom_ability_service.http._routes_helpers",
    }
    for node in ast.walk(parsed):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not any(alias.name == target or alias.name.startswith(f"{target}.") for target in forbidden_imports)
        if isinstance(node, ast.ImportFrom):
            module_name = node.module or ""
            assert not any(module_name == target or module_name.startswith(f"{target}.") for target in forbidden_imports)


def test_automation_conversion_support_helpers_stay_layered():
    http_dir = ROOT / "wecom_ability_service" / "http"
    helper_source = (http_dir / "_routes_helpers.py").read_text(encoding="utf-8")
    render_source = (http_dir / "automation_conversion_render.py").read_text(encoding="utf-8")
    workspaces_source = (http_dir / "automation_conversion_workspaces.py").read_text(encoding="utf-8")

    assert len(helper_source.splitlines()) <= 200
    for forbidden in ("def _build_", "def _render_", "get_overview_payload", "get_settings_payload", "_render_admin_template"):
        assert forbidden not in helper_source

    for forbidden in ("get_overview_payload", "get_settings_payload", "get_stage_detail_payload"):
        assert forbidden not in render_source

    for forbidden in ("_render_admin_template", "ensure_admin_console_action_token", "validate_admin_console_action_token"):
        assert forbidden not in workspaces_source


def test_cloud_orchestrator_controller_stays_a_route_aggregator():
    source_path = ROOT / "wecom_ability_service" / "http" / "cloud_orchestrator_endpoint.py"
    source = source_path.read_text(encoding="utf-8")
    parsed = ast.parse(source)

    assert len(source.splitlines()) <= 220

    forbidden_imports = {
        "flask",
        "wecom_ability_service.domains",
        "wecom_ability_service.db",
        "wecom_ability_service.wecom_client",
    }
    for node in ast.walk(parsed):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not any(alias.name == target or alias.name.startswith(f"{target}.") for target in forbidden_imports)
        if isinstance(node, ast.ImportFrom):
            module_name = node.module or ""
            assert not any(module_name == target or module_name.startswith(f"{target}.") for target in forbidden_imports)


def test_admin_api_docs_controller_stays_a_page_adapter():
    source_path = ROOT / "wecom_ability_service" / "http" / "admin_api_docs.py"
    source = source_path.read_text(encoding="utf-8")

    assert len(source.splitlines()) <= 80
    assert "build_api_docs_view_model" in source
    for forbidden in (
        "def _curl(",
        "def _auth_group(",
        "def _api_endpoint_groups(",
        "_AGENT_GUIDE_MD",
        "_build_markdown_data",
    ):
        assert forbidden not in source


def test_admin_config_marketing_automation_routes_stay_in_child_controller():
    from wecom_ability_service import create_app

    admin_config_source = (ROOT / "wecom_ability_service" / "http" / "admin_config.py").read_text(encoding="utf-8")
    assert len(admin_config_source.splitlines()) <= 350
    assert "def api_admin_config_" not in admin_config_source
    assert "application.automation_engine" not in admin_config_source
    assert "domains.admin_auth" not in admin_config_source

    app = create_app({"TESTING": True})
    route_modules = {
        rule.rule: getattr(app.view_functions[rule.endpoint], "__module__", "")
        for rule in app.url_map.iter_rules()
    }
    expected_module = "wecom_ability_service.http.admin_config_marketing_automation"

    for route in {
        "/admin/marketing-automation/ui",
        "/api/admin/marketing-automation/config",
        "/api/admin/marketing-automation/config/preview",
        "/api/admin/marketing-automation/dispatch-history",
        "/api/admin/marketing-automation/recompute",
        "/api/admin/config/marketing-automation/signup-conversion",
    }:
        assert route_modules[route] == expected_module


def test_admin_config_json_api_routes_stay_in_child_controller():
    from wecom_ability_service import create_app

    app = create_app({"TESTING": True})
    route_modules = {
        rule.rule: getattr(app.view_functions[rule.endpoint], "__module__", "")
        for rule in app.url_map.iter_rules()
    }
    expected_module = "wecom_ability_service.http.admin_config_api"

    for route in {
        "/api/admin/config/overview",
        "/api/admin/config/routing",
        "/api/admin/config/routing/owner-role",
        "/api/admin/config/routing/rule",
        "/api/admin/config/signup-tags",
        "/api/admin/config/class-term-tags",
        "/api/admin/config/app-settings",
        "/api/admin/config/mcp-tools",
    }:
        assert route_modules[route] == expected_module


def test_admin_config_login_access_routes_stay_in_child_controller():
    from wecom_ability_service import create_app

    app = create_app({"TESTING": True})
    route_modules = {
        rule.rule: getattr(app.view_functions[rule.endpoint], "__module__", "")
        for rule in app.url_map.iter_rules()
    }
    expected_module = "wecom_ability_service.http.admin_config_login_access"

    for route in {
        "/admin/config/login-access",
        "/admin/config/login-access/directory/refresh",
        "/admin/config/login-access/save",
    }:
        assert route_modules[route] == expected_module


def test_sidebar_marketing_status_routes_stay_in_child_controller():
    from wecom_ability_service import create_app

    sidebar_source = (ROOT / "wecom_ability_service" / "http" / "sidebar.py").read_text(encoding="utf-8")
    sidebar_marketing_source = (ROOT / "wecom_ability_service" / "http" / "sidebar_marketing.py").read_text(encoding="utf-8")
    assert len(sidebar_source.splitlines()) <= 380
    assert len(sidebar_marketing_source.splitlines()) <= 120
    assert "application.automation_engine" not in sidebar_source
    assert "CustomerMarketingProfileQueryDTO" not in sidebar_marketing_source
    assert "business_marketing_display" not in sidebar_marketing_source

    app = create_app({"TESTING": True})
    route_modules = {
        rule.rule: getattr(app.view_functions[rule.endpoint], "__module__", "")
        for rule in app.url_map.iter_rules()
    }
    expected_module = "wecom_ability_service.http.sidebar_marketing"

    for route in {
        "/api/sidebar/marketing-status",
        "/api/sidebar/marketing-status/set-followup-segment",
        "/api/sidebar/marketing-status/mark-enrolled",
        "/api/sidebar/marketing-status/unmark-enrolled",
    }:
        assert route_modules[route] == expected_module


def test_sidebar_lead_pool_routes_stay_in_child_controller():
    from wecom_ability_service import create_app

    sidebar_source = (ROOT / "wecom_ability_service" / "http" / "sidebar.py").read_text(encoding="utf-8")
    sidebar_lead_pool_source = (
        ROOT / "wecom_ability_service" / "http" / "sidebar_lead_pool.py"
    ).read_text(encoding="utf-8")
    assert len(sidebar_source.splitlines()) <= 190
    assert len(sidebar_lead_pool_source.splitlines()) <= 80
    assert "application.user_ops.commands" not in sidebar_source
    assert "application.user_ops.queries" not in sidebar_source

    app = create_app({"TESTING": True})
    route_modules = {
        rule.rule: getattr(app.view_functions[rule.endpoint], "__module__", "")
        for rule in app.url_map.iter_rules()
    }
    expected_module = "wecom_ability_service.http.sidebar_lead_pool"

    for route in {
        "/api/sidebar/lead-pool/status",
        "/api/sidebar/lead-pool/upsert-class-term",
    }:
        assert route_modules[route] == expected_module


def test_public_questionnaire_oauth_routes_stay_in_child_controller():
    from wecom_ability_service import create_app

    public_source = (ROOT / "wecom_ability_service" / "http" / "public_questionnaires.py").read_text(encoding="utf-8")
    assert len(public_source.splitlines()) <= 270
    assert "CompleteQuestionnaireOauthCallbackCommand" not in public_source
    assert "WeChatOAuthRequestError" not in public_source
    assert "def public_questionnaire_client_diagnostics" not in public_source
    assert "def debug_questionnaire_session" not in public_source

    app = create_app({"TESTING": True})
    route_modules = {
        rule.rule: getattr(app.view_functions[rule.endpoint], "__module__", "")
        for rule in app.url_map.iter_rules()
    }
    expected_module = "wecom_ability_service.http.public_questionnaire_oauth"

    for route in {
        "/api/h5/wechat/oauth/start",
        "/api/h5/wechat/oauth/callback",
    }:
        assert route_modules[route] == expected_module

    expected_diagnostics_module = "wecom_ability_service.http.public_questionnaire_diagnostics"
    for route in {
        "/api/h5/questionnaires/<slug>/client-diagnostics",
        "/api/debug/questionnaire/session",
    }:
        assert route_modules[route] == expected_diagnostics_module


def test_admin_auth_login_routes_stay_in_child_controller():
    from wecom_ability_service import create_app

    internal_auth_source = (ROOT / "wecom_ability_service" / "http" / "internal_auth.py").read_text(encoding="utf-8")
    assert len(internal_auth_source.splitlines()) <= 360
    for forbidden in (
        "def admin_login(",
        "def admin_wecom_start(",
        "build_wecom_qr_login_url",
        "login_break_glass_session",
    ):
        assert forbidden not in internal_auth_source
    assert "def exchange_code_for_wecom_user(" not in internal_auth_source

    app = create_app({"TESTING": True})
    route_modules = {
        rule.rule: getattr(app.view_functions[rule.endpoint], "__module__", "")
        for rule in app.url_map.iter_rules()
    }
    expected_module = "wecom_ability_service.http.admin_auth_routes"

    for route in {
        "/login",
        "/logout",
        "/auth/wecom/start",
        "/auth/wecom/callback",
    }:
        assert route_modules[route] == expected_module


def test_admin_broadcast_job_routes_stay_in_child_controller():
    from wecom_ability_service import create_app

    admin_jobs_source = (ROOT / "wecom_ability_service" / "http" / "admin_jobs.py").read_text(encoding="utf-8")
    assert len(admin_jobs_source.splitlines()) <= 280
    assert "domains.broadcast_jobs" not in admin_jobs_source

    app = create_app({"TESTING": True})
    route_modules = {
        rule.rule: getattr(app.view_functions[rule.endpoint], "__module__", "")
        for rule in app.url_map.iter_rules()
    }
    expected_module = "wecom_ability_service.http.admin_broadcast_jobs"

    for route in {
        "/admin/broadcast-jobs",
        "/api/admin/broadcast-jobs",
        "/api/admin/broadcast-jobs/<int:job_id>/cancel",
        "/api/admin/broadcast-jobs/<int:job_id>/approve",
    }:
        assert route_modules[route] == expected_module


def test_admin_questionnaire_push_log_routes_stay_in_child_controller():
    from wecom_ability_service import create_app

    questionnaire_console_source = (
        ROOT / "wecom_ability_service" / "http" / "admin_questionnaire_console.py"
    ).read_text(encoding="utf-8")
    assert len(questionnaire_console_source.splitlines()) <= 220
    for forbidden in (
        "RetryQuestionnaireExternalPushCommand",
        "GetGlobalQuestionnaireExternalPushLogsQuery",
        "def admin_console_questionnaire_external_push_logs(",
        "def admin_console_global_questionnaire_external_push_logs(",
    ):
        assert forbidden not in questionnaire_console_source

    app = create_app({"TESTING": True})
    route_modules = {
        rule.rule: getattr(app.view_functions[rule.endpoint], "__module__", "")
        for rule in app.url_map.iter_rules()
    }
    expected_module = "wecom_ability_service.http.admin_questionnaire_push_logs"

    for route in {
        "/admin/questionnaires/external-push-logs",
        "/admin/questionnaires/external-push-logs/retry-batch",
        "/admin/questionnaires/external-push-logs/<int:push_log_id>/retry",
        "/admin/questionnaires/<int:questionnaire_id>/external-push-logs",
        "/admin/questionnaires/<int:questionnaire_id>/external-push-logs/<int:push_log_id>/retry",
        "/admin/questionnaires/<int:questionnaire_id>/external-push-logs/retry-batch",
    }:
        assert route_modules[route] == expected_module


def test_admin_user_ops_delivery_routes_stay_in_child_controller():
    from wecom_ability_service import create_app

    user_ops_source = (ROOT / "wecom_ability_service" / "http" / "admin_user_ops.py").read_text(encoding="utf-8")
    assert len(user_ops_source.splitlines()) <= 260
    for forbidden in (
        "MAX_PRIVATE_MESSAGE_IMAGES",
        "validate_wecom_image_upload",
        "def admin_user_ops_batch_send_",
        "def admin_user_ops_send_record",
    ):
        assert forbidden not in user_ops_source

    app = create_app({"TESTING": True})
    route_modules = {
        rule.rule: getattr(app.view_functions[rule.endpoint], "__module__", "")
        for rule in app.url_map.iter_rules()
    }
    expected_module = "wecom_ability_service.http.admin_user_ops_delivery"

    for route in {
        "/api/admin/user-ops/do-not-disturb",
        "/api/admin/user-ops/batch-send/preview",
        "/api/admin/user-ops/batch-send/execute",
        "/api/admin/user-ops/send-records",
        "/api/admin/user-ops/send-records/<int:record_id>",
        "/api/admin/user-ops/send-records/<int:record_id>/refresh",
    }:
        assert route_modules[route] == expected_module


def test_automation_conversion_split_route_modules_stay_owned_by_child_controllers():
    from wecom_ability_service import create_app

    app = create_app({"TESTING": True})
    route_modules = {
        rule.rule: getattr(app.view_functions[rule.endpoint], "__module__", "")
        for rule in app.url_map.iter_rules()
    }

    expected_by_module = {
        "automation_conversion_pages": {
            "/admin/automation-conversion",
            "/admin/automation-conversion/programs",
            "/admin/automation-conversion/programs/<int:program_id>/setup",
            "/admin/automation-conversion/programs/<int:program_id>/overview",
            "/admin/automation-conversion/programs/<int:program_id>/operations",
            "/admin/automation-conversion/shared/agents",
            "/admin/automation-conversion/runtime/router",
            "/admin/automation-conversion/auto-reply",
        },
        "automation_conversion_page_actions": {
            "/admin/automation-conversion/settings/save",
            "/admin/automation-conversion/settings/default-channel/generate",
            "/admin/automation-conversion/programs/<int:program_id>/member-ops/stage/<stage_key>/send",
            "/admin/automation-conversion/programs/<int:program_id>/overview/signup-tag/apply",
            "/admin/automation-conversion/programs/<int:program_id>/overview/message-activity-sync/run",
        },
        "automation_conversion_agent_page_actions": {
            "/admin/automation-conversion/agent-orchestration/agents/<agent_code>/save-draft",
            "/admin/automation-conversion/agent-orchestration/outputs/<output_id>/review",
            "/admin/automation-conversion/agent-orchestration/replay/<run_id>",
        },
        "automation_conversion_auto_reply_actions": {
            "/admin/automation-conversion/auto-reply/reply-monitor/toggle",
            "/admin/automation-conversion/auto-reply/reply-monitor/capture",
            "/admin/automation-conversion/auto-reply/reply-monitor/run-due",
        },
        "automation_conversion_segments": {
            "/api/admin/automation-conversion/programs/<int:program_id>/members/segment-search",
            "/api/admin/automation-conversion/programs/<int:program_id>/members/segment-broadcast",
        },
        "automation_conversion_member_api": {
            "/api/admin/automation-conversion/member",
            "/api/admin/automation-conversion/member/put-in-pool",
            "/api/admin/automation-conversion/member/set-focus",
            "/api/admin/automation-conversion/member/push-openclaw",
            "/api/admin/automation-conversion/stage/<stage_key>/manual-send/preview",
            "/api/admin/automation-conversion/stage/<stage_key>/manual-send",
            "/api/admin/automation-conversion/stage/<stage_key>/focus-send-batches",
        },
        "automation_conversion_delivery": {
            "/api/admin/automation-conversion/focus-send-batches/<batch_id>",
            "/api/admin/automation-conversion/focus-send-batches/run-due",
            "/api/admin/automation-conversion/sop/config",
            "/api/admin/automation-conversion/sop/run-due",
        },
        "automation_conversion_settings": {
            "/api/admin/automation-conversion/settings",
            "/api/admin/automation-conversion/default-channel-settings",
            "/api/admin/automation-conversion/model-settings",
            "/api/admin/automation-conversion/model-settings/test",
        },
        "automation_conversion_setup": {
            "/api/admin/automation-conversion/programs/<int:program_id>/setup",
            "/api/admin/automation-conversion/programs/<int:program_id>/setup/basic",
            "/api/admin/automation-conversion/programs/<int:program_id>/publish-entry",
            "/api/admin/automation-conversion/programs/<int:program_id>/customer-acquisition-links",
        },
        "automation_conversion_templates": {
            "/api/admin/automation-conversion/action-templates",
            "/api/admin/automation-conversion/action-templates/from-workflow",
            "/api/admin/automation-conversion/programs/<int:program_id>/actions/from-template",
            "/api/admin/automation-conversion/profile-segment-templates",
            "/api/admin/automation-conversion/profile-segment-templates/options",
        },
        "automation_conversion_agent_api": {
            "/api/admin/automation-conversion/agent-outputs",
            "/api/admin/automation-conversion/agent-outputs/<output_id>",
            "/api/admin/automation-conversion/agent-runs/<run_id>",
            "/api/admin/automation-conversion/agent-outputs/export",
            "/api/admin/automation-conversion/agent-outputs/export/<job_id>",
            "/api/admin/automation-conversion/agent-replay",
            "/api/admin/automation-conversion/agent-orchestration/pending-publish",
            "/api/admin/automation-conversion/agents",
            "/api/admin/automation-conversion/agents/options",
            "/api/admin/automation-conversion/agents/<agent_code>",
            "/api/admin/automation-conversion/agents/<agent_code>/draft",
            "/api/admin/automation-conversion/agents/<agent_code>/publish",
        },
        "automation_conversion_router_callback_api": {
            "/api/admin/automation-conversion/router-pending-callbacks",
            "/api/admin/automation-conversion/router-callback-replay/<run_id>",
            "/api/admin/automation-conversion/router-pending-callback-check",
        },
        "automation_conversion_review": {
            "/api/admin/automation-conversion/review-outputs",
            "/api/admin/automation-conversion/review-outputs/<output_id>/review",
            "/api/admin/automation-conversion/review-outputs/<output_id>/send-via-webhook",
            "/api/admin/automation-conversion/review-outputs/<output_id>/send-via-wecom",
            "/api/admin/automation-conversion/review-outputs/<output_id>/send-via-bazhuayu",
        },
        "automation_conversion_workflows": {
            "/api/admin/automation-conversion/dashboard",
            "/api/admin/automation-conversion/workflows",
            "/api/admin/automation-conversion/workflows/<int:workflow_id>",
            "/api/admin/automation-conversion/workflows/<int:workflow_id>/nodes",
            "/api/admin/automation-conversion/workflow-nodes/<int:node_id>",
            "/api/admin/automation-conversion/executions",
            "/api/admin/automation-conversion/execution-items/<int:execution_item_id>",
        },
        "automation_conversion_runtime_api": {
            "/api/admin/automation-conversion/message-activity-sync/run",
            "/api/admin/automation-conversion/reply-monitor/capture",
            "/api/admin/automation-conversion/reply-monitor/run-due",
            "/api/internal/automation-conversion/lobster-results",
            "/api/internal/automation-conversion/laohuang-chat-results",
            "/api/internal/automation-conversion/router-test-dispatch",
            "/api/admin/automation-conversion/jobs/run-due",
        },
    }

    for module_name, expected_routes in expected_by_module.items():
        expected_module = f"wecom_ability_service.http.{module_name}"
        for route in expected_routes:
            assert route_modules[route] == expected_module


def test_cloud_orchestrator_split_route_modules_stay_owned_by_child_controllers():
    from wecom_ability_service import create_app

    app = create_app({"TESTING": True})
    route_modules = {
        rule.rule: getattr(app.view_functions[rule.endpoint], "__module__", "")
        for rule in app.url_map.iter_rules()
    }

    expected_by_module = {
        "cloud_orchestrator_pages": {
            "/admin/cloud-orchestrator",
            "/admin/cloud-orchestrator/observability",
            "/admin/cloud-orchestrator/campaigns",
            "/admin/cloud-orchestrator/integration",
        },
        "cloud_orchestrator_media": {
            "/api/admin/cloud-orchestrator/media/upload",
        },
        "cloud_orchestrator_plans": {
            "/api/admin/cloud-orchestrator/plans",
            "/api/admin/cloud-orchestrator/plans/<plan_id>",
            "/api/admin/cloud-orchestrator/plans/<plan_id>/simulate",
            "/api/admin/cloud-orchestrator/plans/<plan_id>/approve",
            "/api/admin/cloud-orchestrator/plans/<plan_id>/commit",
            "/api/admin/cloud-orchestrator/plans/<plan_id>/reject",
            "/api/admin/cloud-orchestrator/audit",
            "/api/admin/cloud-orchestrator/observability",
        },
        "cloud_orchestrator_segments": {
            "/api/admin/cloud-orchestrator/segments",
            "/api/admin/cloud-orchestrator/segments/<segment_code>",
            "/api/admin/cloud-orchestrator/segments/<segment_code>/preview",
        },
        "cloud_orchestrator_campaigns": {
            "/api/admin/cloud-orchestrator/campaigns",
            "/api/admin/cloud-orchestrator/campaigns/<campaign_code>",
            "/api/admin/cloud-orchestrator/campaigns/<campaign_code>/approve",
            "/api/admin/cloud-orchestrator/campaigns/<campaign_code>/start",
            "/api/admin/cloud-orchestrator/campaigns/<campaign_code>/pause",
            "/api/admin/cloud-orchestrator/campaigns/<campaign_code>/reject",
            "/api/admin/cloud-orchestrator/campaigns/batch-start",
            "/api/admin/cloud-orchestrator/campaigns/run-due",
        },
        "cloud_orchestrator_campaign_details": {
            "/api/admin/cloud-orchestrator/campaigns/<campaign_code>/steps",
            "/api/admin/cloud-orchestrator/campaigns/<campaign_code>/steps/<step_index>",
            "/api/admin/cloud-orchestrator/campaigns/<campaign_code>/members",
        },
    }

    for module_name, expected_routes in expected_by_module.items():
        expected_module = f"wecom_ability_service.http.{module_name}"
        for route in expected_routes:
            assert route_modules[route] == expected_module


def test_image_library_create_routes_stay_in_child_controller():
    from wecom_ability_service import create_app

    image_library_source = (ROOT / "wecom_ability_service" / "http" / "image_library_endpoint.py").read_text(encoding="utf-8")
    assert len(image_library_source.splitlines()) <= 210
    for forbidden in (
        "def admin_image_library_upload(",
        "def admin_image_library_create_url(",
        "def admin_image_library_create_base64(",
    ):
        assert forbidden not in image_library_source

    app = create_app({"TESTING": True})
    route_modules = {
        rule.rule: getattr(app.view_functions[rule.endpoint], "__module__", "")
        for rule in app.url_map.iter_rules()
    }
    expected_module = "wecom_ability_service.http.image_library_create"

    for route in {
        "/api/admin/image-library/upload",
        "/api/admin/image-library/from-url",
        "/api/admin/image-library/from-base64",
    }:
        assert route_modules[route] == expected_module


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
