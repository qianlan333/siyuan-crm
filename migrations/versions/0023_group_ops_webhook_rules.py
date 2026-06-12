"""group ops webhook audience rules and execution logs"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "0023_group_ops_webhook_rules"
down_revision = "0022_next_automation_agents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    params_schema = {
        "lookback_days": {"type": "integer", "default": 30, "label": "观察窗口"},
        "feature_codes": {
            "type": "array",
            "default": ["crm_task_publish", "group_activation", "ai_followup"],
            "label": "核心功能列表",
        },
        "min_usage_count": {"type": "integer", "default": 1, "label": "最小使用次数"},
        "high_intent_chat_count": {
            "type": "integer",
            "default": 3,
            "label": "高意向聊天次数",
        },
    }
    output_schema = {
        "user_id": "string",
        "external_user_id": "string",
        "layer_key": "string",
        "score": "number",
        "reason": "string",
        "computed_at": "datetime",
        "rule_version": "integer",
    }
    refresh_policy = {
        "mode": "manual_or_cron",
        "cron": "0 */2 * * *",
        "timezone": "Asia/Shanghai",
    }

    for column_sql in (
        "ALTER TABLE automation_group_ops_plans ADD COLUMN IF NOT EXISTS default_action_type TEXT NOT NULL DEFAULT 'record_only'",
        "ALTER TABLE automation_group_ops_plans ADD COLUMN IF NOT EXISTS allow_no_sop BOOLEAN NOT NULL DEFAULT TRUE",
        "ALTER TABLE automation_group_ops_plans ADD COLUMN IF NOT EXISTS allow_external_recipients BOOLEAN NOT NULL DEFAULT TRUE",
        "ALTER TABLE automation_group_ops_plans ADD COLUMN IF NOT EXISTS description TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_group_ops_plans ADD COLUMN IF NOT EXISTS signature_secret_hash TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE automation_group_ops_plans ADD COLUMN IF NOT EXISTS last_rotated_at TIMESTAMPTZ",
    ):
        op.execute(column_sql)

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_group_ops_plan_scope (
            id BIGSERIAL PRIMARY KEY,
            plan_id BIGINT NOT NULL REFERENCES automation_group_ops_plans(id) ON DELETE CASCADE,
            scope_type TEXT NOT NULL,
            scope_ref_id TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_group_ops_plan_scope UNIQUE (plan_id, scope_type, scope_ref_id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_group_ops_plan_scope_plan ON automation_group_ops_plan_scope (plan_id, scope_type)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_group_ops_plan_member (
            id BIGSERIAL PRIMARY KEY,
            plan_id BIGINT NOT NULL REFERENCES automation_group_ops_plans(id) ON DELETE CASCADE,
            member_key TEXT NOT NULL,
            user_id TEXT NOT NULL DEFAULT '',
            external_user_id TEXT NOT NULL DEFAULT '',
            group_id TEXT NOT NULL DEFAULT '',
            source_type TEXT NOT NULL DEFAULT '',
            source_ref_id TEXT NOT NULL DEFAULT '',
            layer_key TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active',
            joined_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_group_ops_plan_member_key UNIQUE (plan_id, member_key)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_group_ops_plan_member_external ON automation_group_ops_plan_member (external_user_id, plan_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_group_ops_plan_member_layer ON automation_group_ops_plan_member (plan_id, layer_key, status)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS audience_rule (
            id BIGSERIAL PRIMARY KEY,
            rule_key TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            rule_type TEXT NOT NULL DEFAULT 'module',
            owner TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS audience_rule_version (
            id BIGSERIAL PRIMARY KEY,
            rule_id BIGINT NOT NULL REFERENCES audience_rule(id) ON DELETE CASCADE,
            version INTEGER NOT NULL,
            executor_type TEXT NOT NULL DEFAULT 'module',
            code_or_sql TEXT NOT NULL DEFAULT '',
            params_schema JSONB NOT NULL DEFAULT '{}'::jsonb,
            output_schema JSONB NOT NULL DEFAULT '{}'::jsonb,
            refresh_policy JSONB NOT NULL DEFAULT '{}'::jsonb,
            status TEXT NOT NULL DEFAULT 'active',
            published_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_audience_rule_version UNIQUE (rule_id, version)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS audience_rule_result (
            id BIGSERIAL PRIMARY KEY,
            rule_id BIGINT NOT NULL REFERENCES audience_rule(id) ON DELETE CASCADE,
            rule_version INTEGER NOT NULL,
            plan_id BIGINT NOT NULL REFERENCES automation_group_ops_plans(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL DEFAULT '',
            external_user_id TEXT NOT NULL DEFAULT '',
            layer_key TEXT NOT NULL DEFAULT '',
            score NUMERIC NOT NULL DEFAULT 0,
            reason TEXT NOT NULL DEFAULT '',
            evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            computed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_audience_rule_result_plan ON audience_rule_result (plan_id, rule_id, rule_version, layer_key)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_group_ops_plan_segmentation (
            plan_id BIGINT PRIMARY KEY REFERENCES automation_group_ops_plans(id) ON DELETE CASCADE,
            segmentation_type TEXT NOT NULL DEFAULT 'preset_rule',
            rule_key TEXT NOT NULL,
            rule_version INTEGER NOT NULL,
            params_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            layer_actions_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_group_ops_trigger_event (
            id BIGSERIAL PRIMARY KEY,
            plan_id BIGINT NOT NULL REFERENCES automation_group_ops_plans(id) ON DELETE CASCADE,
            endpoint_key TEXT NOT NULL DEFAULT '',
            event_name TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT '',
            idempotency_key TEXT NOT NULL,
            payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            status TEXT NOT NULL DEFAULT 'accepted',
            received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            processed_at TIMESTAMPTZ,
            error_message TEXT NOT NULL DEFAULT '',
            CONSTRAINT uq_group_ops_trigger_idem UNIQUE (plan_id, idempotency_key)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_group_ops_execution_log (
            id BIGSERIAL PRIMARY KEY,
            trigger_event_id TEXT NOT NULL,
            plan_id BIGINT NOT NULL REFERENCES automation_group_ops_plans(id) ON DELETE CASCADE,
            event_name TEXT NOT NULL DEFAULT '',
            user_id TEXT NOT NULL DEFAULT '',
            external_user_id TEXT NOT NULL DEFAULT '',
            sender JSONB NOT NULL DEFAULT '{}'::jsonb,
            recipient JSONB NOT NULL DEFAULT '{}'::jsonb,
            layer_key TEXT NOT NULL DEFAULT '',
            action_type TEXT NOT NULL DEFAULT '',
            action_ref_id TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT '',
            error_message TEXT NOT NULL DEFAULT '',
            idempotency_key TEXT NOT NULL DEFAULT '',
            received_at TIMESTAMPTZ,
            processed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_group_ops_execution_plan ON automation_group_ops_execution_log (plan_id, created_at DESC)")

    op.execute(
        """
        INSERT INTO audience_rule (rule_key, display_name, description, rule_type, owner, status)
        VALUES (
            'has_used_core_feature',
            '是否使用核心功能',
            '判断用户在指定时间窗口内是否使用过 AI-CRM 核心功能',
            'module',
            'growth_platform',
            'active'
        )
        ON CONFLICT (rule_key) DO NOTHING
        """
    )
    op.execute(
        sa.text(
            """
        INSERT INTO audience_rule_version (
            rule_id, version, executor_type, code_or_sql, params_schema, output_schema, refresh_policy, status, published_at
        )
        SELECT
            id,
            :version,
            :executor_type,
            :code_or_sql,
            CAST(:params_schema AS jsonb),
            CAST(:output_schema AS jsonb),
            CAST(:refresh_policy AS jsonb),
            :status,
            CURRENT_TIMESTAMP
        FROM audience_rule
        WHERE rule_key = :rule_key
        ON CONFLICT (rule_id, version) DO NOTHING
        """
        ).bindparams(
            version=1,
            executor_type="module",
            code_or_sql="builtin:has_used_core_feature",
            params_schema=json.dumps(params_schema, ensure_ascii=False),
            output_schema=json.dumps(output_schema, ensure_ascii=False),
            refresh_policy=json.dumps(refresh_policy, ensure_ascii=False),
            status="active",
            rule_key="has_used_core_feature",
        )
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS automation_group_ops_execution_log")
    op.execute("DROP TABLE IF EXISTS automation_group_ops_trigger_event")
    op.execute("DROP TABLE IF EXISTS automation_group_ops_plan_segmentation")
    op.execute("DROP TABLE IF EXISTS audience_rule_result")
    op.execute("DROP TABLE IF EXISTS audience_rule_version")
    op.execute("DROP TABLE IF EXISTS audience_rule")
    op.execute("DROP TABLE IF EXISTS automation_group_ops_plan_member")
    op.execute("DROP TABLE IF EXISTS automation_group_ops_plan_scope")
