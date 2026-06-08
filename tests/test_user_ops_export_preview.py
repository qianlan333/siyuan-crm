from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.main import create_app


def test_user_ops_export_preview_returns_masked_sample_only() -> None:
    response = TestClient(create_app()).post(
        "/api/admin/user-ops/export/preview",
        json={"filters": {"tag": "黄小璨"}, "fields": ["external_userid", "customer_name", "mobile"]},
        headers={"Idempotency-Key": "export-preview-1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["route_owner"] == "ai_crm_next"
    assert body["fallback_used"] is False
    assert body["source_status"] == "next_command"
    assert body["preview_status"] == "controlled_preview"
    assert body["real_external_call_executed"] is False
    assert body["estimated_count"] == 3
    assert body["requires_approval"] is True
    assert body["fields"] == ["external_userid", "customer_name", "mobile"]
    assert body["side_effect_plan"]["adapter_name"] == "storage"
    assert body["side_effect_plan"]["adapter_mode"] == "real_blocked"
    rendered = str(body["masked_sample"])
    assert "13800138000" not in rendered
    assert "wx_ext_001" not in rendered
    assert "张小蓝" not in rendered


def test_user_ops_export_preview_accepts_empty_fields_as_controlled_default_without_storage_file() -> None:
    response = TestClient(create_app()).post(
        "/api/admin/user-ops/export/preview",
        json={"fields": []},
        headers={"Idempotency-Key": "export-preview-empty"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["route_owner"] == "ai_crm_next"
    assert body["fallback_used"] is False
    assert body["source_status"] == "next_command"
    assert body["preview_status"] == "controlled_default_preview"
    assert body["real_external_call_executed"] is False
    assert body["requires_approval"] is True
    assert body["fields"]
    assert body["side_effect_plan"]["adapter_name"] == "storage"
    assert body["side_effect_plan"]["adapter_mode"] == "real_blocked"
    assert body["side_effect_plan"]["real_external_call_executed"] is False
    assert "filename" not in body
    assert "file_path" not in body
