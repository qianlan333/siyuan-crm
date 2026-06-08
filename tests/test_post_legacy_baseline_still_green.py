from __future__ import annotations

from scripts.check_no_new_legacy import run_checks
from tests.post_legacy_baseline import DEFERRED_FRONTEND_API_PATTERNS
from tools.check_production_route_resolution import run_check


def test_post_legacy_deferred_frontend_patterns_are_empty() -> None:
    assert DEFERRED_FRONTEND_API_PATTERNS == ()


def test_post_legacy_route_resolution_final_counters_are_zero() -> None:
    result = run_check()

    assert result["ok"] is True
    assert result["production_compat_route_count"] == 0
    assert result["production_compat_catch_all_count"] == 0
    assert result["wildcard_legacy_forward_count"] == 0
    assert result["undocumented_routes_count"] == 0
    assert result["unknown_owner_routes_count"] == 0
    assert result["deleted_but_still_registered_count"] == 0
    assert result["legacy_fallback_routes_count"] == 0


def test_post_legacy_strict_guard_still_green() -> None:
    result = run_checks(strict=True)

    assert result["ok"] is True
    assert result["violations"] == []
