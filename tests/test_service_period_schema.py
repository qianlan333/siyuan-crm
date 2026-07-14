from __future__ import annotations

from pathlib import Path
import importlib.util

import yaml


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "versions" / "0095_service_period_products.py"
CLEANUP_MIGRATION = ROOT / "migrations" / "versions" / "0097_service_period_unionid_cleanup.py"
HUANGYOUCAN_USAGE_MIGRATION = ROOT / "migrations" / "versions" / "0107_service_period_huangyoucan_usage_snapshot.py"
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

    assert "mobile_snapshot TEXT NOT NULL DEFAULT ''" in text
    cleanup_text = CLEANUP_MIGRATION.read_text(encoding="utf-8")
    assert "DROP COLUMN IF EXISTS mobile_snapshot" in cleanup_text


def test_service_period_tables_registered_in_lifecycle_manifest_and_cleanup_order() -> None:
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))["tables"]

    for table in ("service_period_products", "service_period_entitlements", "service_period_events"):
        assert manifest[table]["domain"] == "service_period"
        assert manifest[table]["write_owner"] == "aicrm_next.service_period"
        expected_migration = (
            "0097_service_period_unionid_cleanup"
            if table == "service_period_entitlements"
            else "0095_service_period_products"
        )
        assert manifest[table]["migration_source"] == expected_migration

    assert "aicrm_next.service_period" in manifest["wechat_pay_orders"]["read_owners"]
    tables = conftest._TABLES_TO_TRUNCATE
    assert tables.index("service_period_events") < tables.index("service_period_entitlements")
    assert tables.index("service_period_entitlements") < tables.index("service_period_products")
    assert tables.index("service_period_products") < tables.index("wechat_pay_products")


def test_huangyoucan_usage_projection_schema_and_lifecycle_contract() -> None:
    migration = HUANGYOUCAN_USAGE_MIGRATION.read_text(encoding="utf-8")
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))["tables"]

    for table in (
        "service_period_huangyoucan_usage_snapshot",
        "service_period_huangyoucan_usage_sync_runs",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in migration
        assert manifest[table]["domain"] == "service_period"
        assert manifest[table]["write_owner"] == "aicrm_next.service_period"
        assert manifest[table]["migration_source"] == "0107_hyc_usage_snapshot"

    assert "mobile_md5 CHAR(32)" in migration
    assert "mobile TEXT" not in migration
    assert "aicrm_next.customer_read_model" in manifest["service_period_huangyoucan_usage_snapshot"]["read_owners"]
    tables = conftest._TABLES_TO_TRUNCATE
    assert tables.index("service_period_huangyoucan_usage_sync_runs") < tables.index(
        "service_period_huangyoucan_usage_snapshot"
    )
