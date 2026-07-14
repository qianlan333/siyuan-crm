from __future__ import annotations

from contextlib import nullcontext

import pytest

from aicrm_next.channel_entry.identity_bridge import ensure_external_contact_identity_for_sidebar
from aicrm_next.channel_entry.application import process_wecom_external_contact_event
from aicrm_next.channel_entry.schemas import ProcessWeComExternalContactEventCommand
from aicrm_next.channel_entry.wecom_adapter import get_wecom_adapter, set_wecom_adapter
from aicrm_next.shared.postgres_connection import get_db
from scripts.run_identity_mobile_bridge_backfill import run_backfill


def _app_context(app):
    return app.app_context() if hasattr(app, "app_context") else nullcontext()


class DetailAdapter:
    def __init__(self):
        self.profile_updates: list[dict] = []

    def get_external_contact_detail(self, external_userid: str):
        return {
            "errcode": 0,
            "errmsg": "ok",
            "external_contact": {
                "external_userid": external_userid,
                "unionid": "union_bridge_001",
                "openid": "openid_bridge_001",
                "name": "桥接客户",
                "type": 1,
            },
            "follow_user": [
                {
                    "userid": "owner_bridge",
                    "remark": "桥接备注",
                    "description": "",
                    "state": "",
                    "createtime": 1780640000,
                }
            ],
        }

    def update_external_contact_remark(self, payload: dict):
        self.profile_updates.append(dict(payload))
        return {"errcode": 0, "errmsg": "ok"}


def _seed_identity_mobile_candidate(db, *, unionid: str, external_userid: str, mobile: str, owner_userid: str, openid: str = "") -> None:
    db.execute(
        """
        INSERT INTO crm_user_identity (
            unionid, primary_external_userid, primary_openid, primary_owner_userid,
            external_userids_json, openids_json, mobile, mobile_normalized,
            identity_status, created_at, updated_at
        )
        VALUES (
            ?, ?, ?, ?,
            jsonb_build_array(CAST(? AS text)),
            CASE WHEN CAST(? AS text) = '' THEN '[]'::jsonb ELSE jsonb_build_array(CAST(? AS text)) END,
            '', ?, 'active', NOW(), NOW() - INTERVAL '5 minutes'
        )
        ON CONFLICT (unionid) DO UPDATE SET
            primary_external_userid = EXCLUDED.primary_external_userid,
            primary_openid = COALESCE(NULLIF(EXCLUDED.primary_openid, ''), crm_user_identity.primary_openid),
            primary_owner_userid = EXCLUDED.primary_owner_userid,
            external_userids_json = EXCLUDED.external_userids_json,
            openids_json = EXCLUDED.openids_json,
            mobile = '',
            mobile_normalized = EXCLUDED.mobile_normalized,
            identity_status = 'active',
            updated_at = NOW() - INTERVAL '5 minutes'
        """,
        (unionid, external_userid, openid, owner_userid, external_userid, openid, openid, mobile),
    )


def test_next_external_contact_callback_syncs_identity_and_binds_orphan_mobile(app, monkeypatch, next_pg_schema):
    monkeypatch.setattr(
        "aicrm_next.channel_entry.application.process_channel_entry",
        lambda command, **kwargs: {"handled": False, "reason": "channel_entry_not_under_test"},
    )
    monkeypatch.setattr(
        "aicrm_next.channel_entry.application.repo.log_external_contact_event",
        lambda **kwargs: {"id": 501, **kwargs},
    )
    monkeypatch.setattr(
        "aicrm_next.channel_entry.application.repo.record_identity_sync_result",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "aicrm_next.channel_entry.application.repo.mark_event_status",
        lambda *args, **kwargs: None,
    )
    previous_adapter = get_wecom_adapter()
    adapter = DetailAdapter()
    set_wecom_adapter(adapter)
    try:
        with _app_context(app):
            db = get_db()
            _seed_identity_mobile_candidate(
                db,
                unionid="union_bridge_001",
                external_userid="wm_bridge_001",
                openid="openid_bridge_001",
                mobile="18565883798",
                owner_userid="owner_bridge",
            )
            db.commit()

        result = process_wecom_external_contact_event(
            ProcessWeComExternalContactEventCommand(
                corp_id="ww-bridge",
                event_data={
                    "Event": "change_external_contact",
                    "ChangeType": "add_external_contact",
                    "ExternalUserID": "wm_bridge_001",
                    "UserID": "owner_bridge",
                    "CreateTime": "1780640000",
                },
                payload_xml="<xml/>",
                route="/wecom/external-contact/callback",
            )
        )

        with _app_context(app):
            db = get_db()
            identity = db.execute(
                """
                SELECT unionid,
                       primary_external_userid,
                       primary_openid,
                       primary_owner_userid,
                       customer_name AS name,
                       mobile_normalized AS mobile,
                       identity_status AS status
                FROM crm_user_identity
                WHERE unionid = ?
                """,
                ("union_bridge_001",),
            ).fetchone()
        assert result["identity_sync"]["status"] == "success"
        assert result["identity_sync"]["unionid_present"] is True
        assert result["identity_sync"]["profile_description"] == {
            "status": "success",
            "description_source": "external_userid",
            "description": "wm_bridge_001",
            "real_external_call_executed": True,
        }
        assert result["identity_sync"]["mobile_binding"]["status"] == "already_bound"
        assert result["identity_sync"]["questionnaire_backfill"]["reason"] == "questionnaire_submissions_unionid_only"
        assert adapter.profile_updates == [
            {
                "userid": "owner_bridge",
                "external_userid": "wm_bridge_001",
                "description": "wm_bridge_001",
            }
        ]
        assert dict(identity) == {
            "unionid": "union_bridge_001",
            "primary_external_userid": "wm_bridge_001",
            "primary_openid": "openid_bridge_001",
            "primary_owner_userid": "owner_bridge",
            "name": "桥接客户",
            "mobile": "18565883798",
            "status": "active",
        }
    finally:
        set_wecom_adapter(previous_adapter)


def test_next_external_contact_callback_keeps_entry_success_when_identity_sync_fails(monkeypatch):
    calls = []
    status_updates = []
    diagnostics = []
    runtime_updates = []
    monkeypatch.setattr(
        "aicrm_next.channel_entry.application.repo.log_external_contact_event",
        lambda **kwargs: {"id": 321, **kwargs},
    )
    monkeypatch.setattr(
        "aicrm_next.channel_entry.application.sync_external_contact_identity_for_event",
        lambda event, corp_id: calls.append("identity_sync") or {"status": "failed", "reason": "wecom_api_error"},
    )
    monkeypatch.setattr(
        "aicrm_next.channel_entry.application.repo.mark_event_status",
        lambda event_id, status, error_message="": status_updates.append(
            {"event_id": event_id, "status": status, "error_message": error_message}
        ),
    )
    monkeypatch.setattr(
        "aicrm_next.channel_entry.application.process_channel_entry",
        lambda command, **kwargs: calls.append("channel_entry") or {"handled": True, "reason": "channel_entry_baseline_recorded"},
    )
    monkeypatch.setattr(
        "aicrm_next.channel_entry.application.repo.record_identity_sync_result",
        lambda event_log_id, **kwargs: diagnostics.append({"event_log_id": event_log_id, **kwargs}),
    )
    monkeypatch.setattr(
        "aicrm_next.channel_entry.application.repo.mark_channel_entry_runtime_identity",
        lambda **kwargs: runtime_updates.append(kwargs) or {"status": "success", "updated_count": 1},
    )
    monkeypatch.setattr(
        "aicrm_next.channel_entry.application._canonicalize_channel_entry_after_identity",
        lambda *args, **kwargs: pytest.fail("failed identity sync should not canonicalize channel contact"),
    )

    result = process_wecom_external_contact_event(
        ProcessWeComExternalContactEventCommand(
            corp_id="ww-bridge",
            event_data={
                "Event": "change_external_contact",
                "ChangeType": "add_external_contact",
                "ExternalUserID": "wm_bridge_failed",
                "UserID": "owner_bridge",
                "State": "scene-a",
                "WelcomeCode": "welcome-failed",
                "CreateTime": "1780640001",
            },
            payload_xml="<xml/>",
            route="/wecom/external-contact/callback",
        )
    )

    assert calls == ["channel_entry", "identity_sync"]
    assert result["handled"] is True
    assert result["identity_sync"]["status"] == "failed"
    assert result["identity_sync"]["reason"] == "wecom_api_error"
    assert result["identity_sync"]["runtime_identity"] == {"status": "success", "updated_count": 1}
    assert status_updates == [
        {
            "event_id": 321,
            "status": "success",
            "error_message": "",
        }
    ]
    assert diagnostics == [
        {
            "event_log_id": 321,
            "status": "failed",
            "error_code": "wecom_api_error",
            "error_message": "wecom_api_error",
            "response_json": {
                "status": "failed",
                "reason": "wecom_api_error",
            },
        }
    ]
    assert runtime_updates[0]["event_log_id"] == 321
    assert runtime_updates[0]["external_userid"] == "wm_bridge_failed"
    assert runtime_updates[0]["identity_status"] == "failed"


def test_next_external_contact_callback_canonicalizes_channel_entry_after_identity_success(monkeypatch):
    calls = []
    status_updates = []
    contacts = []
    internal_events = []
    runtime_updates = []
    effect_logs = []
    monkeypatch.setattr(
        "aicrm_next.channel_entry.application.repo.log_external_contact_event",
        lambda **kwargs: {"id": 432, **kwargs},
    )
    monkeypatch.setattr(
        "aicrm_next.channel_entry.application.sync_external_contact_identity_for_event",
        lambda event, corp_id: calls.append("identity_sync") or {"status": "success", "unionid": "union_bridge_success"},
    )
    monkeypatch.setattr(
        "aicrm_next.channel_entry.application.process_channel_entry",
        lambda command, **kwargs: calls.append("runtime_entry") or {"handled": True, "mode": "channel_runtime_only", "reason": "channel_entry_runtime_recorded"},
    )
    monkeypatch.setattr(
        "aicrm_next.channel_entry.application.resolve_channel_for_scene",
        lambda **kwargs: (
            {"id": 10, "channel_code": "c", "channel_name": "C", "scene_value": "scene-a", "status": "active", "owner_staff_id": "owner_bridge"},
            {"match_type": "current_scene", "matched_scene": "scene-a", "channel_id": 10},
        ),
    )
    monkeypatch.setattr(
        "aicrm_next.channel_entry.application.repo.upsert_channel_contact",
        lambda **kwargs: contacts.append(kwargs) or {"id": 88, **kwargs},
    )
    monkeypatch.setattr(
        "aicrm_next.channel_entry.application.repo.upsert_channel_entry_effect_log",
        lambda **kwargs: effect_logs.append(kwargs) or kwargs,
    )
    monkeypatch.setattr(
        "aicrm_next.channel_entry.application.repo.record_identity_sync_result",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "aicrm_next.channel_entry.application.repo.mark_channel_entry_runtime_identity",
        lambda **kwargs: runtime_updates.append(kwargs) or {"status": "success", "updated_count": 1},
    )
    monkeypatch.setattr(
        "aicrm_next.channel_entry.application.repo.mark_event_status",
        lambda event_id, status, error_message="": status_updates.append(
            {"event_id": event_id, "status": status, "error_message": error_message}
        ),
    )

    class FakeInternalEventService:
        def emit_event(self, **kwargs):
            internal_events.append(kwargs)
            return {"event": {"event_id": "evt-channel-entry"}, "consumer_runs": [{}]}

    monkeypatch.setattr("aicrm_next.channel_entry.application.InternalEventService", FakeInternalEventService)

    result = process_wecom_external_contact_event(
        ProcessWeComExternalContactEventCommand(
            corp_id="ww-bridge",
            event_data={
                "Event": "change_external_contact",
                "ChangeType": "add_external_contact",
                "ExternalUserID": "wm_bridge_success",
                "UserID": "owner_bridge",
                "State": "scene-a",
                "WelcomeCode": "welcome-success",
                "CreateTime": "1780640003",
            },
            payload_xml="<xml/>",
            route="/wecom/external-contact/callback",
        )
    )

    assert calls == ["runtime_entry", "identity_sync"]
    assert result["handled"] is True
    assert result["identity_sync"]["status"] == "success"
    assert result["identity_sync"]["channel_entry_canonical"]["status"] == "success"
    assert contacts == [
        {
            "channel_id": 10,
            "unionid": "union_bridge_success",
            "external_contact_id": "wm_bridge_success",
            "owner_staff_id": "owner_bridge",
            "source_payload": {
                "Event": "change_external_contact",
                "ChangeType": "add_external_contact",
                "ExternalUserID": "wm_bridge_success",
                "UserID": "owner_bridge",
                "State": "scene-a",
                "WelcomeCode": "welcome-success",
                "CreateTime": "1780640003",
                "corp_id": "ww-bridge",
                "unionid": "union_bridge_success",
            },
        }
    ]
    assert internal_events[0]["subject_type"] == "unionid"
    assert internal_events[0]["subject_id"] == "union_bridge_success"
    assert runtime_updates[0]["unionid"] == "union_bridge_success"
    assert runtime_updates[0]["identity_status"] == "success"
    assert effect_logs[0]["effect_type"] == "channel_contact"
    assert status_updates == [{"event_id": 432, "status": "success", "error_message": ""}]


def test_next_external_contact_callback_records_runtime_entry_when_identity_pending(monkeypatch):
    calls = []
    status_updates = []
    runtime_updates = []
    monkeypatch.setattr(
        "aicrm_next.channel_entry.application.repo.log_external_contact_event",
        lambda **kwargs: {"id": 654, **kwargs},
    )
    monkeypatch.setattr(
        "aicrm_next.channel_entry.application.sync_external_contact_identity_for_event",
        lambda event, corp_id: calls.append("identity_sync") or {"status": "pending_identity", "reason": "missing_unionid"},
    )
    monkeypatch.setattr(
        "aicrm_next.channel_entry.application.repo.mark_event_status",
        lambda event_id, status, error_message="": status_updates.append(
            {"event_id": event_id, "status": status, "error_message": error_message}
        ),
    )
    monkeypatch.setattr(
        "aicrm_next.channel_entry.application.process_channel_entry",
        lambda command, **kwargs: calls.append("channel_entry") or {"handled": True, "mode": "channel_runtime_only", "reason": "channel_entry_runtime_recorded"},
    )
    monkeypatch.setattr(
        "aicrm_next.channel_entry.application.repo.mark_channel_entry_runtime_identity",
        lambda **kwargs: runtime_updates.append(kwargs) or {"status": "success", "updated_count": 1},
    )

    result = process_wecom_external_contact_event(
        ProcessWeComExternalContactEventCommand(
            corp_id="ww-bridge",
            event_data={
                "Event": "change_external_contact",
                "ChangeType": "add_external_contact",
                "ExternalUserID": "wm_bridge_pending",
                "UserID": "owner_bridge",
                "State": "scene-a",
                "WelcomeCode": "welcome-pending",
                "CreateTime": "1780640002",
            },
            payload_xml="<xml/>",
            route="/wecom/external-contact/callback",
        )
    )

    assert calls == ["channel_entry", "identity_sync"]
    assert result["handled"] is True
    assert result["entry_result"] == {"handled": True, "mode": "channel_runtime_only", "reason": "channel_entry_runtime_recorded"}
    assert result["identity_sync"]["status"] == "pending_identity"
    assert result["identity_sync"]["runtime_identity"] == {"status": "success", "updated_count": 1}
    assert runtime_updates[0]["event_log_id"] == 654
    assert runtime_updates[0]["external_userid"] == "wm_bridge_pending"
    assert runtime_updates[0]["identity_status"] == "pending_identity"
    assert status_updates == [{"event_id": 654, "status": "success", "error_message": ""}]


def test_sidebar_identity_refresh_binds_missing_identity_on_access(app, next_pg_schema):
    previous_adapter = get_wecom_adapter()
    adapter = DetailAdapter()
    set_wecom_adapter(adapter)
    try:
        with _app_context(app):
            db = get_db()
            _seed_identity_mobile_candidate(
                db,
                unionid="union_bridge_001",
                external_userid="wm_bridge_001",
                openid="openid_bridge_001",
                mobile="18565883798",
                owner_userid="owner_bridge",
            )
            db.commit()

        result = ensure_external_contact_identity_for_sidebar(
            external_userid="wm_bridge_001",
            owner_userid="owner_bridge",
            corp_id="ww-bridge",
            min_interval_seconds=60,
        )

        with _app_context(app):
            db = get_db()
            identity = db.execute(
                """
                SELECT primary_external_userid AS external_userid,
                       mobile_normalized AS mobile,
                       primary_owner_userid
                FROM crm_user_identity
                WHERE unionid = ?
                """,
                ("union_bridge_001",),
            ).fetchone()

        assert result["status"] == "skipped"
        assert result["reason"] == "identity_fresh"
        assert result["mobile_bound"] is True
        assert adapter.profile_updates == []
        assert dict(identity) == {
            "external_userid": "wm_bridge_001",
            "mobile": "18565883798",
            "primary_owner_userid": "owner_bridge",
        }
    finally:
        set_wecom_adapter(previous_adapter)


def test_identity_mobile_bridge_backfill_repairs_historical_unbound_rows(app, next_pg_schema):
    with _app_context(app):
        db = get_db()
        db.execute(
            """
            INSERT INTO wecom_external_contact_identity_map (
                corp_id, external_userid, unionid, openid, follow_user_userid, name
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "ww-bridge",
                "wm_bridge_history",
                "union_bridge_history",
                "openid_bridge_history",
                "owner_history",
                "历史桥接客户",
            ),
        )
        _seed_identity_mobile_candidate(
            db,
            unionid="union_bridge_history",
            external_userid="wm_bridge_history",
            openid="openid_bridge_history",
            mobile="18565883799",
            owner_userid="owner_history",
        )
        db.commit()

        dry_run = run_backfill(execute=False, limit=50, external_userids=["wm_bridge_history"])
        executed = run_backfill(execute=True, limit=50, external_userids=["wm_bridge_history"])

        identity = db.execute(
            """
            SELECT primary_external_userid AS external_userid,
                   mobile_normalized AS mobile,
                   primary_owner_userid
            FROM crm_user_identity
            WHERE unionid = ?
            """,
            ("union_bridge_history",),
        ).fetchone()

    assert dry_run["summary"] == {"already_bound": 1}
    assert executed["summary"] == {"already_bound": 1}
    assert executed["results"][0]["questionnaire_backfill"]["reason"] == "questionnaire_submissions_unionid_only"
    assert dict(identity) == {
        "external_userid": "wm_bridge_history",
        "mobile": "18565883799",
        "primary_owner_userid": "owner_history",
    }
