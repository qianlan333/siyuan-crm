"""complete miniprogram-only resend campaign rows.

Revision ID: 0033_complete_miniprogram_only_resend_20260611
Revises: 0032_miniprogram_only_resend_20260611
"""

from __future__ import annotations

from alembic import op


revision = "0033_complete_miniprogram_only_resend_20260611"
down_revision = "0032_miniprogram_only_resend_20260611"
branch_labels = None
depends_on = None


NEW_GROUP_CODE = "external_second_push_feishu_mini_only_20260611_1625_huangyoucan_v1"


def upgrade() -> None:
    op.execute(
        f"""
        INSERT INTO campaign_segments (campaign_id, segment_id, segment_code, priority, label)
        SELECT
            c.id,
            s.id,
            s.segment_code,
            100,
            COALESCE(NULLIF(c.metadata_json->>'unionid', ''), c.display_name)
        FROM campaigns c
        JOIN segments s
          ON s.segment_code = 'seg_ext_mini_only_' || (c.metadata_json->>'original_campaign_id')
        WHERE c.metadata_json->>'group_code' = '{NEW_GROUP_CODE}'
        ON CONFLICT (campaign_id, segment_id) DO NOTHING
        """
    )
    op.execute(
        f"""
        INSERT INTO campaign_steps (
            campaign_id, campaign_segment_id, step_index, day_offset, send_time, timezone,
            content_text, content_payload_json, stop_on_reply, skip_if_recently_touched_days,
            agent_run_id, updated_at
        )
        SELECT
            c.id,
            cseg.id,
            0,
            0,
            '16:25',
            'Asia/Shanghai',
            '',
            jsonb_build_object(
                'miniprogram_library_ids',
                COALESCE(c.metadata_json->'miniprogram_library_ids', '[]'::jsonb)
            ),
            true,
            0,
            'codex_miniprogram_only_resend_20260611_1625',
            CURRENT_TIMESTAMP
        FROM campaigns c
        JOIN campaign_segments cseg ON cseg.campaign_id = c.id
        WHERE c.metadata_json->>'group_code' = '{NEW_GROUP_CODE}'
        ON CONFLICT (campaign_segment_id, step_index) DO NOTHING
        """
    )
    op.execute(
        f"""
        INSERT INTO campaign_members (
            campaign_id, campaign_segment_id, segment_id, member_id, unionid,
            anchor_date, current_step_index, status, trace_id, updated_at
        )
        SELECT
            c.id,
            cseg.id,
            cseg.segment_id,
            old_cm.member_id,
            old_cm.unionid,
            '2026-06-11',
            -1,
            'pending',
            'mini-only-resend-' || (c.metadata_json->>'original_campaign_id'),
            CURRENT_TIMESTAMP
        FROM campaigns c
        JOIN campaign_segments cseg ON cseg.campaign_id = c.id
        JOIN campaign_members old_cm
          ON old_cm.campaign_id = (c.metadata_json->>'original_campaign_id')::bigint
        WHERE c.metadata_json->>'group_code' = '{NEW_GROUP_CODE}'
        ON CONFLICT (campaign_id, member_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        DELETE FROM campaign_members
        WHERE campaign_id IN (
            SELECT id FROM campaigns WHERE metadata_json->>'group_code' = '{NEW_GROUP_CODE}'
        );
        DELETE FROM campaign_steps
        WHERE campaign_id IN (
            SELECT id FROM campaigns WHERE metadata_json->>'group_code' = '{NEW_GROUP_CODE}'
        );
        DELETE FROM campaign_segments
        WHERE campaign_id IN (
            SELECT id FROM campaigns WHERE metadata_json->>'group_code' = '{NEW_GROUP_CODE}'
        );
        """
    )
