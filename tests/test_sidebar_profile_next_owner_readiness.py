from __future__ import annotations

from tools import check_sidebar_profile_next_owner_readiness as checker


def test_sidebar_profile_readiness_checker_passes_current_repo():
    result = checker.run_check()

    assert result["ok"], result["blockers"]
    assert result["blockers"] == []
    assert result["runtime_changed"] is False


def test_route_matrix_covers_required_sidebar_profile_families():
    patterns = {record["route_pattern"] for record in checker.ROUTE_MATRIX}

    assert "/sidebar/*" in patterns
    assert "/api/sidebar/*" in patterns
    assert "/api/admin/customers/profile" in patterns
    assert "/api/admin/customers/profile/*" in patterns
    assert "/api/admin/automation-conversion/member" in patterns
    assert "/api/admin/automation-conversion/member/*" in patterns


def test_route_matrix_declares_future_next_owners_and_guarded_writes():
    allowed_future_owners = {"customer_read_model", "identity_contact", "frontend_compat", "automation_engine"}
    for record in checker.ROUTE_MATRIX:
        assert record["future_next_owner"] in allowed_future_owners
        assert record["current_owner"] in {
            "production_compat legacy_forward",
            "exact compatibility facade",
            "next exact readonly",
            "missing Next exact owner",
            "blocked",
        }
        if str(record["access"]).startswith("write_"):
            assert str(record["write_guard"]).startswith("guarded")


def test_route_probes_have_explicit_owner_and_no_fixture_markers():
    result = checker.run_check()

    for probe in result["probes"]:
        assert probe["status_code"] != 404, probe
        assert probe["route_owner_header"], probe
        assert probe["compatibility_facade"] == probe["expected_facade"], probe
        if probe["expected_endpoint_module"]:
            assert probe["endpoint_module"] == probe["expected_endpoint_module"], probe
        assert probe["fixture_marker_present"] is False, probe
