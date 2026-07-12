from __future__ import annotations

from scripts.ops import check_admin_read_pages_smoke as smoke


def test_production_smoke_timeout_covers_observed_cold_admin_reads() -> None:
    assert smoke.DEFAULT_TIMEOUT_SECONDS == 20.0


def test_run_fails_when_required_admin_cookie_is_missing(monkeypatch) -> None:
    monkeypatch.setattr(smoke, "_admin_cookie_header", lambda: ("", "admin_cookie_sign_failed:RuntimeError"))
    monkeypatch.setattr(smoke, "_openapi_paths", lambda *args, **kwargs: set(smoke.REQUIRED_OPENAPI_PATHS))
    monkeypatch.setattr(
        smoke,
        "_probe",
        lambda *args, **kwargs: smoke.ProbeResult(
            path=kwargs.get("path", "/admin/customers"),
            status_code=200,
            ok=True,
            duration_ms=1,
            body_prefix="{}",
        ),
    )

    payload = smoke.run("http://127.0.0.1:5001", timeout=1, require_admin_cookie=True)

    assert payload["ok"] is False
    assert payload["admin_cookie_supplied"] is False
    assert payload["admin_cookie_required"] is True
    assert payload["admin_cookie_error"] == "admin_cookie_sign_failed:RuntimeError"
    assert ":admin_cookie_missing" in payload["failed_paths"]


def test_probe_rejects_protected_api_unauthorized_when_cookie_supplied(monkeypatch) -> None:
    monkeypatch.setattr(smoke, "_fetch", lambda *args, **kwargs: (401, {}, '{"ok":false}'))

    result = smoke._probe(
        "http://127.0.0.1:5001",
        "/api/admin/automation-agents",
        timeout=1,
        cookie_header="aicrm_next_admin_session=fake",
    )

    assert result.ok is False
    assert result.error == "admin_cookie_rejected:401"


def test_probe_rejects_admin_login_page_when_cookie_supplied(monkeypatch) -> None:
    monkeypatch.setattr(smoke, "_fetch", lambda *args, **kwargs: (200, {}, "<title>后台登录 · 客户管理后台</title>"))

    result = smoke._probe(
        "http://127.0.0.1:5001",
        "/admin/automation-agents",
        timeout=1,
        cookie_header="aicrm_next_admin_session=fake",
    )

    assert result.ok is False
    assert result.error == "admin_login_page_returned"


def test_probe_rejects_degraded_admin_api_payload(monkeypatch) -> None:
    monkeypatch.setattr(
        smoke,
        "_fetch",
        lambda *args, **kwargs: (
            200,
            {},
            '{"ok":true,"degraded":true,"error_code":"production_read_unavailable","read_model_status":"unavailable"}',
        ),
    )

    result = smoke._probe(
        "http://127.0.0.1:5001",
        "/api/admin/internal-events?limit=1",
        timeout=1,
        cookie_header="aicrm_next_admin_session=fake",
    )

    assert result.ok is False
    assert result.error == "admin_api_degraded:production_read_unavailable"


def test_probe_accepts_healthy_empty_admin_api_payload(monkeypatch) -> None:
    monkeypatch.setattr(
        smoke,
        "_fetch",
        lambda *args, **kwargs: (
            200,
            {},
            '{"ok":true,"degraded":false,"read_model_status":"primary","items":[],"total":0}',
        ),
    )

    result = smoke._probe(
        "http://127.0.0.1:5001",
        "/api/admin/internal-events?limit=1",
        timeout=1,
        cookie_header="aicrm_next_admin_session=fake",
    )

    assert result.ok is True
    assert result.error == ""
