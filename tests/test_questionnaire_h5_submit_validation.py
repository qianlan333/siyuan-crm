from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aicrm_next.main import create_app
from aicrm_next.questionnaire import external_push
from aicrm_next.questionnaire.h5_write import (
    get_questionnaire_h5_side_effect_plans,
    reset_questionnaire_h5_write_fixture_state,
)
from aicrm_next.questionnaire.repo import build_questionnaire_repository, reset_questionnaire_fixture_state


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    reset_questionnaire_fixture_state()
    reset_questionnaire_h5_write_fixture_state()
    return TestClient(create_app())


def _submission_count() -> int:
    rows = build_questionnaire_repository().list_submissions(1, limit=100, offset=0)
    assert rows is not None
    return rows[1]


def _assert_invalid_submission_response(response) -> None:
    assert response.status_code == 400
    assert response.headers.get("X-AICRM-Compatibility-Facade") is None
    body = response.json()
    assert body["ok"] is False
    assert body["route_owner"] == "ai_crm_next"
    assert body["fallback_used"] is False
    assert body["real_external_call_executed"] is False
    assert body["error_code"] == "invalid_questionnaire_submission"
    assert body["source_status"] == "input_error"
    assert body["write_model_status"] == "input_error"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"identity": {"external_userid": "wx_validation_001"}},
        {"answers": {}},
        {"answers": []},
        {"answer_items": []},
        {"responses": []},
    ],
)
def test_h5_submit_rejects_empty_or_missing_answers_without_writing(client: TestClient, payload: dict) -> None:
    before = _submission_count()

    response = client.post("/api/h5/questionnaires/hxc-activation-v1/submit", json=payload)

    _assert_invalid_submission_response(response)
    assert _submission_count() == before
    assert get_questionnaire_h5_side_effect_plans() == []


@pytest.mark.parametrize(
    "payload",
    [
        {"answer_items": [{"question_id": "q_activation"}]},
        {"answer_items": [{"value": "activated"}]},
        {"responses": ["activated"]},
    ],
)
def test_h5_submit_rejects_malformed_answer_items_without_writing(client: TestClient, payload: dict) -> None:
    before = _submission_count()

    response = client.post("/api/h5/questionnaires/hxc-activation-v1/submit", json=payload)

    _assert_invalid_submission_response(response)
    assert _submission_count() == before
    assert get_questionnaire_h5_side_effect_plans() == []


def test_h5_submit_validation_failure_does_not_trigger_external_push(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("external push must not run for invalid questionnaire submissions")

    monkeypatch.setattr(external_push.requests, "post", fail_if_called)
    before = _submission_count()

    response = client.post("/api/h5/questionnaires/hxc-activation-v1/submit", json={})

    _assert_invalid_submission_response(response)
    assert _submission_count() == before
    assert get_questionnaire_h5_side_effect_plans() == []


def test_h5_submit_accepts_legal_minimal_answers_and_writes_submission(client: TestClient) -> None:
    before = _submission_count()

    response = client.post(
        "/api/h5/questionnaires/hxc-activation-v1/submit",
        json={"answers": {"q_activation": "activated"}},
    )

    assert response.status_code == 200
    assert response.headers.get("X-AICRM-Compatibility-Facade") is None
    body = response.json()
    assert body["ok"] is True
    assert body["route_owner"] == "ai_crm_next"
    assert body["fallback_used"] is False
    assert body["real_external_call_executed"] is False
    assert body["submission_id"]
    assert _submission_count() == before + 1
