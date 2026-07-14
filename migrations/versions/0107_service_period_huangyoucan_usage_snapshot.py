"""add service period HuangYouCan usage projection.

Revision ID: 0107_hyc_usage_snapshot
Revises: 0106_critical_read_path_indexes
"""

from __future__ import annotations

from alembic import op


revision = "0107_hyc_usage_snapshot"
down_revision = "0106_critical_read_path_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS service_period_huangyoucan_usage_snapshot (
            huangyoucan_user_id TEXT PRIMARY KEY,
            unionid TEXT NOT NULL DEFAULT '',
            mobile_md5 CHAR(32) NOT NULL DEFAULT '',
            formally_logged_in BOOLEAN NOT NULL DEFAULT FALSE,
            has_token_usage BOOLEAN NOT NULL DEFAULT FALSE,
            learning_plan_id TEXT NOT NULL DEFAULT '',
            learning_plan_current INTEGER,
            learning_plan_total INTEGER,
            open_count_7d INTEGER NOT NULL DEFAULT 0,
            last_open_at TIMESTAMPTZ,
            refreshed_at TIMESTAMPTZ NOT NULL,
            CONSTRAINT ck_service_period_hyc_learning_plan_progress
                CHECK (
                    (learning_plan_current IS NULL AND learning_plan_total IS NULL)
                    OR (
                        learning_plan_current >= 0
                        AND learning_plan_total >= 0
                        AND learning_plan_current <= learning_plan_total
                    )
                ),
            CONSTRAINT ck_service_period_hyc_open_count_7d CHECK (open_count_7d >= 0)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_service_period_hyc_usage_unionid ON service_period_huangyoucan_usage_snapshot (unionid) WHERE unionid <> ''")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_service_period_hyc_usage_mobile_md5 ON service_period_huangyoucan_usage_snapshot (mobile_md5) WHERE mobile_md5 <> ''"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS service_period_huangyoucan_usage_sync_runs (
            id BIGSERIAL PRIMARY KEY,
            trigger_source TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL,
            source_row_count INTEGER NOT NULL DEFAULT 0,
            snapshot_row_count INTEGER NOT NULL DEFAULT 0,
            started_at TIMESTAMPTZ NOT NULL,
            finished_at TIMESTAMPTZ NOT NULL,
            error_summary TEXT NOT NULL DEFAULT '',
            CONSTRAINT ck_service_period_hyc_sync_run_status CHECK (status IN ('succeeded', 'failed')),
            CONSTRAINT ck_service_period_hyc_sync_run_counts CHECK (
                source_row_count >= 0 AND snapshot_row_count >= 0
            )
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_service_period_hyc_sync_runs_finished ON service_period_huangyoucan_usage_sync_runs (finished_at DESC, id DESC)")


def downgrade() -> None:
    # The projection is additive and contains the last known-good readonly
    # snapshot. Application rollback ignores it, so retain it for audit and a
    # later forward re-deploy instead of deleting operational evidence.
    pass
