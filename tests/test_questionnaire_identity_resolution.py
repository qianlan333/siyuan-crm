from __future__ import annotations

import sys
import types

from flask import Flask

from wecom_ability_service.domains.questionnaire import service as questionnaire_service
from wecom_ability_service.domains.questionnaire import _service_helpers as questionnaire_helpers


def test_questionnaire_identity_resolution_prefers_unionid_then_openid_then_external_userid(monkeypatch):
    app = Flask(__name__)
    app.config["WECOM_CORP_ID"] = "ww-test"
    calls: list[tuple[str, str]] = []

    class FakeResolveExternalContactIdentityQuery:
        def __call__(self, dto):
            if dto.unionid:
                calls.append(("unionid", dto.unionid))
                return None
            if dto.openid:
                calls.append(("openid", dto.openid))
                return {"external_userid": "wm_ext_001", "openid": dto.openid}
            if dto.external_userid:
                calls.append(("external_userid", dto.external_userid))
                return {"external_userid": dto.external_userid}
            return None

    monkeypatch.setattr(
        questionnaire_helpers,
        "ResolveExternalContactIdentityQuery",
        FakeResolveExternalContactIdentityQuery,
    )

    with app.app_context():
        resolved = questionnaire_service.resolve_questionnaire_submit_identity(
            openid="openid-001",
            unionid="union-001",
            external_userid="wm_ext_001",
        )

    assert calls == [("unionid", "union-001"), ("openid", "openid-001")]
    assert resolved["external_userid"] == "wm_ext_001"
    assert resolved["matched_by"] == "openid"


def test_apply_questionnaire_mobile_binding_routes_through_application_command(monkeypatch):
    calls: dict[str, object] = {}

    class FakeBindExternalContactIdentityCommand:
        def __call__(self, dto):
            calls["bind_dto"] = dto
            return {"person_id": 101, "external_userid": dto.external_userid, "mobile": dto.mobile}

    class FakeResolvePersonIdentityQuery:
        def __call__(self, dto):
            calls["resolve_dto"] = dto
            return {"person_id": 101, "is_bound": True}

    monkeypatch.setattr(
        questionnaire_helpers,
        "BindExternalContactIdentityCommand",
        FakeBindExternalContactIdentityCommand,
    )
    monkeypatch.setattr(
        questionnaire_helpers,
        "ResolvePersonIdentityQuery",
        FakeResolvePersonIdentityQuery,
    )

    payload = questionnaire_service.apply_questionnaire_mobile_binding(
        {
            "id": 88,
            "mobile_snapshot": "13800138000",
            "external_userid": "wm_ext_questionnaire_001",
            "follow_user_userid": "sales_01",
        }
    )

    bind_dto = calls["bind_dto"]
    resolve_dto = calls["resolve_dto"]
    assert bind_dto.external_userid == "wm_ext_questionnaire_001"
    assert bind_dto.owner_userid == "sales_01"
    assert bind_dto.bind_by_userid == "questionnaire_submit"
    assert bind_dto.mobile == "13800138000"
    assert bind_dto.force_rebind is True
    assert resolve_dto.external_userid == "wm_ext_questionnaire_001"
    assert payload["bound"] is True
    assert payload["binding"]["person_id"] == 101


def test_resolve_questionnaire_respondent_identity_prefers_session_then_request_hints():
    sys.modules.setdefault("imghdr", types.ModuleType("imghdr"))

    from wecom_ability_service.application.questionnaire.queries import (
        ResolveQuestionnaireRespondentIdentityQuery,
    )

    resolved = ResolveQuestionnaireRespondentIdentityQuery()(
        session_identity={
            "respondent_key": "respondent-session-001",
            "openid": "openid-session-001",
            "unionid": "union-session-001",
        },
        request_identity={
            "respondent_key": "respondent-request-001",
            "openid": "openid-request-001",
            "external_userid": "wm_ext_request_001",
        },
    )

    assert resolved == {
        "respondent_key": "respondent-session-001",
        "openid": "openid-session-001",
        "unionid": "union-session-001",
        "external_userid": "wm_ext_request_001",
    }


def test_complete_questionnaire_oauth_callback_builds_session_identity_and_redirect_target():
    sys.modules.setdefault("imghdr", types.ModuleType("imghdr"))

    from wecom_ability_service.application.questionnaire.commands import (
        CompleteQuestionnaireOauthCallbackCommand,
    )

    calls: dict[str, object] = {}

    def fake_exchange_oauth_code(*, app_id: str, app_secret: str, code: str):
        calls["exchange"] = {
            "app_id": app_id,
            "app_secret": app_secret,
            "code": code,
        }
        return {
            "openid": "openid-userinfo-001",
            "access_token": "access-token-001",
        }

    def fake_fetch_wechat_userinfo(*, access_token: str, openid: str):
        calls["userinfo"] = {
            "access_token": access_token,
            "openid": openid,
        }
        return {
            "unionid": "union-userinfo-001",
        }

    result = CompleteQuestionnaireOauthCallbackCommand()(
        code="oauth-code-001",
        state_payload={
            "slug": "questionnaire-slug-001",
            "source_channel": "朋友圈",
            "campaign_id": "cmp-001",
        },
        app_id="wx-test-appid",
        app_secret="wx-test-secret",
        oauth_scope="snsapi_userinfo",
        exchange_oauth_code=fake_exchange_oauth_code,
        fetch_wechat_userinfo_fn=fake_fetch_wechat_userinfo,
    )

    assert calls["exchange"] == {
        "app_id": "wx-test-appid",
        "app_secret": "wx-test-secret",
        "code": "oauth-code-001",
    }
    assert calls["userinfo"] == {
        "access_token": "access-token-001",
        "openid": "openid-userinfo-001",
    }
    assert result["session_identity"]["openid"] == "openid-userinfo-001"
    assert result["session_identity"]["unionid"] == "union-userinfo-001"
    assert result["session_identity"]["respondent_key"] == "union-userinfo-001"
    assert result["redirect_target"] == "/s/questionnaire-slug-001?source_channel=%E6%9C%8B%E5%8F%8B%E5%9C%88&campaign_id=cmp-001"
