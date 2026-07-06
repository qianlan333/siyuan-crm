from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "queue" / "internal-event-queue.md"
RUNBOOK = ROOT / "docs" / "queue" / "internal-event-queue-gray-runbook.md"


def test_internal_event_queue_doc_defines_external_effect_boundary_and_config() -> None:
    source = DOC.read_text(encoding="utf-8")

    for required in [
        "internal_event` records a business fact",
        "internal_event_consumer_run` records one execution state",
        "external_effect_job` records only external side-effect work",
        "AICRM_INTERNAL_EVENTS_ENABLED=0",
        "AICRM_INTERNAL_EVENTS_PAYMENT_ENABLED=0",
        "AICRM_INTERNAL_EVENTS_SHADOW_ONLY=1",
        "AICRM_INTERNAL_EVENTS_ALLOWED_EVENT_TYPES=",
        "AICRM_INTERNAL_EVENT_WORKER_BATCH_SIZE=50",
        "python scripts/run_internal_event_worker.py",
        "--execute --limit 1 --event-types payment.succeeded",
    ]:
        assert required in source


def test_internal_event_gray_runbook_has_payment_rollout_and_rollback_steps() -> None:
    source = RUNBOOK.read_text(encoding="utf-8")

    for required in [
        "shadow emit only",
        "/api/admin/internal-events/diagnostics",
        "/api/admin/internal-events/run-due/preview",
        '\"dry_run\":true',
        '\"batch_size\":1',
        "order_projection_consumer",
        "webhook_order_paid_consumer",
        "/api/admin/external-effects?effect_type=webhook.order_paid.push",
        "AICRM_INTERNAL_EVENTS_PAYMENT_DISABLE_LEGACY_AUTOMATION_DIRECT=1",
        "AICRM_INTERNAL_EVENTS_PAYMENT_ENABLED=0",
        "No schema rollback is",
    ]:
        assert required in source


def test_internal_event_gray_runbook_has_troubleshooting_commands() -> None:
    source = RUNBOOK.read_text(encoding="utf-8")

    for required in [
        "failed_retryable",
        "/api/admin/internal-events/$EVENT_ID/consumers/$CONSUMER_NAME/retry",
        "/api/admin/internal-events/$EVENT_ID/consumers/$CONSUMER_NAME/skip",
        "skipped",
        "idempotency_key=payment.succeeded:$OUT_TRADE_NO",
        "stuck running",
        "UPDATE internal_event_consumer_run",
        "locked_at = NULL",
    ]:
        assert required in source
