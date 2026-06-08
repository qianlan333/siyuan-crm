from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "docs/architecture/legacy_exit_route_registry.yaml"
MANIFEST = ROOT / "docs/route_ownership/production_route_ownership_manifest.yaml"


def _records(path: Path, key: str = "routes") -> list[dict]:
    return list((yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get(key) or [])


def test_campaign_write_registry_is_next_commandbus_locked_without_rollback():
    record = next(item for item in _records(REGISTRY) if item.get("route_id") == "cloud_orchestrator_campaigns_write_legacy_family")

    assert record["path_pattern"] == "/api/admin/cloud-orchestrator/campaigns*"
    assert record["methods"] == ["POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    assert record["runtime_owner"] == "next_command"
    assert record["legacy_fallback_allowed"] is False
    assert record["legacy_source"] == ""
    assert record["external_side_effect_risk"] == "high"
    assert record["adapter_mode"] == "real_blocked"
    assert record["delete_status"] == "deletion_locked"
    assert record["replacement_status"] == "locked"
    assert "Next CommandBus" in record["notes"]
    assert "production_compat rollback removed" in record["notes"]
    assert "run-due is separately deletion_locked" in record["notes"]


def test_campaign_write_manifest_is_next_command_locked_without_rollback():
    record = next(
        item
        for item in _records(MANIFEST)
        if item.get("route_pattern") == "/api/admin/cloud-orchestrator/campaigns*"
        and item.get("methods") == ["POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    )

    assert record["current_runtime_owner"] == "next_command"
    assert record["production_behavior"] == "next_command"
    assert record["legacy_fallback_allowed"] is False
    assert record["external_side_effect_risk"] == "real_blocked"
    assert record["adapter_mode"] == "real_blocked"
    assert record["delete_ready"] is True
    assert record["delete_status"] == "deletion_locked"
    assert record["replacement_status"] == "locked"
    assert "production_compat rollback removed" in record["notes"]
    assert "no real WeCom send" in record["notes"]
    assert "no campaign execute" in record["notes"]


def test_campaign_read_locked_and_run_due_locked_state_do_not_regress():
    registry_records = _records(REGISTRY)
    manifest_records = _records(MANIFEST)

    read = next(item for item in registry_records if item.get("route_id") == "cloud_orchestrator_campaigns_read_family")
    assert read["delete_status"] == "deletion_locked"
    assert read["replacement_status"] == "locked"
    assert read["legacy_fallback_allowed"] is False

    run_due = next(item for item in manifest_records if item.get("route_pattern") == "/api/admin/cloud-orchestrator/campaigns/run-due*")
    assert run_due["current_runtime_owner"] == "next_runtime_plan"
    assert run_due["production_behavior"] == "next_command"
    assert run_due["legacy_fallback_allowed"] is False
    assert run_due["delete_ready"] is True
    assert run_due["delete_status"] == "deletion_locked"
