"""drop external_userid from HXC dashboard snapshot.

Revision ID: 0073_drop_hxc_snapshot_external_userid
Revises: 0072_hxc_snapshot_unionid_foundation
"""

from __future__ import annotations

import importlib

from alembic import op


revision = "0073_drop_hxc_snapshot_external_userid"
down_revision = "0072_hxc_snapshot_unionid_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP VIEW IF EXISTS audience_read.huangxiaocan_member_usage_status_v1")
    op.execute(
        """
        ALTER TABLE IF EXISTS user_ops_hxc_dashboard_snapshot
        DROP COLUMN IF EXISTS external_userid
        """
    )
    _recreate_hxc_member_usage_view()


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE IF EXISTS user_ops_hxc_dashboard_snapshot
        ADD COLUMN IF NOT EXISTS external_userid TEXT NOT NULL DEFAULT ''
        """
    )
    op.execute(
        """
        UPDATE user_ops_hxc_dashboard_snapshot snapshot
        SET external_userid = identity.primary_external_userid
        FROM crm_user_identity identity
        WHERE COALESCE(snapshot.external_userid, '') = ''
          AND snapshot.unionid = identity.unionid
          AND COALESCE(identity.primary_external_userid, '') <> ''
        """
    )
    _recreate_hxc_member_usage_view()


def _recreate_hxc_member_usage_view() -> None:
    module = importlib.import_module("migrations.versions.0060_ai_audience_huangxiaocan_member_usage_view")
    module._create_huangxiaocan_member_usage_view()
