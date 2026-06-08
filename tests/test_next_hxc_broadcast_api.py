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


def _payload(**overrides):
    payload = {
        "source_type": "hxc_dashboard_broadcast",
        "source_id": "pytest-hxc",
        "idempotency_key": "pytest-hxc-key",
        "sender_userid": "QianLan",
        "audience_filter": {"source": "pytest"},
        "selected_customer_ids": ["ext_hxc_001", "ext_hxc_002"],
        "content_package": {"content_text": "  HXC 群发  "},
        "dry_run": False,
    }
    payload.update(overrides)
    return payload


def test_empty_content_package_returns_400_json(client) -> None:
    response = client.post(
        "/api/admin/hxc-dashboard/broadcast-tasks",
        json=_payload(content_package={}),
    )

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    body = response.json()
    assert body["ok"] is False
    assert "内容包不能为空" in body["error"]


def test_valid_content_package_creates_next_native_task(client) -> None:
    response = client.post("/api/admin/hxc-dashboard/broadcast-tasks", json=_payload())

    assert response.status_code == 200
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    body = response.json()
    assert body["ok"] is True
    task = body["task"]
    assert task["status"] in {"created", "degraded", "production_unavailable"}
    assert task["dispatch_status"] == "pending_external_dispatch"
    assert task["audience_total"] == 2
    assert task["eligible_count"] == 1
    assert task["skipped_count"] == 1
    assert task["skipped_by_reason"]["do_not_disturb"] == 1
    assert task["content_package"]["content_text"] == "HXC 群发"


def test_invalid_material_count_returns_400_json(client) -> None:
    response = client.post(
        "/api/admin/hxc-dashboard/broadcast-tasks",
        json=_payload(content_package={"image_library_ids": [1, 2, 3, 4]}),
    )

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["ok"] is False
    assert "最多允许 3 个" in response.json()["error"]


def test_idempotency_key_does_not_create_duplicate_tasks(client) -> None:
    payload = _payload(idempotency_key="same-key")

    first = client.post("/api/admin/hxc-dashboard/broadcast-tasks", json=payload)
    second = client.post("/api/admin/hxc-dashboard/broadcast-tasks", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["task"]["task_id"]
    assert second.json()["task"]["task_id"] == first.json()["task"]["task_id"]
    assert second.json()["duplicate"] is True


def test_dry_run_previews_without_creating_idempotent_task(client) -> None:
    dry_run = client.post(
        "/api/admin/hxc-dashboard/broadcast-tasks",
        json=_payload(idempotency_key="dry-run-key", dry_run=True),
    )
    create = client.post(
        "/api/admin/hxc-dashboard/broadcast-tasks",
        json=_payload(idempotency_key="dry-run-key", dry_run=False),
    )

    assert dry_run.status_code == 200
    assert dry_run.json()["task"]["dry_run"] is True
    assert dry_run.json()["task"]["task_id"] == ""
    assert create.status_code == 200
    assert create.json()["duplicate"] is False
    assert create.json()["task"]["task_id"]


def test_route_is_registered_before_legacy_hxc_wildcard(monkeypatch) -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from aicrm_next.main import create_app

    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://invalid.invalid/aicrm")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.delenv("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.post("/api/admin/hxc-dashboard/broadcast-tasks", json=_payload(idempotency_key="prod-unavailable"))

    assert response.status_code in {200, 400}
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert response.headers["content-type"].startswith("application/json")
    assert response.json().get("task", {}).get("status") == "production_unavailable" or response.json().get("ok") is False


def test_production_without_database_returns_production_unavailable_json(monkeypatch) -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from aicrm_next.main import create_app

    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "0")
    monkeypatch.setenv("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", "1")
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.post("/api/admin/hxc-dashboard/broadcast-tasks", json=_payload(idempotency_key="no-db"))

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()
    assert body["ok"] is True
    assert body["task"]["status"] == "production_unavailable"
