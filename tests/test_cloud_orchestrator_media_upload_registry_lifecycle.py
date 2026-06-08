from __future__ import annotations

import yaml
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "docs/architecture/legacy_exit_route_registry.yaml"
MANIFEST = ROOT / "docs/route_ownership/production_route_ownership_manifest.yaml"


def _records(path: Path, key: str = "routes") -> list[dict]:
    return list((yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get(key) or [])


def test_cloud_orchestrator_media_upload_registry_is_next_adapter_locked():
    records = _records(REGISTRY)
    record = next(item for item in records if item.get("route_id") == "cloud_orchestrator_media_upload_adapter")

    assert record["path_pattern"] == "/api/admin/cloud-orchestrator/media/upload"
    assert record["methods"] == ["POST", "OPTIONS"]
    assert record["runtime_owner"] == "next_adapter"
    assert record["legacy_fallback_allowed"] is False
    assert record["legacy_source"] == ""
    assert record["external_side_effect_risk"] == "high"
    assert record["adapter_mode"] == "production"
    assert record["delete_status"] == "deletion_locked"
    assert record["replacement_status"] == "locked"
    assert "Next native WeComMediaUploadClient" in record["notes"]
    assert "no legacy_flask_facade" in record["notes"]
    assert "no _legacy_app" in record["notes"]
    assert "no legacy_wecom_client_from_app" in record["notes"]
    assert "wecom_media_upload_executed=true" in record["notes"]


def test_cloud_orchestrator_media_upload_manifest_is_next_adapter_locked():
    records = _records(MANIFEST)
    record = next(item for item in records if item.get("route_pattern") == "/api/admin/cloud-orchestrator/media/upload")

    assert record["methods"] == ["POST", "OPTIONS"]
    assert record["capability_owner"] == "aicrm_next.cloud_orchestrator"
    assert record["current_runtime_owner"] == "next"
    assert record["production_behavior"] == "next_adapter_real_upload"
    assert record["legacy_fallback_allowed"] is False
    assert record["external_side_effect_risk"] == "high"
    assert record["adapter_mode"] == "production"
    assert record["delete_ready"] is True
    assert record["delete_status"] == "deletion_locked"
    assert record["replacement_status"] == "locked"
    assert "Next native WeComMediaUploadClient" in record["notes"]
    assert "no legacy_flask_facade" in record["notes"]
    assert "no _legacy_app" in record["notes"]
    assert "no legacy_wecom_client_from_app" in record["notes"]
    assert "wecom_media_upload_executed=true" in record["notes"]
