from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aicrm_next.main import create_app
import aicrm_next.questionnaire.api as questionnaire_api
from aicrm_next.questionnaire.admin_write import (
    get_questionnaire_admin_write_audit_events,
    reset_questionnaire_admin_write_fixture_state,
)
from aicrm_next.questionnaire.h5_write import reset_questionnaire_h5_write_fixture_state
from aicrm_next.questionnaire.repo import reset_questionnaire_fixture_state


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    reset_questionnaire_fixture_state()
    reset_questionnaire_admin_write_fixture_state()
    reset_questionnaire_h5_write_fixture_state()
    return TestClient(create_app())


def _payload(title: str = "测试问卷") -> dict:
    return {
        "title": title,
        "description": "测试描述",
        "questions": [
            {
                "id": "q1",
                "type": "single_choice",
                "title": "是否激活",
                "required": True,
                "options": [{"id": "yes", "label": "是", "value": "yes"}],
            }
        ],
    }


def _assert_command(body: dict, command_name: str, status: str) -> None:
    assert body["ok"] is True
    assert body["command_name"] == command_name
    assert body["source_status"] == "next_command"
    assert body["write_model_status"] == status
    assert body["route_owner"] == "ai_crm_next"
    assert body["fallback_used"] is False
    assert body["real_external_call_executed"] is False
    assert body["audit_recorded"] is True
    assert body["command_id"]
    assert body["questionnaire_id"]


def test_questionnaire_admin_write_routes_execute_next_commandbus(client: TestClient) -> None:
    create = client.post("/api/admin/questionnaires", json=_payload(), headers={"Idempotency-Key": "qw-create"})
    assert create.status_code == 200
    _assert_command(create.json(), "questionnaire.admin.create", "created")
    questionnaire_id = create.json()["questionnaire_id"]

    update = client.put(
        f"/api/admin/questionnaires/{questionnaire_id}",
        json=_payload("测试问卷更新"),
        headers={"Idempotency-Key": "qw-update"},
    )
    assert update.status_code == 200
    _assert_command(update.json(), "questionnaire.admin.update", "updated")
    assert update.json()["questionnaire"]["title"] == "测试问卷更新"

    duplicate = client.post(
        f"/api/admin/questionnaires/{questionnaire_id}/duplicate",
        json={"title": "测试问卷复制"},
        headers={"Idempotency-Key": "qw-duplicate"},
    )
    assert duplicate.status_code == 200
    _assert_command(duplicate.json(), "questionnaire.admin.duplicate", "duplicated")
    assert duplicate.json()["source_questionnaire_id"] == questionnaire_id
    assert duplicate.json()["questionnaire"]["is_disabled"] is True

    publish = client.post(
        f"/api/admin/questionnaires/{questionnaire_id}/publish",
        json={},
        headers={"Idempotency-Key": "qw-publish"},
    )
    assert publish.status_code == 200
    _assert_command(publish.json(), "questionnaire.admin.publish", "published")
    assert publish.json()["side_effect_plan"]["adapter_mode"] == "real_blocked"

    disable = client.post(
        f"/api/admin/questionnaires/{questionnaire_id}/disable",
        json={},
        headers={"Idempotency-Key": "qw-disable"},
    )
    assert disable.status_code == 200
    _assert_command(disable.json(), "questionnaire.admin.disable", "disabled")
    assert disable.json()["questionnaire"]["is_disabled"] is True

    enable = client.post(
        f"/api/admin/questionnaires/{questionnaire_id}/enable",
        json={},
        headers={"Idempotency-Key": "qw-enable"},
    )
    assert enable.status_code == 200
    _assert_command(enable.json(), "questionnaire.admin.enable", "enabled")
    assert enable.json()["questionnaire"]["is_disabled"] is False

    delete = client.delete(
        f"/api/admin/questionnaires/{questionnaire_id}",
        headers={"Idempotency-Key": "qw-delete"},
    )
    assert delete.status_code == 200
    _assert_command(delete.json(), "questionnaire.admin.delete", "soft_deleted")
    assert delete.json()["delete_mode"] == "soft_delete_disable"

    audit_events = get_questionnaire_admin_write_audit_events()
    command_ids = {event["command_id"] for event in audit_events}
    for response in [create, update, duplicate, publish, disable, enable, delete]:
        assert response.json()["command_id"] in command_ids


def test_questionnaire_admin_write_routes_return_controlled_errors(client: TestClient) -> None:
    missing_title = client.post("/api/admin/questionnaires", json={"description": "no title"})
    assert missing_title.status_code == 400
    assert missing_title.json()["source_status"] == "input_error"
    assert missing_title.json()["fallback_used"] is False

    missing_questionnaire = client.post("/api/admin/questionnaires/9999/publish", json={})
    assert missing_questionnaire.status_code == 404
    assert missing_questionnaire.json()["source_status"] == "not_found"


def test_questionnaire_admin_write_production_uses_next_commandbus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(questionnaire_api, "production_data_ready", lambda: True)
    reset_questionnaire_fixture_state()
    reset_questionnaire_admin_write_fixture_state()

    client = TestClient(create_app())
    create = client.post("/api/admin/questionnaires", json=_payload("生产创建"))
    assert create.status_code == 200
    questionnaire_id = create.json()["questionnaire_id"]

    responses = [
        create,
        client.put(f"/api/admin/questionnaires/{questionnaire_id}", json=_payload("生产更新")),
        client.post(f"/api/admin/questionnaires/{questionnaire_id}/publish", json={}),
        client.post(f"/api/admin/questionnaires/{questionnaire_id}/disable", json={}),
        client.post(f"/api/admin/questionnaires/{questionnaire_id}/enable", json={}),
        client.delete(f"/api/admin/questionnaires/{questionnaire_id}"),
    ]
    for response in responses:
        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True
        assert body["source_status"] == "next_command"
        assert body["fallback_used"] is False
        assert "x-aicrm-compatibility-facade" not in response.headers


def test_questionnaire_admin_lifecycle_production_mode_acceptance(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(questionnaire_api, "production_data_ready", lambda: True)
    payload = {
        **_payload("生产闭环问卷"),
        "slug": "prod-lifecycle-survey",
        "assessment_enabled": True,
        "assessment_config": {"levels": [{"name": "高意向", "min_score": 1}]},
        "score_rules": [{"min_score": 1, "max_score": 10, "tag_codes": ["tag_prod_lifecycle"]}],
        "external_push_enabled": True,
        "external_push_url": "https://example.invalid/questionnaire",
        "external_push_type": "trial",
        "external_push_day": 7,
        "external_push_remark": "生产闭环验收",
    }

    create = client.post("/api/admin/questionnaires", json=payload)
    assert create.status_code == 200
    assert create.json()["source_status"] == "next_command"
    assert create.json()["fallback_used"] is False
    assert "x-aicrm-compatibility-facade" not in create.headers
    questionnaire_id = create.json()["questionnaire_id"]

    update_payload = {**payload, "title": "生产闭环问卷更新"}
    update = client.put(f"/api/admin/questionnaires/{questionnaire_id}", json=update_payload)
    assert update.status_code == 200

    refreshed = client.get(f"/api/admin/questionnaires/{questionnaire_id}")
    assert refreshed.status_code == 200
    refreshed_body = refreshed.json()
    assert refreshed_body["questionnaire"]["title"] == "生产闭环问卷更新"
    assert refreshed_body["questionnaire"]["assessment_config"]["levels"][0]["name"] == "高意向"
    assert refreshed_body["questionnaire"]["external_push_type"] == "trial"
    assert refreshed_body["questions"][0]["options"][0]["tag_codes"] == []

    publish = client.post(f"/api/admin/questionnaires/{questionnaire_id}/publish", json={})
    assert publish.status_code == 200
    h5_page = client.get("/s/prod-lifecycle-survey")
    assert h5_page.status_code == 200
    assert "生产闭环问卷更新" in h5_page.text

    submit = client.post(
        "/api/h5/questionnaires/prod-lifecycle-survey/submit",
        json={
            "answers": {"q1": "yes"},
            "identity": {"external_userid": "wm_prod_lifecycle_001", "mobile": "13800138000"},
        },
    )
    assert submit.status_code == 200

    export_preview = client.post(
        f"/api/admin/questionnaires/{questionnaire_id}/export/preview",
        json={"fields": ["submission_id", "external_userid", "mobile", "answers"]},
    )
    assert export_preview.status_code == 200
    export_body = export_preview.json()
    assert export_body["source_status"] == "next_command"
    assert export_body["fallback_used"] is False
    assert export_body["export_preview"]["file_created"] is False
    assert export_body["export_preview"]["masked_sample"][0]["external_userid"] == "masked"
    assert export_body["export_preview"]["masked_sample"][0]["mobile"] == "masked"
    assert "x-aicrm-compatibility-facade" not in export_preview.headers

    disable = client.post(f"/api/admin/questionnaires/{questionnaire_id}/disable", json={})
    assert disable.status_code == 200
    disabled_h5 = client.get("/api/h5/questionnaires/prod-lifecycle-survey")
    assert disabled_h5.status_code == 404

    delete = client.delete(f"/api/admin/questionnaires/{questionnaire_id}")
    assert delete.status_code == 200
    assert delete.json()["delete_mode"] == "soft_delete_disable"
    list_response = client.get("/api/admin/questionnaires")
    assert list_response.status_code == 200
    list_item = next(item for item in list_response.json()["questionnaires"] if item["id"] == questionnaire_id)
    assert list_item["is_disabled"] is True
