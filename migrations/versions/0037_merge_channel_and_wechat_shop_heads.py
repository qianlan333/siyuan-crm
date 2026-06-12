"""merge channel assignment and wechat shop sync heads.

Revision ID: 0037_merge_channel_wechat_shop_heads
Revises: 0036_channel_multi_staff_assignment, 0036_wechat_shop_sync_runs
"""

from __future__ import annotations


revision = "0037_merge_channel_wechat_shop_heads"
down_revision = ("0036_channel_multi_staff_assignment", "0036_wechat_shop_sync_runs")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
