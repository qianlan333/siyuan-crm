"""cloud orchestrator + journey cadence + frequency budget + audit

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-06

Lays the data substrate for the three-end automation operations product:

- Operations cadence: ``automation_workflow_goal`` (per-workflow KPI),
  ``automation_workflow_node_transition`` (branch / interrupt rules)
- Frequency budget: ``automation_frequency_budget`` (config) +
  ``automation_frequency_consumption`` (sliding-window log)
- Cloud orchestrator drafts: ``cloud_broadcast_plans``
- Cross-end audit & traceability: ``cloud_agent_audit_log`` plus ``trace_id``
  columns on ``automation_agent_run`` / ``outbound_tasks`` /
  ``automation_touch_delivery_log``
- Workflow extensions: ``review_status``, ``created_by_agent`` (agent-drafted
  workflows that need human approval)
- Agent config: ``scenario_code`` (one_to_one / bulk_activation /
  silent_wake / journey_step) so the existing copy-AI workorder pipeline can
  serve broadcast scenarios in addition to single-conversation replies
- Execution-item observability: ``last_error_text`` / ``last_error_at`` /
  ``retry_count``
- Aggregated interaction stats view ``automation_member_interaction_stats``

All DDL uses ``IF NOT EXISTS`` / pre-checks so re-running on a database that
was bootstrapped from ``schema.sql`` (which ships the same definitions) is a
no-op.
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import text


revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | None = None
depends_on: str | None = None


def _is_postgres() -> bool:
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    if _is_postgres():
        row = bind.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = :t AND column_name = :c"
            ),
            {"t": table, "c": column},
        ).first()
        return bool(row)
    rows = bind.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return any(r[1] == column for r in rows)


def _add_column(table: str, column_def: str, column_name: str) -> None:
    if not _has_column(table, column_name):
        op.execute(f"ALTER TABLE {table} ADD COLUMN {column_def}")


def upgrade() -> None:
    # ----- Module A: 运营节奏中枢 --------------------------------------------

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_workflow_goal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workflow_id INTEGER NOT NULL,
            goal_code TEXT NOT NULL,
            goal_label TEXT NOT NULL DEFAULT '',
            success_event_action TEXT NOT NULL DEFAULT '',
            weight INTEGER NOT NULL DEFAULT 100,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_workflow_goal
        ON automation_workflow_goal (workflow_id, goal_code)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_workflow_goal_workflow
        ON automation_workflow_goal (workflow_id, enabled, weight DESC, id ASC)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_workflow_node_transition (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_node_id INTEGER NOT NULL,
            to_node_id INTEGER,
            condition_kind TEXT NOT NULL DEFAULT 'reply_received',
            condition_payload_json TEXT NOT NULL DEFAULT '{}',
            action TEXT NOT NULL DEFAULT 'goto_node',
            priority INTEGER NOT NULL DEFAULT 0,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_workflow_node_transition_from
        ON automation_workflow_node_transition (from_node_id, enabled, priority DESC, id ASC)
        """
    )

    # 频次预算（跨 program / 跨渠道）
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_frequency_budget (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            budget_code TEXT NOT NULL UNIQUE,
            scope TEXT NOT NULL DEFAULT 'global',
            scope_key TEXT NOT NULL DEFAULT '',
            window_seconds INTEGER NOT NULL DEFAULT 604800,
            max_count INTEGER NOT NULL DEFAULT 3,
            description TEXT NOT NULL DEFAULT '',
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_frequency_budget_enabled
        ON automation_frequency_budget (enabled, scope, scope_key, id ASC)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_frequency_consumption (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            budget_id INTEGER NOT NULL,
            member_id INTEGER,
            external_contact_id TEXT NOT NULL DEFAULT '',
            consumed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            source_kind TEXT NOT NULL DEFAULT '',
            source_id TEXT NOT NULL DEFAULT '',
            trace_id TEXT NOT NULL DEFAULT ''
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_frequency_consumption_member_window
        ON automation_frequency_consumption (member_id, budget_id, consumed_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_frequency_consumption_external_window
        ON automation_frequency_consumption (external_contact_id, budget_id, consumed_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_frequency_consumption_trace
        ON automation_frequency_consumption (trace_id, id ASC)
        """
    )

    # ----- Module B/D: Cloud 端草稿 + 话术工单关联 ---------------------------

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cloud_broadcast_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id TEXT NOT NULL UNIQUE,
            trace_id TEXT NOT NULL DEFAULT '',
            session_id TEXT NOT NULL DEFAULT '',
            operator TEXT NOT NULL DEFAULT '',
            intent TEXT NOT NULL DEFAULT '',
            selection_json TEXT NOT NULL DEFAULT '{}',
            content_strategy TEXT NOT NULL DEFAULT 'profile_layered',
            content_template TEXT NOT NULL DEFAULT '',
            personalization_json TEXT NOT NULL DEFAULT '[]',
            max_recipients INTEGER NOT NULL DEFAULT 0,
            candidate_count INTEGER NOT NULL DEFAULT 0,
            skipped_count INTEGER NOT NULL DEFAULT 0,
            explanation_json TEXT NOT NULL DEFAULT '{}',
            variants_json TEXT NOT NULL DEFAULT '[]',
            copy_workorder_run_ids TEXT NOT NULL DEFAULT '[]',
            requires_manual_copy INTEGER NOT NULL DEFAULT 0,
            simulate_summary_json TEXT NOT NULL DEFAULT '{}',
            commit_batch_id TEXT NOT NULL DEFAULT '',
            commit_send_record_id INTEGER,
            committed_at TEXT NOT NULL DEFAULT '',
            committed_by TEXT NOT NULL DEFAULT '',
            approval_token_hash TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'draft',
            error_message TEXT NOT NULL DEFAULT '',
            expires_at TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_cloud_broadcast_plans_status
        ON cloud_broadcast_plans (status, expires_at, id DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_cloud_broadcast_plans_trace
        ON cloud_broadcast_plans (trace_id, id DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_cloud_broadcast_plans_session
        ON cloud_broadcast_plans (session_id, created_at DESC, id DESC)
        """
    )

    # ----- Module E: 审计与可观察性 -----------------------------------------

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cloud_agent_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL DEFAULT '',
            trace_id TEXT NOT NULL DEFAULT '',
            operator TEXT NOT NULL DEFAULT '',
            tool_name TEXT NOT NULL DEFAULT '',
            arguments_hash TEXT NOT NULL DEFAULT '',
            arguments_json TEXT NOT NULL DEFAULT '{}',
            result_summary TEXT NOT NULL DEFAULT '',
            latency_ms INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'success',
            error_message TEXT NOT NULL DEFAULT '',
            requires_token INTEGER NOT NULL DEFAULT 0,
            token_verified INTEGER NOT NULL DEFAULT 0,
            full_payload_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_cloud_agent_audit_log_session
        ON cloud_agent_audit_log (session_id, created_at DESC, id DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_cloud_agent_audit_log_trace
        ON cloud_agent_audit_log (trace_id, created_at DESC, id DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_cloud_agent_audit_log_tool
        ON cloud_agent_audit_log (tool_name, status, created_at DESC, id DESC)
        """
    )

    # ----- Approval Token (UI 签发后单次有效) -------------------------------

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cloud_approval_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_hash TEXT NOT NULL UNIQUE,
            plan_id TEXT NOT NULL DEFAULT '',
            operator TEXT NOT NULL DEFAULT '',
            scope TEXT NOT NULL DEFAULT 'commit_broadcast_plan',
            issued_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            expires_at TEXT NOT NULL DEFAULT '',
            consumed_at TEXT NOT NULL DEFAULT '',
            consumed_by TEXT NOT NULL DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_cloud_approval_tokens_plan
        ON cloud_approval_tokens (plan_id, issued_at DESC, id DESC)
        """
    )

    # ----- 字段扩展 -----------------------------------------------------------

    # automation_agent_config: scenario_code 区分 single-chat / bulk / wake / journey
    _add_column(
        "automation_agent_config",
        "scenario_code TEXT NOT NULL DEFAULT 'one_to_one'",
        "scenario_code",
    )

    # automation_agent_run: trace_id 贯穿三端
    _add_column(
        "automation_agent_run",
        "trace_id TEXT NOT NULL DEFAULT ''",
        "trace_id",
    )

    # outbound_tasks: trace_id
    _add_column(
        "outbound_tasks",
        "trace_id TEXT NOT NULL DEFAULT ''",
        "trace_id",
    )

    # automation_touch_delivery_log: trace_id
    _add_column(
        "automation_touch_delivery_log",
        "trace_id TEXT NOT NULL DEFAULT ''",
        "trace_id",
    )

    # automation_workflow: review_status + created_by_agent
    _add_column(
        "automation_workflow",
        "review_status TEXT NOT NULL DEFAULT 'approved'",
        "review_status",
    )
    _add_column(
        "automation_workflow",
        "created_by_agent TEXT NOT NULL DEFAULT ''",
        "created_by_agent",
    )

    # automation_workflow_execution_item: 错误观察字段
    _add_column(
        "automation_workflow_execution_item",
        "last_error_text TEXT NOT NULL DEFAULT ''",
        "last_error_text",
    )
    _add_column(
        "automation_workflow_execution_item",
        "last_error_at TEXT NOT NULL DEFAULT ''",
        "last_error_at",
    )
    _add_column(
        "automation_workflow_execution_item",
        "retry_count INTEGER NOT NULL DEFAULT 0",
        "retry_count",
    )
    _add_column(
        "automation_workflow_execution_item",
        "trace_id TEXT NOT NULL DEFAULT ''",
        "trace_id",
    )
    _add_column(
        "automation_workflow_execution_item",
        "next_node_id INTEGER",
        "next_node_id",
    )

    # 索引：触达日志按 trace 查、按 member+sent_at 查
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_touch_delivery_trace
        ON automation_touch_delivery_log (trace_id, created_at DESC, id DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_touch_delivery_member_sent
        ON automation_touch_delivery_log (member_id, sent_at DESC, id DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_outbound_tasks_trace
        ON outbound_tasks (trace_id, id DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_agent_run_trace
        ON automation_agent_run (trace_id, created_at DESC, id DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_agent_config_scenario
        ON automation_agent_config (scenario_code, enabled, updated_at DESC, id DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_workflow_review
        ON automation_workflow (review_status, status, updated_at DESC, id DESC)
        """
    )

    # ----- 互动聚合视图 -------------------------------------------------------

    op.execute("DROP VIEW IF EXISTS automation_member_interaction_stats")
    if _is_postgres():
        op.execute(
            """
            CREATE VIEW automation_member_interaction_stats AS
            SELECT
                m.id AS member_id,
                m.external_contact_id,
                m.phone,
                m.current_pool,
                m.current_audience_code,
                m.profile_segment_key,
                m.behavior_tier_key,
                m.last_ai_push_at,
                m.ai_cooldown_until,
                (
                    SELECT MAX(sent_at) FROM automation_touch_delivery_log d
                    WHERE d.member_id = m.id AND d.status = 'sent'
                ) AS last_outbound_at,
                (
                    SELECT COUNT(*) FROM automation_touch_delivery_log d
                    WHERE d.member_id = m.id AND d.status = 'sent'
                ) AS outbound_count_total,
                (
                    SELECT COUNT(*) FROM automation_touch_delivery_log d
                    WHERE d.member_id = m.id AND d.status = 'sent'
                      AND d.sent_at >= (NOW() - INTERVAL '7 days')::text
                ) AS outbound_count_7d,
                (
                    SELECT COUNT(*) FROM automation_touch_delivery_log d
                    WHERE d.member_id = m.id AND d.status = 'sent'
                      AND d.sent_at >= (NOW() - INTERVAL '30 days')::text
                ) AS outbound_count_30d,
                (
                    SELECT MAX(pushed_at) FROM automation_ai_push_log p
                    WHERE p.member_id = m.id
                ) AS last_ai_push_log_at,
                (
                    SELECT COUNT(*) FROM automation_ai_push_log p
                    WHERE p.member_id = m.id
                      AND p.pushed_at >= (NOW() - INTERVAL '30 days')::text
                ) AS ai_push_count_30d
            FROM automation_member m
            """
        )
    else:
        op.execute(
            """
            CREATE VIEW automation_member_interaction_stats AS
            SELECT
                m.id AS member_id,
                m.external_contact_id,
                m.phone,
                m.current_pool,
                m.current_audience_code,
                m.profile_segment_key,
                m.behavior_tier_key,
                m.last_ai_push_at,
                m.ai_cooldown_until,
                (
                    SELECT MAX(sent_at) FROM automation_touch_delivery_log d
                    WHERE d.member_id = m.id AND d.status = 'sent'
                ) AS last_outbound_at,
                (
                    SELECT COUNT(*) FROM automation_touch_delivery_log d
                    WHERE d.member_id = m.id AND d.status = 'sent'
                ) AS outbound_count_total,
                (
                    SELECT COUNT(*) FROM automation_touch_delivery_log d
                    WHERE d.member_id = m.id AND d.status = 'sent'
                      AND d.sent_at >= datetime('now', '-7 days')
                ) AS outbound_count_7d,
                (
                    SELECT COUNT(*) FROM automation_touch_delivery_log d
                    WHERE d.member_id = m.id AND d.status = 'sent'
                      AND d.sent_at >= datetime('now', '-30 days')
                ) AS outbound_count_30d,
                (
                    SELECT MAX(pushed_at) FROM automation_ai_push_log p
                    WHERE p.member_id = m.id
                ) AS last_ai_push_log_at,
                (
                    SELECT COUNT(*) FROM automation_ai_push_log p
                    WHERE p.member_id = m.id
                      AND p.pushed_at >= datetime('now', '-30 days')
                ) AS ai_push_count_30d
            FROM automation_member m
            """
        )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS automation_member_interaction_stats")

    op.execute("DROP INDEX IF EXISTS idx_automation_workflow_review")
    op.execute("DROP INDEX IF EXISTS idx_automation_agent_config_scenario")
    op.execute("DROP INDEX IF EXISTS idx_automation_agent_run_trace")
    op.execute("DROP INDEX IF EXISTS idx_outbound_tasks_trace")
    op.execute("DROP INDEX IF EXISTS idx_automation_touch_delivery_member_sent")
    op.execute("DROP INDEX IF EXISTS idx_automation_touch_delivery_trace")

    op.execute("DROP TABLE IF EXISTS cloud_approval_tokens")
    op.execute("DROP TABLE IF EXISTS cloud_agent_audit_log")
    op.execute("DROP TABLE IF EXISTS cloud_broadcast_plans")
    op.execute("DROP TABLE IF EXISTS automation_frequency_consumption")
    op.execute("DROP TABLE IF EXISTS automation_frequency_budget")
    op.execute("DROP TABLE IF EXISTS automation_workflow_node_transition")
    op.execute("DROP TABLE IF EXISTS automation_workflow_goal")

    if _is_postgres():
        for table, column in (
            ("automation_workflow_execution_item", "next_node_id"),
            ("automation_workflow_execution_item", "trace_id"),
            ("automation_workflow_execution_item", "retry_count"),
            ("automation_workflow_execution_item", "last_error_at"),
            ("automation_workflow_execution_item", "last_error_text"),
            ("automation_workflow", "created_by_agent"),
            ("automation_workflow", "review_status"),
            ("automation_touch_delivery_log", "trace_id"),
            ("outbound_tasks", "trace_id"),
            ("automation_agent_run", "trace_id"),
            ("automation_agent_config", "scenario_code"),
        ):
            op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {column}")
