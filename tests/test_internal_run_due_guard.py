from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from aicrm_next.main import create_app
from aicrm_next.platform_foundation import internal_run_due_guard as guard


ROOT = Path(__file__).resolve().parents[1]
GUARD_FILE = ROOT / "aicrm_next/platform_foundation/internal_run_due_guard.py"
AUTOMATION_ROUTE = "/api/admin/automation-conversion/jobs/run-due"
AUTOMATION_PREVIEW_ROUTE = "/api/admin/automation-conversion/jobs/run-due/preview"
REPLY_MONITOR_ROUTE = "/api/admin/automation-conversion/reply-monitor/run-due"
REPLY_MONITOR_CAPTURE_ROUTE = "/api/admin/automation-conversion/reply-monitor/capture"
CAMPAIGN_ROUTE = "/api/admin/cloud-orchestrator/campaigns/run-due"


def _client() -> TestClient:
    return TestClient(create_app(), raise_server_exceptions=False)


def _headers(token: str = "guard-token") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _set_prod(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://probe:probe@example.invalid:5432/aicrm")


def test_missing_token_config_returns_503(monkeypatch):
    monkeypatch.delenv("AUTOMATION_INTERNAL_API_TOKEN", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)
    response = _client().post(AUTOMATION_ROUTE, json={"dry_run": True})

    assert response.status_code == 503
    payload = response.json()
    assert payload["error_code"] == "automation_internal_token_not_configured"
    assert payload["route_owner"] == "ai_crm_next"
    assert payload["fallback_used"] is False
    assert payload["side_effect_executed"] is False
    assert "X-AICRM-Compatibility-Facade" not in response.headers


def test_missing_or_invalid_token_returns_401(monkeypatch):
    monkeypatch.setenv("AUTOMATION_INTERNAL_API_TOKEN", "guard-token")
    client = _client()

    missing = client.post(AUTOMATION_ROUTE, json={"dry_run": True})
    invalid = client.post(AUTOMATION_ROUTE, json={"dry_run": True}, headers=_headers("wrong"))

    for response in (missing, invalid):
        assert response.status_code == 401
        payload = response.json()
        assert payload["error_code"] == "internal_token_required"
        assert payload["fallback_used"] is False
        assert payload["side_effect_executed"] is False
        assert "X-AICRM-Compatibility-Facade" not in response.headers


def test_bearer_token_accepted_for_dry_run(monkeypatch):
    monkeypatch.setenv("AUTOMATION_INTERNAL_API_TOKEN", "guard-token")
    response = _client().post(AUTOMATION_ROUTE, json={"dry_run": True}, headers=_headers())

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["route_owner"] == "ai_crm_next"
    assert payload["fallback_used"] is False
    assert payload["real_external_call_executed"] is False


def test_x_internal_api_token_accepted(monkeypatch):
    monkeypatch.setenv("AUTOMATION_INTERNAL_API_TOKEN", "guard-token")
    response = _client().post(
        REPLY_MONITOR_ROUTE,
        json={"dry_run": True},
        headers={"x-internal-api-token": "guard-token"},
    )

    assert response.status_code == 200
    assert response.json()["fallback_used"] is False


def test_options_not_guarded_when_token_missing(monkeypatch):
    monkeypatch.delenv("AUTOMATION_INTERNAL_API_TOKEN", raising=False)
    response = _client().options(AUTOMATION_ROUTE)

    assert response.status_code == 200
    assert response.json()["route_owner"] == "ai_crm_next"


def test_dry_run_true_skips_production_allowlist_guard(monkeypatch):
    monkeypatch.setenv("AUTOMATION_INTERNAL_API_TOKEN", "guard-token")
    _set_prod(monkeypatch)
    response = _client().post(AUTOMATION_ROUTE, json={"dry_run": True}, headers=_headers())

    assert response.status_code == 200
    payload = response.json()
    assert payload["real_external_call_executed"] is False
    assert payload["fallback_used"] is False


def test_production_real_run_without_automation_allowlist_returns_409(monkeypatch):
    monkeypatch.setenv("AUTOMATION_INTERNAL_API_TOKEN", "guard-token")
    _set_prod(monkeypatch)
    response = _client().post(AUTOMATION_ROUTE, json={"dry_run": False}, headers=_headers())

    assert response.status_code == 409
    payload = response.json()
    assert payload["error_code"] == "automation_run_due_allowlist_required"
    assert payload["required_allowlists"] == ["allow_task_ids", "allow_workflow_ids", "allow_node_ids"]
    assert payload["preflight_summary"]["allowlist_present"] is False
    assert payload["side_effect_executed"] is False


def test_production_real_run_with_automation_allowlist_allows_next_plan(monkeypatch):
    monkeypatch.setenv("AUTOMATION_INTERNAL_API_TOKEN", "guard-token")
    _set_prod(monkeypatch)
    response = _client().post(
        AUTOMATION_ROUTE,
        json={"dry_run": False, "allow_task_ids": [101]},
        headers=_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["timer_status"] == "planned_blocked"
    assert payload["real_external_call_executed"] is False


def test_production_real_run_without_campaign_allowlist_returns_409(monkeypatch):
    monkeypatch.setenv("AUTOMATION_INTERNAL_API_TOKEN", "guard-token")
    _set_prod(monkeypatch)
    response = _client().post(CAMPAIGN_ROUTE, json={"dry_run": False}, headers=_headers())

    assert response.status_code == 409
    payload = response.json()
    assert payload["error_code"] == "campaign_run_due_allowlist_required"
    assert payload["required_allowlists"] == ["allow_campaign_ids"]
    assert payload["side_effect_executed"] is False


def test_scheduled_safe_mode_without_allowlist_blocks_unknown_candidates(monkeypatch):
    monkeypatch.setenv("AUTOMATION_INTERNAL_API_TOKEN", "guard-token")
    _set_prod(monkeypatch)
    response = _client().post(
        AUTOMATION_ROUTE,
        json={"dry_run": False, "scheduled_safe_mode": True},
        headers=_headers(),
    )

    assert response.status_code == 409
    payload = response.json()
    assert payload["ok"] is True
    assert payload["status"] == "blocked_not_executed"
    assert payload["scheduled_safe_mode"] is True
    assert payload["manual_action_required"] is True
    assert payload["error_code"] == "active_automation_due_candidates_require_allowlist"
    assert payload["preview"]["candidate_status"] == "unknown_guarded"


def test_scheduled_safe_mode_with_explicit_zero_due_count_is_idle(monkeypatch):
    monkeypatch.setenv("AUTOMATION_INTERNAL_API_TOKEN", "guard-token")
    _set_prod(monkeypatch)
    response = _client().post(
        CAMPAIGN_ROUTE,
        json={"dry_run": False, "scheduled_safe_mode": True, "expected_due_count": 0},
        headers=_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["status"] == "idle"
    assert payload["scheduled_safe_mode"] is True
    assert payload["side_effect_executed"] is False
    assert payload["preview"]["candidate_status"] == "explicit_none"


def test_preview_and_reply_monitor_routes_require_token(monkeypatch):
    monkeypatch.setenv("AUTOMATION_INTERNAL_API_TOKEN", "guard-token")
    client = _client()

    for path in (AUTOMATION_PREVIEW_ROUTE, REPLY_MONITOR_ROUTE, REPLY_MONITOR_CAPTURE_ROUTE):
        response = client.post(path, json={})
        assert response.status_code == 401
        assert response.json()["error_code"] == "internal_token_required"


def test_internal_run_due_guard_module_has_no_legacy_imports():
    source = GUARD_FILE.read_text(encoding="utf-8")

    forbidden = [
        "wecom_ability_service",
        "legacy_flask_facade",
        "production_compat",
        "current_app",
        "from flask",
        "Flask",
        "X-AICRM-Compatibility-Facade",
    ]
    for marker in forbidden:
        assert marker not in source


def test_helper_truthy_and_production_runtime(monkeypatch):
    assert guard.parse_truthy("true") is True
    assert guard.parse_truthy("0") is False

    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    assert guard.is_production_runtime() is True
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://probe:probe@127.0.0.1:1/aicrm_probe")
    assert guard.is_production_runtime() is False
