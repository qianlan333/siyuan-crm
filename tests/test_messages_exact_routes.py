from __future__ import annotations

from fastapi.testclient import TestClient


def test_exact_message_list_and_search_routes_return_stable_next_payload(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_NEXT_ENV", "development")
    from aicrm_next.main import create_app

    client = TestClient(create_app())

    list_response = client.get("/api/messages/wm_ext_001?limit=2")
    search_response = client.get("/api/messages/search?external_userid=wm_ext_001&keyword=方案")
    filtered_response = client.get("/api/messages/wm_ext_001?chat_type=group")

    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert list_payload["source_status"] == "message_archive_fixture"
    assert list_payload["fallback_used"] is False
    assert list_payload["messages"][0]["msgid"] == "msg-001"
    assert "receiver" not in list_payload["messages"][0]

    assert search_response.status_code == 200
    search_payload = search_response.json()
    assert search_payload["messages"][0]["msgid"] == "msg-002"
    assert search_payload["read_model_status"] == "fixture"

    assert filtered_response.status_code == 200
    assert filtered_response.json()["messages"][0]["chat_type"] == "group"


def test_message_read_routes_return_controlled_production_unavailable(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://messages:messages@127.0.0.1:1/aicrm_messages")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.delenv("AICRM_NEXT_ALLOW_FIXTURE_REPO_IN_PROD", raising=False)

    from aicrm_next.main import create_app

    client = TestClient(create_app())
    list_response = client.get("/api/messages/wm_ext_001")
    search_response = client.get("/api/messages/search?external_userid=wm_ext_001&keyword=方案")

    for response in [list_response, search_response]:
        assert response.status_code == 503
        payload = response.json()
        assert payload["source_status"] == "production_unavailable"
        assert payload["fallback_used"] is False
        assert "legacy_production_facade" not in str(payload)


def test_deprecated_messages_routes_are_explicit_and_do_not_500() -> None:
    from aicrm_next.main import create_app

    client = TestClient(create_app())

    for path in [
        "/api/messages/archive",
        "/api/messages/wm_ext_001/archive",
        "/api/messages/wm_ext_001/history",
    ]:
        response = client.get(path)
        assert response.status_code == 410
        payload = response.json()
        assert payload["error_code"] == "messages_route_deprecated"
        assert payload["source_status"] == "deprecated"
        assert payload["fallback_used"] is False


def test_recent_messages_route_remains_customer_read_model_exact(monkeypatch) -> None:
    from aicrm_next.main import create_app

    client = TestClient(create_app())
    response = client.get("/api/messages/wx_ext_001/recent?limit=1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_status"] == "local_contract_probe"
    assert payload["fallback_used"] is False

