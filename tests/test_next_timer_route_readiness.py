from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from aicrm_next.main import create_app
from tools import check_next_timer_route_readiness as checker

ROOT = Path(__file__).resolve().parents[1]


def test_timer_routes_are_next_owned_and_guarded(monkeypatch):
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.setenv("DATABASE_URL", "postgresql://probe:probe@127.0.0.1:1/aicrm_probe")
    monkeypatch.setenv("AUTOMATION_INTERNAL_API_TOKEN", "probe-token")
    client = TestClient(create_app())

    for route in checker.TIMER_ROUTES:
        unauth = client.post(route, json={}, follow_redirects=False)
        auth = client.post(route, json={}, headers={"Authorization": "Bearer probe-token"}, follow_redirects=False)
        assert unauth.status_code == 401
        assert auth.status_code != 404
        assert unauth.headers["X-AICRM-Route-Owner"] == "ai_crm_next"


def test_timer_body_dry_run_is_noop_and_not_forwarded(monkeypatch):
    client = _production_client(monkeypatch)

    response = client.post(
        "/api/admin/automation-conversion/reply-monitor/run-due",
        json={"dry_run": True},
        headers={"Authorization": "Bearer probe-token"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["dry_run"] is True
    assert payload.get("side_effect_executed", False) is False
    assert payload["fallback_used"] is False
    assert payload["route_owner"] == "ai_crm_next"
    assert "compatibility_facade" not in payload


def test_timer_query_dry_run_is_noop_and_not_forwarded(monkeypatch):
    client = _production_client(monkeypatch)

    response = client.post(
        "/api/admin/automation-conversion/reply-monitor/capture?dry_run=true",
        json={},
        headers={"Authorization": "Bearer probe-token"},
    )

    assert response.status_code == 200
    assert response.json()["fallback_used"] is False
    assert "X-AICRM-Compatibility-Facade" not in response.headers


def test_timer_header_dry_run_is_noop_without_probe_env_flag(monkeypatch):
    client = _production_client(monkeypatch)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_PRODUCTION_PROBE_DRY_RUN", raising=False)

    response = client.post(
        "/api/admin/automation-conversion/jobs/run-due",
        json={},
        headers={"Authorization": "Bearer probe-token", "X-AICRM-Dry-Run": "true"},
    )

    assert response.status_code == 200
    assert response.json()["fallback_used"] is False
    assert "X-AICRM-Compatibility-Facade" not in response.headers


def test_timer_without_dry_run_and_without_token_still_401(monkeypatch):
    client = _production_client(monkeypatch)

    response = client.post("/api/admin/cloud-orchestrator/campaigns/run-due", json={})

    assert response.status_code == 401


def test_timer_readiness_checker_returns_ok():
    result = checker.run_check()

    assert result["ok"] is True
    assert result["safe_to_enable_timers"] is False
    assert "automation_production_data_not_ready" in result["warnings"]
    assert "dry_run_db_sentinel_not_passed" not in result["blockers"]


def test_timer_readiness_safe_only_after_automation_data_ready(monkeypatch):
    monkeypatch.setattr(
        checker,
        "timer_probe_env",
        lambda: _NoopContext(),
    )

    class FakeResponse:
        def __init__(self, status_code, payload=None):
            self.status_code = status_code
            self._payload = payload or {}

        def json(self):
            return dict(self._payload)

    class FakeClient:
        def post(self, route, json=None, headers=None, follow_redirects=False):
            if headers:
                return FakeResponse(
                    200,
                    {
                        "ok": True,
                        "dry_run": True,
                        "side_effect_executed": False,
                        "fallback_used": False,
                        "route_owner": "ai_crm_next",
                        "path": route.split("?", 1)[0],
                        "real_external_call_executed": False,
                    },
                )
            return FakeResponse(401)

        def get(self, route, follow_redirects=False):
            return FakeResponse(
                200,
                {
                    "ok": True,
                    "generated_at": "2026-05-22T00:00:00Z",
                    "status": "live",
                    "source_status": "production_postgres",
                },
            )

    monkeypatch.setattr(checker, "_client", lambda: FakeClient())
    monkeypatch.setattr(
        checker,
        "_read_db_sentinel",
        lambda: {"available": True, "reason": "", "values": {key: "same" for key in checker.DB_SENTINEL_QUERIES}},
    )

    result = checker.run_check()

    assert result["ok"] is True
    assert result["safe_to_enable_timers"] is True
    assert result["automation_production_data_ready"] is True
    assert result["dry_run_db_sentinel"]["ok"] is True
    assert result["blockers"] == []
    assert result["warnings"] == []


def test_timer_readiness_blocks_when_db_sentinel_changes(monkeypatch):
    monkeypatch.setattr(checker, "timer_probe_env", lambda: _NoopContext())

    class FakeResponse:
        status_code = 200

        def __init__(self, payload=None):
            self._payload = payload or {
                "ok": True,
                "dry_run": True,
                "side_effect_executed": False,
                "fallback_used": False,
                "route_owner": "ai_crm_next",
                "real_external_call_executed": False,
            }

        def json(self):
            return dict(self._payload)

    class FakeClient:
        def post(self, route, json=None, headers=None, follow_redirects=False):
            return FakeResponse() if headers else _StatusOnlyResponse(401)

        def get(self, route, follow_redirects=False):
            return FakeResponse({"generated_at": "now", "status": "live", "source_status": "production_postgres"})

    sentinels = iter(
        [
            {"available": True, "reason": "", "values": {key: "before" for key in checker.DB_SENTINEL_QUERIES}},
            {"available": True, "reason": "", "values": {key: "after" for key in checker.DB_SENTINEL_QUERIES}},
        ]
    )
    monkeypatch.setattr(checker, "_client", lambda: FakeClient())
    monkeypatch.setattr(checker, "_read_db_sentinel", lambda: next(sentinels))

    result = checker.run_check()

    assert result["safe_to_enable_timers"] is False
    assert "dry_run_db_sentinel_not_passed" in result["blockers"]


class _NoopContext:
    def __enter__(self):
        return None

    def __exit__(self, *args):
        return False


class _StatusOnlyResponse:
    def __init__(self, status_code):
        self.status_code = status_code

    def json(self):
        return {}


def _production_client(monkeypatch):
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.setenv("DATABASE_URL", "postgresql://probe:probe@127.0.0.1:1/aicrm_probe")
    monkeypatch.setenv("AUTOMATION_INTERNAL_API_TOKEN", "probe-token")
    monkeypatch.setenv("SECRET_KEY", "next-timer-route-readiness")
    return TestClient(create_app())


def test_timer_readiness_checker_does_not_use_forbidden_status_markers():
    content = (ROOT / "tools/check_next_timer_route_readiness.py").read_text(encoding="utf-8")
    for marker in ("delete_ready", "production_ready", "production_approved"):
        assert marker not in content
