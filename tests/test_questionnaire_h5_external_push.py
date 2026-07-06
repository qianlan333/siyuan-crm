from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aicrm_next.main import create_app
from aicrm_next.platform_foundation.external_effects import ExternalEffectService, WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH
from aicrm_next.platform_foundation.external_effects.repo import reset_external_effect_fixture_state
from aicrm_next.questionnaire.h5_write import reset_questionnaire_h5_write_fixture_state
from aicrm_next.questionnaire.repo import build_questionnaire_repository


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    reset_questionnaire_h5_write_fixture_state()
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    return TestClient(create_app())


def test_h5_submit_executes_configured_questionnaire_external_push(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    reset_external_effect_fixture_state()
    repo = build_questionnaire_repository()
    questionnaire = repo._questionnaires[0]  # type: ignore[attr-defined]
    questionnaire["external_push_config"] = {
        "enabled": True,
        "webhook_url": "https://hooks.example.com/questionnaire",
        "type": "subscription",
        "expires_at_ts": 1810310400,
        "remark": "499会员黄小璨激活专用",
    }
    questionnaire["questions"] = [
        {
            "id": "phone",
            "type": "mobile",
            "title": "请填写你要激活的手机号",
            "required": True,
            "options": [],
        }
    ]

    response = client.post(
        "/api/h5/questionnaires/hxc-activation-v1/submit",
        json={"answers": {"phone": "13770938680"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["real_external_call_executed"] is False
    assert body["external_push"]["status"] == "queued"
    assert body["external_push"]["legacy_outbound_disabled"] is True
    assert body["tag_apply"]["status"] == "failed"
    assert body["tag_apply"]["error_code"] == "tag_ids_missing"
    assert body["tag_apply"]["wecom_api_called"] is False
    assert body["side_effect_plan"]["adapter_mode"] == "real_mark_tag"
    assert body["side_effect_plan"]["requires_approval"] is False
    assert "external_push.queued" in body["side_effect_plan"]["payload"]["planned_effects"]
    assert body["external_effect_job_status"] == "queued"

    jobs, total = ExternalEffectService().list_jobs({"effect_type": WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH})
    assert total == 1
    job = jobs[0]
    assert job.status == "queued"
    assert job.execution_mode == "execute"
    assert job.payload_json["webhook_url"] == "https://hooks.example.com/questionnaire"
    assert isinstance(job.payload_json["signature"], dict)
    request_json = job.payload_json["body"]
    assert request_json["phone_number"] == "13770938680"
    assert request_json["type"] == "subscription"
    assert request_json["expires_at_ts"] == 1810310400
    assert request_json["remark"] == "499会员黄小璨激活专用"

    assert repo._external_push_logs == []  # type: ignore[attr-defined]
