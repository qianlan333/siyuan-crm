from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aicrm_next.main import create_app
from aicrm_next.questionnaire.external_push_logs import (
    get_questionnaire_external_push_retry_side_effect_plans,
    reset_questionnaire_external_push_retry_state,
)
from aicrm_next.questionnaire.repo import build_questionnaire_repository, reset_questionnaire_fixture_state


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    monkeypatch.delenv("AICRM_QUESTIONNAIRE_EXTERNAL_PUSH_RETRY_REAL_ENABLED", raising=False)
    reset_questionnaire_fixture_state()
    reset_questionnaire_external_push_retry_state()
    return TestClient(create_app())


def _seed_log(*, status: str = "failed", user_id: str = "user-failed", questionnaire_id: int = 1) -> dict:
    repo = build_questionnaire_repository()
    return repo.create_external_push_log(
        questionnaire_id=questionnaire_id,
        questionnaire_title_snapshot="黄小璨激活问卷",
        submission_record_id=1001,
        user_id=user_id,
        target_url="https://hooks.example.com/questionnaire",
        request_payload={"user_id": user_id, "questionnaire_title": "黄小璨激活问卷"},
        response_status_code=500 if status == "failed" else 200,
        response_body='{"error":"upstream"}' if status == "failed" else '{"ok":true}',
        status=status,
        failure_reason="HTTP 500" if status == "failed" else "",
    )


def test_next_external_push_log_pages_render_global_and_questionnaire_scoped(client: TestClient) -> None:
    _seed_log()

    global_response = client.get("/admin/questionnaires/external-push-logs?status=failed_current")
    scoped_response = client.get("/admin/questionnaires/1/external-push-logs?status=failed_current")

    for response in [global_response, scoped_response]:
        assert response.status_code == 200
        assert "X-AICRM-Compatibility-Facade" not in response.headers
        assert "外部推送记录" in response.text
        assert "黄小璨激活问卷" in response.text
        assert "HTTP 500" in response.text
        assert "补发" in response.text


def test_next_external_push_retry_defaults_to_side_effect_plan_and_is_idempotent(client: TestClient) -> None:
    source = _seed_log()
    repo = build_questionnaire_repository()

    first = client.post(
        f"/admin/questionnaires/external-push-logs/{source['id']}/retry",
        headers={"Accept": "application/json"},
    )
    second = client.post(
        f"/admin/questionnaires/external-push-logs/{source['id']}/retry",
        headers={"Accept": "application/json"},
    )

    assert first.status_code == 200
    first_body = first.json()
    assert first_body["source_status"] == "next_command"
    assert first_body["fallback_used"] is False
    assert first_body["adapter_mode"] == "real_blocked"
    assert first_body["real_external_call_executed"] is False
    assert first_body["log"]["status"] == "planned"
    assert first_body["side_effect_plan"]["effect_type"] == "questionnaire.external_push.retry"
    assert first_body["side_effect_plan"]["requires_approval"] is True

    assert second.status_code == 200
    assert second.json()["skipped"] is True
    assert len(repo._external_push_logs) == 2  # type: ignore[attr-defined]
    assert len(get_questionnaire_external_push_retry_side_effect_plans()) == 2


def test_next_external_push_batch_retry_only_processes_failed_selected_logs(client: TestClient) -> None:
    failed_one = _seed_log(user_id="failed-one")
    failed_two = _seed_log(user_id="failed-two")
    success = _seed_log(status="success", user_id="success-one")
    repo = build_questionnaire_repository()

    response = client.post(
        "/admin/questionnaires/external-push-logs/retry-batch",
        data={"push_log_ids": [str(failed_one["id"]), str(failed_two["id"]), str(success["id"])]},
        headers={"Accept": "application/json"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["source_status"] == "next_command"
    assert body["fallback_used"] is False
    assert body["adapter_mode"] == "real_blocked"
    assert body["selected_count"] == 3
    assert body["retried_count"] == 2
    assert body["planned_count"] == 2
    assert body["skipped_count"] == 1
    assert body["real_external_call_executed"] is False
    assert len(repo._external_push_logs) == 5  # type: ignore[attr-defined]

    scoped = client.get("/admin/questionnaires/1/external-push-logs?status=planned_current")
    assert scoped.status_code == 200
    assert "已生成补发计划" in scoped.text


def test_next_external_push_retry_real_delivery_requires_explicit_gate(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _seed_log()
    captured: dict[str, object] = {}

    class Response:
        status_code = 200
        text = '{"ok":true}'

    def fake_post(url: str, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return Response()

    monkeypatch.setenv("AICRM_QUESTIONNAIRE_EXTERNAL_PUSH_RETRY_REAL_ENABLED", "true")
    monkeypatch.setattr("aicrm_next.questionnaire.external_push_logs.requests.post", fake_post)

    response = client.post(
        f"/admin/questionnaires/external-push-logs/{source['id']}/retry",
        headers={"Accept": "application/json"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["adapter_mode"] == "real_enabled"
    assert body["real_external_call_executed"] is True
    assert body["side_effect_plan"]["requires_approval"] is False
    assert body["log"]["status"] == "success"
    assert captured["url"] == "https://hooks.example.com/questionnaire"
