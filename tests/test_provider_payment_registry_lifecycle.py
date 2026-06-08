from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def _records(path: str) -> list[dict]:
    return list((yaml.safe_load((ROOT / path).read_text(encoding="utf-8")) or {}).get("routes") or [])


def test_provider_payment_registry_records_are_locked() -> None:
    records = {record["route_id"]: record for record in _records("docs/architecture/legacy_exit_route_registry.yaml") if record.get("route_id")}

    expectations = {
        "wechat_pay_notify_next_payment_notify": "next_payment_notify",
        "alipay_notify_next_payment_notify": "next_payment_notify",
        "alipay_return_next_payment_return": "next_payment_return",
        "wechat_pay_unknown_next_not_found": "next_not_found",
        "alipay_unknown_next_not_found": "next_not_found",
    }
    for route_id, owner in expectations.items():
        record = records[route_id]
        assert record["runtime_owner"] == owner
        assert record["legacy_fallback_allowed"] is False
        assert record["legacy_source"] == ""
        assert record["delete_status"] == "deletion_locked"
        assert record["replacement_status"] == "locked"


def test_provider_payment_manifest_records_are_locked() -> None:
    records = {record["route_pattern"]: record for record in _records("docs/route_ownership/production_route_ownership_manifest.yaml")}

    for route in ["/api/wechat-pay*", "/api/alipay*"]:
        record = records[route]
        assert record["current_runtime_owner"] == "next"
        assert record["production_behavior"] == "fake_adapter"
        assert record["legacy_fallback_allowed"] is False
        assert record["delete_ready"] is True
        assert record["delete_status"] == "deletion_locked"
        assert record["replacement_status"] == "locked"
        assert record["adapter_mode"] == "fake/real_blocked"

    for route in ["/api/admin/wechat-pay*", "/api/admin/alipay*", "/api/h5/wechat-pay*", "/api/h5/alipay*"]:
        record = records[route]
        assert record["legacy_fallback_allowed"] is False
        assert record["delete_ready"] is True
        assert record["delete_status"] == "deletion_locked"
        assert record["replacement_status"] == "locked"
