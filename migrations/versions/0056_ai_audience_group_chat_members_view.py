"""add AI audience group chat members read view.

Revision ID: 0056_ai_audience_group_chat_members_view
Revises: 0055_automation_agent_webhook_token_and_send_url
"""

from __future__ import annotations

from alembic import op


revision = "0056_ai_audience_group_chat_members_view"
down_revision = "0055_automation_agent_webhook_token_and_send_url"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS audience_read")
    _create_empty_view()
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.group_chats') IS NOT NULL THEN
                CREATE OR REPLACE VIEW audience_read.group_chat_members_v1 AS
                WITH group_rows AS (
                    SELECT
                        g.chat_id::text AS chat_id,
                        COALESCE(g.group_name, '')::text AS group_name,
                        COALESCE(g.owner_userid, '')::text AS owner_userid,
                        COALESCE(g.status, '')::text AS group_status,
                        COALESCE(g.updated_at, CURRENT_TIMESTAMP)::timestamptz AS updated_at,
                        CASE
                            WHEN jsonb_typeof((g.raw_payload::jsonb)->'group_chat') = 'object'
                                THEN (g.raw_payload::jsonb)->'group_chat'
                            ELSE g.raw_payload::jsonb
                        END AS group_payload
                    FROM public.group_chats g
                    WHERE COALESCE(g.chat_id, '') <> ''
                      AND COALESCE(g.raw_payload, '') <> ''
                )
                SELECT
                    gr.chat_id,
                    COALESCE(NULLIF(gr.group_payload->>'name', ''), gr.group_name)::text AS group_name,
                    COALESCE(NULLIF(gr.group_payload->>'owner', ''), gr.owner_userid)::text AS owner_userid,
                    COALESCE(member->>'userid', '')::text AS external_userid,
                    COALESCE(member->>'unionid', '')::text AS unionid,
                    COALESCE(member->>'name', '')::text AS customer_name,
                    COALESCE(member->>'group_nickname', '')::text AS group_nickname,
                    COALESCE(member->'invitor'->>'userid', '')::text AS invitor_userid,
                    CASE
                        WHEN COALESCE(member->>'type', '') ~ '^[0-9]+$'
                            THEN (member->>'type')::integer
                        ELSE 0
                    END AS member_type,
                    CASE
                        WHEN COALESCE(member->>'join_scene', '') ~ '^[0-9]+$'
                            THEN (member->>'join_scene')::integer
                        ELSE 0
                    END AS join_scene,
                    CASE
                        WHEN COALESCE(member->>'join_time', '') ~ '^[0-9]+(\\.[0-9]+)?$'
                            THEN to_timestamp((member->>'join_time')::double precision)
                        ELSE gr.updated_at
                    END AS joined_at,
                    gr.updated_at,
                    jsonb_build_object(
                        'chat_id', gr.chat_id,
                        'group_name', COALESCE(NULLIF(gr.group_payload->>'name', ''), gr.group_name),
                        'owner_userid', COALESCE(NULLIF(gr.group_payload->>'owner', ''), gr.owner_userid),
                        'external_userid', COALESCE(member->>'userid', ''),
                        'unionid', COALESCE(member->>'unionid', ''),
                        'customer_name', COALESCE(member->>'name', ''),
                        'group_nickname', COALESCE(member->>'group_nickname', ''),
                        'invitor_userid', COALESCE(member->'invitor'->>'userid', ''),
                        'join_scene', CASE
                            WHEN COALESCE(member->>'join_scene', '') ~ '^[0-9]+$'
                                THEN (member->>'join_scene')::integer
                            ELSE 0
                        END
                    ) AS payload_json
                FROM group_rows gr
                CROSS JOIN LATERAL jsonb_array_elements(
                    CASE
                        WHEN jsonb_typeof(gr.group_payload->'member_list') = 'array'
                            THEN gr.group_payload->'member_list'
                        ELSE '[]'::jsonb
                    END
                ) AS member
                WHERE gr.group_status = 'active'
                  AND COALESCE(member->>'type', '') = '2'
                  AND COALESCE(member->>'userid', '') <> '';
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS audience_read.group_chat_members_v1")


def _create_empty_view() -> None:
    op.execute(
        """
        CREATE OR REPLACE VIEW audience_read.group_chat_members_v1 AS
        SELECT
            ''::text AS chat_id,
            ''::text AS group_name,
            ''::text AS owner_userid,
            ''::text AS external_userid,
            ''::text AS unionid,
            ''::text AS customer_name,
            ''::text AS group_nickname,
            ''::text AS invitor_userid,
            0::integer AS member_type,
            0::integer AS join_scene,
            NULL::timestamptz AS joined_at,
            NULL::timestamptz AS updated_at,
            '{}'::jsonb AS payload_json
        WHERE FALSE
        """
    )
