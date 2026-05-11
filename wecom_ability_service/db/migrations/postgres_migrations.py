from __future__ import annotations

from pathlib import Path

from flask import current_app

from ..helpers import _postgres_table_columns
from . import (
    _ensure_automation_agent_prompt_defaults,
    _ensure_automation_sop_v1_seed_data,
)


_LEGACY_AUTOMATION_MEMBER_FOLLOWUP_DECISION_COLUMN = "questionnaire" "_result"


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
    _ensure_postgres_user_ops_page_tables(db)
    _ensure_postgres_automation_agent_config_tables(db)
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
        ALTER TABLE questionnaire_submissions
        ADD COLUMN IF NOT EXISTS mobile_snapshot TEXT NOT NULL DEFAULT ''
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
    # ----- 0004 / 0005 迁移的字段 ALTER（兼容 init-db 走 schema 路径） -------
    # 让既有 PG 库通过 init-db 升级时也能拿到 trace_id / scenario_code / review_status
    # 等新字段；schema_postgres.sql 的 CREATE TABLE IF NOT EXISTS 不会改老表。
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
    ):
        db.execute(stmt)
    db.commit()
