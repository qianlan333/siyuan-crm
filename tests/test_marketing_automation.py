from __future__ import annotations

import base64
import json
from datetime import datetime as real_datetime
from datetime import timedelta, timezone

import pytest
import requests

from wecom_ability_service.db import get_db
from wecom_ability_service.services import (
    evaluate_customer_marketing_state,
    insert_archived_messages,
    upsert_customer_trial_opening_fact,
)
from wecom_ability_service.domains.marketing_automation._repo_helpers import (
    _normalize_bool,
    _normalize_int,
    _normalized_json_text_list,
)


class _WebhookResponse:
    def __init__(self, status_code: int = 200, text: str = ""):
        self.status_code = status_code
        self.text = text


def _test_image_data_url(label: str = "img") -> str:
    encoded = base64.b64encode(f"fake-image-{label}".encode("utf-8")).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def test_marketing_normalizers_are_shared_package_helpers():
    assert _normalize_bool("", default=True) is True
    assert _normalize_bool("yes") is True
    assert _normalize_bool("off") is False
    assert _normalize_int("", "limit", default=3) == 3
    assert _normalize_int("5", "limit", minimum=1, maximum=9) == 5
    with pytest.raises(ValueError, match="limit must be <= 9"):
        _normalize_int(10, "limit", maximum=9)
    assert _normalized_json_text_list('[" wm_a ", "", null, "wm_b"]') == ["wm_a", "wm_b"]
    assert _normalized_json_text_list([" wm_c ", "", None]) == ["wm_c"]
    assert _normalized_json_text_list("not-json") == []


@pytest.fixture()
def app(tmp_path):
    """PG-only：用顶层 build_pg_test_app helper 起 app（2026-05 砍 SQLite 后改造）。"""
    from tests.conftest import build_pg_test_app

    with build_pg_test_app(
        tmp_path,
        MCP_BEARER_TOKEN="mcp-token",
        AUTOMATION_INTERNAL_API_TOKEN="internal-token",
    ) as app:
        yield app


@pytest.fixture()
def client(app):
    client = app.test_client()
    with client.session_transaction() as session:
        session["admin_session_user_id"] = 0
        session["admin_session_wecom_userid"] = ""
        session["admin_session_role_list"] = ["super_admin"]
        session["admin_session_login_type"] = "break_glass"
        session["admin_session_display_name"] = "test-admin"
        session["admin_session_break_glass_username"] = "test-admin"
    return client


def _seed_customer(
    app,
    *,
    external_userid: str,
    mobile: str,
    customer_name: str,
    owner_userid: str,
    signup_status: str,
    signup_label_name: str,
    add_questionnaire: bool = False,
    messages: list[tuple[str, str, str]] | None = None,
):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO owner_role_map (userid, display_name, role, active)
            VALUES (?, ?, ?, ?)
            ON CONFLICT DO NOTHING
            """,
            (owner_userid, owner_userid, "sales", True),
        )
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (external_userid, customer_name, owner_userid, f"{customer_name}备注", external_userid),
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
                mobile_snapshot, set_by_userid, set_at, wecom_tag_sync_status, wecom_tag_sync_error, status_flags_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?)
            """,
            (external_userid, signup_status, signup_label_name, customer_name, owner_userid, mobile, owner_userid, "success", "", "{}"),
        )
        if add_questionnaire:
            db.execute(
                """
                INSERT INTO questionnaires (id, slug, name, title, description, is_disabled, redirect_url)
                VALUES (1, 'marketing-auto', '自动化问卷', '自动化问卷', '', false, '')
                ON CONFLICT DO NOTHING
                """
            )
            db.execute(
                """
                INSERT INTO questionnaire_submissions (
                    questionnaire_id, respondent_key, openid, unionid, external_userid, follow_user_userid,
                    matched_by, mobile_snapshot, total_score, final_tags, redirect_url_snapshot, submitted_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    1,
                    f"resp-{external_userid}",
                    f"openid-{external_userid}",
                    f"union-{external_userid}",
                    external_userid,
                    owner_userid,
                    "external_userid",
                    mobile,
                    88,
                    "[]",
                    "",
                    "2026-04-04 09:58:00",
                ),
            )
        for index, (sender, content, send_time) in enumerate(messages or [], start=1):
            receiver = owner_userid if sender == external_userid else external_userid
            db.execute(
                """
                INSERT INTO archived_messages
                (seq, msgid, chat_type, external_userid, owner_userid, sender, receiver, msgtype, content, send_time, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    index,
                    f"{external_userid}-msg-{index}",
                    "private",
                    external_userid,
                    owner_userid,
                    sender,
                    receiver,
                    "text",
                    content,
                    send_time,
                    json.dumps({"decrypted_message": {"from": sender, "tolist": [receiver], "roomid": ""}}, ensure_ascii=False),
                ),
            )
        db.commit()


def _mcp_call(client, name: str, arguments: dict):
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


def _internal_headers() -> dict[str, str]:
    return {"Authorization": "Bearer internal-token"}


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


def _save_default_signup_conversion_config(client, app, *, questionnaire_id: int) -> dict[str, object]:
    seed = _seed_signup_conversion_questionnaire(app, questionnaire_id=questionnaire_id)
    response = client.put("/api/admin/marketing-automation/config", json=_signup_conversion_config_payload(seed))
    assert response.status_code == 200
    return seed


def _seed_marketing_fixture(app):
    _seed_customer(
        app,
        external_userid="wm_conv_001",
        mobile="13800138001",
        customer_name="候选客户",
        owner_userid="sales_01",
        signup_status="lead",
        signup_label_name="报名引流品",
        add_questionnaire=True,
        messages=[
            ("wm_conv_001", "老师我想了解课程", "2026-04-04 10:01:10"),
            ("sales_01", "好的，我发你课程安排", "2026-04-04 10:01:20"),
        ],
    )
    _seed_customer(
        app,
        external_userid="wm_conv_002",
        mobile="13800138002",
        customer_name="已报名客户",
        owner_userid="sales_01",
        signup_status="signed_999",
        signup_label_name="已报名999",
        messages=[("wm_conv_002", "我已经报名了", "2026-04-04 10:01:30")],
    )
    _seed_customer(
        app,
        external_userid="wm_conv_003",
        mobile="13800138003",
        customer_name="深夜客户",
        owner_userid="sales_01",
        signup_status="lead",
        signup_label_name="报名引流品",
        messages=[("wm_conv_003", "晚上再聊", "2026-04-04 23:05:10")],
    )


def _seed_signup_conversion_questionnaire(
    app,
    *,
    questionnaire_id: int = 11,
    question_count: int = 5,
) -> dict[str, object]:
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO questionnaires (
                id, slug, name, title, description, is_disabled, redirect_url, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, false, '', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                questionnaire_id,
                f"signup-conv-{questionnaire_id}",
                "自动化转化初判问卷",
                "自动化转化初判问卷",
                "",
            ),
        )
        question_ids: list[int] = []
        option_ids_by_question: dict[int, list[int]] = {}
        for index in range(1, question_count + 1):
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
                    (
                        option_id,
                        question_id,
                        f"问题{index}-选项{option_index}",
                        option_index * 10,
                        option_index,
                    ),
                )
            question_ids.append(question_id)
            option_ids_by_question[question_id] = option_ids
        mobile_question_id = questionnaire_id * 100 + question_count + 1
        db.execute(
            """
            INSERT INTO questionnaire_questions (
                id, questionnaire_id, type, title, required, sort_order, created_at, updated_at
            )
            VALUES (?, ?, 'mobile', '手机号', true, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (mobile_question_id, questionnaire_id, question_count + 1),
        )
        db.commit()
    return {
        "questionnaire_id": questionnaire_id,
        "question_ids": question_ids,
        "option_ids_by_question": option_ids_by_question,
        "mobile_question_id": mobile_question_id,
    }


def _seed_signup_conversion_questionnaire_without_required_mobile(app, *, questionnaire_id: int = 31) -> dict[str, object]:
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO questionnaires (
                id, slug, name, title, description, is_disabled, redirect_url, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, false, '', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                questionnaire_id,
                f"signup-conv-no-mobile-{questionnaire_id}",
                "无手机号题问卷",
                "无手机号题问卷",
                "",
            ),
        )
        question_id = questionnaire_id * 100 + 1
        option_base = question_id * 10
        db.execute(
            """
            INSERT INTO questionnaire_questions (
                id, questionnaire_id, type, title, required, sort_order, created_at, updated_at
            )
            VALUES (?, ?, 'single_choice', '关键问题1', true, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (question_id, questionnaire_id),
        )
        db.execute(
            """
            INSERT INTO questionnaire_options (
                id, question_id, option_text, score, tag_codes, sort_order, created_at, updated_at
            )
            VALUES (?, ?, '选项1', 10, '[]', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (option_base + 1, question_id),
        )
        db.execute(
            """
            INSERT INTO questionnaire_options (
                id, question_id, option_text, score, tag_codes, sort_order, created_at, updated_at
            )
            VALUES (?, ?, '选项2', 20, '[]', 2, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (option_base + 2, question_id),
        )
        db.commit()
    return {
        "questionnaire_id": questionnaire_id,
        "question_ids": [question_id],
        "option_ids_by_question": {question_id: [option_base + 1, option_base + 2]},
    }


def _create_questionnaire_submission(
    app,
    questionnaire_seed: dict[str, object],
    *,
    submission_id: int,
    external_userid: str,
    mobile_snapshot: str,
    hit_question_count: int,
    submitted_at: str,
    trial_opened: bool = True,
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
        if trial_opened:
            contact_row = db.execute(
                """
                SELECT customer_name, owner_userid
                FROM contacts
                WHERE external_userid = ?
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                (external_userid,),
            ).fetchone()
            upsert_customer_trial_opening_fact(
                mobile=mobile_snapshot,
                external_userid=external_userid,
                customer_name=str((contact_row or {}).get("customer_name") or external_userid),
                owner_userid=str((contact_row or {}).get("owner_userid") or "sales_01"),
                source="test_seed",
                opened_at=submitted_at,
            )
        db.commit()


def _seed_activation_source(app, *, mobile: str, updated_at: str):
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


def _persist_marketing_state(app, *, external_userid: str) -> dict[str, object]:
    with app.app_context():
        return evaluate_customer_marketing_state(external_userid=external_userid)


def _signup_conversion_config_payload(
    questionnaire_seed: dict[str, object],
    *,
    enabled: bool = True,
    core_threshold: int = 3,
    top_threshold: int = 4,
    day_start_hour: int = 9,
    quiet_hour_start: int = 23,
    timezone: str = "Asia/Shanghai",
    question_ids: list[int] | None = None,
    hit_option_ids_by_question: dict[int, list[int]] | None = None,
    silent_threshold_days_by_pool: dict[str, int] | None = None,
) -> dict[str, object]:
    selected_question_ids = list(question_ids or questionnaire_seed["question_ids"])
    option_ids_by_question = dict(questionnaire_seed["option_ids_by_question"])
    return {
        "enabled": enabled,
        "questionnaire_id": int(questionnaire_seed["questionnaire_id"]),
        "core_threshold": core_threshold,
        "top_threshold": top_threshold,
        "day_start_hour": day_start_hour,
        "quiet_hour_start": quiet_hour_start,
        "timezone": timezone,
        "silent_threshold_days_by_pool": silent_threshold_days_by_pool
        or {
            "new_user": 7,
            "inactive_normal": 7,
            "inactive_focus": 7,
            "active_normal": 7,
            "active_focus": 7,
        },
        "question_rules": [
            {
                "questionnaire_question_id": question_id,
                "hit_option_ids_json": list(
                    hit_option_ids_by_question.get(question_id, [option_ids_by_question[question_id][0]])
                    if hit_option_ids_by_question
                    else [option_ids_by_question[question_id][0]]
                ),
                "sort_order": index,
            }
            for index, question_id in enumerate(selected_question_ids, start=1)
        ],
    }


def test_signup_conversion_batch_api_filters_candidates_and_attaches_customer_context(app, client, monkeypatch):
    _freeze_router_time(monkeypatch, timestamp="2026-04-04 10:30:00")
    seed = _save_default_signup_conversion_config(client, app, questionnaire_id=41)
    _seed_marketing_fixture(app)
    _create_questionnaire_submission(
        app,
        seed,
        submission_id=4101,
        external_userid="wm_conv_001",
        mobile_snapshot="13800138001",
        hit_question_count=4,
        submitted_at="2026-04-04 10:02:00",
    )

    list_response = client.get("/api/customers/automation/signup-conversion/batches")
    list_payload = list_response.get_json()

    assert list_response.status_code == 200
    assert list_payload["ok"] is True
    assert list_payload["automation_batches"]["count"] == 1
    batch_preview = list_payload["automation_batches"]["items"][0]
    assert batch_preview["candidate_count"] == 1
    assert batch_preview["blocked_count"] == 0
    assert batch_preview["candidates_preview"][0]["external_userid"] == "wm_conv_001"
    assert batch_preview["candidates_preview"][0]["value_segment"] == "focus"
    assert batch_preview["candidates_preview"][0]["current_stage"] == "pool/inactive_focus"
    assert batch_preview["candidates_preview"][0]["dispatch_status"] == "pending"

    detail_response = client.get(f"/api/customers/automation/signup-conversion/batches/{batch_preview['id']}")
    detail_payload = detail_response.get_json()["automation_batch"]
    candidate = detail_payload["candidates"][0]

    assert detail_response.status_code == 200
    assert detail_payload["candidate_count"] == 1
    assert detail_payload["blocked_count"] == 0
    assert candidate["external_userid"] == "wm_conv_001"
    assert candidate["current_stage"] == "pool/inactive_focus"
    assert candidate["current_segment"] == "focus"
    assert candidate["dispatch_status"] == "pending"
    assert candidate["customer_context"]["external_userid"] == "wm_conv_001"
    assert candidate["customer_context"]["customer"]["marketing_profile"]["marketing_state"]["marketing_phase"] == "awaiting_trigger"
    assert candidate["customer_context"]["customer"]["marketing_profile"]["value_segment"]["value_segment"] == "focus"
    assert isinstance(candidate["customer_context"]["recent_messages"], list)
    assert candidate["customer_context"]["timeline"]["external_userid"] == "wm_conv_001"
    assert candidate["customer_context"]["recent_timeline_events"] == candidate["customer_context"]["timeline"]["items"]
    assert detail_payload["skipped_count"] == 1

    signed_detail = client.get("/api/customers/wm_conv_002").get_json()["customer"]
    assert signed_detail["marketing_profile"]["marketing_state"]["marketing_phase"] == "exited_signup_success"


def test_signup_conversion_batch_mcp_tools_return_filtered_profiles(app, client, monkeypatch):
    _freeze_router_time(monkeypatch, timestamp="2026-04-04 10:30:00")
    seed = _save_default_signup_conversion_config(client, app, questionnaire_id=42)
    _seed_marketing_fixture(app)
    _create_questionnaire_submission(
        app,
        seed,
        submission_id=4201,
        external_userid="wm_conv_001",
        mobile_snapshot="13800138001",
        hit_question_count=4,
        submitted_at="2026-04-04 10:03:00",
    )

    tools_response = client.post(
        "/mcp",
        headers={"Authorization": "Bearer mcp-token"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    tool_names = {tool["name"] for tool in tools_response.get_json()["result"]["tools"]}
    tool_defs = {tool["name"]: tool for tool in tools_response.get_json()["result"]["tools"]}
    assert "get_customer_marketing_profile" in tool_names
    assert "get_pending_conversion_batches" in tool_names
    assert "get_conversion_batch" in tool_names
    assert "ack_conversion_batch" in tool_names
    assert "get_signup_conversion_batches" in tool_names
    assert "get_signup_conversion_batch" in tool_names
    assert "send_pool_private_message" in tool_names
    pool_send_schema = tool_defs["send_pool_private_message"]["inputSchema"]
    assert "images" in pool_send_schema["properties"]
    assert "image_media_ids" in pool_send_schema["properties"]
    assert "attachments" in pool_send_schema["properties"]
    assert pool_send_schema["required"] == ["owner_userid", "pool_key", "confirm"]

    profile_payload = _mcp_call(
        client,
        "get_customer_marketing_profile",
        {"external_userid": "wm_conv_001", "recent_message_limit": 2},
    ).get_json()["result"]["structuredContent"]
    assert profile_payload["customer"]["external_userid"] == "wm_conv_001"
    assert profile_payload["owner"]["owner_userid"] == "sales_01"
    assert profile_payload["marketing_state"]["main_stage"] == "pool"
    assert profile_payload["value_segment"]["segment"] == "focus"
    assert profile_payload["routing"]["reason"] == "eligible_by_router"
    assert profile_payload["recent_text_summary"]["latest_customer_message_summary"] == "老师我想了解课程"
    assert profile_payload["recent_text_summary"]["latest_staff_message_summary"] == "好的，我发你课程安排"
    assert profile_payload["recent_text_summary"]["sample_size"] <= 2
    assert "items" not in profile_payload["recent_text_summary"]

    batches_payload = _mcp_call(client, "get_pending_conversion_batches", {"limit": 10}).get_json()["result"]["structuredContent"]
    assert batches_payload["count"] == 1
    batch_id = batches_payload["items"][0]["batch_id"]
    assert batches_payload["items"][0]["candidates_preview"][0]["reason"] == "pending_text_message_batch"

    batch_payload = _mcp_call(client, "get_conversion_batch", {"batch_id": batch_id}).get_json()["result"]["structuredContent"]
    candidate = batch_payload["candidates"][0]

    assert batch_payload["candidate_count"] == 1
    assert candidate["external_userid"] == "wm_conv_001"
    assert candidate["dispatch_status"] == "pending"
    assert candidate["marketing_profile"]["marketing_state"]["stage_key"] == "pool/inactive_focus"
    assert candidate["marketing_profile"]["value_segment"]["is_core"] is True
    assert candidate["routing"]["reason"] == "pending_text_message_batch"


def test_mcp_customer_marketing_profile_normalizes_blank_exit_timestamp_before_upsert(app, client, monkeypatch):
    from wecom_ability_service.domains.marketing_automation import repo as marketing_repo

    _freeze_router_time(monkeypatch, timestamp="2026-04-04 10:30:00")
    seed = _save_default_signup_conversion_config(client, app, questionnaire_id=52)
    _seed_marketing_fixture(app)
    _create_questionnaire_submission(
        app,
        seed,
        submission_id=5201,
        external_userid="wm_conv_001",
        mobile_snapshot="13800138001",
        hit_question_count=4,
        submitted_at="2026-04-04 10:03:00",
        trial_opened=False,
    )

    original_upsert = marketing_repo.upsert_customer_marketing_state_current
    captured: dict[str, object] = {}

    def _capturing_upsert(**kwargs):
        captured["entered_at"] = kwargs.get("entered_at")
        captured["exited_at"] = kwargs.get("exited_at")
        return original_upsert(**kwargs)

    monkeypatch.setattr(marketing_repo, "upsert_customer_marketing_state_current", _capturing_upsert)

    profile_payload = _mcp_call(
        client,
        "get_customer_marketing_profile",
        {"external_userid": "wm_conv_001", "recent_message_limit": 2},
    ).get_json()["result"]["structuredContent"]

    assert profile_payload["customer"]["external_userid"] == "wm_conv_001"
    assert profile_payload["routing"]["reason"] == "trial_not_opened"
    assert profile_payload["marketing_state"]["stage_key"] == "pool/new_user"
    assert captured["entered_at"] == "2026-04-04 10:01:20"
    assert captured["exited_at"] is None


def test_send_pool_private_message_mcp_tool_supports_multiple_owners_and_writes_records(app, client):
    seed = _save_default_signup_conversion_config(client, app, questionnaire_id=242)
    _seed_customer(
        app,
        external_userid="wm_pool_send_new_user",
        mobile="13800138601",
        customer_name="新用户池客户",
        owner_userid="QianLan",
        signup_status="lead",
        signup_label_name="报名引流品",
    )
    _seed_customer(
        app,
        external_userid="wm_pool_send_new_user_other_owner",
        mobile="13800138611",
        customer_name="第二负责人新用户",
        owner_userid="sales_02",
        signup_status="lead",
        signup_label_name="报名引流品",
    )
    _seed_customer(
        app,
        external_userid="wm_pool_send_inactive_normal",
        mobile="13800138602",
        customer_name="未激活普通客户",
        owner_userid="QianLan",
        signup_status="lead",
        signup_label_name="报名引流品",
    )
    _create_questionnaire_submission(
        app,
        seed,
        submission_id=24201,
        external_userid="wm_pool_send_inactive_normal",
        mobile_snapshot="13800138602",
        hit_question_count=2,
        submitted_at="2026-04-05 10:00:00",
    )
    _seed_customer(
        app,
        external_userid="wm_pool_send_active_focus",
        mobile="13800138603",
        customer_name="激活重点客户",
        owner_userid="QianLan",
        signup_status="lead",
        signup_label_name="报名引流品",
    )
    _create_questionnaire_submission(
        app,
        seed,
        submission_id=24202,
        external_userid="wm_pool_send_active_focus",
        mobile_snapshot="13800138603",
        hit_question_count=4,
        submitted_at="2026-04-05 10:01:00",
    )
    _seed_customer(
        app,
        external_userid="wm_pool_send_active_focus_other_owner",
        mobile="13800138612",
        customer_name="第二负责人激活重点客户",
        owner_userid="sales_02",
        signup_status="lead",
        signup_label_name="报名引流品",
    )
    _create_questionnaire_submission(
        app,
        seed,
        submission_id=24203,
        external_userid="wm_pool_send_active_focus_other_owner",
        mobile_snapshot="13800138612",
        hit_question_count=4,
        submitted_at="2026-04-05 10:03:00",
    )
    _seed_activation_source(app, mobile="13800138603", updated_at="2026-04-05 10:02:00")
    _seed_activation_source(app, mobile="13800138612", updated_at="2026-04-05 10:04:00")

    with app.app_context():
        get_db().execute(
            """
            INSERT INTO owner_role_map (userid, display_name, role, active, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT DO NOTHING
            """,
            ("sales_empty", "sales_empty", "sales", True),
        )
        get_db().commit()

    assert _persist_marketing_state(app, external_userid="wm_pool_send_new_user")["stage_key"] == "pool/new_user"
    assert _persist_marketing_state(app, external_userid="wm_pool_send_new_user_other_owner")["stage_key"] == "pool/new_user"
    assert _persist_marketing_state(app, external_userid="wm_pool_send_inactive_normal")["stage_key"] == "pool/inactive_normal"
    assert _persist_marketing_state(app, external_userid="wm_pool_send_active_focus")["stage_key"] == "pool/active_focus"
    assert _persist_marketing_state(app, external_userid="wm_pool_send_active_focus_other_owner")["stage_key"] == "pool/active_focus"

    dispatched_payloads: list[dict[str, object]] = []

    def fake_dispatch(task_type: str, fn_name: str, payload: dict[str, object]) -> dict[str, object]:
        dispatched_payloads.append(
            {
                "task_type": task_type,
                "fn_name": fn_name,
                "payload": dict(payload),
            }
        )
        return {
            "task_id": len(dispatched_payloads),
            "wecom_result": {"msgid": f"msg-{len(dispatched_payloads)}"},
        }

    with app.app_context():
        from wecom_ability_service.domains.marketing_automation import service as marketing_service

        original_dispatch = marketing_service.dispatch_wecom_task
        marketing_service.dispatch_wecom_task = fake_dispatch
        try:
            new_user_payload = _mcp_call(
                client,
                "send_pool_private_message",
                {"owner_userid": "QianLan", "pool_key": "new_user", "content": "欢迎添加，我们先发你问卷。", "confirm": True},
            ).get_json()["result"]["structuredContent"]
            second_owner_new_user_payload = _mcp_call(
                client,
                "send_pool_private_message",
                {"owner_userid": "sales_02", "pool_key": "new_user", "content": "第二负责人新用户触达。", "confirm": True},
            ).get_json()["result"]["structuredContent"]
            inactive_normal_payload = _mcp_call(
                client,
                "send_pool_private_message",
                {"owner_userid": "QianLan", "pool_key": "inactive_normal", "content": "试用已经开通，先按标准话术跟进。", "confirm": True},
            ).get_json()["result"]["structuredContent"]
            active_focus_payload = _mcp_call(
                client,
                "send_pool_private_message",
                {"owner_userid": "QianLan", "pool_key": "active_focus", "content": "你已经激活，我们安排重点跟进。", "confirm": True},
            ).get_json()["result"]["structuredContent"]
            second_owner_active_focus_payload = _mcp_call(
                client,
                "send_pool_private_message",
                {"owner_userid": "sales_02", "pool_key": "active_focus", "content": "第二负责人重点激活触达。", "confirm": True},
            ).get_json()["result"]["structuredContent"]
            empty_owner_payload = _mcp_call(
                client,
                "send_pool_private_message",
                {"owner_userid": "sales_empty", "pool_key": "new_user", "content": "空池子不应发送。", "confirm": True},
            ).get_json()["result"]["structuredContent"]
            silent_response = _mcp_call(
                client,
                "send_pool_private_message",
                {"owner_userid": "QianLan", "pool_key": "silent", "content": "沉默池不应允许发送", "confirm": True},
            )
        finally:
            marketing_service.dispatch_wecom_task = original_dispatch

    assert new_user_payload["pool_key"] == "new_user"
    assert new_user_payload["matched_count"] == 1
    assert new_user_payload["sendable_count"] == 1
    assert new_user_payload["skipped_count"] == 0
    assert int(new_user_payload["record_id"]) > 0

    assert second_owner_new_user_payload["owner_userid"] == "sales_02"
    assert second_owner_new_user_payload["matched_count"] == 1
    assert second_owner_new_user_payload["sendable_count"] == 1
    assert second_owner_new_user_payload["skipped_count"] == 0
    assert int(second_owner_new_user_payload["record_id"]) > 0

    assert inactive_normal_payload["pool_key"] == "inactive_normal"
    assert inactive_normal_payload["matched_count"] == 1
    assert inactive_normal_payload["sendable_count"] == 1
    assert inactive_normal_payload["skipped_count"] == 0
    assert int(inactive_normal_payload["record_id"]) > 0

    assert active_focus_payload["pool_key"] == "active_focus"
    assert active_focus_payload["matched_count"] == 1
    assert active_focus_payload["sendable_count"] == 1
    assert active_focus_payload["skipped_count"] == 0
    assert int(active_focus_payload["record_id"]) > 0

    assert second_owner_active_focus_payload["owner_userid"] == "sales_02"
    assert second_owner_active_focus_payload["matched_count"] == 1
    assert second_owner_active_focus_payload["sendable_count"] == 1
    assert second_owner_active_focus_payload["skipped_count"] == 0
    assert int(second_owner_active_focus_payload["record_id"]) > 0

    assert empty_owner_payload["owner_userid"] == "sales_empty"
    assert empty_owner_payload["matched_count"] == 0
    assert empty_owner_payload["sendable_count"] == 0
    assert empty_owner_payload["skipped_count"] == 0
    assert empty_owner_payload["record_id"] is None
    assert empty_owner_payload["status"] == "empty"
    assert empty_owner_payload["empty_reason"] == "no_customers_in_pool_for_owner"

    error_payload = silent_response.get_json()["error"]
    assert silent_response.status_code == 200
    assert error_payload["message"] == "silent pool is record-only and does not support batch send"

    assert [item["payload"]["external_userid"] for item in dispatched_payloads] == [
        ["wm_pool_send_new_user"],
        ["wm_pool_send_new_user_other_owner"],
        ["wm_pool_send_inactive_normal"],
        ["wm_pool_send_active_focus"],
        ["wm_pool_send_active_focus_other_owner"],
    ]

    with app.app_context():
        rows = get_db().execute(
            """
            SELECT id, filter_snapshot_json, selected_count, eligible_count, sent_count
            FROM user_ops_send_records
            ORDER BY id ASC
            """
        ).fetchall()
        assert len(rows) == 5
        assert (rows[0]["filter_snapshot_json"] if isinstance(rows[0]["filter_snapshot_json"], (dict, list)) else json.loads(rows[0]["filter_snapshot_json"]))["pool_key"] == "new_user"
        assert (rows[0]["filter_snapshot_json"] if isinstance(rows[0]["filter_snapshot_json"], (dict, list)) else json.loads(rows[0]["filter_snapshot_json"]))["owner_userid"] == "QianLan"
        assert (rows[1]["filter_snapshot_json"] if isinstance(rows[1]["filter_snapshot_json"], (dict, list)) else json.loads(rows[1]["filter_snapshot_json"]))["pool_key"] == "new_user"
        assert (rows[1]["filter_snapshot_json"] if isinstance(rows[1]["filter_snapshot_json"], (dict, list)) else json.loads(rows[1]["filter_snapshot_json"]))["owner_userid"] == "sales_02"
        assert (rows[2]["filter_snapshot_json"] if isinstance(rows[2]["filter_snapshot_json"], (dict, list)) else json.loads(rows[2]["filter_snapshot_json"]))["pool_key"] == "inactive_normal"
        assert (rows[3]["filter_snapshot_json"] if isinstance(rows[3]["filter_snapshot_json"], (dict, list)) else json.loads(rows[3]["filter_snapshot_json"]))["pool_key"] == "active_focus"
        assert (rows[3]["filter_snapshot_json"] if isinstance(rows[3]["filter_snapshot_json"], (dict, list)) else json.loads(rows[3]["filter_snapshot_json"]))["owner_userid"] == "QianLan"
        assert (rows[4]["filter_snapshot_json"] if isinstance(rows[4]["filter_snapshot_json"], (dict, list)) else json.loads(rows[4]["filter_snapshot_json"]))["pool_key"] == "active_focus"
        assert (rows[4]["filter_snapshot_json"] if isinstance(rows[4]["filter_snapshot_json"], (dict, list)) else json.loads(rows[4]["filter_snapshot_json"]))["owner_userid"] == "sales_02"
        assert [(row["selected_count"], row["eligible_count"], row["sent_count"]) for row in rows] == [
            (1, 1, 1),
            (1, 1, 1),
            (1, 1, 1),
            (1, 1, 1),
            (1, 1, 1),
        ]


def test_send_pool_private_message_mcp_tool_supports_images_and_keeps_records(app, client):
    _seed_customer(
        app,
        external_userid="wm_pool_send_image_qianlan",
        mobile="13800138621",
        customer_name="图片群发客户A",
        owner_userid="QianLan",
        signup_status="lead",
        signup_label_name="报名引流品",
    )
    _seed_customer(
        app,
        external_userid="wm_pool_send_image_sales02",
        mobile="13800138622",
        customer_name="图片群发客户B",
        owner_userid="sales_02",
        signup_status="lead",
        signup_label_name="报名引流品",
    )
    assert _persist_marketing_state(app, external_userid="wm_pool_send_image_qianlan")["stage_key"] == "pool/new_user"
    assert _persist_marketing_state(app, external_userid="wm_pool_send_image_sales02")["stage_key"] == "pool/new_user"

    dispatched_payloads: list[dict[str, object]] = []

    def fake_dispatch(task_type: str, fn_name: str, payload: dict[str, object]) -> dict[str, object]:
        dispatched_payloads.append({"task_type": task_type, "fn_name": fn_name, "payload": dict(payload)})
        return {
            "task_id": len(dispatched_payloads),
            "wecom_result": {"msgid": f"msg-image-{len(dispatched_payloads)}"},
        }

    with app.app_context():
        from wecom_ability_service.domains.marketing_automation import service as marketing_service

        original_dispatch = marketing_service.dispatch_wecom_task
        marketing_service.dispatch_wecom_task = fake_dispatch
        try:
            pure_image_payload = _mcp_call(
                client,
                "send_pool_private_message",
                {
                    "owner_userid": "QianLan",
                    "pool_key": "new_user",
                    "images": [{"file_name": "pool-a.png", "data_url": _test_image_data_url("pool-a")}],
                    "confirm": True,
                },
            ).get_json()["result"]["structuredContent"]
            text_with_image_payload = _mcp_call(
                client,
                "send_pool_private_message",
                {
                    "owner_userid": "sales_02",
                    "pool_key": "new_user",
                    "content": "图片和文本一起发",
                    "images": [{"file_name": "pool-b.png", "data_url": _test_image_data_url("pool-b")}],
                    "confirm": True,
                },
            ).get_json()["result"]["structuredContent"]
        finally:
            marketing_service.dispatch_wecom_task = original_dispatch

    assert pure_image_payload["owner_userid"] == "QianLan"
    assert pure_image_payload["matched_count"] == 1
    assert pure_image_payload["sendable_count"] == 1
    assert pure_image_payload["image_count"] == 1
    assert pure_image_payload["content_preview"] == ""
    assert int(pure_image_payload["record_id"]) > 0

    assert text_with_image_payload["owner_userid"] == "sales_02"
    assert text_with_image_payload["matched_count"] == 1
    assert text_with_image_payload["sendable_count"] == 1
    assert text_with_image_payload["image_count"] == 1
    assert text_with_image_payload["content_preview"] == "图片和文本一起发"
    assert int(text_with_image_payload["record_id"]) > 0

    assert [item["payload"]["external_userid"] for item in dispatched_payloads] == [
        ["wm_pool_send_image_qianlan"],
        ["wm_pool_send_image_sales02"],
    ]
    assert "text" not in dispatched_payloads[0]["payload"]
    assert len(dispatched_payloads[0]["payload"]["images"]) == 1
    assert dispatched_payloads[1]["payload"]["text"]["content"] == "图片和文本一起发"
    assert len(dispatched_payloads[1]["payload"]["images"]) == 1

    with app.app_context():
        rows = get_db().execute(
            """
            SELECT filter_snapshot_json, content_preview, image_count, selected_count, eligible_count, sent_count
            FROM user_ops_send_records
            WHERE CAST(filter_snapshot_json AS TEXT) LIKE '%%marketing_pool%%'
            ORDER BY id DESC
            LIMIT 2
            """
        ).fetchall()
        latest_rows = list(reversed(rows))
        assert len(latest_rows) == 2
        assert (latest_rows[0]["filter_snapshot_json"] if isinstance(latest_rows[0]["filter_snapshot_json"], (dict, list)) else json.loads(latest_rows[0]["filter_snapshot_json"]))["owner_userid"] == "QianLan"
        assert latest_rows[0]["content_preview"] == ""
        assert int(latest_rows[0]["image_count"]) == 1
        assert (latest_rows[0]["selected_count"], latest_rows[0]["eligible_count"], latest_rows[0]["sent_count"]) == (1, 1, 1)
        assert (latest_rows[1]["filter_snapshot_json"] if isinstance(latest_rows[1]["filter_snapshot_json"], (dict, list)) else json.loads(latest_rows[1]["filter_snapshot_json"]))["owner_userid"] == "sales_02"
        assert latest_rows[1]["content_preview"] == "图片和文本一起发"
        assert int(latest_rows[1]["image_count"]) == 1
        assert (latest_rows[1]["selected_count"], latest_rows[1]["eligible_count"], latest_rows[1]["sent_count"]) == (1, 1, 1)


def test_send_pool_private_message_mcp_tool_supports_attachments_and_keeps_records(app, client):
    _seed_customer(
        app,
        external_userid="wm_pool_send_attachment_qianlan",
        mobile="13800138631",
        customer_name="附件群发客户A",
        owner_userid="QianLan",
        signup_status="lead",
        signup_label_name="报名引流品",
    )
    _seed_customer(
        app,
        external_userid="wm_pool_send_attachment_sales02",
        mobile="13800138632",
        customer_name="附件群发客户B",
        owner_userid="sales_02",
        signup_status="lead",
        signup_label_name="报名引流品",
    )
    assert _persist_marketing_state(app, external_userid="wm_pool_send_attachment_qianlan")["stage_key"] == "pool/new_user"
    assert _persist_marketing_state(app, external_userid="wm_pool_send_attachment_sales02")["stage_key"] == "pool/new_user"

    dispatched_payloads: list[dict[str, object]] = []

    def fake_dispatch(task_type: str, fn_name: str, payload: dict[str, object]) -> dict[str, object]:
        dispatched_payloads.append({"task_type": task_type, "fn_name": fn_name, "payload": dict(payload)})
        return {
            "task_id": len(dispatched_payloads),
            "wecom_result": {"msgid": f"msg-attachment-{len(dispatched_payloads)}"},
        }

    with app.app_context():
        from wecom_ability_service.domains import attachment_library
        from wecom_ability_service.domains.marketing_automation import service as marketing_service

        library_item = attachment_library.create_attachment_from_upload(
            file_bytes=b"%PDF-1.4\n%%EOF\n",
            file_name="pool-send.pdf",
            mime_type="application/pdf",
            name="群发附件",
        )
        get_db().execute(
            """
            UPDATE attachment_library
            SET media_id = ?, media_id_expires_at = ?
            WHERE id = ?
            """,
            (
                "file-media-library-pool",
                (real_datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                library_item["id"],
            ),
        )
        get_db().commit()

        original_dispatch = marketing_service.dispatch_wecom_task
        marketing_service.dispatch_wecom_task = fake_dispatch
        try:
            pure_attachment_payload = _mcp_call(
                client,
                "send_pool_private_message",
                {
                    "owner_userid": "QianLan",
                    "pool_key": "new_user",
                    "attachment_library_ids": [library_item["id"]],
                    "confirm": True,
                },
            ).get_json()["result"]["structuredContent"]
            text_image_attachment_payload = _mcp_call(
                client,
                "send_pool_private_message",
                {
                    "owner_userid": "sales_02",
                    "pool_key": "new_user",
                    "content": "文本 + 图片 + 附件一起发",
                    "images": [{"file_name": "mix.png", "data_url": _test_image_data_url("mix")}],
                    "attachments": [{"msgtype": "file", "file": {"media_id": "file-media-b"}}],
                    "confirm": True,
                },
            ).get_json()["result"]["structuredContent"]
        finally:
            marketing_service.dispatch_wecom_task = original_dispatch

    assert pure_attachment_payload["owner_userid"] == "QianLan"
    assert pure_attachment_payload["matched_count"] == 1
    assert pure_attachment_payload["sendable_count"] == 1
    assert pure_attachment_payload["image_count"] == 0
    assert pure_attachment_payload["content_preview"] == ""
    assert int(pure_attachment_payload["record_id"]) > 0

    assert text_image_attachment_payload["owner_userid"] == "sales_02"
    assert text_image_attachment_payload["matched_count"] == 1
    assert text_image_attachment_payload["sendable_count"] == 1
    assert text_image_attachment_payload["image_count"] == 1
    assert text_image_attachment_payload["content_preview"] == "文本 + 图片 + 附件一起发"
    assert int(text_image_attachment_payload["record_id"]) > 0

    assert [item["payload"]["external_userid"] for item in dispatched_payloads] == [
        ["wm_pool_send_attachment_qianlan"],
        ["wm_pool_send_attachment_sales02"],
    ]
    assert "text" not in dispatched_payloads[0]["payload"]
    assert dispatched_payloads[0]["payload"]["attachments"] == [{"msgtype": "file", "file": {"media_id": "file-media-library-pool"}}]
    assert dispatched_payloads[1]["payload"]["text"]["content"] == "文本 + 图片 + 附件一起发"
    assert len(dispatched_payloads[1]["payload"]["images"]) == 1
    assert dispatched_payloads[1]["payload"]["attachments"] == [{"msgtype": "file", "file": {"media_id": "file-media-b"}}]

    with app.app_context():
        rows = get_db().execute(
            """
            SELECT filter_snapshot_json, content_preview, image_count, selected_count, eligible_count, sent_count
            FROM user_ops_send_records
            WHERE CAST(filter_snapshot_json AS TEXT) LIKE '%%marketing_pool%%'
            ORDER BY id DESC
            LIMIT 2
            """
        ).fetchall()
        latest_rows = list(reversed(rows))
        assert len(latest_rows) == 2
        assert (latest_rows[0]["filter_snapshot_json"] if isinstance(latest_rows[0]["filter_snapshot_json"], (dict, list)) else json.loads(latest_rows[0]["filter_snapshot_json"]))["owner_userid"] == "QianLan"
        assert latest_rows[0]["content_preview"] == ""
        assert int(latest_rows[0]["image_count"]) == 0
        assert (latest_rows[0]["selected_count"], latest_rows[0]["eligible_count"], latest_rows[0]["sent_count"]) == (1, 1, 1)
        assert (latest_rows[1]["filter_snapshot_json"] if isinstance(latest_rows[1]["filter_snapshot_json"], (dict, list)) else json.loads(latest_rows[1]["filter_snapshot_json"]))["owner_userid"] == "sales_02"
        assert latest_rows[1]["content_preview"] == "文本 + 图片 + 附件一起发"
        assert int(latest_rows[1]["image_count"]) == 1
        assert (latest_rows[1]["selected_count"], latest_rows[1]["eligible_count"], latest_rows[1]["sent_count"]) == (1, 1, 1)


def test_send_pool_private_message_mcp_tool_supports_image_with_attachment(app, client):
    _seed_customer(
        app,
        external_userid="wm_pool_send_image_attachment",
        mobile="13800138633",
        customer_name="图片附件组合客户",
        owner_userid="sales_02",
        signup_status="lead",
        signup_label_name="报名引流品",
    )
    assert _persist_marketing_state(app, external_userid="wm_pool_send_image_attachment")["stage_key"] == "pool/new_user"

    dispatched_payloads: list[dict[str, object]] = []

    def fake_dispatch(task_type: str, fn_name: str, payload: dict[str, object]) -> dict[str, object]:
        dispatched_payloads.append({"task_type": task_type, "fn_name": fn_name, "payload": dict(payload)})
        return {
            "task_id": len(dispatched_payloads),
            "wecom_result": {"msgid": f"msg-image-attachment-{len(dispatched_payloads)}"},
        }

    with app.app_context():
        from wecom_ability_service.domains.marketing_automation import service as marketing_service

        original_dispatch = marketing_service.dispatch_wecom_task
        marketing_service.dispatch_wecom_task = fake_dispatch
        try:
            payload = _mcp_call(
                client,
                "send_pool_private_message",
                {
                    "owner_userid": "sales_02",
                    "pool_key": "new_user",
                    "images": [{"file_name": "image-attachment.png", "data_url": _test_image_data_url("image-attachment")}],
                    "attachments": [{"msgtype": "file", "file": {"media_id": "file-media-c"}}],
                    "confirm": True,
                },
            ).get_json()["result"]["structuredContent"]
        finally:
            marketing_service.dispatch_wecom_task = original_dispatch

    assert payload["owner_userid"] == "sales_02"
    assert payload["matched_count"] == 1
    assert payload["sendable_count"] == 1
    assert payload["image_count"] == 1
    assert payload["content_preview"] == ""
    assert int(payload["record_id"]) > 0
    assert [item["payload"]["external_userid"] for item in dispatched_payloads] == [["wm_pool_send_image_attachment"]]
    assert "text" not in dispatched_payloads[0]["payload"]
    assert len(dispatched_payloads[0]["payload"]["images"]) == 1
    assert dispatched_payloads[0]["payload"]["attachments"] == [{"msgtype": "file", "file": {"media_id": "file-media-c"}}]


def test_send_pool_private_message_mcp_tool_validates_body_and_image_limit(app, client):
    _seed_customer(
        app,
        external_userid="wm_pool_send_validate",
        mobile="13800138623",
        customer_name="校验客户",
        owner_userid="QianLan",
        signup_status="lead",
        signup_label_name="报名引流品",
    )
    assert _persist_marketing_state(app, external_userid="wm_pool_send_validate")["stage_key"] == "pool/new_user"

    empty_response = _mcp_call(
        client,
        "send_pool_private_message",
        {"owner_userid": "QianLan", "pool_key": "new_user", "confirm": True},
    )
    too_many_images_response = _mcp_call(
        client,
        "send_pool_private_message",
        {
            "owner_userid": "QianLan",
            "pool_key": "new_user",
            "images": [
                {"file_name": f"too-many-{index}.png", "data_url": _test_image_data_url(str(index))}
                for index in range(1, 5)
            ],
            "confirm": True,
        },
    )

    assert empty_response.status_code == 200
    assert empty_response.get_json()["error"]["message"] == "content, images, or attachments is required"
    assert too_many_images_response.status_code == 200
    assert too_many_images_response.get_json()["error"]["message"] == "at most 3 images are allowed"

    invalid_attachment_response = _mcp_call(
        client,
        "send_pool_private_message",
        {
            "owner_userid": "QianLan",
            "pool_key": "new_user",
            "attachments": [{"msgtype": "file", "file": {"name": "missing-media-id"}}],
            "confirm": True,
        },
    )
    assert invalid_attachment_response.status_code == 200
    assert invalid_attachment_response.get_json()["error"]["message"] == "file attachments must include media_id"


def test_ack_conversion_batch_mcp_tool_updates_dispatch_logs(app, client, monkeypatch):
    _freeze_router_time(monkeypatch, timestamp="2026-04-04 10:30:00")
    seed = _save_default_signup_conversion_config(client, app, questionnaire_id=142)
    _seed_marketing_fixture(app)
    _create_questionnaire_submission(
        app,
        seed,
        submission_id=14201,
        external_userid="wm_conv_001",
        mobile_snapshot="13800138001",
        hit_question_count=4,
        submitted_at="2026-04-04 10:03:00",
    )

    pending_payload = _mcp_call(client, "get_pending_conversion_batches", {"limit": 10}).get_json()["result"]["structuredContent"]
    batch_id = pending_payload["items"][0]["batch_id"]

    ack_payload = _mcp_call(
        client,
        "ack_conversion_batch",
        {"batch_id": batch_id, "acked_by": "openclaw", "ack_note": "accepted by openclaw"},
    ).get_json()["result"]["structuredContent"]

    assert ack_payload["batch_id"] == batch_id
    assert ack_payload["acknowledged_count"] == 1
    assert ack_payload["dispatch_logs"][0]["dispatch_status"] == "acked"
    assert ack_payload["dispatch_logs"][0]["acked_at"] != ""

    with app.app_context():
        row = get_db().execute(
            """
            SELECT dispatch_status, acked_at
            FROM conversion_dispatch_log
            WHERE batch_id = ? AND external_userid = ?
            """,
            (batch_id, "wm_conv_001"),
        ).fetchone()
        assert row["dispatch_status"] == "acked"
        assert row["acked_at"] != ""


def test_sidebar_contact_binding_status_includes_marketing_profile(app, client, monkeypatch):
    _freeze_router_time(monkeypatch, timestamp="2026-04-04 10:30:00")
    seed = _save_default_signup_conversion_config(client, app, questionnaire_id=43)
    _seed_marketing_fixture(app)
    _create_questionnaire_submission(
        app,
        seed,
        submission_id=4301,
        external_userid="wm_conv_001",
        mobile_snapshot="13800138001",
        hit_question_count=4,
        submitted_at="2026-04-04 10:04:00",
    )

    response = client.get(
        "/api/sidebar/contact-binding-status",
        query_string={"external_userid": "wm_conv_001", "owner_userid": "sales_01"},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["marketing_profile"]["marketing_state"]["marketing_phase"] in {"waiting_openclaw", "awaiting_trigger"}
    assert payload["marketing_profile"]["value_segment"]["value_segment"] == "focus"


def test_candidate_router_filters_normal_stage_and_is_idempotent(app, client, monkeypatch):
    _freeze_router_time(monkeypatch, timestamp="2026-04-04 10:30:00")
    seed = _save_default_signup_conversion_config(client, app, questionnaire_id=44)

    _seed_customer(
        app,
        external_userid="wm_router_top",
        mobile="13800138401",
        customer_name="Top 候选",
        owner_userid="sales_44",
        signup_status="lead",
        signup_label_name="报名引流品",
        messages=[("wm_router_top", "我想尽快报名", "2026-04-04 10:11:00")],
    )
    _seed_customer(
        app,
        external_userid="wm_router_core",
        mobile="13800138402",
        customer_name="Core 候选",
        owner_userid="sales_44",
        signup_status="lead",
        signup_label_name="报名引流品",
        messages=[("wm_router_core", "能介绍一下课程吗", "2026-04-04 10:11:20")],
    )
    _seed_customer(
        app,
        external_userid="wm_router_normal",
        mobile="13800138403",
        customer_name="Normal 客户",
        owner_userid="sales_44",
        signup_status="lead",
        signup_label_name="报名引流品",
        messages=[("wm_router_normal", "先看看", "2026-04-04 10:11:40")],
    )
    _create_questionnaire_submission(
        app,
        seed,
        submission_id=4401,
        external_userid="wm_router_top",
        mobile_snapshot="13800138401",
        hit_question_count=4,
        submitted_at="2026-04-04 10:12:00",
    )
    _create_questionnaire_submission(
        app,
        seed,
        submission_id=4402,
        external_userid="wm_router_core",
        mobile_snapshot="13800138402",
        hit_question_count=3,
        submitted_at="2026-04-04 10:12:10",
    )
    _create_questionnaire_submission(
        app,
        seed,
        submission_id=4403,
        external_userid="wm_router_normal",
        mobile_snapshot="13800138403",
        hit_question_count=2,
        submitted_at="2026-04-04 10:12:20",
    )
    _seed_activation_source(app, mobile="13800138402", updated_at="2026-04-04 10:12:30")

    list_response = client.get("/api/customers/automation/signup-conversion/batches")
    list_payload = list_response.get_json()["automation_batches"]
    assert list_response.status_code == 200
    assert list_payload["count"] == 1
    batch_id = list_payload["items"][0]["id"]

    first_detail_response = client.get(f"/api/customers/automation/signup-conversion/batches/{batch_id}")
    first_detail = first_detail_response.get_json()["automation_batch"]
    candidate_external_userids = {item["external_userid"] for item in first_detail["candidates"]}
    skipped_map = {item["external_userid"]: item["reason"] for item in first_detail["skipped_customers"]}

    assert first_detail_response.status_code == 200
    assert first_detail["candidate_count"] == 2
    assert candidate_external_userids == {"wm_router_top", "wm_router_core"}
    assert skipped_map["wm_router_normal"] == "pool_not_openclaw_target"
    assert {item["current_stage"] for item in first_detail["candidates"]} == {
        "pool/inactive_focus",
        "pool/active_focus",
    }
    assert {item["current_segment"] for item in first_detail["candidates"]} == {"focus"}

    with app.app_context():
        db = get_db()
        pending_rows = db.execute(
            """
            SELECT external_userid, dispatch_status
            FROM conversion_dispatch_log
            WHERE batch_id = ?
            ORDER BY external_userid ASC
            """,
            (batch_id,),
        ).fetchall()
        assert [(row["external_userid"], row["dispatch_status"]) for row in pending_rows] == [
            ("wm_router_core", "pending"),
            ("wm_router_top", "pending"),
        ]

    second_detail_response = client.get(f"/api/customers/automation/signup-conversion/batches/{batch_id}")
    second_detail = second_detail_response.get_json()["automation_batch"]
    assert second_detail_response.status_code == 200
    assert second_detail["candidate_count"] == 2

    with app.app_context():
        db = get_db()
        pending_count = db.execute(
            """
            SELECT COUNT(*) AS total
            FROM conversion_dispatch_log
            WHERE batch_id = ? AND dispatch_status = 'pending'
            """,
            (batch_id,),
        ).fetchone()["total"]
        assert int(pending_count) == 2

        db.execute(
            """
            UPDATE conversion_dispatch_log
            SET dispatch_status = 'dispatched', dispatched_at = '2026-04-04 10:13:00'
            WHERE batch_id = ? AND external_userid = ?
            """,
            (batch_id, "wm_router_top"),
        )
        db.commit()

    third_detail_response = client.get(f"/api/customers/automation/signup-conversion/batches/{batch_id}")
    third_detail = third_detail_response.get_json()["automation_batch"]
    third_candidates = {item["external_userid"] for item in third_detail["candidates"]}
    third_skipped = {item["external_userid"]: item["reason"] for item in third_detail["skipped_customers"]}

    assert third_detail_response.status_code == 200
    assert third_candidates == {"wm_router_core"}
    assert third_skipped["wm_router_top"] == "already_dispatched"

    with app.app_context():
        db = get_db()
        row_count = db.execute(
            """
            SELECT COUNT(*) AS total
            FROM conversion_dispatch_log
            WHERE batch_id = ?
            """,
            (batch_id,),
        ).fetchone()["total"]
        assert int(row_count) == 2


def test_candidate_router_blocks_after_quiet_hours_and_reenters_next_day(app, client, monkeypatch):
    seed = _save_default_signup_conversion_config(client, app, questionnaire_id=45)
    _seed_customer(
        app,
        external_userid="wm_router_blocked",
        mobile="13800138405",
        customer_name="夜间候选",
        owner_userid="sales_45",
        signup_status="lead",
        signup_label_name="报名引流品",
        messages=[("wm_router_blocked", "今晚先问一下", "2026-04-04 10:21:00")],
    )
    _create_questionnaire_submission(
        app,
        seed,
        submission_id=4501,
        external_userid="wm_router_blocked",
        mobile_snapshot="13800138405",
        hit_question_count=4,
        submitted_at="2026-04-04 10:22:00",
    )

    _freeze_router_time(monkeypatch, timestamp="2026-04-04 23:10:00")
    late_list_response = client.get("/api/customers/automation/signup-conversion/batches")
    late_payload = late_list_response.get_json()["automation_batches"]
    assert late_list_response.status_code == 200
    assert late_payload["count"] == 1
    batch_id = late_payload["items"][0]["id"]
    assert late_payload["items"][0]["candidate_count"] == 0
    assert late_payload["items"][0]["blocked_count"] == 1

    late_detail_response = client.get(f"/api/customers/automation/signup-conversion/batches/{batch_id}")
    late_detail = late_detail_response.get_json()["automation_batch"]
    late_skipped = {item["external_userid"]: item["reason"] for item in late_detail["skipped_customers"]}

    assert late_detail_response.status_code == 200
    assert late_detail["candidate_count"] == 0
    assert late_detail["blocked_count"] == 1
    assert late_skipped["wm_router_blocked"] == "blocked_quiet_hours"

    with app.app_context():
        db = get_db()
        blocked_row = db.execute(
            """
            SELECT dispatch_status
            FROM conversion_dispatch_log
            WHERE batch_id = ? AND external_userid = ?
            """,
            (batch_id, "wm_router_blocked"),
        ).fetchone()
        assert blocked_row["dispatch_status"] == "blocked_quiet_hours"

    _freeze_router_time(monkeypatch, timestamp="2026-04-05 09:05:00")
    next_day_detail_response = client.get(f"/api/customers/automation/signup-conversion/batches/{batch_id}")
    next_day_detail = next_day_detail_response.get_json()["automation_batch"]

    assert next_day_detail_response.status_code == 200
    assert next_day_detail["candidate_count"] == 1
    assert next_day_detail["blocked_count"] == 0
    assert next_day_detail["candidates"][0]["external_userid"] == "wm_router_blocked"
    assert next_day_detail["candidates"][0]["dispatch_status"] == "pending"

    with app.app_context():
        db = get_db()
        rows = db.execute(
            """
            SELECT dispatch_status
            FROM conversion_dispatch_log
            WHERE batch_id = ? AND external_userid = ?
            """,
            (batch_id, "wm_router_blocked"),
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["dispatch_status"] == "pending"


def test_candidate_router_respects_auto_start_window_boundaries(app, client, monkeypatch):
    seed = _seed_signup_conversion_questionnaire(app, questionnaire_id=145)
    save_response = client.put(
        "/api/admin/marketing-automation/config",
        json=_signup_conversion_config_payload(seed, day_start_hour=9, quiet_hour_start=23),
    )
    assert save_response.status_code == 200

    _seed_customer(
        app,
        external_userid="wm_router_window",
        mobile="13800138555",
        customer_name="时间窗候选",
        owner_userid="sales_145",
        signup_status="lead",
        signup_label_name="报名引流品",
        messages=[("wm_router_window", "我先问一下", "2026-04-04 10:21:00")],
    )
    _create_questionnaire_submission(
        app,
        seed,
        submission_id=14501,
        external_userid="wm_router_window",
        mobile_snapshot="13800138555",
        hit_question_count=4,
        submitted_at="2026-04-04 10:22:00",
    )

    _freeze_router_time(monkeypatch, timestamp="2026-04-04 08:59:00")
    early_payload = client.get("/api/customers/automation/signup-conversion/batches").get_json()["automation_batches"]
    assert early_payload["count"] == 1
    batch_id = early_payload["items"][0]["id"]
    assert early_payload["items"][0]["candidate_count"] == 0
    assert early_payload["items"][0]["blocked_count"] == 1

    _freeze_router_time(monkeypatch, timestamp="2026-04-04 09:00:00")
    morning_payload = client.get(f"/api/customers/automation/signup-conversion/batches/{batch_id}").get_json()["automation_batch"]
    assert morning_payload["candidate_count"] == 1
    assert morning_payload["blocked_count"] == 0
    assert morning_payload["candidates"][0]["external_userid"] == "wm_router_window"

    _freeze_router_time(monkeypatch, timestamp="2026-04-04 22:59:00")
    late_payload = client.get(f"/api/customers/automation/signup-conversion/batches/{batch_id}").get_json()["automation_batch"]
    assert late_payload["candidate_count"] == 1
    assert late_payload["blocked_count"] == 0

    _freeze_router_time(monkeypatch, timestamp="2026-04-04 23:00:00")
    blocked_payload = client.get(f"/api/customers/automation/signup-conversion/batches/{batch_id}").get_json()["automation_batch"]
    blocked_reasons = {item["external_userid"]: item["reason"] for item in blocked_payload["skipped_customers"]}

    assert blocked_payload["candidate_count"] == 0
    assert blocked_payload["blocked_count"] == 1
    assert blocked_reasons["wm_router_window"] == "blocked_quiet_hours"


def test_sidebar_marketing_status_query_and_mark_unmark_reflect_latest_state(app, client, monkeypatch):
    seed = _seed_signup_conversion_questionnaire(app, questionnaire_id=23)
    save_response = client.put("/api/admin/marketing-automation/config", json=_signup_conversion_config_payload(seed))
    assert save_response.status_code == 200

    _seed_customer(
        app,
        external_userid="wm_sidebar_marketing",
        mobile="13800138123",
        customer_name="侧边栏营销客户",
        owner_userid="sales_23",
        signup_status="lead",
        signup_label_name="报名引流品",
    )
    _seed_activation_source(app, mobile="13800138123", updated_at="2026-04-04 13:00:00")
    _create_questionnaire_submission(
        app,
        seed,
        submission_id=2301,
        external_userid="wm_sidebar_marketing",
        mobile_snapshot="13800138123",
        hit_question_count=4,
        submitted_at="2026-04-04 13:05:00",
    )
    _freeze_router_time(monkeypatch, timestamp="2026-04-04 13:10:00")

    initial_response = client.get(
        "/api/sidebar/marketing-status",
        query_string={"external_userid": "wm_sidebar_marketing"},
    )
    initial_payload = initial_response.get_json()["marketing_status"]

    assert initial_response.status_code == 200
    assert initial_payload["external_userid"] == "wm_sidebar_marketing"
    assert initial_payload["main_stage"] == "pool"
    assert initial_payload["sub_stage"] == "active_focus"
    assert initial_payload["segment"] == "focus"
    assert initial_payload["stage_display"] == "激活重点跟进池"
    assert initial_payload["segment_display"] == "重点跟进"
    assert initial_payload["pool_display"] == "激活重点跟进池"
    assert initial_payload["activated"] is True
    assert initial_payload["current_followup_type"] == "focus"
    assert initial_payload["current_followup_type_display"] == "重点跟进"
    assert initial_payload["questionnaire_segment_display"] == "重点跟进"
    assert initial_payload["followup_segment_source"] == "questionnaire"
    assert initial_payload["followup_segment_source_display"] == "问卷初判"
    assert initial_payload["manual_override_active"] is False
    assert initial_payload["eligibility_display"] == "会"
    assert initial_payload["hit_count"] == 4
    assert initial_payload["matched_question_ids"] == seed["question_ids"][:4]
    assert initial_payload["eligible_for_conversion"] is True
    assert initial_payload["last_activation_at"] == "2026-04-04 13:00:00"
    assert initial_payload["last_conversion_marked_at"] == ""

    mark_response = client.post(
        "/api/sidebar/marketing-status/mark-enrolled",
        json={"external_userid": "wm_sidebar_marketing", "owner_userid": "sales_23", "operator": "sales_23"},
    )
    mark_payload = mark_response.get_json()

    assert mark_response.status_code == 200
    assert mark_payload["conversion"]["source"] == "sidebar_manual"
    assert mark_payload["marketing_status"]["main_stage"] == "converted"
    assert mark_payload["marketing_status"]["sub_stage"] == "enrolled"
    assert mark_payload["marketing_status"]["stage_display"] == "已确认成交"
    assert mark_payload["marketing_status"]["eligibility_display"] == "不会"
    assert "已退出全部营销" in mark_payload["marketing_status"]["ineligible_reason_display"]
    assert mark_payload["marketing_status"]["eligible_for_conversion"] is False
    assert mark_payload["marketing_status"]["last_conversion_marked_at"] != ""

    marked_status_response = client.get(
        "/api/sidebar/marketing-status",
        query_string={"external_userid": "wm_sidebar_marketing"},
    )
    marked_status = marked_status_response.get_json()["marketing_status"]
    assert marked_status_response.status_code == 200
    assert marked_status["main_stage"] == "converted"
    assert marked_status["sub_stage"] == "enrolled"

    unmark_response = client.post(
        "/api/sidebar/marketing-status/unmark-enrolled",
        json={"external_userid": "wm_sidebar_marketing", "owner_userid": "sales_23", "operator": "sales_23"},
    )
    unmark_payload = unmark_response.get_json()

    assert unmark_response.status_code == 200
    assert unmark_payload["conversion"]["source"] == "sidebar_manual"
    assert unmark_payload["marketing_status"]["main_stage"] == "pool"
    assert unmark_payload["marketing_status"]["sub_stage"] == "active_focus"
    assert unmark_payload["marketing_status"]["stage_display"] == "激活重点跟进池"
    assert unmark_payload["marketing_status"]["eligible_for_conversion"] is True

    unmarked_status_response = client.get(
        "/api/sidebar/marketing-status",
        query_string={"external_userid": "wm_sidebar_marketing"},
    )
    unmarked_status = unmarked_status_response.get_json()["marketing_status"]
    assert unmarked_status_response.status_code == 200
    assert unmarked_status["main_stage"] == "pool"
    assert unmarked_status["sub_stage"] == "active_focus"
    assert unmarked_status["segment"] == "focus"


def test_sidebar_marketing_status_rejects_missing_and_unknown_external_userid(app, client):
    missing_response = client.get("/api/sidebar/marketing-status")
    assert missing_response.status_code == 400
    assert missing_response.get_json()["error"] == "external_userid is required"

    unknown_response = client.get(
        "/api/sidebar/marketing-status",
        query_string={"external_userid": "wm_sidebar_unknown"},
    )
    assert unknown_response.status_code == 404

    mark_missing_response = client.post("/api/sidebar/marketing-status/mark-enrolled", json={})
    assert mark_missing_response.status_code == 400
    assert mark_missing_response.get_json()["error"] == "external_userid is required"

    unmark_unknown_response = client.post(
        "/api/sidebar/marketing-status/unmark-enrolled",
        json={"external_userid": "wm_sidebar_unknown"},
    )
    assert unmark_unknown_response.status_code == 404

    switch_missing_response = client.post("/api/sidebar/marketing-status/set-followup-segment", json={})
    assert switch_missing_response.status_code == 400
    assert switch_missing_response.get_json()["error"] == "external_userid is required"

    switch_unknown_response = client.post(
        "/api/sidebar/marketing-status/set-followup-segment",
        json={"external_userid": "wm_sidebar_unknown", "followup_segment": "focus"},
    )
    assert switch_unknown_response.status_code == 404


@pytest.mark.parametrize(
    ("external_userid", "mobile", "activated", "hit_question_count", "target_segment", "expected_sub_stage"),
    [
        ("wm_sidebar_inactive_normal", "13800138501", False, 1, "focus", "inactive_focus"),
        ("wm_sidebar_inactive_focus", "13800138502", False, 4, "normal", "inactive_normal"),
        ("wm_sidebar_active_normal", "13800138503", True, 1, "focus", "active_focus"),
        ("wm_sidebar_active_focus", "13800138504", True, 4, "normal", "active_normal"),
    ],
)
def test_sidebar_manual_followup_switch_updates_pool_and_preserves_trace(
    app,
    client,
    external_userid,
    mobile,
    activated,
    hit_question_count,
    target_segment,
    expected_sub_stage,
):
    seed = _seed_signup_conversion_questionnaire(app, questionnaire_id=24)
    save_response = client.put("/api/admin/marketing-automation/config", json=_signup_conversion_config_payload(seed))
    assert save_response.status_code == 200

    _seed_customer(
        app,
        external_userid=external_userid,
        mobile=mobile,
        customer_name="侧边栏人工改判客户",
        owner_userid="sales_24",
        signup_status="lead",
        signup_label_name="报名引流品",
    )
    if activated:
        _seed_activation_source(app, mobile=mobile, updated_at="2026-04-04 15:00:00")
    _create_questionnaire_submission(
        app,
        seed,
        submission_id=2400 + int(mobile[-1]),
        external_userid=external_userid,
        mobile_snapshot=mobile,
        hit_question_count=hit_question_count,
        submitted_at="2026-04-04 15:05:00",
    )

    switch_response = client.post(
        "/api/sidebar/marketing-status/set-followup-segment",
        json={
            "external_userid": external_userid,
            "owner_userid": "sales_24",
            "operator": "sales_24",
            "followup_segment": target_segment,
        },
    )
    switch_payload = switch_response.get_json()
    marketing_status = switch_payload["marketing_status"]

    assert switch_response.status_code == 200
    assert switch_payload["override"]["source"] == "sidebar_manual"
    assert switch_payload["override"]["followup_segment"] == target_segment
    assert marketing_status["main_stage"] == "pool"
    assert marketing_status["sub_stage"] == expected_sub_stage
    assert marketing_status["current_followup_type"] == target_segment
    assert marketing_status["segment"] == target_segment
    assert marketing_status["manual_override_active"] is True
    assert marketing_status["manual_override_segment"] == target_segment
    assert marketing_status["manual_override_operator"] == "sales_24"
    assert marketing_status["followup_segment_source"] == "manual_override"
    assert marketing_status["followup_segment_source_display"] == "人工改判"
    assert marketing_status["questionnaire_segment_display"] == ("重点跟进" if hit_question_count >= 4 else "普通跟进")

    get_response = client.get(
        "/api/sidebar/marketing-status",
        query_string={"external_userid": external_userid},
    )
    get_payload = get_response.get_json()["marketing_status"]
    assert get_response.status_code == 200
    assert get_payload["sub_stage"] == expected_sub_stage
    assert get_payload["manual_override_active"] is True

    with app.app_context():
        db = get_db()
        current_row = db.execute(
            """
            SELECT main_stage, sub_stage, state_payload_json
            FROM customer_marketing_state_current
            WHERE external_userid = ?
            """,
            (external_userid,),
        ).fetchone()
        history_row = db.execute(
            """
            SELECT sub_stage, change_reason, state_payload_json
            FROM customer_marketing_state_history
            WHERE external_userid = ?
              AND change_reason = 'manual_followup_segment_changed'
            ORDER BY id DESC
            LIMIT 1
            """,
            (external_userid,),
        ).fetchone()

        assert current_row["main_stage"] == "pool"
        assert current_row["sub_stage"] == expected_sub_stage
        current_payload = (current_row["state_payload_json"] if isinstance(current_row["state_payload_json"], (dict, list)) else json.loads(current_row["state_payload_json"]))
        assert current_payload["manual_followup_segment"] == target_segment
        assert current_payload["manual_followup_segment_source"] == "sidebar_manual"
        assert current_payload["manual_followup_segment_operator"] == "sales_24"
        assert current_payload["questionnaire_segment"] == ("top" if hit_question_count >= 4 else "normal")

        assert history_row is not None, "no history row with change_reason='manual_followup_segment_changed'"
        assert history_row["sub_stage"] == expected_sub_stage
        assert history_row["change_reason"] == "manual_followup_segment_changed"
        history_payload = (history_row["state_payload_json"] if isinstance(history_row["state_payload_json"], (dict, list)) else json.loads(history_row["state_payload_json"]))
        assert history_payload["manual_followup_segment"] == target_segment
        assert history_payload["questionnaire_segment"] == ("top" if hit_question_count >= 4 else "normal")


def test_signup_conversion_config_api_saves_and_reads_back(app, client):
    seed = _seed_signup_conversion_questionnaire(app)

    initial_response = client.get("/api/admin/marketing-automation/config")
    assert initial_response.status_code == 200
    assert initial_response.get_json()["config"]["configured"] is False
    assert initial_response.get_json()["config"]["day_start_hour"] == 9
    assert initial_response.get_json()["config"]["core_threshold"] == 3
    assert initial_response.get_json()["config"]["top_threshold"] == 4

    payload = _signup_conversion_config_payload(
        seed,
        enabled=True,
        core_threshold=35,
        top_threshold=65,
        day_start_hour=8,
        quiet_hour_start=22,
        silent_threshold_days_by_pool={
            "new_user": 3,
            "inactive_normal": 4,
            "inactive_focus": 5,
            "active_normal": 6,
            "active_focus": 7,
        },
        question_ids=seed["question_ids"][:3],
        hit_option_ids_by_question={
            seed["question_ids"][0]: seed["option_ids_by_question"][seed["question_ids"][0]][:2],
        },
    )
    save_response = client.put("/api/admin/marketing-automation/config", json=payload)
    save_payload = save_response.get_json()["config"]

    assert save_response.status_code == 200
    assert save_payload["configured"] is True
    assert save_payload["enabled"] is True
    assert save_payload["questionnaire_id"] == seed["questionnaire_id"]
    assert save_payload["core_threshold"] == 35
    assert save_payload["top_threshold"] == 65
    assert save_payload["day_start_hour"] == 8
    assert save_payload["quiet_hour_start"] == 22
    assert save_payload["timezone"] == "Asia/Shanghai"
    assert save_payload["silent_threshold_days_by_pool"] == {
        "new_user": 3,
        "inactive_normal": 4,
        "inactive_focus": 5,
        "active_normal": 6,
        "active_focus": 7,
    }
    assert len(save_payload["question_rules"]) == 3
    assert save_payload["question_rules"][0]["questionnaire_question_id"] == seed["question_ids"][0]
    assert save_payload["question_rules"][0]["hit_option_ids_json"] == seed["option_ids_by_question"][seed["question_ids"][0]][:2]

    read_response = client.get("/api/admin/marketing-automation/config")
    read_payload = read_response.get_json()["config"]

    assert read_response.status_code == 200
    assert read_payload["configured"] is True
    assert read_payload["day_start_hour"] == 8
    assert read_payload["top_threshold"] == 65
    assert read_payload["silent_threshold_days_by_pool"]["inactive_focus"] == 5
    assert read_payload["question_rules"][2]["sort_order"] == 3


def test_signup_conversion_config_api_rejects_invalid_auto_start_window(app, client):
    seed = _seed_signup_conversion_questionnaire(app, questionnaire_id=191)

    response = client.put(
        "/api/admin/marketing-automation/config",
        json=_signup_conversion_config_payload(seed, day_start_hour=23, quiet_hour_start=23),
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "day_start_hour must be < quiet_hour_start"


def test_signup_conversion_config_api_rejects_invalid_question_and_option(app, client):
    seed = _seed_signup_conversion_questionnaire(app)

    bad_question_payload = _signup_conversion_config_payload(seed)
    bad_question_payload["question_rules"][0]["questionnaire_question_id"] = 999999
    bad_question_response = client.put("/api/admin/marketing-automation/config", json=bad_question_payload)

    assert bad_question_response.status_code == 400
    assert "does not belong to questionnaire" in bad_question_response.get_json()["error"]

    bad_option_payload = _signup_conversion_config_payload(seed)
    first_question_id = seed["question_ids"][0]
    second_question_id = seed["question_ids"][1]
    bad_option_payload["question_rules"][0]["questionnaire_question_id"] = first_question_id
    bad_option_payload["question_rules"][0]["hit_option_ids_json"] = [seed["option_ids_by_question"][second_question_id][0]]
    bad_option_response = client.put("/api/admin/marketing-automation/config", json=bad_option_payload)

    assert bad_option_response.status_code == 400
    assert "does not belong to question" in bad_option_response.get_json()["error"]


def test_signup_conversion_config_api_accepts_questionnaire_without_required_mobile_for_backward_compatibility(app, client):
    seed = _seed_signup_conversion_questionnaire_without_required_mobile(app)

    response = client.put("/api/admin/marketing-automation/config", json=_signup_conversion_config_payload(seed))

    assert response.status_code == 200
    payload = response.get_json()["config"]
    assert payload["questionnaire_id"] == seed["questionnaire_id"]


def test_disabled_signup_conversion_config_blocks_candidate_batches(app, client):
    seed = _seed_signup_conversion_questionnaire(app)
    save_response = client.put(
        "/api/admin/marketing-automation/config",
        json=_signup_conversion_config_payload(seed, enabled=False),
    )
    assert save_response.status_code == 200

    _seed_marketing_fixture(app)

    list_response = client.get("/api/customers/automation/signup-conversion/batches")
    payload = list_response.get_json()["automation_batches"]

    assert list_response.status_code == 200
    assert payload["count"] == 0
    assert payload["items"] == []


def test_admin_marketing_automation_preview_returns_current_state_and_hits(app, client, monkeypatch):
    seed = _seed_signup_conversion_questionnaire(app, questionnaire_id=21)
    save_response = client.put("/api/admin/marketing-automation/config", json=_signup_conversion_config_payload(seed))
    assert save_response.status_code == 200

    _seed_customer(
        app,
        external_userid="wm_admin_preview",
        mobile="13800138121",
        customer_name="预览客户",
        owner_userid="sales_21",
        signup_status="lead",
        signup_label_name="报名引流品",
    )
    _create_questionnaire_submission(
        app,
        seed,
        submission_id=2101,
        external_userid="wm_admin_preview",
        mobile_snapshot="13800138121",
        hit_question_count=3,
        submitted_at="2026-04-04 11:00:00",
    )
    _freeze_router_time(monkeypatch, timestamp="2026-04-04 11:15:00")

    response = client.post(
        "/api/admin/marketing-automation/config/preview",
        json={"external_userid": "wm_admin_preview"},
    )
    payload = response.get_json()["preview"]

    assert response.status_code == 200
    assert payload["resolved_customer"]["external_userid"] == "wm_admin_preview"
    assert payload["summary"]["current_stage"] == "pool/inactive_focus"
    assert payload["summary"]["current_segment"] == "focus"
    assert payload["summary"]["hit_count"] == 3
    assert payload["summary"]["eligible"] is True
    assert [item["questionnaire_question_id"] for item in payload["summary"]["matched_questions"]] == seed["question_ids"][:3]

    with app.app_context():
        state_row = get_db().execute(
            """
            SELECT main_stage, sub_stage, eligible_for_conversion
            FROM customer_marketing_state_current
            WHERE external_userid = ?
            """,
            ("wm_admin_preview",),
        ).fetchone()
        segment_row = get_db().execute(
            """
            SELECT segment, score, matched_question_ids_json
            FROM customer_value_segment_current
            WHERE external_userid = ?
            """,
            ("wm_admin_preview",),
        ).fetchone()
        assert f"{state_row['main_stage']}/{state_row['sub_stage']}" == payload["summary"]["current_stage"]
        assert bool(state_row["eligible_for_conversion"]) is True
        assert segment_row["segment"] == "core"
        assert int(segment_row["score"]) == payload["summary"]["hit_count"]
        assert (segment_row["matched_question_ids_json"] if isinstance(segment_row["matched_question_ids_json"], (dict, list)) else json.loads(segment_row["matched_question_ids_json"])) == payload["summary"]["matched_question_ids"]


def test_admin_marketing_automation_preview_supports_mobile_only_person(app, client):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO people (id, mobile, third_party_user_id, created_at, updated_at)
            VALUES (6101, '13800138601', 'tp-6101', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
        db.commit()

    response = client.post(
        "/api/admin/marketing-automation/config/preview",
        json={"person_id": 6101},
    )
    payload = response.get_json()["preview"]

    assert response.status_code == 200
    assert payload["resolved_customer"]["person_id"] == 6101
    assert payload["resolved_customer"]["external_userid"] == ""
    assert payload["summary"]["current_stage"] == "pool/new_user"
    assert payload["summary"]["current_segment"] == "unknown"
    assert payload["summary"]["eligible"] is False
    assert payload["summary"]["ineligible_reason"] == "awaiting_questionnaire"


def test_admin_marketing_automation_recompute_refreshes_current_and_history(app, client, monkeypatch):
    _freeze_router_time(monkeypatch, timestamp="2026-04-04 10:30:00")
    seed = _seed_signup_conversion_questionnaire(app, questionnaire_id=22)
    save_response = client.put("/api/admin/marketing-automation/config", json=_signup_conversion_config_payload(seed))
    assert save_response.status_code == 200

    _seed_customer(
        app,
        external_userid="wm_admin_recompute",
        mobile="13800138122",
        customer_name="重算客户",
        owner_userid="sales_22",
        signup_status="lead",
        signup_label_name="报名引流品",
    )
    _create_questionnaire_submission(
        app,
        seed,
        submission_id=2201,
        external_userid="wm_admin_recompute",
        mobile_snapshot="13800138122",
        hit_question_count=2,
        submitted_at="2026-04-04 09:00:00",
    )

    first_response = client.post(
        "/api/admin/marketing-automation/recompute",
        json={"external_userid": "wm_admin_recompute"},
    )
    first_item = first_response.get_json()["recompute"]["item"]

    assert first_response.status_code == 200
    assert first_item["summary"]["current_stage"] == "pool/inactive_normal"
    assert first_item["summary"]["current_segment"] == "normal"
    assert first_item["history_refresh"]["marketing_state_history_written"] is True
    assert first_item["history_refresh"]["value_segment_history_written"] is True

    _seed_activation_source(app, mobile="13800138122", updated_at="2026-04-04 12:00:00")
    _create_questionnaire_submission(
        app,
        seed,
        submission_id=2202,
        external_userid="wm_admin_recompute",
        mobile_snapshot="13800138122",
        hit_question_count=4,
        submitted_at="2026-04-04 12:05:00",
    )

    second_response = client.post(
        "/api/admin/marketing-automation/recompute",
        json={"external_userid": "wm_admin_recompute"},
    )
    second_item = second_response.get_json()["recompute"]["item"]

    assert second_response.status_code == 200
    assert second_item["summary"]["current_stage"] == "pool/active_focus"
    assert second_item["summary"]["current_segment"] == "focus"
    assert second_item["history_refresh"]["marketing_state_history_written"] is True
    assert second_item["history_refresh"]["value_segment_history_written"] is True

    with app.app_context():
        db = get_db()
        state_current = db.execute(
            """
            SELECT main_stage, sub_stage
            FROM customer_marketing_state_current
            WHERE external_userid = ?
            """,
            ("wm_admin_recompute",),
        ).fetchone()
        segment_current = db.execute(
            """
            SELECT segment, submission_id
            FROM customer_value_segment_current
            WHERE external_userid = ?
            """,
            ("wm_admin_recompute",),
        ).fetchone()
        state_history_total = db.execute(
            """
            SELECT COUNT(*) AS total
            FROM customer_marketing_state_history
            WHERE external_userid = ?
            """,
            ("wm_admin_recompute",),
        ).fetchone()["total"]
        segment_history_total = db.execute(
            """
            SELECT COUNT(*) AS total
            FROM customer_value_segment_history
            WHERE external_userid = ?
            """,
            ("wm_admin_recompute",),
        ).fetchone()["total"]

        assert f"{state_current['main_stage']}/{state_current['sub_stage']}" == "pool/active_focus"
        assert segment_current["segment"] == "top"
        assert int(segment_current["submission_id"]) == 2202
        assert int(state_history_total) == 2
        assert int(segment_history_total) == 2


def test_signup_conversion_e2e_chain_from_questionnaire_hit_to_enrolled_exit(app, client, monkeypatch):
    _freeze_router_time(monkeypatch, timestamp="2026-04-04 10:30:00")
    seed = _save_default_signup_conversion_config(client, app, questionnaire_id=46)

    _seed_customer(
        app,
        external_userid="wm_e2e_signup",
        mobile="13800138406",
        customer_name="完整链路客户",
        owner_userid="sales_46",
        signup_status="lead",
        signup_label_name="报名引流品",
        messages=[("wm_e2e_signup", "老师我想报名，先了解一下", "2026-04-04 10:06:00")],
    )
    _create_questionnaire_submission(
        app,
        seed,
        submission_id=4601,
        external_userid="wm_e2e_signup",
        mobile_snapshot="13800138406",
        hit_question_count=4,
        submitted_at="2026-04-04 10:05:00",
    )

    preview_response = client.post(
        "/api/admin/marketing-automation/config/preview",
        json={"external_userid": "wm_e2e_signup"},
    )
    preview = preview_response.get_json()["preview"]

    assert preview_response.status_code == 200
    assert preview["summary"]["current_stage"] == "pool/inactive_focus"
    assert preview["summary"]["current_segment"] == "focus"
    assert preview["summary"]["hit_count"] == 4
    assert preview["summary"]["eligible"] is True

    batches_response = client.get("/api/customers/automation/signup-conversion/batches")
    batches_payload = batches_response.get_json()["automation_batches"]

    assert batches_response.status_code == 200
    assert batches_payload["count"] == 1
    assert batches_payload["items"][0]["candidate_count"] == 1
    batch_id = batches_payload["items"][0]["id"]

    batch_detail_response = client.get(f"/api/customers/automation/signup-conversion/batches/{batch_id}")
    batch_detail = batch_detail_response.get_json()["automation_batch"]

    assert batch_detail_response.status_code == 200
    assert batch_detail["candidate_count"] == 1
    assert batch_detail["candidates"][0]["external_userid"] == "wm_e2e_signup"
    assert batch_detail["candidates"][0]["current_segment"] == "focus"
    assert batch_detail["candidates"][0]["current_stage"] == "pool/inactive_focus"
    assert batch_detail["candidates"][0]["dispatch_status"] == "pending"

    mark_response = client.post(
        "/api/sidebar/marketing-status/mark-enrolled",
        json={"external_userid": "wm_e2e_signup", "owner_userid": "sales_46", "operator": "sales_46"},
    )
    mark_payload = mark_response.get_json()

    assert mark_response.status_code == 200
    assert mark_payload["marketing_status"]["main_stage"] == "converted"
    assert mark_payload["marketing_status"]["sub_stage"] == "enrolled"
    assert mark_payload["marketing_status"]["eligible_for_conversion"] is False

    customer_response = client.get("/api/customers/wm_e2e_signup")
    customer_payload = customer_response.get_json()["customer"]

    assert customer_response.status_code == 200
    assert customer_payload["marketing_summary"]["main_stage"] == "converted"
    assert customer_payload["marketing_summary"]["sub_stage"] == "enrolled"
    assert customer_payload["marketing_summary"]["segment"] == "focus"
    assert customer_payload["marketing_summary"]["hit_count"] == 4
    assert customer_payload["marketing_summary"]["eligible_for_conversion"] is False
    assert customer_payload["marketing_summary"]["last_conversion_marked_at"] != ""

    timeline_response = client.get("/api/customers/wm_e2e_signup/timeline")
    timeline_items = timeline_response.get_json()["timeline"]["items"]

    assert timeline_response.status_code == 200
    assert any(item["event_type"] == "value_segment_change" and item["payload"]["current_segment"] == "top" for item in timeline_items)
    assert any(item["event_type"] == "conversion_marked" and item["payload"]["conversion_action"] == "mark_enrolled" for item in timeline_items)

    exited_batch_response = client.get(f"/api/customers/automation/signup-conversion/batches/{batch_id}")
    exited_batch = exited_batch_response.get_json()["automation_batch"]
    skipped_map = {item["external_userid"]: item["reason"] for item in exited_batch["skipped_customers"]}

    assert exited_batch_response.status_code == 200
    assert exited_batch["candidate_count"] == 0
    assert skipped_map["wm_e2e_signup"] == "enrolled"

    with app.app_context():
        db = get_db()
        dispatch_row = db.execute(
            """
            SELECT dispatch_status, acked_at
            FROM conversion_dispatch_log
            WHERE batch_id = ? AND external_userid = ?
            """,
            (batch_id, "wm_e2e_signup"),
        ).fetchone()
        state_row = db.execute(
            """
            SELECT main_stage, sub_stage, eligible_for_conversion
            FROM customer_marketing_state_current
            WHERE external_userid = ?
            """,
            ("wm_e2e_signup",),
        ).fetchone()
        segment_row = db.execute(
            """
            SELECT segment, score
            FROM customer_value_segment_current
            WHERE external_userid = ?
            """,
            ("wm_e2e_signup",),
        ).fetchone()

        assert dispatch_row["dispatch_status"] == "converted_before_dispatch"
        assert dispatch_row["acked_at"] in {"", None}
        assert f"{state_row['main_stage']}/{state_row['sub_stage']}" == "converted/enrolled"
        assert bool(state_row["eligible_for_conversion"]) is False
        assert segment_row["segment"] == "top"
        assert int(segment_row["score"]) == 4


@pytest.mark.parametrize(
    ("owner_userid", "external_userid", "mobile"),
    [
        ("QianLan", "wm_focus_webhook_qianlan", "13800138701"),
        ("sales_02", "wm_focus_webhook_sales_02", "13800138721"),
    ],
)
def test_focus_pool_inbound_message_triggers_openclaw_webhook_with_customer_context(
    app,
    client,
    owner_userid,
    external_userid,
    mobile,
):
    seed = _save_default_signup_conversion_config(client, app, questionnaire_id=247)
    _seed_customer(
        app,
        external_userid=external_userid,
        mobile=mobile,
        customer_name="重点消息客户",
        owner_userid=owner_userid,
        signup_status="lead",
        signup_label_name="报名引流品",
    )
    _create_questionnaire_submission(
        app,
        seed,
        submission_id=24700 + (1 if owner_userid == "QianLan" else 2),
        external_userid=external_userid,
        mobile_snapshot=mobile,
        hit_question_count=4,
        submitted_at="2026-04-05 14:00:00",
    )
    assert _persist_marketing_state(app, external_userid=external_userid)["stage_key"] == "pool/inactive_focus"

    app.config["OPENCLAW_FOCUS_MESSAGE_WEBHOOK_URL"] = "https://openclaw.local/focus-message"
    app.config["OPENCLAW_FOCUS_MESSAGE_WEBHOOK_TOKEN"] = "focus-webhook-token"
    app.config["OPENCLAW_FOCUS_MESSAGE_WEBHOOK_TIMEOUT_SECONDS"] = 9

    webhook_calls: list[dict[str, object]] = []

    def fake_post(url: str, json: dict[str, object] | None = None, headers: dict[str, str] | None = None, timeout: int | None = None):
        webhook_calls.append(
            {
                "url": url,
                "json": dict(json or {}),
                "headers": dict(headers or {}),
                "timeout": timeout,
            }
        )
        return _WebhookResponse(status_code=202)

    with app.app_context():
        from wecom_ability_service.domains.admin_console import customer_profile_service
        from wecom_ability_service.domains.outbound_webhook import service as outbound_webhook_service

        original_post = outbound_webhook_service.requests.post
        original_tags_payload = customer_profile_service.get_customer_profile_tags_payload
        outbound_webhook_service.requests.post = fake_post
        customer_profile_service.get_customer_profile_tags_payload = lambda *, external_userid: {
            "external_userid": external_userid,
            "tags": [
                {"tag_id": "tag_focus", "tag_name": "重点跟进", "owner_userid": owner_userid},
                {"tag_id": "tag_questionnaire", "tag_name": "已提交问卷", "owner_userid": owner_userid},
            ],
        }
        try:
            inserted_count = insert_archived_messages(
                [
                    {
                        "seq": 1,
                        "msgid": f"focus-webhook-msg-{owner_userid}",
                        "chat_type": "private",
                        "external_userid": external_userid,
                        "owner_userid": owner_userid,
                        "sender": external_userid,
                        "receiver": owner_userid,
                        "msgtype": "text",
                        "content": "老师，我刚看完问卷，想继续了解",
                        "send_time": "2026-04-05 14:05:00",
                        "raw_payload": json.dumps(
                            {"decrypted_message": {"from": external_userid, "tolist": [owner_userid], "roomid": ""}},
                            ensure_ascii=False,
                        ),
                    }
                ]
            )
        finally:
            outbound_webhook_service.requests.post = original_post
            customer_profile_service.get_customer_profile_tags_payload = original_tags_payload

    assert inserted_count == 1
    assert len(webhook_calls) == 1
    assert webhook_calls[0]["url"] == "https://openclaw.local/focus-message"
    assert webhook_calls[0]["headers"]["Authorization"] == "Bearer focus-webhook-token"
    assert webhook_calls[0]["timeout"] == 9
    payload = webhook_calls[0]["json"]
    assert payload["external_userid"] == external_userid
    assert payload["current_pool"] == "inactive_focus"
    assert payload["current_stage"] == "pool/inactive_focus"
    assert payload["activated"] is False
    assert payload["owner_userid"] == owner_userid
    assert payload["customer_profile"]["mobile"] == mobile
    assert "questionnaire_summary" in payload
    assert "tags" in payload
    assert "recent_messages" in payload
    assert isinstance(payload["recent_messages"], list)
    with app.app_context():
        row = get_db().execute(
            """
            SELECT event_type, status, attempt_count, response_status_code, source_id
            FROM outbound_webhook_deliveries
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        assert row["event_type"] == "openclaw_focus_message"
        assert row["status"] == "success"
        assert int(row["attempt_count"]) == 1
        assert int(row["response_status_code"]) == 202
        assert row["source_id"] == external_userid


def test_normal_pool_inbound_message_does_not_trigger_openclaw_webhook(app, client):
    seed = _save_default_signup_conversion_config(client, app, questionnaire_id=248)
    _seed_customer(
        app,
        external_userid="wm_normal_webhook",
        mobile="13800138702",
        customer_name="普通消息客户",
        owner_userid="QianLan",
        signup_status="lead",
        signup_label_name="报名引流品",
    )
    _create_questionnaire_submission(
        app,
        seed,
        submission_id=24801,
        external_userid="wm_normal_webhook",
        mobile_snapshot="13800138702",
        hit_question_count=2,
        submitted_at="2026-04-05 14:10:00",
    )
    assert _persist_marketing_state(app, external_userid="wm_normal_webhook")["stage_key"] == "pool/inactive_normal"

    app.config["OPENCLAW_FOCUS_MESSAGE_WEBHOOK_URL"] = "https://openclaw.local/focus-message"
    webhook_calls: list[dict[str, object]] = []

    def fake_post(url: str, json: dict[str, object] | None = None, headers: dict[str, str] | None = None, timeout: int | None = None):
        webhook_calls.append({"url": url, "json": dict(json or {})})
        return _WebhookResponse(status_code=202)

    with app.app_context():
        from wecom_ability_service.domains.outbound_webhook import service as outbound_webhook_service

        original_post = outbound_webhook_service.requests.post
        outbound_webhook_service.requests.post = fake_post
        try:
            inserted_count = insert_archived_messages(
                [
                    {
                        "seq": 1,
                        "msgid": "normal-webhook-msg-001",
                        "chat_type": "private",
                        "external_userid": "wm_normal_webhook",
                        "owner_userid": "QianLan",
                        "sender": "wm_normal_webhook",
                        "receiver": "QianLan",
                        "msgtype": "text",
                        "content": "老师，我先随便看看",
                        "send_time": "2026-04-05 14:11:00",
                        "raw_payload": json.dumps(
                            {"decrypted_message": {"from": "wm_normal_webhook", "tolist": ["QianLan"], "roomid": ""}},
                            ensure_ascii=False,
                        ),
                    }
                ]
            )
        finally:
            outbound_webhook_service.requests.post = original_post

    assert inserted_count == 1
    assert webhook_calls == []


def test_openclaw_webhook_prefers_unified_url_config(app):
    app.config["OPENCLAW_WEBHOOK_URL"] = "https://openclaw.local/unified-message"
    app.config["OPENCLAW_FOCUS_MESSAGE_WEBHOOK_URL"] = "https://openclaw.local/legacy-focus-message"
    app.config["OPENCLAW_FOCUS_MESSAGE_WEBHOOK_TOKEN"] = "focus-webhook-token"
    app.config["OPENCLAW_FOCUS_MESSAGE_WEBHOOK_TIMEOUT_SECONDS"] = 7

    webhook_calls: list[dict[str, object]] = []

    def fake_post(url: str, json: dict[str, object] | None = None, headers: dict[str, str] | None = None, timeout: int | None = None):
        webhook_calls.append(
            {
                "url": url,
                "json": dict(json or {}),
                "headers": dict(headers or {}),
                "timeout": timeout,
            }
        )
        return _WebhookResponse(status_code=202, text='{"ok":true}')

    with app.app_context():
        from wecom_ability_service.domains.outbound_webhook import service as outbound_webhook_service

        original_post = outbound_webhook_service.requests.post
        outbound_webhook_service.requests.post = fake_post
        try:
            result = outbound_webhook_service.send_outbound_webhook(
                event_type="openclaw_focus_message",
                payload={"currentPool": "active_focus"},
                source_key="automation_member",
                source_id="member-001",
            )
        finally:
            outbound_webhook_service.requests.post = original_post

    assert result["ok"] is True
    assert len(webhook_calls) == 1
    assert webhook_calls[0]["url"] == "https://openclaw.local/unified-message"
    assert webhook_calls[0]["headers"]["Authorization"] == "Bearer focus-webhook-token"
    assert webhook_calls[0]["timeout"] == 7
    assert result["delivery"]["target_url"] == "https://openclaw.local/unified-message"


def test_openclaw_webhook_keeps_legacy_url_as_fallback(app):
    app.config["OPENCLAW_WEBHOOK_URL"] = ""
    app.config["OPENCLAW_FOCUS_MESSAGE_WEBHOOK_URL"] = "https://openclaw.local/focus-message"

    webhook_calls: list[str] = []

    def fake_post(url: str, json: dict[str, object] | None = None, headers: dict[str, str] | None = None, timeout: int | None = None):
        webhook_calls.append(url)
        return _WebhookResponse(status_code=202, text='{"ok":true}')

    with app.app_context():
        from wecom_ability_service.domains.outbound_webhook import service as outbound_webhook_service

        original_post = outbound_webhook_service.requests.post
        outbound_webhook_service.requests.post = fake_post
        try:
            result = outbound_webhook_service.send_outbound_webhook(
                event_type="openclaw_focus_message",
                payload={"currentPool": "inactive_focus"},
                source_key="automation_member",
                source_id="member-002",
            )
        finally:
            outbound_webhook_service.requests.post = original_post

    assert result["ok"] is True
    assert webhook_calls == ["https://openclaw.local/focus-message"]
    assert result["delivery"]["target_url"] == "https://openclaw.local/focus-message"


def test_focus_pool_webhook_failure_schedules_retry_and_manual_retry_succeeds(app, client, monkeypatch):
    _freeze_router_time(monkeypatch, timestamp="2026-04-05 16:06:00")
    seed = _save_default_signup_conversion_config(client, app, questionnaire_id=348)
    _seed_customer(
        app,
        external_userid="wm_focus_retry",
        mobile="13800138711",
        customer_name="重点重试客户",
        owner_userid="QianLan",
        signup_status="lead",
        signup_label_name="报名引流品",
    )
    _create_questionnaire_submission(
        app,
        seed,
        submission_id=34801,
        external_userid="wm_focus_retry",
        mobile_snapshot="13800138711",
        hit_question_count=4,
        submitted_at="2026-04-05 16:00:00",
    )
    assert _persist_marketing_state(app, external_userid="wm_focus_retry")["stage_key"] == "pool/inactive_focus"
    app.config["OPENCLAW_FOCUS_MESSAGE_WEBHOOK_URL"] = "https://openclaw.local/focus-message"
    app.config["OPENCLAW_FOCUS_MESSAGE_WEBHOOK_TIMEOUT_SECONDS"] = 9
    app.config["OUTBOUND_WEBHOOK_RETRY_ENABLED"] = True
    app.config["OUTBOUND_WEBHOOK_RETRY_MAX_ATTEMPTS"] = 3
    app.config["OUTBOUND_WEBHOOK_RETRY_INTERVAL_SECONDS"] = 60

    webhook_calls: list[dict[str, object]] = []

    def fake_post(url: str, json: dict[str, object] | None = None, headers: dict[str, str] | None = None, timeout: int | None = None):
        webhook_calls.append({"url": url, "json": dict(json or {})})
        if len(webhook_calls) == 1:
            raise requests.RequestException("focus webhook boom")
        return _WebhookResponse(status_code=202, text='{"ok":true}')

    with app.app_context():
        from wecom_ability_service.domains.admin_console import customer_profile_service
        from wecom_ability_service.domains.outbound_webhook import service as outbound_webhook_service

        original_post = outbound_webhook_service.requests.post
        original_tags_payload = customer_profile_service.get_customer_profile_tags_payload
        outbound_webhook_service.requests.post = fake_post
        customer_profile_service.get_customer_profile_tags_payload = lambda *, external_userid: {
            "external_userid": external_userid,
            "tags": [
                {"tag_id": "tag_focus", "tag_name": "重点跟进", "owner_userid": "QianLan"},
            ],
        }
        try:
            assert insert_archived_messages(
                [
                    {
                        "seq": 1,
                        "msgid": "focus-webhook-retry-msg-001",
                        "chat_type": "private",
                        "external_userid": "wm_focus_retry",
                        "owner_userid": "QianLan",
                        "sender": "wm_focus_retry",
                        "receiver": "QianLan",
                        "msgtype": "text",
                        "content": "第一次 webhook 失败，第二次成功",
                        "send_time": "2026-04-05 16:05:00",
                        "raw_payload": json.dumps(
                            {"decrypted_message": {"from": "wm_focus_retry", "tolist": ["QianLan"], "roomid": ""}},
                            ensure_ascii=False,
                        ),
                    }
                ]
            ) == 1
            with app.app_context():
                row = get_db().execute(
                    """
                    SELECT id, status, attempt_count, next_retry_at, last_error
                    FROM outbound_webhook_deliveries
                    ORDER BY id DESC
                    LIMIT 1
                    """
                ).fetchone()
                delivery_id = int(row["id"])
                assert row["status"] == "retry_scheduled"
                assert int(row["attempt_count"]) == 1
                assert row["next_retry_at"] != ""
                assert row["last_error"] == "focus webhook boom"

            retry_response = client.post(
                f"/api/customers/automation/webhook-deliveries/{delivery_id}/retry",
                headers=_internal_headers(),
            )
            assert retry_response.status_code == 200
            body = retry_response.get_json()
            assert body["ok"] is True
            assert body["delivery"]["delivery"]["status"] == "success"
            assert int(body["delivery"]["delivery"]["attempt_count"]) == 2
        finally:
            outbound_webhook_service.requests.post = original_post
            customer_profile_service.get_customer_profile_tags_payload = original_tags_payload


def test_focus_pool_webhook_retry_exhausted_and_list_endpoint_filters_failed_items(app, client, monkeypatch):
    _freeze_router_time(monkeypatch, timestamp="2026-04-05 16:12:00")
    seed = _save_default_signup_conversion_config(client, app, questionnaire_id=349)
    _seed_customer(
        app,
        external_userid="wm_focus_exhausted",
        mobile="13800138712",
        customer_name="重点耗尽客户",
        owner_userid="QianLan",
        signup_status="lead",
        signup_label_name="报名引流品",
    )
    _create_questionnaire_submission(
        app,
        seed,
        submission_id=34901,
        external_userid="wm_focus_exhausted",
        mobile_snapshot="13800138712",
        hit_question_count=4,
        submitted_at="2026-04-05 16:10:00",
    )
    assert _persist_marketing_state(app, external_userid="wm_focus_exhausted")["stage_key"] == "pool/inactive_focus"
    app.config["OPENCLAW_FOCUS_MESSAGE_WEBHOOK_URL"] = "https://openclaw.local/focus-message"
    app.config["OUTBOUND_WEBHOOK_RETRY_ENABLED"] = True
    app.config["OUTBOUND_WEBHOOK_RETRY_MAX_ATTEMPTS"] = 2

    def fake_post(url: str, json: dict[str, object] | None = None, headers: dict[str, str] | None = None, timeout: int | None = None):
        raise requests.RequestException("focus webhook exhausted")

    with app.app_context():
        from wecom_ability_service.domains.admin_console import customer_profile_service
        from wecom_ability_service.domains.outbound_webhook import service as outbound_webhook_service

        original_post = outbound_webhook_service.requests.post
        original_tags_payload = customer_profile_service.get_customer_profile_tags_payload
        outbound_webhook_service.requests.post = fake_post
        customer_profile_service.get_customer_profile_tags_payload = lambda *, external_userid: {
            "external_userid": external_userid,
            "tags": [
                {"tag_id": "tag_focus", "tag_name": "重点跟进", "owner_userid": "QianLan"},
            ],
        }
        try:
            assert insert_archived_messages(
                [
                    {
                        "seq": 1,
                        "msgid": "focus-webhook-retry-msg-002",
                        "chat_type": "private",
                        "external_userid": "wm_focus_exhausted",
                        "owner_userid": "QianLan",
                        "sender": "wm_focus_exhausted",
                        "receiver": "QianLan",
                        "msgtype": "text",
                        "content": "会重试到耗尽",
                        "send_time": "2026-04-05 16:11:00",
                        "raw_payload": json.dumps(
                            {"decrypted_message": {"from": "wm_focus_exhausted", "tolist": ["QianLan"], "roomid": ""}},
                            ensure_ascii=False,
                        ),
                    }
                ]
            ) == 1
            with app.app_context():
                row = get_db().execute(
                    "SELECT id, status, attempt_count FROM outbound_webhook_deliveries ORDER BY id DESC LIMIT 1"
                ).fetchone()
                delivery_id = int(row["id"])
                assert row["status"] == "retry_scheduled"
                assert int(row["attempt_count"]) == 1

            retry_response = client.post(
                f"/api/customers/automation/webhook-deliveries/{delivery_id}/retry",
                headers=_internal_headers(),
            )
            assert retry_response.status_code == 200
            with app.app_context():
                exhausted_row = get_db().execute(
                    "SELECT status, attempt_count, last_error FROM outbound_webhook_deliveries WHERE id = ?",
                    (delivery_id,),
                ).fetchone()
                assert exhausted_row["status"] == "exhausted"
                assert int(exhausted_row["attempt_count"]) == 2
                assert exhausted_row["last_error"] == "focus webhook exhausted"

            list_response = client.get(
                "/api/customers/automation/webhook-deliveries",
                query_string={"event_type": "openclaw_focus_message", "status": "exhausted", "limit": 10},
            )
            assert list_response.status_code == 200
            items = list_response.get_json()["deliveries"]["items"]
            assert len(items) >= 1
            assert items[0]["event_type"] == "openclaw_focus_message"
            assert items[0]["status"] == "exhausted"
        finally:
            outbound_webhook_service.requests.post = original_post
            customer_profile_service.get_customer_profile_tags_payload = original_tags_payload


def test_focus_pool_webhook_missing_url_records_unconfigured_delivery(app, client, monkeypatch):
    _freeze_router_time(monkeypatch, timestamp="2026-04-05 16:22:00")
    seed = _save_default_signup_conversion_config(client, app, questionnaire_id=350)
    _seed_customer(
        app,
        external_userid="wm_focus_missing_url",
        mobile="13800138713",
        customer_name="重点未配置 URL 客户",
        owner_userid="QianLan",
        signup_status="lead",
        signup_label_name="报名引流品",
    )
    _create_questionnaire_submission(
        app,
        seed,
        submission_id=35001,
        external_userid="wm_focus_missing_url",
        mobile_snapshot="13800138713",
        hit_question_count=4,
        submitted_at="2026-04-05 16:20:00",
    )
    assert _persist_marketing_state(app, external_userid="wm_focus_missing_url")["stage_key"] == "pool/inactive_focus"
    app.config["OPENCLAW_WEBHOOK_URL"] = ""
    app.config["OPENCLAW_FOCUS_MESSAGE_WEBHOOK_URL"] = ""

    with app.app_context():
        from wecom_ability_service.domains.admin_console import customer_profile_service

        original_tags_payload = customer_profile_service.get_customer_profile_tags_payload
        customer_profile_service.get_customer_profile_tags_payload = lambda *, external_userid: {
            "external_userid": external_userid,
            "tags": [
                {"tag_id": "tag_focus", "tag_name": "重点跟进", "owner_userid": "QianLan"},
            ],
        }
        try:
            assert insert_archived_messages(
                [
                    {
                        "seq": 1,
                        "msgid": "focus-webhook-missing-url-msg-001",
                        "chat_type": "private",
                        "external_userid": "wm_focus_missing_url",
                        "owner_userid": "QianLan",
                        "sender": "wm_focus_missing_url",
                        "receiver": "QianLan",
                        "msgtype": "text",
                        "content": "URL 没配置",
                        "send_time": "2026-04-05 16:21:00",
                        "raw_payload": json.dumps(
                            {"decrypted_message": {"from": "wm_focus_missing_url", "tolist": ["QianLan"], "roomid": ""}},
                            ensure_ascii=False,
                        ),
                    }
                ]
            ) == 1
        finally:
            customer_profile_service.get_customer_profile_tags_payload = original_tags_payload

    with app.app_context():
        row = get_db().execute(
            """
            SELECT event_type, status, last_error, attempt_count, target_url
            FROM outbound_webhook_deliveries
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        assert row["event_type"] == "openclaw_focus_message"
        assert row["status"] == "failed"
        assert row["last_error"] == "webhook_not_configured"
        assert int(row["attempt_count"]) == 0
        assert row["target_url"] == ""


def test_activation_webhook_moves_inactive_pools_and_refreshes_active_pool(app, client, monkeypatch):
    _freeze_router_time(monkeypatch, timestamp="2026-04-05 15:05:00")
    seed = _save_default_signup_conversion_config(client, app, questionnaire_id=249)
    _seed_customer(
        app,
        external_userid="wm_activation_normal",
        mobile="13800138703",
        customer_name="未激活普通客户",
        owner_userid="sales_49",
        signup_status="lead",
        signup_label_name="报名引流品",
    )
    _create_questionnaire_submission(
        app,
        seed,
        submission_id=24901,
        external_userid="wm_activation_normal",
        mobile_snapshot="13800138703",
        hit_question_count=2,
        submitted_at="2026-04-05 15:00:00",
    )
    _seed_customer(
        app,
        external_userid="wm_activation_focus",
        mobile="13800138704",
        customer_name="未激活重点客户",
        owner_userid="sales_49",
        signup_status="lead",
        signup_label_name="报名引流品",
    )
    _create_questionnaire_submission(
        app,
        seed,
        submission_id=24902,
        external_userid="wm_activation_focus",
        mobile_snapshot="13800138704",
        hit_question_count=4,
        submitted_at="2026-04-05 15:01:00",
    )
    _seed_customer(
        app,
        external_userid="wm_activation_active",
        mobile="13800138705",
        customer_name="已激活客户",
        owner_userid="sales_49",
        signup_status="lead",
        signup_label_name="报名引流品",
    )
    _create_questionnaire_submission(
        app,
        seed,
        submission_id=24903,
        external_userid="wm_activation_active",
        mobile_snapshot="13800138705",
        hit_question_count=4,
        submitted_at="2026-04-05 15:02:00",
    )
    _seed_activation_source(app, mobile="13800138705", updated_at="2026-04-05 15:03:00")

    assert _persist_marketing_state(app, external_userid="wm_activation_normal")["stage_key"] == "pool/inactive_normal"
    assert _persist_marketing_state(app, external_userid="wm_activation_focus")["stage_key"] == "pool/inactive_focus"
    assert _persist_marketing_state(app, external_userid="wm_activation_active")["stage_key"] == "pool/active_focus"

    app.config["AUTOMATION_ACTIVATION_WEBHOOK_TOKEN"] = "activation-token"

    normal_response = client.post(
        "/api/customers/automation/activation-webhook",
        headers={"X-Automation-Token": "activation-token"},
        json={"mobile": "13800138703", "activated_at": "2026-04-05 15:10:00"},
    )
    focus_response = client.post(
        "/api/customers/automation/activation-webhook",
        headers={"X-Automation-Token": "activation-token"},
        json={"mobile": "13800138704", "activated_at": "2026-04-05 15:11:00"},
    )
    repeat_response = client.post(
        "/api/customers/automation/activation-webhook",
        headers={"X-Automation-Token": "activation-token"},
        json={"mobile": "13800138705", "activated_at": "2026-04-05 15:12:00"},
    )

    assert normal_response.status_code == 200
    assert normal_response.get_json()["marketing_state"]["stage_key"] == "pool/active_normal"
    assert normal_response.get_json()["marketing_state"]["last_activation_at"] == "2026-04-05 15:10:00"

    assert focus_response.status_code == 200
    assert focus_response.get_json()["marketing_state"]["stage_key"] == "pool/active_focus"
    assert focus_response.get_json()["marketing_state"]["last_activation_at"] == "2026-04-05 15:11:00"

    assert repeat_response.status_code == 200
    assert repeat_response.get_json()["marketing_state"]["stage_key"] == "pool/active_focus"
    assert repeat_response.get_json()["marketing_state"]["last_activation_at"] == "2026-04-05 15:12:00"


def test_activation_webhook_returns_error_when_mobile_not_found(app, client):
    app.config["AUTOMATION_ACTIVATION_WEBHOOK_TOKEN"] = "activation-token"

    response = client.post(
        "/api/customers/automation/activation-webhook",
        headers={"Authorization": "Bearer activation-token"},
        json={"mobile": "13800139999", "activated_at": "2026-04-05 15:20:00"},
    )

    assert response.status_code == 404
    assert response.get_json() == {"ok": False, "error": "customer not found by mobile"}


def test_activation_webhook_rejects_invalid_internal_token(app, client):
    app.config["AUTOMATION_INTERNAL_API_TOKEN"] = "internal-token"

    response = client.post(
        "/api/customers/automation/activation-webhook",
        headers={"Authorization": "Bearer wrong-token"},
        json={"mobile": "13800139999", "activated_at": "2026-04-05 18:00:00"},
    )

    assert response.status_code == 401
    assert response.get_json() == {"ok": False, "error": "invalid internal token"}
