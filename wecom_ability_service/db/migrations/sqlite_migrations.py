from __future__ import annotations

from pathlib import Path

from flask import current_app

from ..helpers import (
    _sqlite_normalized_conversion_pool_sql,
    _sqlite_table_columns,
    _sqlite_table_exists,
    _sqlite_table_sql,
)
from . import (
    _ensure_automation_agent_prompt_defaults,
    _ensure_automation_sop_v1_seed_data,
)


_LEGACY_AUTOMATION_MEMBER_FOLLOWUP_DECISION_COLUMN = "questionnaire" "_result"


def _ensure_sqlite_questionnaire_question_fields(db) -> None:
    create_sql = _sqlite_table_sql(db, "questionnaire_questions").lower()
    if not create_sql:
        return
    columns = _sqlite_table_columns(db, "questionnaire_questions")
    if "placeholder_text" not in columns:
        db.execute("ALTER TABLE questionnaire_questions ADD COLUMN placeholder_text TEXT NOT NULL DEFAULT ''")
        columns.add("placeholder_text")
    if "'mobile'" in create_sql:
        return
    db.execute("PRAGMA foreign_keys = OFF")
    db.execute(
        """
        CREATE TABLE questionnaire_questions__new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            questionnaire_id INTEGER NOT NULL REFERENCES questionnaires(id) ON DELETE CASCADE,
            type TEXT NOT NULL CHECK (type IN ('single_choice', 'multi_choice', 'textarea', 'mobile')),
            title TEXT NOT NULL,
            placeholder_text TEXT NOT NULL DEFAULT '',
            required INTEGER NOT NULL DEFAULT 0,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        INSERT INTO questionnaire_questions__new (
            id, questionnaire_id, type, title, placeholder_text, required, sort_order, created_at, updated_at
        )
        SELECT id, questionnaire_id, type, title, COALESCE(placeholder_text, ''), required, sort_order, created_at, updated_at
        FROM questionnaire_questions
        """
    )
    db.execute("DROP TABLE questionnaire_questions")
    db.execute("ALTER TABLE questionnaire_questions__new RENAME TO questionnaire_questions")
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_questionnaire_questions_questionnaire
        ON questionnaire_questions (questionnaire_id, sort_order, id)
        """
    )
    db.execute("PRAGMA foreign_keys = ON")


def _ensure_sqlite_questionnaire_external_push_tables(db) -> None:
    questionnaire_columns = _sqlite_table_columns(db, "questionnaires")
    if questionnaire_columns:
        if "external_push_enabled" not in questionnaire_columns:
            db.execute("ALTER TABLE questionnaires ADD COLUMN external_push_enabled INTEGER NOT NULL DEFAULT 0")
        if "external_push_url" not in questionnaire_columns:
            db.execute("ALTER TABLE questionnaires ADD COLUMN external_push_url TEXT NOT NULL DEFAULT ''")
        if "external_push_day" not in questionnaire_columns:
            db.execute("ALTER TABLE questionnaires ADD COLUMN external_push_day INTEGER")
        if "external_push_frequency" not in questionnaire_columns:
            db.execute("ALTER TABLE questionnaires ADD COLUMN external_push_frequency INTEGER")
        if "external_push_remark" not in questionnaire_columns:
            db.execute("ALTER TABLE questionnaires ADD COLUMN external_push_remark TEXT NOT NULL DEFAULT ''")
        if "external_push_custom_params" not in questionnaire_columns:
            db.execute("ALTER TABLE questionnaires ADD COLUMN external_push_custom_params TEXT NOT NULL DEFAULT '[]'")
        db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_questionnaires_external_push_enabled
            ON questionnaires (external_push_enabled)
            """
        )

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS questionnaire_external_push_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            questionnaire_id INTEGER NOT NULL REFERENCES questionnaires(id) ON DELETE CASCADE,
            questionnaire_title_snapshot TEXT NOT NULL DEFAULT '',
            submission_record_id INTEGER NOT NULL REFERENCES questionnaire_submissions(id) ON DELETE CASCADE,
            retry_from_log_id INTEGER REFERENCES questionnaire_external_push_logs(id) ON DELETE SET NULL,
            retry_attempt INTEGER NOT NULL DEFAULT 0,
            user_id TEXT NOT NULL DEFAULT '',
            target_url TEXT NOT NULL DEFAULT '',
            request_payload TEXT NOT NULL DEFAULT '{}',
            response_status_code INTEGER,
            response_body TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'failed',
            failure_reason TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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
    push_log_columns = _sqlite_table_columns(db, "questionnaire_external_push_logs")
    if push_log_columns and "retry_from_log_id" not in push_log_columns:
        db.execute("ALTER TABLE questionnaire_external_push_logs ADD COLUMN retry_from_log_id INTEGER")
    if push_log_columns and "retry_attempt" not in push_log_columns:
        db.execute("ALTER TABLE questionnaire_external_push_logs ADD COLUMN retry_attempt INTEGER NOT NULL DEFAULT 0")
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_questionnaire_external_push_logs_retry_from
        ON questionnaire_external_push_logs (retry_from_log_id, created_at DESC, id DESC)
        """
    )


def _ensure_sqlite_user_ops_page_tables(db) -> None:
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
    send_record_columns = _sqlite_table_columns(db, "user_ops_send_records")
    if send_record_columns and "image_count" not in send_record_columns:
        db.execute("ALTER TABLE user_ops_send_records ADD COLUMN image_count INTEGER NOT NULL DEFAULT 0")
    if send_record_columns and "task_results_json" not in send_record_columns:
        db.execute("ALTER TABLE user_ops_send_records ADD COLUMN task_results_json TEXT NOT NULL DEFAULT '[]'")
    if send_record_columns and "last_status_sync_at" not in send_record_columns:
        db.execute("ALTER TABLE user_ops_send_records ADD COLUMN last_status_sync_at TEXT")


def _ensure_sqlite_customer_value_segment_tables(db) -> None:
    current_columns = _sqlite_table_columns(db, "customer_value_segment_current")
    if current_columns:
        if "submission_id" not in current_columns:
            db.execute("ALTER TABLE customer_value_segment_current ADD COLUMN submission_id INTEGER")
        if "matched_question_ids_json" not in current_columns:
            db.execute(
                "ALTER TABLE customer_value_segment_current ADD COLUMN matched_question_ids_json TEXT NOT NULL DEFAULT '[]'"
            )
        if "evaluated_at" not in current_columns:
            db.execute(
                "ALTER TABLE customer_value_segment_current ADD COLUMN evaluated_at TEXT NOT NULL DEFAULT ''"
            )

    history_columns = _sqlite_table_columns(db, "customer_value_segment_history")
    if history_columns:
        if "submission_id" not in history_columns:
            db.execute("ALTER TABLE customer_value_segment_history ADD COLUMN submission_id INTEGER")
        if "matched_question_ids_json" not in history_columns:
            db.execute(
                "ALTER TABLE customer_value_segment_history ADD COLUMN matched_question_ids_json TEXT NOT NULL DEFAULT '[]'"
            )
        if "evaluated_at" not in history_columns:
            db.execute(
                "ALTER TABLE customer_value_segment_history ADD COLUMN evaluated_at TEXT NOT NULL DEFAULT ''"
            )


def _rebuild_sqlite_customer_marketing_state_current_table(db) -> None:
    current_columns = _sqlite_table_columns(db, "customer_marketing_state_current")
    if not current_columns:
        return
    db.execute("DROP TABLE IF EXISTS customer_marketing_state_current__new")
    db.execute(
        """
        CREATE TABLE customer_marketing_state_current__new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_id INTEGER REFERENCES people(id) ON DELETE SET NULL,
            external_userid TEXT NOT NULL DEFAULT '',
            automation_key TEXT NOT NULL DEFAULT 'signup_conversion_v1',
            main_stage TEXT NOT NULL DEFAULT 'pending',
            sub_stage TEXT NOT NULL DEFAULT '',
            activated INTEGER NOT NULL DEFAULT 0,
            converted INTEGER NOT NULL DEFAULT 0,
            eligible_for_conversion INTEGER NOT NULL DEFAULT 0,
            lifecycle_status TEXT NOT NULL DEFAULT 'idle',
            last_activation_at TEXT NOT NULL DEFAULT '',
            last_conversion_marked_at TEXT NOT NULL DEFAULT '',
            last_message_at TEXT NOT NULL DEFAULT '',
            last_batch_id INTEGER REFERENCES message_batches(id) ON DELETE SET NULL,
            last_batch_status TEXT NOT NULL DEFAULT '',
            last_batch_window_start TEXT NOT NULL DEFAULT '',
            last_batch_window_end TEXT NOT NULL DEFAULT '',
            last_trigger_message_at TEXT NOT NULL DEFAULT '',
            entered_at TEXT,
            exited_at TEXT,
            exit_reason TEXT NOT NULL DEFAULT '',
            state_payload_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        f"""
        INSERT INTO customer_marketing_state_current__new (
            id,
            person_id,
            external_userid,
            automation_key,
            main_stage,
            sub_stage,
            activated,
            converted,
            eligible_for_conversion,
            lifecycle_status,
            last_activation_at,
            last_conversion_marked_at,
            last_message_at,
            last_batch_id,
            last_batch_status,
            last_batch_window_start,
            last_batch_window_end,
            last_trigger_message_at,
            entered_at,
            exited_at,
            exit_reason,
            state_payload_json,
            created_at,
            updated_at
        )
        SELECT
            id,
            {"person_id" if "person_id" in current_columns else "NULL"} AS person_id,
            CASE
                WHEN substr(COALESCE(external_userid, ''), 1, 7) = 'person:' THEN ''
                ELSE COALESCE(external_userid, '')
            END AS external_userid,
            {"automation_key" if "automation_key" in current_columns else "'signup_conversion_v1'"} AS automation_key,
            {"main_stage" if "main_stage" in current_columns else "'pending'"} AS main_stage,
            {"sub_stage" if "sub_stage" in current_columns else "''"} AS sub_stage,
            {"activated" if "activated" in current_columns else "0"} AS activated,
            {"converted" if "converted" in current_columns else "0"} AS converted,
            {"eligible_for_conversion" if "eligible_for_conversion" in current_columns else "0"} AS eligible_for_conversion,
            {"lifecycle_status" if "lifecycle_status" in current_columns else "'idle'"} AS lifecycle_status,
            {"last_activation_at" if "last_activation_at" in current_columns else "''"} AS last_activation_at,
            {"last_conversion_marked_at" if "last_conversion_marked_at" in current_columns else "''"} AS last_conversion_marked_at,
            {"last_message_at" if "last_message_at" in current_columns else "''"} AS last_message_at,
            {"last_batch_id" if "last_batch_id" in current_columns else "NULL"} AS last_batch_id,
            {"last_batch_status" if "last_batch_status" in current_columns else "''"} AS last_batch_status,
            {"last_batch_window_start" if "last_batch_window_start" in current_columns else "''"} AS last_batch_window_start,
            {"last_batch_window_end" if "last_batch_window_end" in current_columns else "''"} AS last_batch_window_end,
            {"last_trigger_message_at" if "last_trigger_message_at" in current_columns else "''"} AS last_trigger_message_at,
            {"entered_at" if "entered_at" in current_columns else "NULL"} AS entered_at,
            {"exited_at" if "exited_at" in current_columns else "NULL"} AS exited_at,
            {"exit_reason" if "exit_reason" in current_columns else "''"} AS exit_reason,
            {"state_payload_json" if "state_payload_json" in current_columns else "'{}'"} AS state_payload_json,
            {"created_at" if "created_at" in current_columns else "CURRENT_TIMESTAMP"} AS created_at,
            {"updated_at" if "updated_at" in current_columns else "CURRENT_TIMESTAMP"} AS updated_at
        FROM customer_marketing_state_current
        """
    )
    db.execute(
        """
        DELETE FROM customer_marketing_state_current__new
        WHERE id IN (
            SELECT id
            FROM (
                SELECT
                    id,
                    ROW_NUMBER() OVER (
                        PARTITION BY person_id
                        ORDER BY updated_at DESC, id DESC
                    ) AS row_number
                FROM customer_marketing_state_current__new
                WHERE person_id IS NOT NULL
            ) AS ranked
            WHERE row_number > 1
        )
        """
    )
    db.execute("DROP TABLE customer_marketing_state_current")
    db.execute("ALTER TABLE customer_marketing_state_current__new RENAME TO customer_marketing_state_current")
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_customer_marketing_state_current_external_userid
        ON customer_marketing_state_current (external_userid)
        """
    )
    db.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_customer_marketing_state_current_person_id_non_null
        ON customer_marketing_state_current (person_id)
        WHERE person_id IS NOT NULL
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_customer_marketing_state_current_main_stage
        ON customer_marketing_state_current (main_stage)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_customer_marketing_state_current_sub_stage
        ON customer_marketing_state_current (sub_stage)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_customer_marketing_state_current_eligible_for_conversion
        ON customer_marketing_state_current (eligible_for_conversion)
        """
    )


def _rebuild_sqlite_automation_member_table(db) -> None:
    member_columns = _sqlite_table_columns(db, "automation_member")
    if not member_columns:
        return
    db.execute("DROP TABLE IF EXISTS automation_member__new")
    db.execute(
        """
        CREATE TABLE automation_member__new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            external_contact_id TEXT NOT NULL DEFAULT '',
            phone TEXT NOT NULL DEFAULT '',
            master_customer_id INTEGER REFERENCES people(id) ON DELETE SET NULL,
            owner_staff_id TEXT NOT NULL DEFAULT '',
            in_pool INTEGER NOT NULL DEFAULT 0,
            current_pool TEXT NOT NULL DEFAULT 'removed',
            follow_type TEXT NOT NULL DEFAULT '',
            questionnaire_status TEXT NOT NULL DEFAULT 'pending',
            decision_source TEXT NOT NULL DEFAULT 'system',
            source_type TEXT NOT NULL DEFAULT 'system',
            source_channel_id INTEGER REFERENCES automation_channel(id) ON DELETE SET NULL,
            current_audience_code TEXT NOT NULL DEFAULT 'pending_questionnaire'
                CHECK (current_audience_code IN ('pending_questionnaire', 'operating', 'converted')),
            current_audience_entered_at TEXT NOT NULL DEFAULT '',
            last_active_pool TEXT NOT NULL DEFAULT '',
            joined_at TEXT NOT NULL DEFAULT '',
            last_ai_push_at TEXT NOT NULL DEFAULT '',
            ai_cooldown_until TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        f"""
        INSERT INTO automation_member__new (
            id,
            external_contact_id,
            phone,
            master_customer_id,
            owner_staff_id,
            in_pool,
            current_pool,
            follow_type,
            questionnaire_status,
            decision_source,
            source_type,
            source_channel_id,
            current_audience_code,
            current_audience_entered_at,
            last_active_pool,
            joined_at,
            last_ai_push_at,
            ai_cooldown_until,
            created_at,
            updated_at
        )
        SELECT
            id,
            COALESCE(external_contact_id, ''),
            COALESCE(phone, ''),
            {"master_customer_id" if "master_customer_id" in member_columns else "NULL"} AS master_customer_id,
            COALESCE(owner_staff_id, ''),
            COALESCE(in_pool, 0),
            {_sqlite_normalized_conversion_pool_sql("current_pool")},
            COALESCE(follow_type, ''),
            COALESCE(questionnaire_status, 'pending'),
            COALESCE(decision_source, 'system'),
            COALESCE(source_type, 'system'),
            {"source_channel_id" if "source_channel_id" in member_columns else "NULL"} AS source_channel_id,
            CASE
                WHEN {"1" if "current_audience_code" in member_columns else "0"} = 1 THEN
                    CASE
                        WHEN COALESCE(current_audience_code, '') IN ('pending_questionnaire', 'operating', 'converted') THEN COALESCE(current_audience_code, 'pending_questionnaire')
                        ELSE
                            CASE
                                WHEN {_sqlite_normalized_conversion_pool_sql("current_pool")} = 'converted' THEN 'converted'
                                WHEN COALESCE(questionnaire_status, 'pending') = 'submitted' THEN 'operating'
                                ELSE 'pending_questionnaire'
                            END
                    END
                ELSE
                    CASE
                        WHEN {_sqlite_normalized_conversion_pool_sql("current_pool")} = 'converted' THEN 'converted'
                        WHEN COALESCE(questionnaire_status, 'pending') = 'submitted' THEN 'operating'
                        ELSE 'pending_questionnaire'
                    END
            END,
            COALESCE({"current_audience_entered_at" if "current_audience_entered_at" in member_columns else "''"}, ''),
            {_sqlite_normalized_conversion_pool_sql("last_active_pool")},
            COALESCE(joined_at, ''),
            COALESCE(last_ai_push_at, ''),
            COALESCE(ai_cooldown_until, ''),
            COALESCE(created_at, CURRENT_TIMESTAMP),
            COALESCE(updated_at, CURRENT_TIMESTAMP)
        FROM automation_member
        """
    )
    db.execute("DROP TABLE automation_member")
    db.execute("ALTER TABLE automation_member__new RENAME TO automation_member")


_LEGACY_AUTOMATION_MEMBER_FOLLOWUP_DECISION_COLUMN = "questionnaire" "_result"


def _sqlite_normalized_sop_pool_sql(column_name: str) -> str:
    return f"""
        CASE
            WHEN COALESCE({column_name}, '') IN ('pending_questionnaire', 'operating', 'converted') THEN COALESCE({column_name}, '')
            WHEN COALESCE({column_name}, '') = 'new_user' THEN 'pending_questionnaire'
            WHEN COALESCE({column_name}, '') IN ('inactive_normal', 'inactive_focus', 'active_normal', 'active_focus', 'silent') THEN 'operating'
            WHEN COALESCE({column_name}, '') = 'won' THEN 'converted'
            ELSE 'pending_questionnaire'
        END
    """


def _sqlite_legacy_compatible_sop_pool_check_values_sql() -> str:
    return "'pending_questionnaire', 'operating', 'converted'"


def _rebuild_sqlite_automation_sop_tables(db) -> None:
    db.execute("DROP TABLE IF EXISTS automation_sop_batch_item__new")
    db.execute("DROP TABLE IF EXISTS automation_sop_batch__new")
    db.execute("DROP TABLE IF EXISTS automation_sop_progress__new")
    db.execute("DROP TABLE IF EXISTS automation_sop_template__new")
    db.execute("DROP TABLE IF EXISTS automation_sop_pool_config__new")

    db.execute(
        f"""
        CREATE TABLE automation_sop_pool_config__new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pool_key TEXT NOT NULL UNIQUE CHECK (pool_key IN ({_sqlite_legacy_compatible_sop_pool_check_values_sql()})),
            enabled INTEGER NOT NULL DEFAULT 1,
            max_day_count INTEGER NOT NULL DEFAULT 5,
            send_time TEXT NOT NULL DEFAULT '09:00',
            timezone TEXT NOT NULL DEFAULT 'Asia/Shanghai',
            effective_start_at TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    if _sqlite_table_exists(db, "automation_sop_pool_config"):
        db.execute(
            f"""
            INSERT INTO automation_sop_pool_config__new (id, pool_key, enabled, max_day_count, send_time, timezone, effective_start_at, created_at, updated_at)
            SELECT
                id,
                {_sqlite_normalized_sop_pool_sql("pool_key")},
                COALESCE(enabled, 1),
                COALESCE(max_day_count, 5),
                COALESCE(send_time, '09:00'),
                COALESCE(timezone, 'Asia/Shanghai'),
                COALESCE(effective_start_at, ''),
                COALESCE(created_at, CURRENT_TIMESTAMP),
                COALESCE(updated_at, CURRENT_TIMESTAMP)
            FROM automation_sop_pool_config
            """
        )

    db.execute(
        f"""
        CREATE TABLE automation_sop_template__new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pool_key TEXT NOT NULL DEFAULT '' CHECK (pool_key IN ({_sqlite_legacy_compatible_sop_pool_check_values_sql()})),
            day_index INTEGER NOT NULL DEFAULT 1,
            content TEXT NOT NULL DEFAULT '',
            images_json TEXT NOT NULL DEFAULT '[]',
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    if _sqlite_table_exists(db, "automation_sop_template"):
        db.execute(
            f"""
            INSERT INTO automation_sop_template__new (id, pool_key, day_index, content, images_json, enabled, created_at, updated_at)
            SELECT
                id,
                {_sqlite_normalized_sop_pool_sql("pool_key")},
                COALESCE(day_index, 1),
                COALESCE(content, ''),
                COALESCE(images_json, '[]'),
                COALESCE(enabled, 1),
                COALESCE(created_at, CURRENT_TIMESTAMP),
                COALESCE(updated_at, CURRENT_TIMESTAMP)
            FROM automation_sop_template
            """
        )

    db.execute(
        f"""
        CREATE TABLE automation_sop_progress__new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL REFERENCES automation_member(id) ON DELETE CASCADE,
            pool_key TEXT NOT NULL DEFAULT '' CHECK (pool_key IN ({_sqlite_legacy_compatible_sop_pool_check_values_sql()})),
            first_entered_at TEXT NOT NULL DEFAULT '',
            last_entered_at TEXT NOT NULL DEFAULT '',
            sop_anchor_date TEXT NOT NULL DEFAULT '',
            first_effective_in_pool_at TEXT NOT NULL DEFAULT '',
            last_in_pool_at TEXT NOT NULL DEFAULT '',
            last_sent_day INTEGER NOT NULL DEFAULT 0,
            last_sent_at TEXT NOT NULL DEFAULT '',
            completed_at TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    if _sqlite_table_exists(db, "automation_sop_progress"):
        db.execute(
            f"""
            INSERT INTO automation_sop_progress__new (
                id, member_id, pool_key, first_entered_at, last_entered_at, sop_anchor_date,
                first_effective_in_pool_at, last_in_pool_at, last_sent_day, last_sent_at, completed_at, created_at, updated_at
            )
            SELECT
                id,
                member_id,
                {_sqlite_normalized_sop_pool_sql("pool_key")},
                COALESCE(first_entered_at, ''),
                COALESCE(last_entered_at, ''),
                COALESCE(sop_anchor_date, ''),
                COALESCE(first_effective_in_pool_at, ''),
                COALESCE(last_in_pool_at, ''),
                COALESCE(last_sent_day, 0),
                COALESCE(last_sent_at, ''),
                COALESCE(completed_at, ''),
                COALESCE(created_at, CURRENT_TIMESTAMP),
                COALESCE(updated_at, CURRENT_TIMESTAMP)
            FROM automation_sop_progress
            """
        )

    db.execute(
        f"""
        CREATE TABLE automation_sop_batch__new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pool_key TEXT NOT NULL DEFAULT '' CHECK (pool_key IN ({_sqlite_legacy_compatible_sop_pool_check_values_sql()})),
            day_index INTEGER NOT NULL DEFAULT 0,
            template_id INTEGER REFERENCES automation_sop_template(id) ON DELETE SET NULL,
            scheduled_for TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'empty',
            total_count INTEGER NOT NULL DEFAULT 0,
            success_count INTEGER NOT NULL DEFAULT 0,
            skipped_count INTEGER NOT NULL DEFAULT 0,
            failed_count INTEGER NOT NULL DEFAULT 0,
            summary_json TEXT NOT NULL DEFAULT '{{}}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    if _sqlite_table_exists(db, "automation_sop_batch"):
        db.execute(
            f"""
            INSERT INTO automation_sop_batch__new (
                id, pool_key, day_index, template_id, scheduled_for, status, total_count,
                success_count, skipped_count, failed_count, summary_json, created_at, updated_at
            )
            SELECT
                id,
                {_sqlite_normalized_sop_pool_sql("pool_key")},
                COALESCE(day_index, 0),
                template_id,
                COALESCE(scheduled_for, ''),
                COALESCE(status, 'empty'),
                COALESCE(total_count, 0),
                COALESCE(success_count, 0),
                COALESCE(skipped_count, 0),
                COALESCE(failed_count, 0),
                COALESCE(summary_json, '{{}}'),
                COALESCE(created_at, CURRENT_TIMESTAMP),
                COALESCE(updated_at, CURRENT_TIMESTAMP)
            FROM automation_sop_batch
            """
        )

    db.execute(
        f"""
        CREATE TABLE automation_sop_batch_item__new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id INTEGER NOT NULL REFERENCES automation_sop_batch(id) ON DELETE CASCADE,
            member_id INTEGER REFERENCES automation_member(id) ON DELETE CASCADE,
            pool_key TEXT NOT NULL DEFAULT '' CHECK (pool_key IN ({_sqlite_legacy_compatible_sop_pool_check_values_sql()})),
            day_index INTEGER NOT NULL DEFAULT 0,
            day_index_snapshot INTEGER NOT NULL DEFAULT 0,
            external_userid TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'skipped',
            error_message TEXT NOT NULL DEFAULT '',
            content_snapshot TEXT NOT NULL DEFAULT '',
            images_snapshot TEXT NOT NULL DEFAULT '[]',
            sent_record_id INTEGER REFERENCES user_ops_send_records(id) ON DELETE SET NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    if _sqlite_table_exists(db, "automation_sop_batch_item"):
        db.execute(
            f"""
            INSERT INTO automation_sop_batch_item__new (
                id, batch_id, member_id, pool_key, day_index, day_index_snapshot, external_userid,
                status, error_message, content_snapshot, images_snapshot, sent_record_id, created_at, updated_at
            )
            SELECT
                id,
                batch_id,
                member_id,
                {_sqlite_normalized_sop_pool_sql("pool_key")},
                COALESCE(day_index, 0),
                COALESCE(day_index_snapshot, 0),
                COALESCE(external_userid, ''),
                COALESCE(status, 'skipped'),
                COALESCE(error_message, ''),
                COALESCE(content_snapshot, ''),
                COALESCE(images_snapshot, '[]'),
                sent_record_id,
                COALESCE(created_at, CURRENT_TIMESTAMP),
                COALESCE(updated_at, CURRENT_TIMESTAMP)
            FROM automation_sop_batch_item
            """
        )

    for table_name in (
        "automation_sop_batch_item",
        "automation_sop_batch",
        "automation_sop_progress",
        "automation_sop_template",
        "automation_sop_pool_config",
    ):
        if _sqlite_table_exists(db, table_name):
            db.execute(f"DROP TABLE {table_name}")

    db.execute("ALTER TABLE automation_sop_pool_config__new RENAME TO automation_sop_pool_config")
    db.execute("ALTER TABLE automation_sop_template__new RENAME TO automation_sop_template")
    db.execute("ALTER TABLE automation_sop_progress__new RENAME TO automation_sop_progress")
    db.execute("ALTER TABLE automation_sop_batch__new RENAME TO automation_sop_batch")
    db.execute("ALTER TABLE automation_sop_batch_item__new RENAME TO automation_sop_batch_item")

    db.execute("CREATE INDEX IF NOT EXISTS idx_automation_sop_pool_config_updated ON automation_sop_pool_config (updated_at DESC, id DESC)")
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_sop_template_pool_day ON automation_sop_template (pool_key, day_index)")
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_sop_progress_member_pool ON automation_sop_progress (member_id, pool_key)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_automation_sop_progress_pool_day ON automation_sop_progress (pool_key, last_sent_day, updated_at DESC, id DESC)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_automation_sop_progress_pool_anchor ON automation_sop_progress (pool_key, sop_anchor_date, updated_at DESC, id DESC)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_automation_sop_batch_status_scheduled ON automation_sop_batch (status, scheduled_for, id DESC)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_automation_sop_batch_item_batch_created ON automation_sop_batch_item (batch_id, created_at DESC, id DESC)")


def _ensure_sqlite_customer_marketing_state_tables(db) -> None:
    current_columns = _sqlite_table_columns(db, "customer_marketing_state_current")
    if current_columns:
        create_sql = _sqlite_table_sql(db, "customer_marketing_state_current").upper()
        if "EXTERNAL_USERID TEXT NOT NULL UNIQUE" in create_sql:
            _rebuild_sqlite_customer_marketing_state_current_table(db)
            current_columns = _sqlite_table_columns(db, "customer_marketing_state_current")
        if "person_id" not in current_columns:
            db.execute(
                "ALTER TABLE customer_marketing_state_current ADD COLUMN person_id INTEGER REFERENCES people(id) ON DELETE SET NULL"
            )
        if "activated" not in current_columns:
            db.execute(
                "ALTER TABLE customer_marketing_state_current ADD COLUMN activated INTEGER NOT NULL DEFAULT 0"
            )
        if "converted" not in current_columns:
            db.execute(
                "ALTER TABLE customer_marketing_state_current ADD COLUMN converted INTEGER NOT NULL DEFAULT 0"
            )
        if "last_activation_at" not in current_columns:
            db.execute(
                "ALTER TABLE customer_marketing_state_current ADD COLUMN last_activation_at TEXT NOT NULL DEFAULT ''"
            )
        if "last_conversion_marked_at" not in current_columns:
            db.execute(
                "ALTER TABLE customer_marketing_state_current ADD COLUMN last_conversion_marked_at TEXT NOT NULL DEFAULT ''"
            )
        if "last_message_at" not in current_columns:
            db.execute(
                "ALTER TABLE customer_marketing_state_current ADD COLUMN last_message_at TEXT NOT NULL DEFAULT ''"
            )
        db.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_customer_marketing_state_current_person_id_non_null
            ON customer_marketing_state_current (person_id)
            WHERE person_id IS NOT NULL
            """
        )
        db.execute(
            """
            UPDATE customer_marketing_state_current
            SET external_userid = ''
            WHERE substr(COALESCE(external_userid, ''), 1, 7) = 'person:'
            """
        )

    history_columns = _sqlite_table_columns(db, "customer_marketing_state_history")
    if history_columns:
        if "person_id" not in history_columns:
            db.execute(
                "ALTER TABLE customer_marketing_state_history ADD COLUMN person_id INTEGER REFERENCES people(id) ON DELETE SET NULL"
            )
        if "activated" not in history_columns:
            db.execute(
                "ALTER TABLE customer_marketing_state_history ADD COLUMN activated INTEGER NOT NULL DEFAULT 0"
            )
        if "converted" not in history_columns:
            db.execute(
                "ALTER TABLE customer_marketing_state_history ADD COLUMN converted INTEGER NOT NULL DEFAULT 0"
            )
        if "exit_reason" not in history_columns:
            db.execute(
                "ALTER TABLE customer_marketing_state_history ADD COLUMN exit_reason TEXT NOT NULL DEFAULT ''"
            )
        if "last_activation_at" not in history_columns:
            db.execute(
                "ALTER TABLE customer_marketing_state_history ADD COLUMN last_activation_at TEXT NOT NULL DEFAULT ''"
            )
        if "last_conversion_marked_at" not in history_columns:
            db.execute(
                "ALTER TABLE customer_marketing_state_history ADD COLUMN last_conversion_marked_at TEXT NOT NULL DEFAULT ''"
            )
        if "last_message_at" not in history_columns:
            db.execute(
                "ALTER TABLE customer_marketing_state_history ADD COLUMN last_message_at TEXT NOT NULL DEFAULT ''"
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


def _ensure_sqlite_automation_conversion_tables(db) -> None:
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_channel (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            program_id INTEGER,
            channel_code TEXT NOT NULL UNIQUE,
            channel_name TEXT NOT NULL DEFAULT '',
            qr_url TEXT NOT NULL DEFAULT '',
            qr_ticket TEXT NOT NULL DEFAULT '',
            scene_value TEXT NOT NULL DEFAULT '',
            welcome_message TEXT NOT NULL DEFAULT '',
            auto_accept_friend INTEGER NOT NULL DEFAULT 0,
            entry_tag_id TEXT NOT NULL DEFAULT '',
            entry_tag_name TEXT NOT NULL DEFAULT '',
            entry_tag_group_name TEXT NOT NULL DEFAULT '',
            owner_staff_id TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'inactive',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    channel_columns = _sqlite_table_columns(db, "automation_channel")
    if "program_id" not in channel_columns:
        db.execute("ALTER TABLE automation_channel ADD COLUMN program_id INTEGER")
    if "welcome_message" not in channel_columns:
        db.execute("ALTER TABLE automation_channel ADD COLUMN welcome_message TEXT NOT NULL DEFAULT ''")
    if "auto_accept_friend" not in channel_columns:
        db.execute("ALTER TABLE automation_channel ADD COLUMN auto_accept_friend INTEGER NOT NULL DEFAULT 0")
    if "entry_tag_id" not in channel_columns:
        db.execute("ALTER TABLE automation_channel ADD COLUMN entry_tag_id TEXT NOT NULL DEFAULT ''")
    if "entry_tag_name" not in channel_columns:
        db.execute("ALTER TABLE automation_channel ADD COLUMN entry_tag_name TEXT NOT NULL DEFAULT ''")
    if "entry_tag_group_name" not in channel_columns:
        db.execute("ALTER TABLE automation_channel ADD COLUMN entry_tag_group_name TEXT NOT NULL DEFAULT ''")
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_member (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            external_contact_id TEXT NOT NULL DEFAULT '',
            phone TEXT NOT NULL DEFAULT '',
            master_customer_id INTEGER REFERENCES people(id) ON DELETE SET NULL,
            owner_staff_id TEXT NOT NULL DEFAULT '',
            in_pool INTEGER NOT NULL DEFAULT 0,
            current_pool TEXT NOT NULL DEFAULT 'removed',
            follow_type TEXT NOT NULL DEFAULT '',
            questionnaire_status TEXT NOT NULL DEFAULT 'pending',
            decision_source TEXT NOT NULL DEFAULT 'system',
            source_type TEXT NOT NULL DEFAULT 'system',
            source_channel_id INTEGER REFERENCES automation_channel(id) ON DELETE SET NULL,
            current_audience_code TEXT NOT NULL DEFAULT 'pending_questionnaire'
                CHECK (current_audience_code IN ('pending_questionnaire', 'operating', 'converted')),
            current_audience_entered_at TEXT NOT NULL DEFAULT '',
            last_active_pool TEXT NOT NULL DEFAULT '',
            joined_at TEXT NOT NULL DEFAULT '',
            last_ai_push_at TEXT NOT NULL DEFAULT '',
            ai_cooldown_until TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    member_columns = _sqlite_table_columns(db, "automation_member")
    member_table_sql = _sqlite_table_sql(db, "automation_member")
    if (
        _LEGACY_AUTOMATION_MEMBER_FOLLOWUP_DECISION_COLUMN in member_columns
        or "activation_status" in member_columns
        or "'new_user'" in member_table_sql
        or "'inactive_normal'" in member_table_sql
        or "'active_normal'" in member_table_sql
    ):
        _rebuild_sqlite_automation_member_table(db)
        member_columns = _sqlite_table_columns(db, "automation_member")
    if "current_audience_code" not in member_columns:
        db.execute(
            "ALTER TABLE automation_member ADD COLUMN current_audience_code TEXT NOT NULL DEFAULT 'pending_questionnaire'"
        )
    if "current_audience_entered_at" not in member_columns:
        db.execute("ALTER TABLE automation_member ADD COLUMN current_audience_entered_at TEXT NOT NULL DEFAULT ''")
    sop_pool_config_sql = _sqlite_table_sql(db, "automation_sop_pool_config")
    if "'new_user'" in sop_pool_config_sql or "'inactive_normal'" in sop_pool_config_sql or "'active_normal'" in sop_pool_config_sql:
        _rebuild_sqlite_automation_sop_tables(db)
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_event (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL REFERENCES automation_member(id) ON DELETE CASCADE,
            action TEXT NOT NULL DEFAULT '',
            operator_type TEXT NOT NULL DEFAULT 'system',
            operator_id TEXT NOT NULL DEFAULT '',
            before_snapshot TEXT NOT NULL DEFAULT '{}',
            after_snapshot TEXT NOT NULL DEFAULT '{}',
            remark TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_ai_push_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL REFERENCES automation_member(id) ON DELETE CASCADE,
            scene TEXT NOT NULL DEFAULT 'sidebar_script',
            request_payload TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'accepted',
            request_id TEXT NOT NULL DEFAULT '',
            error_message TEXT NOT NULL DEFAULT '',
            pushed_at TEXT NOT NULL DEFAULT '',
            cooldown_until TEXT NOT NULL DEFAULT ''
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_message_activity_sync_run (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trigger_source TEXT NOT NULL DEFAULT 'manual',
            operator_type TEXT NOT NULL DEFAULT 'system',
            operator_id TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'success',
            candidate_count INTEGER NOT NULL DEFAULT 0,
            matched_count INTEGER NOT NULL DEFAULT 0,
            updated_count INTEGER NOT NULL DEFAULT 0,
            skipped_ambiguous_count INTEGER NOT NULL DEFAULT 0,
            skipped_unmatched_count INTEGER NOT NULL DEFAULT 0,
            skipped_missing_phone_count INTEGER NOT NULL DEFAULT 0,
            focus_count INTEGER NOT NULL DEFAULT 0,
            normal_count INTEGER NOT NULL DEFAULT 0,
            error_message TEXT NOT NULL DEFAULT '',
            summary_json TEXT NOT NULL DEFAULT '{}',
            started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            finished_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_message_activity_sync_item (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL REFERENCES automation_message_activity_sync_run(id) ON DELETE CASCADE,
            member_id INTEGER REFERENCES automation_member(id) ON DELETE CASCADE,
            external_contact_id TEXT NOT NULL DEFAULT '',
            phone TEXT NOT NULL DEFAULT '',
            phone_prefix3 TEXT NOT NULL DEFAULT '',
            phone_last4 TEXT NOT NULL DEFAULT '',
            phone_match_key TEXT NOT NULL DEFAULT '',
            message_count INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'updated',
            detail TEXT NOT NULL DEFAULT '',
            before_snapshot TEXT NOT NULL DEFAULT '{}',
            after_snapshot TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_reply_monitor_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            config_key TEXT NOT NULL UNIQUE DEFAULT 'default',
            enabled INTEGER NOT NULL DEFAULT 0,
            last_capture_cursor INTEGER NOT NULL DEFAULT 0,
            last_capture_at TEXT NOT NULL DEFAULT '',
            last_capture_status TEXT NOT NULL DEFAULT '',
            last_capture_summary_json TEXT NOT NULL DEFAULT '{}',
            last_dispatch_at TEXT NOT NULL DEFAULT '',
            last_dispatch_status TEXT NOT NULL DEFAULT '',
            last_dispatch_summary_json TEXT NOT NULL DEFAULT '{}',
            last_error TEXT NOT NULL DEFAULT '',
            quiet_hours_start TEXT NOT NULL DEFAULT '23:00',
            quiet_hours_end TEXT NOT NULL DEFAULT '09:00',
            dispatch_interval_seconds INTEGER NOT NULL DEFAULT 30,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_reply_monitor_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER REFERENCES automation_member(id) ON DELETE SET NULL,
            external_userid TEXT NOT NULL DEFAULT '',
            owner_userid TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            message_ids_json TEXT NOT NULL DEFAULT '[]',
            message_count INTEGER NOT NULL DEFAULT 0,
            first_inbound_at TEXT NOT NULL DEFAULT '',
            last_inbound_at TEXT NOT NULL DEFAULT '',
            not_before TEXT NOT NULL DEFAULT '',
            last_dispatch_at TEXT NOT NULL DEFAULT '',
            error_message TEXT NOT NULL DEFAULT '',
            payload_snapshot_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_laohuang_chat_job (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            queue_id INTEGER REFERENCES automation_reply_monitor_queue(id) ON DELETE SET NULL,
            member_id INTEGER REFERENCES automation_member(id) ON DELETE SET NULL,
            external_contact_id TEXT NOT NULL DEFAULT '',
            phone TEXT NOT NULL DEFAULT '',
            external_message_id TEXT NOT NULL DEFAULT '',
            external_session_id TEXT NOT NULL DEFAULT '',
            laohuang_task_id TEXT NOT NULL DEFAULT '',
            request_payload_json TEXT NOT NULL DEFAULT '{}',
            accepted_payload_json TEXT NOT NULL DEFAULT '{}',
            callback_payload_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'created',
            reply_text TEXT NOT NULL DEFAULT '',
            error_code TEXT NOT NULL DEFAULT '',
            error_message TEXT NOT NULL DEFAULT '',
            send_channel TEXT NOT NULL DEFAULT 'private_message',
            send_record_id INTEGER REFERENCES user_ops_send_records(id) ON DELETE SET NULL,
            send_result_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            finished_at TEXT NOT NULL DEFAULT ''
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_focus_send_batch (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stage_key TEXT NOT NULL DEFAULT '',
            pool_key TEXT NOT NULL DEFAULT '',
            operator_type TEXT NOT NULL DEFAULT 'user',
            operator_id TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            total_count INTEGER NOT NULL DEFAULT 0,
            sent_count INTEGER NOT NULL DEFAULT 0,
            failed_count INTEGER NOT NULL DEFAULT 0,
            skipped_count INTEGER NOT NULL DEFAULT 0,
            cancelled_count INTEGER NOT NULL DEFAULT 0,
            next_run_at TEXT NOT NULL DEFAULT '',
            last_run_at TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            finished_at TEXT NOT NULL DEFAULT ''
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_focus_send_batch_item (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id INTEGER NOT NULL REFERENCES automation_focus_send_batch(id) ON DELETE CASCADE,
            member_id INTEGER REFERENCES automation_member(id) ON DELETE SET NULL,
            external_contact_id TEXT NOT NULL DEFAULT '',
            phone TEXT NOT NULL DEFAULT '',
            position_index INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'pending',
            detail TEXT NOT NULL DEFAULT '',
            result_payload TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            started_at TEXT NOT NULL DEFAULT '',
            finished_at TEXT NOT NULL DEFAULT ''
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_touch_delivery_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            program_code TEXT NOT NULL DEFAULT 'signup_conversion_v1',
            touch_surface TEXT NOT NULL DEFAULT '',
            rule_key TEXT NOT NULL DEFAULT '',
            member_id INTEGER REFERENCES automation_member(id) ON DELETE SET NULL,
            external_contact_id TEXT NOT NULL DEFAULT '',
            source_batch_id INTEGER,
            source_item_id INTEGER,
            send_record_id INTEGER REFERENCES user_ops_send_records(id) ON DELETE SET NULL,
            status TEXT NOT NULL DEFAULT 'claimed'
                CHECK (status IN ('claimed', 'sent', 'failed', 'skipped', 'cancelled')),
            detail TEXT NOT NULL DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            claimed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            sent_at TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        f"""
        CREATE TABLE IF NOT EXISTS automation_sop_pool_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pool_key TEXT NOT NULL UNIQUE CHECK (pool_key IN ({_sqlite_legacy_compatible_sop_pool_check_values_sql()})),
            enabled INTEGER NOT NULL DEFAULT 1,
            max_day_count INTEGER NOT NULL DEFAULT 5,
            send_time TEXT NOT NULL DEFAULT '09:00',
            timezone TEXT NOT NULL DEFAULT 'Asia/Shanghai',
            effective_start_at TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        f"""
        CREATE TABLE IF NOT EXISTS automation_sop_template (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pool_key TEXT NOT NULL DEFAULT '' CHECK (pool_key IN ({_sqlite_legacy_compatible_sop_pool_check_values_sql()})),
            day_index INTEGER NOT NULL DEFAULT 1,
            content TEXT NOT NULL DEFAULT '',
            images_json TEXT NOT NULL DEFAULT '[]',
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        f"""
        CREATE TABLE IF NOT EXISTS automation_sop_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL REFERENCES automation_member(id) ON DELETE CASCADE,
            pool_key TEXT NOT NULL DEFAULT '' CHECK (pool_key IN ({_sqlite_legacy_compatible_sop_pool_check_values_sql()})),
            first_entered_at TEXT NOT NULL DEFAULT '',
            last_entered_at TEXT NOT NULL DEFAULT '',
            sop_anchor_date TEXT NOT NULL DEFAULT '',
            first_effective_in_pool_at TEXT NOT NULL DEFAULT '',
            last_in_pool_at TEXT NOT NULL DEFAULT '',
            last_sent_day INTEGER NOT NULL DEFAULT 0,
            last_sent_at TEXT NOT NULL DEFAULT '',
            completed_at TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        f"""
        CREATE TABLE IF NOT EXISTS automation_sop_batch (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pool_key TEXT NOT NULL DEFAULT '' CHECK (pool_key IN ({_sqlite_legacy_compatible_sop_pool_check_values_sql()})),
            day_index INTEGER NOT NULL DEFAULT 0,
            template_id INTEGER REFERENCES automation_sop_template(id) ON DELETE SET NULL,
            scheduled_for TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'empty',
            total_count INTEGER NOT NULL DEFAULT 0,
            success_count INTEGER NOT NULL DEFAULT 0,
            skipped_count INTEGER NOT NULL DEFAULT 0,
            failed_count INTEGER NOT NULL DEFAULT 0,
            summary_json TEXT NOT NULL DEFAULT '{{}}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        f"""
        CREATE TABLE IF NOT EXISTS automation_sop_batch_item (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id INTEGER NOT NULL REFERENCES automation_sop_batch(id) ON DELETE CASCADE,
            member_id INTEGER REFERENCES automation_member(id) ON DELETE CASCADE,
            pool_key TEXT NOT NULL DEFAULT '' CHECK (pool_key IN ({_sqlite_legacy_compatible_sop_pool_check_values_sql()})),
            day_index INTEGER NOT NULL DEFAULT 0,
            day_index_snapshot INTEGER NOT NULL DEFAULT 0,
            external_userid TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'skipped',
            error_message TEXT NOT NULL DEFAULT '',
            content_snapshot TEXT NOT NULL DEFAULT '',
            images_snapshot TEXT NOT NULL DEFAULT '[]',
            sent_record_id INTEGER REFERENCES user_ops_send_records(id) ON DELETE SET NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_member_external_non_empty
        ON automation_member (external_contact_id)
        WHERE external_contact_id <> ''
        """
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_automation_member_phone ON automation_member (phone)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_automation_member_pool ON automation_member (current_pool, in_pool)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_automation_member_owner ON automation_member (owner_staff_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_automation_member_channel ON automation_member (source_channel_id)")
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_member_audience ON automation_member (current_audience_code, updated_at DESC, id DESC)"
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_automation_event_member_created ON automation_event (member_id, created_at DESC, id DESC)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_automation_event_action_created ON automation_event (action, created_at DESC, id DESC)")
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_ai_push_log_member_pushed ON automation_ai_push_log (member_id, pushed_at DESC, id DESC)"
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_automation_ai_push_log_status ON automation_ai_push_log (status, pushed_at DESC, id DESC)")
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_message_activity_sync_run_finished ON automation_message_activity_sync_run (finished_at DESC, id DESC)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_message_activity_sync_run_status ON automation_message_activity_sync_run (status, finished_at DESC, id DESC)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_message_activity_sync_item_run ON automation_message_activity_sync_item (run_id, id ASC)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_message_activity_sync_item_status ON automation_message_activity_sync_item (status, created_at DESC, id DESC)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_message_activity_sync_item_last4 ON automation_message_activity_sync_item (phone_last4, created_at DESC, id DESC)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_message_activity_sync_item_match_key ON automation_message_activity_sync_item (phone_match_key, created_at DESC, id DESC)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_reply_monitor_config_updated ON automation_reply_monitor_config (updated_at DESC, id DESC)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_reply_monitor_queue_status_due ON automation_reply_monitor_queue (status, not_before, id ASC)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_reply_monitor_queue_external_updated ON automation_reply_monitor_queue (external_userid, updated_at DESC, id DESC)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_reply_monitor_queue_member_updated ON automation_reply_monitor_queue (member_id, updated_at DESC, id DESC)"
    )
    db.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_reply_monitor_queue_active_external
        ON automation_reply_monitor_queue (external_userid)
        WHERE external_userid <> ''
          AND status IN ('pending', 'deferred_quiet_hours', 'paused')
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_agent_prompt_registry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_code TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL DEFAULT '',
            prompt_text TEXT NOT NULL DEFAULT '',
            enabled INTEGER NOT NULL DEFAULT 1,
            version INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_agent_prompt_registry_enabled
        ON automation_agent_prompt_registry (enabled, updated_at DESC, id DESC)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_agent_prompt_registry_updated
        ON automation_agent_prompt_registry (updated_at DESC, id DESC)
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_agent_llm_call_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_code TEXT NOT NULL DEFAULT '',
            model_name TEXT NOT NULL DEFAULT '',
            request_id TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT '',
            latency_ms INTEGER NOT NULL DEFAULT 0,
            error_message TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_agent_llm_call_log_agent_created
        ON automation_agent_llm_call_log (agent_code, created_at DESC, id DESC)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_agent_llm_call_log_status_created
        ON automation_agent_llm_call_log (status, created_at DESC, id DESC)
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_profile_segment_template (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            program_id INTEGER,
            template_code TEXT NOT NULL UNIQUE,
            template_name TEXT NOT NULL DEFAULT '',
            questionnaire_id INTEGER REFERENCES questionnaires(id) ON DELETE SET NULL,
            segmentation_question_id INTEGER REFERENCES questionnaire_questions(id) ON DELETE SET NULL,
            description TEXT NOT NULL DEFAULT '',
            enabled INTEGER NOT NULL DEFAULT 1,
            version INTEGER NOT NULL DEFAULT 1,
            created_by TEXT NOT NULL DEFAULT '',
            updated_by TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_profile_segment_category (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            template_id INTEGER NOT NULL REFERENCES automation_profile_segment_template(id) ON DELETE CASCADE,
            category_key TEXT NOT NULL DEFAULT '',
            category_name TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            sort_order INTEGER NOT NULL DEFAULT 0,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_profile_segment_option_mapping (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            template_id INTEGER NOT NULL REFERENCES automation_profile_segment_template(id) ON DELETE CASCADE,
            category_id INTEGER NOT NULL REFERENCES automation_profile_segment_category(id) ON DELETE CASCADE,
            question_id INTEGER NOT NULL REFERENCES questionnaire_questions(id) ON DELETE CASCADE,
            option_id INTEGER NOT NULL REFERENCES questionnaire_options(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_workflow (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workflow_code TEXT NOT NULL UNIQUE,
            workflow_name TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft', 'active', 'paused', 'archived')),
            segmentation_basis TEXT NOT NULL DEFAULT 'none'
                CHECK (segmentation_basis IN ('none', 'profile', 'behavior')),
            generation_mode TEXT NOT NULL DEFAULT 'manual_layered'
                CHECK (generation_mode IN ('manual_layered', 'auto_layered_rewrite', 'personalized_single')),
            profile_segment_template_id INTEGER REFERENCES automation_profile_segment_template(id) ON DELETE SET NULL,
            behavior_tier_scheme TEXT NOT NULL DEFAULT 'fixed_v1',
            fallback_to_standard_content INTEGER NOT NULL DEFAULT 1,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_by TEXT NOT NULL DEFAULT '',
            updated_by TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_workflow_audience (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workflow_id INTEGER NOT NULL REFERENCES automation_workflow(id) ON DELETE CASCADE,
            audience_code TEXT NOT NULL
                CHECK (audience_code IN ('pending_questionnaire', 'operating', 'converted')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_member_audience_entry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL REFERENCES automation_member(id) ON DELETE CASCADE,
            audience_code TEXT NOT NULL
                CHECK (audience_code IN ('pending_questionnaire', 'operating', 'converted')),
            entered_at TEXT NOT NULL DEFAULT '',
            exited_at TEXT NOT NULL DEFAULT '',
            is_current INTEGER NOT NULL DEFAULT 1,
            entry_source TEXT NOT NULL DEFAULT 'system',
            entry_reason TEXT NOT NULL DEFAULT '',
            source_snapshot_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_workflow_agent_binding (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workflow_id INTEGER NOT NULL REFERENCES automation_workflow(id) ON DELETE CASCADE,
            node_id INTEGER REFERENCES automation_workflow_node(id) ON DELETE CASCADE,
            binding_scope TEXT NOT NULL DEFAULT 'default'
                CHECK (binding_scope IN ('default', 'profile_category', 'behavior_tier', 'personalized')),
            segment_key TEXT NOT NULL DEFAULT '',
            agent_code TEXT NOT NULL REFERENCES automation_agent_config(agent_code) ON DELETE CASCADE,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_workflow_node (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workflow_id INTEGER NOT NULL REFERENCES automation_workflow(id) ON DELETE CASCADE,
            node_code TEXT NOT NULL DEFAULT '',
            node_name TEXT NOT NULL DEFAULT '',
            target_audience_code TEXT NOT NULL
                CHECK (target_audience_code IN ('pending_questionnaire', 'operating', 'converted')),
            trigger_mode TEXT NOT NULL DEFAULT 'scheduled'
                CHECK (trigger_mode IN ('scheduled', 'daily_recurring', 'audience_entered')),
            day_offset INTEGER NOT NULL DEFAULT 1,
            send_time TEXT NOT NULL DEFAULT '09:00',
            timezone TEXT NOT NULL DEFAULT 'Asia/Shanghai',
            position_index INTEGER NOT NULL DEFAULT 0,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    workflow_node_columns = _sqlite_table_columns(db, "automation_workflow_node")
    if "trigger_mode" not in workflow_node_columns:
        db.execute("ALTER TABLE automation_workflow_node ADD COLUMN trigger_mode TEXT NOT NULL DEFAULT 'scheduled'")
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_workflow_node_content (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_id INTEGER NOT NULL UNIQUE REFERENCES automation_workflow_node(id) ON DELETE CASCADE,
            standard_content_text TEXT NOT NULL DEFAULT '',
            standard_content_payload_json TEXT NOT NULL DEFAULT '{}',
            fallback_to_standard_content INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_workflow_node_content_variant (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_content_id INTEGER NOT NULL REFERENCES automation_workflow_node_content(id) ON DELETE CASCADE,
            variant_scope TEXT NOT NULL
                CHECK (variant_scope IN ('profile_category', 'behavior_tier', 'personalized')),
            segment_key TEXT NOT NULL DEFAULT '',
            content_text TEXT NOT NULL DEFAULT '',
            content_payload_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_workflow_execution (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            execution_id TEXT NOT NULL UNIQUE,
            workflow_id INTEGER REFERENCES automation_workflow(id) ON DELETE SET NULL,
            node_id INTEGER REFERENCES automation_workflow_node(id) ON DELETE SET NULL,
            trigger_type TEXT NOT NULL DEFAULT 'scheduled_poll'
                CHECK (trigger_type IN ('scheduled_poll', 'daily_recurring_poll', 'manual_replay', 'debug')),
            audience_code TEXT NOT NULL DEFAULT 'pending_questionnaire'
                CHECK (audience_code IN ('pending_questionnaire', 'operating', 'converted')),
            scheduled_for TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'running', 'finished', 'partial_failed', 'failed')),
            total_count INTEGER NOT NULL DEFAULT 0,
            success_count INTEGER NOT NULL DEFAULT 0,
            skipped_count INTEGER NOT NULL DEFAULT 0,
            failed_count INTEGER NOT NULL DEFAULT 0,
            summary_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            finished_at TEXT NOT NULL DEFAULT ''
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_workflow_execution_item (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            execution_id INTEGER NOT NULL REFERENCES automation_workflow_execution(id) ON DELETE CASCADE,
            workflow_id INTEGER REFERENCES automation_workflow(id) ON DELETE SET NULL,
            node_id INTEGER REFERENCES automation_workflow_node(id) ON DELETE SET NULL,
            member_id INTEGER REFERENCES automation_member(id) ON DELETE SET NULL,
            audience_entry_id INTEGER REFERENCES automation_member_audience_entry(id) ON DELETE SET NULL,
            external_contact_id TEXT NOT NULL DEFAULT '',
            rendered_content_text TEXT NOT NULL DEFAULT '',
            content_snapshot_json TEXT NOT NULL DEFAULT '{}',
            agent_code TEXT NOT NULL DEFAULT '',
            agent_run_id TEXT NOT NULL DEFAULT '',
            agent_output_id TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'prepared', 'sent', 'skipped', 'failed')),
            error_message TEXT NOT NULL DEFAULT '',
            send_record_id INTEGER REFERENCES user_ops_send_records(id) ON DELETE SET NULL,
            sent_at TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_profile_segment_template_enabled ON automation_profile_segment_template (enabled, updated_at DESC, id DESC)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_profile_segment_template_program ON automation_profile_segment_template (program_id, enabled, updated_at DESC, id DESC)"
    )
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_profile_segment_category_template_key ON automation_profile_segment_category (template_id, category_key)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_profile_segment_category_template_sort ON automation_profile_segment_category (template_id, sort_order ASC, id ASC)"
    )
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_profile_segment_option_mapping_unique ON automation_profile_segment_option_mapping (category_id, question_id, option_id)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_profile_segment_option_mapping_template ON automation_profile_segment_option_mapping (template_id, question_id, option_id, id DESC)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_workflow_status ON automation_workflow (status, updated_at DESC, id DESC)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_workflow_enabled ON automation_workflow (enabled, updated_at DESC, id DESC)"
    )
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_workflow_audience_unique ON automation_workflow_audience (workflow_id, audience_code)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_workflow_audience_code ON automation_workflow_audience (audience_code, workflow_id)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_member_audience_entry_member_entered ON automation_member_audience_entry (member_id, entered_at DESC, id DESC)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_member_audience_entry_audience_current ON automation_member_audience_entry (audience_code, is_current, entered_at DESC, id DESC)"
    )
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_member_audience_entry_current ON automation_member_audience_entry (member_id) WHERE is_current = 1"
    )
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_workflow_agent_binding_unique ON automation_workflow_agent_binding (workflow_id, COALESCE(node_id, 0), binding_scope, segment_key)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_workflow_agent_binding_agent ON automation_workflow_agent_binding (agent_code, updated_at DESC, id DESC)"
    )
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_workflow_node_code ON automation_workflow_node (workflow_id, node_code)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_workflow_node_position ON automation_workflow_node (workflow_id, position_index ASC, id ASC)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_workflow_node_schedule ON automation_workflow_node (target_audience_code, day_offset, send_time, enabled, id ASC)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_workflow_node_trigger ON automation_workflow_node (target_audience_code, trigger_mode, enabled, id ASC)"
    )
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_workflow_node_content_variant_unique ON automation_workflow_node_content_variant (node_content_id, variant_scope, segment_key)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_workflow_node_content_variant_scope ON automation_workflow_node_content_variant (variant_scope, segment_key, id DESC)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_workflow_execution_due ON automation_workflow_execution (status, scheduled_for, id DESC)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_workflow_execution_workflow ON automation_workflow_execution (workflow_id, created_at DESC, id DESC)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_workflow_execution_item_execution ON automation_workflow_execution_item (execution_id, id ASC)"
    )
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_workflow_execution_item_member_unique ON automation_workflow_execution_item (execution_id, member_id)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_workflow_execution_item_member ON automation_workflow_execution_item (member_id, created_at DESC, id DESC)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_workflow_execution_item_send_record ON automation_workflow_execution_item (send_record_id, created_at DESC, id DESC)"
    )
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_laohuang_chat_job_external_message ON automation_laohuang_chat_job (external_message_id) WHERE external_message_id <> ''"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_laohuang_chat_job_task ON automation_laohuang_chat_job (laohuang_task_id, id DESC)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_laohuang_chat_job_status_updated ON automation_laohuang_chat_job (status, updated_at DESC, id DESC)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_laohuang_chat_job_queue ON automation_laohuang_chat_job (queue_id, id DESC)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_focus_send_batch_stage_status ON automation_focus_send_batch (stage_key, status, id DESC)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_focus_send_batch_due ON automation_focus_send_batch (status, next_run_at, id ASC)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_focus_send_batch_item_batch_position ON automation_focus_send_batch_item (batch_id, position_index ASC, id ASC)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_focus_send_batch_item_status ON automation_focus_send_batch_item (status, updated_at DESC, id DESC)"
    )
    db.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_touch_delivery_active
        ON automation_touch_delivery_log (program_code, touch_surface, rule_key, external_contact_id)
        WHERE external_contact_id <> '' AND status IN ('claimed', 'sent')
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_touch_delivery_external
        ON automation_touch_delivery_log (external_contact_id, updated_at DESC, id DESC)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_touch_delivery_source
        ON automation_touch_delivery_log (touch_surface, source_batch_id, source_item_id, id DESC)
        """
    )
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_sop_template_pool_day ON automation_sop_template (pool_key, day_index)"
    )
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_sop_progress_member_pool ON automation_sop_progress (member_id, pool_key)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_sop_pool_config_updated ON automation_sop_pool_config (updated_at DESC, id DESC)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_sop_progress_pool_day ON automation_sop_progress (pool_key, last_sent_day, updated_at DESC, id DESC)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_sop_progress_pool_anchor ON automation_sop_progress (pool_key, sop_anchor_date, updated_at DESC, id DESC)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_sop_batch_status_scheduled ON automation_sop_batch (status, scheduled_for, id DESC)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_sop_batch_item_batch_created ON automation_sop_batch_item (batch_id, id ASC)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_sop_batch_item_member_day_snapshot ON automation_sop_batch_item (member_id, pool_key, day_index_snapshot, id DESC)"
    )
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_sop_batch_item_member_pool_day_success ON automation_sop_batch_item (member_id, pool_key, day_index) WHERE status = 'success'"
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_automation_channel_status ON automation_channel (status, updated_at DESC, id DESC)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_automation_channel_program ON automation_channel (program_id, updated_at DESC, id DESC)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_automation_channel_scene ON automation_channel (scene_value)")


def _ensure_sqlite_automation_program_tables(db) -> None:
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_program (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            program_code TEXT NOT NULL UNIQUE,
            program_name TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft', 'active', 'paused', 'archived')),
            config_json TEXT NOT NULL DEFAULT '{}',
            created_by TEXT NOT NULL DEFAULT '',
            updated_by TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_program_status ON automation_program (status, updated_at DESC, id DESC)"
    )
    workflow_columns = _sqlite_table_columns(db, "automation_workflow")
    if workflow_columns and "program_id" not in workflow_columns:
        db.execute("ALTER TABLE automation_workflow ADD COLUMN program_id INTEGER REFERENCES automation_program(id) ON DELETE SET NULL")
    execution_columns = _sqlite_table_columns(db, "automation_workflow_execution")
    if execution_columns and "program_id" not in execution_columns:
        db.execute(
            "ALTER TABLE automation_workflow_execution ADD COLUMN program_id INTEGER REFERENCES automation_program(id) ON DELETE SET NULL"
        )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_workflow_program ON automation_workflow (program_id, status, updated_at DESC, id DESC)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_workflow_execution_program ON automation_workflow_execution (program_id, created_at DESC, id DESC)"
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
            '{"flow_design_source":"legacy_singleton"}',
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
    channel_columns = _sqlite_table_columns(db, "automation_channel")
    if channel_columns and "program_id" in channel_columns:
        db.execute("UPDATE automation_channel SET program_id = ? WHERE program_id IS NULL", (default_program_id,))
    profile_template_columns = _sqlite_table_columns(db, "automation_profile_segment_template")
    if profile_template_columns and "program_id" in profile_template_columns:
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



def _ensure_sqlite_automation_sop_v2_columns(db) -> None:
    pool_config_columns = _sqlite_table_columns(db, "automation_sop_pool_config")
    if "effective_start_at" not in pool_config_columns:
        db.execute("ALTER TABLE automation_sop_pool_config ADD COLUMN effective_start_at TEXT NOT NULL DEFAULT ''")

    progress_columns = _sqlite_table_columns(db, "automation_sop_progress")
    if "sop_anchor_date" not in progress_columns:
        db.execute("ALTER TABLE automation_sop_progress ADD COLUMN sop_anchor_date TEXT NOT NULL DEFAULT ''")
    if "first_effective_in_pool_at" not in progress_columns:
        db.execute("ALTER TABLE automation_sop_progress ADD COLUMN first_effective_in_pool_at TEXT NOT NULL DEFAULT ''")
    if "last_in_pool_at" not in progress_columns:
        db.execute("ALTER TABLE automation_sop_progress ADD COLUMN last_in_pool_at TEXT NOT NULL DEFAULT ''")

    batch_item_columns = _sqlite_table_columns(db, "automation_sop_batch_item")
    if "day_index_snapshot" not in batch_item_columns:
        db.execute("ALTER TABLE automation_sop_batch_item ADD COLUMN day_index_snapshot INTEGER NOT NULL DEFAULT 0")
    if "content_snapshot" not in batch_item_columns:
        db.execute("ALTER TABLE automation_sop_batch_item ADD COLUMN content_snapshot TEXT NOT NULL DEFAULT ''")
    if "images_snapshot" not in batch_item_columns:
        db.execute("ALTER TABLE automation_sop_batch_item ADD COLUMN images_snapshot TEXT NOT NULL DEFAULT '[]'")

    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_sop_progress_pool_anchor ON automation_sop_progress (pool_key, sop_anchor_date, updated_at DESC, id DESC)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_sop_batch_item_member_day_snapshot ON automation_sop_batch_item (member_id, pool_key, day_index_snapshot, id DESC)"
    )


def _migrate_sqlite_conversion_agent_pools_to_bindings(db) -> None:
    if not _sqlite_table_exists(db, "automation_workflow_agent_binding"):
        return
    if _sqlite_table_exists(db, "automation_workflow_agent_pool_binding") and _sqlite_table_exists(db, "automation_agent_pool_agent"):
        db.execute(
            """
            INSERT OR REPLACE INTO automation_workflow_agent_binding (
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
                COALESCE(
                    (
                        SELECT member.agent_code
                        FROM automation_agent_pool_agent member
                        WHERE member.agent_pool_id = binding.agent_pool_id
                        ORDER BY CASE WHEN lower(COALESCE(member.role_code, '')) = 'primary' THEN 0 ELSE 1 END,
                                 member.position_index ASC,
                                 member.id ASC
                        LIMIT 1
                    ),
                    ''
                ) AS agent_code,
                COALESCE(binding.created_at, CURRENT_TIMESTAMP),
                COALESCE(binding.updated_at, CURRENT_TIMESTAMP)
            FROM automation_workflow_agent_pool_binding binding
            WHERE COALESCE(
                (
                    SELECT member.agent_code
                    FROM automation_agent_pool_agent member
                    WHERE member.agent_pool_id = binding.agent_pool_id
                    ORDER BY CASE WHEN lower(COALESCE(member.role_code, '')) = 'primary' THEN 0 ELSE 1 END,
                             member.position_index ASC,
                             member.id ASC
                    LIMIT 1
                ),
                ''
            ) <> ''
            """
        )

    execution_item_columns = _sqlite_table_columns(db, "automation_workflow_execution_item")
    if execution_item_columns and ("agent_pool_id" in execution_item_columns or "agent_code" not in execution_item_columns):
        agent_code_sql = (
            """
            CASE
                WHEN TRIM(COALESCE(agent_code, '')) <> '' THEN agent_code
                ELSE COALESCE(
                    (
                        SELECT member.agent_code
                        FROM automation_agent_pool_agent member
                        WHERE member.agent_pool_id = automation_workflow_execution_item.agent_pool_id
                        ORDER BY CASE WHEN lower(COALESCE(member.role_code, '')) = 'primary' THEN 0 ELSE 1 END,
                                 member.position_index ASC,
                                 member.id ASC
                        LIMIT 1
                    ),
                    ''
                )
            END
            """
            if "agent_code" in execution_item_columns and "agent_pool_id" in execution_item_columns
            else (
                """
                COALESCE(
                    (
                        SELECT member.agent_code
                        FROM automation_agent_pool_agent member
                        WHERE member.agent_pool_id = automation_workflow_execution_item.agent_pool_id
                        ORDER BY CASE WHEN lower(COALESCE(member.role_code, '')) = 'primary' THEN 0 ELSE 1 END,
                                 member.position_index ASC,
                                 member.id ASC
                        LIMIT 1
                    ),
                    ''
                )
                """
                if "agent_pool_id" in execution_item_columns
                else "COALESCE(agent_code, '')"
            )
        )
        db.execute("PRAGMA foreign_keys = OFF")
        db.execute("DROP TABLE IF EXISTS automation_workflow_execution_item__new")
        db.execute(
            """
            CREATE TABLE automation_workflow_execution_item__new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                execution_id INTEGER NOT NULL REFERENCES automation_workflow_execution(id) ON DELETE CASCADE,
                workflow_id INTEGER REFERENCES automation_workflow(id) ON DELETE SET NULL,
                node_id INTEGER REFERENCES automation_workflow_node(id) ON DELETE SET NULL,
                member_id INTEGER REFERENCES automation_member(id) ON DELETE SET NULL,
                audience_entry_id INTEGER REFERENCES automation_member_audience_entry(id) ON DELETE SET NULL,
                external_contact_id TEXT NOT NULL DEFAULT '',
                rendered_content_text TEXT NOT NULL DEFAULT '',
                content_snapshot_json TEXT NOT NULL DEFAULT '{}',
                agent_code TEXT NOT NULL DEFAULT '',
                agent_run_id TEXT NOT NULL DEFAULT '',
                agent_output_id TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'prepared', 'sent', 'skipped', 'failed')),
                error_message TEXT NOT NULL DEFAULT '',
                send_record_id INTEGER REFERENCES user_ops_send_records(id) ON DELETE SET NULL,
                sent_at TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        db.execute(
            f"""
            INSERT INTO automation_workflow_execution_item__new (
                id,
                execution_id,
                workflow_id,
                node_id,
                member_id,
                audience_entry_id,
                external_contact_id,
                rendered_content_text,
                content_snapshot_json,
                agent_code,
                agent_run_id,
                agent_output_id,
                status,
                error_message,
                send_record_id,
                sent_at,
                created_at,
                updated_at
            )
            SELECT
                id,
                execution_id,
                workflow_id,
                node_id,
                member_id,
                audience_entry_id,
                COALESCE(external_contact_id, ''),
                COALESCE(rendered_content_text, ''),
                COALESCE(content_snapshot_json, '{{}}'),
                {agent_code_sql},
                COALESCE(agent_run_id, ''),
                COALESCE(agent_output_id, ''),
                COALESCE(status, 'pending'),
                COALESCE(error_message, ''),
                send_record_id,
                COALESCE(sent_at, ''),
                COALESCE(created_at, CURRENT_TIMESTAMP),
                COALESCE(updated_at, CURRENT_TIMESTAMP)
            FROM automation_workflow_execution_item
            """
        )
        db.execute("DROP TABLE automation_workflow_execution_item")
        db.execute("ALTER TABLE automation_workflow_execution_item__new RENAME TO automation_workflow_execution_item")
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_automation_workflow_execution_item_execution ON automation_workflow_execution_item (execution_id, id ASC)"
        )
        db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_workflow_execution_item_member_unique ON automation_workflow_execution_item (execution_id, member_id)"
        )
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_automation_workflow_execution_item_member ON automation_workflow_execution_item (member_id, created_at DESC, id DESC)"
        )
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_automation_workflow_execution_item_send_record ON automation_workflow_execution_item (send_record_id, created_at DESC, id DESC)"
        )
        db.execute("PRAGMA foreign_keys = ON")

    if _sqlite_table_exists(db, "automation_workflow_agent_pool_binding"):
        db.execute("DROP TABLE automation_workflow_agent_pool_binding")
    if _sqlite_table_exists(db, "automation_agent_pool_agent"):
        db.execute("DROP TABLE automation_agent_pool_agent")
    if _sqlite_table_exists(db, "automation_agent_pool"):
        db.execute("DROP TABLE automation_agent_pool")


def _ensure_sqlite_customer_pulse_tables(db) -> None:
    deferred_job_columns = _sqlite_table_columns(db, "user_ops_deferred_jobs")
    if deferred_job_columns and "tenant_key" not in deferred_job_columns:
        db.execute("ALTER TABLE user_ops_deferred_jobs ADD COLUMN tenant_key TEXT NOT NULL DEFAULT 'aicrm'")
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_user_ops_deferred_jobs_job_tenant_status
        ON user_ops_deferred_jobs (job_type, tenant_key, status, run_after, id DESC)
        """
    )

    signal_columns = _sqlite_table_columns(db, "customer_pulse_signal_events")
    if signal_columns and "tenant_key" not in signal_columns:
        db.execute("ALTER TABLE customer_pulse_signal_events ADD COLUMN tenant_key TEXT NOT NULL DEFAULT 'aicrm'")
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_customer_pulse_signal_events_tenant_external_status
        ON customer_pulse_signal_events (tenant_key, external_userid, signal_status, updated_at DESC, id DESC)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_customer_pulse_signal_events_tenant_type
        ON customer_pulse_signal_events (tenant_key, signal_type, updated_at DESC, id DESC)
        """
    )

    snapshot_columns = _sqlite_table_columns(db, "customer_pulse_snapshots")
    if snapshot_columns:
        if "tenant_key" not in snapshot_columns:
            db.execute("ALTER TABLE customer_pulse_snapshots ADD COLUMN tenant_key TEXT NOT NULL DEFAULT 'aicrm'")
        if "priority_score" not in snapshot_columns:
            db.execute("ALTER TABLE customer_pulse_snapshots ADD COLUMN priority_score REAL NOT NULL DEFAULT 0")
        if "risk_flags_json" not in snapshot_columns:
            db.execute("ALTER TABLE customer_pulse_snapshots ADD COLUMN risk_flags_json TEXT NOT NULL DEFAULT '[]'")
        if "opportunity_flags_json" not in snapshot_columns:
            db.execute("ALTER TABLE customer_pulse_snapshots ADD COLUMN opportunity_flags_json TEXT NOT NULL DEFAULT '[]'")
        if "suggested_action_candidates_json" not in snapshot_columns:
            db.execute("ALTER TABLE customer_pulse_snapshots ADD COLUMN suggested_action_candidates_json TEXT NOT NULL DEFAULT '[]'")
        if "score_breakdown_json" not in snapshot_columns:
            db.execute("ALTER TABLE customer_pulse_snapshots ADD COLUMN score_breakdown_json TEXT NOT NULL DEFAULT '[]'")
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_customer_pulse_snapshots_tenant_external
        ON customer_pulse_snapshots (tenant_key, external_userid, created_at DESC, id DESC)
        """
    )

    card_columns = _sqlite_table_columns(db, "customer_pulse_cards")
    if card_columns:
        if "tenant_key" not in card_columns:
            db.execute("ALTER TABLE customer_pulse_cards ADD COLUMN tenant_key TEXT NOT NULL DEFAULT 'aicrm'")
        if "customer_name" not in card_columns:
            db.execute("ALTER TABLE customer_pulse_cards ADD COLUMN customer_name TEXT NOT NULL DEFAULT ''")
        if "mobile" not in card_columns:
            db.execute("ALTER TABLE customer_pulse_cards ADD COLUMN mobile TEXT NOT NULL DEFAULT ''")
        if "owner_display_name" not in card_columns:
            db.execute("ALTER TABLE customer_pulse_cards ADD COLUMN owner_display_name TEXT NOT NULL DEFAULT ''")
        if "marketing_main_stage" not in card_columns:
            db.execute("ALTER TABLE customer_pulse_cards ADD COLUMN marketing_main_stage TEXT NOT NULL DEFAULT ''")
        if "marketing_sub_stage" not in card_columns:
            db.execute("ALTER TABLE customer_pulse_cards ADD COLUMN marketing_sub_stage TEXT NOT NULL DEFAULT ''")
        if "value_segment" not in card_columns:
            db.execute("ALTER TABLE customer_pulse_cards ADD COLUMN value_segment TEXT NOT NULL DEFAULT ''")
        if "priority_score" not in card_columns:
            db.execute("ALTER TABLE customer_pulse_cards ADD COLUMN priority_score REAL NOT NULL DEFAULT 0")
        if "risk_flags_json" not in card_columns:
            db.execute("ALTER TABLE customer_pulse_cards ADD COLUMN risk_flags_json TEXT NOT NULL DEFAULT '[]'")
        if "opportunity_flags_json" not in card_columns:
            db.execute("ALTER TABLE customer_pulse_cards ADD COLUMN opportunity_flags_json TEXT NOT NULL DEFAULT '[]'")
        if "suggested_action_candidates_json" not in card_columns:
            db.execute("ALTER TABLE customer_pulse_cards ADD COLUMN suggested_action_candidates_json TEXT NOT NULL DEFAULT '[]'")
        if "score_breakdown_json" not in card_columns:
            db.execute("ALTER TABLE customer_pulse_cards ADD COLUMN score_breakdown_json TEXT NOT NULL DEFAULT '[]'")

    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_customer_pulse_cards_status_score
        ON customer_pulse_cards (card_status, priority_score DESC, due_at, updated_at DESC, id DESC)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_customer_pulse_cards_tenant_external
        ON customer_pulse_cards (tenant_key, external_userid, updated_at DESC, id DESC)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_customer_pulse_cards_tenant_status_score
        ON customer_pulse_cards (tenant_key, card_status, priority_score DESC, due_at, updated_at DESC, id DESC)
        """
    )
    feedback_columns = _sqlite_table_columns(db, "customer_pulse_feedback_logs")
    if feedback_columns and "tenant_key" not in feedback_columns:
        db.execute("ALTER TABLE customer_pulse_feedback_logs ADD COLUMN tenant_key TEXT NOT NULL DEFAULT 'aicrm'")
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_customer_pulse_feedback_logs_tenant_card
        ON customer_pulse_feedback_logs (tenant_key, card_id, created_at DESC, id DESC)
        """
    )
    execution_log_columns = _sqlite_table_columns(db, "customer_pulse_execution_logs")
    if execution_log_columns:
        if "tenant_key" not in execution_log_columns:
            db.execute("ALTER TABLE customer_pulse_execution_logs ADD COLUMN tenant_key TEXT NOT NULL DEFAULT 'aicrm'")
        if "actor_userid" not in execution_log_columns:
            db.execute("ALTER TABLE customer_pulse_execution_logs ADD COLUMN actor_userid TEXT NOT NULL DEFAULT ''")
        if "actor_role" not in execution_log_columns:
            db.execute("ALTER TABLE customer_pulse_execution_logs ADD COLUMN actor_role TEXT NOT NULL DEFAULT ''")
        if "resource_type" not in execution_log_columns:
            db.execute("ALTER TABLE customer_pulse_execution_logs ADD COLUMN resource_type TEXT NOT NULL DEFAULT ''")
        if "resource_id" not in execution_log_columns:
            db.execute("ALTER TABLE customer_pulse_execution_logs ADD COLUMN resource_id TEXT NOT NULL DEFAULT ''")
        if "tenant_context_json" not in execution_log_columns:
            db.execute("ALTER TABLE customer_pulse_execution_logs ADD COLUMN tenant_context_json TEXT NOT NULL DEFAULT '{}'")
        if "audit_labels_json" not in execution_log_columns:
            db.execute("ALTER TABLE customer_pulse_execution_logs ADD COLUMN audit_labels_json TEXT NOT NULL DEFAULT '[]'")
        if "rollback_payload_json" not in execution_log_columns:
            db.execute("ALTER TABLE customer_pulse_execution_logs ADD COLUMN rollback_payload_json TEXT NOT NULL DEFAULT '{}'")
        if "execution_key" not in execution_log_columns:
            db.execute("ALTER TABLE customer_pulse_execution_logs ADD COLUMN execution_key TEXT NOT NULL DEFAULT ''")
        if "idempotency_key" not in execution_log_columns:
            db.execute("ALTER TABLE customer_pulse_execution_logs ADD COLUMN idempotency_key TEXT NOT NULL DEFAULT ''")
        if "activity_log_id" not in execution_log_columns:
            db.execute("ALTER TABLE customer_pulse_execution_logs ADD COLUMN activity_log_id INTEGER")
        if "outbound_task_id" not in execution_log_columns:
            db.execute("ALTER TABLE customer_pulse_execution_logs ADD COLUMN outbound_task_id INTEGER")
        if "undo_status" not in execution_log_columns:
            db.execute("ALTER TABLE customer_pulse_execution_logs ADD COLUMN undo_status TEXT NOT NULL DEFAULT ''")
        if "undo_until" not in execution_log_columns:
            db.execute("ALTER TABLE customer_pulse_execution_logs ADD COLUMN undo_until TEXT NOT NULL DEFAULT ''")
        if "undone_at" not in execution_log_columns:
            db.execute("ALTER TABLE customer_pulse_execution_logs ADD COLUMN undone_at TEXT NOT NULL DEFAULT ''")
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_customer_pulse_execution_logs_tenant_card
        ON customer_pulse_execution_logs (tenant_key, card_id, created_at DESC, id DESC)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_customer_pulse_execution_logs_tenant_idempotency
        ON customer_pulse_execution_logs (tenant_key, idempotency_key, created_at DESC, id DESC)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_customer_pulse_execution_logs_tenant_resource
        ON customer_pulse_execution_logs (tenant_key, resource_type, resource_id, created_at DESC, id DESC)
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS customer_pulse_activity_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            card_id INTEGER NOT NULL REFERENCES customer_pulse_cards(id) ON DELETE CASCADE,
            external_userid TEXT NOT NULL DEFAULT '',
            owner_userid TEXT NOT NULL DEFAULT '',
            activity_type TEXT NOT NULL DEFAULT '',
            activity_status TEXT NOT NULL DEFAULT '',
            activity_source TEXT NOT NULL DEFAULT 'ai_customer_pulse',
            tenant_key TEXT NOT NULL DEFAULT 'aicrm',
            execution_key TEXT NOT NULL DEFAULT '',
            idempotency_key TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL DEFAULT '',
            summary TEXT NOT NULL DEFAULT '',
            due_at TEXT NOT NULL DEFAULT '',
            operator TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL DEFAULT '{}',
            undone_at TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_customer_pulse_activity_logs_tenant_external_userid
        ON customer_pulse_activity_logs (tenant_key, external_userid, created_at DESC, id DESC)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_customer_pulse_activity_logs_tenant_card
        ON customer_pulse_activity_logs (tenant_key, card_id, created_at DESC, id DESC)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_customer_pulse_activity_logs_tenant_idempotency
        ON customer_pulse_activity_logs (tenant_key, idempotency_key, created_at DESC, id DESC)
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS customer_pulse_action_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            card_id INTEGER NOT NULL REFERENCES customer_pulse_cards(id) ON DELETE CASCADE,
            execution_log_id INTEGER REFERENCES customer_pulse_execution_logs(id) ON DELETE SET NULL,
            external_userid TEXT NOT NULL DEFAULT '',
            owner_userid TEXT NOT NULL DEFAULT '',
            action_type TEXT NOT NULL DEFAULT '',
            feedback_type TEXT NOT NULL DEFAULT '',
            feedback_source TEXT NOT NULL DEFAULT '',
            tenant_key TEXT NOT NULL DEFAULT 'aicrm',
            operator TEXT NOT NULL DEFAULT '',
            note TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_customer_pulse_action_feedback_tenant_card
        ON customer_pulse_action_feedback (tenant_key, card_id, created_at DESC, id DESC)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_customer_pulse_action_feedback_tenant_execution
        ON customer_pulse_action_feedback (tenant_key, execution_log_id, created_at DESC, id DESC)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_customer_pulse_action_feedback_tenant_type
        ON customer_pulse_action_feedback (tenant_key, feedback_type, created_at DESC, id DESC)
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS customer_pulse_metric_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            card_id INTEGER REFERENCES customer_pulse_cards(id) ON DELETE SET NULL,
            execution_log_id INTEGER REFERENCES customer_pulse_execution_logs(id) ON DELETE SET NULL,
            external_userid TEXT NOT NULL DEFAULT '',
            owner_userid TEXT NOT NULL DEFAULT '',
            action_type TEXT NOT NULL DEFAULT '',
            event_type TEXT NOT NULL DEFAULT '',
            event_source TEXT NOT NULL DEFAULT '',
            tenant_key TEXT NOT NULL DEFAULT 'aicrm',
            operator TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_customer_pulse_metric_events_tenant_type
        ON customer_pulse_metric_events (tenant_key, event_type, created_at DESC, id DESC)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_customer_pulse_metric_events_tenant_card
        ON customer_pulse_metric_events (tenant_key, card_id, created_at DESC, id DESC)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_customer_pulse_metric_events_tenant_execution
        ON customer_pulse_metric_events (tenant_key, execution_log_id, created_at DESC, id DESC)
        """
    )


def _ensure_sqlite_admin_auth_tables(db) -> None:
    if not _sqlite_table_exists(db, "admin_users"):
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wecom_userid TEXT NOT NULL DEFAULT '',
                wecom_corpid TEXT NOT NULL DEFAULT '',
                display_name TEXT NOT NULL DEFAULT '',
                is_active INTEGER NOT NULL DEFAULT 1,
                login_enabled INTEGER NOT NULL DEFAULT 1,
                admin_level TEXT NOT NULL DEFAULT 'admin',
                auth_source TEXT NOT NULL DEFAULT 'wecom_sso',
                last_login_at TEXT,
                created_by TEXT NOT NULL DEFAULT '',
                updated_by TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    columns = _sqlite_table_columns(db, "admin_users")
    if "wecom_userid" not in columns:
        db.execute("ALTER TABLE admin_users ADD COLUMN wecom_userid TEXT NOT NULL DEFAULT ''")
        columns.add("wecom_userid")
    if "wecom_corpid" not in columns:
        db.execute("ALTER TABLE admin_users ADD COLUMN wecom_corpid TEXT NOT NULL DEFAULT ''")
        columns.add("wecom_corpid")
    if "auth_source" not in columns:
        db.execute("ALTER TABLE admin_users ADD COLUMN auth_source TEXT NOT NULL DEFAULT 'wecom_sso'")
        columns.add("auth_source")
    if "last_login_at" not in columns:
        db.execute("ALTER TABLE admin_users ADD COLUMN last_login_at TEXT")
        columns.add("last_login_at")
    if "created_at" not in columns:
        db.execute("ALTER TABLE admin_users ADD COLUMN created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP")
        columns.add("created_at")
    if "updated_at" not in columns:
        db.execute("ALTER TABLE admin_users ADD COLUMN updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP")
        columns.add("updated_at")
    if "is_active" not in columns:
        db.execute("ALTER TABLE admin_users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
        columns.add("is_active")
    if "login_enabled" not in columns:
        db.execute("ALTER TABLE admin_users ADD COLUMN login_enabled INTEGER NOT NULL DEFAULT 1")
        columns.add("login_enabled")
    if "admin_level" not in columns:
        db.execute("ALTER TABLE admin_users ADD COLUMN admin_level TEXT NOT NULL DEFAULT 'admin'")
        columns.add("admin_level")
    if "created_by" not in columns:
        db.execute("ALTER TABLE admin_users ADD COLUMN created_by TEXT NOT NULL DEFAULT ''")
        columns.add("created_by")
    if "updated_by" not in columns:
        db.execute("ALTER TABLE admin_users ADD COLUMN updated_by TEXT NOT NULL DEFAULT ''")
        columns.add("updated_by")
    legacy_columns = _sqlite_table_columns(db, "admin_users")
    if "username" in legacy_columns:
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
    if "password_hash" in legacy_columns:
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
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wecom_corpid TEXT NOT NULL DEFAULT '',
            wecom_userid TEXT NOT NULL DEFAULT '',
            display_name TEXT NOT NULL DEFAULT '',
            department_ids_json TEXT NOT NULL DEFAULT '[]',
            position TEXT NOT NULL DEFAULT '',
            wecom_status INTEGER,
            is_active INTEGER NOT NULL DEFAULT 1,
            synced_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            raw_payload_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_user_id INTEGER NOT NULL REFERENCES admin_users(id) ON DELETE CASCADE,
            role_code TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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
    if "role_code" in legacy_columns:
        rows = db.execute(
            """
            SELECT id, role_code
            FROM admin_users
            WHERE COALESCE(role_code, '') <> ''
            """
        ).fetchall()
        for row in rows:
            db.execute(
                """
                INSERT OR IGNORE INTO admin_user_roles (admin_user_id, role_code, created_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                """,
                (int(row["id"]), str(row["role_code"] or "").strip()),
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
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_user_id INTEGER REFERENCES admin_users(id) ON DELETE SET NULL,
            login_type TEXT NOT NULL DEFAULT '',
            login_result TEXT NOT NULL DEFAULT '',
            ip TEXT NOT NULL DEFAULT '',
            user_agent TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_admin_sso_states_expires
        ON admin_sso_states (expires_at)
        """
    )


def _init_sqlite(db) -> None:
    schema_path = Path(current_app.root_path) / "schema.sql"
    _prepare_sqlite_schema_columns_for_executescript(db)
    db.executescript(schema_path.read_text(encoding="utf-8"))
    _ensure_sqlite_questionnaire_question_fields(db)
    _ensure_sqlite_questionnaire_external_push_tables(db)
    _ensure_sqlite_user_ops_page_tables(db)
    _ensure_sqlite_customer_value_segment_tables(db)
    _ensure_sqlite_customer_marketing_state_tables(db)
    _ensure_sqlite_automation_conversion_tables(db)
    _ensure_sqlite_automation_program_tables(db)
    _migrate_sqlite_conversion_agent_pools_to_bindings(db)
    _ensure_sqlite_automation_sop_v2_columns(db)
    _ensure_sqlite_customer_pulse_tables(db)
    _ensure_sqlite_admin_auth_tables(db)
    _ensure_automation_sop_v1_seed_data()
    _ensure_automation_agent_prompt_defaults()
    columns = _sqlite_table_columns(db, "archived_messages")
    if "chat_type" not in columns:
        db.execute("ALTER TABLE archived_messages ADD COLUMN chat_type TEXT NOT NULL DEFAULT 'private'")
    contact_columns = _sqlite_table_columns(db, "contacts")
    if contact_columns:
        if "description" not in contact_columns:
            db.execute("ALTER TABLE contacts ADD COLUMN description TEXT")
        if "remark" not in contact_columns:
            db.execute("ALTER TABLE contacts ADD COLUMN remark TEXT")
    batch_columns = _sqlite_table_columns(db, "message_batches")
    if batch_columns and "acked_by" not in batch_columns:
        db.execute("ALTER TABLE message_batches ADD COLUMN acked_by TEXT")
    questionnaire_submission_columns = _sqlite_table_columns(db, "questionnaire_submissions")
    if questionnaire_submission_columns and "mobile_snapshot" not in questionnaire_submission_columns:
        db.execute("ALTER TABLE questionnaire_submissions ADD COLUMN mobile_snapshot TEXT NOT NULL DEFAULT ''")
    class_term_mapping_columns = _sqlite_table_columns(db, "class_term_tag_mapping")
    if class_term_mapping_columns:
        if "strategy_id" not in class_term_mapping_columns:
            db.execute("ALTER TABLE class_term_tag_mapping ADD COLUMN strategy_id TEXT NOT NULL DEFAULT ''")
        if "group_id" not in class_term_mapping_columns:
            db.execute("ALTER TABLE class_term_tag_mapping ADD COLUMN group_id TEXT NOT NULL DEFAULT ''")
        if "tag_id" not in class_term_mapping_columns:
            db.execute("ALTER TABLE class_term_tag_mapping ADD COLUMN tag_id TEXT NOT NULL DEFAULT ''")
        db.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_class_term_tag_mapping_tag_id_non_empty
            ON class_term_tag_mapping (tag_id)
            WHERE tag_id <> ''
            """
        )
    message_activity_sync_item_columns = _sqlite_table_columns(db, "automation_message_activity_sync_item")
    if message_activity_sync_item_columns:
        if "phone_prefix3" not in message_activity_sync_item_columns:
            db.execute("ALTER TABLE automation_message_activity_sync_item ADD COLUMN phone_prefix3 TEXT NOT NULL DEFAULT ''")
        if "phone_match_key" not in message_activity_sync_item_columns:
            db.execute("ALTER TABLE automation_message_activity_sync_item ADD COLUMN phone_match_key TEXT NOT NULL DEFAULT ''")
        db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_automation_message_activity_sync_item_match_key
            ON automation_message_activity_sync_item (phone_match_key, created_at DESC, id DESC)
            """
        )
    agent_output_columns = _sqlite_table_columns(db, "automation_agent_output")
    if agent_output_columns:
        if "adopted_by" not in agent_output_columns:
            db.execute("ALTER TABLE automation_agent_output ADD COLUMN adopted_by TEXT NOT NULL DEFAULT ''")
        if "adopted_action" not in agent_output_columns:
            db.execute("ALTER TABLE automation_agent_output ADD COLUMN adopted_action TEXT NOT NULL DEFAULT ''")
        if "adopted_at" not in agent_output_columns:
            db.execute("ALTER TABLE automation_agent_output ADD COLUMN adopted_at TEXT NOT NULL DEFAULT ''")
        if "outcome_status" not in agent_output_columns:
            db.execute("ALTER TABLE automation_agent_output ADD COLUMN outcome_status TEXT NOT NULL DEFAULT ''")
        if "outcome_value" not in agent_output_columns:
            db.execute("ALTER TABLE automation_agent_output ADD COLUMN outcome_value TEXT NOT NULL DEFAULT ''")
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
    profile_template_columns = _sqlite_table_columns(db, "automation_profile_segment_template")
    if profile_template_columns and "program_id" not in profile_template_columns:
        db.execute("ALTER TABLE automation_profile_segment_template ADD COLUMN program_id INTEGER")
    if profile_template_columns and "segmentation_question_id" not in profile_template_columns:
        db.execute("ALTER TABLE automation_profile_segment_template ADD COLUMN segmentation_question_id INTEGER")
    agent_config_columns = _sqlite_table_columns(db, "automation_agent_config")
    if agent_config_columns:
        if "submitted_for_publish" not in agent_config_columns:
            db.execute("ALTER TABLE automation_agent_config ADD COLUMN submitted_for_publish INTEGER NOT NULL DEFAULT 0")
        if "submitted_at" not in agent_config_columns:
            db.execute("ALTER TABLE automation_agent_config ADD COLUMN submitted_at TEXT NOT NULL DEFAULT ''")
        if "submitted_by" not in agent_config_columns:
            db.execute("ALTER TABLE automation_agent_config ADD COLUMN submitted_by TEXT NOT NULL DEFAULT ''")
    db.commit()


def _prepare_sqlite_schema_columns_for_executescript(db) -> None:
    """Add columns required by schema indexes before CREATE INDEX runs."""
    for table_name in (
        "automation_channel",
        "automation_profile_segment_template",
        "automation_workflow",
        "automation_workflow_execution",
    ):
        if _sqlite_table_exists(db, table_name) and "program_id" not in _sqlite_table_columns(db, table_name):
            db.execute(f"ALTER TABLE {table_name} ADD COLUMN program_id INTEGER")

