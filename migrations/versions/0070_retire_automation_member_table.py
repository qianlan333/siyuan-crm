"""drop retired automation_member table and derived view.

Revision ID: 0070_retire_automation_member_table
Revises: 0069_unionid_channel_contact_cleanup
"""

from __future__ import annotations

from alembic import op


revision = "0070_retire_automation_member_table"
down_revision = "0069_unionid_channel_contact_cleanup"
branch_labels = None
depends_on = None


DROP_TABLES = ("automation_member",)
DROP_VIEWS = ("automation_member_interaction_stats",)


def upgrade() -> None:
    for view_name in DROP_VIEWS:
        op.execute(f"DROP VIEW IF EXISTS {view_name}")
    for table_name in DROP_TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")


def downgrade() -> None:
    # The legacy automation_member table is retired. Restoring it requires an
    # older release and database backup; current runtime must stay off this table.
    return None
