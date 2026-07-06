"""skip obsolete ai audience member outbound consumer backlog.

Revision ID: 0062_skip_obsolete_ai_audience_member_outbound
Revises: 0061_automation_agent_type_fixed_script
"""

from __future__ import annotations

from alembic import op


revision = "0062_skip_obsolete_ai_audience_member_outbound"
down_revision = "0061_automation_agent_type_fixed_script"
branch_labels = None
depends_on = None


def upgrade() -> None:
    _backfill_run_refreshed_events_for_pending_entered_member_runs()
    _skip_obsolete_member_outbound_runs()


def downgrade() -> None:
    # Irreversible cleanup of obsolete queue rows; previous releases can still
    # re-create needed runs from internal_event if the old consumer is restored.
    pass


def _backfill_run_refreshed_events_for_pending_entered_member_runs() -> None:
    op.execute(
        """
        WITH pending_entered_runs AS (
            SELECT
                m.run_id,
                m.package_id,
                MIN(COALESCE(e.occurred_at, m.occurred_at, CURRENT_TIMESTAMP)) AS occurred_at,
                COUNT(*) AS pending_entered_count
            FROM internal_event_consumer_run r
            JOIN internal_event e ON e.event_id = r.event_id
            JOIN ai_audience_member_event m ON m.id::text = e.aggregate_id
            WHERE r.consumer_name = 'ai_audience_outbound_effect_planner'
              AND r.status IN ('pending', 'failed_retryable', 'blocked')
              AND e.event_type = 'ai_audience.member.entered'
              AND COALESCE(m.run_id, 0) > 0
            GROUP BY m.run_id, m.package_id
        )
        INSERT INTO internal_event (
            tenant_id, event_id, event_type, event_version, aggregate_type, aggregate_id,
            subject_type, subject_id, idempotency_key, actor_id, actor_type,
            source_module, source_route, occurred_at, payload_json, payload_summary_json, created_at
        )
        SELECT
            'aicrm',
            'iev_backfill_' || md5('ai_audience.run.refreshed:' || pending.run_id::text),
            'ai_audience.run.refreshed',
            1,
            'ai_audience_package_run',
            pending.run_id::text,
            'ai_audience_package',
            pending.package_id::text,
            'ai_audience.run.refreshed:' || pending.run_id::text,
            'ai_audience_refresh_backfill',
            'system',
            'ai_audience_ops.migration_0062',
            'ai_audience.refresh_backfill',
            pending.occurred_at,
            jsonb_build_object(
                'run_id', pending.run_id,
                'run_type', COALESCE(run.run_type, 'backfill'),
                'package_id', pending.package_id,
                'package_key', pkg.package_key,
                'package_name', pkg.name,
                'returned_count', COALESCE(run.returned_count, 0),
                'entered_count', COALESCE(run.entered_count, pending.pending_entered_count),
                'updated_count', COALESCE(run.updated_count, 0),
                'exited_count', COALESCE(run.exited_count, 0),
                'member_event_count', COALESCE(run.member_event_count, pending.pending_entered_count),
                'backfilled_from_member_entered_consumer_runs', true
            ),
            jsonb_build_object(
                'run_id', pending.run_id,
                'package_key', pkg.package_key,
                'entered_count', COALESCE(run.entered_count, pending.pending_entered_count),
                'backfill', true
            ),
            CURRENT_TIMESTAMP
        FROM pending_entered_runs pending
        LEFT JOIN ai_audience_package_run run ON run.id = pending.run_id
        LEFT JOIN ai_audience_package pkg ON pkg.id = pending.package_id
        ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
        """
    )
    op.execute(
        """
        WITH pending_entered_runs AS (
            SELECT DISTINCT m.run_id
            FROM internal_event_consumer_run r
            JOIN internal_event e ON e.event_id = r.event_id
            JOIN ai_audience_member_event m ON m.id::text = e.aggregate_id
            WHERE r.consumer_name = 'ai_audience_outbound_effect_planner'
              AND r.status IN ('pending', 'failed_retryable', 'blocked')
              AND e.event_type = 'ai_audience.member.entered'
              AND COALESCE(m.run_id, 0) > 0
        )
        INSERT INTO internal_event_consumer_run (
            tenant_id, event_id, consumer_name, consumer_type, status,
            attempt_count, max_attempts, created_at, updated_at
        )
        SELECT
            event.tenant_id,
            event.event_id,
            'ai_audience_outbound_effect_planner',
            'external_effect_planner',
            'pending',
            0,
            5,
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        FROM pending_entered_runs pending
        JOIN internal_event event
          ON event.tenant_id = 'aicrm'
         AND event.idempotency_key = 'ai_audience.run.refreshed:' || pending.run_id::text
        ON CONFLICT (tenant_id, event_id, consumer_name) DO NOTHING
        """
    )


def _skip_obsolete_member_outbound_runs() -> None:
    op.execute(
        """
        UPDATE internal_event_consumer_run r
        SET status = 'skipped',
            next_retry_at = NULL,
            locked_at = NULL,
            locked_by = '',
            last_error_code = 'ai_audience_member_outbound_replaced_by_run_refreshed',
            last_error_message = 'AI Audience outbound planning now runs once per refresh run via ai_audience.run.refreshed; per-member outbound runs are obsolete.',
            result_summary_json = jsonb_build_object(
                'skipped', true,
                'reason', 'run_level_outbound_replaced_member_outbound',
                'replacement_event_type', 'ai_audience.run.refreshed',
                'real_external_call_executed', false
            ),
            finished_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        FROM internal_event e
        LEFT JOIN ai_audience_member_event m
          ON m.id::text = e.aggregate_id
         AND e.event_type = 'ai_audience.member.entered'
        WHERE r.event_id = e.event_id
          AND r.consumer_name = 'ai_audience_outbound_effect_planner'
          AND r.status IN ('pending', 'failed_retryable', 'blocked')
          AND (
              e.event_type IN ('ai_audience.member.updated', 'ai_audience.member.exited')
              OR (e.event_type = 'ai_audience.member.entered' AND COALESCE(m.run_id, 0) > 0)
          )
        """
    )
