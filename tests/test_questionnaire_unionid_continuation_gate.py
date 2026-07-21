from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.main import create_app
from aicrm_next.questionnaire.application import CompleteWechatOAuthCallbackCommand
from aicrm_next.questionnaire.dto import OAuthCallbackRequest, OAuthStartRequest
from aicrm_next.questionnaire.oauth import (
    COOKIE_NAME,
    QuestionnaireOAuthAdapter,
    build_questionnaire_h5_identity_cookie,
    reset_questionnaire_oauth_state,
)
from aicrm_next.questionnaire.repo import build_questionnaire_repository


WECHAT_UA = "Mozilla/5.0 MicroMessenger/8.0.49"


def _signed_unionid_client(monkeypatch) -> TestClient:
    monkeypatch.setenv("AICRM_QUESTIONNAIRE_UNIONID_REQUIRED", "1")
    client = TestClient(create_app())
    client.cookies.set(
        COOKIE_NAME,
        build_questionnaire_h5_identity_cookie(
            {
                "openid": "openid-questionnaire-gate-001",
                "unionid": "unionid-questionnaire-gate-001",
                "respondent_key": "unionid-questionnaire-gate-001",
                "slug": "hxc-activation-v1",
                "unionid_verified": True,
                "identity_source": "wechat_oauth_provider",
            }
        ),
    )
    return client


def test_published_questionnaire_gate_rejects_forged_query_and_body_unionid(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_QUESTIONNAIRE_UNIONID_REQUIRED", "1")
    client = TestClient(create_app())

    page = client.get(
        "/s/hxc-activation-v1?unionid=forged-unionid",
        headers={"User-Agent": WECHAT_UA},
        follow_redirects=False,
    )
    submit = client.post(
        "/api/h5/questionnaires/hxc-activation-v1/submit?unionid=forged-query-unionid",
        json={
            "unionid": "forged-body-unionid",
            "answers": {"q_activation": "activated"},
        },
        headers={"User-Agent": WECHAT_UA},
    )

    assert page.status_code == 302
    assert page.headers["location"].startswith("/api/h5/wechat/oauth/start?")
    assert submit.status_code == 401
    assert submit.json()["error"] == "unionid_oauth_required"
    assert submit.json()["write_model_status"] == "blocked"


def test_published_questionnaire_gate_rejects_legacy_signed_but_unverified_unionid(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_QUESTIONNAIRE_UNIONID_REQUIRED", "1")
    client = TestClient(create_app())
    client.cookies.set(
        COOKIE_NAME,
        build_questionnaire_h5_identity_cookie(
            {
                "openid": "openid-legacy-query-cookie",
                "unionid": "unionid-legacy-query-cookie",
                "respondent_key": "unionid-legacy-query-cookie",
            }
        ),
    )

    response = client.post(
        "/api/h5/questionnaires/hxc-activation-v1/submit",
        json={"answers": {"q_activation": "activated"}},
        headers={"User-Agent": WECHAT_UA},
    )

    assert response.status_code == 401
    assert response.json()["error"] == "unionid_oauth_required"


def test_signed_unionid_session_can_submit_and_is_preserved_without_wecom_identity(monkeypatch) -> None:
    client = _signed_unionid_client(monkeypatch)

    response = client.post(
        "/api/h5/questionnaires/hxc-activation-v1/submit",
        json={"mobile": "13800138000", "answers": {"q_activation": "activated"}},
        headers={"User-Agent": WECHAT_UA},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["unionid"] == "unionid-questionnaire-gate-001"
    assert body["mobile"] == ""
    assert body["mobile_binding"]["reason"] == "questionnaire_mobile_is_answer_only"
    persisted = build_questionnaire_repository().latest_submission(int(body["questionnaire_id"]))
    assert persisted["unionid_verification_source"] == "wechat_oauth_signed_session"
    assert persisted["unionid_verified"] is True


def test_questionnaire_oauth_callback_fails_closed_when_unionid_is_unavailable(monkeypatch) -> None:
    reset_questionnaire_oauth_state()
    adapter = QuestionnaireOAuthAdapter(mode="fake")
    start = adapter.build_authorize_url(
        OAuthStartRequest(slug="hxc-activation-v1", redirect="/s/hxc-activation-v1")
    )
    monkeypatch.setattr(
        adapter,
        "fetch_user_identity",
        lambda _request, _state: {
            "ok": True,
            "openid": "openid-without-unionid",
            "unionid": "",
            "external_userid": "",
            "real_external_call_executed": False,
        },
    )

    result = adapter.callback(OAuthCallbackRequest(code="code", state=start["state"]))

    assert result["ok"] is False
    assert result["error"] == "unionid_unavailable"
    assert result["status_code"] == 409
    assert "session_cookie" not in result


def test_questionnaire_oauth_projection_conflict_never_issues_cookie() -> None:
    reset_questionnaire_oauth_state()
    adapter = QuestionnaireOAuthAdapter(mode="fake")
    start = adapter.build_authorize_url(
        OAuthStartRequest(slug="hxc-activation-v1", redirect="/s/hxc-activation-v1")
    )
    command = CompleteWechatOAuthCallbackCommand(
        adapter=adapter,
        identity_projector=lambda **_kwargs: {
            "ok": False,
            "reason": "openid_identity_conflict",
        },
    )

    result = command(OAuthCallbackRequest(code="code", state=start["state"]))

    assert result["ok"] is False
    assert result["error"] == "identity_conflict"
    assert result["status_code"] == 409
    assert "session_cookie" not in result
    assert "identity" not in result
