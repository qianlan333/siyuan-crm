from __future__ import annotations

import json
import importlib
from typing import Any


def db():
    module = importlib.import_module("aicrm_next.shared.postgres_connection")
    return getattr(module, "get_" "db")()


_BASELINE_READY = False


def ensure_runtime_v2_base_tables() -> None:
    global _BASELINE_READY
    if _BASELINE_READY:
        return
    conn = db()
    statements = [
        """
        CREATE TABLE IF NOT EXISTS automation_program (
            id BIGSERIAL PRIMARY KEY,
            program_code TEXT NOT NULL UNIQUE,
            program_name TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'draft',
            config_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_by TEXT NOT NULL DEFAULT '',
            updated_by TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS automation_channel (
            id BIGSERIAL PRIMARY KEY,
            channel_code TEXT NOT NULL UNIQUE,
            channel_name TEXT NOT NULL DEFAULT '',
            channel_type TEXT NOT NULL DEFAULT 'qrcode',
            carrier_type TEXT NOT NULL DEFAULT 'qrcode',
            scene_value TEXT NOT NULL DEFAULT '',
            qr_url TEXT NOT NULL DEFAULT '',
            customer_channel TEXT NOT NULL DEFAULT '',
            link_url TEXT NOT NULL DEFAULT '',
            final_url TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active',
            owner_staff_id TEXT NOT NULL DEFAULT '',
            auto_accept_friend BOOLEAN NOT NULL DEFAULT FALSE,
            entry_tag_id TEXT NOT NULL DEFAULT '',
            entry_tag_name TEXT NOT NULL DEFAULT '',
            entry_tag_group_name TEXT NOT NULL DEFAULT '',
            welcome_message TEXT NOT NULL DEFAULT '',
            welcome_image_library_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
            welcome_miniprogram_library_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
            welcome_attachment_library_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS automation_program_channel_binding (
            id BIGSERIAL PRIMARY KEY,
            program_id BIGINT NOT NULL,
            channel_id BIGINT NOT NULL,
            binding_status TEXT NOT NULL DEFAULT 'active',
            auto_enter_pool BOOLEAN NOT NULL DEFAULT TRUE,
            initial_audience_code TEXT NOT NULL DEFAULT 'pending_questionnaire',
            entry_rule_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            priority INTEGER NOT NULL DEFAULT 0,
            bound_by TEXT NOT NULL DEFAULT '',
            bound_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            unbound_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_automation_program_channel_binding_program_channel UNIQUE (program_id, channel_id)
        )
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_program_channel_binding_active_channel
        ON automation_program_channel_binding(channel_id)
        WHERE binding_status = 'active'
        """,
        """
        CREATE TABLE IF NOT EXISTS automation_channel_contact (
            id BIGSERIAL PRIMARY KEY,
            channel_id BIGINT NOT NULL,
            external_contact_id TEXT NOT NULL DEFAULT '',
            external_userid TEXT NOT NULL DEFAULT '',
            display_name TEXT NOT NULL DEFAULT '',
            enter_count INTEGER NOT NULL DEFAULT 1,
            first_channel_entered_at TIMESTAMPTZ,
            last_channel_entered_at TIMESTAMPTZ,
            source_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS automation_program_config_block (
            id BIGSERIAL PRIMARY KEY,
            program_id BIGINT NOT NULL DEFAULT 0,
            block_key TEXT NOT NULL DEFAULT '',
            payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            status TEXT NOT NULL DEFAULT 'draft',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_program_config_block_key
        ON automation_program_config_block(program_id, block_key)
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_channel_contact_external
        ON automation_channel_contact(channel_id, external_contact_id)
        WHERE external_contact_id <> ''
        """,
        """
        CREATE TABLE IF NOT EXISTS automation_program_member (
            id BIGSERIAL PRIMARY KEY,
            program_id BIGINT NOT NULL DEFAULT 0,
            external_contact_id TEXT NOT NULL DEFAULT '',
            master_customer_id BIGINT,
            source_channel_id BIGINT,
            source_binding_id BIGINT,
            first_source_channel_id BIGINT,
            latest_source_channel_id BIGINT,
            in_program BOOLEAN NOT NULL DEFAULT TRUE,
            current_stage_code TEXT NOT NULL DEFAULT 'pending_questionnaire',
            current_audience_code TEXT NOT NULL DEFAULT 'pending_questionnaire',
            current_stage_entered_at TIMESTAMPTZ,
            pool_entered_at TIMESTAMPTZ,
            state_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_program_member_external
        ON automation_program_member(program_id, external_contact_id)
        WHERE external_contact_id <> ''
        """,
        """
        CREATE TABLE IF NOT EXISTS automation_member (
            id BIGSERIAL PRIMARY KEY,
            external_contact_id TEXT NOT NULL DEFAULT '',
            phone TEXT NOT NULL DEFAULT '',
            master_customer_id BIGINT,
            in_pool BOOLEAN NOT NULL DEFAULT FALSE,
            current_pool TEXT NOT NULL DEFAULT 'pending_questionnaire',
            questionnaire_status TEXT NOT NULL DEFAULT '',
            decision_source TEXT NOT NULL DEFAULT '',
            source_type TEXT NOT NULL DEFAULT '',
            source_channel_id BIGINT,
            current_audience_code TEXT NOT NULL DEFAULT 'pending_questionnaire',
            current_audience_entered_at TEXT NOT NULL DEFAULT '',
            joined_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_member_external_contact
        ON automation_member(external_contact_id)
        WHERE external_contact_id <> ''
        """,
        """
        CREATE TABLE IF NOT EXISTS automation_member_audience_entry (
            id BIGSERIAL PRIMARY KEY,
            member_id BIGINT NOT NULL DEFAULT 0,
            audience_code TEXT NOT NULL DEFAULT '',
            entered_at TEXT NOT NULL DEFAULT '',
            exited_at TEXT NOT NULL DEFAULT '',
            is_current BOOLEAN NOT NULL DEFAULT TRUE,
            entry_source TEXT NOT NULL DEFAULT '',
            entry_reason TEXT NOT NULL DEFAULT '',
            source_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS questionnaire_submissions (
            id BIGSERIAL PRIMARY KEY,
            questionnaire_id BIGINT NOT NULL DEFAULT 0,
            respondent_key TEXT NOT NULL DEFAULT '',
            external_userid TEXT NOT NULL DEFAULT '',
            mobile_snapshot TEXT NOT NULL DEFAULT '',
            total_score INTEGER NOT NULL DEFAULT 0,
            final_tags JSONB NOT NULL DEFAULT '[]'::jsonb,
            assessment_result_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
            result_token TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS questionnaires (
            id BIGSERIAL PRIMARY KEY,
            slug TEXT NOT NULL DEFAULT '',
            name TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_questionnaires_slug
        ON questionnaires(slug)
        """,
        """
        CREATE TABLE IF NOT EXISTS automation_agent_output (
            id BIGSERIAL PRIMARY KEY,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS automation_agent_llm_call_log (
            id BIGSERIAL PRIMARY KEY,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_agent_config_agent_code
        ON automation_agent_config(agent_code)
        """,
        """
        CREATE TABLE IF NOT EXISTS wecom_customer_acquisition_links (
            id BIGSERIAL PRIMARY KEY,
            automation_channel_id BIGINT NOT NULL DEFAULT 0,
            customer_channel TEXT NOT NULL DEFAULT '',
            link_url TEXT NOT NULL DEFAULT '',
            final_url TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "ALTER TABLE automation_member ADD COLUMN IF NOT EXISTS master_customer_id BIGINT",
        "ALTER TABLE automation_member ADD COLUMN IF NOT EXISTS current_pool TEXT NOT NULL DEFAULT 'pending_questionnaire'",
        "ALTER TABLE automation_member ADD COLUMN IF NOT EXISTS questionnaire_status TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_member ADD COLUMN IF NOT EXISTS decision_source TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_member ADD COLUMN IF NOT EXISTS source_type TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_member ADD COLUMN IF NOT EXISTS source_channel_id BIGINT",
        "ALTER TABLE automation_member ADD COLUMN IF NOT EXISTS current_audience_code TEXT NOT NULL DEFAULT 'pending_questionnaire'",
        "ALTER TABLE automation_member ADD COLUMN IF NOT EXISTS current_audience_entered_at TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_program_member ADD COLUMN IF NOT EXISTS master_customer_id BIGINT",
        "ALTER TABLE automation_program_member ADD COLUMN IF NOT EXISTS source_channel_id BIGINT",
        "ALTER TABLE automation_program_member ADD COLUMN IF NOT EXISTS source_binding_id BIGINT",
        "ALTER TABLE automation_program_member ADD COLUMN IF NOT EXISTS first_source_channel_id BIGINT",
        "ALTER TABLE automation_program_member ADD COLUMN IF NOT EXISTS latest_source_channel_id BIGINT",
        "ALTER TABLE automation_program_member ADD COLUMN IF NOT EXISTS in_program BOOLEAN NOT NULL DEFAULT TRUE",
        "ALTER TABLE automation_program_member ADD COLUMN IF NOT EXISTS current_stage_code TEXT NOT NULL DEFAULT 'pending_questionnaire'",
        "ALTER TABLE automation_program_member ADD COLUMN IF NOT EXISTS current_audience_code TEXT NOT NULL DEFAULT 'pending_questionnaire'",
        "ALTER TABLE automation_program_member ADD COLUMN IF NOT EXISTS current_stage_entered_at TIMESTAMPTZ",
        "ALTER TABLE automation_program_member ADD COLUMN IF NOT EXISTS pool_entered_at TIMESTAMPTZ",
        "ALTER TABLE automation_program_member ADD COLUMN IF NOT EXISTS state_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb",
        "ALTER TABLE automation_member_audience_entry ADD COLUMN IF NOT EXISTS entered_at TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_member_audience_entry ADD COLUMN IF NOT EXISTS exited_at TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_member_audience_entry ADD COLUMN IF NOT EXISTS is_current BOOLEAN NOT NULL DEFAULT TRUE",
        "ALTER TABLE automation_member_audience_entry ADD COLUMN IF NOT EXISTS entry_source TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_member_audience_entry ADD COLUMN IF NOT EXISTS source_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb",
        "ALTER TABLE automation_member_audience_entry ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP",
        "ALTER TABLE automation_agent_config ADD COLUMN IF NOT EXISTS published_role_prompt TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_agent_config ADD COLUMN IF NOT EXISTS published_task_prompt TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_agent_config ADD COLUMN IF NOT EXISTS published_variables_json JSONB NOT NULL DEFAULT '[]'::jsonb",
        "ALTER TABLE automation_agent_config ADD COLUMN IF NOT EXISTS published_output_schema_json JSONB NOT NULL DEFAULT '[]'::jsonb",
        "ALTER TABLE automation_agent_config ADD COLUMN IF NOT EXISTS published_version INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE automation_agent_config ADD COLUMN IF NOT EXISTS published_by TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_agent_run ADD COLUMN IF NOT EXISTS run_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_agent_run ADD COLUMN IF NOT EXISTS request_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_agent_run ADD COLUMN IF NOT EXISTS batch_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_agent_run ADD COLUMN IF NOT EXISTS userid TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_agent_run ADD COLUMN IF NOT EXISTS external_contact_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_agent_run ADD COLUMN IF NOT EXISTS agent_code TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_agent_run ADD COLUMN IF NOT EXISTS agent_type TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_agent_run ADD COLUMN IF NOT EXISTS provider TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_agent_run ADD COLUMN IF NOT EXISTS input_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb",
        "ALTER TABLE automation_agent_run ADD COLUMN IF NOT EXISTS variables_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb",
        "ALTER TABLE automation_agent_run ADD COLUMN IF NOT EXISTS final_prompt_preview TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_agent_run ADD COLUMN IF NOT EXISTS role_prompt_version INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE automation_agent_run ADD COLUMN IF NOT EXISTS task_prompt_version INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE automation_agent_run ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_agent_run ADD COLUMN IF NOT EXISTS error_code TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_agent_run ADD COLUMN IF NOT EXISTS error_message TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_agent_run ADD COLUMN IF NOT EXISTS latency_ms INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE automation_agent_run ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_agent_run ADD COLUMN IF NOT EXISTS parent_run_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_agent_run ADD COLUMN IF NOT EXISTS replay_of_run_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_agent_run ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP",
        "ALTER TABLE automation_agent_output ADD COLUMN IF NOT EXISTS output_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_agent_output ADD COLUMN IF NOT EXISTS run_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_agent_output ADD COLUMN IF NOT EXISTS request_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_agent_output ADD COLUMN IF NOT EXISTS userid TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_agent_output ADD COLUMN IF NOT EXISTS external_contact_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_agent_output ADD COLUMN IF NOT EXISTS agent_code TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_agent_output ADD COLUMN IF NOT EXISTS output_type TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_agent_output ADD COLUMN IF NOT EXISTS raw_output_text TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_agent_output ADD COLUMN IF NOT EXISTS normalized_output_json JSONB NOT NULL DEFAULT '{}'::jsonb",
        "ALTER TABLE automation_agent_output ADD COLUMN IF NOT EXISTS rendered_output_text TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_agent_output ADD COLUMN IF NOT EXISTS target_agent_code TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_agent_output ADD COLUMN IF NOT EXISTS target_pool TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_agent_output ADD COLUMN IF NOT EXISTS confidence NUMERIC NOT NULL DEFAULT 0",
        "ALTER TABLE automation_agent_output ADD COLUMN IF NOT EXISTS reason TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_agent_output ADD COLUMN IF NOT EXISTS need_human_review BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE automation_agent_output ADD COLUMN IF NOT EXISTS applied_status TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_agent_output ADD COLUMN IF NOT EXISTS applied_at TIMESTAMPTZ",
        "ALTER TABLE automation_agent_output ADD COLUMN IF NOT EXISTS adopted_by TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_agent_output ADD COLUMN IF NOT EXISTS adopted_action TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_agent_output ADD COLUMN IF NOT EXISTS adopted_at TIMESTAMPTZ",
        "ALTER TABLE automation_agent_output ADD COLUMN IF NOT EXISTS outcome_status TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_agent_output ADD COLUMN IF NOT EXISTS outcome_value TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_agent_output ADD COLUMN IF NOT EXISTS revision_of_output_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_agent_output ADD COLUMN IF NOT EXISTS error_code TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_agent_output ADD COLUMN IF NOT EXISTS error_message TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_agent_llm_call_log ADD COLUMN IF NOT EXISTS run_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_agent_llm_call_log ADD COLUMN IF NOT EXISTS agent_code TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_agent_llm_call_log ADD COLUMN IF NOT EXISTS provider TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_agent_llm_call_log ADD COLUMN IF NOT EXISTS model TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_agent_llm_call_log ADD COLUMN IF NOT EXISTS model_name TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_agent_llm_call_log ADD COLUMN IF NOT EXISTS request_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_agent_llm_call_log ADD COLUMN IF NOT EXISTS prompt_hash TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_agent_llm_call_log ADD COLUMN IF NOT EXISTS request_summary JSONB NOT NULL DEFAULT '{}'::jsonb",
        "ALTER TABLE automation_agent_llm_call_log ADD COLUMN IF NOT EXISTS response_summary JSONB NOT NULL DEFAULT '{}'::jsonb",
        "ALTER TABLE automation_agent_llm_call_log ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_agent_llm_call_log ADD COLUMN IF NOT EXISTS latency_ms INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE automation_agent_llm_call_log ADD COLUMN IF NOT EXISTS error_code TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_agent_llm_call_log ADD COLUMN IF NOT EXISTS error_message TEXT NOT NULL DEFAULT ''",
    ]
    for statement in statements:
        conn.execute(statement)
    conn.commit()
    _BASELINE_READY = True


def seed_program(code: str = "runtime_v2_program") -> int:
    ensure_runtime_v2_base_tables()
    conn = db()
    row = conn.execute(
        """
        INSERT INTO automation_program (program_code, program_name, status, config_json, created_by, updated_by)
        VALUES (?, ?, 'active', '{}'::jsonb, 'test', 'test')
        RETURNING id
        """,
        (code, code),
    ).fetchone()
    conn.commit()
    return int(row["id"])


def seed_channel(code: str = "runtime_v2_channel") -> int:
    ensure_runtime_v2_base_tables()
    conn = db()
    row = conn.execute(
        """
        INSERT INTO automation_channel (channel_code, channel_name, status, scene_value, owner_staff_id)
        VALUES (?, ?, 'active', ?, 'owner')
        RETURNING id
        """,
        (code, code, code),
    ).fetchone()
    conn.commit()
    return int(row["id"])


def seed_contact(channel_id: int, external: str, first_at: str = "2026-01-01 00:00:00+00") -> int:
    ensure_runtime_v2_base_tables()
    conn = db()
    row = conn.execute(
        """
        INSERT INTO automation_channel_contact (channel_id, external_contact_id, first_channel_entered_at, last_channel_entered_at)
        VALUES (?, ?, ?::timestamptz, ?::timestamptz)
        RETURNING id
        """,
        (int(channel_id), external, first_at, first_at),
    ).fetchone()
    conn.commit()
    return int(row["id"])


def seed_task(
    program_id: int,
    *,
    trigger_type: str = "audience_entered",
    target_stage: str = "operating",
    audience_day_offset: int = 1,
    content_mode: str = "unified",
    content_text: str = "hello",
    segment_contents: list[dict[str, Any]] | None = None,
    agent_config: dict[str, Any] | None = None,
) -> int:
    ensure_runtime_v2_base_tables()
    conn = db()
    row = conn.execute(
        """
        INSERT INTO automation_operation_task (
            program_id, task_name, status, trigger_type, send_time, timezone,
            target_audience_code, target_stage_code, audience_day_offset, behavior_filter, content_mode,
            unified_content_json, segment_contents_json, agent_config_json, created_by, updated_by, published_at
        )
        VALUES (?, 'runtime v2 task', 'active', ?, '10:00', 'Asia/Shanghai', ?, ?, ?, 'none', ?,
                CAST(? AS jsonb), CAST(? AS jsonb), CAST(? AS jsonb), 'test', 'test', CURRENT_TIMESTAMP)
        RETURNING id
        """,
        (
            int(program_id),
            trigger_type,
            target_stage,
            target_stage,
            int(audience_day_offset),
            content_mode,
            json.dumps({"content_text": content_text}, ensure_ascii=False),
            json.dumps(segment_contents or [], ensure_ascii=False),
            json.dumps(agent_config or {}, ensure_ascii=False),
        ),
    ).fetchone()
    conn.commit()
    return int(row["id"])


def seed_agent(agent_code: str = "runtime_agent", *, published: bool = True, role_prompt: str | None = None, task_prompt: str | None = None) -> None:
    conn = db()
    role = role_prompt if role_prompt is not None else ("role" if published else "")
    task = task_prompt if task_prompt is not None else ("请根据问卷生成话术" if published else "")
    conn.execute(
        """
        INSERT INTO automation_agent_config (
            agent_code, display_name, enabled, published_role_prompt, published_task_prompt,
            published_variables_json, published_output_schema_json, published_version
        )
        VALUES (?, ?, TRUE, ?, ?, '[]'::jsonb, '[]'::jsonb, ?)
        ON CONFLICT (agent_code) DO UPDATE
        SET published_role_prompt = EXCLUDED.published_role_prompt,
            published_task_prompt = EXCLUDED.published_task_prompt,
            published_version = EXCLUDED.published_version
        """,
        (agent_code, agent_code, role, task, 1 if published else 0),
    )
    conn.commit()


def count(table: str) -> int:
    return int(db().execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"])
