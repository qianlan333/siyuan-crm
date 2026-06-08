from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from aicrm_next.main import create_app
from scripts.check_no_new_legacy import _decorator_route_paths
from tools import check_production_route_resolution as checker


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_COMPAT = ROOT / "aicrm_next/production_compat/api.py"


def test_cloud_orchestrator_media_upload_resolves_to_next_before_production_compat(monkeypatch):
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    result = checker.run_check()
    sample = next(
        item
        for item in result["resolution_samples"]
        if item["method"] == "POST" and item["path"] == "/api/admin/cloud-orchestrator/media/upload"
    )

    assert sample["route_owner"] == "next"
    assert sample["endpoint_module"] == "aicrm_next.cloud_orchestrator.api"


def test_cloud_orchestrator_media_upload_does_not_call_legacy_forward(monkeypatch):

    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")

    response = TestClient(create_app(), raise_server_exceptions=False).options(
        "/api/admin/cloud-orchestrator/media/upload"
    )

    assert response.status_code == 200
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert response.headers["X-AICRM-Fallback-Used"] == "false"
    assert response.json()["source_status"] == "next_cloud_orchestrator_media_upload"
    assert response.json()["route_owner"] == "ai_crm_next"
    assert response.json()["fallback_used"] is False
    assert "X-AICRM-Compatibility-Facade" not in response.headers


def test_cloud_orchestrator_media_upload_is_removed_from_production_compat():
    assert "/api/admin/cloud-orchestrator/media/upload" not in _decorator_route_paths(PRODUCTION_COMPAT)
