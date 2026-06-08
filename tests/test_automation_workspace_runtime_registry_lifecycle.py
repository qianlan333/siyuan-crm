from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "docs/architecture/legacy_exit_route_registry.yaml"
MANIFEST = ROOT / "docs/route_ownership/production_route_ownership_manifest.yaml"


def _records(path: Path, key: str = "routes") -> list[dict]:
    return list((yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get(key) or [])


def test_workspace_runtime_registry_records_are_locked():
    records = {item.get("route_id"): item for item in _records(REGISTRY)}

    expected = {
        "automation_workspace_tasks_run_due_next_safe_mode": "/api/admin/automation-conversion/tasks/run-due",
        "automation_workspace_execution_item_bazhuayu_next_safe_mode": "/api/admin/automation-conversion/execution-items/{execution_item_id}/send-via-bazhuayu",
    }
    for route_id, route_path in expected.items():
        record = records[route_id]
        assert record["path_pattern"] == route_path
        assert record["methods"] == ["POST", "OPTIONS"]
        assert record["runtime_owner"] == "next_runtime_plan"
        assert record["legacy_fallback_allowed"] is False
        assert record["legacy_source"] == ""
        assert record["external_side_effect_risk"] == "high"
        assert record["adapter_mode"] == "real_blocked"
        assert record["delete_status"] == "deletion_locked"
        assert record["replacement_status"] == "locked"


def test_workspace_runtime_manifest_records_are_locked_and_broad_families_remain_out_of_scope():
    records = {item.get("route_pattern"): item for item in _records(MANIFEST)}

    for route_path in (
        "/api/admin/automation-conversion/tasks/run-due",
        "/api/admin/automation-conversion/execution-items/{execution_item_id}/send-via-bazhuayu",
    ):
        record = records[route_path]
        assert record["methods"] == ["POST", "OPTIONS"]
        assert record["current_runtime_owner"] == "next_runtime_plan"
        assert record["production_behavior"] == "next_command"
        assert record["legacy_fallback_allowed"] is False
        assert record["external_side_effect_risk"] == "high"
        assert record["adapter_mode"] == "real_blocked"
        assert record["delete_ready"] is True
        assert record["delete_status"] == "deletion_locked"
        assert record["replacement_status"] == "locked"

    broad_tasks = records["/api/admin/automation-conversion/tasks*"]
    assert broad_tasks["current_runtime_owner"] == "next"
    assert broad_tasks["production_behavior"] == "archived_no_runtime"
    assert broad_tasks["legacy_fallback_allowed"] is False
    assert "no production_compat fallback is restored" in str(broad_tasks.get("notes") or "")

    broad_execution_items = records["/api/admin/automation-conversion/execution-items*"]
    assert broad_execution_items["current_runtime_owner"] == "next"
    assert broad_execution_items["production_behavior"] == "archived_no_runtime"
    assert broad_execution_items["legacy_fallback_allowed"] is False
    assert "no production_compat fallback is restored" in str(broad_execution_items.get("notes") or "")
    assert "/api/admin/automation-conversion/member*" not in records
