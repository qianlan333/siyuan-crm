from __future__ import annotations

from flask import Blueprint, Flask

from wecom_ability_service.http.questionnaire_support import (
    _build_questionnaire_page_state,
    _parse_questionnaire_form_payload,
    _questionnaire_oauth_start_url,
    _questionnaire_request_meta,
    _wechat_oauth_authorize_url,
)


def _app() -> Flask:
    app = Flask(__name__)
    app.secret_key = "test-secret"
    app.config.update(
        WECHAT_MP_APP_ID="wx-test-appid",
        WECHAT_MP_APP_SECRET="wx-test-secret",
    )
    bp = Blueprint("api", __name__)
    bp.add_url_rule("/api/h5/wechat/oauth/start", endpoint="h5_wechat_oauth_start", view_func=lambda: "")
    app.register_blueprint(bp)
    return app


def _questionnaire() -> dict[str, object]:
    return {
        "slug": "lead-quiz",
        "title": "线索问卷",
        "description": "用于 H5 表单提交",
        "answer_display_mode": "one_by_one",
        "questions": [
            {"id": 1, "type": "single_choice", "title": "来源", "options": []},
            {"id": 2, "type": "multi_choice", "title": "需求", "options": []},
            {"id": 3, "type": "textarea", "title": "备注", "options": []},
            {"id": 4, "type": "mobile", "title": "手机号", "options": []},
        ],
    }


def test_parse_questionnaire_form_payload_normalizes_h5_form_answers_and_hints():
    app = _app()
    with app.test_request_context(
        "/s/lead-quiz?source_channel=wechat&external_userid=wm_ext_001",
        method="POST",
        data={
            "q_1": "11",
            "q_2": ["21", "custom"],
            "q_3": " 备注内容 ",
            "q_4": "13800138000",
        },
    ):
        payload = _parse_questionnaire_form_payload(_questionnaire())

    assert payload["source_channel"] == "wechat"
    assert payload["external_userid"] == "wm_ext_001"
    assert payload["answers"] == {
        "1": 11,
        "2": [21, "custom"],
        "3": "备注内容",
        "4": "13800138000",
    }


def test_build_questionnaire_page_state_centralizes_oauth_request_hints_and_prefill_fields():
    app = _app()
    with app.test_request_context(
        "/s/lead-quiz?campaign_id=cmp_001",
        headers={"X-Forwarded-For": "203.0.113.9, 10.0.0.1", "User-Agent": "wechat-browser"},
    ):
        oauth_url = _questionnaire_oauth_start_url("lead-quiz", {"campaign_id": "cmp_001"})
        page_state = _build_questionnaire_page_state(
            _questionnaire(),
            page_mode="questionnaire",
            env_notice="",
            oauth_start_url=oauth_url,
            is_wechat_browser=True,
            is_authorized=True,
            prefill_payload={"answers": {"1": 11, "2": [21, "custom"], "3": "备注内容"}},
        )
        request_meta = _questionnaire_request_meta()

    assert page_state["oauth_start_url"] == "/api/h5/wechat/oauth/start?slug=lead-quiz&campaign_id=cmp_001"
    assert page_state["request_hints"] == {"campaign_id": "cmp_001"}
    assert page_state["prefill_fields"] == {"q_1": "11", "q_2": ["21", "custom"], "q_3": "备注内容"}
    assert request_meta == {"ip": "203.0.113.9", "user_agent": "wechat-browser"}


def test_wechat_oauth_authorize_url_uses_standard_questionnaire_oauth_query_shape():
    authorize_url = _wechat_oauth_authorize_url(
        app_id="wx-test-appid",
        redirect_uri="https://crm.example.com/api/h5/wechat/oauth/callback",
        scope="snsapi_userinfo",
        state="state-token",
    )

    assert authorize_url == (
        "https://open.weixin.qq.com/connect/oauth2/authorize?"
        "appid=wx-test-appid&"
        "redirect_uri=https%3A%2F%2Fcrm.example.com%2Fapi%2Fh5%2Fwechat%2Foauth%2Fcallback&"
        "response_type=code&scope=snsapi_userinfo&state=state-token#wechat_redirect"
    )
