"""add canonical WeCom temporary media leases.

Revision ID: 0115_wecom_media_leases
Revises: 0114_commerce_coupons
"""

from __future__ import annotations

from alembic import op


revision = "0115_wecom_media_leases"
down_revision = "0114_commerce_coupons"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS wecom_media_leases (
            id BIGSERIAL PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT 'aicrm',
            corp_id TEXT NOT NULL DEFAULT '',
            material_kind TEXT NOT NULL
                CHECK (material_kind IN ('image', 'attachment', 'miniprogram')),
            material_id BIGINT NOT NULL CHECK (material_id > 0),
            upload_kind TEXT NOT NULL
                CHECK (upload_kind IN ('image', 'attachment')),
            media_id TEXT NOT NULL DEFAULT '',
            content_sha256 TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'refreshing', 'ready', 'failed', 'invalid_source')),
            provider_created_at TIMESTAMPTZ,
            provider_expires_at TIMESTAMPTZ,
            refresh_after TIMESTAMPTZ,
            next_retry_at TIMESTAMPTZ,
            locked_until TIMESTAMPTZ,
            lock_token TEXT NOT NULL DEFAULT '',
            attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
            lease_version INTEGER NOT NULL DEFAULT 0 CHECK (lease_version >= 0),
            last_error_code TEXT NOT NULL DEFAULT '',
            last_error_message TEXT NOT NULL DEFAULT '',
            last_used_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_wecom_media_lease_scope
                UNIQUE (tenant_id, corp_id, material_kind, material_id, upload_kind)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_wecom_media_leases_refresh_due
        ON wecom_media_leases (status, refresh_after, next_retry_at, id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_wecom_media_leases_material
        ON wecom_media_leases (material_kind, material_id, upload_kind)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS wecom_media_leases")
