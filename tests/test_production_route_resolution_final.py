from __future__ import annotations

from tools.check_production_route_resolution import run_check


def test_production_route_resolution_final_counters_are_zero() -> None:
    result = run_check()

    assert result["ok"] is True
    assert result["production_compat_route_count"] == 0
    assert result["production_compat_catch_all_count"] == 0
    assert result["wildcard_legacy_forward_count"] == 0
    assert result["undocumented_routes_count"] == 0
    assert result["legacy_fallback_routes_count"] == 0
    assert result["unknown_owner_routes_count"] == 0
    assert result["deleted_but_still_registered_count"] == 0
