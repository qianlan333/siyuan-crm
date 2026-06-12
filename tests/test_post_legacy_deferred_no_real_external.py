from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from aicrm_next.main import create_app
from tests.post_legacy_baseline import assert_no_legacy_flags, baseline_env

ROOT = Path(__file__).resolve().parents[1]


def test_pr11_handoff_modules_have_no_direct_external_clients() -> None:
    source = "\n".join(
        [
            (ROOT / "aicrm_next/automation_engine/channels_api.py").read_text(encoding="utf-8"),
            (ROOT / "aicrm_next/class_user_management/api.py").read_text(encoding="utf-8"),
        ]
    )

    for marker in ("httpx.", "urlopen(", "create_contact_way", "dispatch_wecom_task", "external_storage"):
        assert marker not in source


def test_wecom_customer_acquisition_defaults_never_call_wecom(monkeypatch) -> None:
    baseline_env(monkeypatch)
    client = TestClient(create_app())

    create = client.post("/api/admin/wecom-customer-acquisition-links", json={"name": "No Real External"})
    body = create.json()
    assert create.status_code == 200
    assert_no_legacy_flags(body)
    assert body["adapter_mode"] == "real_blocked"
    assert body["wecom_api_called"] is False
    assert body["real_external_call_executed"] is False
    assert body["side_effect_plan"]["status"] == "blocked"

    sync = client.post(f"/api/admin/wecom-customer-acquisition-links/{body['link']['id']}/sync")
    sync_body = sync.json()
    assert sync.status_code == 200
    assert_no_legacy_flags(sync_body)
    assert sync_body["wecom_api_called"] is False
    assert sync_body["sync_executed"] is False
    assert sync_body["side_effect_plan"]["status"] == "blocked"


def test_class_user_export_defaults_never_write_external_storage(monkeypatch) -> None:
    baseline_env(monkeypatch)
    client = TestClient(create_app())
    response = client.get("/api/admin/class-user-management/export")

    assert response.status_code == 200
    assert response.headers["X-AICRM-External-Storage-Executed"] == "false"
    assert "local_only" in response.text
