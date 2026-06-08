from __future__ import annotations

import yaml
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "docs/architecture/legacy_exit_route_registry.yaml"
MANIFEST = ROOT / "docs/route_ownership/production_route_ownership_manifest.yaml"

MEDIA_LIBRARY_REGISTRY_IDS = {
    "media_library_admin_pages_family",
    "media_library_image_read_family",
    "media_library_image_command_family",
    "media_library_attachment_read_family",
    "media_library_attachment_command_family",
    "media_library_miniprogram_read_family",
    "media_library_miniprogram_command_family",
}

MEDIA_LIBRARY_MANIFEST_ROUTES = {
    "/admin/image-library",
    "/admin/attachment-library",
    "/admin/miniprogram-library",
    "/api/admin/image-library*",
    "/api/admin/image-library/upload",
    "/api/admin/attachment-library*",
    "/api/admin/miniprogram-library*",
}


def _records(path: Path) -> list[dict]:
    return list((yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("routes") or [])


def test_media_library_legacy_exit_registry_remains_deletion_locked():
    records = {item.get("route_id"): item for item in _records(REGISTRY)}

    for route_id in MEDIA_LIBRARY_REGISTRY_IDS:
        record = records[route_id]
        assert record["legacy_fallback_allowed"] is False
        assert record["legacy_source"] == ""
        assert record["delete_status"] == "deletion_locked"
        assert record["replacement_status"] == "locked"


def test_media_library_production_manifest_remains_deletion_locked():
    records = {item.get("route_pattern"): item for item in _records(MANIFEST)}

    for route_path in MEDIA_LIBRARY_MANIFEST_ROUTES:
        record = records[route_path]
        assert record["legacy_fallback_allowed"] is False
        assert record["delete_ready"] is True
        assert record["delete_status"] == "deletion_locked"
        assert record["replacement_status"] == "locked"
