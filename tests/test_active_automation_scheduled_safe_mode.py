from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.main import create_app
from tools import check_active_automation_scheduled_safe_mode as checker


def _production_client(monkeypatch):
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.setenv("DATABASE_URL", "postgresql://probe:probe@127.0.0.1:1/aicrm_probe")
    monkeypatch.setenv("SECRET_KEY", "active-automation-scheduled-safe-mode")
    return TestClient(create_app())


def _auth_headers():
    return {"Authorization": "Bearer probe-token"}


def test_legacy_jobs_runner_is_not_part_of_scheduled_safe_mode():
    assert not hasattr(checker, "ACTIVE_JOBS_ROUTE")
    assert not checker.DB_SENTINEL_QUERIES


def test_campaign_scheduled_safe_mode_no_due_returns_idle_200(monkeypatch):
    client = _production_client(monkeypatch)

    response = client.post(
        checker.CAMPAIGN_ROUTE,
        json={
            "operator": "aicrm-campaign-run-due",
            "batch_size": 200,
            "dry_run": False,
            "scheduled_safe_mode": True,
            "expected_due_count": 0,
        },
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "idle"
    assert payload["side_effect_executed"] is False
    assert payload["fallback_used"] is False
    assert payload["preview"]["candidate_status"] == "explicit_none"


def test_campaign_scheduled_safe_mode_due_without_allowlist_returns_blocked_409(monkeypatch):
    client = _production_client(monkeypatch)

    response = client.post(
        checker.CAMPAIGN_ROUTE,
        json={
            "operator": "aicrm-campaign-run-due",
            "batch_size": 200,
            "dry_run": False,
            "scheduled_safe_mode": True,
            "expected_due_count": 1,
        },
        headers=_auth_headers(),
    )

    assert response.status_code == 409
    payload = response.json()
    assert payload["status"] == "blocked_not_executed"
    assert payload["error_code"] == "active_automation_due_candidates_require_allowlist"
    assert payload["side_effect_executed"] is False
    assert payload["fallback_used"] is False
    assert payload["preview"]["candidate_status"] == "explicit_present"


def test_raw_true_execution_without_allowlist_still_returns_409(monkeypatch):
    client = _production_client(monkeypatch)

    campaign = client.post(checker.CAMPAIGN_ROUTE, json={"operator": "manual", "batch_size": 1, "dry_run": False}, headers=_auth_headers())

    assert campaign.status_code == 409
    assert campaign.json()["error_code"] == "campaign_run_due_allowlist_required"


def test_checker_returns_ok_and_keeps_local_sentinel_stable(monkeypatch):
    monkeypatch.setattr(checker, "production_config_modified", lambda: False)

    result = checker.run_check()

    assert result["ok"] is True
    assert result["legacy_jobs_runner_removed_from_safe_mode"] is True
    assert result["scheduled_safe_mode_idle_ok"] is True
    assert result["scheduled_safe_mode_blocked_ok"] is True
    assert result["raw_true_execution_without_allowlist_still_409"] is True
    assert result["db_sentinel"]["ok"] is True
    assert result["retired_timers_not_enabled"] is True


def test_checker_detects_sentinel_change(monkeypatch):
    monkeypatch.setattr(checker, "scheduled_safe_mode_probe_env", lambda: _NoopContext())

    class FakeResponse:
        def __init__(self, status_code=200, payload=None):
            self.status_code = status_code
            self._payload = payload or {}

        def json(self):
            return dict(self._payload)

    class FakeClient:
        def post(self, route, json=None, headers=None, follow_redirects=False):
            if (json or {}).get("scheduled_safe_mode"):
                status = 409 if (json or {}).get("expected_due_count") else 200
                state = "blocked_not_executed" if status == 409 else "idle"
                return FakeResponse(
                    status,
                    {
                        "ok": True,
                        "status": state,
                        "scheduled_safe_mode": True,
                        "side_effect_executed": False,
                        "fallback_used": False,
                        "error_code": "active_automation_due_candidates_require_allowlist" if status == 409 else "",
                        "preview": {"candidate_status": "explicit_present" if status == 409 else "explicit_none"},
                    },
                )
            return FakeResponse(409, {"error_code": "campaign_run_due_allowlist_required"})

    sentinels = iter(
        [
            {"available": True, "reason": "", "values": {}},
            {"available": False, "reason": "sentinel_unavailable", "values": {}},
        ]
    )
    monkeypatch.setattr(checker, "_client", lambda: FakeClient())
    monkeypatch.setattr(checker, "_read_db_sentinel", lambda: next(sentinels))
    monkeypatch.setattr(checker, "_timer_enablement_status", lambda: {"retired_timers_not_enabled": True, "units": {}})
    monkeypatch.setattr(checker, "_docs_payloads_ready", lambda: (True, []))

    result = checker.run_check()

    assert result["ok"] is False
    assert "db_sentinel_changed_or_unavailable" in result["blockers"]


def test_runbook_marks_jobs_timer_retired_and_keeps_campaign_safe_mode_payload():
    content = open("docs/runbooks/active_automation_retirement.md", encoding="utf-8").read()

    assert checker.SYSTEMD_CAMPAIGN_PAYLOAD in content
    assert "scheduled_safe_mode" in content


def test_docs_do_not_use_forbidden_status_markers():
    content = "\n".join(
        open(path, encoding="utf-8").read()
        for path in [
            "docs/runbooks/active_automation_retirement.md",
        ]
    )
    for marker in ("delete_ready", "production_ready", "production_approved"):
        assert marker not in content


class _NoopContext:
    def __enter__(self):
        return None

    def __exit__(self, *args):
        return False
