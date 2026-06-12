from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.main import create_app


def _client(monkeypatch) -> TestClient:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)
    return TestClient(create_app(), raise_server_exceptions=False)


def _assert_next(payload: dict) -> None:
    assert payload["route_owner"] == "ai_crm_next"
    assert payload["fallback_used"] is False


def test_sidebar_v2_workbench_and_read_panels_are_next_owned(monkeypatch):
    client = _client(monkeypatch)

    workbench = client.get("/api/sidebar/v2/workbench?external_userid=wx_ext_001")
    questionnaires = client.get("/api/sidebar/v2/questionnaires?external_userid=wx_ext_001")
    products = client.get("/api/sidebar/v2/products?external_userid=wx_ext_001")
    orders = client.get("/api/sidebar/v2/orders?external_userid=wx_ext_001")

    for response in (workbench, questionnaires, products, orders):
        assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
        payload = response.json()
        _assert_next(payload)
        assert "X-AICRM-Compatibility-Facade" not in response.headers
        assert payload["source_status"] in {"next_read_model", "production_unavailable"}


def test_sidebar_v2_profile_context_and_binding_status_use_next_read_models(monkeypatch):
    client = _client(monkeypatch)

    context = client.get("/api/sidebar/customer-context?external_userid=wx_ext_001").json()
    profile = client.get("/api/sidebar/profile?external_userid=wx_ext_001").json()
    binding = client.get("/api/sidebar/contact-binding-status?external_userid=wx_ext_001").json()

    for payload in (context, profile, binding):
        assert payload["ok"] is True
        _assert_next(payload)
    assert context["context"]["customer"]["external_userid"] == "wx_ext_001"
    assert profile["profile"]["external_userid"] == "wx_ext_001"
    assert binding["is_bound"] is True
    assert binding["mobile"] == "13800138000"


def test_sidebar_jssdk_config_is_fake_safe(monkeypatch):
    client = _client(monkeypatch)

    response = client.get("/api/sidebar/jssdk-config?url=https://example.com/sidebar/bind-mobile")
    payload = response.json()

    assert response.status_code == 200
    _assert_next(payload)
    assert payload["source_status"] == "next_jssdk_adapter"
    assert payload["real_external_call_executed"] is False
    assert "getCurExternalContact" in payload["jsApiList"]


def test_sidebar_bind_mobile_command_stays_local_only(monkeypatch):
    client = _client(monkeypatch)

    response = client.post(
        "/api/sidebar/bind-mobile",
        json={"external_userid": "wx_ext_001", "mobile": "13800138000", "owner_userid": "ZhaoYanFang"},
    )
    payload = response.json()

    assert response.status_code == 200
    _assert_next(payload)
    assert payload["real_external_call_executed"] is False
    assert payload["source_status"] == "next_command"
