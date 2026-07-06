from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.customer_tags.local_projection import get_customer_tag_local_projection_fixture_rows
from aicrm_next.integration_gateway.wecom_channel_entry_client import WeComApiError
from aicrm_next.main import create_app
from aicrm_next.questionnaire import h5_write


def _client(monkeypatch) -> TestClient:
    h5_write.reset_questionnaire_h5_write_fixture_state()
    monkeypatch.setenv("SECRET_KEY", "questionnaire-real-wecom-tags")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    return TestClient(create_app(), raise_server_exceptions=False)


def _enable_wecom_config(monkeypatch) -> None:
    monkeypatch.setenv("WECOM_CORP_ID", "corp-real-tags")
    monkeypatch.setenv("WECOM_CONTACT_SECRET", "secret-real-tags")
    monkeypatch.delenv("WECOM_SECRET", raising=False)


def _submit(client: TestClient, *, identity: dict, idempotency_key: str = "questionnaire-real-tags"):
    return client.post(
        "/api/h5/questionnaires/hxc-activation-v1/submit",
        json={
            "answers": {"q_activation": "activated", "q_interest": ["ai_tools"]},
            "identity": identity,
        },
        headers={"Idempotency-Key": idempotency_key},
    )


def test_questionnaire_final_tags_calls_wecom_mark_tag(monkeypatch) -> None:
    calls: list[dict] = []

    class FakeProductionWeComAdapter:
        def mark_external_contact_tags(self, **payload):
            calls.append(payload)
            return {"errcode": 0, "errmsg": "ok"}

    _enable_wecom_config(monkeypatch)
    monkeypatch.setattr(h5_write, "ProductionWeComAdapter", FakeProductionWeComAdapter)
    client = _client(monkeypatch)

    response = _submit(
        client,
        identity={
            "external_userid": "wx_real_001",
            "follow_user_userid": "owner-real-001",
            "unionid": "union-real-001",
        },
    )

    assert response.status_code == 200
    tag_apply = response.json()["tag_apply"]
    assert tag_apply["status"] == "succeeded"
    assert tag_apply["wecom_api_called"] is True
    assert tag_apply["real_external_call_executed"] is True
    assert tag_apply["mark_tag_executed"] is True
    assert calls == [
        {
            "external_userid": "wx_real_001",
            "follow_user_userid": "owner-real-001",
            "add_tags": ["tag_hxc_activated", "tag_interest_ai_tools"],
            "remove_tags": [],
        }
    ]
    assert tag_apply["request_payload"] == {
        "userid": "owner-real-001",
        "external_userid": "wx_real_001",
        "add_tag": ["tag_hxc_activated", "tag_interest_ai_tools"],
    }


def test_questionnaire_final_tags_missing_external_userid_fails(monkeypatch) -> None:
    _enable_wecom_config(monkeypatch)
    client = _client(monkeypatch)

    response = _submit(
        client,
        identity={"follow_user_userid": "owner-real-001", "unionid": "union-missing-external"},
        idempotency_key="questionnaire-missing-external",
    )

    tag_apply = response.json()["tag_apply"]
    assert tag_apply["status"] == "failed"
    assert tag_apply["error_code"] == "missing_external_userid"
    assert tag_apply["wecom_api_called"] is False
    assert tag_apply["local_projection_updated"] is False
    assert get_customer_tag_local_projection_fixture_rows() == []


def test_questionnaire_final_tags_missing_follow_userid_fails(monkeypatch) -> None:
    _enable_wecom_config(monkeypatch)
    client = _client(monkeypatch)

    response = _submit(
        client,
        identity={"external_userid": "wx_missing_owner", "unionid": "union-missing-owner"},
        idempotency_key="questionnaire-missing-owner",
    )

    tag_apply = response.json()["tag_apply"]
    assert tag_apply["status"] == "failed"
    assert tag_apply["error_code"] == "owner_userid_missing"
    assert tag_apply["wecom_api_called"] is False
    assert tag_apply["local_projection_updated"] is False
    assert get_customer_tag_local_projection_fixture_rows() == []


def test_questionnaire_final_tags_missing_wecom_config_fails(monkeypatch) -> None:
    monkeypatch.delenv("WECOM_CORP_ID", raising=False)
    monkeypatch.delenv("WECOM_CONTACT_SECRET", raising=False)
    monkeypatch.delenv("WECOM_SECRET", raising=False)
    client = _client(monkeypatch)

    response = _submit(
        client,
        identity={
            "external_userid": "wx_missing_config",
            "follow_user_userid": "owner-real-001",
            "unionid": "union-missing-config",
        },
        idempotency_key="questionnaire-missing-config",
    )

    tag_apply = response.json()["tag_apply"]
    assert tag_apply["status"] == "failed"
    assert tag_apply["error_code"] == "missing_wecom_config"
    assert tag_apply["wecom_api_called"] is False
    assert tag_apply["missing_config"] == ["WECOM_CORP_ID", "WECOM_CONTACT_SECRET"]
    assert get_customer_tag_local_projection_fixture_rows() == []


def test_questionnaire_final_tags_wecom_error_surfaces(monkeypatch) -> None:
    class FakeProductionWeComAdapter:
        def mark_external_contact_tags(self, **payload):
            raise WeComApiError("mark_tag failed", payload={"errcode": 40058, "errmsg": "invalid tagid"})

    _enable_wecom_config(monkeypatch)
    monkeypatch.setattr(h5_write, "ProductionWeComAdapter", FakeProductionWeComAdapter)
    client = _client(monkeypatch)

    response = _submit(
        client,
        identity={
            "external_userid": "wx_wecom_error",
            "follow_user_userid": "owner-real-001",
            "unionid": "union-wecom-error",
        },
        idempotency_key="questionnaire-wecom-error",
    )

    tag_apply = response.json()["tag_apply"]
    assert tag_apply["status"] == "failed"
    assert tag_apply["error_code"] == "wecom_error_40058"
    assert tag_apply["wecom_api_called"] is True
    assert tag_apply["real_external_call_executed"] is True
    assert tag_apply["mark_tag_executed"] is False
    assert get_customer_tag_local_projection_fixture_rows() == []


def test_questionnaire_final_tags_success_updates_contact_tags_mirror(monkeypatch) -> None:
    class FakeProductionWeComAdapter:
        def mark_external_contact_tags(self, **payload):
            return {"errcode": 0, "errmsg": "ok"}

    _enable_wecom_config(monkeypatch)
    monkeypatch.setattr(h5_write, "ProductionWeComAdapter", FakeProductionWeComAdapter)
    client = _client(monkeypatch)

    response = _submit(
        client,
        identity={
            "external_userid": "wx_mirror_001",
            "follow_user_userid": "owner-mirror-001",
            "unionid": "union-mirror-001",
        },
        idempotency_key="questionnaire-mirror",
    )

    tag_apply = response.json()["tag_apply"]
    assert tag_apply["status"] == "succeeded"
    assert tag_apply["contact_tags_mirror_status"] == "updated"
    rows = [row for row in get_customer_tag_local_projection_fixture_rows() if row["unionid"] == "union-mirror-001"]
    assert {"tag_hxc_activated", "tag_interest_ai_tools"} <= {row["tag_id"] for row in rows}
    assert {row["userid"] for row in rows} == {"owner-mirror-001"}


def test_questionnaire_final_tags_no_real_blocked_status(monkeypatch) -> None:
    class FakeProductionWeComAdapter:
        def mark_external_contact_tags(self, **payload):
            return {"errcode": 0, "errmsg": "ok"}

    _enable_wecom_config(monkeypatch)
    monkeypatch.setattr(h5_write, "ProductionWeComAdapter", FakeProductionWeComAdapter)
    client = _client(monkeypatch)

    response = _submit(
        client,
        identity={
            "external_userid": "wx_no_blocked",
            "follow_user_userid": "owner-no-blocked",
            "unionid": "union-no-blocked",
        },
        idempotency_key="questionnaire-no-real-blocked",
    )

    body = response.json()
    serialized = response.text
    assert body["tag_apply"]["execution_mode"] == "execute"
    assert body["tag_apply"]["requires_approval"] is False
    assert body["tag_apply"]["status"] == "succeeded"
    for forbidden in ["real_blocked", "planned_as_success", "plan_only", "execute_dryrun", "shadow"]:
        assert forbidden not in serialized
