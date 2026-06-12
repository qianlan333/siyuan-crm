from __future__ import annotations

import ast
from pathlib import Path

from aicrm_next.main import app


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "docs/architecture/post_legacy_legacy_module_prune_inventory.md"

PR9_DELETED_MODULES = [
    "wecom_ability_service/http/automation_conversion.py",
    "wecom_ability_service/http/automation_conversion_runtime_api.py",
    "wecom_ability_service/http/automation_conversion_task_runtime.py",
    "wecom_ability_service/http/automation_conversion_execution_outbound.py",
    "wecom_ability_service/http/automation_conversion_member_api.py",
    "wecom_ability_service/http/automation_conversion_compat.py",
    "wecom_ability_service/http/automation_conversion_delivery.py",
    "wecom_ability_service/http/customer_automation.py",
]

PR9_DELETED_DOTTED = [
    "wecom_ability_service.http.automation_conversion",
    "wecom_ability_service.http.automation_conversion_runtime_api",
    "wecom_ability_service.http.automation_conversion_task_runtime",
    "wecom_ability_service.http.automation_conversion_execution_outbound",
    "wecom_ability_service.http.automation_conversion_member_api",
    "wecom_ability_service.http.automation_conversion_compat",
    "wecom_ability_service.http.automation_conversion_delivery",
    "wecom_ability_service.http.customer_automation",
]

NEXT_EXACT_ROUTES = {
    "/api/admin/automation-conversion/member/put-in-pool": "aicrm_next.automation_engine.api",
    "/api/admin/automation-conversion/member/set-focus": "aicrm_next.automation_engine.api",
    "/api/admin/automation-conversion/reply-monitor/run-due": "aicrm_next.automation_engine.api",
    "/api/admin/automation-conversion/tasks/run-due": "aicrm_next.automation_engine.api",
    "/api/admin/automation-conversion/execution-items/{execution_item_id}/send-via-bazhuayu": "aicrm_next.automation_engine.api",
    "/api/customers/automation/activation-webhook": "aicrm_next.automation_engine.api",
    "/api/customers/automation/webhook-deliveries/{delivery_id:int}/retry": "aicrm_next.automation_engine.api",
    "/api/customers/automation/webhook-deliveries/retry-due": "aicrm_next.automation_engine.api",
}

FORBIDDEN_MAIN_MARKERS = {
    "production_compat_router",
    "production_compat_wildcard_router",
    "legacy_flask_facade",
    "forward_to_legacy_flask",
}


def _first_route_module(path: str) -> str:
    modules = [
        getattr(route.endpoint, "__module__", "")
        for route in app.routes
        if getattr(route, "path", "") == path
    ]
    if not modules:
        raise AssertionError(f"missing route: {path}")
    return modules[0]


def _imports(path: Path) -> set[str]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module or "")
    return imports


def test_pr9_deleted_legacy_http_modules_do_not_exist() -> None:
    for rel_path in PR9_DELETED_MODULES:
        assert not (ROOT / rel_path).exists(), rel_path


def test_pr9_main_does_not_reintroduce_legacy_facades() -> None:
    main_text = (ROOT / "aicrm_next/main.py").read_text(encoding="utf-8")
    for marker in FORBIDDEN_MAIN_MARKERS:
        assert marker not in main_text


def test_pr9_next_routes_own_automation_and_customer_webhook_surfaces() -> None:
    for path, expected_module in NEXT_EXACT_ROUTES.items():
        assert _first_route_module(path) == expected_module


def test_pr9_frontend_compat_does_not_own_pruned_exact_routes() -> None:
    frontend_compat_routes = [
        getattr(route, "path", "")
        for route in app.routes
        if getattr(getattr(route, "endpoint", None), "__module__", "") == "aicrm_next.frontend_compat.legacy_routes"
    ]
    assert not (set(frontend_compat_routes) & set(NEXT_EXACT_ROUTES))


def test_pr9_no_unknown_or_legacy_route_owners() -> None:
    for route in app.routes:
        endpoint = getattr(route, "endpoint", None)
        if endpoint is None:
            continue
        module = getattr(endpoint, "__module__", "")
        assert module
        assert not module.startswith("aicrm_next.production_compat")
        assert module != "legacy_flask_facade"
        assert "forward_to_legacy_flask" not in module


def test_pr9_runtime_sources_do_not_import_deleted_legacy_modules() -> None:
    runtime_roots = [ROOT / "aicrm_next", ROOT / "scripts", ROOT / "tools"]
    for root in runtime_roots:
        for path in root.rglob("*.py"):
            imports = _imports(path)
            for dotted in PR9_DELETED_DOTTED:
                assert dotted not in imports, f"{path.relative_to(ROOT)} imports {dotted}"
            source = path.read_text(encoding="utf-8")
            for dotted in PR9_DELETED_DOTTED:
                assert dotted not in source, f"{path.relative_to(ROOT)} references {dotted}"


def test_pr9_inventory_matches_deleted_file_state() -> None:
    text = INVENTORY.read_text(encoding="utf-8")
    for rel_path in PR9_DELETED_MODULES:
        assert f"`{rel_path}`" in text
        assert "deleted_in_pr9" in text
    assert "Deferred modules" in text
