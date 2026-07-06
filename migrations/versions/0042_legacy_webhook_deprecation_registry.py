"""legacy webhook deprecation registry"""

from __future__ import annotations

from alembic import op


revision = "0042_legacy_webhook_deprecation_registry"
down_revision = "0041_completion_target_json"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS legacy_webhook_deprecation_registry (
            id BIGSERIAL PRIMARY KEY,
            legacy_key TEXT UNIQUE NOT NULL,
            legacy_type TEXT NOT NULL DEFAULT '',
            legacy_route TEXT NOT NULL DEFAULT '',
            legacy_module TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'deprecated',
            deprecated_at TIMESTAMPTZ,
            deprecated_by TEXT NOT NULL DEFAULT '',
            deprecation_reason TEXT NOT NULL DEFAULT '',
            replacement_route TEXT NOT NULL DEFAULT '/admin/push-center',
            delete_scheduled_at TIMESTAMPTZ,
            delete_status TEXT NOT NULL DEFAULT 'scheduled',
            delete_job_id TEXT NOT NULL DEFAULT '',
            notes_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_legacy_webhook_deprecation_status ON legacy_webhook_deprecation_registry (status, delete_status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_legacy_webhook_deprecation_due ON legacy_webhook_deprecation_registry (delete_status, delete_scheduled_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_legacy_webhook_deprecation_type ON legacy_webhook_deprecation_registry (legacy_type)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_legacy_webhook_deprecation_module ON legacy_webhook_deprecation_registry (legacy_module)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS legacy_webhook_cleanup_audit (
            id BIGSERIAL PRIMARY KEY,
            audit_id TEXT UNIQUE NOT NULL,
            legacy_key TEXT NOT NULL DEFAULT '',
            action TEXT NOT NULL DEFAULT '',
            operator TEXT NOT NULL DEFAULT '',
            before_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            after_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_legacy_webhook_cleanup_audit_key ON legacy_webhook_cleanup_audit (legacy_key, created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_legacy_webhook_cleanup_audit_action ON legacy_webhook_cleanup_audit (action, created_at)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_legacy_webhook_cleanup_audit_action")
    op.execute("DROP INDEX IF EXISTS idx_legacy_webhook_cleanup_audit_key")
    op.execute("DROP TABLE IF EXISTS legacy_webhook_cleanup_audit")
    op.execute("DROP INDEX IF EXISTS idx_legacy_webhook_deprecation_module")
    op.execute("DROP INDEX IF EXISTS idx_legacy_webhook_deprecation_type")
    op.execute("DROP INDEX IF EXISTS idx_legacy_webhook_deprecation_due")
    op.execute("DROP INDEX IF EXISTS idx_legacy_webhook_deprecation_status")
    op.execute("DROP TABLE IF EXISTS legacy_webhook_deprecation_registry")
