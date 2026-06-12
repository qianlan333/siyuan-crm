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
    "automation_conversion_uploads.py",
    "background_jobs.py",
    "callback_runtime.py",
    "common.py",
    "image_library_support.py",
    "ops_runtime.py",
    "questionnaire_support.py",
    "sidebar_marketing_support.py",
    "sync_jobs.py",
    "sync_support.py",
    "wechat_pay_support.py",
}
HTTP_LARGE_ROUTE_OWNER_LINE_LIMITS = {
    "admin_wechat_pay.py": 360,
    "admin_config.py": 350,
    "internal_auth.py": 390,
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
        "archive",
        "contacts",
        "group_chats",
        "callbacks",
        "tasks",
        "tags",
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


def test_automation_conversion_controller_is_pruned_after_next_cutover():
    source_path = ROOT / "wecom_ability_service" / "http" / "automation_conversion.py"
    assert not source_path.exists()


def test_automation_conversion_support_helpers_stay_layered():
    http_dir = ROOT / "wecom_ability_service" / "http"
    helper_source = (http_dir / "_routes_helpers.py").read_text(encoding="utf-8")

    assert len(helper_source.splitlines()) <= 200
    for forbidden in ("def _build_", "def _render_", "get_overview_payload", "get_settings_payload", "_render_admin_template"):
        assert forbidden not in helper_source

    for retired_helper in (
        "automation_conversion_pages.py",
        "automation_conversion_render.py",
        "automation_conversion_workspaces.py",
    ):
        assert not (http_dir / retired_helper).exists()


def test_cloud_orchestrator_legacy_http_handlers_are_retired_from_flask_registry():
    from aicrm_next.main import create_app as create_next_app
    from wecom_ability_service import create_app

    for file_name in (
        "cloud_orchestrator_endpoint.py",
        "cloud_orchestrator_campaigns.py",
        "cloud_orchestrator_campaign_details.py",
        "cloud_orchestrator_media.py",
        "cloud_orchestrator_pages.py",
        "cloud_orchestrator_plans.py",
        "cloud_orchestrator_segments.py",
    ):
        assert not (ROOT / "wecom_ability_service" / "http" / file_name).exists()

    legacy_app = create_app({"TESTING": True})
    legacy_routes = {rule.rule for rule in legacy_app.url_map.iter_rules()}
    for route in legacy_routes:
        assert not route.startswith("/admin/cloud-orchestrator")
        assert not route.startswith("/api/admin/cloud-orchestrator")

    next_routes = {}
    for route in create_next_app().routes:
        route_path = getattr(route, "path", "")
        if route_path:
            next_routes.setdefault(route_path, getattr(getattr(route, "endpoint", None), "__module__", ""))
    assert next_routes["/admin/cloud-orchestrator/campaigns"] == "aicrm_next.cloud_orchestrator.api"
    assert next_routes["/api/admin/cloud-orchestrator/campaigns"] == "aicrm_next.cloud_orchestrator.api"
    assert next_routes["/api/admin/cloud-orchestrator/campaigns/run-due/preview"] == "aicrm_next.cloud_orchestrator.api"
    assert next_routes["/api/admin/cloud-orchestrator/media/upload"] == "aicrm_next.cloud_orchestrator.api"
    assert next_routes["/api/admin/cloud-orchestrator/observability"] == "aicrm_next.cloud_orchestrator.api"


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


def test_admin_auth_legacy_module_is_pruned_but_shell_routes_stay_internal():
    from wecom_ability_service import create_app

    internal_auth_source = (ROOT / "wecom_ability_service" / "http" / "internal_auth.py").read_text(encoding="utf-8")
    assert len(internal_auth_source.splitlines()) <= 390
    assert not (ROOT / "wecom_ability_service" / "http" / "admin_auth_routes.py").exists()
    for forbidden in (
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

    for route in {
        "/auth/wecom/start",
        "/auth/wecom/callback",
    }:
        assert route not in route_modules
    for route in {"/login", "/logout"}:
        assert route_modules[route] == "wecom_ability_service.http.internal_auth"


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


def test_retired_admin_questionnaire_push_log_routes_are_not_registered_in_legacy_flask():
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
    registered_routes = {rule.rule for rule in app.url_map.iter_rules()}
    retired_routes = {
        "/admin/questionnaires/external-push-logs",
        "/admin/questionnaires/external-push-logs/retry-batch",
        "/admin/questionnaires/external-push-logs/<int:push_log_id>/retry",
        "/admin/questionnaires/<int:questionnaire_id>/external-push-logs",
        "/admin/questionnaires/<int:questionnaire_id>/external-push-logs/<int:push_log_id>/retry",
        "/admin/questionnaires/<int:questionnaire_id>/external-push-logs/retry-batch",
    }
    assert registered_routes.isdisjoint(retired_routes)


def test_retired_admin_user_ops_page_routes_are_not_registered():
    from wecom_ability_service import create_app

    app = create_app({"TESTING": True})
    retired_routes = {
        "/admin/user-ops/ui",
        "/api/admin/user-ops/overview",
        "/api/admin/user-ops/list",
        "/api/admin/user-ops/history",
        "/api/admin/user-ops/export",
        "/api/admin/user-ops/do-not-disturb",
        "/api/admin/user-ops/batch-send/preview",
        "/api/admin/user-ops/batch-send/execute",
        "/api/admin/user-ops/send-records",
        "/api/admin/user-ops/send-records/<int:record_id>",
        "/api/admin/user-ops/send-records/<int:record_id>/refresh",
    }
    registered_routes = {rule.rule for rule in app.url_map.iter_rules()}

    assert not (retired_routes & registered_routes)


def test_automation_conversion_split_route_modules_are_removed_from_legacy_registry():
    from wecom_ability_service import create_app

    app = create_app({"TESTING": True})
    route_modules = {
        rule.rule: getattr(app.view_functions[rule.endpoint], "__module__", "")
        for rule in app.url_map.iter_rules()
    }

    retired_routes = {
        "/api/admin/automation-conversion/member/put-in-pool",
        "/api/admin/automation-conversion/member/set-focus",
        "/api/admin/automation-conversion/member/push-openclaw",
        "/api/admin/automation-conversion/stage/<stage_key>/manual-send/preview",
        "/api/admin/automation-conversion/stage/<stage_key>/manual-send",
        "/api/admin/automation-conversion/stage/<stage_key>/focus-send-batches",
        "/api/admin/automation-conversion/focus-send-batches/<batch_id>",
        "/api/admin/automation-conversion/focus-send-batches/run-due",
        "/api/admin/automation-conversion/sop/config",
        "/api/admin/automation-conversion/sop/run-due",
        "/api/admin/automation-conversion/execution-items/<int:execution_item_id>/send-via-bazhuayu",
        "/api/admin/automation-conversion/tasks/run-due",
        "/api/admin/automation-conversion/message-activity-sync/run",
        "/api/admin/automation-conversion/reply-monitor/capture",
        "/api/admin/automation-conversion/reply-monitor/run-due",
        "/api/internal/automation-conversion/lobster-results",
        "/api/internal/automation-conversion/laohuang-chat-results",
        "/api/internal/automation-conversion/router-test-dispatch",
        "/api/admin/automation-conversion/jobs/run-due",
    }

    assert route_modules.keys().isdisjoint(retired_routes)


def test_cloud_orchestrator_split_route_modules_are_removed_from_legacy_registry():
    from wecom_ability_service import create_app

    app = create_app({"TESTING": True})
    route_modules = {
        rule.rule: getattr(app.view_functions[rule.endpoint], "__module__", "")
        for rule in app.url_map.iter_rules()
    }

    retired_modules = {
        "wecom_ability_service.http.cloud_orchestrator_pages",
        "wecom_ability_service.http.cloud_orchestrator_media",
        "wecom_ability_service.http.cloud_orchestrator_plans",
        "wecom_ability_service.http.cloud_orchestrator_segments",
        "wecom_ability_service.http.cloud_orchestrator_campaigns",
        "wecom_ability_service.http.cloud_orchestrator_campaign_details",
        "wecom_ability_service.http.cloud_orchestrator_endpoint",
    }
    assert not retired_modules.intersection(route_modules.values())
    assert not any(route.startswith("/admin/cloud-orchestrator") for route in route_modules)
    assert not any(route.startswith("/api/admin/cloud-orchestrator") for route in route_modules)


def test_legacy_media_library_routes_are_retired_after_d1():
    from wecom_ability_service import create_app

    retired_files = {
        "image_library_endpoint.py",
        "image_library_create.py",
        "attachment_library_endpoint.py",
        "miniprogram_library_endpoint.py",
    }
    http_dir = ROOT / "wecom_ability_service" / "http"
    for file_name in retired_files:
        assert not (http_dir / file_name).exists()

    assert not {
        "image_library",
        "image_library_create",
        "attachment_library",
        "miniprogram_library",
    } & set(HTTP_ROUTE_MODULES)
    assert all(key not in {"image_library", "attachment_library", "miniprogram_library"} for key, _ in HTTP_ROUTE_REGISTRARS)
    assert HTTP_ROUTE_MODULES["image_library_upload"] == "wecom_ability_service.http.image_library_upload"

    app = create_app({"TESTING": True})
    routes = {rule.rule for rule in app.url_map.iter_rules()}

    for route in {
        "/admin/image-library",
        "/api/admin/image-library",
        "/api/admin/image-library/from-url",
        "/api/admin/image-library/from-base64",
        "/admin/attachment-library",
        "/api/admin/attachment-library",
        "/admin/miniprogram-library",
        "/api/admin/miniprogram-library",
    }:
        assert route not in routes
    assert "/api/admin/image-library/upload" in routes


def test_legacy_customer_read_model_routes_are_retired_after_d3():
    from wecom_ability_service import create_app

    http_dir = ROOT / "wecom_ability_service" / "http"
    for file_name in {"customer_center.py", "customer_timeline.py"}:
        assert not (http_dir / file_name).exists()

    assert not {"customer_center", "customer_timeline"} & set(HTTP_ROUTE_MODULES)
    assert all(key not in {"customer_center", "customer_timeline"} for key, _ in HTTP_ROUTE_REGISTRARS)

    app = create_app({"TESTING": True})
    routes = {rule.rule for rule in app.url_map.iter_rules()}

    for route in {
        "/admin/customers",
        "/api/customers",
        "/api/customers/<external_userid>",
        "/api/customers/<external_userid>/timeline",
    }:
        assert route not in routes

    for route in {
        "/api/messages/<external_userid>",
        "/api/messages/<external_userid>/recent",
        "/api/messages/search",
    }:
        assert route in routes


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
        "/admin/automation-conversion",
        "/admin/automation-conversion/programs/<int:program_id>/overview",
        "/admin/automation-conversion/programs/<int:program_id>/operations",
        "/admin/automation-conversion/programs/<int:program_id>/executions",
        "/admin/automation-conversion/programs/<int:program_id>/flow-design",
        "/admin/automation-conversion/programs/<int:program_id>/member-ops",
        "/admin/automation-conversion/programs/<int:program_id>/member-ops/stage/<stage_key>/send",
        "/api/admin/automation-conversion/dashboard",
        "/api/admin/automation-conversion/executions",
        "/api/admin/automation-conversion/executions/<int:execution_id>",
        "/api/admin/automation-conversion/executions/<int:execution_id>/items",
        "/api/admin/automation-conversion/execution-items/<int:execution_item_id>",
        "/admin/automation-conversion/programs/<int:program_id>/overview/signup-tag/apply",
        "/admin/automation-conversion/programs/<int:program_id>/overview/message-activity-sync/run",
        "/admin/automation-conversion/auto-reply/reply-monitor/toggle",
        "/admin/automation-conversion/auto-reply/reply-monitor/capture",
        "/admin/automation-conversion/auto-reply/reply-monitor/run-due",
        "/admin/automation-conversion/shared/agents",
        "/admin/automation-conversion/shared/model-infra",
        "/admin/automation-conversion/runtime/debug",
        "/api/admin/automation-conversion/settings",
        "/api/admin/automation-conversion/settings/default-channel/generate",
        "/api/admin/automation-conversion/default-channel-settings",
        "/api/admin/automation-conversion/default-channel-settings/generate-qr",
        "/api/admin/automation-conversion/model-settings",
        "/api/admin/automation-conversion/model-settings/test",
        "/api/admin/automation-conversion/programs/<int:program_id>/setup",
        "/api/admin/automation-conversion/programs/<int:program_id>/setup/basic",
        "/api/admin/automation-conversion/programs/<int:program_id>/setup/entry-channel",
        "/api/admin/automation-conversion/programs/<int:program_id>/setup/segmentation",
        "/api/admin/automation-conversion/programs/<int:program_id>/setup/audience-entry-rule",
        "/api/admin/automation-conversion/programs/<int:program_id>/setup/publish-check",
        "/api/admin/automation-conversion/programs/<int:program_id>/publish-entry",
        "/api/admin/automation-conversion/programs/<int:program_id>/publish-full",
        "/api/admin/automation-conversion/programs/<int:program_id>/customer-acquisition-links",
        "/api/admin/automation-conversion/programs/<int:program_id>/members/segment-search",
        "/api/admin/automation-conversion/programs/<int:program_id>/members/segment-broadcast",
        "/api/admin/automation-conversion/router-pending-callbacks",
        "/api/admin/automation-conversion/router-callback-replay/<run_id>",
        "/api/admin/automation-conversion/router-pending-callback-check",
        "/api/admin/automation-conversion/review-outputs",
        "/api/admin/automation-conversion/review-outputs/<output_id>/review",
        "/api/admin/automation-conversion/review-outputs/<output_id>/send-via-webhook",
        "/api/admin/automation-conversion/review-outputs/<output_id>/send-via-wecom",
        "/api/admin/automation-conversion/review-outputs/<output_id>/send-via-bazhuayu",
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
        "api_admin_automation_program_setup",
        "api_admin_automation_program_setup_basic",
        "api_admin_automation_program_setup_entry_channel",
        "api_admin_automation_program_setup_segmentation",
        "api_admin_automation_program_setup_audience_entry_rule",
        "api_admin_automation_program_setup_publish_check",
        "api_admin_automation_program_publish_entry",
        "api_admin_automation_program_publish_full",
        "api_admin_automation_program_customer_acquisition_links",
        "api_admin_automation_program_member_segment_search",
        "api_admin_automation_program_member_segment_broadcast",
        "api_admin_automation_conversion_router_pending_callbacks",
        "api_admin_automation_conversion_router_callback_replay",
        "api_admin_automation_conversion_router_pending_callback_check",
        "api_admin_automation_conversion_review_outputs",
        "api_admin_automation_conversion_review_output",
        "api_admin_automation_conversion_review_output_send_via_webhook",
        "api_admin_automation_conversion_review_output_send_via_wecom",
        "api_admin_automation_conversion_review_output_send_via_bazhuayu",
    }
    kept_routes: set[str] = set()

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
