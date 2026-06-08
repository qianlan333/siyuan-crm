from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def _records(path: str) -> list[dict]:
    return list((yaml.safe_load((ROOT / path).read_text(encoding="utf-8")) or {}).get("routes") or [])


def test_checkout_orders_registry_records_are_locked() -> None:
    records = {record["route_id"]: record for record in _records("docs/architecture/legacy_exit_route_registry.yaml") if record.get("route_id")}

    expectations = {
        "checkout_wechat_next_checkout": "next_checkout",
        "checkout_alipay_next_checkout": "next_checkout",
        "orders_public_read_next_order_read": "next_order_read",
        "orders_public_status_next_order_read": "next_order_read",
        "checkout_unknown_next_blocked": "next_blocked",
        "orders_unknown_child_next_not_found": "next_not_found",
    }
    for route_id, owner in expectations.items():
        record = records[route_id]
        assert record["runtime_owner"] == owner
        assert record["legacy_fallback_allowed"] is False
        assert record["legacy_source"] == ""
        assert record["delete_status"] == "deletion_locked"
        assert record["replacement_status"] == "locked"


def test_checkout_orders_manifest_records_are_locked() -> None:
    records = {record["route_pattern"]: record for record in _records("docs/route_ownership/production_route_ownership_manifest.yaml")}

    checkout = records["/api/checkout*"]
    assert checkout["current_runtime_owner"] == "next"
    assert checkout["production_behavior"] == "fake_adapter"
    assert checkout["legacy_fallback_allowed"] is False
    assert checkout["delete_ready"] is True
    assert checkout["delete_status"] == "deletion_locked"
    assert checkout["replacement_status"] == "locked"
    assert checkout["adapter_mode"] == "fake/real_blocked"

    orders = records["/api/orders*"]
    assert orders["current_runtime_owner"] == "next"
    assert orders["production_behavior"] == "next_exact"
    assert orders["legacy_fallback_allowed"] is False
    assert orders["delete_ready"] is True
    assert orders["delete_status"] == "deletion_locked"
    assert orders["replacement_status"] == "locked"

    for route in ["/api/admin/wechat-pay*", "/api/admin/alipay*", "/api/h5/wechat-pay*", "/api/h5/alipay*"]:
        record = records[route]
        assert record["legacy_fallback_allowed"] is False
        assert record["delete_ready"] is True
        assert record["delete_status"] == "deletion_locked"
        assert record["replacement_status"] == "locked"
