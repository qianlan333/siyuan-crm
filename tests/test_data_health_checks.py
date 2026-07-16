from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture()
def client(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from aicrm_next.main import create_app

    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "0")
    monkeypatch.setenv("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", "1")
    return TestClient(create_app(), raise_server_exceptions=False)


def test_data_health_summary_exposes_registered_checks(client) -> None:
    response = client.get("/api/admin/data-health/summary")

    assert response.status_code == 200
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    body = response.json()
    assert body["ok"] is True
    assert body["overall_status"] == "ok"
    check_ids = {item["check_id"] for item in body["checks"]}
    assert {
        "identity_legacy_column_guard",
        "table_lifecycle_manifest_guard",
        "retired_table_runtime_reference_guard",
        "schema_drift_guard",
        "unionid_orphan_fact_guard",
        "identity_resolution_queue_backlog",
        "projection_freshness_customer_read_model",
        "broadcast_job_blocked_backlog",
        "external_effect_failed_retryable_backlog",
        "deprecated_execution_settings_present",
        "fake_stub_route_exposed",
        "external_effect_approved_not_queued",
        "questionnaire_submission_without_user_guard",
        "payment_order_without_user_guard",
        "customer_360_freshness_guard",
    } <= check_ids
    assert body["counts"]["fail"] == 0
    assert body["counts"]["ok"] >= 3
    assert body["counts"]["not_applicable"] >= 1


def test_customer_360_freshness_guard_registers_phase4_probes(client) -> None:
    response = client.get("/api/admin/data-health/checks/customer_360_freshness_guard")
    payload = response.json()

    assert response.status_code == 200
    assert payload["ok"] is True
    check = payload["check"]
    assert check["status"] == "not_applicable"
    assert check["evidence"]["freshness_probes"] == [
        "latest_identity_update",
        "latest_order",
        "latest_questionnaire",
        "latest_message",
        "latest_projection_refresh",
    ]
    assert set(check["evidence"]["source_tables"]) >= {
        "crm_user_identity",
        "questionnaire_submissions",
        "archived_messages",
        "customer_detail_snapshot_next",
    }


def test_data_health_checks_do_not_expose_raw_identity_values(client) -> None:
    response = client.get("/api/admin/data-health/checks")

    assert response.status_code == 200
    text = response.text
    for forbidden in ("external_userid_value", "openid_value", "mobile_normalized", "raw_payload_json"):
        assert forbidden not in text


def test_data_health_check_detail_and_missing_check(client) -> None:
    detail = client.get("/api/admin/data-health/checks/table_lifecycle_manifest_guard")

    assert detail.status_code == 200
    payload = detail.json()
    assert payload["ok"] is True
    assert payload["check"]["check_id"] == "table_lifecycle_manifest_guard"
    assert payload["check"]["status"] == "ok"

    missing = client.get("/api/admin/data-health/checks/not_a_check")
    assert missing.status_code == 404
    assert missing.json()["error_code"] == "data_health_check_not_found"


def test_schema_drift_guard_reports_manifest_and_live_schema_mismatches() -> None:
    from aicrm_next.data_health.schema_drift import evaluate_schema_drift

    manifest = {
        "tables": {
            "declared_missing": {
                "domain": "test",
                "lifecycle": "canonical",
                "write_owner": "tests",
                "drop_candidate": False,
            },
            "retired_still_exists": {
                "domain": "test",
                "lifecycle": "retired",
                "replacement": "declared_missing",
                "drop_candidate": False,
            },
            "canonical_without_owner": {
                "domain": "test",
                "lifecycle": "canonical",
                "write_owner": "",
                "drop_candidate": False,
            },
            "pii_without_level": {
                "domain": "test",
                "lifecycle": "canonical",
                "write_owner": "tests",
                "drop_candidate": False,
            },
            "queue_without_status_enum": {
                "domain": "test",
                "lifecycle": "queue",
                "write_owner": "tests",
                "drop_candidate": False,
            },
            "queue_with_status_enum": {
                "domain": "test",
                "lifecycle": "queue",
                "write_owner": "tests",
                "status_enum": {"column": "status"},
                "drop_candidate": False,
            },
        }
    }
    actual_schema = {
        "retired_still_exists": {"id"},
        "canonical_without_owner": {"id"},
        "pii_without_level": {"id", "mobile"},
        "queue_without_status_enum": {"id", "status"},
        "queue_with_status_enum": {"id", "status"},
        "unregistered_live_table": {"id"},
    }

    violations = evaluate_schema_drift(manifest=manifest, actual_schema=actual_schema)
    joined = "\n".join(violations)

    assert "declared_missing: manifest declares physical lifecycle=canonical but table is missing" in joined
    assert "retired_still_exists: retired table still exists in public schema" in joined
    assert "canonical_without_owner: canonical table must declare write_owner" in joined
    assert "pii_without_level: table has PII-like columns but missing pii_level" in joined
    assert "queue_without_status_enum: queue table has status/state column but missing status_enum" in joined
    assert "unregistered_live_table: table exists but is not registered in lifecycle manifest" in joined
    assert "queue_with_status_enum" not in joined


class _FakeResult:
    def __init__(self, row: dict):
        self._row = row

    def mappings(self):
        return self

    def first(self):
        return self._row


class _FakeSession:
    def __init__(self, row: dict, calls: list[str]):
        self._row = row
        self._calls = calls

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, statement):
        self._calls.append(str(statement))
        return _FakeResult(self._row)


def _patch_health_db(monkeypatch, row: dict) -> list[str]:
    from aicrm_next.data_health import checks

    calls: list[str] = []
    monkeypatch.setattr(checks, "database_schema_available", lambda: True)
    monkeypatch.setattr(checks, "get_session_factory", lambda: lambda: _FakeSession(row, calls))
    return calls


def test_projection_freshness_probe_uses_live_projection_counts(monkeypatch) -> None:
    from aicrm_next.data_health import checks

    calls = _patch_health_db(
        monkeypatch,
        {
            "list_count": 12,
            "detail_count": 0,
            "list_stale_minutes": 5,
            "detail_stale_minutes": 90,
        },
    )

    result = checks._projection_freshness_customer_read_model()

    assert result.status == "fail"
    assert result.evidence["list_count"] == 12
    assert result.evidence["detail_count"] == 0
    assert any("customer_list_index_next" in sql and "customer_detail_snapshot_next" in sql for sql in calls)
    assert "external_userid_value" not in str(result.evidence)


def test_projection_freshness_probe_accepts_managed_fresh_parity(monkeypatch) -> None:
    from aicrm_next.data_health import checks

    _patch_health_db(
        monkeypatch,
        {
            "list_count": 12,
            "detail_count": 12,
            "refresh_state_present": True,
            "refresh_source_count": 12,
            "refresh_target_count": 12,
            "refresh_age_minutes": 5,
        },
    )

    result = checks._projection_freshness_customer_read_model()

    assert result.status == "ok"
    assert result.evidence["refresh_state_present"] is True


def test_broadcast_backlog_probe_counts_blocked_and_retryable(monkeypatch) -> None:
    from aicrm_next.data_health import checks

    calls = _patch_health_db(
        monkeypatch,
        {
            "blocked_count": 1,
            "failed_terminal_count": 0,
            "due_retryable_count": 2,
            "oldest_terminal_hours": 3.5,
        },
    )

    result = checks._broadcast_job_blocked_backlog()

    assert result.status == "fail"
    assert result.evidence["blocked_count"] == 1
    assert result.evidence["due_retryable_count"] == 2
    assert any("FROM broadcast_jobs" in sql for sql in calls)


def test_broadcast_backlog_probe_keeps_historical_terminal_evidence_without_permanent_failure(monkeypatch) -> None:
    from aicrm_next.data_health import checks

    _patch_health_db(
        monkeypatch,
        {
            "recent_blocked_count": 0,
            "recent_failed_terminal_count": 0,
            "historical_blocked_count": 8,
            "historical_failed_terminal_count": 6,
            "due_retryable_count": 0,
            "oldest_terminal_hours": 72,
        },
    )

    result = checks._broadcast_job_blocked_backlog()

    assert result.status == "ok"
    assert result.evidence["blocked_count"] == 0
    assert result.evidence["historical_blocked_count"] == 8
    assert result.evidence["historical_failed_terminal_count"] == 6


def test_previously_placeholder_probes_are_live_and_green_with_zero_actionable_counts(monkeypatch) -> None:
    from aicrm_next.data_health import checks

    _patch_health_db(
        monkeypatch,
        {
            "questionnaire_orphan_count": 0,
            "wechat_pay_orphan_count": 0,
            "alipay_pay_orphan_count": 0,
            "wechat_shop_orphan_count": 0,
            "broadcast_orphan_count": 0,
            "approved_not_runnable_count": 0,
            "approved_job_count": 4,
            "missing_unionid_count": 0,
            "guarded_missing_unionid_count": 0,
            "unguarded_missing_unionid_count": 0,
            "missing_continuation_guard_count": 0,
            "identity_dependent_effect_without_unionid_count": 0,
            "missing_identity_count": 0,
            "historical_pre_cutover_count": 48,
            "wechat_pay_missing_user_count": 0,
            "alipay_pay_missing_user_count": 0,
            "wechat_shop_missing_user_count": 0,
            "refresh_state_present": True,
            "refresh_age_minutes": 5,
            "identity_lag_minutes": 2,
            "order_lag_minutes": -10,
            "questionnaire_lag_minutes": 1,
            "message_lag_minutes": 3,
        },
    )

    results = [
        checks._unionid_orphan_fact_guard(),
        checks._external_effect_approved_not_queued(),
        checks._questionnaire_submission_without_user_guard(),
        checks._payment_order_without_user_guard(),
        checks._customer_360_freshness_guard(),
    ]

    assert [result.status for result in results] == ["ok"] * 5
    assert all(result.status != "not_applicable" for result in results)


def test_questionnaire_submission_guard_accepts_quarantined_missing_unionids(monkeypatch) -> None:
    from aicrm_next.data_health import checks

    _patch_health_db(
        monkeypatch,
        {
            "missing_unionid_count": 3,
            "guarded_missing_unionid_count": 3,
            "unguarded_missing_unionid_count": 0,
            "missing_continuation_guard_count": 0,
            "identity_dependent_effect_without_unionid_count": 0,
            "missing_identity_count": 0,
            "historical_pre_cutover_count": 48,
        },
    )

    result = checks._questionnaire_submission_without_user_guard()

    assert result.status == "ok"
    assert result.evidence["missing_unionid_count"] == 3
    assert result.evidence["guarded_missing_unionid_count"] == 3
    assert result.evidence["unguarded_missing_unionid_count"] == 0


def test_questionnaire_submission_guard_rejects_unguarded_missing_unionid(monkeypatch) -> None:
    from aicrm_next.data_health import checks

    _patch_health_db(
        monkeypatch,
        {
            "missing_unionid_count": 2,
            "guarded_missing_unionid_count": 1,
            "unguarded_missing_unionid_count": 1,
            "missing_continuation_guard_count": 1,
            "identity_dependent_effect_without_unionid_count": 0,
            "missing_identity_count": 0,
            "historical_pre_cutover_count": 48,
        },
    )

    result = checks._questionnaire_submission_without_user_guard()

    assert result.status == "fail"
    assert result.evidence["unguarded_missing_unionid_count"] == 1
    assert result.evidence["missing_continuation_guard_count"] == 1


def test_external_effect_backlog_probe_accepts_small_retryable_queue(monkeypatch) -> None:
    from aicrm_next.data_health import checks

    calls = _patch_health_db(
        monkeypatch,
        {
            "failed_retryable_count": 2,
            "failed_terminal_count": 0,
            "blocked_count": 0,
            "due_retryable_count": 2,
            "oldest_failed_retryable_age_seconds": 120,
        },
    )

    result = checks._external_effect_failed_retryable_backlog()

    assert result.status == "ok"
    assert result.evidence["failed_retryable_count"] == 2
    assert result.evidence["oldest_failed_retryable_age_seconds"] == 120
    assert any("FROM external_effect_job" in sql for sql in calls)


def test_external_effect_backlog_keeps_historical_terminal_evidence_without_permanent_failure(monkeypatch) -> None:
    from aicrm_next.data_health import checks

    _patch_health_db(
        monkeypatch,
        {
            "failed_retryable_count": 0,
            "recent_failed_terminal_count": 0,
            "recent_blocked_count": 0,
            "historical_failed_terminal_count": 7,
            "historical_blocked_count": 3,
            "due_retryable_count": 0,
            "oldest_failed_retryable_age_seconds": 0,
        },
    )

    result = checks._external_effect_failed_retryable_backlog()

    assert result.status == "ok"
    assert result.evidence["failed_terminal_count"] == 0
    assert result.evidence["blocked_count"] == 0
    assert result.evidence["historical_failed_terminal_count"] == 7
    assert result.evidence["historical_blocked_count"] == 3
    assert result.evidence["terminal_lookback_hours"] == 24


def test_retired_runtime_reference_scan_reads_each_source_once(tmp_path, monkeypatch) -> None:
    from tools import check_data_table_lifecycle as lifecycle

    runtime_root = tmp_path / "aicrm_next"
    runtime_root.mkdir()
    first = runtime_root / "first.py"
    second = runtime_root / "second.py"
    first.write_text("SELECT * FROM RETIRED_1\n", encoding="utf-8")
    second.write_text("SELECT 1\n", encoding="utf-8")
    tables = {f"retired_{index}": {"lifecycle": "retired"} for index in range(1, 51)}

    original_read_text = Path.read_text
    read_counts: dict[Path, int] = {}

    def tracked_read_text(path: Path, *args, **kwargs) -> str:
        if path.parent == runtime_root:
            read_counts[path] = read_counts.get(path, 0) + 1
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", tracked_read_text)

    violations = lifecycle._retired_runtime_reference_violations(tmp_path, tables)

    assert violations == ["aicrm_next/first.py references retired table retired_1"]
    assert read_counts == {first: 1, second: 1}
