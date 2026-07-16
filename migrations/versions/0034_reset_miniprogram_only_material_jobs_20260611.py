"""reset miniprogram-only material jobs after enabling production media upload.

Revision ID: 0034_reset_miniprogram_only_material_jobs_20260611
Revises: 0033_complete_miniprogram_only_resend_20260611
"""

from __future__ import annotations

from alembic import op


revision = "0034_reset_miniprogram_only_material_jobs_20260611"
down_revision = "0033_complete_miniprogram_only_resend_20260611"
branch_labels = None
depends_on = None


GROUP_CODE = "external_second_push_feishu_mini_only_20260611_1625_huangyoucan_v1"


def upgrade() -> None:
    op.execute(
        f"""
        WITH target_campaigns AS (
            SELECT id
            FROM campaigns
            WHERE metadata_json->>'group_code' = '{GROUP_CODE}'
        )
        UPDATE broadcast_jobs bj
        SET status = 'queued',
            failure_type = NULL,
            last_error = '',
            claimed_at = NULL,
            claim_token = '',
            lease_expires_at = NULL,
            updated_at = CURRENT_TIMESTAMP
        FROM target_campaigns c
        WHERE bj.source_type = 'campaign'
          AND split_part(bj.source_id, ':', 1)::bigint = c.id
          AND bj.status = 'failed'
          AND bj.failure_type = 'material_resolve_failed'
        """
    )


def downgrade() -> None:
    return None
