"""create contact_tags local mirror table.

Revision ID: 0080_create_contact_tags_mirror
Revises: 0079_final_target_schema_cleanup
"""

from __future__ import annotations

from alembic import op


revision = "0080_create_contact_tags_mirror"
down_revision = "0079_final_target_schema_cleanup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS contact_tags (
            id BIGSERIAL PRIMARY KEY,
            unionid TEXT NOT NULL DEFAULT '',
            userid TEXT NOT NULL DEFAULT '',
            tag_id TEXT NOT NULL DEFAULT '',
            tag_name TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT '',
            questionnaire_id TEXT NOT NULL DEFAULT '',
            submission_id TEXT NOT NULL DEFAULT '',
            idempotency_key TEXT NOT NULL DEFAULT '',
            raw_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    for column_name, column_type in {
        "unionid": "TEXT NOT NULL DEFAULT ''",
        "userid": "TEXT NOT NULL DEFAULT ''",
        "tag_id": "TEXT NOT NULL DEFAULT ''",
        "tag_name": "TEXT NOT NULL DEFAULT ''",
        "source": "TEXT NOT NULL DEFAULT ''",
        "questionnaire_id": "TEXT NOT NULL DEFAULT ''",
        "submission_id": "TEXT NOT NULL DEFAULT ''",
        "idempotency_key": "TEXT NOT NULL DEFAULT ''",
        "raw_payload_json": "JSONB NOT NULL DEFAULT '{}'::jsonb",
        "created_at": "TIMESTAMPTZ NOT NULL DEFAULT NOW()",
        "updated_at": "TIMESTAMPTZ NOT NULL DEFAULT NOW()",
    }.items():
        op.execute(f"ALTER TABLE contact_tags ADD COLUMN IF NOT EXISTS {column_name} {column_type}")
    op.execute("CREATE INDEX IF NOT EXISTS ix_contact_tags_unionid ON contact_tags (unionid) WHERE unionid <> ''")
    op.execute("CREATE INDEX IF NOT EXISTS ix_contact_tags_userid ON contact_tags (userid) WHERE userid <> ''")
    op.execute("CREATE INDEX IF NOT EXISTS ix_contact_tags_tag_id ON contact_tags (tag_id) WHERE tag_id <> ''")
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_contact_tags_unionid_userid_tag_id
        ON contact_tags (unionid, userid, tag_id)
        WHERE unionid <> '' AND userid <> '' AND tag_id <> ''
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS contact_tags")
