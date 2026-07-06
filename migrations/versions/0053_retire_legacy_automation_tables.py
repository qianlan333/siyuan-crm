"""drop retired automation runtime and program tables.

Revision ID: 0053_retire_legacy_automation_tables
Revises: 0052_ai_audience_package_version_parameters
"""

from __future__ import annotations

from alembic import op


revision = "0053_retire_legacy_automation_tables"
down_revision = "0052_ai_audience_package_version_parameters"
branch_labels = None
depends_on = None


DROP_TABLES = (
    "automation_workflow_execution_item",
    "automation_workflow_execution",
    "automation_workflow_node_content_variant",
    "automation_workflow_node_content",
    "automation_workflow_node_transition",
    "automation_workflow_node",
    "automation_workflow_goal",
    "automation_workflow",
    "automation_task_plan_v2",
    "automation_stage_entry_v2",
    "automation_membership_v2",
    "automation_event_v2",
    "automation_member_audience_entry",
    "automation_program_member_stage_history",
    "automation_program_member",
    "automation_program_admission_attempt",
    "automation_program_channel_binding",
    "automation_program_config_block",
    "automation_operation_task",
    "automation_event",
    "automation_program",
)


def upgrade() -> None:
    for table_name in DROP_TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")


def downgrade() -> None:
    # Data in these retired runtime/program tables is intentionally not migrated
    # or recreated. Restoring the legacy runtime requires restoring an older
    # release and database backup.
    return None
