from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.main import create_app


def _client() -> TestClient:
    return TestClient(create_app())


def _assert_next_read_payload(payload: dict) -> None:
    assert payload["ok"] is True
    assert payload["route_owner"] == "ai_crm_next"
    assert payload["fallback_used"] is False
    assert payload["source_status"] == "local_contract_probe"
    assert payload["read_model_status"] == "fixture"
    assert payload["degraded"] is False
    assert payload["page_error"] == ""
    assert "compatibility_facade" not in payload


def test_questionnaire_admin_list_uses_next_read_model() -> None:
    response = _client().get("/api/admin/questionnaires")

    assert response.status_code == 200
    payload = response.json()
    _assert_next_read_payload(payload)
    assert payload["total"] >= 1
    assert payload["items"][0]["id"] == 1
    assert payload["items"][0]["status"] == "published"
    assert payload["items"][0]["version"] == 1


def test_questionnaire_admin_detail_and_editor_read_use_next_read_model() -> None:
    response = _client().get("/api/admin/questionnaires/1")

    assert response.status_code == 200
    payload = response.json()
    _assert_next_read_payload(payload)
    assert payload["questionnaire"]["id"] == 1
    assert payload["questionnaire"]["questions"]
    assert payload["questions"] == payload["questionnaire"]["questions"]
    assert payload["questionnaire"]["submissions_summary"]


def test_questionnaire_admin_questions_results_and_submissions_use_next_read_model() -> None:
    client = _client()

    questions = client.get("/api/admin/questionnaires/1/questions")
    results = client.get("/api/admin/questionnaires/1/results")
    submissions = client.get("/api/admin/questionnaires/1/submissions?limit=10")

    for response in [questions, results, submissions]:
        assert response.status_code == 200
        _assert_next_read_payload(response.json())

    assert questions.json()["questions"][0]["options"]
    assert results.json()["results"]["submission_count"] >= 1
    assert submissions.json()["submissions"][0]["questionnaire_id"] == 1
