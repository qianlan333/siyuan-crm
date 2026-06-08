from __future__ import annotations

from pathlib import Path

from tests.post_legacy_baseline import DEFERRED_FRONTEND_API_PATTERNS

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "docs/architecture/post_legacy_deferred_api_cleanup_inventory.md"
BASELINE = ROOT / "docs/architecture/post_legacy_product_baseline_inventory.md"

DEFERRED_ROUTES = (
    "/api/admin/class-user-management/export",
    "/api/admin/cloud-orchestrator/audit",
    "/api/admin/cloud-orchestrator/observability",
    "/api/admin/wecom-customer-acquisition-links",
    "/api/admin/wecom-customer-acquisition-links/{link_id}",
    "/api/admin/wecom-customer-acquisition-links/{link_id}/{action}",
)


def test_deferred_cleanup_inventory_has_decision_matrix() -> None:
    text = INVENTORY.read_text(encoding="utf-8")

    assert "## Deferred API Decision Matrix" in text
    assert "## Code Investigation" in text
    assert "## Guardrails" in text
    assert "## Smoke Acceptance" in text
    for route in DEFERRED_ROUTES:
        assert route in text
    for decision in ("next_export", "next_cloud_observability", "next_wecom_customer_acquisition"):
        assert decision in text
    for marker in (
        "DEFERRED_FRONTEND_API_PATTERNS` is empty",
        "real WeCom blocked",
        "external_storage_executed=false",
        "wecom_api_called=false",
    ):
        assert marker in text


def test_post_legacy_baseline_deferred_whitelist_is_empty_and_closed() -> None:
    baseline = BASELINE.read_text(encoding="utf-8")

    assert DEFERRED_FRONTEND_API_PATTERNS == ()
    assert "Deferred frontend API whitelist count: 0" in baseline
    for forbidden in ("deferred_unregistered_api", "deferred_unregistered_workspace", "deprecated_historical"):
        assert forbidden not in baseline
    for status in ("closed_next_export", "closed_next_cloud_observability", "closed_next_wecom_customer_acquisition"):
        assert status in baseline
