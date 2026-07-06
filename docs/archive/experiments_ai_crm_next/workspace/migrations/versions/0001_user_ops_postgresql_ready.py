"""Create PostgreSQL-ready User Ops tables.

Revision ID: 0001_user_ops_pg
Revises:
Create Date: 2026-05-20
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_user_ops_pg"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_ops_pool_current_next",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("person_id", sa.String(length=80), nullable=True),
        sa.Column("mobile", sa.String(length=32), nullable=True),
        sa.Column("external_userid", sa.String(length=128), nullable=True),
        sa.Column("customer_name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("owner_userid", sa.String(length=128), nullable=True),
        sa.Column("owner_display_name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("class_term_no", sa.String(length=80), nullable=True),
        sa.Column("class_term_label", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("source_type", sa.String(length=80), nullable=False, server_default="lead_pool"),
        sa.Column("activation_bucket", sa.String(length=40), nullable=False, server_default="pending_input"),
        sa.Column("activation_bucket_label", sa.String(length=80), nullable=False, server_default="激活待录入"),
        sa.Column("is_mobile_bound", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("auto_do_not_disturb_reasons_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_user_ops_pool_current_next_external_userid", "user_ops_pool_current_next", ["external_userid"])
    op.create_index("ix_user_ops_pool_current_next_mobile", "user_ops_pool_current_next", ["mobile"])
    op.create_index("ix_user_ops_pool_current_next_owner_userid", "user_ops_pool_current_next", ["owner_userid"])
    op.create_index("ix_user_ops_pool_current_next_class_term_no", "user_ops_pool_current_next", ["class_term_no"])
    op.create_index("ix_user_ops_pool_current_next_activation_bucket", "user_ops_pool_current_next", ["activation_bucket"])

    op.create_table(
        "user_ops_do_not_disturb_next",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("external_userid", sa.String(length=128), nullable=True),
        sa.Column("mobile", sa.String(length=32), nullable=True),
        sa.Column("source_type", sa.String(length=40), nullable=False, server_default="manual"),
        sa.Column("reason_code", sa.String(length=80), nullable=False, server_default="manual_set"),
        sa.Column("reason_text", sa.Text(), nullable=False, server_default="运营设置"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.String(length=128), nullable=False, server_default="fixture-admin"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_user_ops_dnd_next_external_userid", "user_ops_do_not_disturb_next", ["external_userid"])
    op.create_index("ix_user_ops_dnd_next_mobile", "user_ops_do_not_disturb_next", ["mobile"])
    op.create_index(
        "ix_user_ops_dnd_next_active_reason",
        "user_ops_do_not_disturb_next",
        ["is_active", "reason_code"],
    )

    op.create_table(
        "user_ops_send_records_next",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("record_key", sa.String(length=80), nullable=False, unique=True),
        sa.Column("task_type", sa.String(length=80), nullable=False, server_default="user_ops_batch_send"),
        sa.Column("outbound_task_ids_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("task_results_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("selected_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("eligible_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sent_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_reasons_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("include_do_not_disturb", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("content_preview", sa.Text(), nullable=False, server_default=""),
        sa.Column("image_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sender_userids_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("filter_snapshot_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("operator", sa.String(length=128), nullable=False, server_default="fixture-admin"),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="created"),
        sa.Column("status_label", sa.String(length=80), nullable=False, server_default="已创建任务"),
        sa.Column("last_status_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_user_ops_send_records_next_created_at", "user_ops_send_records_next", ["created_at"])
    op.create_index("ix_user_ops_send_records_next_status", "user_ops_send_records_next", ["status"])


def downgrade() -> None:
    op.drop_index("ix_user_ops_send_records_next_status", table_name="user_ops_send_records_next")
    op.drop_index("ix_user_ops_send_records_next_created_at", table_name="user_ops_send_records_next")
    op.drop_table("user_ops_send_records_next")
    op.drop_index("ix_user_ops_dnd_next_active_reason", table_name="user_ops_do_not_disturb_next")
    op.drop_index("ix_user_ops_dnd_next_mobile", table_name="user_ops_do_not_disturb_next")
    op.drop_index("ix_user_ops_dnd_next_external_userid", table_name="user_ops_do_not_disturb_next")
    op.drop_table("user_ops_do_not_disturb_next")
    op.drop_index("ix_user_ops_pool_current_next_activation_bucket", table_name="user_ops_pool_current_next")
    op.drop_index("ix_user_ops_pool_current_next_class_term_no", table_name="user_ops_pool_current_next")
    op.drop_index("ix_user_ops_pool_current_next_owner_userid", table_name="user_ops_pool_current_next")
    op.drop_index("ix_user_ops_pool_current_next_mobile", table_name="user_ops_pool_current_next")
    op.drop_index("ix_user_ops_pool_current_next_external_userid", table_name="user_ops_pool_current_next")
    op.drop_table("user_ops_pool_current_next")
