from __future__ import annotations

from fastapi.testclient import TestClient

import aicrm_next.questionnaire.h5_write as h5_write
from aicrm_next.channel_entry.wecom_adapter import set_wecom_adapter
from aicrm_next.customer_tags.live_mutation import execute_wecom_tag_mutation, reset_wecom_tag_live_mutation_fixture_state
from aicrm_next.customer_tags.mutation_commands import PlanCustomerTagAssignmentCommand
from aicrm_next.identity_contact.dto import IdentityResolution
from aicrm_next.main import create_app


def _client(monkeypatch) -> TestClient:
    monkeypatch.setenv("SECRET_KEY", "wecom-live-mutation-callers")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    return TestClient(create_app(), raise_server_exceptions=False)


def test_sidebar_signup_tag_mutation_remains_plan_only(monkeypatch) -> None:
    client = _client(monkeypatch)

    response = client.post(
        "/api/sidebar/signup-tags/mark",
        json={"external_userid": "wx_ext_001", "tag_id": "tag_fixture_active", "marked": True},
        headers={"Idempotency-Key": "sidebar-tag-plan-only"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_status"] == "next_command"
    assert payload["fallback_used"] is False
    assert payload["real_external_call_executed"] is False
    assert payload["side_effect_plan"]["effect_type"] == "wecom.tag.update"
    assert payload["side_effect_plan"]["adapter_mode"] == "real_blocked"
    assert payload["side_effect_plan"]["real_external_call_executed"] is False


def test_questionnaire_submit_tag_side_effect_uses_next_plan(monkeypatch) -> None:
    client = _client(monkeypatch)

    response = client.post(
        "/api/h5/questionnaires/hxc-activation-v1/submit",
        json={
            "answers": {"q_activation": "activated", "q_interest": ["ai_tools"]},
            "identity": {"external_userid": "wx_ext_001", "openid": "openid_001", "unionid": "unionid_001"},
        },
        headers={"Idempotency-Key": "questionnaire-tag-plan-only"},
    )

    assert response.status_code == 200
    tag_plan = response.json()["side_effects"]["wecom_tag"]
    assert tag_plan["source_status"] == "next_command"
    assert tag_plan["effect_type"] == "questionnaire.tag.apply"
    assert tag_plan["fallback_used"] is False
    assert tag_plan["real_external_call_executed"] is False
    assert tag_plan["wecom_api_called"] is False
    assert tag_plan["side_effect_plan"]["adapter_mode"] == "real_blocked"
    assert tag_plan["side_effect_plan"]["requires_approval"] is True


def test_questionnaire_submit_marks_wecom_tags_when_live_adapter_enabled(monkeypatch) -> None:
    calls: list[dict] = []
    projection_calls: list[dict] = []
    mobile_bind_calls: list[dict] = []

    class FakeWeComAdapter:
        def mark_external_contact_tags(self, **payload):
            calls.append(dict(payload))
            return {"errcode": 0, "errmsg": "ok"}

    class FakeBindMobileToExternalContactCommand:
        def __call__(self, request):
            mobile_bind_calls.append(
                {
                    "external_userid": request.external_userid,
                    "mobile": request.mobile,
                    "owner_userid": request.owner_userid,
                    "bind_by_userid": request.bind_by_userid,
                }
            )
            return {"binding_status": "bound"}

    class FakeResolvePersonIdentityQuery:
        def __call__(self, request):
            return IdentityResolution(
                person_id="person-real-tag",
                external_userid=request.external_userid,
                mobile="",
                binding_status="bound",
                follow_user_userid="owner-real-tag",
                matched_by="external_userid",
            )

    def fake_projection(**payload):
        projection_calls.append(dict(payload))
        return {
            "ok": True,
            "contact_tags_upserted": len(payload["tag_ids"]),
            "customer_list_updated": 1,
            "customer_detail_updated": 1,
            "tags_after": list(payload["tag_ids"]),
        }

    monkeypatch.setenv("SECRET_KEY", "questionnaire-real-tag")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    monkeypatch.setenv("AICRM_NEXT_WECOM_REAL_CALLS_ENABLED", "true")
    monkeypatch.setenv("WECOM_CORP_ID", "ww-test")
    monkeypatch.setenv("WECOM_CONTACT_SECRET", "secret")
    monkeypatch.setattr(h5_write, "ResolvePersonIdentityQuery", FakeResolvePersonIdentityQuery)
    monkeypatch.setattr(h5_write, "BindMobileToExternalContactCommand", FakeBindMobileToExternalContactCommand)
    monkeypatch.setattr(h5_write, "apply_questionnaire_tag_projection", fake_projection)
    set_wecom_adapter(FakeWeComAdapter())
    try:
        client = TestClient(create_app(), raise_server_exceptions=False)
        response = client.post(
            "/api/h5/questionnaires/hxc-activation-v1/submit",
            json={
                "answers": {"q_activation": "activated", "q_interest": ["ai_tools"]},
                "identity": {"external_userid": "wx_real_tag_001", "mobile": "13800138000"},
            },
            headers={"Idempotency-Key": "questionnaire-tag-real-live"},
        )
    finally:
        set_wecom_adapter(None)

    assert response.status_code == 200
    tag_effect = response.json()["side_effects"]["wecom_tag"]
    assert tag_effect["source_status"] == "wecom_live_mark_tag_completed"
    assert tag_effect["adapter_mode"] == "real_enabled"
    assert tag_effect["real_external_call_executed"] is True
    assert tag_effect["wecom_api_called"] is True
    assert tag_effect["mark_tag_executed"] is True
    assert calls == [
        {
            "external_userid": "wx_real_tag_001",
            "follow_user_userid": "owner-real-tag",
            "add_tags": ["tag_hxc_activated", "tag_interest_ai_tools"],
            "remove_tags": [],
        }
    ]
    assert projection_calls == [
        {
            "external_userid": "wx_real_tag_001",
            "follow_user_userid": "owner-real-tag",
            "tag_ids": ["tag_hxc_activated", "tag_interest_ai_tools"],
        }
    ]
    assert mobile_bind_calls == [
        {
            "external_userid": "wx_real_tag_001",
            "mobile": "13800138000",
            "owner_userid": "owner-real-tag",
            "bind_by_userid": "owner-real-tag",
        }
    ]
    assert response.json()["side_effects"]["mobile_binding"]["binding_status"] == "bound"
    assert "wecom.tag.executed" in response.json()["side_effect_plan"]["payload"]["planned_effects"]


def test_customer_tag_assignment_command_is_plan_only() -> None:
    reset_wecom_tag_live_mutation_fixture_state()

    payload = execute_wecom_tag_mutation(
        PlanCustomerTagAssignmentCommand(
            idempotency_key="customer-assignment-plan",
            actor_id="customer_profile",
            actor_type="system",
            external_userid="wx_ext_001",
            tag_ids=["tag_fixture_active"],
            source_route="/api/admin/customers/profile/tags",
            source_context={"source": "customer_profile_tag_assignment"},
        )
    )

    assert payload["ok"] is True
    assert payload["command_name"] == "wecom.tag.assignment.apply"
    assert payload["effect_type"] == "wecom.tag.assignment.apply"
    assert payload["side_effect_plan"]["adapter_mode"] == "real_blocked"
    assert payload["real_external_call_executed"] is False
    assert payload["wecom_api_called"] is False
