from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def _records(path: str) -> list[dict]:
    return list(yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))["routes"])


def test_admin_auth_registry_records_are_deletion_locked() -> None:
    by_id = {record["route_id"]: record for record in _records("docs/architecture/legacy_exit_route_registry.yaml")}

    for route_id in ("frontend_compat_auth_pages", "frontend_compat_logout_pages"):
        record = by_id[route_id]
        assert record["capability_owner"] == "aicrm_next.admin_auth"
        assert record["runtime_owner"] == "next_auth"
        assert record["legacy_fallback_allowed"] is False
        assert record["legacy_source"] == ""
        assert record["delete_status"] == "deletion_locked"
        assert record["replacement_status"] == "locked"


def test_admin_auth_manifest_records_are_next_locked_and_auth_wecom_unchanged() -> None:
    by_route = {record["route_pattern"]: record for record in _records("docs/route_ownership/production_route_ownership_manifest.yaml")}

    for route in ("/login", "/logout"):
        record = by_route[route]
        assert record["current_runtime_owner"] == "next"
        assert record["production_behavior"] == "next_exact"
        assert record["legacy_fallback_allowed"] is False
        assert record["delete_status"] == "deletion_locked"
        assert record["replacement_status"] == "locked"
    assert by_route["/auth/wecom/start"]["current_runtime_owner"] == "next"
    assert by_route["/auth/wecom/callback"]["current_runtime_owner"] == "next"
    assert by_route["/auth/wecom/start"]["delete_status"] == "deletion_locked"
    assert by_route["/auth/wecom/callback"]["delete_status"] == "deletion_locked"
