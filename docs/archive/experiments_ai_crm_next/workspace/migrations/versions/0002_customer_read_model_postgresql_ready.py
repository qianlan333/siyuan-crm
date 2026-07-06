"""Create PostgreSQL-ready Customer Read Model tables.

Revision ID: 0002_customer_read_model_pg
Revises: 0001_user_ops_pg
Create Date: 2026-05-20
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_customer_read_model_pg"
down_revision = "0001_user_ops_pg"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customer_list_index_next",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("person_id", sa.String(length=80), nullable=True),
        sa.Column("external_userid", sa.String(length=128), nullable=False),
        sa.Column("customer_name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("owner_userid", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("owner_display_name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("remark", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("mobile", sa.String(length=32), nullable=True),
        sa.Column("is_bound", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("binding_status", sa.String(length=80), nullable=False, server_default="unbound"),
        sa.Column("tags_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("class_user_status_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_touch_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_customer_list_index_next_external_userid", "customer_list_index_next", ["external_userid"])
    op.create_index("ix_customer_list_index_next_owner_userid", "customer_list_index_next", ["owner_userid"])
    op.create_index("ix_customer_list_index_next_mobile", "customer_list_index_next", ["mobile"])
    op.create_index("ix_customer_list_index_next_updated_at", "customer_list_index_next", ["updated_at"])

    op.create_table(
        "customer_detail_snapshot_next",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("person_id", sa.String(length=80), nullable=True),
        sa.Column("external_userid", sa.String(length=128), nullable=False),
        sa.Column("customer_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("binding_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("identity_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("follow_users_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("marketing_summary_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("marketing_profile_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("contact_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("sidebar_context_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_customer_detail_snapshot_next_external_userid",
        "customer_detail_snapshot_next",
        ["external_userid"],
    )

    op.create_table(
        "customer_timeline_event_next",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("person_id", sa.String(length=80), nullable=True),
        sa.Column("external_userid", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_table", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("source_id", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_customer_timeline_event_next_external_userid",
        "customer_timeline_event_next",
        ["external_userid"],
    )
    op.create_index("ix_customer_timeline_event_next_event_type", "customer_timeline_event_next", ["event_type"])
    op.create_index("ix_customer_timeline_event_next_event_time", "customer_timeline_event_next", ["event_time"])

    op.create_table(
        "customer_recent_message_next",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("msgid", sa.String(length=128), nullable=False),
        sa.Column("external_userid", sa.String(length=128), nullable=False),
        sa.Column("msgtype", sa.String(length=40), nullable=False, server_default="text"),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("send_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("owner_userid", sa.String(length=128), nullable=True),
        sa.Column("chat_type", sa.String(length=40), nullable=False, server_default="single"),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_customer_recent_message_next_external_userid",
        "customer_recent_message_next",
        ["external_userid"],
    )
    op.create_index("ix_customer_recent_message_next_send_time", "customer_recent_message_next", ["send_time"])


def downgrade() -> None:
    op.drop_index("ix_customer_recent_message_next_send_time", table_name="customer_recent_message_next")
    op.drop_index("ix_customer_recent_message_next_external_userid", table_name="customer_recent_message_next")
    op.drop_table("customer_recent_message_next")
    op.drop_index("ix_customer_timeline_event_next_event_time", table_name="customer_timeline_event_next")
    op.drop_index("ix_customer_timeline_event_next_event_type", table_name="customer_timeline_event_next")
    op.drop_index("ix_customer_timeline_event_next_external_userid", table_name="customer_timeline_event_next")
    op.drop_table("customer_timeline_event_next")
    op.drop_index("ix_customer_detail_snapshot_next_external_userid", table_name="customer_detail_snapshot_next")
    op.drop_table("customer_detail_snapshot_next")
    op.drop_index("ix_customer_list_index_next_updated_at", table_name="customer_list_index_next")
    op.drop_index("ix_customer_list_index_next_mobile", table_name="customer_list_index_next")
    op.drop_index("ix_customer_list_index_next_owner_userid", table_name="customer_list_index_next")
    op.drop_index("ix_customer_list_index_next_external_userid", table_name="customer_list_index_next")
    op.drop_table("customer_list_index_next")
