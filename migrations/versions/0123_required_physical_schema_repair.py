"""repair required physical tables on databases stamped past historical owners.

Revision ID: 0123_required_physical_schema_repair
Revises: 0122_internal_event_fanout_manifest
"""

from __future__ import annotations

import importlib


revision = "0123_required_physical_schema_repair"
down_revision = "0122_internal_event_fanout_manifest"
branch_labels = None
depends_on = None


_IDEMPOTENT_SCHEMA_OWNERS = (
    "migrations.versions.0018_hxc_dashboard_broadcast_tasks",
    "migrations.versions.0023_group_ops_webhook_rules",
    "migrations.versions.0028_owner_migration_excel_sessions",
)


def upgrade() -> None:
    for module_name in _IDEMPOTENT_SCHEMA_OWNERS:
        importlib.import_module(module_name).upgrade()


def downgrade() -> None:
    # This revision repairs tables that may already contain production data.
    # A code rollback must not delete those tables or their rows.
    return None
