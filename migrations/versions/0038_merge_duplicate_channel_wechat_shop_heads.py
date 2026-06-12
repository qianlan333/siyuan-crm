"""merge duplicate channel and wechat shop migration heads.

Revision ID: 0038_merge_duplicate_channel_wechat_shop_heads
Revises: 0037_merge_channel_wechat_shop_heads, 0037_merge_channel_multi_staff_and_wechat_shop_heads, 0037_channel_multi_staff_assignment
"""

from __future__ import annotations


revision = "0038_merge_duplicate_channel_wechat_shop_heads"
down_revision = (
    "0037_merge_channel_wechat_shop_heads",
    "0037_merge_channel_multi_staff_and_wechat_shop_heads",
    "0037_channel_multi_staff_assignment",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
