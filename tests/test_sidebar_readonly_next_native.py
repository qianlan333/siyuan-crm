from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.main import create_app
from aicrm_next.shared.signed_context import build_sidebar_owner_context_token


def _client() -> TestClient:
    return TestClient(create_app())


def _assert_readonly_ok(payload: dict) -> None:
    assert payload["route_owner"] == "ai_crm_next"
    assert payload["fallback_used"] is False
    assert payload["source_status"] in {"local_contract_probe", "identity_contact", "next_read_model"}
    assert payload["read_model_status"] in {"fixture", "identity_contact", "primary", "local_contract_probe", "next_read_model"}


def test_sidebar_readonly_routes_return_next_native_diagnostics() -> None:
    client = _client()

    responses = {
        "customer-context": client.get("/api/sidebar/customer-context?external_userid=wx_ext_001&owner_userid=ZhaoYanFang"),
        "profile": client.get("/api/sidebar/profile?external_userid=wx_ext_001&owner_userid=ZhaoYanFang"),
        "tags": client.get("/api/sidebar/tags?external_userid=wx_ext_001&owner_userid=ZhaoYanFang"),
        "binding-status": client.get("/api/sidebar/binding-status?external_userid=wx_ext_001&owner_userid=ZhaoYanFang"),
        "lead-pool": client.get("/api/sidebar/lead-pool/status?external_userid=wx_ext_001&owner_userid=ZhaoYanFang"),
        "signup-tags": client.get("/api/sidebar/signup-tags/status?external_userid=wx_ext_001&owner_userid=ZhaoYanFang"),
        "marketing-status": client.get("/api/sidebar/marketing-status?external_userid=wx_ext_001&owner_userid=ZhaoYanFang"),
    }

    assert {name: response.status_code for name, response in responses.items()} == {
        name: 200 for name in responses
    }
    for response in responses.values():
        _assert_readonly_ok(response.json())
        assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
        assert "X-AICRM-Compatibility-Facade" not in response.headers

    assert responses["customer-context"].json()["context"]["customer"]["external_userid"] == "wx_ext_001"
    assert responses["profile"].json()["profile"]["external_userid"] == "wx_ext_001"
    assert "付费意向" in responses["tags"].json()["tags"]
    assert responses["binding-status"].json()["is_bound"] is True
    assert responses["lead-pool"].json()["is_wecom_added"] is True
    assert responses["signup-tags"].json()["current_signup_status"] == "trial_9_9"
    assert responses["marketing-status"].json()["marketing_status"]["external_userid"] == "wx_ext_001"


def test_sidebar_readonly_routes_handle_missing_and_unknown_customers() -> None:
    client = _client()

    missing = client.get("/api/sidebar/marketing-status")
    unknown = client.get("/api/sidebar/marketing-status?external_userid=wx_missing_sidebar&owner_userid=ZhaoYanFang")

    assert missing.status_code == 400
    assert missing.json()["source_status"] == "input_error"
    assert missing.json()["fallback_used"] is False
    assert unknown.status_code == 404
    assert unknown.json()["source_status"] == "not_found"
    assert unknown.json()["fallback_used"] is False


def test_sidebar_readonly_routes_reject_missing_owner_userid_for_pii() -> None:
    client = _client()

    blocked_paths = [
        "/api/sidebar/customer-context?external_userid=wx_ext_001",
        "/api/sidebar/profile?external_userid=wx_ext_001",
        "/api/sidebar/tags?external_userid=wx_ext_001",
        "/api/sidebar/binding-status?external_userid=wx_ext_001",
        "/api/sidebar/contact-binding-status?external_userid=wx_ext_001",
        "/api/sidebar/lead-pool/status?external_userid=wx_ext_001",
        "/api/sidebar/signup-tags/status?external_userid=wx_ext_001",
        "/api/sidebar/marketing-status?external_userid=wx_ext_001",
        "/api/sidebar/v2/other-staff-messages?external_userid=wx_ext_001",
    ]

    for path in blocked_paths:
        response = client.get(path)
        assert response.status_code in {400, 404}, path
        assert response.json()["ok"] is False, path
        assert response.json()["fallback_used"] is False, path


def test_sidebar_binding_status_accepts_signed_owner_token() -> None:
    client = _client()
    token = build_sidebar_owner_context_token(viewer_userid="ZhaoYanFang", corp_id="ww-test")

    for path in [
        "/api/sidebar/binding-status?external_userid=wx_ext_001",
        "/api/sidebar/contact-binding-status?external_userid=wx_ext_001",
    ]:
        response = client.get(path, headers={"X-AICRM-Sidebar-Owner-Token": token})
        assert response.status_code == 200, path
        payload = response.json()
        assert payload["ok"] is True
        assert payload["is_bound"] is True
        assert payload["owner_userid"] == "ZhaoYanFang"


def test_sidebar_readonly_routes_filter_by_owner_userid() -> None:
    client = _client()

    allowed = client.get("/api/sidebar/customer-context?external_userid=wx_ext_001&owner_userid=ZhaoYanFang")
    assert allowed.status_code == 200
    assert allowed.json()["context"]["customer"]["owner_userid"] == "ZhaoYanFang"

    scoped_paths = [
        "/api/sidebar/customer-context?external_userid=wx_ext_001&owner_userid=LiuXiao",
        "/api/sidebar/profile?external_userid=wx_ext_001&owner_userid=LiuXiao",
        "/api/sidebar/tags?external_userid=wx_ext_001&owner_userid=LiuXiao",
        "/api/sidebar/binding-status?external_userid=wx_ext_001&owner_userid=LiuXiao",
        "/api/sidebar/contact-binding-status?external_userid=wx_ext_001&owner_userid=LiuXiao",
        "/api/sidebar/lead-pool/status?external_userid=wx_ext_001&owner_userid=LiuXiao",
        "/api/sidebar/signup-tags/status?external_userid=wx_ext_001&owner_userid=LiuXiao",
        "/api/sidebar/marketing-status?external_userid=wx_ext_001&owner_userid=LiuXiao",
        "/api/sidebar/v2/workbench?external_userid=wx_ext_001&owner_userid=LiuXiao",
        "/api/sidebar/v2/questionnaires?external_userid=wx_ext_001&owner_userid=LiuXiao",
        "/api/sidebar/v2/orders?external_userid=wx_ext_001&owner_userid=LiuXiao",
        "/api/sidebar/v2/other-staff-messages?external_userid=wx_ext_001&current_userid=LiuXiao",
    ]

    for path in scoped_paths:
        response = client.get(path)
        assert response.status_code == 404, path
        assert response.json()["source_status"] == "not_found"
        assert response.json()["fallback_used"] is False


def test_sidebar_readonly_production_unavailable_is_controlled(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.setenv("DATABASE_URL", "postgresql://sidebar-readonly:sidebar-readonly@127.0.0.1:1/aicrm_sidebar")
    client = _client()

    response = client.get("/api/sidebar/customer-context?external_userid=wx_ext_001&owner_userid=ZhaoYanFang")

    assert response.status_code == 503
    payload = response.json()
    assert payload["source_status"] == "production_unavailable"
    assert payload["fallback_used"] is False
    assert payload["degraded"] is True
