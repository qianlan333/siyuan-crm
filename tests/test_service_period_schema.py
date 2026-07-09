from __future__ import annotations

from pathlib import Path
import importlib.util

import yaml


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "versions" / "0095_service_period_products.py"
MANIFEST = ROOT / "docs" / "architecture" / "data_table_lifecycle_manifest.yml"
_CONFTEST_SPEC = importlib.util.spec_from_file_location("service_period_test_conftest", ROOT / "tests" / "conftest.py")
assert _CONFTEST_SPEC and _CONFTEST_SPEC.loader
conftest = importlib.util.module_from_spec(_CONFTEST_SPEC)
_CONFTEST_SPEC.loader.exec_module(conftest)


def test_service_period_migration_creates_required_tables_and_indexes() -> None:
    text = MIGRATION.read_text(encoding="utf-8")

    for table in ("service_period_products", "service_period_entitlements", "service_period_events"):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in text

    assert "uq_service_period_products_trade_product_id" in text
    assert "uq_service_period_products_link_slug" in text
    assert "idx_service_period_products_updated" in text
    assert "UNIQUE (tenant_id, service_product_id, unionid)" in text
    assert "idx_service_period_entitlements_product_status_end" in text
    assert "uq_service_period_events_event_once" in text
    assert "WHERE out_trade_no <> ''" in text
    for event_type in (
        "activated",
        "renewed",
        "expired",
        "disabled",
        "refunded",
        "grant_failed_missing_unionid",
        "membership_sync_failed",
        "admin_adjusted",
    ):
        assert event_type in text


def test_service_period_tables_registered_in_lifecycle_manifest_and_cleanup_order() -> None:
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))["tables"]

    for table in ("service_period_products", "service_period_entitlements", "service_period_events"):
        assert manifest[table]["domain"] == "service_period"
        assert manifest[table]["write_owner"] == "aicrm_next.service_period"
        assert manifest[table]["migration_source"] == "0095_service_period_products"

    assert "aicrm_next.service_period" in manifest["wechat_pay_orders"]["read_owners"]
    tables = conftest._TABLES_TO_TRUNCATE
    assert tables.index("service_period_events") < tables.index("service_period_entitlements")
    assert tables.index("service_period_entitlements") < tables.index("service_period_products")
    assert tables.index("service_period_products") < tables.index("wechat_pay_products")
