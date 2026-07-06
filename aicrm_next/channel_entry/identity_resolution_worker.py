from __future__ import annotations

from typing import Any, Callable

from psycopg.types.json import Jsonb

from . import application
from .repo import _connect, json_safe, text


SyncFunc = Callable[[dict[str, Any], str, int | None], dict[str, Any]]


class IdentityResolutionBackfillWorker:
    def __init__(
        self,
        *,
        connection_factory: Callable[[], Any] | None = None,
        sync_func: SyncFunc | None = None,
        locked_by: str = "identity-resolution-worker",
    ) -> None:
        self.connection_factory = connection_factory or _connect
        self.sync_func = sync_func or self._sync
        self.locked_by = text(locked_by) or "identity-resolution-worker"

    def run_due(self, *, limit: int = 100, max_attempts: int = 5, dry_run: bool = True) -> dict[str, Any]:
        conn = self.connection_factory()
        processed = 0
        resolved = 0
        retryable = 0
        terminal = 0
        runtime_processed = 0
        details: list[dict[str, Any]] = []
        try:
            queue_rows = _claim_queue_rows(conn, limit=limit, locked_by=self.locked_by)
            runtime_rows = _claim_runtime_rows(
                conn,
                limit=max(0, int(limit or 100) - len(queue_rows)),
                max_attempts=max_attempts,
            )
            if dry_run:
                conn.rollback()
                return {
                    "ok": True,
                    "dry_run": True,
                    "claimed_count": len(queue_rows),
                    "runtime_claimed_count": len(runtime_rows),
                    "resolved_count": 0,
                    "retryable_count": 0,
                    "terminal_count": 0,
                    "details": [
                        {"source": "queue", "id": row.get("id"), "external_userid": text(row.get("external_userid"))}
                        for row in queue_rows
                    ]
                    + [
                        {"source": "runtime", "id": row.get("id"), "external_userid": text(row.get("external_userid"))}
                        for row in runtime_rows
                    ],
                    "source_status": "identity_resolution_backfill_worker",
                }
            for row in queue_rows:
                processed += 1
                event = _event_from_queue_row(row)
                result = self.sync_func(event, text(row.get("corp_id")), None)
                status = text(result.get("status"))
                if status == "success":
                    _mark_queue_resolved(conn, row, result)
                    resolved += 1
                else:
                    attempts = int(row.get("attempts") or row.get("attempt_count") or 0)
                    if attempts >= max(1, int(max_attempts)):
                        _mark_queue_failed(conn, row, result)
                        terminal += 1
                    else:
                        _mark_queue_retryable(conn, row, result)
                        retryable += 1
                details.append({"source": "queue", "id": row.get("id"), "status": status, "reason": text(result.get("reason"))})
            for row in runtime_rows:
                runtime_processed += 1
                event = _event_from_runtime_row(row)
                result = self.sync_func(event, text(row.get("corp_id")), int(row.get("event_log_id") or 0) or None)
                status = text(result.get("status")) or "pending"
                attempts = int(row.get("identity_attempt_count") or 0)
                terminal_after_attempt = status != "success" and attempts + 1 >= max(1, int(max_attempts))
                _mark_runtime_identity(conn, row, result, terminal=terminal_after_attempt, max_attempts=max_attempts)
                if status == "success":
                    resolved += 1
                elif terminal_after_attempt:
                    terminal += 1
                else:
                    retryable += 1
                details.append({"source": "runtime", "id": row.get("id"), "status": status, "reason": text(result.get("reason"))})
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return {
            "ok": terminal == 0,
            "dry_run": False,
            "processed_count": processed,
            "runtime_processed_count": runtime_processed,
            "resolved_count": resolved,
            "retryable_count": retryable,
            "terminal_count": terminal,
            "details": details,
            "source_status": "identity_resolution_backfill_worker",
        }

    @staticmethod
    def _sync(event: dict[str, Any], corp_id: str, event_log_id: int | None) -> dict[str, Any]:
        return application._sync_identity_best_effort(event, corp_id=corp_id, event_log_id=event_log_id)


def _claim_queue_rows(conn: Any, *, limit: int, locked_by: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        WITH due AS (
            SELECT id
            FROM crm_user_identity_resolution_queue
            WHERE status = 'pending'
              AND (next_attempt_at IS NULL OR next_attempt_at <= CURRENT_TIMESTAMP)
            ORDER BY COALESCE(next_attempt_at, first_seen_at, created_at) ASC, id ASC
            LIMIT %s
            FOR UPDATE SKIP LOCKED
        )
        UPDATE crm_user_identity_resolution_queue q
        SET status = 'polling',
            attempts = COALESCE(attempts, 0) + 1,
            attempt_count = COALESCE(attempt_count, 0) + 1,
            last_seen_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP,
            payload_json = payload_json || %s
        FROM due
        WHERE q.id = due.id
        RETURNING q.*
        """,
        (max(1, min(int(limit or 100), 500)), Jsonb({"locked_by": locked_by})),
    ).fetchall()
    return [dict(row) for row in rows or []]


def _claim_runtime_rows(conn: Any, *, limit: int, max_attempts: int) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    rows = conn.execute(
        """
        SELECT *
        FROM automation_channel_entry_runtime
        WHERE identity_status IN ('pending', 'pending_identity', 'failed')
          AND COALESCE(identity_attempt_count, 0) < %s
          AND (identity_next_attempt_at IS NULL OR identity_next_attempt_at <= CURRENT_TIMESTAMP)
        ORDER BY COALESCE(identity_next_attempt_at, updated_at) ASC, id ASC
        LIMIT %s
        FOR UPDATE SKIP LOCKED
        """,
        (max(1, int(max_attempts or 5)), max(1, min(int(limit or 100), 500))),
    ).fetchall()
    return [dict(row) for row in rows or []]


def _event_from_queue_row(row: dict[str, Any]) -> dict[str, Any]:
    payload = dict(row.get("payload_json") or {})
    if text(payload.get("Event")):
        return payload
    source_key_parts = text(row.get("source_key")).split(":")
    follow_user_userid = text(payload.get("follow_user_userid") or payload.get("UserID"))
    if not follow_user_userid and len(source_key_parts) >= 3:
        follow_user_userid = source_key_parts[2]
    return {
        **payload,
        "Event": "change_external_contact",
        "ChangeType": text(payload.get("ChangeType")) or "edit_external_contact",
        "ExternalUserID": text(row.get("external_userid")) or text(payload.get("ExternalUserID")),
        "UserID": follow_user_userid,
    }


def _event_from_runtime_row(row: dict[str, Any]) -> dict[str, Any]:
    payload = dict(row.get("payload_json") or {})
    return {
        **payload,
        "Event": text(payload.get("Event")) or "change_external_contact",
        "ChangeType": text(payload.get("ChangeType")) or "edit_external_contact",
        "ExternalUserID": text(row.get("external_userid")) or text(payload.get("ExternalUserID")),
        "UserID": text(row.get("follow_user_userid")) or text(payload.get("UserID")),
    }


def _mark_queue_resolved(conn: Any, row: dict[str, Any], result: dict[str, Any]) -> None:
    unionid = text(result.get("unionid"))
    conn.execute(
        """
        UPDATE crm_user_identity_resolution_queue
        SET status = 'resolved',
            resolved_unionid = %s,
            resolved_at = CURRENT_TIMESTAMP,
            last_error = '',
            payload_json = payload_json || %s,
            next_attempt_at = NULL,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
        """,
        (unionid, Jsonb({"identity_backfill_result": json_safe(result)}), int(row.get("id") or 0)),
    )


def _mark_queue_retryable(conn: Any, row: dict[str, Any], result: dict[str, Any]) -> None:
    conn.execute(
        """
        UPDATE crm_user_identity_resolution_queue
        SET status = 'pending',
            last_error = %s,
            payload_json = payload_json || %s,
            next_attempt_at = CURRENT_TIMESTAMP + (LEAST(GREATEST(COALESCE(attempts, 1), 1), 30) || ' minutes')::interval,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
        """,
        (_result_error(result), Jsonb({"identity_backfill_result": json_safe(result)}), int(row.get("id") or 0)),
    )


def _mark_queue_failed(conn: Any, row: dict[str, Any], result: dict[str, Any]) -> None:
    conn.execute(
        """
        UPDATE crm_user_identity_resolution_queue
        SET status = 'failed',
            last_error = %s,
            payload_json = payload_json || %s,
            next_attempt_at = NULL,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
        """,
        (_result_error(result), Jsonb({"identity_backfill_result": json_safe(result)}), int(row.get("id") or 0)),
    )


def _mark_runtime_identity(
    conn: Any,
    row: dict[str, Any],
    result: dict[str, Any],
    *,
    terminal: bool = False,
    max_attempts: int = 5,
) -> None:
    status = text(result.get("status")) or "pending"
    stored_status = "failed_terminal" if terminal else status
    conn.execute(
        """
        UPDATE automation_channel_entry_runtime
        SET unionid = CASE WHEN %s <> '' THEN %s ELSE unionid END,
            identity_status = %s,
            identity_attempt_count = CASE
                WHEN %s = 'success' THEN 0
                ELSE COALESCE(identity_attempt_count, 0) + 1
            END,
            identity_next_attempt_at = CASE
                WHEN %s = 'success' THEN NULL
                WHEN COALESCE(identity_attempt_count, 0) + 1 >= %s THEN NULL
                ELSE CURRENT_TIMESTAMP + (LEAST(GREATEST(COALESCE(identity_attempt_count, 0) + 1, 1), 30) || ' minutes')::interval
            END,
            identity_last_error = CASE WHEN %s = 'success' THEN '' ELSE %s END,
            payload_json = payload_json || %s,
            last_seen_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
        """,
        (
            text(result.get("unionid")),
            text(result.get("unionid")),
            stored_status,
            status,
            status,
            max(1, int(max_attempts or 5)),
            status,
            _result_error(result),
            Jsonb({"identity_backfill_result": json_safe(result)}),
            int(row.get("id") or 0),
        ),
    )


def _result_error(result: dict[str, Any]) -> str:
    return (text(result.get("reason")) or text(result.get("message")) or text(result.get("status")) or "identity_resolution_failed")[:500]
