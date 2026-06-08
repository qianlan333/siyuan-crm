from __future__ import annotations

from pathlib import Path

from aicrm_next.platform_foundation.route_registry.checker import build_route_check_report


ROOT = Path(__file__).resolve().parents[1]


def test_aicrm_next_main_has_no_legacy_runtime_import_or_facade() -> None:
    text = (ROOT / "aicrm_next/main.py").read_text(encoding="utf-8")

    for marker in [
        "production_compat_router",
        "production_compat_wildcard_router",
        "forward_to_legacy_flask",
        "legacy_flask_facade",
        "X-AICRM-Compatibility-Facade",
    ]:
        assert marker not in text


def test_deleted_legacy_handlers_are_not_imported_by_runtime_tools_or_scripts() -> None:
    deleted_modules = [
        "wecom_ability_service.http.admin_hxc_dashboard",
        "wecom_ability_service.http.admin_auth_routes",
        "wecom_ability_service.http.cloud_orchestrator_endpoint",
        "wecom_ability_service.http.cloud_orchestrator_campaigns",
        "wecom_ability_service.http.cloud_orchestrator_campaign_details",
        "wecom_ability_service.http.cloud_orchestrator_media",
        "wecom_ability_service.http.cloud_orchestrator_pages",
        "wecom_ability_service.http.cloud_orchestrator_plans",
        "wecom_ability_service.http.cloud_orchestrator_segments",
    ]
    roots = [ROOT / "aicrm_next", ROOT / "scripts", ROOT / "tools"]
    matches: list[str] = []
    for source_root in roots:
        for path in source_root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for module in deleted_modules:
                if module in text:
                    matches.append(f"{path.relative_to(ROOT)}:{module}")

    assert matches == []


def test_route_resolution_counters_remain_zero_after_prune() -> None:
    report = build_route_check_report(strict=True)

    assert report["production_compat_route_count"] == 0
    assert report["production_compat_catch_all_count"] == 0
    assert report["wildcard_legacy_forward_count"] == 0
    assert report["undocumented_routes_count"] == 0
    assert report["unknown_owner_routes_count"] == 0
    assert report["deleted_but_still_registered_count"] == 0
    assert report["legacy_fallback_routes_count"] == 0
