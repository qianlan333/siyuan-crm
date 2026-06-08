from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from aicrm_next.main import create_app
from tools import check_next_production_cutover_readiness as cutover_checker
from tools import check_next_production_runtime_gaps as gap_checker

ROOT = Path(__file__).resolve().parents[1]
LEGACY_FACADE_PATH = ROOT / "aicrm_next/integration_gateway/legacy_flask_facade.py"


def test_health_degrades_when_production_uses_fixture(monkeypatch):
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    monkeypatch.delenv("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    client = TestClient(create_app())

    payload = client.get("/health").json()

    assert payload["runtime_owner"] == "ai_crm_next"
    assert payload["database_mode"] == "fixture"
    assert payload["fixture_mode"] is True
    assert payload["production_data_ready"] is False
    assert payload["ok"] is False
    assert payload["status"] == "degraded"


def test_health_reports_postgres_when_database_url_is_real(monkeypatch):
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://probe:probe@127.0.0.1:1/aicrm_probe")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    client = TestClient(create_app())

    payload = client.get("/health").json()

    assert payload["database_mode"] == "postgres"
    assert payload["fixture_mode"] is False
    assert payload["production_data_ready"] is True
    assert payload["runtime_owner"] == "ai_crm_next"


def test_next_production_facade_catches_legacy_routes_without_404(monkeypatch):
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://probe:probe@127.0.0.1:1/aicrm_probe")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.setenv("AUTOMATION_INTERNAL_API_TOKEN", "probe-token")
    client = TestClient(create_app())

    for path in [
        "/admin/customers",
        "/api/customers",
        "/api/admin/questionnaires",
        "/api/h5/wechat-pay/jsapi/orders",
        "/wecom/external-contact/callback",
    ]:
        response = client.get(path) if path.startswith("/admin") or path == "/api/customers" or "questionnaires" in path else client.post(path, json={})
        assert response.status_code != 404
        assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"


def test_runtime_gap_checker_returns_ok():
    result = gap_checker.run_check()

    assert result["ok"] is True
    assert result["database_mode"] == "postgres"
    assert result["route_404_blockers"] == []
    assert result["content_blockers"] == []
    assert result["oauth_blockers"] == []
    assert result["callback_currently_has_5013_fallback"] is True


def test_runtime_gap_checker_flags_fixture_questionnaire_payload():
    routes = {
        "GET /api/admin/questionnaires": {
            "status_code": 200,
            "json": {"questionnaires": [{"slug": "hxc-activation-v1"}, {"slug": "disabled-demo"}]},
        }
    }

    blockers, warnings = gap_checker._questionnaire_content_blockers(routes, local_probe_database=False)

    assert warnings == []
    assert "questionnaire_fixture_demo_only" in blockers


def test_runtime_gap_checker_flags_fixture_automation_payload():
    routes = {
        "GET /api/admin/automation-conversion/overview": {
            "status_code": 200,
            "json": {"generated_at": "fixture", "status": "partial"},
        }
    }

    blockers, warnings = gap_checker._automation_content_blockers(routes, local_probe_database=False)

    assert warnings == []
    assert "automation_generated_at_fixture" in blockers
    assert "automation_status_partial" in blockers


def test_runtime_gap_checker_flags_oauth_500_and_localhost_redirect():
    routes = {
        "GET /api/h5/wechat/oauth/start?next=/admin": {
            "status_code": 500,
            "json": {},
            "location": "",
        },
        "GET /api/h5/wechat-pay/oauth/start?next=/admin": {
            "status_code": 302,
            "json": {},
            "location": "https://open.weixin.qq.com/connect/oauth2/authorize?redirect_uri=http%3A%2F%2Flocalhost%2Fapi%2Fh5%2Fwechat-pay%2Foauth%2Fcallback",
        },
    }

    blockers = gap_checker._oauth_blockers(routes)

    assert any(item.startswith("oauth_start_500:/api/h5/wechat/oauth/start") for item in blockers)
    assert "oauth_redirect_uri_localhost:/api/h5/wechat-pay/oauth/start" in blockers


def test_legacy_flask_facade_runtime_file_removed():
    assert not LEGACY_FACADE_PATH.exists()


def test_legacy_flask_facade_forwarding_symbols_removed_from_runtime():
    markers = ("legacy_flask_facade", "forward_to_legacy_flask", "_legacy_app", "legacy_wecom_client_from_app")
    hits: list[str] = []
    for path in (ROOT / "aicrm_next").rglob("*.py"):
        if "__pycache__" in path.parts or path.as_posix().endswith("frontend_compat/legacy_routes.py"):
            continue
        text = path.read_text(encoding="utf-8")
        for marker in markers:
            if marker in text:
                hits.append(f"{path.relative_to(ROOT)}:{marker}")

    assert hits == []


def test_cutover_checker_contract(monkeypatch):
    monkeypatch.setattr(
        cutover_checker,
        "run_gap_check",
        lambda: {
            "ok": True,
            "database_mode": "postgres",
            "route_404_blockers": [],
            "content_blockers": [],
            "oauth_blockers": [],
            "automation_production_data_ready": True,
            "production_config_modified": False,
        },
    )
    monkeypatch.setattr(
        cutover_checker,
        "run_timer_check",
        lambda: {"ok": True, "safe_to_enable_timers": True, "dry_run_db_sentinel": {"ok": True}},
    )
    result = cutover_checker.run_check()

    assert result["ok"] is True
    assert result["database_mode"] == "postgres"
    assert result["fixture_in_production"] is False
    assert result["route_404_blockers"] == []
    assert result["callback_ready"] is True
    assert result["timer_routes_ready"] is True
    assert result["payment_routes_ready"] is True
    assert result["oauth_routes_ready"] is True
    assert result["safe_to_enable_timers"] is True
    assert result["safe_to_remove_5013_callback_fallback"] is False


def test_cutover_checker_requires_dry_run_db_sentinel(monkeypatch):
    monkeypatch.setattr(
        cutover_checker,
        "run_gap_check",
        lambda: {
            "ok": True,
            "database_mode": "postgres",
            "route_404_blockers": [],
            "content_blockers": [],
            "oauth_blockers": [],
            "automation_production_data_ready": True,
            "production_config_modified": False,
        },
    )
    monkeypatch.setattr(
        cutover_checker,
        "run_timer_check",
        lambda: {"ok": True, "safe_to_enable_timers": True, "dry_run_db_sentinel": {"ok": False}},
    )

    result = cutover_checker.run_check()

    assert result["safe_to_enable_timers"] is False
    assert result["dry_run_db_sentinel_ok"] is False


def test_cutover_checker_avoids_forbidden_status_markers():
    content = "\n".join(
        [
            (ROOT / "tools/check_next_production_cutover_readiness.py").read_text(encoding="utf-8"),
            (ROOT / "tools/check_next_production_runtime_gaps.py").read_text(encoding="utf-8"),
        ]
    )
    for marker in ("delete_ready", "production_ready", "production_approved"):
        assert marker not in content


def test_production_config_not_modified():
    assert gap_checker.production_config_modified() is False
