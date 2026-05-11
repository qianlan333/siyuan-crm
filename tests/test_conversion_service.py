from __future__ import annotations

import json
from datetime import datetime as real_datetime

import pytest

from wecom_ability_service.db import get_db
from wecom_ability_service.services import (
    get_signup_conversion_batch,
    list_signup_conversion_batches,
    mark_enrolled,
    save_signup_conversion_config,
    unmark_enrolled,
    upsert_customer_trial_opening_fact,
)


@pytest.fixture()
def app(tmp_path):
    from tests.conftest import build_pg_test_app

    with build_pg_test_app(tmp_path, MCP_BEARER_TOKEN="mcp-token") as app:
        yield app


@pytest.fixture()
def client(app):
    return app.test_client()


def _mcp_call(client, name: str, arguments: dict[str, object]):
    return client.post(
        "/mcp",
        headers={"Authorization": "Bearer mcp-token"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
    )


def _freeze_router_time(monkeypatch, *, timestamp: str):
    from wecom_ability_service.domains.marketing_automation import service as marketing_service

    frozen = real_datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")

    class FrozenDateTime(real_datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return cls(
                    frozen.year,
                    frozen.month,
                    frozen.day,
                    frozen.hour,
                    frozen.minute,
                    frozen.second,
                )
            return cls(
                frozen.year,
                frozen.month,
                frozen.day,
                frozen.hour,
                frozen.minute,
                frozen.second,
                tzinfo=tz,
            )

    monkeypatch.setattr(marketing_service, "datetime", FrozenDateTime)


def _seed_signup_conversion_questionnaire(app, *, questionnaire_id: int = 51) -> dict[str, object]:
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO questionnaires (
                id, slug, name, title, description, is_disabled, redirect_url, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, '', false, '', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                questionnaire_id,
                f"conversion-service-{questionnaire_id}",
                "转化服务问卷",
                "转化服务问卷",
            ),
        )
        question_ids: list[int] = []
        option_ids_by_question: dict[int, list[int]] = {}
        for index in range(1, 6):
            question_id = questionnaire_id * 100 + index
            db.execute(
                """
                INSERT INTO questionnaire_questions (
                    id, questionnaire_id, type, title, required, sort_order, created_at, updated_at
                )
                VALUES (?, ?, 'single_choice', ?, true, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (question_id, questionnaire_id, f"关键问题{index}", index),
            )
            option_ids: list[int] = []
            for option_index in range(1, 3):
                option_id = question_id * 10 + option_index
                option_ids.append(option_id)
                db.execute(
                    """
                    INSERT INTO questionnaire_options (
                        id, question_id, option_text, score, tag_codes, sort_order, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, '[]', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """,
                    (option_id, question_id, f"问题{index}-选项{option_index}", option_index * 10, option_index),
                )
            question_ids.append(question_id)
            option_ids_by_question[question_id] = option_ids
        mobile_question_id = questionnaire_id * 100 + 6
        db.execute(
            """
            INSERT INTO questionnaire_questions (
                id, questionnaire_id, type, title, required, sort_order, created_at, updated_at
            )
            VALUES (?, ?, 'mobile', '手机号', true, 6, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (mobile_question_id, questionnaire_id),
        )
        db.commit()
    return {
        "questionnaire_id": questionnaire_id,
        "question_ids": question_ids,
        "option_ids_by_question": option_ids_by_question,
    }


def _save_default_signup_conversion_config(app, questionnaire_seed: dict[str, object]) -> None:
    with app.app_context():
        save_signup_conversion_config(
            {
                "enabled": True,
                "questionnaire_id": int(questionnaire_seed["questionnaire_id"]),
                "core_threshold": 3,
                "top_threshold": 4,
                "quiet_hour_start": 23,
                "timezone": "Asia/Shanghai",
                "question_rules": [
                    {
                        "questionnaire_question_id": question_id,
                        "hit_option_ids_json": [questionnaire_seed["option_ids_by_question"][question_id][0]],
                        "sort_order": index,
                    }
                    for index, question_id in enumerate(questionnaire_seed["question_ids"], start=1)
                ],
            }
        )


def _create_questionnaire_submission(
    app,
    questionnaire_seed: dict[str, object],
    *,
    submission_id: int,
    external_userid: str,
    mobile_snapshot: str,
    hit_question_count: int,
    submitted_at: str,
):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO questionnaire_submissions (
                id, questionnaire_id, respondent_key, external_userid, mobile_snapshot, total_score, final_tags, redirect_url_snapshot, submitted_at
            )
            VALUES (?, ?, ?, ?, ?, ?, '[]', '', ?)
            """,
            (
                submission_id,
                int(questionnaire_seed["questionnaire_id"]),
                f"resp-{submission_id}",
                external_userid,
                mobile_snapshot,
                hit_question_count * 10,
                submitted_at,
            ),
        )
        for index, question_id in enumerate(questionnaire_seed["question_ids"], start=1):
            option_id = questionnaire_seed["option_ids_by_question"][question_id][0 if index <= hit_question_count else 1]
            db.execute(
                """
                INSERT INTO questionnaire_submission_answers (
                    submission_id, question_id, question_type, question_title_snapshot,
                    selected_option_ids, selected_option_texts_snapshot, selected_option_scores_snapshot,
                    selected_option_tags_snapshot, text_value, score_contribution, created_at
                )
                VALUES (?, ?, 'single_choice', ?, ?, '[]', '[]', '[]', '', ?, CURRENT_TIMESTAMP)
                """,
                (
                    submission_id,
                    question_id,
                    f"关键问题{index}",
                    json.dumps([option_id]),
                    10 if index <= hit_question_count else 0,
                ),
            )
        db.commit()


def _seed_bound_customer(
    app,
    *,
    external_userid: str,
    mobile: str,
    customer_name: str,
    owner_userid: str = "sales_01",
    signup_status: str = "lead",
    signup_label_name: str = "报名引流品",
    send_time: str = "2026-04-04 10:01:10",
):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO owner_role_map (userid, display_name, role, active, updated_at)
            VALUES (?, ?, 'sales', true, CURRENT_TIMESTAMP)
            ON CONFLICT DO NOTHING
            """,
            (owner_userid, owner_userid),
        )
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
            VALUES (?, ?, ?, '', '', CURRENT_TIMESTAMP)
            """,
            (external_userid, customer_name, owner_userid),
        )
        db.execute(
            """
            INSERT INTO people (mobile, third_party_user_id, created_at, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (mobile, f"tp-{external_userid}"),
        )
        person_id = db.execute("SELECT id FROM people WHERE mobile = ?", (mobile,)).fetchone()["id"]
        db.execute(
            """
            INSERT INTO external_contact_bindings (
                external_userid, person_id, first_bound_by_userid, first_owner_userid, last_owner_userid, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (external_userid, person_id, owner_userid, owner_userid, owner_userid),
        )
        db.execute(
            """
            INSERT INTO class_user_status_current (
                external_userid, signup_status, signup_label_name, customer_name_snapshot, owner_userid_snapshot,
                mobile_snapshot, set_by_userid, set_at, wecom_tag_sync_status, wecom_tag_sync_error, status_flags_json,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, 'success', '', '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (external_userid, signup_status, signup_label_name, customer_name, owner_userid, mobile, owner_userid),
        )
        db.execute(
            """
            INSERT INTO archived_messages
            (seq, msgid, chat_type, external_userid, owner_userid, sender, receiver, msgtype, content, send_time, raw_payload)
            VALUES (1, ?, 'private', ?, ?, ?, ?, 'text', ?, ?, ?)
            """,
            (
                f"{external_userid}-msg-1",
                external_userid,
                owner_userid,
                external_userid,
                owner_userid,
                "老师我想了解课程",
                send_time,
                json.dumps({"decrypted_message": {"from": external_userid, "tolist": [owner_userid], "roomid": ""}}, ensure_ascii=False),
            ),
        )
        db.commit()


def _seed_activation_source(app, *, mobile: str, updated_at: str = "2026-04-04 09:00:00"):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO user_ops_huangxiaocan_activation_source (
                mobile, activation_state, import_batch_id, created_by, is_active, created_at, updated_at
            )
            VALUES (?, 'activated', 'batch-seed', 'seed', true, ?, ?)
            """,
            (mobile, updated_at, updated_at),
        )
        db.commit()


def _seed_trial_opening_fact(
    app,
    *,
    mobile: str,
    external_userid: str,
    customer_name: str,
    owner_userid: str = "sales_01",
    opened_at: str = "2026-04-04 09:00:00",
):
    with app.app_context():
        upsert_customer_trial_opening_fact(
            mobile=mobile,
            external_userid=external_userid,
            customer_name=customer_name,
            owner_userid=owner_userid,
            source="test_seed",
            opened_at=opened_at,
        )
        get_db().commit()


def _remove_live_external_facts(app, *, external_userid: str):
    with app.app_context():
        db = get_db()
        db.execute("DELETE FROM contacts WHERE external_userid = ?", (external_userid,))
        db.execute("DELETE FROM external_contact_bindings WHERE external_userid = ?", (external_userid,))
        db.execute("DELETE FROM user_ops_lead_pool_current WHERE external_userid = ?", (external_userid,))
        db.execute("DELETE FROM wecom_external_contact_identity_map WHERE external_userid = ?", (external_userid,))
        db.execute("DELETE FROM wecom_external_contact_follow_users WHERE external_userid = ?", (external_userid,))
        db.commit()


def test_mark_enrolled_cancels_pending_candidate_and_unmark_recomputes_to_activated(app, monkeypatch):
    _freeze_router_time(monkeypatch, timestamp="2026-04-04 10:30:00")
    questionnaire_seed = _seed_signup_conversion_questionnaire(app, questionnaire_id=51)
    _save_default_signup_conversion_config(app, questionnaire_seed)
    _seed_bound_customer(
        app,
        external_userid="wm_conv_task05",
        mobile="13800139001",
        customer_name="转化候选客户",
    )
    _seed_trial_opening_fact(
        app,
        mobile="13800139001",
        external_userid="wm_conv_task05",
        customer_name="转化候选客户",
        opened_at="2026-04-04 10:02:00",
    )
    _seed_activation_source(app, mobile="13800139001")
    _create_questionnaire_submission(
        app,
        questionnaire_seed,
        submission_id=5101,
        external_userid="wm_conv_task05",
        mobile_snapshot="13800139001",
        hit_question_count=4,
        submitted_at="2026-04-04 10:02:00",
    )

    with app.app_context():
        batches = list_signup_conversion_batches(limit=10)
        assert batches["count"] == 1
        batch_id = batches["items"][0]["id"]

        before = get_signup_conversion_batch(batch_id)
        assert before is not None
        assert [item["external_userid"] for item in before["candidates"]] == ["wm_conv_task05"]

        marked = mark_enrolled(
            external_userid="wm_conv_task05",
            owner_userid="sales_01",
            operator="sales_01",
            source="sidebar_manual",
        )
        assert marked["marketing_state"]["stage_key"] == "converted/enrolled"
        assert marked["cancelled_dispatch_count"] == 1
        assert marked["pending_candidate_batch_ids"] == [batch_id]
        assert marked["source"] == "sidebar_manual"

        after = get_signup_conversion_batch(batch_id)
        assert after is not None
        assert after["candidate_count"] == 0
        assert after["candidates"] == []
        assert after["skipped_customers"] == [
            {"external_userid": "wm_conv_task05", "reason": "enrolled"}
        ]

        dispatch_row = get_db().execute(
            """
            SELECT dispatch_status, dispatch_payload_json
            FROM conversion_dispatch_log
            WHERE batch_id = ? AND external_userid = ?
            """,
            (batch_id, "wm_conv_task05"),
        ).fetchone()
        assert dispatch_row["dispatch_status"] == "converted_before_dispatch"
        dispatch_payload = (dispatch_row["dispatch_payload_json"] if isinstance(dispatch_row["dispatch_payload_json"], (dict, list)) else json.loads(dispatch_row["dispatch_payload_json"]))
        assert dispatch_payload["source"] == "sidebar_manual"
        assert dispatch_payload["action"] == "mark_enrolled"

        unmarked = unmark_enrolled(
            external_userid="wm_conv_task05",
            owner_userid="sales_01",
            operator="sales_01",
            source="sidebar_manual",
        )
        assert unmarked["class_user_status"]["signup_status"] == "lead"
        assert unmarked["marketing_state"]["stage_key"] == "pool/active_focus"
        assert unmarked["marketing_state"]["converted"] is False


def test_unmark_enrolled_recomputes_to_wecom_connected_without_activation(app, monkeypatch):
    _freeze_router_time(monkeypatch, timestamp="2026-04-04 10:30:00")
    _seed_bound_customer(
        app,
        external_userid="wm_conv_task05_wecom",
        mobile="13800139003",
        customer_name="回退到已加微",
    )

    with app.app_context():
        marked = mark_enrolled(
            external_userid="wm_conv_task05_wecom",
            owner_userid="sales_01",
            operator="sales_01",
            source="sidebar_manual",
        )
        assert marked["marketing_state"]["stage_key"] == "converted/enrolled"

        unmarked = unmark_enrolled(
            external_userid="wm_conv_task05_wecom",
            owner_userid="sales_01",
            operator="sales_01",
            source="sidebar_manual",
        )
        assert unmarked["class_user_status"]["signup_status"] == "lead"
        assert unmarked["marketing_state"]["stage_key"] == "pool/new_user"


def test_unmark_enrolled_recomputes_to_mobile_only_without_live_external_facts(app):
    _seed_bound_customer(
        app,
        external_userid="wm_conv_task05_mobile_only",
        mobile="13800139004",
        customer_name="回退到手机号线索",
    )

    with app.app_context():
        marked = mark_enrolled(
            external_userid="wm_conv_task05_mobile_only",
            owner_userid="sales_01",
            operator="sales_01",
            source="sidebar_manual",
        )
        assert marked["marketing_state"]["stage_key"] == "converted/enrolled"

    _remove_live_external_facts(app, external_userid="wm_conv_task05_mobile_only")

    with app.app_context():
        unmarked = unmark_enrolled(
            external_userid="wm_conv_task05_mobile_only",
            owner_userid="sales_01",
            operator="sales_01",
            source="sidebar_manual",
        )
        assert unmarked["class_user_status"]["signup_status"] == "lead"
        assert unmarked["marketing_state"]["stage_key"] == "pool/new_user"
        assert unmarked["marketing_state"]["external_userid"] == ""


def test_unmark_enrolled_without_restore_status_does_not_default_class_user_to_lead(app, monkeypatch):
    _freeze_router_time(monkeypatch, timestamp="2026-04-04 10:30:00")
    _seed_bound_customer(
        app,
        external_userid="wm_conv_task05_no_restore",
        mobile="13800139005",
        customer_name="无历史回退客户",
        signup_status="signed_999",
        signup_label_name="已报名999",
    )

    with app.app_context():
        unmarked = unmark_enrolled(
            external_userid="wm_conv_task05_no_restore",
            owner_userid="sales_01",
            operator="sales_01",
            source="sidebar_manual",
        )
        assert unmarked["class_user_status"] == {}
        assert unmarked["signup_status"] == ""
        assert unmarked["marketing_state"]["stage_key"] == "pool/new_user"


def test_mcp_mark_and_unmark_enrolled_tools_use_unified_conversion_service(app, client, monkeypatch):
    _freeze_router_time(monkeypatch, timestamp="2026-04-04 10:30:00")
    _seed_bound_customer(
        app,
        external_userid="wm_conv_mcp_001",
        mobile="13800139002",
        customer_name="MCP转化客户",
    )
    _seed_activation_source(app, mobile="13800139002", updated_at="2026-04-04 09:30:00")

    tools_response = client.post(
        "/mcp",
        headers={"Authorization": "Bearer mcp-token"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    tool_names = {tool["name"] for tool in tools_response.get_json()["result"]["tools"]}
    assert "mark_enrolled" in tool_names
    assert "unmark_enrolled" in tool_names

    marked = _mcp_call(
        client,
        "mark_enrolled",
        {"external_userid": "wm_conv_mcp_001", "owner_userid": "sales_01"},
    ).get_json()["result"]["structuredContent"]
    assert marked["source"] == "mcp"
    assert marked["marketing_state"]["stage_key"] == "converted/enrolled"
    assert marked["marketing_state"]["state_payload"]["manual_conversion_source"] == "mcp"

    unmarked = _mcp_call(
        client,
        "unmark_enrolled",
        {"external_userid": "wm_conv_mcp_001", "owner_userid": "sales_01"},
    ).get_json()["result"]["structuredContent"]
    assert unmarked["source"] == "mcp"
    assert unmarked["class_user_status"]["signup_status"] == "lead"
    assert unmarked["marketing_state"]["stage_key"] == "pool/new_user"


def test_mcp_record_conversion_feedback_mark_enrolled_matches_manual_mark(app, client, monkeypatch):
    _freeze_router_time(monkeypatch, timestamp="2026-04-04 10:30:00")
    questionnaire_seed = _seed_signup_conversion_questionnaire(app, questionnaire_id=61)
    _save_default_signup_conversion_config(app, questionnaire_seed)
    _seed_bound_customer(
        app,
        external_userid="wm_conv_feedback_manual",
        mobile="13800139011",
        customer_name="手工回写客户",
    )
    _seed_bound_customer(
        app,
        external_userid="wm_conv_feedback_mcp",
        mobile="13800139012",
        customer_name="MCP回写客户",
    )
    _seed_trial_opening_fact(
        app,
        mobile="13800139011",
        external_userid="wm_conv_feedback_manual",
        customer_name="手工回写客户",
        opened_at="2026-04-04 10:02:00",
    )
    _seed_trial_opening_fact(
        app,
        mobile="13800139012",
        external_userid="wm_conv_feedback_mcp",
        customer_name="MCP回写客户",
        opened_at="2026-04-04 10:03:00",
    )
    _create_questionnaire_submission(
        app,
        questionnaire_seed,
        submission_id=6101,
        external_userid="wm_conv_feedback_manual",
        mobile_snapshot="13800139011",
        hit_question_count=4,
        submitted_at="2026-04-04 10:02:00",
    )
    _create_questionnaire_submission(
        app,
        questionnaire_seed,
        submission_id=6102,
        external_userid="wm_conv_feedback_mcp",
        mobile_snapshot="13800139012",
        hit_question_count=4,
        submitted_at="2026-04-04 10:03:00",
    )

    with app.app_context():
        batches = list_signup_conversion_batches(limit=10)
        assert batches["count"] == 1
        batch_id = batches["items"][0]["id"]
        before = get_signup_conversion_batch(batch_id)
        assert before is not None
        assert {item["external_userid"] for item in before["candidates"]} == {
            "wm_conv_feedback_manual",
            "wm_conv_feedback_mcp",
        }

        manual_marked = mark_enrolled(
            external_userid="wm_conv_feedback_manual",
            owner_userid="sales_01",
            operator="sales_01",
            source="sidebar_manual",
        )

    feedback_marked = _mcp_call(
        client,
        "record_conversion_feedback",
        {
            "feedback_type": "mark_enrolled",
            "external_userid": "wm_conv_feedback_mcp",
            "actor": "openclaw",
            "feedback_payload": {"owner_userid": "sales_01"},
        },
    ).get_json()["result"]["structuredContent"]

    assert feedback_marked["feedback_id"] > 0
    assert feedback_marked["conversion_result"]["marketing_state"]["stage_key"] == manual_marked["marketing_state"]["stage_key"] == "converted/enrolled"
    assert feedback_marked["conversion_result"]["class_user_status"]["signup_status"] == manual_marked["class_user_status"]["signup_status"] == "signed_999"
    assert feedback_marked["conversion_result"]["cancelled_dispatch_count"] == manual_marked["cancelled_dispatch_count"] == 1

    with app.app_context():
        manual_row = get_db().execute(
            """
            SELECT dispatch_status
            FROM conversion_dispatch_log
            WHERE batch_id = ? AND external_userid = ?
            """,
            (batch_id, "wm_conv_feedback_manual"),
        ).fetchone()
        mcp_row = get_db().execute(
            """
            SELECT dispatch_status
            FROM conversion_dispatch_log
            WHERE batch_id = ? AND external_userid = ?
            """,
            (batch_id, "wm_conv_feedback_mcp"),
        ).fetchone()
        assert manual_row["dispatch_status"] == "converted_before_dispatch"
        assert mcp_row["dispatch_status"] == "converted_before_dispatch"
