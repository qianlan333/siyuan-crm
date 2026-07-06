"""create missing baseline runtime tables.

Revision ID: 0076_create_missing_baseline_runtime_tables
Revises: 0075_drop_message_batch_legacy_tables
"""

from __future__ import annotations

from alembic import op

from migrations.audience_read import ensure_audience_read_schema


revision = "0076_create_missing_baseline_runtime_tables"
down_revision = "0075_drop_message_batch_legacy_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    audience_read_available = ensure_audience_read_schema()
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS questionnaires (
            id BIGSERIAL PRIMARY KEY,
            slug TEXT NOT NULL DEFAULT '',
            name TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            is_disabled BOOLEAN NOT NULL DEFAULT FALSE,
            redirect_url TEXT NOT NULL DEFAULT '',
            completion_target_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            answer_display_mode TEXT NOT NULL DEFAULT 'all_in_one',
            assessment_enabled BOOLEAN NOT NULL DEFAULT FALSE,
            assessment_config JSONB NOT NULL DEFAULT '{}'::jsonb,
            external_push_enabled BOOLEAN NOT NULL DEFAULT FALSE,
            external_push_url TEXT NOT NULL DEFAULT '',
            external_push_type TEXT NOT NULL DEFAULT '',
            external_push_expires_at_ts BIGINT,
            external_push_day INTEGER,
            external_push_frequency INTEGER,
            external_push_remark TEXT NOT NULL DEFAULT '',
            external_push_custom_params JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_questionnaires_slug ON questionnaires (slug) WHERE slug <> ''")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS questionnaire_questions (
            id BIGSERIAL PRIMARY KEY,
            questionnaire_id BIGINT NOT NULL DEFAULT 0,
            type TEXT NOT NULL DEFAULT 'single_choice',
            title TEXT NOT NULL DEFAULT '',
            placeholder_text TEXT NOT NULL DEFAULT '',
            assessment_dimension_key TEXT NOT NULL DEFAULT '',
            sidebar_profile_field TEXT NOT NULL DEFAULT '',
            required BOOLEAN NOT NULL DEFAULT FALSE,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_questionnaire_questions_questionnaire
        ON questionnaire_questions (questionnaire_id, sort_order, id)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS questionnaire_options (
            id BIGSERIAL PRIMARY KEY,
            question_id BIGINT NOT NULL DEFAULT 0,
            option_text TEXT NOT NULL DEFAULT '',
            score DOUBLE PRECISION NOT NULL DEFAULT 0,
            assessment_type_key TEXT NOT NULL DEFAULT '',
            tag_codes JSONB NOT NULL DEFAULT '[]'::jsonb,
            is_other BOOLEAN NOT NULL DEFAULT FALSE,
            other_placeholder TEXT NOT NULL DEFAULT '',
            other_max_length INTEGER NOT NULL DEFAULT 80,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_questionnaire_options_question
        ON questionnaire_options (question_id, sort_order, id)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS questionnaire_score_rules (
            id BIGSERIAL PRIMARY KEY,
            questionnaire_id BIGINT NOT NULL DEFAULT 0,
            min_score DOUBLE PRECISION,
            max_score DOUBLE PRECISION,
            tag_codes JSONB NOT NULL DEFAULT '[]'::jsonb,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_questionnaire_score_rules_questionnaire
        ON questionnaire_score_rules (questionnaire_id, sort_order, id)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS questionnaire_submissions (
            id BIGSERIAL PRIMARY KEY,
            questionnaire_id BIGINT NOT NULL DEFAULT 0,
            unionid TEXT NOT NULL DEFAULT '',
            follow_user_userid TEXT NOT NULL DEFAULT '',
            matched_by TEXT NOT NULL DEFAULT '',
            source_channel TEXT NOT NULL DEFAULT '',
            campaign_id TEXT NOT NULL DEFAULT '',
            staff_id TEXT NOT NULL DEFAULT '',
            total_score DOUBLE PRECISION NOT NULL DEFAULT 0,
            final_tags JSONB NOT NULL DEFAULT '[]'::jsonb,
            assessment_result_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
            result_token TEXT NOT NULL DEFAULT '',
            redirect_url_snapshot TEXT NOT NULL DEFAULT '',
            submitted_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_questionnaire_submissions_unionid_submitted
        ON questionnaire_submissions (unionid, submitted_at DESC, id DESC)
        WHERE unionid <> ''
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_questionnaire_submissions_questionnaire
        ON questionnaire_submissions (questionnaire_id, submitted_at DESC, id DESC)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS questionnaire_submission_answers (
            id BIGSERIAL PRIMARY KEY,
            submission_id BIGINT NOT NULL DEFAULT 0,
            question_id BIGINT NOT NULL DEFAULT 0,
            question_type TEXT NOT NULL DEFAULT '',
            question_title_snapshot TEXT NOT NULL DEFAULT '',
            selected_option_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
            selected_option_texts_snapshot JSONB NOT NULL DEFAULT '[]'::jsonb,
            selected_option_scores_snapshot JSONB NOT NULL DEFAULT '[]'::jsonb,
            selected_option_tags_snapshot JSONB NOT NULL DEFAULT '[]'::jsonb,
            text_value TEXT NOT NULL DEFAULT '',
            score_contribution DOUBLE PRECISION NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_questionnaire_submission_answers_submission
        ON questionnaire_submission_answers (submission_id, id)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS questionnaire_external_push_logs (
            id BIGSERIAL PRIMARY KEY,
            questionnaire_id BIGINT NOT NULL DEFAULT 0,
            questionnaire_title_snapshot TEXT NOT NULL DEFAULT '',
            submission_record_id BIGINT NOT NULL DEFAULT 0,
            retry_from_log_id BIGINT,
            retry_attempt INTEGER NOT NULL DEFAULT 0,
            user_id TEXT NOT NULL DEFAULT '',
            target_url TEXT NOT NULL DEFAULT '',
            request_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            response_status_code INTEGER,
            response_body TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT '',
            failure_reason TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_questionnaire_external_push_logs_questionnaire
        ON questionnaire_external_push_logs (questionnaire_id, created_at DESC, id DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_questionnaire_external_push_logs_retry
        ON questionnaire_external_push_logs (retry_from_log_id)
        WHERE retry_from_log_id IS NOT NULL
        """
    )
    if not audience_read_available:
        return
    op.execute(
        """
        DO $$
        DECLARE
            updated_at_expr TEXT;
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'questionnaire_submissions' AND column_name = 'updated_at'
            ) THEN
                updated_at_expr := 'qs.updated_at';
            ELSIF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'questionnaire_submissions' AND column_name = 'submitted_at'
            ) THEN
                updated_at_expr := 'qs.submitted_at';
            ELSE
                updated_at_expr := 'qs.created_at';
            END IF;

            EXECUTE format($sql$
            CREATE OR REPLACE VIEW audience_read.questionnaire_submissions_v1 AS
            SELECT
                qs.id AS submission_id,
                qs.questionnaire_id,
                qs.unionid,
                COALESCE(identity.primary_external_userid, '')::text AS external_userid,
                qs.follow_user_userid AS owner_userid,
                ''::text AS mobile_hash,
                qs.submitted_at,
                qs.created_at,
                %s AS updated_at,
                qs.total_score,
                qs.final_tags,
                qs.assessment_result_snapshot,
                'unionid'::text AS identity_type,
                qs.unionid::text AS identity_value,
                jsonb_build_object(
                    'submission_id', qs.id,
                    'questionnaire_id', qs.questionnaire_id,
                    'unionid', qs.unionid,
                    'score', qs.total_score,
                    'tags', qs.final_tags
                ) AS payload_json
            FROM questionnaire_submissions qs
            LEFT JOIN crm_user_identity identity ON identity.unionid = qs.unionid
            $sql$, updated_at_expr);
        END $$;
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS attachment_library (
            id BIGSERIAL PRIMARY KEY,
            name TEXT NOT NULL DEFAULT '',
            file_name TEXT NOT NULL DEFAULT '',
            mime_type TEXT NOT NULL DEFAULT 'application/octet-stream',
            file_size BIGINT NOT NULL DEFAULT 0,
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
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_attachment_library_enabled
        ON attachment_library (enabled, updated_at DESC, id DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_attachment_library_tags_gin
        ON attachment_library USING GIN (tags)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS outbound_webhook_deliveries (
            id BIGSERIAL PRIMARY KEY,
            event_type TEXT NOT NULL DEFAULT '',
            source_key TEXT NOT NULL DEFAULT '',
            source_id TEXT NOT NULL DEFAULT '',
            target_url TEXT NOT NULL DEFAULT '',
            payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            payload_summary TEXT NOT NULL DEFAULT '',
            token_configured BOOLEAN NOT NULL DEFAULT FALSE,
            status TEXT NOT NULL DEFAULT 'pending',
            attempt_count INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 3,
            response_status_code INTEGER,
            response_body_summary TEXT NOT NULL DEFAULT '',
            last_error TEXT NOT NULL DEFAULT '',
            last_attempted_at TIMESTAMPTZ,
            next_retry_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_outbound_webhook_deliveries_status_retry
        ON outbound_webhook_deliveries (status, next_retry_at, id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_outbound_webhook_deliveries_event
        ON outbound_webhook_deliveries (event_type, id DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS audience_read.questionnaire_submissions_v1")
    op.execute("DROP INDEX IF EXISTS idx_questionnaire_external_push_logs_retry")
    op.execute("DROP INDEX IF EXISTS idx_questionnaire_external_push_logs_questionnaire")
    op.execute("DROP TABLE IF EXISTS questionnaire_external_push_logs")
    op.execute("DROP INDEX IF EXISTS idx_questionnaire_submission_answers_submission")
    op.execute("DROP TABLE IF EXISTS questionnaire_submission_answers")
    op.execute("DROP INDEX IF EXISTS idx_questionnaire_submissions_questionnaire")
    op.execute("DROP INDEX IF EXISTS idx_questionnaire_submissions_unionid_submitted")
    op.execute("DROP TABLE IF EXISTS questionnaire_submissions")
    op.execute("DROP INDEX IF EXISTS idx_questionnaire_score_rules_questionnaire")
    op.execute("DROP TABLE IF EXISTS questionnaire_score_rules")
    op.execute("DROP INDEX IF EXISTS idx_questionnaire_options_question")
    op.execute("DROP TABLE IF EXISTS questionnaire_options")
    op.execute("DROP INDEX IF EXISTS idx_questionnaire_questions_questionnaire")
    op.execute("DROP TABLE IF EXISTS questionnaire_questions")
    op.execute("DROP INDEX IF EXISTS ux_questionnaires_slug")
    op.execute("DROP TABLE IF EXISTS questionnaires")
    op.execute("DROP INDEX IF EXISTS idx_outbound_webhook_deliveries_event")
    op.execute("DROP INDEX IF EXISTS idx_outbound_webhook_deliveries_status_retry")
    op.execute("DROP TABLE IF EXISTS outbound_webhook_deliveries")
    op.execute("DROP INDEX IF EXISTS idx_attachment_library_tags_gin")
    op.execute("DROP INDEX IF EXISTS idx_attachment_library_enabled")
    op.execute("DROP TABLE IF EXISTS attachment_library")
