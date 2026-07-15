"""add immutable operation-cycle reports and read projections.

Revision ID: 0113_operation_cycles
Revises: 0112_sync_fde_quarter_members
"""

from __future__ import annotations

from alembic import op


revision = "0113_operation_cycles"
down_revision = "0112_sync_fde_quarter_members"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE operation_cycle_strategies (
            id BIGSERIAL PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT 'aicrm',
            strategy_key TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            cadence TEXT NOT NULL DEFAULT '',
            timezone TEXT NOT NULL DEFAULT 'Asia/Shanghai',
            status TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'paused', 'archived', 'draft')),
            current_version INTEGER NOT NULL DEFAULT 1 CHECK (current_version > 0),
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_operation_cycle_strategies_tenant_key UNIQUE (tenant_id, strategy_key)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE operation_cycle_strategy_versions (
            id BIGSERIAL PRIMARY KEY,
            strategy_id BIGINT NOT NULL REFERENCES operation_cycle_strategies(id) ON DELETE CASCADE,
            version INTEGER NOT NULL CHECK (version > 0),
            label TEXT NOT NULL DEFAULT '',
            objective TEXT NOT NULL DEFAULT '',
            definition_json JSONB NOT NULL DEFAULT '{}'::jsonb
                CHECK (jsonb_typeof(definition_json) = 'object'),
            version_hash TEXT NOT NULL CHECK (length(version_hash) = 64),
            effective_from TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_operation_cycle_strategy_versions UNIQUE (strategy_id, version)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE operation_cycle_runs (
            id BIGSERIAL PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT 'aicrm',
            strategy_id BIGINT NOT NULL REFERENCES operation_cycle_strategies(id) ON DELETE CASCADE,
            strategy_version_id BIGINT NOT NULL REFERENCES operation_cycle_strategy_versions(id),
            run_key TEXT NOT NULL,
            label TEXT NOT NULL DEFAULT '',
            objective TEXT NOT NULL DEFAULT '',
            plan_version TEXT NOT NULL DEFAULT '',
            plan_status TEXT NOT NULL DEFAULT '',
            plan_source TEXT NOT NULL DEFAULT '',
            started_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            intended_send_at TIMESTAMPTZ,
            plan_scheduled_for TIMESTAMPTZ,
            first_sent_at TIMESTAMPTZ,
            last_sent_at TIMESTAMPTZ,
            execution_stage TEXT NOT NULL DEFAULT 'scheduled'
                CHECK (execution_stage IN ('scheduled','preflight','decisioning','dry_run','review','delivery','observing','postmortem','closed')),
            review_status TEXT NOT NULL DEFAULT 'not_created'
                CHECK (review_status IN ('not_created','pending','approved','rejected','cancelled')),
            delivery_status TEXT NOT NULL DEFAULT 'not_started'
                CHECK (delivery_status IN ('not_started','waiting_window','dispatching','partial','completed','failed','cancelled')),
            data_status TEXT NOT NULL DEFAULT 'unavailable'
                CHECK (data_status IN ('unavailable','collecting','early','mature','partial','attribution_gap')),
            optimization_status TEXT NOT NULL DEFAULT 'none'
                CHECK (optimization_status IN ('none','draft','pending_confirmation','accepted','rejected','applied')),
            artifact_status TEXT NOT NULL DEFAULT 'source_missing'
                CHECK (artifact_status IN ('complete','partial','source_missing','snapshot_only')),
            funnel_json JSONB NOT NULL DEFAULT '{}'::jsonb
                CHECK (jsonb_typeof(funnel_json) = 'object'),
            retrospective_json JSONB NOT NULL DEFAULT '{}'::jsonb
                CHECK (jsonb_typeof(retrospective_json) = 'object'),
            next_iteration_json JSONB NOT NULL DEFAULT '{}'::jsonb
                CHECK (jsonb_typeof(next_iteration_json) = 'object'),
            fact_conflict BOOLEAN NOT NULL DEFAULT FALSE,
            latest_snapshot_revision INTEGER NOT NULL DEFAULT 0 CHECK (latest_snapshot_revision >= 0),
            latest_snapshot_id BIGINT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_operation_cycle_runs_tenant_key UNIQUE (tenant_id, run_key)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE operation_cycle_attempts (
            id BIGSERIAL PRIMARY KEY,
            run_id BIGINT NOT NULL REFERENCES operation_cycle_runs(id) ON DELETE CASCADE,
            attempt_key TEXT NOT NULL,
            parent_attempt_key TEXT,
            status TEXT NOT NULL CHECK (status IN ('running','completed','blocked')),
            started_at TIMESTAMPTZ,
            ended_at TIMESTAMPTZ,
            blocked_reason TEXT NOT NULL DEFAULT '',
            summary_json JSONB NOT NULL DEFAULT '{}'::jsonb
                CHECK (jsonb_typeof(summary_json) = 'object'),
            last_snapshot_id BIGINT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_operation_cycle_attempts_run_key UNIQUE (run_id, attempt_key)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE operation_cycle_snapshots (
            id BIGSERIAL PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT 'aicrm',
            run_id BIGINT NOT NULL REFERENCES operation_cycle_runs(id) ON DELETE CASCADE,
            report_id TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            snapshot_revision INTEGER NOT NULL CHECK (snapshot_revision > 0),
            schema_version TEXT NOT NULL CHECK (schema_version = 'operation_cycle_snapshot.v1'),
            payload_hash TEXT NOT NULL CHECK (length(payload_hash) = 64),
            payload_json JSONB NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
            reporter_id TEXT NOT NULL DEFAULT '',
            client_id TEXT NOT NULL DEFAULT '',
            reported_at TIMESTAMPTZ,
            receipt_id TEXT NOT NULL UNIQUE,
            received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_operation_cycle_snapshots_tenant_report UNIQUE (tenant_id, report_id),
            CONSTRAINT uq_operation_cycle_snapshots_tenant_idempotency UNIQUE (tenant_id, idempotency_key),
            CONSTRAINT uq_operation_cycle_snapshots_run_revision UNIQUE (run_id, snapshot_revision)
        )
        """
    )
    op.execute(
        "ALTER TABLE operation_cycle_runs ADD CONSTRAINT fk_operation_cycle_runs_latest_snapshot "
        "FOREIGN KEY (latest_snapshot_id) REFERENCES operation_cycle_snapshots(id)"
    )
    op.execute(
        "ALTER TABLE operation_cycle_attempts ADD CONSTRAINT fk_operation_cycle_attempts_last_snapshot "
        "FOREIGN KEY (last_snapshot_id) REFERENCES operation_cycle_snapshots(id)"
    )
    op.execute(
        """
        CREATE TABLE operation_cycle_stages (
            id BIGSERIAL PRIMARY KEY,
            run_id BIGINT NOT NULL REFERENCES operation_cycle_runs(id) ON DELETE CASCADE,
            attempt_id BIGINT NOT NULL REFERENCES operation_cycle_attempts(id) ON DELETE CASCADE,
            stage_key TEXT NOT NULL,
            stage_name TEXT NOT NULL
                CHECK (stage_name IN ('scheduled','preflight','decisioning','dry_run','review','delivery','observing','postmortem','closed')),
            status TEXT NOT NULL CHECK (status IN ('running','completed','blocked')),
            started_at TIMESTAMPTZ,
            ended_at TIMESTAMPTZ,
            blocked_reason TEXT NOT NULL DEFAULT '',
            summary_json JSONB NOT NULL DEFAULT '{}'::jsonb
                CHECK (jsonb_typeof(summary_json) = 'object'),
            last_snapshot_id BIGINT NOT NULL REFERENCES operation_cycle_snapshots(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_operation_cycle_stages_run_key UNIQUE (run_id, stage_key)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE operation_cycle_metrics (
            id BIGSERIAL PRIMARY KEY,
            run_id BIGINT NOT NULL REFERENCES operation_cycle_runs(id) ON DELETE CASCADE,
            metric_key TEXT NOT NULL,
            label TEXT NOT NULL,
            numerator DOUBLE PRECISION,
            denominator DOUBLE PRECISION,
            value DOUBLE PRECISION,
            unit TEXT NOT NULL DEFAULT 'count',
            observation_window TEXT NOT NULL,
            data_source TEXT NOT NULL,
            data_quality TEXT NOT NULL,
            limitations_json JSONB NOT NULL DEFAULT '[]'::jsonb
                CHECK (jsonb_typeof(limitations_json) = 'array'),
            is_causal BOOLEAN NOT NULL DEFAULT FALSE CHECK (is_causal = FALSE),
            value_status TEXT NOT NULL DEFAULT 'unknown'
                CHECK (value_status IN ('observed','not_started','not_due','unknown','not_applicable','blocked','instrumentation_missing','partial_lower_bound')),
            last_snapshot_id BIGINT NOT NULL REFERENCES operation_cycle_snapshots(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_operation_cycle_metrics_run_key UNIQUE (run_id, metric_key)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE operation_cycle_references (
            id BIGSERIAL PRIMARY KEY,
            run_id BIGINT NOT NULL REFERENCES operation_cycle_runs(id) ON DELETE CASCADE,
            reference_key TEXT NOT NULL,
            reference_type TEXT NOT NULL
                CHECK (reference_type IN ('broadcast_job','push_center','delivery_lineage','report','artifact','other')),
            label TEXT NOT NULL DEFAULT '',
            source_system TEXT NOT NULL DEFAULT '',
            source_id TEXT NOT NULL DEFAULT '',
            href TEXT NOT NULL DEFAULT '',
            evidence_hash TEXT NOT NULL DEFAULT '',
            data_status TEXT NOT NULL DEFAULT 'unknown'
                CHECK (data_status IN ('observed','not_started','not_due','unknown','not_applicable','blocked','instrumentation_missing','partial_lower_bound')),
            last_snapshot_id BIGINT NOT NULL REFERENCES operation_cycle_snapshots(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_operation_cycle_references_run_key UNIQUE (run_id, reference_key)
        )
        """
    )

    op.execute("CREATE INDEX idx_operation_cycle_runs_strategy_time ON operation_cycle_runs (strategy_id, intended_send_at DESC, id DESC)")
    op.execute("CREATE INDEX idx_operation_cycle_runs_status ON operation_cycle_runs (execution_stage, delivery_status, data_status)")
    op.execute("CREATE INDEX idx_operation_cycle_snapshots_run_received ON operation_cycle_snapshots (run_id, received_at DESC, id DESC)")
    op.execute("CREATE INDEX idx_operation_cycle_stages_run_status ON operation_cycle_stages (run_id, status, id)")
    op.execute("CREATE INDEX idx_operation_cycle_metrics_run_window ON operation_cycle_metrics (run_id, observation_window, id)")
    op.execute("CREATE INDEX idx_operation_cycle_references_source ON operation_cycle_references (source_system, source_id) WHERE source_id <> ''")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS operation_cycle_references")
    op.execute("DROP TABLE IF EXISTS operation_cycle_metrics")
    op.execute("DROP TABLE IF EXISTS operation_cycle_stages")
    op.execute("ALTER TABLE IF EXISTS operation_cycle_attempts DROP CONSTRAINT IF EXISTS fk_operation_cycle_attempts_last_snapshot")
    op.execute("ALTER TABLE IF EXISTS operation_cycle_runs DROP CONSTRAINT IF EXISTS fk_operation_cycle_runs_latest_snapshot")
    op.execute("DROP TABLE IF EXISTS operation_cycle_snapshots")
    op.execute("DROP TABLE IF EXISTS operation_cycle_attempts")
    op.execute("DROP TABLE IF EXISTS operation_cycle_runs")
    op.execute("DROP TABLE IF EXISTS operation_cycle_strategy_versions")
    op.execute("DROP TABLE IF EXISTS operation_cycle_strategies")
