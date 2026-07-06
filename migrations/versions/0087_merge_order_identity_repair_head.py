"""merge order identity repair and ID-refactor migration heads.

Revision ID: 0087_merge_order_identity_repair_head
Revises: 0062_wechat_pay_order_identity_repair, 0086_merge_ai_crm_heads
"""

from __future__ import annotations


revision = "0087_merge_order_identity_repair_head"
down_revision = ("0062_wechat_pay_order_identity_repair", "0086_merge_ai_crm_heads")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
