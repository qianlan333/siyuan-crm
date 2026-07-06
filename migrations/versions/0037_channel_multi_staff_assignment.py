"""preserve siyuan channel assignment compatibility revision.

Revision ID: 0037_channel_multi_staff_assignment
Revises: 0036_wechat_shop_sync_runs
"""

from __future__ import annotations


revision = "0037_channel_multi_staff_assignment"
down_revision = "0036_wechat_shop_sync_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The generic schema lives in 0036_channel_multi_staff_assignment.
    # Keep this siyuan-only revision ID so already-stamped databases and the
    # duplicate-head merge revision remain traversable without recreating the
    # pre-unionid external_contact_id shape.
    return None


def downgrade() -> None:
    return None
