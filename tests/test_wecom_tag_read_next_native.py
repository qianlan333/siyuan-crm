from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.main import create_app


def _client(monkeypatch) -> TestClient:
    monkeypatch.setenv("SECRET_KEY", "wecom-tag-read-next-native")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    return TestClient(create_app(), raise_server_exceptions=False)


def test_get_wecom_tags_uses_next_read_model_shape(monkeypatch) -> None:
    response = _client(monkeypatch).get("/api/admin/wecom/tags")
    payload = response.json()

    assert response.status_code == 200
    assert "X-AICRM-Compatibility-Facade" not in response.headers
    assert payload["ok"] is True
    assert payload["route_owner"] == "ai_crm_next"
    assert payload["fallback_used"] is False
    assert payload["real_external_call_executed"] is False
    assert payload["sync_executed"] is False
    assert payload["source_status"] == "local_contract_probe"
    assert payload["read_model_status"] == "fixture"
    assert payload["count"] == len(payload["tags"]) == len(payload["items"])
    assert {
        "tag_group_id",
        "group_name",
        "tag_id",
        "tag_name",
        "order",
        "status",
        "source",
        "updated_at",
    }.issubset(payload["tags"][0])


def test_get_wecom_tag_groups_uses_same_next_catalog(monkeypatch) -> None:
    response = _client(monkeypatch).get("/api/admin/wecom/tag-groups")
    payload = response.json()

    assert response.status_code == 200
    assert payload["route_owner"] == "ai_crm_next"
    assert payload["fallback_used"] is False
    assert payload["real_external_call_executed"] is False
    assert payload["items"] == payload["groups"]
    assert payload["count"] == len(payload["groups"])
    assert payload["groups"][0]["tags"]
    assert payload["tags"][0]["group_id"] == payload["groups"][0]["group_id"]


def test_get_wecom_tag_and_group_detail_filter_catalog(monkeypatch) -> None:
    client = _client(monkeypatch)

    tag_response = client.get("/api/admin/wecom/tags/tag_fixture_active")
    group_response = client.get("/api/admin/wecom/tag-groups/group_fixture_lifecycle")

    assert tag_response.status_code == 200
    assert tag_response.json()["tags"][0]["tag_id"] == "tag_fixture_active"
    assert tag_response.json()["count"] == 1
    assert group_response.status_code == 200
    assert group_response.json()["groups"][0]["group_id"] == "group_fixture_lifecycle"
    assert group_response.json()["tags"]
