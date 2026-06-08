from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "docs/architecture/legacy_exit_route_registry.yaml"
MANIFEST = ROOT / "docs/route_ownership/production_route_ownership_manifest.yaml"


def _records(path: Path, key: str = "routes") -> list[dict]:
    return list((yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get(key) or [])


def test_run_due_registry_is_next_runtime_plan_locked():
    record = next(item for item in _records(REGISTRY) if item.get("route_id") == "cloud_orchestrator_campaigns_run_due_safe_timer")

    assert record["path_pattern"] == "/api/admin/cloud-orchestrator/campaigns/run-due*"
    assert record["methods"] == ["POST", "OPTIONS"]
    assert record["runtime_owner"] == "next_runtime_plan"
    assert record["legacy_fallback_allowed"] is False
    assert record["legacy_source"] == ""
    assert record["external_side_effect_risk"] == "high"
    assert record["adapter_mode"] == "real_blocked"
    assert record["delete_status"] == "deletion_locked"
    assert record["replacement_status"] == "locked"
    assert "production_compat rollback removed" in record["notes"]
    assert "campaign_runtime_executed=false" in record["notes"]


def test_run_due_manifest_is_next_safe_mode_locked():
    record = next(item for item in _records(MANIFEST) if item.get("route_pattern") == "/api/admin/cloud-orchestrator/campaigns/run-due*")

    assert record["methods"] == ["POST", "OPTIONS"]
    assert record["current_runtime_owner"] == "next_runtime_plan"
    assert record["production_behavior"] == "next_command"
    assert record["legacy_fallback_allowed"] is False
    assert record["external_side_effect_risk"] == "high"
    assert record["adapter_mode"] == "real_blocked"
    assert record["delete_ready"] is True
    assert record["delete_status"] == "deletion_locked"
    assert record["replacement_status"] == "locked"
    assert "Legacy rollback removed" in record["notes"]
    assert "wecom_send_executed=false" in record["notes"]


def test_campaign_read_write_and_media_upload_locked_state_does_not_regress():
    registry_records = _records(REGISTRY)
    manifest_records = _records(MANIFEST)

    read = next(item for item in registry_records if item.get("route_id") == "cloud_orchestrator_campaigns_read_family")
    write = next(item for item in registry_records if item.get("route_id") == "cloud_orchestrator_campaigns_write_legacy_family")
    media = next(item for item in registry_records if item.get("route_id") == "cloud_orchestrator_media_upload_adapter")
    for record in [read, write, media]:
        assert record["legacy_fallback_allowed"] is False
        assert record["delete_status"] == "deletion_locked"
        assert record["replacement_status"] == "locked"

    manifest_read = next(item for item in manifest_records if item.get("route_pattern") == "/api/admin/cloud-orchestrator/campaigns*" and item.get("methods") == ["GET"])
    manifest_write = next(item for item in manifest_records if item.get("route_pattern") == "/api/admin/cloud-orchestrator/campaigns*" and item.get("methods") == ["POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    manifest_media = next(item for item in manifest_records if item.get("route_pattern") == "/api/admin/cloud-orchestrator/media/upload")
    for record in [manifest_read, manifest_write, manifest_media]:
        assert record["legacy_fallback_allowed"] is False
        assert record["delete_status"] == "deletion_locked"
        assert record["replacement_status"] == "locked"


def test_automation_timer_manifest_is_now_next_safe_mode_locked():
    records = _records(MANIFEST)
    automation = next(item for item in records if item.get("route_pattern") == "/api/admin/automation-conversion/jobs/run-due*")

    assert automation["current_runtime_owner"] == "next_runtime_plan"
    assert automation["production_behavior"] == "next_command"
    assert automation["legacy_fallback_allowed"] is False
    assert automation["delete_ready"] is True
    assert automation["delete_status"] == "deletion_locked"
    assert automation["replacement_status"] == "locked"
