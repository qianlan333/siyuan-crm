from __future__ import annotations

from aicrm_next.main import create_app
from aicrm_next.platform_foundation.route_registry.checker import build_route_check_report
from tests.post_legacy_baseline import API_CONTRACT_CASES, ADMIN_PAGE_CASES, PUBLIC_H5_PAGE_CASES, baseline_env, first_matching_route
from tools.check_production_route_resolution import run_check


def test_post_legacy_route_resolution_baseline_counters_are_zero() -> None:
    result = run_check()

    assert result["ok"] is True
    assert result["production_compat_route_count"] == 0
    assert result["production_compat_catch_all_count"] == 0
    assert result["wildcard_legacy_forward_count"] == 0
    assert result["undocumented_routes_count"] == 0
    assert result["legacy_fallback_routes_count"] == 0
    assert result["unknown_owner_routes_count"] == 0
    assert result["deleted_but_still_registered_count"] == 0


def test_post_legacy_registry_checker_baseline_counters_are_zero(monkeypatch) -> None:
    baseline_env(monkeypatch)
    report = build_route_check_report(strict=True)

    assert report["ok"] is True
    assert report["undocumented_routes_count"] == 0
    assert report["unknown_owner_count"] == 0
    assert report["deleted_but_still_registered_count"] == 0
    assert report["production_compat_route_count"] == 0
    assert report["legacy_fallback_routes_count"] == 0
    assert report["wildcard_legacy_forward_count"] == 0


def test_post_legacy_baseline_cases_are_registered_with_next_owners(monkeypatch) -> None:
    baseline_env(monkeypatch)
    app = create_app()
    cases = [(case.path, "GET") for case in ADMIN_PAGE_CASES + PUBLIC_H5_PAGE_CASES]
    cases.extend((case.path, case.method) for case in API_CONTRACT_CASES)

    unresolved: list[str] = []
    compat: list[str] = []
    for path, method in cases:
        route = first_matching_route(app, method, path)
        if route is None:
            unresolved.append(f"{method} {path}")
            continue
        endpoint_module = getattr(getattr(route, "endpoint", None), "__module__", "")
        if endpoint_module == "aicrm_next.production_compat.api":
            compat.append(f"{method} {path}")

    assert unresolved == []
    assert compat == []
