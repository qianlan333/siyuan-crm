"""image_library variants for thumbnails and previews

Revision ID: 0017
Revises: 0016_wecom_corp_tag_catalog
Create Date: 2026-05-26

Store generated image variants in the database first, while keeping the
storage_backend/storage_key/public_url shape ready for object storage or CDN.
"""
from __future__ import annotations

from alembic import op


revision: str = "0017"
down_revision: str | None = "0016_wecom_corp_tag_catalog"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS image_library_variants (
            id BIGSERIAL PRIMARY KEY,
            image_id BIGINT NOT NULL REFERENCES image_library(id) ON DELETE CASCADE,
            variant_key TEXT NOT NULL,
            storage_backend TEXT NOT NULL DEFAULT 'db_base64',
            storage_key TEXT NOT NULL DEFAULT '',
            public_url TEXT NOT NULL DEFAULT '',
            mime_type TEXT NOT NULL DEFAULT 'image/png',
            width INTEGER NOT NULL DEFAULT 0,
            height INTEGER NOT NULL DEFAULT 0,
            file_size INTEGER NOT NULL DEFAULT 0,
            checksum TEXT NOT NULL DEFAULT '',
            data_base64 TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (image_id, variant_key)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_image_library_variants_image
        ON image_library_variants (image_id, variant_key)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_image_library_variants_image")
    op.execute("DROP TABLE IF EXISTS image_library_variants")
