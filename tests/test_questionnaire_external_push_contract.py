from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.main import create_app
from aicrm_next.questionnaire.external_push_logs import (
    get_questionnaire_external_push_retry_side_effect_plans,
    reset_questionnaire_external_push_retry_state,
)
from aicrm_next.questionnaire.repo import reset_questionnaire_fixture_state


def _client() -> TestClient:
    reset_questionnaire_fixture_state()
    reset_questionnaire_external_push_retry_state()
    return TestClient(create_app(), raise_server_exceptions=False)


def test_questionnaire_external_push_log_pages_are_next_owned():
    client = _client()

    all_logs = client.get("/admin/questionnaires/external-push-logs")
    scoped_logs = client.get("/admin/questionnaires/1/external-push-logs")

    for response in (all_logs, scoped_logs):
        assert response.status_code == 200
        assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
        assert "X-AICRM-Compatibility-Facade" not in response.headers
        assert "问卷外推记录" in response.text


def test_questionnaire_external_push_retry_is_planned_not_sent():
    client = _client()

    response = client.post("/admin/questionnaires/1/external-push-logs/retry-batch", data={"log_ids": "1"})

    assert response.status_code == 200
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert get_questionnaire_external_push_retry_side_effect_plans() == []
    assert "问卷外推记录" in response.text
