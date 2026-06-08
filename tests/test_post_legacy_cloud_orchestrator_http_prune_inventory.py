from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "docs/architecture/post_legacy_cloud_orchestrator_http_prune_inventory.md"
MAIN_INVENTORY = ROOT / "docs/architecture/post_legacy_legacy_module_prune_inventory.md"

CLOUD_HTTP_MODULES = [
    "wecom_ability_service/http/cloud_orchestrator_endpoint.py",
    "wecom_ability_service/http/cloud_orchestrator_campaigns.py",
    "wecom_ability_service/http/cloud_orchestrator_campaign_details.py",
    "wecom_ability_service/http/cloud_orchestrator_media.py",
    "wecom_ability_service/http/cloud_orchestrator_pages.py",
    "wecom_ability_service/http/cloud_orchestrator_plans.py",
    "wecom_ability_service/http/cloud_orchestrator_segments.py",
]


def test_cloud_orchestrator_http_prune_inventory_exists_and_classifies_references() -> None:
    text = INVENTORY.read_text(encoding="utf-8")

    for phrase in [
        "Reference Classification",
        "Next runtime import",
        "Legacy HTTP registry",
        "Tests / monkeypatch",
        "Old fallback app",
        "Module Decisions",
        "Retained Modules",
    ]:
        assert phrase in text
    assert "None in the Cloud Orchestrator HTTP handler family" in text
    assert "domains/cloud_orchestrator" in text


def test_cloud_orchestrator_modules_are_deleted_in_prune_inventories() -> None:
    cloud_text = INVENTORY.read_text(encoding="utf-8")
    main_text = MAIN_INVENTORY.read_text(encoding="utf-8")

    for module in CLOUD_HTTP_MODULES:
        assert f"`{module}`" in cloud_text
        assert f"`{module}`" in main_text
        cloud_row = next(line for line in cloud_text.splitlines() if f"`{module}`" in line)
        main_row = next(line for line in main_text.splitlines() if f"`{module}`" in line)
        assert "`deleted`" in cloud_row
        assert "`deleted`" in main_row
        assert "keep_temporarily_historical" not in cloud_row
        assert "keep_temporarily_historical" not in main_row


def test_cloud_orchestrator_inventory_records_next_replacements_and_validation() -> None:
    text = INVENTORY.read_text(encoding="utf-8")

    for phrase in [
        "aicrm_next.cloud_orchestrator.api",
        "aicrm_next.cloud_orchestrator.media_upload",
        "aicrm_next.post_legacy_deferred.api",
        "Next `TestClient` batch-start command",
        "production_compat_route_count",
        "legacy_fallback_routes_count",
        "deleted_but_still_registered_count",
    ]:
        assert phrase in text
