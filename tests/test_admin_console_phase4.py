from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timedelta

import pytest

from wecom_ability_service.db import get_db
from wecom_ability_service.infra.settings import set_settings


@pytest.fixture()
def app(tmp_path):
    from tests.conftest import build_pg_test_app

    with build_pg_test_app(
        tmp_path,
        WECOM_CALLBACK_TOKEN="callback-token",
        WECOM_CALLBACK_AES_KEY="abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
        MCP_BEARER_TOKEN="mcp-token",
    ) as app:
        yield app


@pytest.fixture()
def client(app):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["admin_session_user_id"] = 0
        sess["admin_session_wecom_userid"] = ""
        sess["admin_session_role_list"] = ["super_admin"]
        sess["admin_session_login_type"] = "break_glass"
        sess["admin_session_display_name"] = "phase4-test-admin"
        sess["admin_session_break_glass_username"] = "phase4-test-admin"
    return client


def _seed_phase4_data(app) -> None:
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO owner_role_map (userid, display_name, role, active)
            VALUES ('owner-a', '顾问甲', 'sales', true)
            """
        )
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
            VALUES ('ext-1', '客户一', 'owner-a', '高意向', '主客户档案', '2026-04-02 09:30:00')
            """
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
            INSERT INTO contact_tags (external_userid, userid, tag_id, tag_name)
            VALUES
              ('ext-1', 'owner-a', 'tag-1', 'AI产品报名'),
              ('ext-1', 'owner-a', 'tag-999', '已报名999')
            """
        )
        db.execute(
            """
            INSERT INTO class_user_status_current (
                external_userid, signup_status, signup_label_name, customer_name_snapshot, owner_userid_snapshot,
                mobile_snapshot, set_by_userid, set_at, wecom_tag_sync_status, wecom_tag_sync_error, status_flags_json
            )
            VALUES (
                'ext-1', 'signed_999', '已报名999', '客户一', 'owner-a',
                '13800138000', 'owner-a', '2026-04-02 10:00:00', 'success', '', '{}'
            )
            """
        )
        db.execute(
            """
            INSERT INTO class_user_status_history (
                external_userid, old_signup_status, new_signup_status, old_label_name, new_label_name,
                customer_name_snapshot, owner_userid_snapshot, mobile_snapshot, set_by_userid, set_at,
                wecom_tag_sync_status, wecom_tag_sync_error, status_flags_json, created_at
            )
            VALUES (
                'ext-1', 'lead', 'signed_999', '报名引流品', '已报名999',
                '客户一', 'owner-a', '13800138000', 'owner-a', '2026-04-02 10:00:00',
                'success', '', '{}', '2026-04-02 10:00:00'
            )
            """
        )
        db.execute(
            """
            INSERT INTO archived_messages (
                seq, msgid, chat_type, external_userid, owner_userid, sender, receiver, msgtype, content, send_time, raw_payload, created_at
            )
            VALUES (
                1, 'msg-1', 'private', 'ext-1', 'owner-a', 'owner-a', 'ext-1', 'text', '你好，欢迎咨询',
                '2026-04-02 10:05:00', '{}', '2026-04-02 10:05:00'
            )
            """
        )
        db.execute(
            """
            INSERT INTO outbound_tasks (task_type, request_payload, response_payload, wecom_task_id, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "private_message",
                json.dumps(
                    {
                        "chat_type": "single",
                        "external_userid": ["ext-1"],
                        "sender": ["owner-a"],
                        "text": {"content": "测试触达"},
                    },
                    ensure_ascii=False,
                ),
                json.dumps({"errcode": 0, "errmsg": "ok"}, ensure_ascii=False),
                "task-1",
                "created",
                "2026-04-02 10:06:00",
            ),
        )
        db.execute(
            """
            INSERT INTO questionnaires (
                id, slug, name, title, description, is_disabled, redirect_url, created_at, updated_at
            )
            VALUES (1, 'q-1', 'q-1', '客户问卷', '问卷描述', false, '', '2026-04-02 09:00:00', '2026-04-02 09:20:00')
            """
        )
        db.execute(
            """
            INSERT INTO questionnaire_questions (
                id, questionnaire_id, type, title, required, sort_order, created_at, updated_at
            )
            VALUES (1, 1, 'single_choice', '当前阶段', true, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
        db.execute(
            """
            INSERT INTO questionnaire_options (
                id, question_id, option_text, score, tag_codes, sort_order, created_at, updated_at
            )
            VALUES (1, 1, '已报名999', 10, '[\"tag-999\"]', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
        db.execute(
            """
            INSERT INTO questionnaire_score_rules (
                questionnaire_id, min_score, max_score, tag_codes, sort_order, created_at, updated_at
            )
            VALUES (1, 0, 100, '[\"tag-999\"]', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
        db.execute(
            """
            INSERT INTO questionnaire_submissions (
                id, questionnaire_id, respondent_key, openid, unionid, external_userid, follow_user_userid,
                matched_by, mobile_snapshot, total_score, final_tags, redirect_url_snapshot, submitted_at
            )
            VALUES (
                1, 1, 'resp-1', 'openid-1', 'union-1', 'ext-1', 'owner-a',
                'openid', '13800138000', 88, '[\"tag-999\"]', '', '2026-04-02 10:10:00'
            )
            """
        )
        db.execute(
            """
            INSERT INTO questionnaire_submission_answers (
                submission_id, question_id, question_type, question_title_snapshot,
                selected_option_ids, selected_option_texts_snapshot, selected_option_scores_snapshot,
                selected_option_tags_snapshot, text_value, score_contribution, created_at
            )
            VALUES (
                1, 1, 'single_choice', '当前阶段',
                '[1]', '[\"已报名999\"]', '[10]', '[\"tag-999\"]', '', 10, CURRENT_TIMESTAMP
            )
            """
        )
        db.execute(
            """
            INSERT INTO questionnaire_scrm_apply_logs (
                submission_id, external_userid, follow_user_userid, final_tags, status, error_message, created_at
            )
            VALUES (1, 'ext-1', 'owner-a', '[\"tag-999\"]', 'success', '', '2026-04-02 10:11:00')
            """
        )
        db.execute(
            """
            INSERT INTO questionnaire_external_push_logs (
                questionnaire_id, questionnaire_title_snapshot, submission_record_id, user_id, target_url,
                request_payload, response_status_code, response_body, status, failure_reason, created_at, updated_at
            )
            VALUES (
                1, '客户问卷', 1, 'resp-1', 'https://hooks.example.com/apply',
                '{"user_id":"resp-1","questionnaire_title":"客户问卷","submitted_at":"2026-04-02T10:10:00+08:00","answers":[{"title":"当前阶段","answer":"已报名999"}]}',
                500, '{"error":"server exploded"}', 'failed', 'HTTP 500', '2026-04-02 10:12:00', '2026-04-02 10:12:00'
            )
            """
        )
        db.execute(
            """
            INSERT INTO user_ops_lead_pool_current (
                mobile, external_userid, customer_name, owner_userid, is_wecom_added, is_mobile_bound,
                huangxiaocan_activation_state, class_term_no, class_term_label, first_entry_source, last_entry_source, created_at, updated_at
            )
            VALUES (
                '13800138000', 'ext-1', '客户一', 'owner-a', true, true,
                'activated', 1, '1期', 'student_import', 'student_import', '2026-04-02 09:40:00', '2026-04-02 09:45:00'
            )
            """
        )
        db.execute(
            """
            INSERT INTO user_ops_lead_pool_history (
                mobile, external_userid, action_type, source_type, operator, before_json, after_json, remark, created_at
            )
            VALUES (
                '13800138000', 'ext-1', 'lead_pool_insert', 'student_import', 'owner-a', '{}', '{}', 'seed', '2026-04-02 09:45:00'
            )
            """
        )
        db.execute(
            """
            INSERT INTO user_ops_import_batches (
                import_type, file_name, total_rows, success_rows, failed_rows, error_summary, created_by, created_at
            )
            VALUES ('class_term_source', 'seed.csv', 1, 1, 0, '', 'owner-a', '2026-04-02 09:42:00')
            """
        )
        db.execute(
            """
            INSERT INTO user_ops_deferred_jobs (
                job_type, external_userid, owner_userid, run_after, status, attempt_count, payload_json, result_json, created_at, updated_at
            )
            VALUES (
                'verify_class_term_tag_and_upsert_lead_pool', 'ext-1', 'owner-a', '2026-04-02 11:00:00', 'pending', 0, '{}', '{}', '2026-04-02 10:20:00', '2026-04-02 10:20:00'
            )
            """
        )
        db.commit()


def test_admin_customers_pages_render_as_search_and_profile(app, client):
    _seed_phase4_data(app)

    list_response = client.get("/admin/customers")
    detail_response = client.get("/admin/customers/ext-1?tab=questionnaires")

    assert list_response.status_code == 200
    list_html = list_response.get_data(as_text=True)
    assert "客户查找" in list_html
    assert "查看档案" in list_html
    assert "name=\"status\"" not in list_html
    assert "name=\"tag\"" in list_html
    assert "最近消息" not in list_html
    assert "更新时间" not in list_html

    detail_html = detail_response.get_data(as_text=True)
    assert detail_response.status_code == 200
    assert "客户档案" in detail_html
    assert "实时标签" in detail_html
    assert "问卷记录" in detail_html
    assert "聊天记录" in detail_html
    assert "互动记录" not in detail_html
    assert "高级信息" not in detail_html


def test_admin_customer_detail_tag_preview_is_dry_run(app, client):
    _seed_phase4_data(app)

    response = client.post(
        "/admin/customers/ext-1/tags",
        data={
            "return_tab": "tags",
            "tag_action": "mark",
            "userid": "owner-a",
            "tag_ids": "tag-2,tag-3",
        },
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "这里会先展示操作预览，确认后才会真正执行。" in html
    assert '"would_execute": true' in html
    assert "tag-2" in html


def test_admin_questionnaire_pages_render_detail_sections(app, client):
    _seed_phase4_data(app)

    list_response = client.get("/admin/questionnaires")
    detail_response = client.get("/admin/questionnaires/1")
    external_push_logs_response = client.get("/admin/questionnaires/1/external-push-logs?status=failed&limit=10")

    list_html = list_response.get_data(as_text=True)
    detail_html = detail_response.get_data(as_text=True)
    external_push_logs_html = external_push_logs_response.get_data(as_text=True)

    assert list_response.status_code == 200
    assert "问卷管理" in list_html
    assert "创建新问卷" in list_html
    assert "问卷名称" in list_html
    assert "提交数" in list_html
    assert "/s/q-1" in list_html

    assert detail_response.status_code == 200
    assert "编辑问卷" in detail_html
    assert "返回问卷管理" in detail_html
    assert "题型" in detail_html
    assert "删除此问卷" in detail_html or "删除" in detail_html
    assert "下载数据" in detail_html
    assert "开启外部推送" in detail_html
    assert "外推记录" in detail_html

    assert external_push_logs_response.status_code == 200
    assert "问卷外部推送记录" in external_push_logs_html
    assert "仅待补发" in external_push_logs_html
    assert "HTTP 500" in external_push_logs_html
    assert "https://hooks.example.com/apply" in external_push_logs_html
    assert "补发" in external_push_logs_html


def test_admin_questionnaire_external_push_logs_show_retry_result(app, client):
    _seed_phase4_data(app)

    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO questionnaire_external_push_logs (
                questionnaire_id, questionnaire_title_snapshot, submission_record_id, retry_from_log_id, retry_attempt,
                user_id, target_url, request_payload, response_status_code, response_body, status, failure_reason,
                created_at, updated_at
            )
            VALUES (
                1, '客户问卷', 1, 1, 1,
                'resp-1', 'https://hooks.example.com/apply',
                '{"user_id":"resp-1","questionnaire_title":"客户问卷","submitted_at":"2026-04-02T10:10:00+08:00","answers":[{"title":"当前阶段","answer":"已报名999"}]}',
                200, '{"ok":true}', 'success', '', '2026-04-02 10:20:00', '2026-04-02 10:20:00'
            )
            """
        )
        db.commit()

    response = client.get("/admin/questionnaires/1/external-push-logs?status=success&limit=10")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "补发成功" in html
    assert "第 1 次补发" in html
    assert "仅当前成功" in html


def test_admin_questionnaire_external_push_logs_failed_current_filter_hides_recovered_items(app, client):
    _seed_phase4_data(app)

    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO questionnaire_external_push_logs (
                questionnaire_id, questionnaire_title_snapshot, submission_record_id, retry_from_log_id, retry_attempt,
                user_id, target_url, request_payload, response_status_code, response_body, status, failure_reason,
                created_at, updated_at
            )
            VALUES (
                1, '客户问卷', 1, 1, 1,
                'resp-1', 'https://hooks.example.com/apply',
                '{"user_id":"resp-1","questionnaire_title":"客户问卷","submitted_at":"2026-04-02T10:10:00+08:00","answers":[{"title":"当前阶段","answer":"已报名999"}]}',
                200, '{"ok":true}', 'success', '', '2026-04-02 10:20:00', '2026-04-02 10:20:00'
            )
            """
        )
        db.execute(
            """
            INSERT INTO questionnaire_external_push_logs (
                questionnaire_id, questionnaire_title_snapshot, submission_record_id, user_id, target_url,
                request_payload, response_status_code, response_body, status, failure_reason, created_at, updated_at
            )
            VALUES (
                1, '客户问卷', 1, 'resp-2', 'https://hooks.example.com/apply',
                '{"user_id":"resp-2","questionnaire_title":"客户问卷","submitted_at":"2026-04-02T10:10:00+08:00","answers":[{"title":"当前阶段","answer":"已报名999"}]}',
                500, '{"error":"server exploded again"}', 'failed', 'HTTP 500', '2026-04-02 10:30:00', '2026-04-02 10:30:00'
            )
            """
        )
        db.commit()

    response = client.get("/admin/questionnaires/1/external-push-logs?status=failed_current&limit=10")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "仅待补发" in html
    assert "补发成功" not in html
    assert "首发失败（待补发）" in html


def test_admin_questionnaire_global_external_push_logs_page_supports_filters(app, client):
    _seed_phase4_data(app)

    with app.app_context():
        db = get_db()
        set_settings({"QUESTIONNAIRE_EXTERNAL_PUSH_GLOBAL_ENABLED": "false"})
        now = datetime.now()
        recent_success = now.strftime("%Y-%m-%d %H:%M:%S")
        recent_failed = (now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        db.execute(
            """
            INSERT INTO questionnaires (
                id, slug, name, title, description, is_disabled, redirect_url, created_at, updated_at
            )
            VALUES (2, 'q-2', 'q-2', '另一份问卷', '第二份问卷', false, '', '2026-04-03 09:00:00', '2026-04-03 09:20:00')
            """
        )
        db.execute(
            """
            INSERT INTO questionnaire_submissions (
                id, questionnaire_id, respondent_key, openid, unionid, external_userid, follow_user_userid,
                matched_by, mobile_snapshot, total_score, final_tags, redirect_url_snapshot, submitted_at
            )
            VALUES (
                2, 2, 'resp-2', 'openid-2', 'union-2', 'ext-1', 'owner-a',
                'openid', '13800138111', 60, '[]', '', '2026-04-03 10:10:00'
            )
            """
        )
        db.execute(
            """
            INSERT INTO questionnaire_external_push_logs (
                questionnaire_id, questionnaire_title_snapshot, submission_record_id, user_id, target_url,
                request_payload, response_status_code, response_body, status, failure_reason, created_at, updated_at
            )
            VALUES (
                2, '另一份问卷', 2, 'resp-2', 'https://hooks.example.com/other',
                '{"user_id":"resp-2","questionnaire_title":"另一份问卷","submitted_at":"2026-04-03T10:10:00+08:00","answers":[]}',
                200, '{"ok":true}', 'success', '', ?, ?
            )
            """,
            (recent_success, recent_success),
        )
        db.execute(
            """
            INSERT INTO questionnaire_external_push_logs (
                questionnaire_id, questionnaire_title_snapshot, submission_record_id, user_id, target_url,
                request_payload, response_status_code, response_body, status, failure_reason, created_at, updated_at
            )
            VALUES (
                2, '另一份问卷', 2, 'resp-3', 'https://hooks.example.com/other',
                '{"user_id":"resp-3","questionnaire_title":"另一份问卷","submitted_at":"2026-04-03T10:20:00+08:00","answers":[]}',
                500, '{"error":"recent failed"}', 'failed', 'HTTP 500', ?, ?
            )
            """,
            (recent_failed, recent_failed),
        )
        db.commit()

    response = client.get("/admin/questionnaires/external-push-logs?questionnaire_title=客户问卷&status=failed_current&limit=10")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "全局问卷外部推送总览" in html
    assert "仅待补发" in html
    assert "客户问卷" in html
    assert "另一份问卷" not in html
    assert "当前待补发" in html
    assert "已关闭（止损中）" in html
    assert "最近 24h 成功" in html
    assert "最近 24h 失败" in html
    assert "已开启外推问卷" in html


def test_admin_questionnaire_global_external_push_logs_support_retry_actions(app, client, monkeypatch):
    _seed_phase4_data(app)

    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO questionnaire_external_push_logs (
                questionnaire_id, questionnaire_title_snapshot, submission_record_id, user_id, target_url,
                request_payload, response_status_code, response_body, status, failure_reason, created_at, updated_at
            )
            VALUES (
                1, '客户问卷', 1, 'resp-2', 'https://hooks.example.com/apply',
                '{"user_id":"resp-2","questionnaire_title":"客户问卷","submitted_at":"2026-04-02T10:30:00+08:00","answers":[]}',
                500, '{"error":"still failed"}', 'failed', 'HTTP 500', '2026-04-02 10:30:00', '2026-04-02 10:30:00'
            )
            """
        )
        db.execute(
            """
            INSERT INTO questionnaire_external_push_logs (
                questionnaire_id, questionnaire_title_snapshot, submission_record_id, user_id, target_url,
                request_payload, response_status_code, response_body, status, failure_reason, created_at, updated_at
            )
            VALUES (
                1, '客户问卷', 1, 'resp-3', 'https://hooks.example.com/apply',
                '{"user_id":"resp-3","questionnaire_title":"客户问卷","submitted_at":"2026-04-02T10:40:00+08:00","answers":[]}',
                500, '{"error":"failed again"}', 'failed', 'HTTP 500', '2026-04-02 10:40:00', '2026-04-02 10:40:00'
            )
            """
        )
        db.commit()

    responses = [
        type("Resp", (), {"status_code": 200, "text": '{"ok":true}'})(),
        type("Resp", (), {"status_code": 200, "text": '{"ok":true}'})(),
        type("Resp", (), {"status_code": 502, "text": '{"error":"bad gateway"}'})(),
    ]

    def fake_push_post(url, json=None, headers=None, timeout=None):
        return responses.pop(0)

    monkeypatch.setattr("wecom_ability_service.domains.questionnaire.service.requests.post", fake_push_post)

    single_retry_response = client.post(
        "/admin/questionnaires/external-push-logs/1/retry",
        data={"status": "failed_current", "limit": "10", "questionnaire_title": "客户问卷"},
        follow_redirects=True,
    )
    single_html = single_retry_response.get_data(as_text=True)

    assert single_retry_response.status_code == 200
    assert "补发已执行，请查看最近结果。" in single_html
    assert "补发成功" in single_html

    batch_retry_response = client.post(
        "/admin/questionnaires/external-push-logs/retry-batch",
        data={
            "status": "failed_current",
            "limit": "10",
            "questionnaire_title": "客户问卷",
            "push_log_ids": ["2", "3"],
        },
        follow_redirects=True,
    )
    batch_html = batch_retry_response.get_data(as_text=True)

    assert batch_retry_response.status_code == 200
    assert "批量补发已执行：选中 2 条，实际补发 2 条，成功 1 条，失败 1 条。" in batch_html

    with app.app_context():
        rows = get_db().execute(
            """
            SELECT retry_from_log_id, retry_attempt, status, response_status_code
            FROM questionnaire_external_push_logs
            WHERE retry_from_log_id IS NOT NULL
            ORDER BY id ASC
            """
        ).fetchall()
        assert len(rows) == 3
        assert rows[0]["status"] == "success"
        assert rows[1]["status"] == "success"
        assert rows[2]["status"] == "failed"
        assert int(rows[2]["response_status_code"]) == 502


def test_admin_operations_page_and_migrate_action_are_audited(app, client):
    _seed_phase4_data(app)

    # /admin/user-ops is sunset (410)
    page_response = client.get("/admin/user-ops")
    assert page_response.status_code == 410
