from __future__ import annotations

from datetime import datetime, timezone

import pytest

from aicrm_next.channel_entry import application as channel_application
from aicrm_next.platform_foundation.internal_events import InternalEventService
from aicrm_next.platform_foundation.internal_events.customer_identity import (
    CUSTOMER_WECOM_IDENTITY_READY_EVENT_TYPE,
    emit_customer_wecom_identity_ready_event,
)
from aicrm_next.platform_foundation.internal_events.worker import InternalEventWorker
from aicrm_next.questionnaire.continuation_repo import reset_questionnaire_continuation_fixture_state


pytestmark = pytest.mark.usefixtures("composed_internal_event_registry")


def _enable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("AICRM_INTERNAL_EVENTS_ENABLED", "1")
    monkeypatch.setenv("AICRM_INTERNAL_EVENTS_CUSTOMER_IDENTITY_ENABLED", "1")
    monkeypatch.setenv("AICRM_INTERNAL_EVENTS_ALLOWED_EVENT_TYPES", CUSTOMER_WECOM_IDENTITY_READY_EVENT_TYPE)
    monkeypatch.setenv("AICRM_QUESTIONNAIRE_CONTINUATION_ENABLED", "1")


def test_identity_ready_event_is_idempotent_and_contains_no_questionnaire_pii(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable(monkeypatch)
    reset_questionnaire_continuation_fixture_state()
    emitted_at = datetime(2026, 7, 21, 1, 2, 3, tzinfo=timezone.utc)

    first = emit_customer_wecom_identity_ready_event(
        unionid="union-ready-001",
        external_userid="wm-ready-001",
        follow_user_userid="owner-ready-001",
        identity_map_id=91,
        occurred_at=emitted_at,
        trace_id="wecom-callback-log-91",
    )
    duplicate = emit_customer_wecom_identity_ready_event(
        unionid="union-ready-001",
        external_userid="wm-ready-001",
        follow_user_userid="owner-ready-001",
        identity_map_id=91,
        occurred_at=emitted_at,
        trace_id="wecom-callback-log-91",
    )

    events, total = InternalEventService().list_events({"event_type": CUSTOMER_WECOM_IDENTITY_READY_EVENT_TYPE})
    assert total == 1
    assert first["event_id"] == duplicate["event_id"] == events[0].event_id
    assert first["consumer_run_count"] == 1
    identity = events[0].payload_json["identity"]
    assert set(identity) == {
        "identity_map_id",
        "unionid",
        "external_userid",
        "follow_user_userid",
        "occurred_at",
        "trace_id",
    }
    payload_text = str(events[0].payload_json).lower()
    assert "mobile" not in payload_text
    assert "openid" not in payload_text
    assert "answer" not in payload_text

    processed = InternalEventWorker().dispatch_one_consumer(
        events[0].event_id,
        "questionnaire_identity_continuation_consumer",
        dry_run=False,
        force=False,
        reason="questionnaire_identity_ready_event_test",
    )
    assert processed["consumer_run"]["status"] == "succeeded"
    assert processed["attempt"]["response_summary_json"]["claimed_count"] == 0


def test_identity_sync_emits_ready_event_without_channel_state(monkeypatch: pytest.MonkeyPatch) -> None:
    emitted: list[dict] = []
    monkeypatch.setattr(
        channel_application,
        "sync_external_contact_identity_for_event",
        lambda event, corp_id: {
            "status": "success",
            "unionid": "union-no-state-001",
            "identity_map_id": 501,
        },
    )
    monkeypatch.setattr(channel_application, "_record_identity_sync_result", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        channel_application,
        "_canonicalize_channel_entry_after_identity",
        lambda *args, **kwargs: {"status": "success"},
    )
    monkeypatch.setattr(
        channel_application,
        "emit_customer_wecom_identity_ready_event",
        lambda **kwargs: emitted.append(kwargs) or {"status": "emitted", "event_id": "iev-ready-no-state"},
    )

    result = channel_application._sync_identity_best_effort(
        {
            "Event": "change_external_contact",
            "ChangeType": "add_external_contact",
            "ExternalUserID": "wm-no-state-001",
            "UserID": "owner-no-state-001",
            "CreateTime": "1784592000",
        },
        corp_id="ww-no-state",
        event_log_id=501,
    )

    assert result["questionnaire_identity_ready_event"]["status"] == "emitted"
    assert emitted[0]["unionid"] == "union-no-state-001"
    assert emitted[0]["external_userid"] == "wm-no-state-001"
    assert emitted[0]["follow_user_userid"] == "owner-no-state-001"
