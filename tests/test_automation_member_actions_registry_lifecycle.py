from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "docs/architecture/legacy_exit_route_registry.yaml"
MANIFEST = ROOT / "docs/route_ownership/production_route_ownership_manifest.yaml"


ACTION_RECORDS = {
    "automation_member_put_in_pool_next_command": "/api/admin/automation-conversion/member/put-in-pool",
    "automation_member_remove_from_pool_next_command": "/api/admin/automation-conversion/member/remove-from-pool",
    "automation_member_set_focus_next_command": "/api/admin/automation-conversion/member/set-focus",
    "automation_member_set_normal_next_command": "/api/admin/automation-conversion/member/set-normal",
    "automation_member_mark_won_next_command": "/api/admin/automation-conversion/member/mark-won",
    "automation_member_unmark_won_next_command": "/api/admin/automation-conversion/member/unmark-won",
    "automation_member_push_openclaw_next_command": "/api/admin/automation-conversion/member/push-openclaw",
}


def _records(path: Path, key: str = "routes") -> list[dict]:
    return list((yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get(key) or [])


def test_member_action_registry_records_are_locked():
    records = {item.get("route_id"): item for item in _records(REGISTRY)}

    detail = records["automation_member_detail_next_read_model"]
    assert detail["path_pattern"] == "/api/admin/automation-conversion/member"
    assert detail["methods"] == ["GET", "HEAD"]
    assert detail["runtime_owner"] == "next_read_model"
    assert detail["legacy_fallback_allowed"] is False
    assert detail["external_side_effect_risk"] == "none"
    assert detail["delete_status"] == "deletion_locked"
    assert detail["replacement_status"] == "locked"

    for route_id, route_path in ACTION_RECORDS.items():
        record = records[route_id]
        assert record["path_pattern"] == route_path
        assert record["methods"] == ["POST", "OPTIONS"]
        assert record["runtime_owner"] == "next_command"
        assert record["legacy_fallback_allowed"] is False
        assert record["external_side_effect_risk"] == ("high" if route_id == "automation_member_push_openclaw_next_command" else "medium")
        assert record["adapter_mode"] == "real_blocked"
        assert record["delete_status"] == "deletion_locked"
        assert record["replacement_status"] == "locked"


def test_member_action_manifest_records_are_locked_and_out_of_scope_not_locked():
    records = {item.get("route_pattern"): item for item in _records(MANIFEST)}

    detail = records["/api/admin/automation-conversion/member"]
    assert detail["methods"] == ["GET", "HEAD"]
    assert detail["current_runtime_owner"] == "next_read_model"
    assert detail["production_behavior"] == "next_exact"
    assert detail["legacy_fallback_allowed"] is False
    assert detail["external_side_effect_risk"] == "none"
    assert detail["delete_status"] == "deletion_locked"
    assert detail["replacement_status"] == "locked"

    for route_path in ACTION_RECORDS.values():
        record = records[route_path]
        assert record["methods"] == ["POST", "OPTIONS"]
        assert record["current_runtime_owner"] == "next_command"
        assert record["production_behavior"] == "next_command"
        assert record["legacy_fallback_allowed"] is False
        assert record["adapter_mode"] == "real_blocked"
        assert record["delete_status"] == "deletion_locked"
        assert record["replacement_status"] == "locked"

    assert "/api/admin/automation-conversion/stage/{stage_key}/manual-send" not in records
    assert "/api/admin/automation-conversion/sop/run-due" not in records
