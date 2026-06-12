from __future__ import annotations

from scripts import smoke_automation_runtime_v2 as smoke


def test_missing_database_url_fails_clearly(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("STAGING_DATABASE_URL", raising=False)
    monkeypatch.delenv("AI_CRM_STAGING_DATABASE_URL", raising=False)

    code, payload = smoke.run_cli(["--scenario", "all"])

    assert code == 2
    assert payload["ok"] is False
    assert "DATABASE_URL" in payload["failures"][0]["error"]
    assert payload["scenarios"] == []


def test_dry_run_does_not_connect_or_write(monkeypatch):
    connected = {"value": False}

    def fail_connect(self):
        connected["value"] = True
        raise AssertionError("dry-run should not connect to database")

    monkeypatch.setattr(smoke.SmokeDatabase, "connect", fail_connect)

    code, payload = smoke.run_cli(["--database-url", "postgresql://example/db", "--scenario", "channel-binding"])

    assert code == 0
    assert payload["ok"] is True
    assert payload["environment"]["dry_run"] is True
    assert payload["scenarios"][0]["diagnostics"]["dry_run"] is True
    assert connected["value"] is False


def test_allow_write_executes_selected_scenario(monkeypatch):
    called = []

    def fake_connect(self):
        called.append("connect")

    def fake_close(self):
        called.append("close")

    def fake_scenario(self):
        called.append("scenario")
        return smoke.ScenarioResult("channel-binding", True, {"events": 1})

    monkeypatch.setattr(smoke.SmokeDatabase, "connect", fake_connect)
    monkeypatch.setattr(smoke.SmokeDatabase, "close", fake_close)
    monkeypatch.setattr(smoke.SmokeRunner, "_preflight_queue_safety", lambda self: None)
    monkeypatch.setattr(smoke.SmokeRunner, "_apply_worker_claimed_result", lambda self, results, failures: None)
    monkeypatch.setattr(smoke.SmokeRunner, "scenario_channel_binding", fake_scenario)
    monkeypatch.setattr(smoke, "SmokeHttpClient", lambda *args, **kwargs: object())

    code, payload = smoke.run_cli(
        [
            "--database-url",
            "postgresql://example/db",
            "--scenario",
            "channel-binding",
            "--allow-write",
        ]
    )

    assert code == 0
    assert payload["ok"] is True
    assert payload["environment"]["dry_run"] is False
    assert called == ["connect", "scenario", "close"]


def test_remote_app_does_not_push_flask_context_or_import_legacy(monkeypatch):
    called = []

    def fake_connect(self):
        called.append("connect")

    def fake_close(self):
        called.append("close")

    def fake_scenario(self):
        called.append("scenario")
        return smoke.ScenarioResult("channel-binding", True, {"events": 1})

    monkeypatch.setattr(smoke.SmokeDatabase, "connect", fake_connect)
    monkeypatch.setattr(smoke.SmokeDatabase, "close", fake_close)
    monkeypatch.setattr(smoke.SmokeRunner, "_preflight_queue_safety", lambda self: None)
    monkeypatch.setattr(smoke.SmokeRunner, "_apply_worker_claimed_result", lambda self, results, failures: None)
    monkeypatch.setattr(smoke.SmokeRunner, "scenario_channel_binding", fake_scenario)
    monkeypatch.setattr(smoke, "SmokeHttpClient", lambda *args, **kwargs: object())

    code, payload = smoke.run_cli(
        [
            "--database-url",
            "postgresql://example/db",
            "--app-url",
            "https://staging.example.test",
            "--scenario",
            "channel-binding",
            "--allow-write",
        ]
    )

    assert code == 0
    assert payload["ok"] is True
    assert payload["environment"]["mode"] == "remote-app"
    assert called == ["connect", "scenario", "close"]


def test_local_app_uses_next_test_client_not_legacy_create_app(monkeypatch):
    captured = {}

    class FakeTestClient:
        def __init__(self, app):
            captured["app"] = app

    monkeypatch.setitem(__import__("sys").modules, "wecom_ability_service", None)
    monkeypatch.setitem(__import__("sys").modules, "wecom_ability_service.observability", None)
    monkeypatch.setattr("fastapi.testclient.TestClient", FakeTestClient)

    client = smoke.SmokeHttpClient("")

    assert client.mode == "local-app"
    assert "app" in captured


def test_all_scenarios_include_runtime_v2_release_blockers():
    names = smoke.scenario_list(["all"])

    assert names == [
        "channel-binding",
        "large-channel-protection",
        "future-scan",
        "questionnaire-agent",
        "payment",
        "webhook",
        "scheduled",
    ]


class FakeCleanupDb:
    def __init__(self):
        self.sql: list[str] = []
        self.params: list[tuple] = []
        self.committed = False
        self.closed = False

    def connect(self):
        self.sql.append("CONNECT")

    def scalar(self, sql, params=()):
        self.sql.append(sql)
        self.params.append(params)
        return 1

    def commit(self):
        self.committed = True

    def rollback(self):
        raise AssertionError("cleanup should not rollback on success")

    def close(self):
        self.closed = True


def test_cleanup_is_limited_to_smoke_run_scope():
    fake_db = FakeCleanupDb()
    runner = smoke.SmokeRunner(
        database_url="postgresql://example/db",
        smoke_run_id="smoke_runtime_v2_abc123",
        dry_run=False,
        allow_write=True,
        db=fake_db,  # type: ignore[arg-type]
    )

    result = runner.cleanup()
    joined_sql = "\n".join(fake_db.sql)

    assert result["ok"] is True
    assert result["cancelled_broadcast_jobs"] == 1
    assert result["cancelled_task_plans"] == 1
    assert result["deleted_memberships"] == 0
    assert "automation_program WHERE program_code LIKE" in joined_sql
    assert "broadcast_jobs" in joined_sql
    assert "source_type = 'automation_runtime_v2'" in joined_sql
    assert "status IN ('queued', 'pending', 'planned')" in joined_sql
    assert "status = 'claimed'" in joined_sql
    assert "outbound_task_id" in joined_sql
    assert "UPDATE automation_membership_v2" not in joined_sql
    assert fake_db.params == [("smoke_runtime_v2_abc123%",), ("smoke_runtime_v2_abc123%",)]
    assert fake_db.committed is True
    assert fake_db.closed is True


def test_worker_claimed_smoke_jobs_fail_scenarios():
    class FakeDb:
        def scalar(self, sql, params=()):
            assert "broadcast_jobs" in sql
            assert params == ("smoke_runtime_v2_worker%",)
            return 2

    runner = smoke.SmokeRunner(
        database_url="postgresql://example/db",
        smoke_run_id="smoke_runtime_v2_worker",
        dry_run=False,
        allow_write=True,
        db=FakeDb(),  # type: ignore[arg-type]
    )
    results = [smoke.ScenarioResult("channel-binding", True)]
    failures: list[dict] = []

    runner._apply_worker_claimed_result(results, failures)

    assert results[0].ok is False
    assert results[0].diagnostics["worker_claimed"] is True
    assert failures[0]["error"] == "worker_claimed_smoke_jobs"
