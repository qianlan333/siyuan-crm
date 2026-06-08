from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.main import create_app
from tools import check_active_automation_run_due_guardrails as checker


def _production_client(monkeypatch):
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.setenv("DATABASE_URL", "postgresql://probe:probe@127.0.0.1:1/aicrm_probe")
    monkeypatch.setenv("AUTOMATION_INTERNAL_API_TOKEN", "probe-token")
    monkeypatch.setenv("SECRET_KEY", "active-automation-run-due-guardrails")
    return TestClient(create_app())


def _auth_headers():
    return {"Authorization": "Bearer probe-token"}


def test_jobs_run_due_dry_run_is_noop_and_not_forwarded(monkeypatch):
    client = _production_client(monkeypatch)

    response = client.post(
        checker.ACTIVE_JOBS_ROUTE,
        json={"dry_run": True, "jobs": ["sop", "conversion_workflow"]},
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["dry_run"] is True
    assert payload.get("side_effect_executed", False) is False
    assert payload["fallback_used"] is False
    assert payload["route_owner"] == "ai_crm_next"
    assert "X-AICRM-Compatibility-Facade" not in response.headers


def test_jobs_run_due_preview_body_is_read_only_and_not_forwarded(monkeypatch):
    client = _production_client(monkeypatch)

    response = client.post(
        checker.ACTIVE_JOBS_ROUTE,
        json={"preview": True, "jobs": ["sop", "conversion_workflow"]},
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["timer_status"] == "preview_only"
    assert payload.get("side_effect_executed", False) is False
    assert payload["fallback_used"] is False
    assert "X-AICRM-Compatibility-Facade" not in response.headers
    assert [item["job_code"] for item in payload["candidates"]] == ["sop", "conversion_workflow"]
    assert set(payload["candidates"][0]) >= {"job_code", "status", "estimated_actions"}


def test_jobs_run_due_preview_endpoint_is_available(monkeypatch):
    client = _production_client(monkeypatch)

    response = client.post(checker.ACTIVE_JOBS_PREVIEW_ROUTE, json={"jobs": ["sop"]}, headers=_auth_headers())

    assert response.status_code == 200
    assert response.json()["timer_status"] == "preview_only"


def test_jobs_run_due_real_execution_requires_allowlist_in_production(monkeypatch):
    client = _production_client(monkeypatch)

    response = client.post(
        checker.ACTIVE_JOBS_ROUTE,
        json={"dry_run": False, "jobs": ["sop", "conversion_workflow"], "max_send_records": 1, "max_outbound_tasks": 1},
        headers=_auth_headers(),
    )

    assert response.status_code == 409
    payload = response.json()
    assert payload["error_code"] == "automation_run_due_allowlist_required"
    assert payload["side_effect_executed"] is False
    assert payload["fallback_used"] is False
    assert payload["preflight_summary"]["allowlist_present"] is False


def test_campaign_dry_run_and_preview_are_noop(monkeypatch):
    client = _production_client(monkeypatch)

    dry_run = client.post(checker.CAMPAIGN_ROUTE, json={"dry_run": True, "batch_size": 1}, headers=_auth_headers())
    preview = client.post(checker.CAMPAIGN_PREVIEW_ROUTE, json={"batch_size": 1}, headers=_auth_headers())

    assert dry_run.status_code == 200
    assert dry_run.json().get("side_effect_executed", False) is False
    assert dry_run.json()["fallback_used"] is False
    assert preview.status_code == 200
    assert preview.json()["run_due_status"] == "preview_only"
    assert preview.json().get("side_effect_executed", False) is False
    assert preview.json()["fallback_used"] is False


def test_campaign_real_execution_requires_allowlist_in_production(monkeypatch):
    client = _production_client(monkeypatch)

    response = client.post(checker.CAMPAIGN_ROUTE, json={"dry_run": False, "batch_size": 1, "max_dispatch_count": 1}, headers=_auth_headers())

    assert response.status_code == 409
    payload = response.json()
    assert payload["error_code"] == "campaign_run_due_allowlist_required"
    assert payload["side_effect_executed"] is False
    assert payload["fallback_used"] is False


def test_active_guardrail_routes_still_require_internal_token(monkeypatch):
    client = _production_client(monkeypatch)

    response = client.post(checker.ACTIVE_JOBS_ROUTE, json={"preview": True})

    assert response.status_code == 401


def test_checker_returns_ok_and_keeps_local_sentinel_stable():
    result = checker.run_check()

    assert result["ok"] is True
    assert result["dry_run_noop"] is True
    assert result["preview_noop"] is True
    assert result["true_execution_without_allowlist_rejected"] is True
    assert result["db_sentinel"]["ok"] is True
    assert result["timers_not_enabled"] is True


def test_checker_detects_sentinel_change(monkeypatch):
    monkeypatch.setattr(checker, "guardrail_probe_env", lambda: _NoopContext())

    class FakeResponse:
        def __init__(self, status_code=200, payload=None):
            self.status_code = status_code
            self._payload = payload or {}

        def json(self):
            return dict(self._payload)

    class FakeClient:
        def post(self, route, json=None, headers=None, follow_redirects=False):
            if not headers:
                return FakeResponse(401, {})
            if route.endswith("/preview") or (json or {}).get("preview"):
                return FakeResponse(200, _noop_payload(route, preview=True))
            if (json or {}).get("dry_run"):
                return FakeResponse(200, _noop_payload(route, dry_run=True))
            if route == checker.ACTIVE_JOBS_ROUTE:
                return FakeResponse(409, {"error_code": "automation_run_due_allowlist_required"})
            return FakeResponse(409, {"error_code": "campaign_run_due_allowlist_required"})

    sentinels = iter(
        [
            {"available": True, "reason": "", "values": {key: "before" for key in checker.DB_SENTINEL_QUERIES}},
            {"available": True, "reason": "", "values": {key: "after" for key in checker.DB_SENTINEL_QUERIES}},
        ]
    )
    monkeypatch.setattr(checker, "_client", lambda: FakeClient())
    monkeypatch.setattr(checker, "_read_db_sentinel", lambda: next(sentinels))
    monkeypatch.setattr(checker, "_timer_enablement_status", lambda: {"timers_not_enabled": True, "units": {}})

    result = checker.run_check()

    assert result["ok"] is False
    assert "db_sentinel_changed_or_unavailable" in result["blockers"]


def test_docs_do_not_use_forbidden_status_markers():
    docs = [
        "docs/reply_system_reenable_runbook.md",
        "docs/active_automation_reenable_runbook.md",
    ]
    content = "\n".join(open(path, encoding="utf-8").read() for path in docs)
    for marker in ("delete_ready", "production_ready", "production_approved"):
        assert marker not in content


class _NoopContext:
    def __enter__(self):
        return None

    def __exit__(self, *args):
        return False


def _noop_payload(route: str, *, preview: bool = False, dry_run: bool = False):
    return {
        "ok": True,
        "preview": preview,
        "dry_run": dry_run,
        "side_effect_executed": False,
        "fallback_used": False,
        "route_owner": "ai_crm_next",
        "real_external_call_executed": False,
        "automation_runtime_executed": False,
        "wecom_send_executed": False,
        "path": route,
    }
