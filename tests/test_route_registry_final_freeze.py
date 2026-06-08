from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def _records(path: str) -> list[dict]:
    return list((yaml.safe_load((ROOT / path).read_text(encoding="utf-8")) or {}).get("routes") or [])


def test_legacy_exit_registry_has_no_active_legacy_fallback() -> None:
    for record in _records("docs/architecture/legacy_exit_route_registry.yaml"):
        assert record.get("legacy_fallback_allowed") is not True, record.get("route_id")
        assert record.get("runtime_owner") not in {"production_compat", "legacy_forward"}, record.get("route_id")
        assert record.get("delete_status") != "next_primary_with_legacy_rollback", record.get("route_id")


def test_production_manifest_has_no_active_legacy_forward() -> None:
    for record in _records("docs/route_ownership/production_route_ownership_manifest.yaml"):
        assert record.get("legacy_fallback_allowed") is not True, record.get("route_pattern")
        assert record.get("current_runtime_owner") not in {"production_compat", "legacy_forward"}, record.get("route_pattern")
        assert record.get("production_behavior") not in {"legacy_forward", "next_primary_with_legacy_rollback"}, record.get("route_pattern")


def test_final_closeout_records_are_locked() -> None:
    registry = {record["route_id"]: record for record in _records("docs/architecture/legacy_exit_route_registry.yaml") if record.get("route_id")}
    for route_id in (
        "frontend_compat_auth_pages",
        "frontend_compat_logout_pages",
        "public_product_page_next_landing",
        "questionnaire_public_h5_out_of_scope",
        "checkout_wechat_next_checkout",
        "wechat_pay_notify_next_payment_notify",
        "admin_wechat_pay_wildcard_final_closeout",
    ):
        record = registry[route_id]
        assert record["legacy_fallback_allowed"] is False
        assert record["delete_status"] == "deletion_locked"
        assert record["replacement_status"] == "locked"


def test_public_h5_questionnaire_manifest_is_final_locked() -> None:
    manifest = {record["route_pattern"]: record for record in _records("docs/route_ownership/production_route_ownership_manifest.yaml")}
    record = manifest["/api/h5/questionnaires*"]

    assert record["legacy_fallback_allowed"] is False
    assert record["production_behavior"] == "guarded_preview"
    assert record["delete_ready"] is True
    assert record["delete_status"] == "deletion_locked"
    assert record["replacement_status"] == "locked"


def test_questionnaire_auxiliary_admin_read_routes_are_locked_next_native() -> None:
    registry = {record["route_id"]: record for record in _records("docs/architecture/legacy_exit_route_registry.yaml") if record.get("route_id")}

    for route_id in (
        "questionnaire_admin_share_out_of_scope",
        "questionnaire_admin_latest_submit_debug_out_of_scope",
    ):
        record = registry[route_id]
        assert record["legacy_fallback_allowed"] is False
        assert record["runtime_owner"] == "next_native"
        assert record["legacy_source"] == ""
        assert record["delete_status"] == "deletion_locked"
        assert record["replacement_status"] == "locked"
        assert record["checker"] == "tests/test_questionnaire_admin_read_registry_lifecycle.py"
