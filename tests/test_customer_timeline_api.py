from __future__ import annotations

import json

import pytest

from wecom_ability_service.db import get_db


@pytest.fixture()
def app(tmp_path):
    from tests.conftest import build_pg_test_app

    with build_pg_test_app(tmp_path) as app:
        yield app


@pytest.fixture()
def client(app):
    return app.test_client()


def seed_timeline_fixture(app) -> None:
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("wm_timeline_001", "时间线客户", "sales_01", "重点跟进", "用于 timeline 测试", "2026-03-24 10:00:00"),
        )
        db.execute(
            """
            INSERT INTO archived_messages (
                seq, msgid, chat_type, external_userid, owner_userid, sender, receiver, msgtype, content, send_time, raw_payload, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                101,
                "timeline-msg-001",
                "private",
                "wm_timeline_001",
                "sales_01",
                "sales_01",
                "wm_timeline_001",
                "text",
                "第一条客户消息",
                "2026-03-20 10:00:00",
                json.dumps({"decrypted_message": {"from": "sales_01", "tolist": ["wm_timeline_001"]}}, ensure_ascii=False),
                "2026-03-20 10:00:01",
            ),
        )
        db.execute(
            """
            INSERT INTO class_user_status_history (
                external_userid, old_signup_status, new_signup_status, old_label_name, new_label_name,
                customer_name_snapshot, owner_userid_snapshot, mobile_snapshot, set_by_userid, set_at,
                wecom_tag_sync_status, wecom_tag_sync_error, status_flags_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "wm_timeline_001",
                "lead",
                "signed_999",
                "报名引流品",
                "已报名999",
                "时间线客户",
                "sales_01",
                "13800138000",
                "sales_01",
                "2026-03-23 11:00:00",
                "success",
                "",
                "{}",
                "2026-03-23 11:00:01",
            ),
        )
        db.commit()


def seed_marketing_timeline_fixture(app) -> None:
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO customer_value_segment_history (
                external_userid, segment, segment_rank, score, scoring_version, change_reason,
                submission_id, matched_question_ids_json, source_payload_json, evaluated_at, recorded_at, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "wm_timeline_001",
                "normal",
                1,
                2,
                "signup_conversion_v1",
                "initial_compute",
                None,
                json.dumps([101, 102], ensure_ascii=False),
                json.dumps({"core_threshold": 3, "top_threshold": 4}, ensure_ascii=False),
                "2026-03-21 09:00:00",
                "2026-03-21 09:00:00",
                "2026-03-21 09:00:01",
            ),
        )
        db.execute(
            """
            INSERT INTO customer_value_segment_history (
                external_userid, segment, segment_rank, score, scoring_version, change_reason,
                submission_id, matched_question_ids_json, source_payload_json, evaluated_at, recorded_at, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "wm_timeline_001",
                "top",
                3,
                4,
                "signup_conversion_v1",
                "segment_changed",
                None,
                json.dumps([101, 102, 103, 104], ensure_ascii=False),
                json.dumps({"core_threshold": 3, "top_threshold": 4}, ensure_ascii=False),
                "2026-03-22 09:00:00",
                "2026-03-22 09:00:00",
                "2026-03-22 09:00:01",
            ),
        )
        db.execute(
            """
            INSERT INTO message_batches (
                id, batch_key, window_start, window_end, status, message_count, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                778,
                "timeline-batch-778",
                "2026-03-24 09:30:00",
                "2026-03-24 09:45:00",
                "pending",
                1,
                "2026-03-24 09:30:00",
            ),
        )
        db.execute(
            """
            INSERT INTO customer_marketing_state_history (
                person_id, external_userid, automation_key, main_stage, sub_stage, activated, converted,
                eligible_for_conversion, batch_id, lifecycle_status, exit_reason, last_activation_at,
                last_conversion_marked_at, last_message_at, change_reason, state_payload_json, recorded_at, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                None,
                "wm_timeline_001",
                "signup_conversion_v1",
                "pool",
                "active_focus",
                True,
                False,
                True,
                None,
                "pool",
                "",
                "2026-03-23 08:00:00",
                "",
                "2026-03-20 10:00:00",
                "initial_compute",
                json.dumps(
                    {
                        "bound_external_userids": ["wm_timeline_001"],
                        "followup_segment": "focus",
                        "questionnaire_segment": "top",
                    },
                    ensure_ascii=False,
                ),
                "2026-03-23 08:00:00",
                "2026-03-23 08:00:01",
            ),
        )
        db.execute(
            """
            INSERT INTO customer_marketing_state_history (
                person_id, external_userid, automation_key, main_stage, sub_stage, activated, converted,
                eligible_for_conversion, batch_id, lifecycle_status, exit_reason, last_activation_at,
                last_conversion_marked_at, last_message_at, change_reason, state_payload_json, recorded_at, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                None,
                "wm_timeline_001",
                "signup_conversion_v1",
                "converted",
                "enrolled",
                True,
                True,
                False,
                778,
                "converted",
                "enrolled",
                "2026-03-23 08:00:00",
                "2026-03-24 09:00:00",
                "2026-03-20 10:00:00",
                "mark_enrolled",
                json.dumps(
                    {
                        "bound_external_userids": ["wm_timeline_001"],
                        "manual_conversion_action": "mark_enrolled",
                        "manual_conversion_operator": "sales_01",
                        "manual_conversion_source": "sidebar_manual",
                    },
                    ensure_ascii=False,
                ),
                "2026-03-24 09:00:00",
                "2026-03-24 09:00:01",
            ),
        )
        db.execute(
            """
            INSERT INTO conversion_dispatch_log (
                automation_key, batch_id, external_userid, dispatch_status, dispatch_channel,
                dispatch_payload_json, dispatch_note, dispatched_at, acked_at, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "signup_conversion_v1",
                778,
                "wm_timeline_001",
                "dispatched",
                "text_message",
                json.dumps({"operator": "openclaw", "source": "openclaw"}, ensure_ascii=False),
                "dispatched to openclaw",
                "2026-03-24 10:00:00",
                None,
                "2026-03-24 10:00:00",
                "2026-03-24 10:00:01",
            ),
        )
        db.commit()


def test_timeline_returns_ok_and_external_userid(client, app):
    seed_timeline_fixture(app)

    response = client.get("/api/customers/wm_timeline_001/timeline")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert "timeline" in payload
    assert payload["timeline"]["external_userid"] == "wm_timeline_001"


def test_timeline_includes_message_event(client, app):
    seed_timeline_fixture(app)

    response = client.get("/api/customers/wm_timeline_001/timeline?event_type=message")
    items = response.get_json()["timeline"]["items"]

    assert len(items) == 1
    assert items[0]["event_type"] == "message"
    assert items[0]["source_table"] == "archived_messages"


def test_timeline_includes_status_change_event(client, app):
    seed_timeline_fixture(app)

    response = client.get("/api/customers/wm_timeline_001/timeline?event_type=status_change")
    items = response.get_json()["timeline"]["items"]

    assert len(items) == 1
    assert items[0]["event_type"] == "status_change"
    assert items[0]["source_table"] == "class_user_status_history"


def test_timeline_orders_events_desc_by_event_time(client, app):
    seed_timeline_fixture(app)

    response = client.get("/api/customers/wm_timeline_001/timeline")
    items = response.get_json()["timeline"]["items"]

    assert [item["event_type"] for item in items] == ["status_change", "message"]


def test_timeline_event_type_filter_and_paging(client, app):
    seed_timeline_fixture(app)

    response = client.get("/api/customers/wm_timeline_001/timeline?limit=1&offset=1")
    timeline = response.get_json()["timeline"]

    assert timeline["count"] == 1
    assert timeline["limit"] == 1
    assert timeline["offset"] == 1
    assert timeline["filters"] == {"event_type": "", "limit": "1", "offset": "1"}
    assert timeline["items"][0]["event_type"] == "message"


def test_timeline_returns_404_for_missing_customer(client):
    response = client.get("/api/customers/wm_timeline_missing/timeline")
    payload = response.get_json()

    assert response.status_code == 404
    assert payload["ok"] is False


def test_timeline_includes_marketing_events_with_human_summaries(client, app):
    seed_timeline_fixture(app)
    seed_marketing_timeline_fixture(app)

    response = client.get("/api/customers/wm_timeline_001/timeline")
    payload = response.get_json()["timeline"]
    items = payload["items"]
    event_types = [item["event_type"] for item in items]

    assert response.status_code == 200
    assert {"message", "status_change", "marketing_state_change", "value_segment_change", "conversion_marked", "openclaw_dispatch"} <= set(
        event_types
    )

    segment_item = next(item for item in items if item["event_type"] == "value_segment_change" and item["payload"]["current_segment"] == "top")
    assert segment_item["summary"] == "客户初判从普通跟进变为重点跟进"
    assert segment_item["type"] == "value_segment_change"
    assert segment_item["payload"]["matched_question_ids_json"] == [101, 102, 103, 104]

    state_item = next(
        item
        for item in items
        if item["event_type"] == "marketing_state_change" and item["payload"]["current_stage"] == "converted/enrolled"
    )
    assert state_item["summary"] == "客户池子从激活重点跟进池变为已确认成交"
    assert state_item["payload"]["previous_stage"] == "pool/active_focus"

    conversion_item = next(item for item in items if item["event_type"] == "conversion_marked")
    assert conversion_item["summary"] == "人工确认客户已成交，系统已退出全部营销。"
    assert conversion_item["payload"]["conversion_action"] == "mark_enrolled"

    dispatch_item = next(item for item in items if item["event_type"] == "openclaw_dispatch")
    assert dispatch_item["summary"] == "OpenClaw 已下发转化候选 批次 #778"
    assert dispatch_item["payload"]["dispatch_payload_json"] == {"operator": "openclaw", "source": "openclaw"}


def test_timeline_marketing_event_filter_and_desc_order_keep_legacy_events(client, app):
    seed_timeline_fixture(app)
    seed_marketing_timeline_fixture(app)

    response = client.get("/api/customers/wm_timeline_001/timeline")
    items = response.get_json()["timeline"]["items"]

    assert items[0]["event_type"] == "openclaw_dispatch"
    assert "message" in [item["event_type"] for item in items]
    assert "status_change" in [item["event_type"] for item in items]

    filtered_response = client.get("/api/customers/wm_timeline_001/timeline?event_type=conversion_marked")
    filtered_items = filtered_response.get_json()["timeline"]["items"]

    assert filtered_response.status_code == 200
    assert len(filtered_items) == 1
    assert filtered_items[0]["event_type"] == "conversion_marked"
    assert filtered_items[0]["summary"] == "人工确认客户已成交，系统已退出全部营销。"
