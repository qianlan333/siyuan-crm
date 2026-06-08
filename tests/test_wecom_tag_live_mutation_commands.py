from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.customer_tags.live_mutation import (
    get_wecom_tag_live_mutation_audit_events,
    get_wecom_tag_live_mutation_side_effect_plans,
)
from aicrm_next.main import create_app


def _client(monkeypatch) -> TestClient:
    monkeypatch.setenv("SECRET_KEY", "wecom-live-mutation-command-test")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    monkeypatch.delenv("AICRM_WECOM_TAG_LIVE_ADAPTER_ENABLED", raising=False)
    return TestClient(create_app(), raise_server_exceptions=False)


def _assert_plan_only(payload: dict, command_name: str, effect_type: str) -> None:
    assert payload["ok"] is True
    assert payload["command_name"] == command_name
    assert payload["source_status"] == "next_command"
    assert payload["route_owner"] == "ai_crm_next"
    assert payload["fallback_used"] is False
    assert payload["adapter_mode"] == "real_blocked"
    assert payload["effect_type"] == effect_type
    assert payload["real_external_call_executed"] is False
    assert payload["wecom_api_called"] is False
    assert payload["side_effect_plan"]["effect_type"] == effect_type
    assert payload["side_effect_plan"]["adapter_name"] == "wecom"
    assert payload["side_effect_plan"]["adapter_mode"] == "real_blocked"
    assert payload["side_effect_plan"]["requires_approval"] is True
    assert payload["side_effect_plan"]["real_external_call_executed"] is False
    assert payload["side_effect_plan"]["wecom_api_called"] is False


def test_live_gate_is_next_owned_blocked_gate(monkeypatch) -> None:
    client = _client(monkeypatch)

    response = client.get("/api/admin/wecom/tags/live/gate")

    assert response.status_code == 200
    assert "X-AICRM-Compatibility-Facade" not in response.headers
    payload = response.json()
    assert payload["source_status"] == "next_live_gate"
    assert payload["route_owner"] == "ai_crm_next"
    assert payload["fallback_used"] is False
    assert payload["adapter_mode"] == "real_blocked"
    assert payload["real_enabled"] is False
    assert payload["available"] is False
    assert payload["blocked"] is True
    assert payload["real_external_call_executed"] is False
    assert payload["wecom_api_called"] is False


def test_live_mark_and_unmark_execute_next_commandbus_plan_only(monkeypatch) -> None:
    client = _client(monkeypatch)

    mark = client.post(
        "/api/admin/wecom/tags/live/mark",
        json={"external_userid": "wx_ext_001", "tag_ids": ["tag_fixture_active"], "operator": "tester"},
        headers={"Idempotency-Key": "wecom-live-mark-command"},
    )
    unmark = client.post(
        "/api/admin/wecom/tags/live/unmark",
        json={"external_userid": "wx_ext_001", "tag_ids": ["tag_fixture_active"], "operator": "tester"},
        headers={"Idempotency-Key": "wecom-live-unmark-command"},
    )

    assert mark.status_code == 200
    assert unmark.status_code == 200
    _assert_plan_only(mark.json(), "wecom.tag.mark", "wecom.tag.mark")
    _assert_plan_only(unmark.json(), "wecom.tag.unmark", "wecom.tag.unmark")
    assert len(get_wecom_tag_live_mutation_audit_events()) == 2
    assert len(get_wecom_tag_live_mutation_side_effect_plans()) == 2


def test_live_mutation_validation_errors_are_400(monkeypatch) -> None:
    client = _client(monkeypatch)

    missing_external = client.post("/api/admin/wecom/tags/live/mark", json={"tag_ids": ["tag_fixture_active"]})
    missing_tags = client.post("/api/admin/wecom/tags/live/unmark", json={"external_userid": "wx_ext_001", "tag_ids": []})

    assert missing_external.status_code == 400
    assert missing_external.json()["error_code"] == "external_userid_missing"
    assert missing_external.json()["fallback_used"] is False
    assert missing_external.json()["wecom_api_called"] is False
    assert missing_tags.status_code == 400
    assert missing_tags.json()["error_code"] == "tag_ids_missing"
