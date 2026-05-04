from __future__ import annotations

import logging
from datetime import datetime, timedelta

from flask import current_app, jsonify

from ..domains.callbacks.service import (
    count_failed_events_since,
    count_pending_events,
    list_stale_pending_events,
    mark_event_dead_letter,
    mark_external_contact_event_processing,
)
from ..infra.circuit_breaker import CircuitBreaker
from ..infra.task_queue import get_queue_depth, is_rq_active
from .background_jobs import _dispatch_background_task, _process_external_contact_event
from .common import APP_STARTED_AT_TEXT

health_logger = logging.getLogger("system_health")

_COMPENSATE_AGE_SECONDS = 120
_COMPENSATE_MAX_RETRY = 5
_COMPENSATE_BATCH_LIMIT = 50


def _get_circuit_breaker_state() -> str:
    try:
        from ..wecom_client import _circuit_breaker
        return _circuit_breaker.state
    except Exception:
        return "unknown"


def _get_archive_sync_info() -> dict:
    try:
        from ..domains.archive.repo import get_archive_last_seq, get_last_sync_run
        last_run = get_last_sync_run()
        info: dict = {"last_seq": get_archive_last_seq()}
        if last_run:
            info["last_sync_status"] = last_run.get("status", "")
            info["last_sync_at"] = last_run.get("finished_at") or last_run.get("created_at") or ""
        return info
    except Exception:
        return {}


def _pending_event_stats() -> dict:
    try:
        stats = count_pending_events()
        pending_count = int(stats.get("pending_count") or 0)
        oldest = stats.get("oldest_created_at")
        oldest_age: float | None = None
        if oldest and pending_count > 0:
            try:
                oldest_dt = datetime.fromisoformat(str(oldest))
                oldest_age = (datetime.utcnow() - oldest_dt).total_seconds()
            except (ValueError, TypeError):
                pass
        return {"pending_events": pending_count, "oldest_pending_age_seconds": oldest_age}
    except Exception:
        return {"pending_events": None, "oldest_pending_age_seconds": None}


def _failed_event_count_24h() -> int | None:
    try:
        since = (datetime.utcnow() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
        return count_failed_events_since(since)
    except Exception:
        return None


def system_health():
    pending = _pending_event_stats()
    archive = _get_archive_sync_info()
    return jsonify({
        "status": "ok",
        "started_at": APP_STARTED_AT_TEXT,
        "pending_events": pending.get("pending_events"),
        "oldest_pending_age_seconds": pending.get("oldest_pending_age_seconds"),
        "failed_events_24h": _failed_event_count_24h(),
        "archive_last_seq": archive.get("last_seq"),
        "archive_last_sync_at": archive.get("last_sync_at", ""),
        "archive_last_sync_status": archive.get("last_sync_status", ""),
        "circuit_breaker_state": _get_circuit_breaker_state(),
        "task_queue_backend": "rq" if is_rq_active() else "thread_pool",
        "task_queue_pending": get_queue_depth(),
    })


def run_compensating_scan():
    stale = list_stale_pending_events(
        age_seconds=_COMPENSATE_AGE_SECONDS,
        limit=_COMPENSATE_BATCH_LIMIT,
    )
    requeued = 0
    dead_lettered = 0

    for event in stale:
        event_id = int(event["id"])
        retry_count = int(event.get("retry_count") or 0)

        if retry_count >= _COMPENSATE_MAX_RETRY:
            mark_event_dead_letter(
                event_id,
                error_message=f"exceeded max retries ({_COMPENSATE_MAX_RETRY})",
            )
            dead_lettered += 1
            health_logger.warning(
                "compensating scan: dead_letter event_id=%s retries=%s",
                event_id, retry_count,
            )
            continue

        try:
            mark_external_contact_event_processing(event_id)
            _dispatch_background_task(
                "compensate_external_contact_event",
                _process_external_contact_event,
                event_id,
            )
            requeued += 1
        except Exception:
            health_logger.exception(
                "compensating scan: failed to requeue event_id=%s", event_id,
            )

    health_logger.info(
        "compensating scan complete: scanned=%s requeued=%s dead_lettered=%s",
        len(stale), requeued, dead_lettered,
    )
    return {
        "scanned": len(stale),
        "requeued": requeued,
        "dead_lettered": dead_lettered,
    }


def api_compensating_scan():
    try:
        result = run_compensating_scan()
        return jsonify({"ok": True, **result})
    except Exception as exc:
        health_logger.exception("compensating scan endpoint failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


def register_routes(bp):
    bp.route('/api/system/health', methods=['GET'])(system_health)
    bp.route('/api/system/compensate', methods=['POST'])(api_compensating_scan)
