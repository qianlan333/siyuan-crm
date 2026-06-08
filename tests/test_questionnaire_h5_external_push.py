from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aicrm_next.main import create_app
from aicrm_next.questionnaire import external_push
from aicrm_next.questionnaire.repo import build_questionnaire_repository


class _Response:
    status_code = 200
    text = '{"ok":true,"message":"accepted"}'


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    return TestClient(create_app())


def test_h5_submit_executes_configured_questionnaire_external_push(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
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

    captured: dict[str, object] = {}

    def fake_post(url: str, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return _Response()

    monkeypatch.setattr(external_push.requests, "post", fake_post)

    response = client.post(
        "/api/h5/questionnaires/hxc-activation-v1/submit",
        json={"answers": {"phone": "13770938680"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["real_external_call_executed"] is True
    assert body["external_push"]["status"] == "success"
    assert body["side_effect_plan"]["adapter_mode"] == "real_enabled"
    assert body["side_effect_plan"]["requires_approval"] is False
    assert "external_push.executed" in body["side_effect_plan"]["payload"]["planned_effects"]

    assert captured["url"] == "https://hooks.example.com/questionnaire"
    request_json = captured["kwargs"]["json"]  # type: ignore[index]
    assert request_json["phone_number"] == "13770938680"
    assert request_json["type"] == "subscription"
    assert request_json["expires_at_ts"] == 1810310400
    assert request_json["remark"] == "499会员黄小璨激活专用"

    logs = repo._external_push_logs  # type: ignore[attr-defined]
    assert len(logs) == 1
    assert logs[0]["status"] == "success"
    assert logs[0]["response_status_code"] == 200
    assert logs[0]["request_payload"]["phone_number"] == "13770938680"
