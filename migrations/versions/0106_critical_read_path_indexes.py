"""add critical read path indexes.

Revision ID: 0106_critical_read_path_indexes
Revises: 0105_drop_legacy_cleanup_tables
"""

from __future__ import annotations

from alembic import op


revision = "0106_critical_read_path_indexes"
down_revision = "0105_drop_legacy_cleanup_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The supported baseline pre-dated the canonical corp-scoped contact mirror
    # shape, while active sync/read paths already depend on these columns. Keep
    # the additive repair in the first performance revision so a fresh install
    # exercises the same indexed schema as production.
    op.execute(
        "ALTER TABLE IF EXISTS wecom_external_contact_identity_map "
        "ADD COLUMN IF NOT EXISTS raw_profile JSONB NOT NULL DEFAULT '{}'::jsonb"
    )
    op.execute(
        "ALTER TABLE IF EXISTS wecom_external_contact_identity_map "
        "ADD COLUMN IF NOT EXISTS first_seen_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP"
    )
    op.execute(
        "ALTER TABLE IF EXISTS wecom_external_contact_identity_map "
        "ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP"
    )
    op.execute(
        "ALTER TABLE IF EXISTS wecom_external_contact_identity_map "
        "ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP"
    )
    op.execute(
        "ALTER TABLE IF EXISTS wecom_external_contact_follow_users "
        "ADD COLUMN IF NOT EXISTS corp_id TEXT NOT NULL DEFAULT ''"
    )
    op.execute(
        "ALTER TABLE IF EXISTS wecom_external_contact_follow_users "
        "ADD COLUMN IF NOT EXISTS raw_follow_user JSONB NOT NULL DEFAULT '{}'::jsonb"
    )
    op.execute(
        "ALTER TABLE IF EXISTS wecom_external_contact_follow_users "
        "ADD COLUMN IF NOT EXISTS first_seen_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP"
    )
    op.execute(
        "ALTER TABLE IF EXISTS wecom_external_contact_follow_users "
        "ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP"
    )
    op.execute(
        "ALTER TABLE IF EXISTS wecom_external_contact_follow_users "
        "ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_wecom_external_contact_identity_map_corp_external "
        "ON wecom_external_contact_identity_map (corp_id, external_userid)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_wecom_external_contact_follow_users_corp_external_user "
        "ON wecom_external_contact_follow_users (corp_id, external_userid, user_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_wecom_external_contact_follow_users_external_active "
        "ON wecom_external_contact_follow_users (external_userid, relation_status, is_primary, updated_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_customer_list_index_next_owner_id "
        "ON customer_list_index_next (owner_userid, id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_questionnaires_updated_id "
        "ON questionnaires (updated_at DESC, id DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_wecom_external_contact_follow_users_external_active")
    op.execute("DROP INDEX IF EXISTS ux_wecom_external_contact_follow_users_corp_external_user")
    op.execute("DROP INDEX IF EXISTS ux_wecom_external_contact_identity_map_corp_external")
    op.execute("DROP INDEX IF EXISTS idx_questionnaires_updated_id")
    op.execute("DROP INDEX IF EXISTS ix_customer_list_index_next_owner_id")
    # Additive baseline-repair columns are intentionally retained on release
    # rollback; older releases tolerate them and dropping them would lose mirror
    # evidence written by the newer sync path.
