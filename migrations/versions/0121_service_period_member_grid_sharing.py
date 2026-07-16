"""add workspace collaborators and revocable public sharing.

Lifecycle manifest entries:
- service_period_member_collaborators: canonical, service_period write owner
- service_period_member_shares: canonical, service_period write owner

Existing active non-super-admin users are backfilled as read collaborators for
the products that exist at migration time. New products remain super-admin-only
until explicitly shared.

Revision ID: 0121_service_period_member_grid_sharing
Revises: 0120_service_period_member_views
"""

from __future__ import annotations

from alembic import op


revision = "0121_service_period_member_grid_sharing"
down_revision = "0120_service_period_member_views"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS service_period_member_collaborators (
            id BIGSERIAL PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT 'aicrm',
            service_product_id BIGINT NOT NULL REFERENCES service_period_products(id) ON DELETE CASCADE,
            admin_user_id BIGINT NOT NULL REFERENCES admin_users(id) ON DELETE CASCADE,
            wecom_userid TEXT NOT NULL CHECK (BTRIM(wecom_userid) <> ''),
            display_name TEXT NOT NULL DEFAULT '',
            avatar_url TEXT NOT NULL DEFAULT '',
            permission TEXT NOT NULL CHECK (permission IN ('read', 'edit')),
            version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
            created_by TEXT NOT NULL DEFAULT '',
            updated_by TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (tenant_id, service_product_id, admin_user_id),
            UNIQUE (tenant_id, service_product_id, wecom_userid)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_service_period_member_collaborators_admin
        ON service_period_member_collaborators (tenant_id, admin_user_id, service_product_id)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS service_period_member_shares (
            id BIGSERIAL PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT 'aicrm',
            service_product_id BIGINT NOT NULL REFERENCES service_period_products(id) ON DELETE CASCADE,
            enabled BOOLEAN NOT NULL DEFAULT FALSE,
            public_id TEXT NOT NULL DEFAULT '',
            generation INTEGER NOT NULL DEFAULT 0 CHECK (generation >= 0),
            version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
            created_by TEXT NOT NULL DEFAULT '',
            updated_by TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (tenant_id, service_product_id)
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_service_period_member_shares_public_id
        ON service_period_member_shares (public_id)
        WHERE public_id <> ''
        """
    )
    op.execute(
        """
        INSERT INTO service_period_member_shares (
            tenant_id, service_product_id, enabled, public_id, generation,
            version, created_by, updated_by, created_at, updated_at
        )
        SELECT products.tenant_id, products.id, FALSE, '', 0, 1,
               'migration', 'migration', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM service_period_products products
        WHERE products.deleted = FALSE
        ON CONFLICT (tenant_id, service_product_id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO service_period_member_collaborators (
            tenant_id, service_product_id, admin_user_id, wecom_userid,
            display_name, avatar_url, permission, version,
            created_by, updated_by, created_at, updated_at
        )
        SELECT
            products.tenant_id,
            products.id,
            users.id,
            users.wecom_userid,
            COALESCE(NULLIF(users.display_name, ''), users.wecom_userid),
            COALESCE(directory.avatar_url, ''),
            'read',
            1,
            'migration',
            'migration',
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        FROM service_period_products products
        CROSS JOIN admin_users users
        LEFT JOIN admin_wecom_directory_members directory
          ON directory.wecom_userid = users.wecom_userid
         AND directory.is_active = TRUE
        WHERE products.deleted = FALSE
          AND users.is_active = TRUE
          AND users.login_enabled = TRUE
          AND COALESCE(users.wecom_userid, '') <> ''
          AND COALESCE(users.admin_level, 'admin') <> 'super_admin'
          AND NOT EXISTS (
              SELECT 1 FROM admin_user_roles roles
              WHERE roles.admin_user_id = users.id AND roles.role_code = 'super_admin'
          )
        ON CONFLICT (tenant_id, service_product_id, admin_user_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_service_period_member_shares_public_id")
    op.execute("DROP INDEX IF EXISTS idx_service_period_member_collaborators_admin")
    op.execute("DROP TABLE IF EXISTS service_period_member_shares")
    op.execute("DROP TABLE IF EXISTS service_period_member_collaborators")
