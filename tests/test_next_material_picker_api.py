from __future__ import annotations

import pytest


@pytest.fixture()
def client(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from aicrm_next.main import create_app

    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "0")
    monkeypatch.setenv("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", "1")
    return TestClient(create_app(), raise_server_exceptions=False)


def test_validate_returns_route_owner_and_normalized_package(client) -> None:
    response = client.post(
        "/api/admin/send-content/validate",
        json={
            "content_package": {
                "content_text": "  你好  ",
                "image_library_ids": [12, "12", 13],
                "miniprogram_library_ids": [34],
                "attachment_library_ids": [56],
            }
        },
    )

    assert response.status_code == 200
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert response.json() == {
        "ok": True,
        "content_package": {
            "content_text": "你好",
            "image_library_ids": [12, 13],
            "miniprogram_library_ids": [34],
            "attachment_library_ids": [56],
        },
    }


def test_validate_error_is_json_not_html(client) -> None:
    response = client.post(
        "/api/admin/send-content/validate",
        json={"content_package": {"image_library_ids": ["abc"]}},
    )

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    body = response.json()
    assert body["ok"] is False
    assert "正整数" in body["error"]


def test_preview_is_local_only_and_does_not_create_tasks(client, monkeypatch) -> None:
    import requests

    def _fail_external_call(*args, **kwargs):
        raise AssertionError("preview must not perform external HTTP calls")

    monkeypatch.setattr(requests, "post", _fail_external_call)
    before = client.get("/api/admin/automation-conversion/tasks").json()["total"]

    response = client.post(
        "/api/admin/send-content/preview",
        json={
            "content_package": {
                "content_text": "  预览  ",
                "image_library_ids": [12],
                "miniprogram_library_ids": [34],
                "attachment_library_ids": [56],
            }
        },
    )

    assert response.status_code == 200
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    body = response.json()
    assert body["ok"] is True
    assert body["preview"]["content_text"] == "预览"
    assert body["preview"]["material_summary"] == {
        "image_count": 1,
        "miniprogram_count": 1,
        "attachment_count": 1,
    }
    assert all("media_id" not in item for item in body["preview"]["materials"])
    after = client.get("/api/admin/automation-conversion/tasks").json()["total"]
    assert after == before


def test_material_picker_image_shape_excludes_base64(client) -> None:
    response = client.get("/api/admin/material-picker/items?type=image")

    assert response.status_code == 200
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    item = response.json()["items"][0]
    assert {"type", "library_id", "title", "thumbnail_url", "enabled", "metadata"} <= set(item)
    assert item["type"] == "image"
    assert "data_base64" not in item
    assert "data_base64" not in item["metadata"]


def test_material_picker_miniprogram_shape(client) -> None:
    response = client.get("/api/admin/material-picker/items?type=miniprogram")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["type"] == "miniprogram"
    assert item["metadata"]["appid"]
    assert item["metadata"]["pagepath"]


def test_material_picker_attachment_shape(client) -> None:
    response = client.get("/api/admin/material-picker/items?type=attachment")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["type"] == "attachment"
    assert {"file_name", "mime_type", "file_size"} <= set(item["metadata"])
    assert item["mime_type"] == "application/pdf"
    assert item["metadata"]["mime_type"] == "application/pdf"


def test_material_picker_unknown_type_returns_400_json(client) -> None:
    response = client.get("/api/admin/material-picker/items?type=unknown")

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert response.json()["ok"] is False
