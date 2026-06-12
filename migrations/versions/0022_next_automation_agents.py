"""next automation agents metadata table"""

from __future__ import annotations

from alembic import op

revision = "0022_next_automation_agents"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_agents (
            id BIGSERIAL PRIMARY KEY,
            program_id BIGINT NOT NULL DEFAULT 0,
            workflow_id BIGINT NOT NULL DEFAULT 0,
            node_id BIGINT NOT NULL DEFAULT 0,
            task_id BIGINT NOT NULL DEFAULT 0,
            agent_code TEXT NOT NULL,
            agent_name TEXT NOT NULL DEFAULT '',
            agent_type TEXT NOT NULL DEFAULT 'assistant',
            status TEXT NOT NULL DEFAULT 'active',
            sort_order INTEGER NOT NULL DEFAULT 0,
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            config_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            created_by TEXT NOT NULL DEFAULT '',
            updated_by TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            archived_at TEXT NOT NULL DEFAULT '',
            CONSTRAINT uq_automation_agents_workflow_code UNIQUE (workflow_id, agent_code)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_automation_agents_program ON automation_agents (program_id, enabled, sort_order ASC, id ASC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_automation_agents_workflow ON automation_agents (workflow_id, node_id, task_id, sort_order ASC, id ASC)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_agent_idempotency (
            id BIGSERIAL PRIMARY KEY,
            route_family TEXT NOT NULL,
            operation TEXT NOT NULL,
            operator TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            request_hash TEXT NOT NULL,
            response_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
            resource_type TEXT NOT NULL DEFAULT 'agent',
            resource_id BIGINT,
            status TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_automation_agent_idempotency_scope
                UNIQUE (route_family, operation, operator, idempotency_key)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_agent_audit_log (
            id BIGSERIAL PRIMARY KEY,
            route_family TEXT NOT NULL,
            operation TEXT NOT NULL,
            operator TEXT NOT NULL,
            resource_type TEXT NOT NULL DEFAULT 'agent',
            resource_id BIGINT,
            before_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
            after_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
            request_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            validation_result JSONB NOT NULL DEFAULT '{}'::jsonb,
            rollback_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            side_effect_safety JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        INSERT INTO automation_agents (
            program_id, workflow_id, node_id, task_id, agent_code, agent_name, agent_type,
            status, sort_order, metadata_json, config_json, enabled, created_by, updated_by
        )
        VALUES
            (0, 0, 0, 0, 'central_router_agent', '中央路由 Agent', 'classifier', 'active', 10, '{"source":"next_default_seed"}'::jsonb, '{}'::jsonb, TRUE, 'system', 'system'),
            (0, 0, 0, 0, 'welcome_agent', '欢迎接待 Agent', 'assistant', 'active', 20, '{"source":"next_default_seed"}'::jsonb, '{}'::jsonb, TRUE, 'system', 'system'),
            (0, 0, 0, 0, 'pricing_agent', '价格答疑 Agent', 'assistant', 'active', 30, '{"source":"next_default_seed"}'::jsonb, '{}'::jsonb, TRUE, 'system', 'system'),
            (0, 0, 0, 0, 'proof_agent', '案例证明 Agent', 'assistant', 'active', 40, '{"source":"next_default_seed"}'::jsonb, '{}'::jsonb, TRUE, 'system', 'system'),
            (0, 0, 0, 0, 'closing_agent', '成交推进 Agent', 'followup', 'active', 50, '{"source":"next_default_seed"}'::jsonb, '{}'::jsonb, TRUE, 'system', 'system')
        ON CONFLICT (workflow_id, agent_code) DO NOTHING
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.automation_agent_config') IS NOT NULL THEN
                INSERT INTO automation_agents (
                    program_id, workflow_id, node_id, task_id, agent_code, agent_name, agent_type,
                    status, sort_order, metadata_json, config_json, enabled, created_by, updated_by
                )
                SELECT
                    0,
                    0,
                    0,
                    0,
                    agent_code,
                    COALESCE(NULLIF(display_name, ''), agent_code),
                    'assistant',
                    CASE WHEN COALESCE(enabled, FALSE) IS TRUE THEN 'active' ELSE 'disabled' END,
                    100 + ROW_NUMBER() OVER (ORDER BY updated_at DESC, id DESC),
                    jsonb_build_object('source', 'legacy_automation_agent_config_backfill'),
                    jsonb_build_object('scenario_code', scenario_code),
                    COALESCE(enabled, FALSE),
                    'legacy_backfill',
                    'legacy_backfill'
                FROM automation_agent_config
                WHERE COALESCE(agent_code, '') <> ''
                ON CONFLICT (workflow_id, agent_code) DO NOTHING;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS automation_agent_audit_log")
    op.execute("DROP TABLE IF EXISTS automation_agent_idempotency")
    op.execute("DROP TABLE IF EXISTS automation_agents")
