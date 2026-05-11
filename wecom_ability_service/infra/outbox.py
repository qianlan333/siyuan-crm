"""Transactional outbox for at-least-once outbound delivery.

Use this when a database write must be reliably accompanied by an external
side-effect (webhook, message, sync). Writers enqueue a row in
``outbound_event_outbox`` *inside the same DB transaction* as their main
write; the scanner (a separate code path, runnable in-process via
``run_outbox_scan_once`` or via a cron / RQ job) picks pending rows and
invokes the handler registered for that ``event_type``. Failures bump
``attempt_count`` and re-schedule with exponential backoff; the row is
preserved indefinitely until success or a deliberate admin intervention.

Idempotency: when an ``idempotency_key`` is supplied, repeat enqueues are
collapsed (dedup is best-effort — a unique index on ``idempotency_key``
would harden it, but the current schema keeps it as a soft constraint so
historical retries keep working).

Status state machine: ``pending -> in_flight -> success`` on the happy path,
``pending -> in_flight -> retry_scheduled -> pending`` on transient failure,
``pending -> in_flight -> failed`` after ``max_attempts`` exhausted.

Designed to mirror the proven scanner shape used by the callback compensation
job that already ships with PR #146 — keep them aligned so operators only
have to learn one mental model.
"""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from flask import current_app, has_app_context

from ..db import get_db

outbox_logger = logging.getLogger("outbox")

# event_type -> handler. Handlers receive the (id, payload, attempt) and
# either return ``None``/truthy on success, or raise on failure. We keep the
# protocol intentionally small so callers can plug in WeCom / webhook /
# anything without subclassing.
_handlers_lock = threading.Lock()
_handlers: dict[str, Callable[[dict[str, Any]], None]] = {}

STATUS_PENDING = "pending"
STATUS_IN_FLIGHT = "in_flight"
STATUS_SUCCESS = "success"
STATUS_RETRY_SCHEDULED = "retry_scheduled"
STATUS_FAILED = "failed"

DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_BACKOFF_BASE_SECONDS = 30


@dataclass
class OutboxEvent:
    id: int
    event_type: str
    target_name: str
    payload: dict[str, Any]
    idempotency_key: str
    status: str
    attempt_count: int
    request_id: str


def register_outbox_handler(event_type: str, handler: Callable[[dict[str, Any]], None]) -> None:
    """Register a delivery callable for ``event_type``.

    The callable receives the ``payload`` dict (as enqueued, after JSON
    round-trip). Return value is ignored. Raise on failure to trigger retry.
    """
    with _handlers_lock:
        _handlers[event_type] = handler


def get_outbox_handler(event_type: str) -> Callable[[dict[str, Any]], None] | None:
    with _handlers_lock:
        return _handlers.get(event_type)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def enqueue_outbox_event(
    *,
    event_type: str,
    target_name: str,
    payload: dict[str, Any],
    idempotency_key: str = "",
    request_id: str = "",
) -> int:
    """Insert an outbox row in the *caller's* transaction.

    Caller must commit. If ``idempotency_key`` is given and a non-final row
    already exists with the same key, the existing row's id is returned and
    no new row is inserted.
    """
    db = get_db()
    normalized_key = str(idempotency_key or "").strip()
    if normalized_key:
        existing = db.execute(
            """
            SELECT id FROM outbound_event_outbox
            WHERE idempotency_key = ?
              AND status IN ('pending', 'in_flight', 'retry_scheduled', 'success')
            ORDER BY id ASC
            LIMIT 1
            """,
            (normalized_key,),
        ).fetchone()
        if existing:
            return int(existing["id"])

    now_text = _now_iso()
    cursor = db.execute(
        """
        INSERT INTO outbound_event_outbox
            (event_type, target_name, payload_json, idempotency_key, status,
             attempt_count, next_attempt_at, request_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
        """,
        (
            str(event_type or "").strip(),
            str(target_name or "").strip(),
            json.dumps(payload, ensure_ascii=False),
            normalized_key,
            STATUS_PENDING,
            now_text,
            str(request_id or "").strip(),
            now_text,
            now_text,
        ),
    )
    last_id = getattr(cursor, "lastrowid", None)
    if last_id is not None:
        return int(last_id)
    row = db.execute(
        "SELECT id FROM outbound_event_outbox WHERE created_at = ? AND idempotency_key = ? ORDER BY id DESC LIMIT 1",
        (now_text, normalized_key),
    ).fetchone()
    return int(row["id"]) if row else 0


def _claim_due_events(limit: int) -> list[OutboxEvent]:
    db = get_db()
    now_text = _now_iso()
    rows = db.execute(
        """
        SELECT id, event_type, target_name, payload_json, idempotency_key,
               status, attempt_count, request_id
        FROM outbound_event_outbox
        WHERE status IN ('pending', 'retry_scheduled')
          AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
        ORDER BY id ASC
        LIMIT ?
        """,
        (now_text, int(max(1, limit))),
    ).fetchall()

    claimed: list[OutboxEvent] = []
    for row in rows:
        # Best-effort claim — without a SELECT FOR UPDATE on SQLite, a
        # second scanner racing in parallel could pick the same row. The
        # per-event idempotency_key + ``status`` transition give us a
        # belt-and-braces guard, but operators should run at most one
        # scanner per process for now.
        update_cursor = db.execute(
            """
            UPDATE outbound_event_outbox
            SET status = ?, updated_at = ?
            WHERE id = ?
              AND status IN ('pending', 'retry_scheduled')
            """,
            (STATUS_IN_FLIGHT, now_text, int(row["id"])),
        )
        if getattr(update_cursor, "rowcount", 1) == 0:
            continue
        raw_payload = row.get("payload_json")
        if isinstance(raw_payload, (dict, list)):
            payload = raw_payload
        else:
            try:
                payload = json.loads(raw_payload or "{}")
            except (TypeError, json.JSONDecodeError):
                payload = {}
        claimed.append(
            OutboxEvent(
                id=int(row["id"]),
                event_type=str(row.get("event_type") or "").strip(),
                target_name=str(row.get("target_name") or "").strip(),
                payload=payload if isinstance(payload, dict) else {"_raw": payload},
                idempotency_key=str(row.get("idempotency_key") or "").strip(),
                status=str(row.get("status") or "").strip(),
                attempt_count=int(row.get("attempt_count") or 0),
                request_id=str(row.get("request_id") or "").strip(),
            )
        )
    db.commit()
    return claimed


def _mark_success(event_id: int) -> None:
    db = get_db()
    now_text = _now_iso()
    db.execute(
        """
        UPDATE outbound_event_outbox
        SET status = ?, last_error = '', updated_at = ?, next_attempt_at = NULL
        WHERE id = ?
        """,
        (STATUS_SUCCESS, now_text, int(event_id)),
    )
    db.commit()


def _mark_failure(
    event_id: int,
    *,
    attempt_count: int,
    error_message: str,
    max_attempts: int,
    backoff_base_seconds: int,
) -> None:
    db = get_db()
    now = datetime.now(timezone.utc)
    new_attempt = attempt_count + 1
    truncated_error = (error_message or "")[:500]
    if new_attempt >= max_attempts:
        db.execute(
            """
            UPDATE outbound_event_outbox
            SET status = ?, attempt_count = ?, last_error = ?, updated_at = ?,
                next_attempt_at = NULL
            WHERE id = ?
            """,
            (STATUS_FAILED, new_attempt, truncated_error, now.strftime("%Y-%m-%d %H:%M:%S"), int(event_id)),
        )
    else:
        # Exponential backoff capped at 1 hour to avoid runaway intervals.
        delay = min(backoff_base_seconds * (2 ** (new_attempt - 1)), 3600)
        next_attempt_at = (now + timedelta(seconds=delay)).strftime("%Y-%m-%d %H:%M:%S")
        db.execute(
            """
            UPDATE outbound_event_outbox
            SET status = ?, attempt_count = ?, last_error = ?, updated_at = ?,
                next_attempt_at = ?
            WHERE id = ?
            """,
            (
                STATUS_RETRY_SCHEDULED,
                new_attempt,
                truncated_error,
                now.strftime("%Y-%m-%d %H:%M:%S"),
                next_attempt_at,
                int(event_id),
            ),
        )
    db.commit()


def run_outbox_scan_once(
    *,
    batch_size: int = 50,
    max_attempts: int | None = None,
    backoff_base_seconds: int | None = None,
) -> dict[str, int]:
    """Drive one pass of the scanner. Returns a stats dict.

    Safe to call repeatedly (e.g. from a cron, an RQ job, or an admin "scan
    now" button). Defaults are read from app config when available so they
    can be tuned without code changes once Sprint 4 lands the schema.
    """
    if max_attempts is None:
        max_attempts = _config_int("OUTBOX_MAX_ATTEMPTS", DEFAULT_MAX_ATTEMPTS)
    if backoff_base_seconds is None:
        backoff_base_seconds = _config_int("OUTBOX_BACKOFF_BASE_SECONDS", DEFAULT_BACKOFF_BASE_SECONDS)

    events = _claim_due_events(batch_size)
    success = 0
    failure = 0
    skipped = 0
    for event in events:
        handler = get_outbox_handler(event.event_type)
        if handler is None:
            outbox_logger.warning(
                "outbox no handler registered event_id=%s event_type=%s",
                event.id,
                event.event_type,
            )
            _mark_failure(
                event.id,
                attempt_count=event.attempt_count,
                error_message=f"no handler for {event.event_type}",
                max_attempts=max_attempts,
                backoff_base_seconds=backoff_base_seconds,
            )
            skipped += 1
            continue
        try:
            handler(event.payload)
        except Exception as exc:
            outbox_logger.exception(
                "outbox delivery failed event_id=%s event_type=%s attempt=%d",
                event.id,
                event.event_type,
                event.attempt_count,
            )
            _mark_failure(
                event.id,
                attempt_count=event.attempt_count,
                error_message=f"{exc.__class__.__name__}: {exc}",
                max_attempts=max_attempts,
                backoff_base_seconds=backoff_base_seconds,
            )
            failure += 1
            continue
        outbox_logger.info(
            "outbox delivery success event_id=%s event_type=%s",
            event.id,
            event.event_type,
        )
        _mark_success(event.id)
        success += 1
    return {
        "claimed": len(events),
        "success": success,
        "failure": failure,
        "skipped": skipped,
    }


def _config_int(key: str, default: int) -> int:
    if not has_app_context():
        return default
    raw = current_app.config.get(key)
    try:
        return int(raw) if raw not in (None, "") else default
    except (TypeError, ValueError):
        return default


# Test helpers --------------------------------------------------------------
def _reset_handlers() -> None:
    with _handlers_lock:
        _handlers.clear()
