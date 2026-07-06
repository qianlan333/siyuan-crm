"""retire legacy webhook deprecations"""

from __future__ import annotations

from alembic import op


revision = "0044_retire_legacy_webhook_deprecations"
down_revision = "0043_internal_event_queue"
branch_labels = None
depends_on = None


LEGACY_VALUES_SQL = """
VALUES
    ('old_payment_direct_automation_bridge', 'direct_automation', 'public_product.h5_wechat_pay.process_payment_succeeded_event', 'payment'),
    ('old_ai_assist_direct_send', 'direct_send', '/api/ai-assist/legacy/direct-send', 'ai_assist'),
    ('old_ai_assist_webhook_outbound', 'webhook_outbound', '/api/ai-assist/legacy/webhook-outbound', 'ai_assist'),
    ('old_ai_assist_campaign_run_due_direct', 'campaign_run_due_direct', '/api/cloud-orchestrator/campaigns/run-due', 'cloud_orchestrator'),
    ('old_group_ops_queue_gateway_send', 'queue_gateway', 'integration_gateway.wecom_group_adapter.queue_gateway', 'group_ops'),
    ('old_group_ops_broadcast_job_send', 'broadcast_job', '/api/admin/broadcast-jobs/*/send', 'group_ops'),
    ('old_broadcast_jobs_direct_approve_cancel', 'broadcast_job_control_plane', '/api/admin/broadcast-jobs/{job_id}/approve|cancel', 'admin_jobs'),
    ('old_group_ops_webhook_outbound', 'webhook_outbound', '/api/automation/group-ops/webhooks/{webhook_key}', 'group_ops'),
    ('old_questionnaire_sync_external_push', 'sync_webhook', 'questionnaire.deliver_questionnaire_external_push', 'questionnaire'),
    ('old_order_webhook_push', 'webhook_outbound', 'commerce.domain_event_outbox_legacy_delivery', 'commerce'),
    ('old_external_push_outbox_worker', 'webhook_outbox_worker', 'external_push.service.run_due_external_push_events', 'external_push'),
    ('old_external_push_delivery_retry', 'webhook_retry', 'external_push.service.retry_order_delivery', 'external_push'),
    ('old_payment_refund_direct_request', 'payment_refund_request', '/api/admin/refunds|/api/admin/wechat-pay/orders/{order_id}/refunds', 'commerce'),
    ('old_admin_jobs_deferred_run', 'deferred_job_runner', '/api/admin/jobs/deferred-jobs/run', 'admin_jobs'),
    ('old_customer_webhook_delivery_retry', 'webhook_retry', '/api/admin/jobs/webhook-deliveries/*/retry', 'admin_jobs'),
    ('old_broadcast_jobs_feishu_hourly_report', 'feishu_notification', '/api/admin/broadcast-jobs/feishu-hourly-report/run', 'admin_jobs'),
    ('old_owner_migration_legacy_execute_path', 'legacy_application_path', 'owner_migration.OwnerMigrationService._run_legacy', 'owner_migration'),
    ('old_external_direct_wecom_webhook_payment_feishu_openclaw', 'direct_external_call', 'legacy_external_adapters/*', 'platform_foundation')
"""


def upgrade() -> None:
    op.execute(
        f"""
        INSERT INTO legacy_webhook_deprecation_registry (
            legacy_key, legacy_type, legacy_route, legacy_module, status,
            deprecated_at, deprecated_by, deprecation_reason, replacement_route,
            delete_scheduled_at, delete_status, delete_job_id, notes_json,
            created_at, updated_at
        )
        SELECT
            legacy_key,
            legacy_type,
            legacy_route,
            legacy_module,
            'deleted',
            CURRENT_TIMESTAMP,
            'p0_1_external_effect_queue_migration',
            'All outbound effects now use External Effect Queue',
            '/admin/push-center',
            CURRENT_TIMESTAMP,
            'deleted',
            'migration_0044_retire_legacy_webhook_deprecations',
            jsonb_build_object(
                'replacement_capability', 'external_effect_queue',
                'real_external_call_executed', false,
                'physical_delete', false,
                'retired_by_migration', '0044_retire_legacy_webhook_deprecations',
                'history_data_deleted', false
            ),
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        FROM ({LEGACY_VALUES_SQL}) AS defaults(legacy_key, legacy_type, legacy_route, legacy_module)
        ON CONFLICT (legacy_key) DO UPDATE
        SET legacy_type = EXCLUDED.legacy_type,
            legacy_route = EXCLUDED.legacy_route,
            legacy_module = EXCLUDED.legacy_module,
            status = 'deleted',
            delete_status = 'deleted',
            delete_job_id = 'migration_0044_retire_legacy_webhook_deprecations',
            replacement_route = '/admin/push-center',
            deprecated_at = COALESCE(legacy_webhook_deprecation_registry.deprecated_at, EXCLUDED.deprecated_at),
            deprecated_by = COALESCE(NULLIF(legacy_webhook_deprecation_registry.deprecated_by, ''), EXCLUDED.deprecated_by),
            deprecation_reason = COALESCE(NULLIF(legacy_webhook_deprecation_registry.deprecation_reason, ''), EXCLUDED.deprecation_reason),
            delete_scheduled_at = COALESCE(legacy_webhook_deprecation_registry.delete_scheduled_at, EXCLUDED.delete_scheduled_at),
            notes_json = legacy_webhook_deprecation_registry.notes_json || EXCLUDED.notes_json,
            updated_at = CURRENT_TIMESTAMP
        """
    )
    op.execute(
        f"""
        INSERT INTO legacy_webhook_cleanup_audit (
            audit_id, legacy_key, action, operator, before_json, after_json, created_at
        )
        SELECT
            'migration_0044_retired_' || legacy_key,
            legacy_key,
            'retire_legacy_entry_by_migration',
            'migration_0044_retire_legacy_webhook_deprecations',
            '{{}}'::jsonb,
            jsonb_build_object(
                'legacy_key', legacy_key,
                'status', 'deleted',
                'delete_status', 'deleted',
                'delete_job_id', 'migration_0044_retire_legacy_webhook_deprecations',
                'history_data_deleted', false,
                'real_external_call_executed', false
            ),
            CURRENT_TIMESTAMP
        FROM ({LEGACY_VALUES_SQL}) AS defaults(legacy_key, legacy_type, legacy_route, legacy_module)
        ON CONFLICT (audit_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE legacy_webhook_deprecation_registry
        SET status = 'deprecated',
            delete_status = 'scheduled',
            delete_job_id = '',
            notes_json = notes_json - 'retired_by_migration',
            updated_at = CURRENT_TIMESTAMP
        WHERE delete_job_id = 'migration_0044_retire_legacy_webhook_deprecations'
        """
    )
    op.execute(
        """
        DELETE FROM legacy_webhook_cleanup_audit
        WHERE audit_id LIKE 'migration_0044_retired_%'
        """
    )
