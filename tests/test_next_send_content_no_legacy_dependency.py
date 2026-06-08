from __future__ import annotations

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
LEGACY_TOKEN = "wecom_" + "ability_service"


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_send_content_package_does_not_import_legacy_service() -> None:
    for path in (ROOT / "aicrm_next" / "send_content").glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert LEGACY_TOKEN not in source


def test_hxc_dashboard_broadcast_does_not_import_legacy_service() -> None:
    for path in (ROOT / "aicrm_next" / "hxc_dashboard").glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert LEGACY_TOKEN not in source


def test_automation_send_content_logic_does_not_import_legacy_service() -> None:
    for path in [
        "aicrm_next/automation_engine/api.py",
        "aicrm_next/automation_engine/application.py",
        "aicrm_next/automation_engine/dto.py",
        "aicrm_next/automation_engine/repo.py",
        "aicrm_next/automation_engine/postgres_repo.py",
    ]:
        assert LEGACY_TOKEN not in _read(path)


def test_new_routes_are_not_registered_through_production_compat() -> None:
    assert not (ROOT / "aicrm_next/production_compat/api.py").exists()


def test_new_tests_do_not_start_old_flask_app() -> None:
    forbidden = [
        LEGACY_TOKEN,
        "Flask" + "Client",
        "create_" + "flask_app",
        "wecom_app." + "test_client",
    ]
    for name in [
        "test_next_send_content_package_contract.py",
        "test_next_material_picker_api.py",
        "test_next_automation_task_send_content.py",
        "test_next_send_content_no_legacy_dependency.py",
        "test_next_hxc_broadcast_api.py",
        "test_next_hxc_broadcast_repo.py",
        "test_next_hxc_broadcast_frontend_contract.py",
    ]:
        source = (ROOT / "tests" / name).read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in source


def test_new_route_owner_is_ai_crm_next_and_prod_without_db_is_degraded(monkeypatch) -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from aicrm_next.main import create_app

    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "0")
    monkeypatch.setenv("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", "1")

    client = TestClient(create_app(), raise_server_exceptions=False)
    response = client.get("/api/admin/material-picker/items?type=image")

    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert response.status_code == 503
    body = response.json()
    assert body["ok"] is False
    assert body["degraded"] is True
    assert body["source_status"] == "production_unavailable"
