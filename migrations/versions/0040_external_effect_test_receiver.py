"""external effect test receiver receipts"""

from __future__ import annotations

from alembic import op

revision = "0040_external_effect_test_receiver"
down_revision = "0039_external_effect_queue"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS external_effect_test_receipt (
            id BIGSERIAL PRIMARY KEY,
            receipt_id TEXT UNIQUE NOT NULL,
            receiver_token TEXT NOT NULL,
            job_id BIGINT,
            effect_type TEXT NOT NULL,
            trace_id TEXT NOT NULL DEFAULT '',
            idempotency_key TEXT NOT NULL DEFAULT '',
            target_type TEXT NOT NULL DEFAULT '',
            target_id TEXT NOT NULL DEFAULT '',
            business_type TEXT NOT NULL DEFAULT '',
            business_id TEXT NOT NULL DEFAULT '',
            request_method TEXT NOT NULL DEFAULT 'POST',
            request_path TEXT NOT NULL DEFAULT '',
            headers_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            payload_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            payload_hash TEXT NOT NULL DEFAULT '',
            body_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            signature_valid BOOLEAN,
            response_status INTEGER NOT NULL DEFAULT 200,
            received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_external_effect_test_receipt_token ON external_effect_test_receipt (receiver_token)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_external_effect_test_receipt_job ON external_effect_test_receipt (job_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_external_effect_test_receipt_effect ON external_effect_test_receipt (effect_type)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_external_effect_test_receipt_trace ON external_effect_test_receipt (trace_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_external_effect_test_receipt_idempotency ON external_effect_test_receipt (idempotency_key)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_external_effect_test_receipt_received ON external_effect_test_receipt (received_at)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_external_effect_test_receipt_received")
    op.execute("DROP INDEX IF EXISTS idx_external_effect_test_receipt_idempotency")
    op.execute("DROP INDEX IF EXISTS idx_external_effect_test_receipt_trace")
    op.execute("DROP INDEX IF EXISTS idx_external_effect_test_receipt_effect")
    op.execute("DROP INDEX IF EXISTS idx_external_effect_test_receipt_job")
    op.execute("DROP INDEX IF EXISTS idx_external_effect_test_receipt_token")
    op.execute("DROP TABLE IF EXISTS external_effect_test_receipt")
