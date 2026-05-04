from __future__ import annotations

import json
from datetime import datetime as real_datetime
from pathlib import Path

import pytest

from wecom_ability_service import create_app
from wecom_ability_service.db import get_db, init_db
from wecom_ability_service.domains.marketing_automation import service as marketing_automation_service


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http error: {self.status_code}")


def fake_wecom_get(url, params=None, timeout=None):
    if url.endswith("/cgi-bin/gettoken"):
        return FakeResponse({"errcode": 0, "errmsg": "ok", "access_token": "token-123", "expires_in": 7200})
    if url.endswith("/cgi-bin/externalcontact/get_follow_user_list"):
        return FakeResponse({"errcode": 0, "errmsg": "ok", "follow_user": ["sales_01"]})
    if url.endswith("/cgi-bin/externalcontact/list"):
        return FakeResponse({"errcode": 0, "errmsg": "ok", "external_userid": ["wm_ext_001"]})
    if url.endswith("/cgi-bin/externalcontact/get"):
        return FakeResponse(
            {
                "errcode": 0,
                "errmsg": "ok",
                "external_contact": {
                    "external_userid": "wm_ext_001",
                    "name": "周青",
                    "unionid": "union-001",
                    "type": 1,
                    "gender": 2,
                    "avatar": "https://example.com/001.png",
                },
                "follow_user": [{"userid": "sales_01", "remark": "老同学介绍", "description": "wm_ext_001"}],
            }
        )
    raise AssertionError(f"unexpected GET url: {url}")


def fake_wecom_post(url, params=None, json=None, timeout=None):
    if url.endswith("/cgi-bin/externalcontact/get_corp_tag_list"):
        return FakeResponse(
            {
                "errcode": 0,
                "errmsg": "ok",
                "tag_group": [
                    {
                        "group_id": "group-001",
                        "group_name": "客户分层",
                        "tag": [{"id": "et-tag-001", "name": "高意向"}],
                    }
                ],
            }
        )
    if url.endswith("/cgi-bin/externalcontact/mark_tag"):
        return FakeResponse({"errcode": 0, "errmsg": "ok"})
    if url.endswith("/cgi-bin/externalcontact/add_msg_template"):
        return FakeResponse({"errcode": 0, "errmsg": "ok", "msgid": "task-msg-001"})
    if url.endswith("/cgi-bin/externalcontact/add_moment_task"):
        return FakeResponse({"errcode": 0, "errmsg": "ok", "jobid": "moment-job-001"})
    raise AssertionError(f"unexpected POST url: {url}")


@pytest.fixture()
def app(tmp_path):
    db_path = tmp_path / "contract.sqlite3"
    private_key_path = tmp_path / "wecom_private_key.pem"
    sdk_lib_path = tmp_path / "libWeWorkFinanceSdk_C.so"
    private_key_path.write_text("fake-key", encoding="utf-8")
    sdk_lib_path.write_text("fake-so", encoding="utf-8")
    app = create_app(
        {
            "TESTING": True,
            "DATABASE_PATH": str(db_path),
            "RELEASE_SHA": "contract-release-sha",
            "WECOM_CORP_ID": "ww-test",
            "WECOM_CONTACT_SECRET": "contact-secret-test",
            "WECOM_SECRET": "secret-test",
            "WECOM_AGENT_ID": "1000002",
            "WECOM_ARCHIVE_SECRET": "archive-secret",
            "WECOM_API_BASE": "http://fake-wecom.local",
            "WECOM_PRIVATE_KEY_PATH": str(private_key_path),
            "WECOM_SDK_LIB_PATH": str(sdk_lib_path),
            "WECOM_CALLBACK_TOKEN": "callback-token",
            "WECOM_CALLBACK_AES_KEY": "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
            "MCP_BEARER_TOKEN": "mcp-token",
        }
    )
    with app.app_context():
        init_db()
        db = get_db()
        db.execute(
            """
            INSERT INTO archived_messages
            (seq, msgid, chat_type, external_userid, owner_userid, sender, receiver, msgtype, content, send_time, raw_payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                21,
                "contract-msg-001",
                "private",
                "wm_ext_001",
                "sales_01",
                "wm_ext_001",
                "sales_01",
                "text",
                "契约消息",
                "2026-03-20 12:12:00",
                '{"decrypted_message":{"from":"wm_ext_001","tolist":["sales_01"],"roomid":"","msgtype":"text"}}',
            ),
        )
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("wm_ext_001", "周青", "sales_01", "老同学介绍", "wm_ext_001"),
        )
        db.execute(
            """
            INSERT INTO people (mobile, third_party_user_id)
            VALUES (?, ?)
            """,
            ("13800138000", "tp-001"),
        )
        person_id = db.execute("SELECT id FROM people WHERE mobile = ?", ("13800138000",)).fetchone()["id"]
        db.execute(
            """
            INSERT INTO external_contact_bindings (
                external_userid, person_id, first_bound_by_userid, first_owner_userid, last_owner_userid
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            ("wm_ext_001", person_id, "sales_01", "sales_01", "sales_01"),
        )
        db.execute(
            """
            INSERT INTO wecom_external_contact_identity_map (
                corp_id, external_userid, unionid, openid, follow_user_userid, name, status, raw_profile
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("ww-test", "wm_ext_001", "union-001", "", "sales_01", "周青", "active", "{}"),
        )
        db.execute(
            """
            INSERT INTO class_user_status_current (
                external_userid, signup_status, signup_label_name, customer_name_snapshot,
                owner_userid_snapshot, mobile_snapshot, set_by_userid, wecom_tag_sync_status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("wm_ext_001", "signed_999", "已报名999", "周青", "sales_01", "13800138000", "sales_01", "success"),
        )
        db.commit()
    yield app


@pytest.fixture()
def client(app):
    return app.test_client()


def test_contract_health_and_ops(client):
    assert client.get("/health").status_code == 200
    ops_response = client.get("/api/ops/status", headers={"X-Request-Id": "contract-request-id"})
    data = ops_response.get_json()
    assert ops_response.status_code == 200
    assert {"ok", "service_ok", "archived_messages_count", "contacts_count", "group_chats_count", "last_seq"} <= set(data.keys())
    assert {
        "request_id",
        "release_sha",
        "app_started_at",
        "uptime_seconds",
        "background_async_enabled",
        "last_archive_sync_run_id",
        "user_ops_deferred_jobs",
    } <= set(data.keys())
    assert data["request_id"] == "contract-request-id"
    assert data["release_sha"] == "contract-release-sha"
    assert isinstance(data["uptime_seconds"], int)
    assert {"total_count", "pending_count", "running_count", "success_count", "conflict_count", "skipped_count", "failed_count"} <= set(
        data["user_ops_deferred_jobs"].keys()
    )


def test_contract_contacts_and_identity(client, monkeypatch):
    monkeypatch.setattr("requests.get", fake_wecom_get)
    contacts_response = client.get("/api/contacts/wm_ext_001")
    identity_response = client.get("/api/identity/resolve?external_userid=wm_ext_001")
    assert contacts_response.status_code == 200
    assert {"external_userid", "customer_name", "owner_userid", "remark", "description"} <= set(
        contacts_response.get_json()["contact"].keys()
    )
    assert identity_response.status_code == 200
    assert {"person_id", "mobile", "external_userid", "unionid", "signup_status"} <= set(identity_response.get_json().keys())


def test_contract_messages(client):
    messages_response = client.get("/api/messages/wm_ext_001")
    recent_response = client.get("/api/messages/wm_ext_001/recent?limit=1")
    search_response = client.get("/api/messages/search?external_userid=wm_ext_001&keyword=契约")
    assert messages_response.status_code == 200
    assert {"seq", "msgid", "chat_type", "external_userid", "content", "send_time"} <= set(
        messages_response.get_json()["messages"][0].keys()
    )
    assert recent_response.status_code == 200
    recent_payload = recent_response.get_json()
    assert "messages" in recent_payload
    assert len(recent_payload["messages"]) == 1
    assert {"msgid", "msgtype", "content", "send_time", "external_userid"} <= set(recent_payload["messages"][0].keys())
    assert search_response.status_code == 200
    assert len(search_response.get_json()["messages"]) == 1


def test_contract_customer_aggregation_reads(client):
    list_response = client.get("/api/customers")
    detail_response = client.get("/api/customers/wm_ext_001")
    timeline_response = client.get("/api/customers/wm_ext_001/timeline")

    assert list_response.status_code == 200
    list_payload = list_response.get_json()
    assert {"ok", "customers", "count", "items", "total", "limit", "offset", "filters"} <= set(list_payload.keys())
    assert list_payload["items"][0]["external_userid"] == "wm_ext_001"

    assert detail_response.status_code == 200
    detail_payload = detail_response.get_json()
    assert {"ok", "customer"} <= set(detail_payload.keys())
    assert {
        "external_userid",
        "customer_name",
        "owner_userid",
        "last_message_at",
        "last_touch_at",
        "tags",
        "class_user_status",
    } <= set(detail_payload["customer"].keys())
    assert detail_payload["customer"]["external_userid"] == "wm_ext_001"

    assert timeline_response.status_code == 200
    timeline_payload = timeline_response.get_json()
    assert {"ok", "timeline"} <= set(timeline_payload.keys())
    assert {"external_userid", "items", "count", "limit", "offset", "filters", "total"} <= set(
        timeline_payload["timeline"].keys()
    )
    assert timeline_payload["timeline"]["external_userid"] == "wm_ext_001"
    assert {"event_id", "event_type", "event_time", "title", "summary", "source_table", "source_id", "metadata"} <= set(
        timeline_payload["timeline"]["items"][0].keys()
    )


def _mcp_call(client, name: str, arguments: dict[str, object]):
    from wecom_ability_service.mcp_adapter import streamable_http_mcp

    with client.application.test_request_context(
        "/mcp",
        method="POST",
        headers={"Authorization": "Bearer mcp-token"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
    ):
        response = streamable_http_mcp()
    assert response.status_code == 200
    return response.get_json()["result"]["structuredContent"]


def _freeze_router_time(monkeypatch, *, timestamp: str) -> None:
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

    monkeypatch.setattr(marketing_automation_service, "datetime", FrozenDateTime)
    monkeypatch.setattr(
        marketing_automation_service,
        "_router_now",
        lambda *, timezone: FrozenDateTime.now(),
    )


def test_contract_openclaw_conversion_mcp_reads(client, app, monkeypatch):
    _freeze_router_time(monkeypatch, timestamp="2026-04-04 10:30:00")
    with app.app_context():
        from wecom_ability_service.services import materialize_message_batches

        db = get_db()
        db.execute(
            """
            INSERT OR IGNORE INTO owner_role_map (userid, display_name, role, active)
            VALUES (?, ?, ?, ?)
            """,
            ("sales_01", "销售一", "sales", 1),
        )
        db.execute(
            """
            UPDATE class_user_status_current
            SET signup_status = ?, signup_label_name = ?, set_by_userid = ?, set_at = CURRENT_TIMESTAMP
            WHERE external_userid = ?
            """,
            ("lead", "报名引流品", "sales_01", "wm_ext_001"),
        )
        db.execute(
            """
            INSERT INTO questionnaires (
                id, slug, name, title, description, is_disabled, redirect_url, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, 0, '', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (901, "contract-signup-conv", "合同转化问卷", "合同转化问卷", ""),
        )
        question_rules: list[dict[str, object]] = []
        for index in range(5):
            question_id = 90100 + index + 1
            hit_option_id = question_id * 10 + 1
            db.execute(
                """
                INSERT INTO questionnaire_questions (
                    id, questionnaire_id, type, title, required, sort_order, created_at, updated_at
                )
                VALUES (?, ?, 'single_choice', ?, 1, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (question_id, 901, f"关键题 {index + 1}", index + 1),
            )
            db.execute(
                """
                INSERT INTO questionnaire_options (
                    id, question_id, option_text, score, tag_codes, sort_order, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, '[]', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (hit_option_id, question_id, "命中", 10, 1),
            )
            db.execute(
                """
                INSERT INTO questionnaire_options (
                    id, question_id, option_text, score, tag_codes, sort_order, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, '[]', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (question_id * 10 + 2, question_id, "未命中", 0, 2),
            )
            question_rules.append(
                {
                    "questionnaire_question_id": int(question_id),
                    "hit_option_ids_json": [int(hit_option_id)],
                    "sort_order": index + 1,
                }
            )
        db.execute(
            """
            INSERT INTO archived_messages
            (seq, msgid, chat_type, external_userid, owner_userid, sender, receiver, msgtype, content, send_time, raw_payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                22,
                "contract-msg-002",
                "private",
                "wm_ext_001",
                "sales_01",
                "wm_ext_001",
                "sales_01",
                "text",
                "我想继续了解报名",
                "2026-04-04 10:03:00",
                '{"decrypted_message":{"from":"wm_ext_001","tolist":["sales_01"],"roomid":"","msgtype":"text"}}',
            ),
        )
        db.commit()
        marketing_automation_service.upsert_customer_trial_opening_fact(
            mobile="13800138000",
            external_userid="wm_ext_001",
            customer_name="周青",
            owner_userid="sales_01",
            source="contract_seed",
            opened_at="2026-04-04 10:02:00",
        )

    config_response = client.put(
        "/api/admin/marketing-automation/config",
        json={
            "enabled": True,
            "questionnaire_id": 901,
            "core_threshold": 3,
            "top_threshold": 4,
            "quiet_hour_start": 23,
            "timezone": "Asia/Shanghai",
            "question_rules": question_rules,
        },
    )
    assert config_response.status_code == 200

    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO questionnaire_submissions (
                id, questionnaire_id, respondent_key, openid, unionid, external_userid, follow_user_userid,
                matched_by, mobile_snapshot, total_score, final_tags, redirect_url_snapshot, submitted_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                90101,
                901,
                "resp-contract-001",
                "openid-contract-001",
                "union-contract-001",
                "wm_ext_001",
                "sales_01",
                "external_userid",
                "13800138000",
                88,
                "[]",
                "",
                "2026-04-04 10:04:00",
            ),
        )
        for item in question_rules[:4]:
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
                    90101,
                    item["questionnaire_question_id"],
                    "关键题",
                    json.dumps(item["hit_option_ids_json"], ensure_ascii=False),
                    10,
                ),
                )
            db.commit()
        materialize_message_batches(window_minutes=3)
        batch_row = db.execute(
            """
            SELECT id
            FROM message_batches
            WHERE status = 'pending'
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        assert batch_row is not None
        batch_id = int(batch_row["id"])

    detail = _mcp_call(client, "get_conversion_batch", {"batch_id": batch_id})
    profile = _mcp_call(client, "get_customer_marketing_profile", {"external_userid": "wm_ext_001"})
    acked = _mcp_call(client, "ack_conversion_batch", {"batch_id": batch_id, "acked_by": "openclaw"})

    assert detail["batch"]["batch_id"] == batch_id
    assert "candidates" in detail
    assert profile["customer"]["external_userid"] == "wm_ext_001"
    assert profile["routing"]["reason"] in {"eligible_by_router", "trial_not_opened"}
    assert profile["recent_text_summary"]["latest_customer_message_summary"] == "我想继续了解报名"
    assert "items" not in profile["recent_text_summary"]
    assert acked["batch_id"] == batch_id


def test_contract_record_conversion_feedback_syncs_enrolled_truth(client, app):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            UPDATE class_user_status_current
            SET signup_status = ?, signup_label_name = ?, set_by_userid = ?, set_at = CURRENT_TIMESTAMP
            WHERE external_userid = ?
            """,
            ("lead", "报名引流品", "sales_01", "wm_ext_001"),
        )
        db.commit()

    feedback = _mcp_call(
        client,
        "record_conversion_feedback",
        {
            "feedback_type": "mark_enrolled",
            "external_userid": "wm_ext_001",
            "actor": "openclaw",
            "feedback_payload": {"owner_userid": "sales_01"},
        },
    )

    assert feedback["ok"] is True
    assert feedback["feedback_id"] > 0
    assert feedback["conversion_result"]["marketing_state"]["stage_key"] == "converted/enrolled"
    assert feedback["conversion_result"]["class_user_status"]["signup_status"] == "signed_999"


def test_contract_tags_and_tasks(client, monkeypatch):
    monkeypatch.setattr("requests.get", fake_wecom_get)
    monkeypatch.setattr("requests.post", fake_wecom_post)
    tags_response = client.get("/api/tags")
    mark_response = client.post(
        "/api/tags/mark",
        json={"userid": "sales_01", "external_userid": "wm_ext_001", "add_tag": ["et-tag-001"]},
    )
    task_response = client.post(
        "/api/tasks/private-message",
        json={"text": {"content": "今天统一跟进"}, "sender": ["sales_01"]},
    )
    assert tags_response.status_code == 200
    assert {"ok", "result"} <= set(tags_response.get_json().keys())
    assert mark_response.status_code == 200
    assert mark_response.get_json()["ok"] is True
    assert task_response.status_code == 200
    assert {"ok", "task_id", "wecom_result"} <= set(task_response.get_json().keys())


def test_contract_class_user_read(client):
    response = client.get("/api/sidebar/signup-tags/status?external_userid=wm_ext_001")
    data = response.get_json()
    assert response.status_code == 200
    assert {"ok", "definitions", "initialized", "current_signup_status", "current_tag"} <= set(data.keys())


def test_contract_identity_requires_locator(client):
    response = client.get("/api/identity/resolve")
    assert response.status_code == 400
    assert response.get_json()["ok"] is False
