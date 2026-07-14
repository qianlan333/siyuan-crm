"""activate questionnaire continuations without replaying shadow history.

Revision ID: 0109_questionnaire_auto_execute
Revises: 0108_customer_read_model_refresh
"""

from __future__ import annotations

from alembic import op


revision = "0109_questionnaire_auto_execute"
down_revision = "0108_customer_read_model_refresh"
branch_labels = None
depends_on = None


_CUTOVER_SQL = "TIMESTAMPTZ '2026-07-13 16:20:00+00'"


def upgrade() -> None:
    # Questionnaire events before this cutover were deliberately shadow-only.
    # Record an auditable terminal skip before the runtime pair allowlist is
    # enabled so those historical rows can never produce delayed webhooks or
    # WeCom mutations.
    op.execute(
        f"""
        INSERT INTO internal_event_consumer_attempt (
            attempt_id,
            consumer_run_id,
            consumer_name,
            status,
            request_summary_json,
            response_summary_json,
            error_code,
            error_message,
            started_at,
            completed_at
        )
        SELECT
            'iea_questionnaire_cutover_' || run.id::text,
            run.id,
            run.consumer_name,
            'skipped',
            jsonb_build_object(
                'cutover_skip', TRUE,
                'from_status', run.status,
                'cutover_at', '2026-07-13T16:20:00Z'
            ),
            jsonb_build_object(
                'skipped', TRUE,
                'reason', 'questionnaire_shadow_before_auto_execute_cutover'
            ),
            'questionnaire_shadow_before_auto_execute_cutover',
            'historical shadow continuation was not replayed',
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        FROM internal_event_consumer_run run
        JOIN internal_event event ON event.event_id = run.event_id
        WHERE event.event_type = 'questionnaire.submitted'
          AND event.created_at < {_CUTOVER_SQL}
          AND run.consumer_name IN (
              'questionnaire_projection_consumer',
              'questionnaire_webhook_consumer',
              'questionnaire_tag_consumer',
              'automation_questionnaire_consumer',
              'customer_summary_consumer'
          )
          AND run.status IN ('pending', 'failed_retryable')
        ON CONFLICT (attempt_id) DO NOTHING
        """
    )
    op.execute(
        f"""
        UPDATE internal_event_consumer_run run
        SET status = 'skipped',
            next_retry_at = NULL,
            locked_at = NULL,
            locked_by = '',
            lease_token = '',
            last_attempt_id = 'iea_questionnaire_cutover_' || run.id::text,
            last_error_code = 'questionnaire_shadow_before_auto_execute_cutover',
            last_error_message = 'historical shadow continuation was not replayed',
            result_summary_json = COALESCE(run.result_summary_json, '{{}}'::jsonb) ||
                jsonb_build_object(
                    'skipped', TRUE,
                    'reason', 'questionnaire_shadow_before_auto_execute_cutover',
                    'cutover_at', '2026-07-13T16:20:00Z'
                ),
            finished_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        FROM internal_event event
        WHERE event.event_id = run.event_id
          AND event.event_type = 'questionnaire.submitted'
          AND event.created_at < {_CUTOVER_SQL}
          AND run.consumer_name IN (
              'questionnaire_projection_consumer',
              'questionnaire_webhook_consumer',
              'questionnaire_tag_consumer',
              'automation_questionnaire_consumer',
              'customer_summary_consumer'
          )
          AND run.status IN ('pending', 'failed_retryable')
        """
    )


def downgrade() -> None:
    # Reopening terminal shadow rows during rollback could execute historical
    # external work.  The data transition is intentionally one-way; older code
    # remains compatible with skipped consumer runs.
    pass
