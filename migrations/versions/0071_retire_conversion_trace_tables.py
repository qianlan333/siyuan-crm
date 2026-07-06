"""drop retired conversion workflow trace tables.

Revision ID: 0071_retire_conversion_trace_tables
Revises: 0070_retire_automation_member_table
"""

from __future__ import annotations

from alembic import op


revision = "0071_retire_conversion_trace_tables"
down_revision = "0070_retire_automation_member_table"
branch_labels = None
depends_on = None


DROP_INDEXES = (
    "idx_automation_execution_trace_external",
    "idx_automation_execution_trace_workflow",
    "idx_conversion_dispatch_log_external_dispatched",
)
DROP_TABLES = (
    "automation_execution_trace",
    "conversion_dispatch_log",
)


def upgrade() -> None:
    for index_name in DROP_INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {index_name}")
    for table_name in DROP_TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table_name}")


def downgrade() -> None:
    # These conversion workflow trace tables are retired. Restoring them requires
    # an older release and database backup; current runtime must stay off them.
    return None
