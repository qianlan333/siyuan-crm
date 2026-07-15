from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "versions" / "0113_operation_cycles.py"


def migration_source() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def test_migration_declares_linear_revision_and_eight_tables() -> None:
    source = migration_source()

    assert 'revision = "0113_operation_cycles"' in source
    assert 'down_revision = "0112_sync_fde_quarter_members"' in source
    tables = (
        "operation_cycle_strategies",
        "operation_cycle_strategy_versions",
        "operation_cycle_runs",
        "operation_cycle_attempts",
        "operation_cycle_snapshots",
        "operation_cycle_stages",
        "operation_cycle_metrics",
        "operation_cycle_references",
    )
    assert source.count("CREATE TABLE operation_cycle_") == len(tables)
    for table in tables:
        assert f"CREATE TABLE {table}" in source
        assert f"DROP TABLE IF EXISTS {table}" in source


def test_migration_enforces_snapshot_idempotency_and_revision_immutability() -> None:
    source = migration_source()

    assert "uq_operation_cycle_snapshots_tenant_report" in source
    assert "uq_operation_cycle_snapshots_tenant_idempotency" in source
    assert "uq_operation_cycle_snapshots_run_revision" in source
    assert "payload_hash TEXT NOT NULL CHECK (length(payload_hash) = 64)" in source
    assert "schema_version = 'operation_cycle_snapshot.v1'" in source
    assert "reporter_id TEXT NOT NULL DEFAULT ''" in source
    assert "client_id TEXT NOT NULL DEFAULT ''" in source


def test_migration_has_six_axes_plan_facts_and_noncausal_metric_guard() -> None:
    source = migration_source()

    for column in (
        "execution_stage TEXT",
        "review_status TEXT",
        "delivery_status TEXT",
        "data_status TEXT",
        "optimization_status TEXT",
        "artifact_status TEXT",
        "plan_version TEXT",
        "plan_status TEXT",
        "plan_source TEXT",
        "intended_send_at TIMESTAMPTZ",
        "plan_scheduled_for TIMESTAMPTZ",
        "first_sent_at TIMESTAMPTZ",
        "last_sent_at TIMESTAMPTZ",
    ):
        assert column in source
    assert "is_causal BOOLEAN NOT NULL DEFAULT FALSE CHECK (is_causal = FALSE)" in source
    assert "partial_lower_bound" in source
    assert "instrumentation_missing" in source


def test_migration_stores_only_aggregate_projection_fields() -> None:
    source = migration_source().lower()

    for forbidden in ("phone_number", "mobile_number", "unionid", "external_userid", "openid", "raw_message"):
        assert forbidden not in source
