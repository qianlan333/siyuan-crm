"""create miniprogram-only resend campaigns for 2026-06-11 second push.

Revision ID: 0032_miniprogram_only_resend_20260611
Revises: 0031_automation_runtime_v2
"""

from __future__ import annotations

from alembic import op


revision = "0032_miniprogram_only_resend_20260611"
down_revision = "0031_automation_runtime_v2"
branch_labels = None
depends_on = None


OLD_GROUP_CODE = "external_second_push_feishu_postfix_20260611_1451_huangyoucan_v1"
NEW_GROUP_CODE = "external_second_push_feishu_mini_only_20260611_1625_huangyoucan_v1"
NEW_GROUP_LABEL = "本周第二推飞书表小程序补发 · HuangYouCan · 2026-06-11 16:25"


def upgrade() -> None:
    op.execute("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(128)")
    op.execute(
        f"""
        WITH constants AS (
            SELECT
                '{NEW_GROUP_CODE}'::text AS group_code,
                '{NEW_GROUP_LABEL}'::text AS group_label,
                '{OLD_GROUP_CODE}'::text AS old_group_code,
                '2026-06-11'::text AS anchor_date,
                '16:25'::text AS send_time
        ), mini_old AS (
            SELECT
                c.id AS old_campaign_id,
                c.campaign_code AS old_campaign_code,
                c.display_name,
                c.owner_userid,
                cs.content_payload_json,
                cm.id AS old_member_row_id,
                cm.member_id,
                cm.unionid,
                seg.sql_query,
                seg.sql_params_json,
                seg.cached_sample_json
            FROM campaigns c
            JOIN campaign_steps cs ON cs.campaign_id = c.id
            JOIN campaign_members cm ON cm.campaign_id = c.id
            JOIN campaign_segments cseg ON cseg.id = cm.campaign_segment_id
            JOIN segments seg ON seg.id = cm.segment_id
            JOIN constants k ON k.old_group_code = c.metadata_json->>'group_code'
            WHERE jsonb_array_length(COALESCE(cs.content_payload_json->'miniprogram_library_ids', '[]'::jsonb)) > 0
              AND c.owner_userid = 'HuangYouCan'
        ), mark_old_sent AS (
            UPDATE campaign_members cm
            SET status = 'sent',
                current_step_index = GREATEST(cm.current_step_index, 0),
                last_step_sent_at = COALESCE(cm.last_step_sent_at, CURRENT_TIMESTAMP),
                updated_at = CURRENT_TIMESTAMP
            FROM mini_old m
            WHERE cm.id = m.old_member_row_id
              AND cm.status = 'pending'
            RETURNING cm.id
        ), upsert_segments AS (
            INSERT INTO segments (
                segment_code, display_name, description, source_type, sql_query,
                sql_params_json, status, version, created_by_agent, created_by_session,
                cached_headcount, cached_sample_json, last_refreshed_at, tags_json, usage_count
            )
            SELECT
                'seg_ext_mini_only_' || m.old_campaign_id::text,
                '小程序补发 · ' || COALESCE(NULLIF(m.display_name, ''), m.unionid),
                'Attachment-only miniprogram resend copied from ' || m.old_campaign_code,
                'external_campaign',
                m.sql_query,
                m.sql_params_json,
                'active',
                1,
                'codex',
                'campaign_private_attachment_only_20260611_1625',
                1,
                COALESCE(m.cached_sample_json, '[]'::jsonb),
                CURRENT_TIMESTAMP,
                jsonb_build_array('external_campaign', 'HuangYouCan', 'miniprogram_only_resend'),
                0
            FROM mini_old m
            ON CONFLICT (segment_code) DO UPDATE SET
                display_name = EXCLUDED.display_name,
                description = EXCLUDED.description,
                status = 'active',
                cached_headcount = 1,
                cached_sample_json = EXCLUDED.cached_sample_json,
                last_refreshed_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            RETURNING id, segment_code
        ), insert_campaigns AS (
            INSERT INTO campaigns (
                campaign_code, display_name, intent, anchor_mode, anchor_date,
                review_status, run_status, created_by_agent, created_by_session,
                trace_id, owner_userid, metadata_json, stats_json
            )
            SELECT
                'camp_ext_mini_only_' || m.old_campaign_id::text,
                COALESCE(NULLIF(m.display_name, ''), m.unionid),
                '只补发原批次遗漏的小程序卡片，不重复发送文本话术',
                'campaign_start_date',
                k.anchor_date,
                'pending_review',
                'draft',
                'codex',
                'campaign_private_attachment_only_20260611_1625',
                'mini-only-resend-' || m.old_campaign_id::text,
                m.owner_userid,
                jsonb_build_object(
                    'source', 'codex_miniprogram_only_resend',
                    'group_code', k.group_code,
                    'group_label', k.group_label,
                    'unionid', m.unionid,
                    'owner_userid', m.owner_userid,
                    'idempotency_key', k.group_code || ':' || m.unionid,
                    'original_group_code', k.old_group_code,
                    'original_campaign_id', m.old_campaign_id,
                    'original_campaign_code', m.old_campaign_code,
                    'content_mode', 'miniprogram_only',
                    'miniprogram_library_ids', COALESCE(m.content_payload_json->'miniprogram_library_ids', '[]'::jsonb)
                ),
                '{{}}'::jsonb
            FROM mini_old m
            CROSS JOIN constants k
            ON CONFLICT (campaign_code) DO NOTHING
            RETURNING id, campaign_code
        ), new_campaigns AS (
            SELECT c.id, c.campaign_code, m.old_campaign_id, m.unionid, m.member_id, m.content_payload_json
            FROM mini_old m
            JOIN campaigns c ON c.campaign_code = 'camp_ext_mini_only_' || m.old_campaign_id::text
        ), new_segments AS (
            SELECT s.id, s.segment_code, m.old_campaign_id
            FROM mini_old m
            JOIN segments s ON s.segment_code = 'seg_ext_mini_only_' || m.old_campaign_id::text
        ), insert_campaign_segments AS (
            INSERT INTO campaign_segments (campaign_id, segment_id, segment_code, priority, label)
            SELECT nc.id, ns.id, ns.segment_code, 100, nc.unionid
            FROM new_campaigns nc
            JOIN new_segments ns ON ns.old_campaign_id = nc.old_campaign_id
            ON CONFLICT (campaign_id, segment_id) DO NOTHING
            RETURNING id, campaign_id, segment_id
        ), new_campaign_segments AS (
            SELECT cseg.id, cseg.campaign_id, cseg.segment_id, nc.old_campaign_id
            FROM new_campaigns nc
            JOIN new_segments ns ON ns.old_campaign_id = nc.old_campaign_id
            JOIN campaign_segments cseg ON cseg.campaign_id = nc.id AND cseg.segment_id = ns.id
        ), insert_steps AS (
            INSERT INTO campaign_steps (
                campaign_id, campaign_segment_id, step_index, day_offset, send_time, timezone,
                content_text, content_payload_json, stop_on_reply, skip_if_recently_touched_days,
                agent_run_id, updated_at
            )
            SELECT
                nc.id,
                ncs.id,
                0,
                0,
                k.send_time,
                'Asia/Shanghai',
                '',
                jsonb_build_object('miniprogram_library_ids', COALESCE(nc.content_payload_json->'miniprogram_library_ids', '[]'::jsonb)),
                true,
                0,
                'codex_miniprogram_only_resend_20260611_1625',
                CURRENT_TIMESTAMP
            FROM new_campaigns nc
            JOIN new_campaign_segments ncs ON ncs.old_campaign_id = nc.old_campaign_id
            CROSS JOIN constants k
            ON CONFLICT (campaign_segment_id, step_index) DO NOTHING
            RETURNING id
        ), insert_members AS (
            INSERT INTO campaign_members (
                campaign_id, campaign_segment_id, segment_id, member_id, unionid,
                anchor_date, current_step_index, status, trace_id, updated_at
            )
            SELECT
                nc.id,
                ncs.id,
                ncs.segment_id,
                nc.member_id,
                nc.unionid,
                k.anchor_date,
                -1,
                'pending',
                'mini-only-resend-' || nc.old_campaign_id::text,
                CURRENT_TIMESTAMP
            FROM new_campaigns nc
            JOIN new_campaign_segments ncs ON ncs.old_campaign_id = nc.old_campaign_id
            CROSS JOIN constants k
            ON CONFLICT (campaign_id, member_id) DO NOTHING
            RETURNING id
        )
        SELECT 1
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
        DELETE FROM campaigns WHERE metadata_json->>'group_code' = '{NEW_GROUP_CODE}';
        DELETE FROM segments WHERE segment_code LIKE 'seg_ext_mini_only_%';
        """
    )
