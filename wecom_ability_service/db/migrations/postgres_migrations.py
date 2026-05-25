from __future__ import annotations

from pathlib import Path

from flask import current_app

from ..helpers import _postgres_table_columns
from . import (
    _ensure_automation_agent_prompt_defaults,
    _ensure_automation_sop_v1_seed_data,
)


_LEGACY_AUTOMATION_MEMBER_FOLLOWUP_DECISION_COLUMN = "questionnaire" "_result"


_HXC_DASHBOARD_V6_COLUMN_DEFS: tuple[tuple[str, str], ...] = (
    ("hxc_member_level", "TEXT NOT NULL DEFAULT ''"),
    ("hxc_member_expires_at", "TIMESTAMPTZ"),
    ("hxc_onboard_status", "TEXT NOT NULL DEFAULT ''"),
    ("hxc_assessment_status", "TEXT NOT NULL DEFAULT ''"),
    ("hxc_growth_onboard_status", "TEXT NOT NULL DEFAULT ''"),
    ("hxc_first_login_at", "TIMESTAMPTZ"),
    ("identity_stage", "TEXT NOT NULL DEFAULT ''"),
    ("monthly_income_range", "TEXT NOT NULL DEFAULT ''"),
    ("business_focus", "TEXT NOT NULL DEFAULT ''"),
    ("ai_usage_status", "TEXT NOT NULL DEFAULT ''"),
    ("main_pain_points", "TEXT NOT NULL DEFAULT ''"),
    ("ai_pain_points", "TEXT NOT NULL DEFAULT ''"),
    ("core_painful_scenario", "TEXT NOT NULL DEFAULT ''"),
    ("focus_topics", "TEXT NOT NULL DEFAULT ''"),
    ("persona_sketch", "TEXT NOT NULL DEFAULT ''"),
    ("interaction_style", "TEXT NOT NULL DEFAULT ''"),
    ("communication_style", "TEXT NOT NULL DEFAULT ''"),
    ("background_confidence", "TEXT NOT NULL DEFAULT ''"),
    ("main_line_type", "TEXT NOT NULL DEFAULT ''"),
    ("main_line_stage", "TEXT NOT NULL DEFAULT ''"),
    ("main_line_tier", "TEXT NOT NULL DEFAULT ''"),
    ("main_line_confirmed_at", "TIMESTAMPTZ"),
    ("main_line_desc", "TEXT NOT NULL DEFAULT ''"),
    ("main_line_issue", "TEXT NOT NULL DEFAULT ''"),
    ("assessment_count", "INTEGER NOT NULL DEFAULT 0"),
    ("latest_assessment_status", "TEXT NOT NULL DEFAULT ''"),
    ("latest_assessment_score", "INTEGER"),
    ("latest_assessment_phase", "TEXT NOT NULL DEFAULT ''"),
    ("latest_assessment_sub_type", "TEXT NOT NULL DEFAULT ''"),
    ("latest_assessment_completed_at", "TIMESTAMPTZ"),
    ("assessment_dimension_scores", "TEXT NOT NULL DEFAULT ''"),
    ("subscription_tier", "TEXT NOT NULL DEFAULT ''"),
    ("subscription_expires_at", "TIMESTAMPTZ"),
    ("subscription_quota", "INTEGER"),
    ("subscription_used", "INTEGER"),
    ("subscription_period_start", "DATE"),
    ("last_activation_sku_code", "TEXT NOT NULL DEFAULT ''"),
    ("last_activation_new_tier", "TEXT NOT NULL DEFAULT ''"),
    ("last_activation_source", "TEXT NOT NULL DEFAULT ''"),
    ("last_activation_at", "TIMESTAMPTZ"),
    ("active_goals_count", "INTEGER NOT NULL DEFAULT 0"),
    ("active_paths_count", "INTEGER NOT NULL DEFAULT 0"),
    ("current_milestone_max", "INTEGER"),
    ("active_tasks_count", "INTEGER NOT NULL DEFAULT 0"),
    ("completed_tasks_count", "INTEGER NOT NULL DEFAULT 0"),
    ("task_checkin_count", "INTEGER NOT NULL DEFAULT 0"),
    ("last_task_checkin_at", "TIMESTAMPTZ"),
    ("last_task_checkin_mood", "TEXT NOT NULL DEFAULT ''"),
    ("last_task_checkin_state_score", "INTEGER"),
    ("next_review_at", "TIMESTAMPTZ"),
    ("last_reviewed_at", "TIMESTAMPTZ"),
    ("review_schedule_status", "TEXT NOT NULL DEFAULT ''"),
    ("last_recent_event_at", "TIMESTAMPTZ"),
    ("last_recent_event_type", "TEXT NOT NULL DEFAULT ''"),
    ("recommended_topic_status", "TEXT NOT NULL DEFAULT ''"),
    ("recommended_topic_generated_at", "TIMESTAMPTZ"),
    ("topic_summary_count", "INTEGER NOT NULL DEFAULT 0"),
    ("last_topic_summary_at", "TIMESTAMPTZ"),
    ("last_topic_summary_title", "TEXT NOT NULL DEFAULT ''"),
    ("primary_role", "TEXT NOT NULL DEFAULT ''"),
    ("biz_score", "INTEGER"),
    ("inner_score", "INTEGER"),
    ("trust_score", "INTEGER"),
    ("trust_tier", "TEXT NOT NULL DEFAULT ''"),
    ("clarity_score", "INTEGER"),
    ("role_mode", "TEXT NOT NULL DEFAULT ''"),
    ("growth_credit_balance", "INTEGER"),
    ("growth_credit_period_granted", "INTEGER"),
    ("growth_credit_period_used", "INTEGER"),
    ("growth_credit_period_ends_at", "TIMESTAMPTZ"),
    ("webhook_questionnaire_count", "INTEGER NOT NULL DEFAULT 0"),
    ("last_webhook_questionnaire_at", "TIMESTAMPTZ"),
    ("last_webhook_questionnaire_status", "TEXT NOT NULL DEFAULT ''"),
    ("crm_chat_job_count", "INTEGER NOT NULL DEFAULT 0"),
    ("crm_chat_done_count", "INTEGER NOT NULL DEFAULT 0"),
    ("crm_chat_failed_count", "INTEGER NOT NULL DEFAULT 0"),
    ("last_crm_chat_job_status", "TEXT NOT NULL DEFAULT ''"),
    ("last_crm_chat_job_at", "TIMESTAMPTZ"),
    ("last_crm_chat_callback_status", "TEXT NOT NULL DEFAULT ''"),
)


def _run_schema_with_forward_fk_retries(db, script: str, *, max_passes: int = 4) -> None:
    """跑 schema_postgres.sql，对前向 FK 引用容错。

    schema 里有少数 ``CREATE TABLE`` 的 FK 引用了下方才定义的表（例如
    ``customer_value_segment_current.submission_id REFERENCES questionnaire_submissions``
    出现在 line 759，但 ``questionnaire_submissions`` 直到 line 1414 才建）。

    单次顺跑 ``executescript`` 会在第一条前向 FK 上 ``UndefinedTable`` 死掉，让
    fresh PG 上的 ``init_db`` 整个崩。多 pass 重试容错：每轮跑通能跑通的，把
    ``UndefinedTable`` 失败的留到下一轮 —— 等被引用表建好后再补。
    """
    statements = [s.strip() for s in script.split(";") if s.strip()]
    pending = statements
    for _ in range(max_passes):
        if not pending:
            return
        next_pending: list[str] = []
        for stmt in pending:
            try:
                db.execute(stmt)
                db.commit()
            except Exception:
                db.rollback()
                next_pending.append(stmt)
        if len(next_pending) == len(pending):
            # 没进展：剩下的就是真坏掉的，让最后一条原样抛出来便于 debug。
            for stmt in next_pending:
                db.execute(stmt)
            return
        pending = next_pending
    for stmt in pending:
        db.execute(stmt)


def _ensure_postgres_user_ops_page_tables(db) -> None:
    db.execute(
        """
        ALTER TABLE IF EXISTS user_ops_send_records
        ADD COLUMN IF NOT EXISTS image_count INTEGER NOT NULL DEFAULT 0
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_message_activity_sync_item
        ADD COLUMN IF NOT EXISTS phone_prefix3 TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_message_activity_sync_item
        ADD COLUMN IF NOT EXISTS phone_match_key TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_message_activity_sync_item_match_key
        ON automation_message_activity_sync_item (phone_match_key, created_at DESC, id DESC)
        """
    )


def _ensure_postgres_hxc_dashboard_v6_columns(db) -> None:
    for name, column_type in _HXC_DASHBOARD_V6_COLUMN_DEFS:
        db.execute(
            f"ALTER TABLE IF EXISTS user_ops_hxc_dashboard_snapshot "
            f"ADD COLUMN IF NOT EXISTS {name} {column_type}"
        )


def _ensure_postgres_miniprogram_library_thumb_image_id(db) -> None:
    db.execute(
        """
        ALTER TABLE IF EXISTS miniprogram_library
        ADD COLUMN IF NOT EXISTS thumb_image_id BIGINT
        """
    )


def _ensure_postgres_attachment_library(db) -> None:
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_channel
        ADD COLUMN IF NOT EXISTS welcome_image_library_ids JSONB NOT NULL DEFAULT '[]'::jsonb
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_channel
        ADD COLUMN IF NOT EXISTS welcome_attachment_library_ids JSONB NOT NULL DEFAULT '[]'::jsonb
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_channel
        ADD COLUMN IF NOT EXISTS welcome_miniprogram_library_ids JSONB NOT NULL DEFAULT '[]'::jsonb
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS attachment_library (
            id BIGSERIAL PRIMARY KEY,
            name TEXT NOT NULL DEFAULT '',
            file_name TEXT NOT NULL DEFAULT '',
            mime_type TEXT NOT NULL DEFAULT 'application/pdf',
            file_size INTEGER NOT NULL DEFAULT 0,
            data_base64 TEXT NOT NULL DEFAULT '',
            media_id TEXT NOT NULL DEFAULT '',
            media_id_expires_at TIMESTAMPTZ,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            description TEXT NOT NULL DEFAULT '',
            tags JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_attachment_library_enabled
        ON attachment_library (enabled, updated_at DESC, id DESC)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_attachment_library_tags_gin
        ON attachment_library USING GIN (tags)
        """
    )


def _ensure_postgres_automation_agent_config_tables(db) -> None:
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_agent_config
        ADD COLUMN IF NOT EXISTS submitted_for_publish BOOLEAN NOT NULL DEFAULT FALSE
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_agent_config
        ADD COLUMN IF NOT EXISTS submitted_at TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_agent_config
        ADD COLUMN IF NOT EXISTS submitted_by TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_profile_segment_template
        ADD COLUMN IF NOT EXISTS program_id BIGINT
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_profile_segment_template
        ADD COLUMN IF NOT EXISTS segmentation_question_id BIGINT REFERENCES questionnaire_questions(id) ON DELETE SET NULL
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_profile_segment_template_program
        ON automation_profile_segment_template (program_id, enabled, updated_at DESC, id DESC)
        """
    )


def _ensure_postgres_automation_operation_templates(db) -> None:
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_operation_templates (
            id BIGSERIAL PRIMARY KEY,
            template_code TEXT NOT NULL UNIQUE,
            template_name TEXT NOT NULL DEFAULT '',
            template_source TEXT NOT NULL DEFAULT 'crm_local',
            category TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active',
            default_config_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            ui_schema_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            workflow_blueprint_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            node_blueprints_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_by TEXT NOT NULL DEFAULT '',
            updated_by TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            archived_at TIMESTAMPTZ
        )
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_operation_templates
        DROP CONSTRAINT IF EXISTS automation_operation_templates_template_source_check
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_operation_templates
        ADD CONSTRAINT automation_operation_templates_template_source_check
        CHECK (template_source IN ('builtin', 'crm_local', 'ai_generated'))
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_operation_templates
        DROP CONSTRAINT IF EXISTS automation_operation_templates_status_check
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_operation_templates
        ADD CONSTRAINT automation_operation_templates_status_check
        CHECK (status IN ('active', 'archived'))
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_operation_templates_source
        ON automation_operation_templates (template_source, status, updated_at DESC, id DESC)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_operation_templates_category
        ON automation_operation_templates (category, status, updated_at DESC, id DESC)
        """
    )


def _ensure_pending_questionnaire_followup_cadence(db) -> None:
    db.execute(
        """
        UPDATE automation_workflow_node AS node
        SET day_offset = CASE node.node_code
            WHEN '催问卷_1' THEN 1
            WHEN '催问卷_2' THEN 2
            WHEN '催问卷_3' THEN 3
            ELSE node.day_offset
        END,
            updated_at = CURRENT_TIMESTAMP
        FROM automation_workflow AS workflow
        WHERE workflow.id = node.workflow_id
          AND workflow.workflow_code = '3_次推填问卷'
          AND node.node_code IN ('催问卷_1', '催问卷_2', '催问卷_3')
          AND node.target_audience_code = 'pending_questionnaire'
          AND node.trigger_mode = 'scheduled'
          AND node.send_time = '09:00'
          AND node.day_offset <> CASE node.node_code
              WHEN '催问卷_1' THEN 1
              WHEN '催问卷_2' THEN 2
              WHEN '催问卷_3' THEN 3
              ELSE node.day_offset
          END
          AND EXISTS (
              SELECT 1
              FROM automation_workflow_node AS legacy_node
              WHERE legacy_node.workflow_id = workflow.id
                AND legacy_node.node_code = '催问卷_1'
                AND legacy_node.day_offset = 2
          )
          AND EXISTS (
              SELECT 1
              FROM automation_workflow_node AS legacy_node
              WHERE legacy_node.workflow_id = workflow.id
                AND legacy_node.node_code = '催问卷_2'
                AND legacy_node.day_offset = 3
          )
          AND EXISTS (
              SELECT 1
              FROM automation_workflow_node AS legacy_node
              WHERE legacy_node.workflow_id = workflow.id
                AND legacy_node.node_code = '催问卷_3'
                AND legacy_node.day_offset = 4
          )
        """
    )


def _migrate_postgres_conversion_agent_pools_to_bindings(db) -> None:
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_workflow_execution_item
        ADD COLUMN IF NOT EXISTS agent_code TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = current_schema()
                  AND table_name = 'automation_workflow_agent_pool_binding'
            ) AND EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = current_schema()
                  AND table_name = 'automation_agent_pool_agent'
            ) THEN
                DELETE FROM automation_workflow_agent_binding
                WHERE workflow_id IN (SELECT workflow_id FROM automation_workflow_agent_pool_binding);

                INSERT INTO automation_workflow_agent_binding (
                    workflow_id,
                    node_id,
                    binding_scope,
                    segment_key,
                    agent_code,
                    created_at,
                    updated_at
                )
                SELECT
                    binding.workflow_id,
                    NULL,
                    binding.binding_scope,
                    COALESCE(binding.segment_key, ''),
                    selected.agent_code,
                    COALESCE(binding.created_at, CURRENT_TIMESTAMP),
                    COALESCE(binding.updated_at, CURRENT_TIMESTAMP)
                FROM automation_workflow_agent_pool_binding binding
                JOIN LATERAL (
                    SELECT member.agent_code
                    FROM automation_agent_pool_agent member
                    WHERE member.agent_pool_id = binding.agent_pool_id
                    ORDER BY CASE WHEN lower(COALESCE(member.role_code, '')) = 'primary' THEN 0 ELSE 1 END,
                             member.position_index ASC,
                             member.id ASC
                    LIMIT 1
                ) AS selected ON TRUE;

                UPDATE automation_workflow_execution_item item
                SET agent_code = COALESCE((
                    SELECT member.agent_code
                    FROM automation_agent_pool_agent member
                    WHERE member.agent_pool_id = item.agent_pool_id
                    ORDER BY CASE WHEN lower(COALESCE(member.role_code, '')) = 'primary' THEN 0 ELSE 1 END,
                             member.position_index ASC,
                             member.id ASC
                    LIMIT 1
                ), '')
                WHERE COALESCE(item.agent_code, '') = ''
                  AND item.agent_pool_id IS NOT NULL;
            END IF;
        END $$;
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_workflow_execution_item
        DROP COLUMN IF EXISTS agent_pool_id
        """
    )
    db.execute("DROP TABLE IF EXISTS automation_workflow_agent_pool_binding")
    db.execute("DROP TABLE IF EXISTS automation_agent_pool_agent")
    db.execute("DROP TABLE IF EXISTS automation_agent_pool")


def _ensure_postgres_questionnaire_external_push_tables(db) -> None:
    db.execute(
        """
        ALTER TABLE IF EXISTS questionnaires
        ADD COLUMN IF NOT EXISTS external_push_enabled BOOLEAN NOT NULL DEFAULT FALSE
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS questionnaires
        ADD COLUMN IF NOT EXISTS external_push_url TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS questionnaires
        ADD COLUMN IF NOT EXISTS external_push_day INTEGER
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS questionnaires
        ADD COLUMN IF NOT EXISTS external_push_frequency INTEGER
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS questionnaires
        ADD COLUMN IF NOT EXISTS external_push_remark TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS questionnaires
        ADD COLUMN IF NOT EXISTS external_push_custom_params JSONB NOT NULL DEFAULT '[]'::jsonb
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_questionnaires_external_push_enabled
        ON questionnaires (external_push_enabled)
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS questionnaire_external_push_logs (
            id BIGSERIAL PRIMARY KEY,
            questionnaire_id BIGINT NOT NULL REFERENCES questionnaires(id) ON DELETE CASCADE,
            questionnaire_title_snapshot TEXT NOT NULL DEFAULT '',
            submission_record_id BIGINT NOT NULL REFERENCES questionnaire_submissions(id) ON DELETE CASCADE,
            retry_from_log_id BIGINT REFERENCES questionnaire_external_push_logs(id) ON DELETE SET NULL,
            retry_attempt INTEGER NOT NULL DEFAULT 0,
            user_id TEXT NOT NULL DEFAULT '',
            target_url TEXT NOT NULL DEFAULT '',
            request_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            response_status_code INTEGER,
            response_body TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'failed',
            failure_reason TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_questionnaire_external_push_logs_questionnaire
        ON questionnaire_external_push_logs (questionnaire_id, created_at DESC, id DESC)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_questionnaire_external_push_logs_status
        ON questionnaire_external_push_logs (status, created_at DESC, id DESC)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_questionnaire_external_push_logs_submission
        ON questionnaire_external_push_logs (submission_record_id)
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS questionnaire_external_push_logs
        ADD COLUMN IF NOT EXISTS retry_from_log_id BIGINT REFERENCES questionnaire_external_push_logs(id) ON DELETE SET NULL
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS questionnaire_external_push_logs
        ADD COLUMN IF NOT EXISTS retry_attempt INTEGER NOT NULL DEFAULT 0
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_questionnaire_external_push_logs_retry_from
        ON questionnaire_external_push_logs (retry_from_log_id, created_at DESC, id DESC)
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS user_ops_send_records
        ADD COLUMN IF NOT EXISTS task_results_json JSONB NOT NULL DEFAULT '[]'::jsonb
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS user_ops_send_records
        ADD COLUMN IF NOT EXISTS last_status_sync_at TIMESTAMPTZ
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_user_ops_send_records_created
        ON user_ops_send_records (created_at DESC, id DESC)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_user_ops_do_not_disturb_external_active
        ON user_ops_do_not_disturb (external_userid, is_active, updated_at DESC)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_user_ops_do_not_disturb_mobile_active
        ON user_ops_do_not_disturb (mobile, is_active, updated_at DESC)
        """
    )


def _ensure_postgres_questionnaire_scrm_apply_log_columns(db) -> None:
    for stmt in (
        "ALTER TABLE IF EXISTS questionnaire_scrm_apply_logs "
        "ADD COLUMN IF NOT EXISTS questionnaire_id BIGINT NOT NULL DEFAULT 0",
        "ALTER TABLE IF EXISTS questionnaire_scrm_apply_logs "
        "ADD COLUMN IF NOT EXISTS openid TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE IF EXISTS questionnaire_scrm_apply_logs "
        "ADD COLUMN IF NOT EXISTS unionid TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE IF EXISTS questionnaire_scrm_apply_logs "
        "ADD COLUMN IF NOT EXISTS matched_score_tier_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE IF EXISTS questionnaire_scrm_apply_logs "
        "ADD COLUMN IF NOT EXISTS matched_score_tier_name TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE IF EXISTS questionnaire_scrm_apply_logs "
        "ADD COLUMN IF NOT EXISTS matched_dimension_categories JSONB NOT NULL DEFAULT '[]'::jsonb",
        "ALTER TABLE IF EXISTS questionnaire_scrm_apply_logs "
        "ADD COLUMN IF NOT EXISTS add_tag_ids JSONB NOT NULL DEFAULT '[]'::jsonb",
        "ALTER TABLE IF EXISTS questionnaire_scrm_apply_logs "
        "ADD COLUMN IF NOT EXISTS wecom_response JSONB NOT NULL DEFAULT '{}'::jsonb",
    ):
        db.execute(stmt)


def _ensure_postgres_wechat_pay_tables(db) -> None:
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS wechat_pay_products (
            id BIGSERIAL PRIMARY KEY,
            product_code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL DEFAULT '',
            amount_total INTEGER NOT NULL DEFAULT 0,
            currency TEXT NOT NULL DEFAULT 'CNY',
            status TEXT NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft', 'active', 'disabled')),
            enabled BOOLEAN NOT NULL DEFAULT FALSE,
            cta_text TEXT NOT NULL DEFAULT '立即报名',
            require_mobile BOOLEAN NOT NULL DEFAULT FALSE,
            lead_program_id BIGINT,
            lead_channel_id BIGINT,
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    for stmt in (
        "ALTER TABLE IF EXISTS wechat_pay_products ADD COLUMN IF NOT EXISTS cta_text TEXT NOT NULL DEFAULT '立即报名'",
        "ALTER TABLE IF EXISTS wechat_pay_products ADD COLUMN IF NOT EXISTS require_mobile BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE IF EXISTS wechat_pay_products ADD COLUMN IF NOT EXISTS lead_program_id BIGINT",
        "ALTER TABLE IF EXISTS wechat_pay_products ADD COLUMN IF NOT EXISTS lead_channel_id BIGINT",
        "ALTER TABLE IF EXISTS wechat_pay_products ADD COLUMN IF NOT EXISTS metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb",
    ):
        db.execute(stmt)
    db.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_wechat_pay_products_code
        ON wechat_pay_products (product_code)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_wechat_pay_products_status_updated
        ON wechat_pay_products (status, updated_at DESC, id DESC)
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS wechat_pay_product_page_slices (
            id BIGSERIAL PRIMARY KEY,
            product_id BIGINT NOT NULL REFERENCES wechat_pay_products(id) ON DELETE CASCADE,
            image_library_id BIGINT NOT NULL REFERENCES image_library(id) ON DELETE RESTRICT,
            sort_order INTEGER NOT NULL DEFAULT 0,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_wechat_pay_product_slices_product_order
        ON wechat_pay_product_page_slices (product_id, sort_order ASC, id ASC)
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS wechat_pay_orders (
            id BIGSERIAL PRIMARY KEY,
            out_trade_no TEXT NOT NULL UNIQUE,
            order_source TEXT NOT NULL DEFAULT 'h5_checkout',
            client_order_ref TEXT NOT NULL DEFAULT '',
            product_code TEXT NOT NULL,
            product_name TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            amount_total INTEGER NOT NULL,
            currency TEXT NOT NULL DEFAULT 'CNY',
            payer_openid TEXT NOT NULL DEFAULT '',
            respondent_key TEXT NOT NULL DEFAULT '',
            unionid TEXT NOT NULL DEFAULT '',
            external_userid TEXT NOT NULL DEFAULT '',
            userid_snapshot TEXT NOT NULL DEFAULT '',
            mobile_snapshot TEXT NOT NULL DEFAULT '',
            payer_name_snapshot TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'created',
            trade_state TEXT NOT NULL DEFAULT '',
            transaction_id TEXT NOT NULL DEFAULT '',
            prepay_id TEXT NOT NULL DEFAULT '',
            bank_type TEXT NOT NULL DEFAULT '',
            payer_total INTEGER NOT NULL DEFAULT 0,
            success_url TEXT NOT NULL DEFAULT '',
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            request_meta_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            request_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            response_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            notify_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            refunded_amount_total INTEGER NOT NULL DEFAULT 0,
            refund_status TEXT NOT NULL DEFAULT '',
            last_error TEXT NOT NULL DEFAULT '',
            expires_at TIMESTAMPTZ,
            paid_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    for stmt in (
        "ALTER TABLE IF EXISTS wechat_pay_orders ADD COLUMN IF NOT EXISTS userid_snapshot TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE IF EXISTS wechat_pay_orders ADD COLUMN IF NOT EXISTS mobile_snapshot TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE IF EXISTS wechat_pay_orders ADD COLUMN IF NOT EXISTS payer_name_snapshot TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE IF EXISTS wechat_pay_orders ADD COLUMN IF NOT EXISTS refunded_amount_total INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE IF EXISTS wechat_pay_orders ADD COLUMN IF NOT EXISTS refund_status TEXT NOT NULL DEFAULT ''",
        "UPDATE wechat_pay_orders SET product_name = product_code WHERE COALESCE(product_name, '') = ''",
    ):
        db.execute(stmt)
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_wechat_pay_orders_status_created
        ON wechat_pay_orders (status, created_at DESC, id DESC)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_wechat_pay_orders_payer
        ON wechat_pay_orders (payer_openid, created_at DESC)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_wechat_pay_orders_product
        ON wechat_pay_orders (product_code, created_at DESC, id DESC)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_wechat_pay_orders_created
        ON wechat_pay_orders (created_at DESC, id DESC)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_wechat_pay_orders_product_created
        ON wechat_pay_orders (product_code, created_at DESC, id DESC)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_wechat_pay_orders_external_created
        ON wechat_pay_orders (external_userid, created_at DESC, id DESC)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_wechat_pay_orders_mobile_created
        ON wechat_pay_orders (mobile_snapshot, created_at DESC, id DESC)
        WHERE mobile_snapshot <> ''
        """
    )
    db.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_wechat_pay_orders_transaction_id
        ON wechat_pay_orders (transaction_id)
        WHERE transaction_id <> ''
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS wechat_pay_order_events (
            id BIGSERIAL PRIMARY KEY,
            out_trade_no TEXT NOT NULL REFERENCES wechat_pay_orders(out_trade_no) ON DELETE CASCADE,
            event_type TEXT NOT NULL,
            transaction_id TEXT NOT NULL DEFAULT '',
            trade_state TEXT NOT NULL DEFAULT '',
            payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            headers_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_wechat_pay_order_events_order
        ON wechat_pay_order_events (out_trade_no, created_at DESC)
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS wechat_pay_refunds (
            id BIGSERIAL PRIMARY KEY,
            order_id BIGINT NOT NULL REFERENCES wechat_pay_orders(id) ON DELETE CASCADE,
            out_trade_no TEXT NOT NULL DEFAULT '',
            transaction_id TEXT NOT NULL DEFAULT '',
            out_refund_no TEXT UNIQUE NOT NULL,
            refund_id TEXT NOT NULL DEFAULT '',
            reason TEXT NOT NULL DEFAULT '',
            refund_amount_total INTEGER NOT NULL DEFAULT 0,
            order_amount_total INTEGER NOT NULL DEFAULT 0,
            currency TEXT NOT NULL DEFAULT 'CNY',
            status TEXT NOT NULL DEFAULT 'requested',
            requested_by TEXT NOT NULL DEFAULT '',
            request_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            response_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            error_message TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_wechat_pay_refunds_order
        ON wechat_pay_refunds (order_id, created_at DESC, id DESC)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_wechat_pay_refunds_status
        ON wechat_pay_refunds (status, created_at DESC, id DESC)
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS wechat_pay_order_export_jobs (
            id BIGSERIAL PRIMARY KEY,
            job_id TEXT UNIQUE NOT NULL,
            requested_by TEXT NOT NULL DEFAULT '',
            filters_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            scope TEXT NOT NULL DEFAULT 'filtered',
            file_format TEXT NOT NULL DEFAULT 'xlsx',
            status TEXT NOT NULL DEFAULT 'queued',
            exported_count INTEGER NOT NULL DEFAULT 0,
            file_name TEXT NOT NULL DEFAULT '',
            file_path TEXT NOT NULL DEFAULT '',
            error_message TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            finished_at TEXT NOT NULL DEFAULT ''
        )
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_wechat_pay_order_export_jobs_status
        ON wechat_pay_order_export_jobs (status, created_at DESC, id DESC)
        """
    )


def _ensure_postgres_customer_value_segment_tables(db) -> None:
    db.execute(
        """
        ALTER TABLE IF EXISTS customer_value_segment_current
        ADD COLUMN IF NOT EXISTS submission_id BIGINT REFERENCES questionnaire_submissions(id) ON DELETE SET NULL
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS customer_value_segment_current
        ADD COLUMN IF NOT EXISTS matched_question_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS customer_value_segment_current
        ADD COLUMN IF NOT EXISTS evaluated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS customer_value_segment_history
        ADD COLUMN IF NOT EXISTS submission_id BIGINT REFERENCES questionnaire_submissions(id) ON DELETE SET NULL
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS customer_value_segment_history
        ADD COLUMN IF NOT EXISTS matched_question_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS customer_value_segment_history
        ADD COLUMN IF NOT EXISTS evaluated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        """
    )


def _ensure_postgres_customer_marketing_state_tables(db) -> None:
    db.execute(
        """
        ALTER TABLE IF EXISTS customer_marketing_state_current
        ALTER COLUMN external_userid SET DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS customer_marketing_state_history
        ALTER COLUMN external_userid SET DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS customer_marketing_state_current
        DROP CONSTRAINT IF EXISTS customer_marketing_state_current_external_userid_key
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS customer_marketing_state_current
        ADD COLUMN IF NOT EXISTS person_id BIGINT REFERENCES people(id) ON DELETE SET NULL
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS customer_marketing_state_current
        ADD COLUMN IF NOT EXISTS activated BOOLEAN NOT NULL DEFAULT FALSE
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS customer_marketing_state_current
        ADD COLUMN IF NOT EXISTS converted BOOLEAN NOT NULL DEFAULT FALSE
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS customer_marketing_state_current
        ADD COLUMN IF NOT EXISTS last_activation_at TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS customer_marketing_state_current
        ADD COLUMN IF NOT EXISTS last_conversion_marked_at TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS customer_marketing_state_current
        ADD COLUMN IF NOT EXISTS last_message_at TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_customer_marketing_state_current_person_id_non_null
        ON customer_marketing_state_current (person_id)
        WHERE person_id IS NOT NULL
        """
    )


def _ensure_postgres_admin_auth_tables(db) -> None:
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_users (
            id BIGSERIAL PRIMARY KEY,
            wecom_userid TEXT NOT NULL DEFAULT '',
            wecom_corpid TEXT NOT NULL DEFAULT '',
            display_name TEXT NOT NULL DEFAULT '',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            login_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            admin_level TEXT NOT NULL DEFAULT 'admin',
            auth_source TEXT NOT NULL DEFAULT 'wecom_sso',
            last_login_at TIMESTAMPTZ,
            created_by TEXT NOT NULL DEFAULT '',
            updated_by TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS admin_users
        ADD COLUMN IF NOT EXISTS wecom_userid TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS admin_users
        ADD COLUMN IF NOT EXISTS wecom_corpid TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS admin_users
        ADD COLUMN IF NOT EXISTS auth_source TEXT NOT NULL DEFAULT 'wecom_sso'
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS admin_users
        ADD COLUMN IF NOT EXISTS login_enabled BOOLEAN NOT NULL DEFAULT TRUE
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS admin_users
        ADD COLUMN IF NOT EXISTS admin_level TEXT NOT NULL DEFAULT 'admin'
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS admin_users
        ADD COLUMN IF NOT EXISTS created_by TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS admin_users
        ADD COLUMN IF NOT EXISTS updated_by TEXT NOT NULL DEFAULT ''
        """
    )
    admin_user_columns = _postgres_table_columns(db, "admin_users")
    if "username" in admin_user_columns:
        db.execute(
            """
            UPDATE admin_users
            SET wecom_userid = COALESCE(NULLIF(wecom_userid, ''), username)
            WHERE COALESCE(NULLIF(wecom_userid, ''), '') = ''
            """
        )
    db.execute(
        """
        UPDATE admin_users
        SET wecom_corpid = COALESCE(NULLIF(wecom_corpid, ''), ?)
        WHERE COALESCE(NULLIF(wecom_corpid, ''), '') = ''
        """,
        (str(current_app.config.get("WECOM_CORP_ID", "") or ""),),
    )
    if "password_hash" in admin_user_columns:
        db.execute(
            """
            UPDATE admin_users
            SET auth_source = 'legacy_migrated'
            WHERE COALESCE(NULLIF(password_hash, ''), '') <> ''
            """
        )
    db.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_admin_users_wecom_identity
        ON admin_users (wecom_corpid, wecom_userid)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_admin_users_active_identity
        ON admin_users (is_active, display_name, wecom_userid)
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_wecom_directory_members (
            id BIGSERIAL PRIMARY KEY,
            wecom_corpid TEXT NOT NULL DEFAULT '',
            wecom_userid TEXT NOT NULL DEFAULT '',
            display_name TEXT NOT NULL DEFAULT '',
            department_ids_json TEXT NOT NULL DEFAULT '[]',
            position TEXT NOT NULL DEFAULT '',
            wecom_status INTEGER,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            synced_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            raw_payload_json TEXT NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_admin_wecom_directory_identity
        ON admin_wecom_directory_members (wecom_corpid, wecom_userid)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_admin_wecom_directory_lookup
        ON admin_wecom_directory_members (is_active, display_name, wecom_userid)
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_user_roles (
            id BIGSERIAL PRIMARY KEY,
            admin_user_id BIGINT NOT NULL REFERENCES admin_users(id) ON DELETE CASCADE,
            role_code TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_admin_user_roles_binding
        ON admin_user_roles (admin_user_id, role_code)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_admin_user_roles_role_code
        ON admin_user_roles (role_code, admin_user_id)
        """
    )
    if "role_code" in admin_user_columns:
        db.execute(
            """
            INSERT INTO admin_user_roles (admin_user_id, role_code, created_at)
            SELECT id, role_code, CURRENT_TIMESTAMP
            FROM admin_users
            WHERE COALESCE(role_code, '') <> ''
            ON CONFLICT (admin_user_id, role_code) DO NOTHING
            """
        )
    db.execute(
        """
        UPDATE admin_users
        SET admin_level = 'super_admin'
        WHERE id IN (
            SELECT admin_user_id
            FROM admin_user_roles
            WHERE role_code = 'super_admin'
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_login_audit (
            id BIGSERIAL PRIMARY KEY,
            admin_user_id BIGINT REFERENCES admin_users(id) ON DELETE SET NULL,
            login_type TEXT NOT NULL DEFAULT '',
            login_result TEXT NOT NULL DEFAULT '',
            ip TEXT NOT NULL DEFAULT '',
            user_agent TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_admin_login_audit_created
        ON admin_login_audit (created_at DESC, id DESC)
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_sso_states (
            state_token TEXT PRIMARY KEY,
            login_kind TEXT NOT NULL DEFAULT 'wecom_qr',
            next_path TEXT NOT NULL DEFAULT '/admin/automation-conversion',
            expires_at TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_admin_sso_states_expires
        ON admin_sso_states (expires_at)
        """
    )
    db.execute(
        """
        UPDATE customer_marketing_state_current
        SET external_userid = ''
        WHERE substr(COALESCE(external_userid, ''), 1, 7) = 'person:'
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS customer_marketing_state_history
        ADD COLUMN IF NOT EXISTS person_id BIGINT REFERENCES people(id) ON DELETE SET NULL
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS customer_marketing_state_history
        ADD COLUMN IF NOT EXISTS activated BOOLEAN NOT NULL DEFAULT FALSE
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS customer_marketing_state_history
        ADD COLUMN IF NOT EXISTS converted BOOLEAN NOT NULL DEFAULT FALSE
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS customer_marketing_state_history
        ADD COLUMN IF NOT EXISTS exit_reason TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS customer_marketing_state_history
        ADD COLUMN IF NOT EXISTS last_activation_at TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS customer_marketing_state_history
        ADD COLUMN IF NOT EXISTS last_conversion_marked_at TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS customer_marketing_state_history
        ADD COLUMN IF NOT EXISTS last_message_at TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_customer_marketing_state_history_person_id
        ON customer_marketing_state_history (person_id, recorded_at DESC)
        """
    )
    db.execute(
        """
        UPDATE customer_marketing_state_history
        SET external_userid = ''
        WHERE substr(COALESCE(external_userid, ''), 1, 7) = 'person:'
        """
    )


def _ensure_postgres_automation_program_tables(db) -> None:
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_program (
            id BIGSERIAL PRIMARY KEY,
            program_code TEXT NOT NULL UNIQUE,
            program_name TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft', 'active', 'paused', 'archived')),
            config_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_by TEXT NOT NULL DEFAULT '',
            updated_by TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_program_status
        ON automation_program (status, updated_at DESC, id DESC)
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_program_config_block (
            id BIGSERIAL PRIMARY KEY,
            program_id BIGINT NOT NULL REFERENCES automation_program(id) ON DELETE CASCADE,
            block_key TEXT NOT NULL,
            payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            status TEXT NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft', 'saved', 'published', 'archived')),
            version INTEGER NOT NULL DEFAULT 1,
            copied_from_program_id BIGINT REFERENCES automation_program(id) ON DELETE SET NULL,
            copied_from_block_id BIGINT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_automation_program_config_block_program_key UNIQUE (program_id, block_key)
        )
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_program_config_block_program
        ON automation_program_config_block (program_id, block_key)
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_program_channel_binding (
            id BIGSERIAL PRIMARY KEY,
            program_id BIGINT NOT NULL REFERENCES automation_program(id) ON DELETE CASCADE,
            channel_id BIGINT NOT NULL REFERENCES automation_channel(id) ON DELETE CASCADE,
            binding_status TEXT NOT NULL DEFAULT 'active'
                CHECK (binding_status IN ('active', 'paused', 'archived')),
            auto_enter_pool BOOLEAN NOT NULL DEFAULT TRUE,
            initial_audience_code TEXT NOT NULL DEFAULT 'pending_questionnaire'
                CHECK (initial_audience_code IN ('pending_questionnaire', 'operating', 'converted')),
            entry_rule_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            priority INTEGER NOT NULL DEFAULT 0,
            bound_by TEXT NOT NULL DEFAULT '',
            bound_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            unbound_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_automation_program_channel_binding_program_channel UNIQUE (program_id, channel_id)
        )
        """
    )
    db.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_program_channel_binding_active_channel
        ON automation_program_channel_binding (channel_id)
        WHERE binding_status = 'active'
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_program_channel_binding_program
        ON automation_program_channel_binding (program_id, binding_status, priority DESC, id DESC)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_program_channel_binding_channel
        ON automation_program_channel_binding (channel_id, binding_status, priority DESC, id DESC)
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_channel_contact (
            id BIGSERIAL PRIMARY KEY,
            channel_id BIGINT NOT NULL REFERENCES automation_channel(id) ON DELETE CASCADE,
            external_contact_id TEXT NOT NULL DEFAULT '',
            master_customer_id BIGINT REFERENCES people(id) ON DELETE SET NULL,
            owner_staff_id TEXT NOT NULL DEFAULT '',
            first_channel_entered_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_channel_entered_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            enter_count INTEGER NOT NULL DEFAULT 1,
            source_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_channel_contact_external
        ON automation_channel_contact (channel_id, external_contact_id)
        WHERE external_contact_id <> ''
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_channel_contact_channel_last
        ON automation_channel_contact (channel_id, last_channel_entered_at DESC)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_channel_contact_external
        ON automation_channel_contact (external_contact_id)
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_program_member (
            id BIGSERIAL PRIMARY KEY,
            program_id BIGINT NOT NULL REFERENCES automation_program(id) ON DELETE CASCADE,
            external_contact_id TEXT NOT NULL DEFAULT '',
            master_customer_id BIGINT REFERENCES people(id) ON DELETE SET NULL,
            source_channel_id BIGINT REFERENCES automation_channel(id) ON DELETE SET NULL,
            source_binding_id BIGINT REFERENCES automation_program_channel_binding(id) ON DELETE SET NULL,
            first_source_channel_id BIGINT REFERENCES automation_channel(id) ON DELETE SET NULL,
            latest_source_channel_id BIGINT REFERENCES automation_channel(id) ON DELETE SET NULL,
            in_program BOOLEAN NOT NULL DEFAULT TRUE,
            current_stage_code TEXT NOT NULL DEFAULT '',
            current_audience_code TEXT NOT NULL DEFAULT 'pending_questionnaire'
                CHECK (current_audience_code IN ('pending_questionnaire', 'operating', 'converted')),
            current_stage_entered_at TIMESTAMPTZ,
            pool_entered_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            exited_at TIMESTAMPTZ,
            exit_reason TEXT NOT NULL DEFAULT '',
            reentry_count INTEGER NOT NULL DEFAULT 0,
            state_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_program_member_external
        ON automation_program_member (program_id, external_contact_id)
        WHERE external_contact_id <> ''
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_program_member_stage_audience
        ON automation_program_member (program_id, current_stage_code, current_audience_code)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_program_member_source_channel
        ON automation_program_member (source_channel_id)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_program_member_latest_channel
        ON automation_program_member (latest_source_channel_id)
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_program_admission_attempt (
            id BIGSERIAL PRIMARY KEY,
            program_id BIGINT NOT NULL REFERENCES automation_program(id) ON DELETE CASCADE,
            channel_id BIGINT REFERENCES automation_channel(id) ON DELETE SET NULL,
            binding_id BIGINT REFERENCES automation_program_channel_binding(id) ON DELETE SET NULL,
            external_contact_id TEXT NOT NULL DEFAULT '',
            master_customer_id BIGINT REFERENCES people(id) ON DELETE SET NULL,
            trigger_type TEXT NOT NULL DEFAULT 'channel_enter',
            trigger_event_id TEXT NOT NULL DEFAULT '',
            trigger_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            admission_status TEXT NOT NULL DEFAULT 'pending'
                CHECK (admission_status IN ('standalone_channel', 'pending', 'accepted', 'waiting', 'converted', 'rejected', 'duplicate_active', 'manual_review')),
            pool_entered_at TIMESTAMPTZ,
            stage_code TEXT NOT NULL DEFAULT '',
            audience_code TEXT NOT NULL DEFAULT '',
            stage_entered_at TIMESTAMPTZ,
            entry_reason TEXT NOT NULL DEFAULT '',
            cleaning_result_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_program_admission_attempt_program
        ON automation_program_admission_attempt (program_id, created_at DESC)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_program_admission_attempt_channel
        ON automation_program_admission_attempt (channel_id, created_at DESC)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_program_admission_attempt_external
        ON automation_program_admission_attempt (external_contact_id, created_at DESC)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_program_admission_attempt_status
        ON automation_program_admission_attempt (admission_status, created_at DESC)
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_program_member_stage_history (
            id BIGSERIAL PRIMARY KEY,
            program_member_id BIGINT NOT NULL REFERENCES automation_program_member(id) ON DELETE CASCADE,
            program_id BIGINT NOT NULL REFERENCES automation_program(id) ON DELETE CASCADE,
            stage_code TEXT NOT NULL,
            audience_code TEXT NOT NULL DEFAULT '',
            entered_at TIMESTAMPTZ NOT NULL,
            exited_at TIMESTAMPTZ,
            entry_reason TEXT NOT NULL DEFAULT '',
            source_event_type TEXT NOT NULL DEFAULT '',
            source_event_id TEXT NOT NULL DEFAULT '',
            snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_program_member_stage_history_member
        ON automation_program_member_stage_history (program_member_id, entered_at DESC)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_program_member_stage_history_stage
        ON automation_program_member_stage_history (program_id, stage_code, entered_at DESC)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_program_member_stage_history_audience
        ON automation_program_member_stage_history (program_id, audience_code, entered_at DESC)
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_workflow
        ADD COLUMN IF NOT EXISTS program_id BIGINT REFERENCES automation_program(id) ON DELETE SET NULL
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_workflow_execution
        ADD COLUMN IF NOT EXISTS program_id BIGINT REFERENCES automation_program(id) ON DELETE SET NULL
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_workflow_program
        ON automation_workflow (program_id, status, updated_at DESC, id DESC)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_workflow_execution_program
        ON automation_workflow_execution (program_id, created_at DESC, id DESC)
        """
    )
    db.execute(
        """
        INSERT INTO automation_program (
            program_code,
            program_name,
            description,
            status,
            config_json,
            created_by,
            updated_by
        )
        SELECT
            'signup_conversion_v1',
            '默认自动化转化方案',
            '承接历史单例自动化运营能力的默认方案。',
            'active',
            '{"flow_design_source":"legacy_singleton"}'::jsonb,
            'system',
            'system'
        WHERE NOT EXISTS (
            SELECT 1 FROM automation_program WHERE program_code = 'signup_conversion_v1'
        )
        """
    )
    default_row = db.execute(
        "SELECT id FROM automation_program WHERE program_code = 'signup_conversion_v1' LIMIT 1"
    ).fetchone()
    if not default_row:
        return
    default_program_id = int(default_row["id"] if hasattr(default_row, "keys") else default_row[0])
    db.execute("UPDATE automation_workflow SET program_id = ? WHERE program_id IS NULL", (default_program_id,))
    db.execute("UPDATE automation_channel SET program_id = ? WHERE program_id IS NULL", (default_program_id,))
    db.execute(
        "UPDATE automation_profile_segment_template SET program_id = ? WHERE program_id IS NULL",
        (default_program_id,),
    )
    db.execute(
        """
        UPDATE automation_workflow_execution
        SET program_id = COALESCE(
            (
                SELECT automation_workflow.program_id
                FROM automation_workflow
                WHERE automation_workflow.id = automation_workflow_execution.workflow_id
                LIMIT 1
            ),
            ?
        )
        WHERE program_id IS NULL
        """,
        (default_program_id,),
    )


def _init_postgres(db) -> None:
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_channel
        ADD COLUMN IF NOT EXISTS program_id BIGINT
        """
    )
    for stmt in (
        "ALTER TABLE IF EXISTS automation_channel ADD COLUMN IF NOT EXISTS channel_type TEXT NOT NULL DEFAULT 'qrcode'",
        "ALTER TABLE IF EXISTS automation_channel ADD COLUMN IF NOT EXISTS carrier_type TEXT NOT NULL DEFAULT 'qrcode'",
        "ALTER TABLE IF EXISTS automation_channel ADD COLUMN IF NOT EXISTS customer_channel TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE IF EXISTS automation_channel ADD COLUMN IF NOT EXISTS link_url TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE IF EXISTS automation_channel ADD COLUMN IF NOT EXISTS final_url TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE IF EXISTS automation_channel ADD COLUMN IF NOT EXISTS welcome_image_library_ids JSONB NOT NULL DEFAULT '[]'::jsonb",
        "ALTER TABLE IF EXISTS automation_channel ADD COLUMN IF NOT EXISTS welcome_miniprogram_library_ids JSONB NOT NULL DEFAULT '[]'::jsonb",
    ):
        db.execute(stmt)
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_channel
        ADD COLUMN IF NOT EXISTS welcome_message TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_channel
        ADD COLUMN IF NOT EXISTS auto_accept_friend BOOLEAN NOT NULL DEFAULT FALSE
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_channel
        ADD COLUMN IF NOT EXISTS entry_tag_id TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_channel
        ADD COLUMN IF NOT EXISTS entry_tag_name TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_channel
        ADD COLUMN IF NOT EXISTS entry_tag_group_name TEXT NOT NULL DEFAULT ''
        """
    )
    # idx_automation_channel_program 由 schema_postgres.sql 建（line 1533）。
    # 这里**不要**再 CREATE INDEX —— fresh PG 上 automation_channel 表还没建，
    # CREATE INDEX 没有 IF EXISTS 的表存在性 guard，会让整个 init_db 挂掉。
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_profile_segment_template
        ADD COLUMN IF NOT EXISTS program_id BIGINT
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_workflow
        ADD COLUMN IF NOT EXISTS program_id BIGINT
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_workflow_execution
        ADD COLUMN IF NOT EXISTS program_id BIGINT
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS class_term_tag_mapping
        ADD COLUMN IF NOT EXISTS strategy_id TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS class_term_tag_mapping
        ADD COLUMN IF NOT EXISTS group_id TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS class_term_tag_mapping
        ADD COLUMN IF NOT EXISTS tag_id TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_sop_pool_config
        ADD COLUMN IF NOT EXISTS effective_start_at TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_sop_progress
        ADD COLUMN IF NOT EXISTS sop_anchor_date TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_sop_progress
        ADD COLUMN IF NOT EXISTS first_effective_in_pool_at TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_sop_progress
        ADD COLUMN IF NOT EXISTS last_in_pool_at TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_sop_batch_item
        ADD COLUMN IF NOT EXISTS day_index_snapshot INTEGER NOT NULL DEFAULT 0
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_sop_batch_item
        ADD COLUMN IF NOT EXISTS content_snapshot TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_sop_batch_item
        ADD COLUMN IF NOT EXISTS images_snapshot JSONB NOT NULL DEFAULT '[]'::jsonb
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS user_ops_deferred_jobs
        ADD COLUMN IF NOT EXISTS tenant_key TEXT NOT NULL DEFAULT 'aicrm'
        """
    )
    legacy_pulse_followup_tables = (
        "customer_pulse_metric_events",
        "customer_pulse_action_feedback",
        "customer_pulse_activity_logs",
        "customer_pulse_execution_logs",
        "customer_pulse_feedback_logs",
        "customer_pulse_cards",
        "customer_pulse_snapshots",
        "customer_pulse_signal_events",
        "followup_orchestrator_execution_logs",
        "followup_orchestrator_mission_feedback",
        "followup_orchestrator_assignment_decisions",
        "followup_orchestrator_mission_items",
        "followup_orchestrator_missions",
        "followup_orchestrator_policies",
    )
    for table_name in legacy_pulse_followup_tables:
        db.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_member
        ADD COLUMN IF NOT EXISTS current_audience_code TEXT NOT NULL DEFAULT 'pending_questionnaire'
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_member
        ADD COLUMN IF NOT EXISTS current_audience_entered_at TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_member
        ADD COLUMN IF NOT EXISTS profile_segment_key TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_member
        ADD COLUMN IF NOT EXISTS behavior_tier_key TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_member
        ADD COLUMN IF NOT EXISTS segment_refreshed_at TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_member
        DROP COLUMN IF EXISTS """
        + _LEGACY_AUTOMATION_MEMBER_FOLLOWUP_DECISION_COLUMN
    )

    # ----- 0004 / 0005 字段 ALTER 必须在 schema 加载之前跑！----------------
    # schema_postgres.sql 里有 CREATE INDEX 引用 trace_id / scenario_code 等
    # 新字段，老库上这些字段还没加，CREATE INDEX 会 UndefinedColumn 报错。
    # 这里先把字段加上，schema 才能跑过。
    for stmt in (
        "ALTER TABLE IF EXISTS automation_agent_config "
        "ADD COLUMN IF NOT EXISTS scenario_code TEXT NOT NULL DEFAULT 'one_to_one'",
        "ALTER TABLE IF EXISTS automation_agent_run "
        "ADD COLUMN IF NOT EXISTS trace_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE IF EXISTS outbound_tasks "
        "ADD COLUMN IF NOT EXISTS trace_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE IF EXISTS automation_touch_delivery_log "
        "ADD COLUMN IF NOT EXISTS trace_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE IF EXISTS automation_workflow "
        "ADD COLUMN IF NOT EXISTS review_status TEXT NOT NULL DEFAULT 'approved'",
        "ALTER TABLE IF EXISTS automation_workflow "
        "ADD COLUMN IF NOT EXISTS created_by_agent TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE IF EXISTS automation_workflow_execution_item "
        "ADD COLUMN IF NOT EXISTS last_error_text TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE IF EXISTS automation_workflow_execution_item "
        "ADD COLUMN IF NOT EXISTS last_error_at TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE IF EXISTS automation_workflow_execution_item "
        "ADD COLUMN IF NOT EXISTS retry_count INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE IF EXISTS automation_workflow_execution_item "
        "ADD COLUMN IF NOT EXISTS trace_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE IF EXISTS automation_workflow_execution_item "
        "ADD COLUMN IF NOT EXISTS next_node_id BIGINT",
        "ALTER TABLE IF EXISTS cloud_broadcast_plans "
        "ADD COLUMN IF NOT EXISTS segment_id BIGINT",
        "ALTER TABLE IF EXISTS cloud_broadcast_plans "
        "ADD COLUMN IF NOT EXISTS campaign_id BIGINT",
        "ALTER TABLE IF EXISTS questionnaires "
        "ADD COLUMN IF NOT EXISTS assessment_enabled BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE IF EXISTS questionnaires "
        "ADD COLUMN IF NOT EXISTS answer_display_mode TEXT NOT NULL DEFAULT 'all_in_one'",
        "ALTER TABLE IF EXISTS questionnaires "
        "ADD COLUMN IF NOT EXISTS assessment_config JSONB NOT NULL DEFAULT '{}'::jsonb",
        "ALTER TABLE IF EXISTS questionnaire_questions "
        "ADD COLUMN IF NOT EXISTS assessment_dimension_key TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE IF EXISTS questionnaire_questions "
        "ADD COLUMN IF NOT EXISTS sidebar_profile_field TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE IF EXISTS questionnaire_options "
        "ADD COLUMN IF NOT EXISTS assessment_type_key TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE IF EXISTS questionnaire_submissions "
        "ADD COLUMN IF NOT EXISTS assessment_result_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb",
        "ALTER TABLE IF EXISTS questionnaire_submissions "
        "ADD COLUMN IF NOT EXISTS result_token TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE IF EXISTS wechat_pay_orders "
        "ADD COLUMN IF NOT EXISTS userid_snapshot TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE IF EXISTS wechat_pay_orders "
        "ADD COLUMN IF NOT EXISTS mobile_snapshot TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE IF EXISTS wechat_pay_orders "
        "ADD COLUMN IF NOT EXISTS payer_name_snapshot TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE IF EXISTS wechat_pay_orders "
        "ADD COLUMN IF NOT EXISTS refunded_amount_total INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE IF EXISTS wechat_pay_orders "
        "ADD COLUMN IF NOT EXISTS refund_status TEXT NOT NULL DEFAULT ''",
    ):
        db.execute(stmt)

    schema_path = Path(current_app.root_path) / "schema_postgres.sql"
    _run_schema_with_forward_fk_retries(db, schema_path.read_text(encoding="utf-8"))
    db.execute(
        """
        ALTER TABLE IF EXISTS user_ops_deferred_jobs
        ADD COLUMN IF NOT EXISTS tenant_key TEXT NOT NULL DEFAULT 'aicrm'
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_user_ops_deferred_jobs_job_tenant_status
        ON user_ops_deferred_jobs (job_type, tenant_key, status, run_after, id DESC)
        """
    )
    _ensure_postgres_questionnaire_external_push_tables(db)
    _ensure_postgres_questionnaire_scrm_apply_log_columns(db)
    _ensure_postgres_wechat_pay_tables(db)
    _ensure_postgres_hxc_dashboard_v6_columns(db)
    _ensure_postgres_user_ops_page_tables(db)
    _ensure_postgres_miniprogram_library_thumb_image_id(db)
    _ensure_postgres_attachment_library(db)
    _ensure_postgres_automation_agent_config_tables(db)
    _ensure_postgres_automation_operation_templates(db)
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_workflow_node
        ADD COLUMN IF NOT EXISTS trigger_mode TEXT NOT NULL DEFAULT 'scheduled'
        """
    )
    db.execute(
        """
        UPDATE automation_workflow_node
        SET trigger_mode = CASE
            WHEN COALESCE(trigger_mode, '') IN ('scheduled', 'daily_recurring', 'audience_entered') THEN trigger_mode
            ELSE 'scheduled'
        END
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_workflow_node
        DROP CONSTRAINT IF EXISTS automation_workflow_node_trigger_mode_check
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_workflow_node
        ADD CONSTRAINT automation_workflow_node_trigger_mode_check
        CHECK (trigger_mode IN ('scheduled', 'daily_recurring', 'audience_entered'))
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_workflow_node_trigger
        ON automation_workflow_node (target_audience_code, trigger_mode, enabled, id ASC)
        """
    )
    _ensure_pending_questionnaire_followup_cadence(db)
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_workflow_execution
        DROP CONSTRAINT IF EXISTS automation_workflow_execution_trigger_type_check
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_workflow_execution
        ADD CONSTRAINT automation_workflow_execution_trigger_type_check
        CHECK (trigger_type IN ('scheduled_poll', 'daily_recurring_poll', 'manual_replay', 'debug'))
        """
    )
    _migrate_postgres_conversion_agent_pools_to_bindings(db)
    _ensure_postgres_customer_value_segment_tables(db)
    _ensure_postgres_customer_marketing_state_tables(db)
    _ensure_postgres_admin_auth_tables(db)
    _ensure_postgres_automation_program_tables(db)
    _ensure_automation_sop_v1_seed_data()
    _ensure_automation_agent_prompt_defaults()
    db.execute("ALTER TABLE questionnaire_questions DROP CONSTRAINT IF EXISTS questionnaire_questions_type_check")
    db.execute(
        """
        ALTER TABLE questionnaire_questions
        ADD CONSTRAINT questionnaire_questions_type_check
        CHECK (type IN ('single_choice', 'multi_choice', 'textarea', 'mobile'))
        """
    )
    db.execute(
        """
        ALTER TABLE questionnaire_questions
        ADD COLUMN IF NOT EXISTS placeholder_text TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS questionnaires
        ADD COLUMN IF NOT EXISTS answer_display_mode TEXT NOT NULL DEFAULT 'all_in_one'
        """
    )
    db.execute(
        """
        UPDATE questionnaires
        SET answer_display_mode = 'all_in_one'
        WHERE COALESCE(answer_display_mode, '') NOT IN ('all_in_one', 'one_by_one')
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS questionnaires
        DROP CONSTRAINT IF EXISTS questionnaires_answer_display_mode_check
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS questionnaires
        ADD CONSTRAINT questionnaires_answer_display_mode_check
        CHECK (answer_display_mode IN ('all_in_one', 'one_by_one'))
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS questionnaires
        ADD COLUMN IF NOT EXISTS assessment_enabled BOOLEAN NOT NULL DEFAULT FALSE
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS questionnaires
        ADD COLUMN IF NOT EXISTS assessment_config JSONB NOT NULL DEFAULT '{}'::jsonb
        """
    )
    db.execute(
        """
        ALTER TABLE questionnaire_questions
        ADD COLUMN IF NOT EXISTS assessment_dimension_key TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE questionnaire_questions
        ADD COLUMN IF NOT EXISTS sidebar_profile_field TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE questionnaire_options
        ADD COLUMN IF NOT EXISTS assessment_type_key TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE questionnaire_submissions
        ADD COLUMN IF NOT EXISTS mobile_snapshot TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE questionnaire_submissions
        ADD COLUMN IF NOT EXISTS assessment_result_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb
        """
    )
    db.execute(
        """
        ALTER TABLE questionnaire_submissions
        ADD COLUMN IF NOT EXISTS result_token TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_questionnaire_submissions_result_token
        ON questionnaire_submissions (result_token)
        WHERE result_token <> ''
        """
    )
    db.execute(
        """
        ALTER TABLE class_term_tag_mapping
        ADD COLUMN IF NOT EXISTS strategy_id TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE class_term_tag_mapping
        ADD COLUMN IF NOT EXISTS group_id TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE class_term_tag_mapping
        ADD COLUMN IF NOT EXISTS tag_id TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_class_term_tag_mapping_tag_id_non_empty
        ON class_term_tag_mapping (tag_id)
        WHERE tag_id <> ''
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_sop_progress_pool_anchor
        ON automation_sop_progress (pool_key, sop_anchor_date, updated_at DESC, id DESC)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_sop_batch_item_member_day_snapshot
        ON automation_sop_batch_item (member_id, pool_key, day_index_snapshot, id DESC)
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_member
        ADD COLUMN IF NOT EXISTS current_audience_code TEXT NOT NULL DEFAULT 'pending_questionnaire'
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_member
        ADD COLUMN IF NOT EXISTS current_audience_entered_at TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_member_audience
        ON automation_member (current_audience_code, updated_at DESC, id DESC)
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_member
        ADD COLUMN IF NOT EXISTS profile_segment_key TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_member
        ADD COLUMN IF NOT EXISTS behavior_tier_key TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_member
        ADD COLUMN IF NOT EXISTS segment_refreshed_at TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_member_segments
        ON automation_member (current_audience_code, profile_segment_key, behavior_tier_key)
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS wecom_customer_acquisition_links (
            id BIGSERIAL PRIMARY KEY,
            corp_id TEXT NOT NULL DEFAULT '',
            automation_channel_id BIGINT NOT NULL REFERENCES automation_channel(id) ON DELETE CASCADE,
            program_id BIGINT,
            workflow_id BIGINT,
            initial_audience_code TEXT NOT NULL DEFAULT 'pending_questionnaire'
                CHECK (initial_audience_code IN ('pending_questionnaire', 'operating', 'converted')),
            link_id TEXT NOT NULL DEFAULT '',
            link_name TEXT NOT NULL DEFAULT '',
            link_url TEXT NOT NULL DEFAULT '',
            customer_channel TEXT NOT NULL DEFAULT '',
            final_url TEXT NOT NULL DEFAULT '',
            skip_verify BOOLEAN NOT NULL DEFAULT FALSE,
            range_user_list JSONB NOT NULL DEFAULT '[]'::jsonb,
            range_department_list JSONB NOT NULL DEFAULT '[]'::jsonb,
            priority_option JSONB NOT NULL DEFAULT '{}'::jsonb,
            status TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'disabled')),
            last_sync_at TIMESTAMPTZ,
            last_event_at TIMESTAMPTZ,
            last_error TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_wecom_customer_acquisition_links_corp_link UNIQUE (corp_id, link_id),
            CONSTRAINT uq_wecom_customer_acquisition_links_corp_channel UNIQUE (corp_id, customer_channel)
        )
        """
    )
    for stmt in (
        "ALTER TABLE IF EXISTS wecom_customer_acquisition_links "
        "ADD COLUMN IF NOT EXISTS initial_audience_code TEXT NOT NULL DEFAULT 'pending_questionnaire'",
        "CREATE INDEX IF NOT EXISTS idx_wecom_customer_acquisition_links_channel "
        "ON wecom_customer_acquisition_links (automation_channel_id)",
        "CREATE INDEX IF NOT EXISTS idx_wecom_customer_acquisition_links_status "
        "ON wecom_customer_acquisition_links (status, updated_at DESC, id DESC)",
        "CREATE INDEX IF NOT EXISTS idx_wecom_customer_acquisition_links_program "
        "ON wecom_customer_acquisition_links (program_id, status, updated_at DESC, id DESC)",
    ):
        db.execute(stmt)
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_operation_task_group (
            id BIGSERIAL PRIMARY KEY,
            program_id BIGINT NOT NULL REFERENCES automation_program(id) ON DELETE CASCADE,
            group_name TEXT NOT NULL DEFAULT '',
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_by TEXT NOT NULL DEFAULT '',
            updated_by TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            archived_at TEXT NOT NULL DEFAULT ''
        )
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_operation_task_group_program
        ON automation_operation_task_group (program_id, sort_order ASC, id ASC)
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_operation_task (
            id BIGSERIAL PRIMARY KEY,
            program_id BIGINT NOT NULL REFERENCES automation_program(id) ON DELETE CASCADE,
            group_id BIGINT REFERENCES automation_operation_task_group(id) ON DELETE SET NULL,
            task_name TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft', 'active', 'paused', 'archived')),
            trigger_type TEXT NOT NULL DEFAULT 'scheduled_daily'
                CHECK (trigger_type IN ('scheduled_daily', 'audience_entered')),
            send_time TEXT NOT NULL DEFAULT '10:00',
            timezone TEXT NOT NULL DEFAULT 'Asia/Shanghai',
            target_audience_code TEXT NOT NULL DEFAULT 'operating'
                CHECK (target_audience_code IN ('pending_questionnaire', 'operating', 'converted')),
            audience_day_offset INTEGER NOT NULL DEFAULT 1,
            behavior_filter TEXT NOT NULL DEFAULT 'none'
                CHECK (behavior_filter IN ('none', 'lt_2', 'between_2_9', 'gte_10')),
            content_mode TEXT NOT NULL DEFAULT 'unified'
                CHECK (content_mode IN ('unified', 'profile_layered', 'behavior_layered', 'agent')),
            profile_segment_template_id BIGINT REFERENCES automation_profile_segment_template(id) ON DELETE SET NULL,
            unified_content_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            segment_contents_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            agent_config_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_by TEXT NOT NULL DEFAULT '',
            updated_by TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            published_at TIMESTAMPTZ
        )
        """
    )
    for stmt in (
        "ALTER TABLE IF EXISTS automation_operation_task "
        "ADD COLUMN IF NOT EXISTS trigger_type TEXT NOT NULL DEFAULT 'scheduled_daily'",
        "CREATE INDEX IF NOT EXISTS idx_automation_operation_task_program "
        "ON automation_operation_task (program_id, status, send_time, id DESC)",
        "CREATE INDEX IF NOT EXISTS idx_automation_operation_task_group "
        "ON automation_operation_task (group_id, status, updated_at DESC, id DESC)",
    ):
        db.execute(stmt)
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_operation_task_execution (
            id BIGSERIAL PRIMARY KEY,
            execution_id TEXT NOT NULL UNIQUE,
            program_id BIGINT NOT NULL REFERENCES automation_program(id) ON DELETE CASCADE,
            task_id BIGINT NOT NULL REFERENCES automation_operation_task(id) ON DELETE CASCADE,
            scheduled_for TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            status TEXT NOT NULL DEFAULT 'running',
            target_count INTEGER NOT NULL DEFAULT 0,
            enqueued_count INTEGER NOT NULL DEFAULT 0,
            sent_count INTEGER NOT NULL DEFAULT 0,
            failed_count INTEGER NOT NULL DEFAULT 0,
            summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            finished_at TIMESTAMPTZ
        )
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_operation_task_execution_task
        ON automation_operation_task_execution (task_id, scheduled_for DESC, id DESC)
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_operation_task_execution_item (
            id BIGSERIAL PRIMARY KEY,
            execution_id TEXT NOT NULL REFERENCES automation_operation_task_execution(execution_id) ON DELETE CASCADE,
            task_id BIGINT NOT NULL REFERENCES automation_operation_task(id) ON DELETE CASCADE,
            member_id BIGINT NOT NULL REFERENCES automation_member(id) ON DELETE CASCADE,
            audience_entry_id BIGINT REFERENCES automation_member_audience_entry(id) ON DELETE SET NULL,
            external_contact_id TEXT NOT NULL DEFAULT '',
            segment_key TEXT NOT NULL DEFAULT '',
            rendered_content_text TEXT NOT NULL DEFAULT '',
            content_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            send_record_id BIGINT,
            status TEXT NOT NULL DEFAULT 'pending',
            error_message TEXT NOT NULL DEFAULT '',
            sent_at TIMESTAMPTZ
        )
        """
    )
    for stmt in (
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_operation_task_item_entry "
        "ON automation_operation_task_execution_item (task_id, audience_entry_id) WHERE audience_entry_id IS NOT NULL",
        "CREATE INDEX IF NOT EXISTS idx_automation_operation_task_item_execution "
        "ON automation_operation_task_execution_item (execution_id, status, id ASC)",
    ):
        db.execute(stmt)
    db.execute("ALTER TABLE IF EXISTS broadcast_jobs DROP CONSTRAINT IF EXISTS broadcast_jobs_source_type_check")
    db.execute(
        """
        ALTER TABLE IF EXISTS broadcast_jobs
        ADD CONSTRAINT broadcast_jobs_source_type_check
        CHECK (source_type IN ('campaign', 'sop', 'workflow', 'operation_task', 'cloud_plan', 'focus_send', 'deferred', 'manual'))
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_agent_output
        ADD COLUMN IF NOT EXISTS adopted_by TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_agent_output
        ADD COLUMN IF NOT EXISTS adopted_action TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_agent_output
        ADD COLUMN IF NOT EXISTS adopted_at TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_agent_output
        ADD COLUMN IF NOT EXISTS outcome_status TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        ALTER TABLE IF EXISTS automation_agent_output
        ADD COLUMN IF NOT EXISTS outcome_value TEXT NOT NULL DEFAULT ''
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_agent_output_target_agent
        ON automation_agent_output (target_agent_code, created_at DESC, id DESC)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_agent_output_outcome_status
        ON automation_agent_output (outcome_status, created_at DESC, id DESC)
        """
    )
    db.commit()
