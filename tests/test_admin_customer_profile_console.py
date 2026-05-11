from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from wecom_ability_service.db import get_db


@pytest.fixture()
def app(tmp_path):
    from tests.conftest import build_pg_test_app

    with build_pg_test_app(tmp_path, MCP_BEARER_TOKEN="mcp-token") as app:
        yield app


@pytest.fixture()
def client(app):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["admin_session_user_id"] = 0
        sess["admin_session_wecom_userid"] = ""
        sess["admin_session_role_list"] = ["super_admin"]
        sess["admin_session_login_type"] = "break_glass"
        sess["admin_session_display_name"] = "customer-test-admin"
        sess["admin_session_break_glass_username"] = "customer-test-admin"
    return client


class _FakeCustomerProfileContactClient:
    def __init__(self, *, detail: dict[str, object] | None = None, error: Exception | None = None) -> None:
        self._detail = detail or {
            "external_contact": {"external_userid": "ext-1", "name": "客户一"},
            "follow_user": [
                {
                    "userid": "owner-a",
                    "tags": [
                        {"tag_id": "tag-live-1", "tag_name": "实时标签一"},
                        {"tag_id": "tag-live-2", "tag_name": "实时标签二"},
                    ],
                }
            ],
        }
        self._error = error

    def get_contact(self, external_userid: str) -> dict[str, object]:
        if self._error:
            raise self._error
        assert external_userid == "ext-1"
        return dict(self._detail)


@pytest.fixture()
def fake_contact_client(monkeypatch):
    client = _FakeCustomerProfileContactClient()
    monkeypatch.setattr(
        "wecom_ability_service.domains.admin_console.customer_profile_service._customer_profile_contact_client",
        lambda: client,
    )
    return client


def _seed_customer_profile_fixture(app) -> None:
    with app.app_context():
        db = get_db()
        now = datetime.now().replace(microsecond=0)
        contact_updated_at = (now - timedelta(hours=6)).strftime("%Y-%m-%d %H:%M:%S")
        status_set_at = (now - timedelta(hours=5, minutes=50)).strftime("%Y-%m-%d %H:%M:%S")
        submission_1_at = (now - timedelta(hours=5, minutes=45)).strftime("%Y-%m-%d %H:%M:%S")
        submission_2_at = (now - timedelta(hours=5, minutes=40)).strftime("%Y-%m-%d %H:%M:%S")
        activation_at = (now - timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
        last_message_at = (now - timedelta(hours=5, minutes=25)).strftime("%Y-%m-%d %H:%M:%S")
        trial_opened_at = (now - timedelta(hours=5, minutes=35)).strftime("%Y-%m-%d %H:%M:%S")
        segment_evaluated_at = (now - timedelta(hours=5, minutes=28)).strftime("%Y-%m-%d %H:%M:%S")
        batch_window_start = (now - timedelta(hours=5, minutes=25)).strftime("%Y-%m-%d %H:%M:%S")
        batch_window_end = (now - timedelta(hours=5, minutes=15)).strftime("%Y-%m-%d %H:%M:%S")
        dispatch_at = (now - timedelta(hours=5, minutes=20)).strftime("%Y-%m-%d %H:%M:%S")
        db.execute(
            """
            INSERT INTO owner_role_map (userid, display_name, role, active)
            VALUES ('owner-a', '顾问甲', 'sales', true)
            """
        )
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
            VALUES ('ext-1', '客户一', 'owner-a', '重点客户', '客户描述', ?)
            """
            ,
            (contact_updated_at,),
        )
        db.execute(
            """
            INSERT INTO people (id, mobile, third_party_user_id, created_at, updated_at)
            VALUES (1, '13800138000', 'tp-1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
        db.execute(
            """
            INSERT INTO external_contact_bindings (
                external_userid, person_id, first_bound_by_userid, first_owner_userid, last_owner_userid, created_at, updated_at
            )
            VALUES ('ext-1', 1, 'owner-a', 'owner-a', 'owner-a', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
        db.execute(
            """
            INSERT INTO wecom_external_contact_identity_map (
                corp_id, external_userid, unionid, openid, follow_user_userid, name, status, raw_profile
            )
            VALUES ('ww-test', 'ext-1', 'union-1', 'openid-1', 'owner-a', '客户一', 'active', '{}')
            """
        )
        db.execute(
            """
            INSERT INTO wecom_external_contact_follow_users (
                corp_id, external_userid, user_id, relation_status, is_primary, remark, description, raw_follow_user
            )
            VALUES ('ww-test', 'ext-1', 'owner-a', 'active', true, '主跟进', '一线顾问', '{}')
            """
        )
        db.execute(
            """
            INSERT INTO class_user_status_current (
                external_userid, signup_status, signup_label_name, customer_name_snapshot, owner_userid_snapshot,
                mobile_snapshot, set_by_userid, set_at, wecom_tag_sync_status, wecom_tag_sync_error, status_flags_json
            )
            VALUES (
                'ext-1', 'lead', '报名引流品', '客户一', 'owner-a',
                '13800138000', 'owner-a', ?, 'success', '', '{}'
            )
            """,
            (status_set_at,),
        )
        db.execute(
            """
            INSERT INTO questionnaires (
                id, slug, name, title, description, is_disabled, redirect_url, created_at, updated_at
            )
            VALUES (1, 'q-1', '客户问卷', '客户问卷', '', false, '', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
        db.execute(
            """
            INSERT INTO questionnaire_submissions (
                id, questionnaire_id, respondent_key, openid, unionid, external_userid, follow_user_userid,
                matched_by, mobile_snapshot, total_score, final_tags, redirect_url_snapshot, submitted_at
            )
            VALUES
            (1, 1, 'resp-1', 'openid-1', 'union-1', 'ext-1', 'owner-a', 'openid', '13800138000', 80, '[]', '', ?),
            (2, 1, 'resp-2', 'openid-1', 'union-1', 'ext-1', 'owner-a', 'openid', '13800138000', 90, '[]', '', ?)
            """,
            (submission_1_at, submission_2_at),
        )
        db.execute(
            """
            INSERT INTO questionnaire_submission_answers (
                submission_id, question_id, question_type, question_title_snapshot,
                selected_option_ids, selected_option_texts_snapshot, selected_option_scores_snapshot,
                selected_option_tags_snapshot, text_value, score_contribution, created_at
            )
            VALUES
            (1, 1, 'textarea', '你现在最关注什么？', '[]', '[]', '[]', '[]', '想看课程安排', 0, CURRENT_TIMESTAMP),
            (2, 2, 'single_choice', '你当前在哪个阶段？', '[1]', '[\"已报名999\"]', '[10]', '[\"tag-999\"]', '', 10, CURRENT_TIMESTAMP)
            """
        )
        db.execute(
            """
            INSERT INTO customer_marketing_state_current (
                person_id, external_userid, automation_key, main_stage, sub_stage, activated, converted,
                eligible_for_conversion, lifecycle_status, last_activation_at, last_conversion_marked_at,
                last_message_at, last_batch_id, last_batch_status, last_batch_window_start, last_batch_window_end,
                last_trigger_message_at, entered_at, exited_at, exit_reason, state_payload_json, created_at, updated_at
            )
            VALUES (
                1, 'ext-1', 'signup_conversion_v1', 'pool', 'active_focus', true, false, true, 'pool',
                ?, '', ?, NULL, '', '', '',
                ?, ?, NULL, '',
                ?,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """,
            (
                activation_at,
                last_message_at,
                last_message_at,
                activation_at,
                '{"followup_segment":"focus","questionnaire_segment":"top","trial_opened":true,"trial_opened_at":"%s"}'
                % trial_opened_at,
            ),
        )
        db.execute(
            """
            INSERT INTO customer_value_segment_current (
                external_userid, segment, segment_rank, score, scoring_version, computed_reason, submission_id,
                matched_question_ids_json, source_payload_json, evaluated_at, computed_at, created_at, updated_at
            )
            VALUES (
                'ext-1', 'top', 3, 4, 'signup_conversion_question_hits_v1', 'seed', 2,
                '[1,2,3,4]', '{}', ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """,
            (segment_evaluated_at, segment_evaluated_at),
        )
        db.execute(
            """
            INSERT INTO message_batches (
                id, batch_key, window_start, window_end, status, message_count, created_at
            )
            VALUES (9001, 'seed-batch-9001', ?, ?, 'acked', 1, CURRENT_TIMESTAMP)
            """,
            (batch_window_start, batch_window_end),
        )
        db.execute(
            """
            INSERT INTO conversion_dispatch_log (
                automation_key, batch_id, external_userid, dispatch_status, dispatch_channel,
                dispatch_payload_json, dispatch_note, dispatched_at, acked_at, created_at, updated_at
            )
            VALUES (
                'signup_conversion_v1', 9001, 'ext-1', 'sent', 'text_message', '{}',
                'seed dispatch', ?, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """,
            (dispatch_at,),
        )

        started_at = now - timedelta(hours=6)
        for index in range(1, 36):
            send_time = started_at + timedelta(minutes=index)
            sender = "owner-a" if index % 2 else "ext-1"
            db.execute(
                """
                INSERT INTO archived_messages (
                    seq, msgid, chat_type, external_userid, owner_userid, sender, receiver, msgtype, content, send_time, raw_payload, created_at
                )
                VALUES (?, ?, 'private', 'ext-1', 'owner-a', ?, ?, 'text', ?, ?, '{}', ?)
                """,
                (
                    index,
                    f"msg-{index}",
                    sender,
                    "ext-1" if sender == "owner-a" else "owner-a",
                    f"消息{index}",
                    send_time.strftime("%Y-%m-%d %H:%M:%S"),
                    send_time.strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )
        db.commit()


def test_admin_customer_list_page_is_search_focused(app, client):
    _seed_customer_profile_fixture(app)

    response = client.get("/admin/customers")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "客户查找" in html
    assert "关键词" in html
    assert "负责人" in html
    assert "手机号" in html
    assert "标签" in html
    assert 'name="status"' not in html
    assert 'name="tag"' in html
    assert 'name="is_bound"' not in html
    assert 'name="limit"' not in html
    assert "最近消息" not in html
    assert "更新时间" not in html
    assert "查看档案" in html
    assert "客户编号：ext-1" in html


def test_admin_customer_profile_page_renders_profile_sections_without_tabs(app, client, fake_contact_client):
    _seed_customer_profile_fixture(app)

    response = client.get("/admin/customers/ext-1?tab=questionnaires")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "客户档案" in html
    assert "实时标签" in html
    assert "已填写问卷及答案" in html
    assert "聊天记录" in html
    assert "获取全部聊天记录" in html
    assert "自动化转化" in html
    assert "这里专门处理当前客户的自动化状态与快捷动作" in html
    assert "是否在自动化池" in html
    assert "当前池子" in html
    assert "当前阶段" in html
    assert "当前目标" in html
    assert "问卷状态" in html
    assert "最近人工操作" in html
    assert "最近 AI 推送时间" in html
    assert "冷却状态" in html
    assert "放入自动化转化池" in html
    assert "移除自动化转化池" in html
    assert "转化为重点跟进" in html
    assert "转化为普通跟进" in html
    assert "确认已成交" in html
    assert "移除已成交" in html
    assert "一键自动化写话术" in html
    assert "外部联系人 ID" in html
    assert "unionid" in html
    assert "营销状态 / 自动化转化" not in html
    assert "当前跟进类型" not in html
    assert "命中题数" not in html
    assert "是否进入自动化" not in html
    assert "最近激活时间" not in html
    assert "最近确认成交时间" not in html
    assert "release-test-sha" not in html
    assert "运行正常" not in html


def test_admin_customer_profile_page_renders_marketing_summary_placeholders(app, client, fake_contact_client):
    _seed_customer_profile_fixture(app)

    with app.app_context():
        db = get_db()
        db.execute("DELETE FROM customer_marketing_state_current WHERE external_userid = 'ext-1'")
        db.execute("DELETE FROM customer_value_segment_current WHERE external_userid = 'ext-1'")
        db.execute("DELETE FROM conversion_dispatch_log WHERE external_userid = 'ext-1'")
        db.commit()

    response = client.get("/admin/customers/ext-1")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "自动化转化" in html
    assert "是否在自动化池" in html
    assert "当前池子" in html
    assert "当前阶段" in html
    assert "当前目标" in html
    assert "最近人工操作" in html
    assert "最近 AI 推送时间" in html
    assert "营销状态 / 自动化转化" not in html
    assert "当前跟进类型" not in html
    assert "命中题数" not in html


def test_customer_profile_tags_failure_does_not_break_page(app, client, monkeypatch):
    _seed_customer_profile_fixture(app)
    monkeypatch.setattr(
        "wecom_ability_service.domains.admin_console.customer_profile_service._customer_profile_contact_client",
        lambda: _FakeCustomerProfileContactClient(error=RuntimeError("boom")),
    )

    page_response = client.get("/admin/customers/ext-1")
    tags_response = client.get("/api/admin/customers/profile/tags", query_string={"external_userid": "ext-1"})

    assert page_response.status_code == 200
    assert "客户档案" in page_response.get_data(as_text=True)
    assert tags_response.status_code == 200
    payload = tags_response.get_json()
    assert payload["ok"] is False
    assert payload["error"] == "当前无法加载实时标签"
    with app.app_context():
        tag_count = get_db().execute("SELECT COUNT(*) AS total FROM contact_tags").fetchone()["total"]
    assert tag_count == 0


def test_customer_profile_questionnaire_answers_api_returns_flat_rows(app, client, fake_contact_client):
    _seed_customer_profile_fixture(app)

    response = client.get(
        "/api/admin/customers/profile/questionnaire-answers",
        query_string={"mobile": "13800138000"},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["count"] == 2
    assert [item["question"] for item in payload["answers"]] == ["你当前在哪个阶段？", "你现在最关注什么？"]
    assert [item["answer"] for item in payload["answers"]] == ["已报名999", "想看课程安排"]


def test_customer_profile_messages_api_defaults_to_recent_30_and_supports_fetch_all(app, client, fake_contact_client):
    _seed_customer_profile_fixture(app)

    recent_response = client.get(
        "/api/admin/customers/profile/messages",
        query_string={"external_userid": "ext-1"},
    )
    all_response = client.get(
        "/api/admin/customers/profile/messages",
        query_string={"external_userid": "ext-1", "fetch_all": "1"},
    )

    recent_payload = recent_response.get_json()
    all_payload = all_response.get_json()

    assert recent_response.status_code == 200
    assert recent_payload["ok"] is True
    assert recent_payload["count"] == 30
    assert recent_payload["messages"][0]["content"] == "消息6"
    assert recent_payload["messages"][-1]["content"] == "消息35"

    assert all_response.status_code == 200
    assert all_payload["ok"] is True
    assert all_payload["count"] == 35
    assert all_payload["messages"][0]["content"] == "消息1"
    assert all_payload["messages"][-1]["content"] == "消息35"


def test_customer_profile_api_supports_external_userid_mobile_and_reserved_user_id(app, client, fake_contact_client):
    _seed_customer_profile_fixture(app)

    by_external_userid = client.get("/api/admin/customers/profile", query_string={"external_userid": "ext-1"})
    by_mobile = client.get("/api/admin/customers/profile", query_string={"mobile": "13800138000"})
    by_user_id = client.get("/api/admin/customers/profile", query_string={"user_id": "ext-1"})

    external_payload = by_external_userid.get_json()
    mobile_payload = by_mobile.get_json()
    user_id_payload = by_user_id.get_json()

    assert by_external_userid.status_code == 200
    assert external_payload["profile"]["user_id"] == "ext-1"
    assert external_payload["lookup"]["resolved_by"] == "external_userid"
    assert external_payload["profile"]["marketing_profile"]["marketing_state"]["marketing_phase"] == "awaiting_trigger"

    assert by_mobile.status_code == 200
    assert mobile_payload["profile"]["external_userid"] == "ext-1"
    assert mobile_payload["lookup"]["resolved_by"] == "mobile"

    assert by_user_id.status_code == 200
    assert user_id_payload["profile"]["external_userid"] == "ext-1"
    assert user_id_payload["lookup"]["resolved_by"] == "user_id_fallback_external_userid"


