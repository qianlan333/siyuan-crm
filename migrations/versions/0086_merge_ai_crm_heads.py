"""merge AI-CRM target and ID-refactor migration heads.

Revision ID: 0086_merge_ai_crm_heads
Revises: 0062_skip_obsolete_ai_audience_member_outbound, 0085_admin_config_audit_baseline
"""

from __future__ import annotations


revision = "0086_merge_ai_crm_heads"
down_revision = ("0062_skip_obsolete_ai_audience_member_outbound", "0085_admin_config_audit_baseline")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
