from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs" / "architecture" / "data_table_lifecycle_manifest.yml"
LINEAGE = ROOT / "docs" / "architecture" / "event_effect_table_lineage.md"

EVENT_EFFECT_TABLES = {
    "domain_event_outbox",
    "external_push_delivery",
    "outbound_webhook_deliveries",
    "outbound_event_outbox",
    "internal_event",
    "internal_event_consumer_run",
    "internal_event_consumer_attempt",
    "external_effect_job",
    "external_effect_attempt",
}


def _manifest_tables() -> dict:
    data = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    return dict(data["tables"])


def test_event_effect_tables_are_registered_in_lifecycle_manifest() -> None:
    tables = _manifest_tables()
    assert EVENT_EFFECT_TABLES <= set(tables)

    assert tables["internal_event"]["lifecycle"] == "event"
    assert tables["internal_event_consumer_run"]["lifecycle"] == "queue"
    assert tables["external_effect_job"]["lifecycle"] == "queue"
    assert tables["external_effect_attempt"]["lifecycle"] == "audit"
    assert tables["external_push_delivery"]["lifecycle"] == "legacy_boundary"
    assert tables["outbound_webhook_deliveries"]["lifecycle"] == "queue"

    for table_name in EVENT_EFFECT_TABLES:
        assert tables[table_name]["replacement"] is not None
        assert "tests/test_event_effect_table_lineage.py" in tables[table_name]["guard_tests"]


def test_event_effect_lineage_doc_declares_canonical_and_legacy_boundaries() -> None:
    source = LINEAGE.read_text(encoding="utf-8")
    for table_name in EVENT_EFFECT_TABLES:
        assert f"`{table_name}`" in source

    assert "internal_event for in-process business state fanout" in source
    assert "external_effect_job for real external side effects" in source
    assert "active runtime references still exist" in source
    assert "not deleted in" in source
