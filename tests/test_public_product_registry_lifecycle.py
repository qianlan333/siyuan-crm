from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def _records(path: str) -> list[dict]:
    return list((yaml.safe_load((ROOT / path).read_text(encoding="utf-8")) or {}).get("routes") or [])


def test_public_product_registry_records_are_locked() -> None:
    records = {record["route_id"]: record for record in _records("docs/architecture/legacy_exit_route_registry.yaml") if record.get("route_id")}

    expectations = {
        "public_product_page_next_landing": "next_public_product",
        "public_pay_landing_next_blocked": "next_public_pay_landing",
        "public_product_api_next_contract": "next_public_product_api",
    }
    for route_id, owner in expectations.items():
        record = records[route_id]
        assert record["runtime_owner"] == owner
        assert record["legacy_fallback_allowed"] is False
        assert record["legacy_source"] == ""
        assert record["delete_status"] == "deletion_locked"
        assert record["replacement_status"] == "locked"


def test_public_product_manifest_records_are_locked_and_out_of_scope_retained() -> None:
    records = {record["route_pattern"]: record for record in _records("docs/route_ownership/production_route_ownership_manifest.yaml")}

    for route in ["/p/{page_slug}", "/pay/{product_code}", "/api/products*"]:
        record = records[route]
        assert record["current_runtime_owner"] == "next"
        assert record["legacy_fallback_allowed"] is False
        assert record["delete_status"] == "deletion_locked"
        assert record["replacement_status"] == "locked"

    for route in ["/api/admin/wechat-pay*", "/api/h5/wechat-pay*"]:
        record = records[route]
        assert record["legacy_fallback_allowed"] is False
        assert record["delete_ready"] is True
        assert record["delete_status"] == "deletion_locked"
        assert record["replacement_status"] == "locked"
