from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def _records(path: str, key: str = "routes") -> list[dict]:
    payload = yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))
    return list(payload[key])


def test_hxc_registry_records_are_deletion_locked() -> None:
    by_id = {record["route_id"]: record for record in _records("docs/architecture/legacy_exit_route_registry.yaml")}

    for route_id in (
        "hxc_dashboard_admin_api_family",
        "hxc_dashboard_admin_pages_family",
        "hxc_dashboard_refresh_next_command",
        "hxc_dashboard_directory_sync_next_command",
        "hxc_dashboard_send_config_next_read",
        "hxc_dashboard_send_config_next_command",
        "hxc_dashboard_broadcast_next_command",
    ):
        record = by_id[route_id]
        assert record["legacy_fallback_allowed"] is False
        assert record["legacy_source"] == ""
        assert record["runtime_owner"] != "production_compat"
        assert record["delete_status"] == "deletion_locked"
        assert record["replacement_status"] == "locked"


def test_hxc_manifest_records_are_next_locked() -> None:
    records = _records("docs/route_ownership/production_route_ownership_manifest.yaml")
    hxc_records = [record for record in records if str(record["route_pattern"]).startswith(("/admin/hxc", "/api/admin/hxc-dashboard"))]

    assert hxc_records
    for record in hxc_records:
        assert record["current_runtime_owner"] == "next"
        assert record["production_behavior"] != "legacy_forward"
        assert record["legacy_fallback_allowed"] is False
        assert record["delete_ready"] is True
        assert record["delete_status"] == "deletion_locked"
        assert record["replacement_status"] == "locked"
