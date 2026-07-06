"""merge webhook inbox compatibility and HuangYouCan audience heads.

Revision ID: 0058_merge_webhook_inbox_and_huangyoucan_audience
Revises: 0054_webhook_inbox, 0057_huangyoucan_unregistered_ai_audience
"""

from __future__ import annotations


revision = "0058_merge_webhook_inbox_and_huangyoucan_audience"
down_revision = ("0054_webhook_inbox", "0057_huangyoucan_unregistered_ai_audience")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
