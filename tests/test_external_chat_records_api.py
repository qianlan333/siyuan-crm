from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.main import create_app


TOKEN = "external-chat-token"


def _client(monkeypatch, *, token_configured: bool = True) -> TestClient:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    monkeypatch.setenv("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.setenv("SECRET_KEY", "external-chat-api")
    if token_configured:
        monkeypatch.setenv("ARCHIVE_INTERNAL_API_TOKEN", TOKEN)
    else:
        monkeypatch.delenv("ARCHIVE_INTERNAL_API_TOKEN", raising=False)
    return TestClient(create_app(), raise_server_exceptions=False)


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


def test_external_chat_records_requires_configured_bearer_token(monkeypatch) -> None:
    unconfigured = _client(monkeypatch, token_configured=False).get(
        "/api/external/chat-records?external_userid=wx_ext_001&start_time=1780358760&chat_scene=private"
    )
    assert unconfigured.status_code == 503
    assert unconfigured.json()["error_code"] == "internal_token_not_configured"

    client = _client(monkeypatch)
    missing = client.get("/api/external/chat-records?external_userid=wx_ext_001&start_time=1780358760&chat_scene=private")
    assert missing.status_code == 401
    assert missing.json()["error_code"] == "missing_internal_token"

    invalid = client.get(
        "/api/external/chat-records?external_userid=wx_ext_001&start_time=1780358760&chat_scene=private",
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert invalid.status_code == 401
    assert invalid.json()["error_code"] == "invalid_internal_token"


def test_external_chat_records_resolves_by_mobile_and_defaults_private_peer(monkeypatch) -> None:
    response = _client(monkeypatch).get(
        "/api/external/chat-records?mobile=13800138000&start_time=1780358760&chat_scene=private",
        headers=_headers(),
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["source_status"] == "external_chat_records"
    assert payload["route_owner"] == "ai_crm_next"
    assert payload["fallback_used"] is False
    assert payload["external_userid"] == "wx_ext_001"
    assert payload["matched_by"] == "mobile"
    assert payload["limit"] == 20
    assert payload["has_more"] is False
    assert payload["filters"]["chat_scene"] == "private"
    assert payload["filters"]["with_userid"] == "HuangYouCan"
    assert [item["msgid"] for item in payload["items"]] == ["msg-ext-private-001", "msg-ext-private-002"]
    assert payload["items"][0]["chat_scene"] == "private"
    assert payload["items"][0]["content"]


def test_external_chat_records_resolves_by_unionid_and_supports_group_scene(monkeypatch) -> None:
    response = _client(monkeypatch).get(
        "/api/external/chat-records?unionid=unionid_001&start_time=1780358760&chat_scene=group",
        headers=_headers(),
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["external_userid"] == "wx_ext_001"
    assert payload["matched_by"] == "unionid"
    assert payload["filters"]["chat_scene"] == "group"
    assert payload["filters"]["with_userid"] == ""
    assert [item["msgid"] for item in payload["items"]] == ["msg-ext-group-001"]
    assert payload["items"][0]["chat_id"] == "wr_hxc_group_001"
    assert payload["items"][0]["group_name"] == "黄小璨体验群"


def test_external_chat_records_cursor_paginates_fixed_twenty_rows(monkeypatch) -> None:
    client = _client(monkeypatch)
    first = client.get(
        "/api/external/chat-records?external_userid=wm_ext_001&start_time=1773567000&chat_scene=private&with_userid=sales_01&cursor=",
        headers=_headers(),
    ).json()

    assert first["items"]
    assert first["limit"] == 20
    assert first["has_more"] is False
    assert first["next_cursor"] == ""
    assert "offset" not in first


def test_external_chat_records_rejects_bad_inputs(monkeypatch) -> None:
    client = _client(monkeypatch)
    missing_identity = client.get(
        "/api/external/chat-records?start_time=1780358760&chat_scene=private",
        headers=_headers(),
    )
    assert missing_identity.status_code == 400
    assert missing_identity.json()["error_code"] == "invalid_request"

    milliseconds = client.get(
        "/api/external/chat-records?external_userid=wx_ext_001&start_time=1780358760000&chat_scene=private",
        headers=_headers(),
    )
    assert milliseconds.status_code == 400
    assert milliseconds.json()["error_code"] == "invalid_request"

    bad_scene = client.get(
        "/api/external/chat-records?external_userid=wx_ext_001&start_time=1780358760&chat_scene=dm",
        headers=_headers(),
    )
    assert bad_scene.status_code == 400
    assert bad_scene.json()["error_code"] == "invalid_request"
