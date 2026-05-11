"""Sprint 1+2 infra tests: dialect helpers, TTL cache, outbound HTTP client,
transactional outbox. One file because the modules are small and tightly
coupled to each other in real usage.
"""
from __future__ import annotations

import pytest
import requests

from wecom_ability_service.db import get_db
from wecom_ability_service.db import dialect as db_dialect
from wecom_ability_service.infra import cache as infra_cache
from wecom_ability_service.infra import http_client
from wecom_ability_service.infra import outbox


@pytest.fixture()
def app(tmp_path):
    from tests.conftest import build_pg_test_app

    with build_pg_test_app(tmp_path) as app:
        yield app


# -------- dialect ----------------------------------------------------------


def test_cast_text_emits_postgres_cast_only_under_postgres(monkeypatch):
    monkeypatch.setattr(db_dialect, "get_db_backend", lambda: "postgres")
    # PG-only: cast_text 使用 ::timestamp::text 确保 TIMESTAMPTZ 输出不带时区
    assert db_dialect.cast_text("ts.updated_at") == "(ts.updated_at)::timestamp::text"
    assert db_dialect.is_postgres() is True
    assert db_dialect.is_sqlite() is False


def test_coalesce_text_chains_casts(monkeypatch):
    monkeypatch.setattr(db_dialect, "get_db_backend", lambda: "postgres")
    assert (
        db_dialect.coalesce_text("a", "b", default="''")
        == "COALESCE((a)::timestamp::text, (b)::timestamp::text, '')"
    )


# -------- TTL cache --------------------------------------------------------


def test_cached_decorator_memoizes_outside_test_mode(monkeypatch):
    # Force the helper to think we're not under app testing so the cache is
    # actually hit. (Inside a Flask app context the decorator bypasses cache
    # to keep test fixtures isolated.)
    monkeypatch.setattr(infra_cache, "_cache_disabled", lambda: False)

    calls = {"n": 0}

    @infra_cache.cached(ttl=10)
    def expensive(x: int) -> int:
        calls["n"] += 1
        return x * 2

    assert expensive(3) == 6
    assert expensive(3) == 6
    assert expensive(3) == 6
    assert calls["n"] == 1

    expensive.invalidate()
    assert expensive(3) == 6
    assert calls["n"] == 2


def test_cached_decorator_bypasses_under_test_mode(app):
    calls = {"n": 0}

    @infra_cache.cached(ttl=10, key_prefix="test_bypass")
    def under_app() -> int:
        calls["n"] += 1
        return 42

    with app.app_context():
        under_app()
        under_app()
        under_app()

    assert calls["n"] == 3, "cache must bypass when current_app.testing is True"


# -------- OutboundHttpClient ----------------------------------------------


def test_outbound_client_returns_response_on_success(monkeypatch):
    monkeypatch.setattr(http_client, "_testing_mode", lambda: False)
    http_client.reset_clients()

    class _FakeResp:
        def __init__(self, status_code: int = 200, text: str = "ok"):
            self.status_code = status_code
            self.text = text

        def json(self):
            return {"ok": True}

    seen = {}

    def fake_post(url, **kwargs):
        seen["url"] = url
        seen["kwargs"] = kwargs
        return _FakeResp()

    monkeypatch.setattr(requests, "post", fake_post)
    client = http_client.get_outbound_client("unit_target", timeout=2.0, retry_max=0)
    response = client.post("https://example.invalid/x", json={"a": 1})
    assert response.status_code == 200
    assert seen["url"] == "https://example.invalid/x"
    assert seen["kwargs"]["json"] == {"a": 1}
    assert seen["kwargs"]["timeout"] == 2.0


def test_outbound_client_retries_5xx_then_raises(monkeypatch):
    monkeypatch.setattr(http_client, "_testing_mode", lambda: False)
    http_client.reset_clients()

    class _FakeResp:
        status_code = 500
        text = "boom"

        def json(self):  # pragma: no cover - not used
            return {}

    call_count = {"n": 0}

    def fake_post(url, **kwargs):
        call_count["n"] += 1
        return _FakeResp()

    monkeypatch.setattr(requests, "post", fake_post)
    client = http_client.get_outbound_client(
        "unit_5xx",
        timeout=0.01,
        retry_max=1,
        retry_backoff_base=0.0,
    )
    with pytest.raises(http_client.OutboundHttpError) as excinfo:
        client.post("https://example.invalid/y")
    err = excinfo.value
    assert err.category == "http_status"
    assert err.status_code == 500
    assert err.response_text == "boom"
    assert call_count["n"] == 2  # initial + 1 retry


def test_outbound_client_circuit_breaker_isolates_per_name(monkeypatch):
    monkeypatch.setattr(http_client, "_testing_mode", lambda: False)
    http_client.reset_clients()

    def always_fail(url, **kwargs):
        raise requests.ConnectionError("upstream A is sick")

    monkeypatch.setattr(requests, "post", always_fail)

    sick = http_client.get_outbound_client(
        "unit_sick", timeout=0.01, retry_max=0, retry_backoff_base=0.0, failure_threshold=1
    )
    healthy = http_client.get_outbound_client(
        "unit_healthy", timeout=0.01, retry_max=0, retry_backoff_base=0.0
    )

    # Trip the sick breaker.
    with pytest.raises(http_client.OutboundHttpError):
        sick.post("https://sick.invalid")

    # Sick should now reject without a network call.
    with pytest.raises(http_client.OutboundHttpError) as excinfo:
        sick.post("https://sick.invalid")
    assert excinfo.value.category == "circuit_open"

    # Healthy must still be able to attempt (its breaker is independent).
    with pytest.raises(http_client.OutboundHttpError) as excinfo:
        healthy.post("https://healthy.invalid")
    assert excinfo.value.category in {"network", "timeout"}


def test_outbound_client_bypasses_breaker_under_test_mode(app, monkeypatch):
    http_client.reset_clients()

    def fail(url, **kwargs):
        raise requests.ConnectionError("anything")

    monkeypatch.setattr(requests, "post", fail)
    with app.app_context():
        client = http_client.get_outbound_client(
            "unit_test_mode_skip",
            timeout=0.01,
            retry_max=0,
            retry_backoff_base=0.0,
            failure_threshold=1,
        )
        # Many failures shouldn't trip the breaker because we're under
        # testing mode — every call should reach the fake (and raise
        # network) rather than ever returning ``circuit_open``.
        for _ in range(5):
            with pytest.raises(http_client.OutboundHttpError) as excinfo:
                client.post("https://x.invalid")
            assert excinfo.value.category in {"network", "timeout"}


# -------- Outbox -----------------------------------------------------------


def test_outbox_enqueue_and_deliver_happy_path(app):
    outbox._reset_handlers()
    delivered = []
    outbox.register_outbox_handler(
        "unit_event",
        lambda payload: delivered.append(payload),
    )
    with app.app_context():
        event_id = outbox.enqueue_outbox_event(
            event_type="unit_event",
            target_name="unit_target",
            payload={"hello": "world"},
            idempotency_key="k1",
        )
        get_db().commit()
        assert event_id > 0

        stats = outbox.run_outbox_scan_once(batch_size=10)
        assert stats == {"claimed": 1, "success": 1, "failure": 0, "skipped": 0}
        assert delivered == [{"hello": "world"}]

        row = get_db().execute(
            "SELECT status FROM outbound_event_outbox WHERE id = ?", (event_id,)
        ).fetchone()
        assert row["status"] == outbox.STATUS_SUCCESS


def test_outbox_idempotency_key_collapses_repeat_enqueues(app):
    outbox._reset_handlers()
    outbox.register_outbox_handler("unit_event", lambda payload: None)
    with app.app_context():
        first = outbox.enqueue_outbox_event(
            event_type="unit_event",
            target_name="t",
            payload={"n": 1},
            idempotency_key="dup-key-1",
        )
        get_db().commit()
        second = outbox.enqueue_outbox_event(
            event_type="unit_event",
            target_name="t",
            payload={"n": 2},
            idempotency_key="dup-key-1",
        )
        get_db().commit()
        assert first == second, "second enqueue with same key must collapse"


def test_outbox_failure_reschedules_with_backoff(app):
    outbox._reset_handlers()

    def boom(_payload):
        raise RuntimeError("upstream is on fire")

    outbox.register_outbox_handler("unit_fail", boom)
    with app.app_context():
        event_id = outbox.enqueue_outbox_event(
            event_type="unit_fail",
            target_name="t",
            payload={},
        )
        get_db().commit()

        stats = outbox.run_outbox_scan_once(
            batch_size=10,
            max_attempts=3,
            backoff_base_seconds=1,
        )
        assert stats["failure"] == 1
        row = get_db().execute(
            "SELECT status, attempt_count, last_error, next_attempt_at FROM outbound_event_outbox WHERE id = ?",
            (event_id,),
        ).fetchone()
        assert row["status"] == outbox.STATUS_RETRY_SCHEDULED
        assert int(row["attempt_count"]) == 1
        assert "upstream is on fire" in str(row["last_error"])
        assert str(row["next_attempt_at"] or "").strip() != ""


def test_outbox_failure_marks_failed_after_max_attempts(app):
    outbox._reset_handlers()

    def boom(_payload):
        raise RuntimeError("permafail")

    outbox.register_outbox_handler("unit_fail2", boom)
    with app.app_context():
        event_id = outbox.enqueue_outbox_event(
            event_type="unit_fail2",
            target_name="t",
            payload={},
        )
        get_db().commit()

        # After enough retries the row terminates in ``failed`` rather than
        # rescheduling forever. Force the next_attempt_at back to now to
        # avoid sleeping during the test.
        for _ in range(4):
            stats = outbox.run_outbox_scan_once(
                batch_size=10,
                max_attempts=3,
                backoff_base_seconds=0,
            )
            if stats["claimed"] == 0:
                # Reschedule manually if backoff put it in the future
                get_db().execute(
                    "UPDATE outbound_event_outbox SET next_attempt_at = NULL WHERE id = ?",
                    (event_id,),
                )
                get_db().commit()

        row = get_db().execute(
            "SELECT status, attempt_count FROM outbound_event_outbox WHERE id = ?",
            (event_id,),
        ).fetchone()
        assert row["status"] == outbox.STATUS_FAILED


def test_outbox_missing_handler_marks_skipped(app):
    outbox._reset_handlers()
    with app.app_context():
        event_id = outbox.enqueue_outbox_event(
            event_type="no_handler_registered",
            target_name="t",
            payload={},
        )
        get_db().commit()
        stats = outbox.run_outbox_scan_once(
            batch_size=10,
            max_attempts=2,
            backoff_base_seconds=0,
        )
        assert stats["skipped"] == 1
        # The next call should re-pick the row (still pending after retry
        # scheduling) and either skip again or terminate as ``failed`` once
        # max_attempts is reached.
        get_db().execute(
            "UPDATE outbound_event_outbox SET next_attempt_at = NULL WHERE id = ?",
            (event_id,),
        )
        get_db().commit()
        outbox.run_outbox_scan_once(
            batch_size=10,
            max_attempts=2,
            backoff_base_seconds=0,
        )
        row = get_db().execute(
            "SELECT status FROM outbound_event_outbox WHERE id = ?",
            (event_id,),
        ).fetchone()
        # 2 attempts with max_attempts=2 → terminal failed.
        assert row["status"] == outbox.STATUS_FAILED


# -------- observability PII masking + background_context -----------------


def test_mask_pii_on_mobiles_and_external_userids():
    from wecom_ability_service.observability import mask_pii

    assert mask_pii("接到投诉 13800138000，请处理") == "接到投诉 138****8000，请处理"
    # 11 digits should mask; 10 digits (not a mobile) should pass through.
    assert mask_pii("ID 0123456789 是订单号") == "ID 0123456789 是订单号"
    # external_userid like wm12345678abcdef should partially mask.
    masked = mask_pii("/api/customers/wmabcd1234efgh5678/tags")
    assert "wmabcd1234efgh5678" not in masked
    assert masked.startswith("/api/customers/wmab")
    assert masked.endswith("/tags")


def test_background_context_binds_and_unbinds_job_id(app):
    from wecom_ability_service.observability import (
        background_context,
        get_job_id,
        get_parent_request_id,
        get_task_name,
    )

    with app.app_context():
        assert get_job_id() == ""
        with background_context(job_id="job-abc", parent_request_id="req-xyz", task_name="my_task"):
            assert get_job_id() == "job-abc"
            assert get_parent_request_id() == "req-xyz"
            assert get_task_name() == "my_task"
        assert get_job_id() == ""
        assert get_parent_request_id() == ""


def test_outbound_client_injects_x_request_id_header(app, monkeypatch):
    """The shared client must add X-Request-Id to outbound requests so the
    upstream can correlate calls back to our log line. Header injection is
    suppressed under test mode (legacy mocks reject ``headers=``), so this
    test forces production-mode behaviour."""
    monkeypatch.setattr(http_client, "_testing_mode", lambda: False)
    seen_headers = {}

    def fake_post(url, **kwargs):
        seen_headers.update(dict(kwargs.get("headers") or {}))

        class _Resp:
            status_code = 200
            text = ""

            def json(self):
                return {}

        return _Resp()

    monkeypatch.setattr(requests, "post", fake_post)
    with app.test_request_context("/anything", headers={"X-Request-Id": "abc-123"}):
        from flask import g
        g.request_id = "abc-123"
        client = http_client.get_outbound_client(
            "trace_test", timeout=1.0, retry_max=0, retry_backoff_base=0.0
        )
        client.post("https://x.invalid")
    assert seen_headers.get("X-Request-Id") == "abc-123"


def test_thread_task_runner_propagates_parent_request_id(app):
    """``enqueue_task`` (thread fallback) must rebind the parent request_id
    so log lines emitted inside the task include the originating trace id."""
    from wecom_ability_service.infra.task_queue import _thread_task_runner
    from wecom_ability_service.observability import get_parent_request_id, get_task_name

    captured = {}

    def task():
        captured["parent"] = get_parent_request_id()
        captured["name"] = get_task_name()

    with app.app_context():
        _thread_task_runner(task, (), {}, "demo_task", "req-from-http", "job-xyz")

    assert captured["parent"] == "req-from-http"
    assert captured["name"] == "demo_task"


# -------- automation execution trace --------------------------------------


def test_record_execution_trace_persists_with_correlation_ids(app):
    from wecom_ability_service.domains.automation_state import (
        list_execution_trace_for_external,
        list_execution_trace_for_workflow,
        record_execution_trace,
    )
    from wecom_ability_service.observability import background_context

    with app.app_context():
        with background_context(job_id="job-trace-1", parent_request_id="req-parent-1", task_name="t"):
            row_id = record_execution_trace(
                workflow_id="wf-001",
                workflow_node_id="node-evaluate",
                external_userid="wmABCDEF",
                member_id=42,
                decision_point="evaluate",
                decision_outcome="matched",
                reason="last_msg=2026-04",
                payload={"current_pool": "operating"},
            )
        assert row_id > 0
        rows = list_execution_trace_for_external("wmABCDEF")
        assert len(rows) == 1
        row = rows[0]
        assert row["workflow_id"] == "wf-001"
        assert row["decision_outcome"] == "matched"
        assert row["job_id"] == "job-trace-1"
        assert row["parent_request_id"] == "req-parent-1"
        assert "operating" in (row.get("payload_json") or "")

        wf_rows = list_execution_trace_for_workflow("wf-001")
        assert len(wf_rows) == 1


# -------- config_schema validators ---------------------------------------


def test_config_schema_includes_reliability_group():
    from wecom_ability_service.infra.config_schema import CONFIG_SCHEMA

    assert "reliability" in CONFIG_SCHEMA
    fields = CONFIG_SCHEMA["reliability"]["fields"]
    assert "HTTP_DEFAULT_TIMEOUT" in fields
    assert "CIRCUIT_FAILURE_THRESHOLD" in fields
    assert "RQ_DEFAULT_TIMEOUT" in fields


def test_config_schema_validates_integer_min_max():
    from wecom_ability_service.infra.config_schema import validate_config

    errors = validate_config(
        {
            "WECOM_CORP_ID": "x",
            "WECOM_SECRET": "x",
            "WECOM_AGENT_ID": "x",
            "WECOM_CONTACT_SECRET": "x",
            "WECOM_DEFAULT_OWNER_USERID": "x",
            "WECOM_CALLBACK_TOKEN": "x",
            "WECOM_CALLBACK_AES_KEY": "x",
            "HTTP_DEFAULT_TIMEOUT": "0",  # below min=1
            "HTTP_RETRY_MAX": "999",  # above max=10
        }
    )
    keys = {(e.get("key"), e.get("error")) for e in errors}
    assert ("HTTP_DEFAULT_TIMEOUT", "不能小于 1") in keys
    assert ("HTTP_RETRY_MAX", "不能大于 10") in keys


def test_outbound_client_picks_defaults_from_app_config(app):
    """When the caller doesn't override, ``get_outbound_client`` reads
    timeouts / retries from the reliability config group."""
    with app.app_context():
        from flask import current_app
        current_app.config["HTTP_DEFAULT_TIMEOUT"] = 7
        current_app.config["HTTP_RETRY_MAX"] = 3
        client = http_client.get_outbound_client("config_default_test")
        assert client.timeout == 7.0
        assert client.retry_max == 3


# -------- enqueue_task idempotency_key handling --------------------------


def test_enqueue_task_thread_fallback_runs_with_idempotency_key(app):
    from wecom_ability_service.infra.task_queue import enqueue_task

    seen = []

    def task(value):
        seen.append(value)

    with app.app_context():
        # Thread fallback can't dedup, but it must still execute the task
        # without crashing on the new kwargs.
        enqueue_task(
            task,
            "first",
            idempotency_key="dup-key",
            task_name="t",
            task_timeout=30,
        )
        enqueue_task(
            task,
            "second",
            idempotency_key="dup-key",
            task_name="t",
        )
    import time
    time.sleep(0.2)
    assert "first" in seen
    assert "second" in seen
