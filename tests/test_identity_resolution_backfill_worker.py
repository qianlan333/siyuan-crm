from __future__ import annotations

from aicrm_next.channel_entry.identity_resolution_worker import IdentityResolutionBackfillWorker
from aicrm_next.data_health import checks


class _Cursor:
    def __init__(self, rows=None):
        self._rows = rows or []

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self, queue_rows=None, runtime_rows=None):
        self.queue_rows = queue_rows or []
        self.runtime_rows = runtime_rows or []
        self.queries: list[tuple[str, tuple]] = []
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def execute(self, query, params=()):
        self.queries.append((query, tuple(params)))
        normalized = " ".join(query.split())
        if "UPDATE crm_user_identity_resolution_queue q" in normalized:
            return _Cursor(self.queue_rows)
        if normalized.startswith("SELECT * FROM automation_channel_entry_runtime"):
            return _Cursor(self.runtime_rows)
        return _Cursor()

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def test_identity_resolution_worker_resolves_queue_row() -> None:
    row = {
        "id": 10,
        "source_key": "corp:external_1:user_1",
        "corp_id": "corp",
        "external_userid": "external_1",
        "payload_json": {"scene": "qr_scene", "ChangeType": "add_external_contact"},
        "attempts": 1,
        "attempt_count": 1,
    }
    conn = _FakeConn(queue_rows=[row])

    def sync(event, corp_id, event_log_id):
        assert event["ExternalUserID"] == "external_1"
        assert event["UserID"] == "user_1"
        assert corp_id == "corp"
        assert event_log_id is None
        return {"status": "success", "unionid": "union_1"}

    result = IdentityResolutionBackfillWorker(connection_factory=lambda: conn, sync_func=sync).run_due(dry_run=False)

    assert result["resolved_count"] == 1
    assert any("SET status = 'resolved'" in query for query, _ in conn.queries)
    assert conn.committed is True
    assert conn.closed is True


def test_identity_resolution_worker_retries_then_terminal_fails_queue_row() -> None:
    retry_conn = _FakeConn(queue_rows=[{"id": 11, "external_userid": "external_retry", "payload_json": {}, "attempts": 1}])
    terminal_conn = _FakeConn(queue_rows=[{"id": 12, "external_userid": "external_terminal", "payload_json": {}, "attempts": 5}])

    def failed_sync(event, corp_id, event_log_id):
        return {"status": "failed", "reason": "wecom_api_error"}

    retry_result = IdentityResolutionBackfillWorker(connection_factory=lambda: retry_conn, sync_func=failed_sync).run_due(
        dry_run=False,
        max_attempts=5,
    )
    terminal_result = IdentityResolutionBackfillWorker(connection_factory=lambda: terminal_conn, sync_func=failed_sync).run_due(
        dry_run=False,
        max_attempts=5,
    )

    assert retry_result["retryable_count"] == 1
    assert any("SET status = 'pending'" in query for query, _ in retry_conn.queries)
    assert terminal_result["terminal_count"] == 1
    assert any("SET status = 'failed'" in query for query, _ in terminal_conn.queries)


def test_identity_resolution_worker_updates_runtime_row() -> None:
    conn = _FakeConn(
        runtime_rows=[
            {
                "id": 20,
                "event_log_id": 99,
                "corp_id": "corp",
                "external_userid": "external_runtime",
                "follow_user_userid": "user_runtime",
                "payload_json": {},
            }
        ]
    )

    result = IdentityResolutionBackfillWorker(
        connection_factory=lambda: conn,
        sync_func=lambda event, corp_id, event_log_id: {"status": "success", "unionid": "union_runtime"},
    ).run_due(dry_run=False)

    assert result["runtime_processed_count"] == 1
    assert result["resolved_count"] == 1
    assert any("UPDATE automation_channel_entry_runtime" in query for query, _ in conn.queries)


def test_identity_resolution_worker_runtime_rows_use_backoff_and_terminal_limit() -> None:
    retry_conn = _FakeConn(
        runtime_rows=[
            {
                "id": 21,
                "event_log_id": 100,
                "corp_id": "corp",
                "external_userid": "external_retry",
                "follow_user_userid": "user_retry",
                "payload_json": {},
                "identity_attempt_count": 1,
            }
        ]
    )
    terminal_conn = _FakeConn(
        runtime_rows=[
            {
                "id": 22,
                "event_log_id": 101,
                "corp_id": "corp",
                "external_userid": "external_terminal",
                "follow_user_userid": "user_terminal",
                "payload_json": {},
                "identity_attempt_count": 4,
            }
        ]
    )

    def failed_sync(event, corp_id, event_log_id):
        return {"status": "failed", "reason": "wecom_api_error"}

    retry_result = IdentityResolutionBackfillWorker(connection_factory=lambda: retry_conn, sync_func=failed_sync).run_due(
        dry_run=False,
        max_attempts=5,
    )
    terminal_result = IdentityResolutionBackfillWorker(connection_factory=lambda: terminal_conn, sync_func=failed_sync).run_due(
        dry_run=False,
        max_attempts=5,
    )

    assert retry_result["retryable_count"] == 1
    assert retry_result["terminal_count"] == 0
    claim_query = retry_conn.queries[1][0]
    assert "COALESCE(identity_attempt_count, 0) < %s" in claim_query
    assert "identity_next_attempt_at IS NULL OR identity_next_attempt_at <= CURRENT_TIMESTAMP" in claim_query
    update_query = retry_conn.queries[-1][0]
    assert "identity_attempt_count" in update_query
    assert "identity_next_attempt_at" in update_query
    assert terminal_result["terminal_count"] == 1
    assert "failed_terminal" in terminal_conn.queries[-1][1]


def test_identity_resolution_worker_dry_run_rolls_back_claims() -> None:
    conn = _FakeConn(queue_rows=[{"id": 10, "external_userid": "external_1", "payload_json": {}}])

    result = IdentityResolutionBackfillWorker(
        connection_factory=lambda: conn,
        sync_func=lambda event, corp_id, event_log_id: {"status": "success"},
    ).run_due(dry_run=True)

    assert result["dry_run"] is True
    assert result["claimed_count"] == 1
    assert conn.rolled_back is True
    assert conn.committed is False


def test_identity_resolution_queue_backlog_health_probe_reports_red(monkeypatch) -> None:
    class Result:
        def mappings(self):
            return self

        def first(self):
            return {"pending_count": 101, "oldest_pending_hours": 25.0}

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, statement):
            return Result()

    monkeypatch.setattr(checks, "database_schema_available", lambda: True)
    monkeypatch.setattr(checks, "get_session_factory", lambda: Session)

    result = checks.run_check("identity_resolution_queue_backlog")

    assert result is not None
    assert result.status == "fail"
    assert result.severity == "red"
    assert result.evidence["pending_count"] == 101
