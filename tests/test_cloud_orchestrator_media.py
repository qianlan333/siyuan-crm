from __future__ import annotations

import base64

from fastapi.testclient import TestClient

from aicrm_next.main import create_app


PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def test_cloud_orchestrator_media_upload_fake_mode_has_no_real_external_call(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_NEXT_CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_MODE", "fake")
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.post(
        "/api/admin/cloud-orchestrator/media/upload",
        files={"image": ("probe.png", PNG_BYTES, "image/png")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["route_owner"] == "ai_crm_next"
    assert body["fallback_used"] is False
    assert body["adapter_mode"] == "fake"
    assert body["real_external_call_executed"] is False
    assert body["wecom_media_upload_executed"] is False
