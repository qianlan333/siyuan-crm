"""add unionid foundation to HXC dashboard snapshot.

Revision ID: 0072_hxc_snapshot_unionid_foundation
Revises: 0071_retire_conversion_trace_tables
"""

from __future__ import annotations

import importlib

from alembic import op


revision = "0072_hxc_snapshot_unionid_foundation"
down_revision = "0071_retire_conversion_trace_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE IF EXISTS user_ops_hxc_dashboard_snapshot
        ADD COLUMN IF NOT EXISTS unionid TEXT NOT NULL DEFAULT ''
        """
    )
    op.execute(
        """
        UPDATE user_ops_hxc_dashboard_snapshot snapshot
        SET unionid = identity.unionid
        FROM crm_user_identity identity
        WHERE COALESCE(snapshot.unionid, '') = ''
          AND (
              (
                  COALESCE(snapshot.external_userid, '') <> ''
                  AND (
                      identity.primary_external_userid = snapshot.external_userid
                      OR jsonb_exists(identity.external_userids_json, snapshot.external_userid)
                  )
              )
              OR (
                  COALESCE(snapshot.mobile, '') <> ''
                  AND identity.mobile_normalized = regexp_replace(snapshot.mobile, '\\D', '', 'g')
              )
          )
          AND COALESCE(identity.unionid, '') <> ''
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_hxc_snapshot_unionid
        ON user_ops_hxc_dashboard_snapshot (unionid)
        WHERE unionid <> ''
        """
    )
    _recreate_hxc_member_usage_view()


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_hxc_snapshot_unionid")
    op.execute(
        """
        ALTER TABLE IF EXISTS user_ops_hxc_dashboard_snapshot
        DROP COLUMN IF EXISTS unionid
        """
    )
    _recreate_hxc_member_usage_view()


def _recreate_hxc_member_usage_view() -> None:
    module = importlib.import_module("migrations.versions.0060_ai_audience_huangxiaocan_member_usage_view")
    module._create_huangxiaocan_member_usage_view()
