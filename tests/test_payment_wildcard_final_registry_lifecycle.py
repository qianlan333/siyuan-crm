from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def _records(path: str) -> list[dict]:
    return list((yaml.safe_load((ROOT / path).read_text(encoding="utf-8")) or {}).get("routes") or [])


def test_payment_final_registry_records_are_locked() -> None:
    records = {record["route_id"]: record for record in _records("docs/architecture/legacy_exit_route_registry.yaml") if record.get("route_id")}

    expectations = {
        "admin_wechat_pay_wildcard_final_closeout": "next_payment_admin",
        "admin_alipay_wildcard_final_closeout": "next_payment_admin",
        "h5_wechat_pay_wildcard_final_closeout": "next_h5_payment_blocked",
        "h5_alipay_wildcard_final_closeout": "next_h5_payment_blocked",
    }
    for route_id, owner in expectations.items():
        record = records[route_id]
        assert record["runtime_owner"] == owner
        assert record["legacy_fallback_allowed"] is False
        assert record["legacy_source"] == ""
        assert record["delete_status"] == "deletion_locked"
        assert record["replacement_status"] == "locked"


def test_payment_final_manifest_records_are_locked() -> None:
    records = {record["route_pattern"]: record for record in _records("docs/route_ownership/production_route_ownership_manifest.yaml")}

    expectations = {
        "/api/admin/wechat-pay*": "next_payment_admin",
        "/api/admin/alipay*": "next_payment_admin",
        "/api/h5/wechat-pay*": "next_h5_payment_blocked",
        "/api/h5/alipay*": "next_h5_payment_blocked",
    }
    for route, owner in expectations.items():
        record = records[route]
        assert record["current_runtime_owner"] == owner
        assert record["production_behavior"] in {"fake_adapter", "next_blocked"}
        assert record["legacy_fallback_allowed"] is False
        assert record["delete_ready"] is True
        assert record["delete_status"] == "deletion_locked"
        assert record["replacement_status"] == "locked"


def test_production_compat_has_no_remaining_routes() -> None:
    assert not (ROOT / "aicrm_next/production_compat/api.py").exists()
