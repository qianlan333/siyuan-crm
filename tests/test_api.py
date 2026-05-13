from __future__ import annotations

import base64
from datetime import datetime
from io import BytesIO
import json
from pathlib import Path
import re
import requests
import subprocess
import tempfile
import xml.etree.ElementTree as ET

import pytest

from wecom_ability_service.archive_sdk import extract_text_record, normalize_timestamp
from wecom_ability_service.wecom_callback import compute_signature, encrypt_message
from wecom_ability_service.db import get_db
from wecom_ability_service.infra.settings import set_settings
from wecom_ability_service.services import (
    ThirdPartyUserSyncError,
    bind_openid_to_external_contact,
    delete_questionnaire_submissions_by_slug,
    resolve_external_contact_identity,
)


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload, ensure_ascii=False)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http error: {self.status_code}")


def _test_image_data_url(label: str = "img") -> str:
    encoded = base64.b64encode(f"fake-image-{label}".encode("utf-8")).decode("ascii")
    return f"data:image/png;base64,{encoded}"


@pytest.fixture()
def app(tmp_path):
    """PG-only：用顶层 build_pg_test_app helper 起 app（2026-05 砍 SQLite 后改造）。"""
    from tests.conftest import build_pg_test_app

    with build_pg_test_app(
        tmp_path,
        SIDEBAR_PERSON_DETAIL_URL_TEMPLATE="https://www.youcangogogo.com/person/{person_id}",
        MCP_BEARER_TOKEN="mcp-token",
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


def _admin_action_token(client, path: str = "/admin/automation-conversion/shared/agents") -> str:
    client.get(path, follow_redirects=True)
    with client.session_transaction() as session:
        return str(session["admin_console_action_token"])


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


def _seed_profile_segment_questionnaire(app, *, questionnaire_id: int = 901) -> dict[str, int | list[int]]:
    choice_question_id = questionnaire_id * 100 + 1
    option_ids = [questionnaire_id * 1000 + 1, questionnaire_id * 1000 + 2]
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
                f"agent-config-{questionnaire_id}",
                f"agent-config-{questionnaire_id}",
                f"Agent 配置问卷 {questionnaire_id}",
            ),
        )
        db.execute(
            """
            INSERT INTO questionnaire_questions (
                id, questionnaire_id, type, title, required, sort_order, created_at, updated_at
            )
            VALUES (?, ?, 'single_choice', '你最关心什么？', true, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (choice_question_id, questionnaire_id),
        )
        db.executemany(
            """
            INSERT INTO questionnaire_options (
                id, question_id, option_text, sort_order, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            [
                (option_ids[0], choice_question_id, "效率", 1),
                (option_ids[1], choice_question_id, "成交", 2),
            ],
        )
        db.commit()
    return {
        "questionnaire_id": questionnaire_id,
        "choice_question_id": choice_question_id,
        "option_ids": option_ids,
    }


def fake_wecom_get(url, params=None, timeout=None):
    if url.endswith("/sns/oauth2/access_token"):
        code = (params or {}).get("code")
        if code == "oauth-code-001":
            return FakeResponse(
                {
                    "access_token": "wechat-access-token",
                    "expires_in": 7200,
                    "refresh_token": "wechat-refresh-token",
                    "openid": "openid-oauth-001",
                    "scope": "snsapi_base",
                    "unionid": "union-oauth-001",
                }
            )
        if code == "oauth-code-userinfo-001":
            return FakeResponse(
                {
                    "access_token": "wechat-access-token-userinfo",
                    "expires_in": 7200,
                    "refresh_token": "wechat-refresh-token-userinfo",
                    "openid": "openid-userinfo-001",
                    "scope": "snsapi_userinfo",
                }
            )
        return FakeResponse({"errcode": 40029, "errmsg": "invalid code"})
    if url.endswith("/sns/userinfo"):
        openid = (params or {}).get("openid")
        if openid == "openid-userinfo-001":
            return FakeResponse(
                {
                    "openid": "openid-userinfo-001",
                    "nickname": "测试用户",
                    "sex": 1,
                    "language": "zh_CN",
                    "city": "",
                    "province": "",
                    "country": "CN",
                    "headimgurl": "",
                    "privilege": [],
                    "unionid": "union-userinfo-001",
                }
            )
        return FakeResponse({"errcode": 40003, "errmsg": "invalid openid"})
    if url.endswith("/cgi-bin/gettoken"):
        return FakeResponse(
            {"errcode": 0, "errmsg": "ok", "access_token": "token-123", "expires_in": 7200}
        )
    if url.endswith("/cgi-bin/externalcontact/get_follow_user_list"):
        return FakeResponse({"errcode": 0, "errmsg": "ok", "follow_user": ["sales_01", "sales_bad", "sales_02"]})
    if url.endswith("/cgi-bin/externalcontact/list"):
        userid = (params or {}).get("userid")
        if userid == "sales_01":
            return FakeResponse({"errcode": 0, "errmsg": "ok", "external_userid": ["wm_ext_001", "wm_ext_002"]})
        if userid == "sales_bad":
            return FakeResponse({"errcode": 84061, "errmsg": "not external contact"})
        if userid == "sales_02":
            return FakeResponse({"errcode": 0, "errmsg": "ok", "external_userid": ["wm_ext_001", "wm_ext_003"]})
        return FakeResponse({"errcode": 0, "errmsg": "ok", "external_userid": []})
    if url.endswith("/cgi-bin/externalcontact/get"):
        external_userid = (params or {}).get("external_userid")
        cursor = (params or {}).get("cursor", "")
        if external_userid == "wm_ext_paged":
            if cursor == "page-2":
                return FakeResponse(
                    {
                        "errcode": 0,
                        "errmsg": "ok",
                        "external_contact": {
                            "external_userid": "wm_ext_paged",
                            "name": "分页客户",
                            "unionid": "union-paged",
                            "type": 1,
                            "gender": 1,
                            "avatar": "https://example.com/paged.png",
                        },
                        "follow_user": [{"userid": "sales_01", "remark": "分页命中", "description": "wm_ext_paged"}],
                    }
                )
            return FakeResponse(
                {
                    "errcode": 0,
                    "errmsg": "ok",
                    "external_contact": {
                        "external_userid": "wm_ext_paged",
                        "name": "分页客户",
                        "unionid": "union-paged",
                        "type": 1,
                        "gender": 1,
                        "avatar": "https://example.com/paged.png",
                    },
                    "follow_user": [{"userid": "sales_99", "remark": "错误页", "description": "wrong"}],
                    "next_cursor": "page-2",
                }
            )
        records = {
            "wm_ext_001": {
                "external_contact": {
                    "external_userid": "wm_ext_001",
                    "name": "周青",
                    "unionid": "union-001",
                    "type": 1,
                    "gender": 2,
                    "avatar": "https://example.com/001.png",
                },
                "follow_user": [
                    {"userid": "sales_99", "remark": "错误备注", "description": "wrong"},
                    {"userid": "sales_01", "remark": "老同学介绍", "description": "wm_ext_001"},
                ],
            },
            "wm_ext_002": {
                "external_contact": {
                    "external_userid": "wm_ext_002",
                    "name": "李木",
                    "unionid": "union-002",
                    "type": 2,
                    "gender": 1,
                    "avatar": "https://example.com/002.png",
                },
                "follow_user": [{"userid": "sales_01", "remark": "直播间", "description": ""}],
            },
            "wm_ext_003": {
                "external_contact": {
                    "external_userid": "wm_ext_003",
                    "name": "王敏",
                    "unionid": "union-003",
                    "type": 1,
                    "gender": 2,
                    "avatar": "https://example.com/003.png",
                },
                "follow_user": [{"userid": "sales_02", "remark": "转介绍", "description": "not-target"}],
            },
        }
        return FakeResponse(
            {
                "errcode": 0,
                "errmsg": "ok",
                **records[external_userid],
            }
        )
    if url.endswith("/cgi-bin/get_jsapi_ticket"):
        return FakeResponse({"errcode": 0, "errmsg": "ok", "ticket": "corp-jsapi-ticket", "expires_in": 7200})
    if url.endswith("/cgi-bin/ticket/get"):
        ticket_type = (params or {}).get("type")
        if ticket_type == "agent_config":
            return FakeResponse({"errcode": 0, "errmsg": "ok", "ticket": "agent-jsapi-ticket", "expires_in": 7200})
        return FakeResponse({"errcode": 40013, "errmsg": "invalid ticket type"})
    raise AssertionError(f"unexpected GET url: {url}")


def fake_wecom_post(url, params=None, json=None, timeout=None, files=None):
    if url.endswith("/cgi-bin/externalcontact/get_corp_tag_list"):
        return FakeResponse(
            {
                "errcode": 0,
                "errmsg": "ok",
                "tag_group": [
                    {
                        "group_id": "group-002",
                        "group_name": "业务标签",
                        "tag": [
                            {"id": "et-tag-002", "name": "私域运营"},
                        ],
                    },
                    {
                        "group_id": "group-001",
                        "group_name": "客户分层",
                        "tag": [
                            {"id": "et-tag-003", "name": "低意向"},
                            {"id": "et-tag-001", "name": "高意向"},
                        ],
                    },
                ],
            }
        )
    if url.endswith("/cgi-bin/externalcontact/add_corp_tag"):
        return FakeResponse({"errcode": 0, "errmsg": "ok", "tag_group": {"group_id": "g1"}})
    if url.endswith("/cgi-bin/externalcontact/mark_tag"):
        return FakeResponse({"errcode": 0, "errmsg": "ok"})
    if url.endswith("/cgi-bin/externalcontact/remark"):
        return FakeResponse({"errcode": 0, "errmsg": "ok"})
    if url.endswith("/cgi-bin/externalcontact/groupchat/list"):
        owner_filter = ((((json or {}).get("owner_filter") or {}).get("userid_list") or []))
        if owner_filter == ["sales_01"]:
            return FakeResponse({"errcode": 0, "errmsg": "ok", "group_chat_list": [{"chat_id": "chat-001"}]})
        if owner_filter == ["sales_02"]:
            return FakeResponse({"errcode": 0, "errmsg": "ok", "group_chat_list": [{"chat_id": "chat-002"}]})
        return FakeResponse({"errcode": 0, "errmsg": "ok", "group_chat_list": []})
    if url.endswith("/cgi-bin/externalcontact/groupchat/get"):
        chat_id = (json or {}).get("chat_id")
        details = {
            "chat-001": {
                "group_chat": {
                    "chat_id": "chat-001",
                    "name": "高意向测试群",
                    "notice": "群公告A",
                    "member_list": [{"userid": "sales_01"}, {"userid": "wm_ext_001"}],
                    "create_time": 1761950405,
                }
            },
            "chat-002": {
                "group_chat": {
                    "chat_id": "chat-002",
                    "name": "第二测试群",
                    "notice": "群公告B",
                    "member_list": [{"userid": "sales_02"}, {"userid": "wm_ext_003"}],
                    "create_time": 1761950406,
                }
            },
        }
        return FakeResponse({"errcode": 0, "errmsg": "ok", **details[chat_id]})
    if url.endswith("/cgi-bin/media/upload"):
        uploaded = (files or {}).get("media")
        file_name = uploaded[0] if isinstance(uploaded, tuple) and uploaded else "uploaded-image.png"
        return FakeResponse({"errcode": 0, "errmsg": "ok", "type": "image", "media_id": f"media-{file_name}"})
    if url.endswith("/cgi-bin/externalcontact/send_welcome_msg"):
        return FakeResponse({"errcode": 0, "errmsg": "ok"})
    if url.endswith("/cgi-bin/externalcontact/add_msg_template"):
        return FakeResponse({"errcode": 0, "errmsg": "ok", "msgid": "task-msg-001"})
    if url.endswith("/cgi-bin/externalcontact/add_moment_task"):
        return FakeResponse({"errcode": 0, "errmsg": "ok", "jobid": "moment-job-001"})
    raise AssertionError(f"unexpected POST url: {url}")


def test_automation_conversion_agent_create_and_edit_flow(client):
    action_token = _admin_action_token(client)

    create_response = client.post(
        "/api/admin/automation-conversion/agents",
        json={
            "admin_action_token": action_token,
            "agent_code": "conversion_followup_agent",
            "display_name": "转化跟进 Agent",
            "enabled": True,
            "role_prompt": "你是转化跟进 Agent。",
            "task_prompt": "请基于 {{问卷信息}} 和 {{用户标签}} 生成跟进话术。",
            "enabled_context_sources": ["questionnaire", "user_tags"],
            "change_summary": "创建新 Agent",
        },
    )

    assert create_response.status_code == 201
    created = create_response.get_json()
    assert created["ok"] is True
    assert created["agent"]["agent_code"] == "conversion_followup_agent"
    assert created["agent"]["display_name"] == "转化跟进 Agent"
    assert created["agent"]["published_version"] == 0
    assert created["agent"]["draft"]["enabled_context_sources"] == ["questionnaire", "user_tags"]
    assert created["agent"]["draft"]["variables"][0]["variable_key"] == "questionnaire_info"
    assert created["agent"]["draft"]["output_schema"][0]["field_key"] == "draft_reply"

    detail_response = client.get("/api/admin/automation-conversion/agents/conversion_followup_agent")
    assert detail_response.status_code == 200
    assert detail_response.get_json()["item"]["agent_code"] == "conversion_followup_agent"

    options_response = client.get("/api/admin/automation-conversion/agents/options", query_string={"enabled_only": 0})
    assert options_response.status_code == 200
    option_codes = [item["agent_code"] for item in options_response.get_json()["items"]]
    assert "conversion_followup_agent" in option_codes

    update_response = client.post(
        "/api/admin/automation-conversion/agents/conversion_followup_agent/draft",
        json={
            "admin_action_token": action_token,
            "display_name": "转化跟进 Agent",
            "enabled": True,
            "role_prompt": "你是更新后的转化跟进 Agent。",
            "task_prompt": "生成更新后的跟进话术。",
            "enabled_context_sources": ["questionnaire", "recent_messages", "activation_info"],
            "expected_draft_version": 1,
            "change_summary": "更新新 Agent 草稿",
        },
    )
    assert update_response.status_code == 200
    assert update_response.get_json()["agent"]["draft"]["role_prompt"] == "你是更新后的转化跟进 Agent。"
    assert update_response.get_json()["agent"]["draft"]["enabled_context_sources"] == ["questionnaire", "recent_messages", "activation_info"]


def test_mcp_create_agent_config_tool(client):
    response = _mcp_call(
        client,
        "create_agent_config",
        {
            "agent_code": "lobster_created_agent",
            "display_name": "龙虾新建 Agent",
            "enabled": True,
            "role_prompt": "你是龙虾新建 Agent。",
            "task_prompt": "请根据 {{问卷信息}} 和 {{最近20条聊天信息}} 生成跟进话术。",
            "enabled_context_sources": ["questionnaire", "recent_messages"],
            "operator": "lobster_test",
        },
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["result"]["structuredContent"]["created"] is True
    created = body["result"]["structuredContent"]["agent"]
    assert created["agent_code"] == "lobster_created_agent"
    assert created["draft"]["enabled_context_sources"] == ["questionnaire", "recent_messages"]

    update_response = _mcp_call(
        client,
        "save_agent_prompt_draft",
        {
            "agent_code": "lobster_created_agent",
            "task_prompt": "请结合 {{用户标签}} 和 {{激活信息}} 输出一条成交推进话术。",
            "enabled_context_sources": ["user_tags", "activation_info"],
            "expected_draft_version": 1,
            "operator": "lobster_test",
        },
    )

    assert update_response.status_code == 200
    updated = update_response.get_json()["result"]["structuredContent"]["agent"]
    assert updated["draft"]["enabled_context_sources"] == ["user_tags", "activation_info"]


def test_automation_conversion_profile_segment_template_detail_returns_template_bundle(client, app):
    questionnaire = _seed_profile_segment_questionnaire(app, questionnaire_id=902)

    created_response = client.post(
        "/api/admin/automation-conversion/profile-segment-templates",
        json={
            "template_name": "基础画像模板 A",
            "questionnaire_id": questionnaire["questionnaire_id"],
            "segmentation_question_id": questionnaire["choice_question_id"],
            "enabled": True,
            "categories": [
                {
                    "category_name": "效率优先",
                    "category_key": "efficiency",
                    "option_ids": [questionnaire["option_ids"][0]],
                },
                {
                    "category_name": "成交优先",
                    "category_key": "closing",
                    "option_ids": [questionnaire["option_ids"][1]],
                },
            ],
        },
    )
    assert created_response.status_code == 201
    template_id = created_response.get_json()["template_bundle"]["template"]["id"]

    detail_response = client.get(f"/api/admin/automation-conversion/profile-segment-templates/{template_id}")
    assert detail_response.status_code == 200
    detail = detail_response.get_json()
    assert detail["ok"] is True
    assert detail["template_bundle"]["template"]["id"] == template_id
    assert detail["template_bundle"]["template"]["template_name"] == "基础画像模板 A"
    assert detail["template_bundle"]["questionnaire"]["id"] == questionnaire["questionnaire_id"]
    assert detail["template_bundle"]["segmentation_question"]["id"] == questionnaire["choice_question_id"]
    assert len(detail["template_bundle"]["categories"]) == 2


def make_signup_management_fake_wecom_post(*, include_lead_tag: bool = True):
    state = {
        "include_lead_tag": include_lead_tag,
        "created_payloads": [],
        "mark_payloads": [],
    }

    def _fake(url, params=None, json=None, timeout=None):
        if url.endswith("/cgi-bin/externalcontact/get_corp_tag_list"):
            ai_tags = []
            if state["include_lead_tag"]:
                ai_tags.append({"id": "tag-lead", "name": "报名引流品"})
            ai_tags.extend(
                [
                    {"id": "tag-999", "name": "已报名999"},
                    {"id": "tag-3999", "name": "已报名3999"},
                ]
            )
            return FakeResponse(
                {
                    "errcode": 0,
                    "errmsg": "ok",
                    "tag_group": [
                        {
                            "group_id": "group-signup",
                            "group_name": "AI 产品报名情况",
                            "tag": ai_tags,
                        }
                    ],
                }
            )
        if url.endswith("/cgi-bin/externalcontact/add_corp_tag"):
            state["created_payloads"].append(json or {})
            state["include_lead_tag"] = True
            return FakeResponse({"errcode": 0, "errmsg": "ok", "tag_group": {"group_id": "group-signup"}})
        if url.endswith("/cgi-bin/externalcontact/mark_tag"):
            state["mark_payloads"].append(json or {})
            return FakeResponse({"errcode": 0, "errmsg": "ok"})
        return fake_wecom_post(url, params=params, json=json, timeout=timeout)

    _fake.state = state
    return _fake


class FakeArchiveAdapterClient:
    @classmethod
    def from_app(cls):
        return cls()

    def health(self):
        return {
            "ok": True,
            "mode": "official-sdk",
            "sdk_lib_path": "/fake/libWeWorkFinanceSdk_C.so",
            "sdk_lib_exists": True,
            "private_key_path": "/fake/wecom_private_key.pem",
            "private_key_exists": True,
        }

    def sync_messages(self, start_time, end_time, owner_userid, cursor=""):
        return {
            "fetched_count": 2,
            "inserted_count": 0,
            "has_more": False,
            "next_cursor": "12",
            "last_seq": 12,
        }


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json()["ok"] is True
    assert response.headers["X-Request-Id"]



def test_ops_status(client, app):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO archived_messages
            (seq, msgid, chat_type, external_userid, owner_userid, sender, receiver, msgtype, content, send_time, raw_payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                99,
                "ops-msg-001",
                "private",
                "wm_ext_001",
                "sales_01",
                "wm_ext_001",
                "sales_01",
                "text",
                "ops status",
                "2026-03-20 12:00:00",
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
            INSERT INTO group_chats (chat_id, group_name, owner_userid, raw_payload)
            VALUES (?, ?, ?, ?)
            """,
            ("chat-001", "测试群", "sales_01", "{}"),
        )
        db.execute(
            """
            INSERT INTO sync_runs (status, start_time, end_time, owner_userid, cursor, fetched_count, inserted_count, finished_at)
            VALUES ('success', ?, ?, ?, ?, ?, ?, ?)
            """,
            ("2026-03-20 00:00:00", "2026-03-20 23:59:59", "sales_01", "99", 1, 1, "2026-03-20 12:01:00"),
        )
        db.execute(
            """
            INSERT INTO archive_sync_state (state_key, last_seq, updated_at)
            VALUES ('global', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(state_key) DO UPDATE SET last_seq = excluded.last_seq
            """,
            (99,),
        )
        db.execute(
            """
            INSERT INTO user_ops_deferred_jobs (
                job_type, external_userid, owner_userid, run_after, status,
                attempt_count, payload_json, result_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            ("auto_assign_class_term", "wm_ext_001", "sales_01", "2026-03-20 12:02:00", "pending", 0, "{}", "{}"),
        )
        db.execute(
            """
            INSERT INTO user_ops_deferred_jobs (
                job_type, external_userid, owner_userid, run_after, status,
                attempt_count, payload_json, result_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            ("auto_assign_class_term", "wm_ext_002", "sales_01", "2026-03-20 12:03:00", "success", 1, "{}", "{}"),
        )
        db.commit()

    response = client.get("/api/ops/status")
    data = response.get_json()
    assert response.status_code == 200
    assert data["service_ok"] is True
    assert data["archived_messages_count"] == 1
    assert data["contacts_count"] == 1
    assert data["group_chats_count"] == 1
    assert data["database_backend"] == "postgres"
    assert data["last_seq"] == 99
    assert data["last_archive_sync_run_id"] == 1
    assert data["last_archive_sync_status"] == "success"
    assert data["callback_enabled"] is True
    assert data["request_id"]
    assert data["release_sha"] == "release-test-sha"
    assert data["app_started_at"]
    assert data["uptime_seconds"] >= 0
    assert data["background_async_enabled"] is False
    assert data["user_ops_deferred_jobs"]["total_count"] == 2
    assert data["user_ops_deferred_jobs"]["pending_count"] == 1
    assert data["user_ops_deferred_jobs"]["success_count"] == 1
    assert data["database_url_configured"] is True


def test_ops_status_v2_returns_extended_diagnostics(client, app):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO user_ops_deferred_jobs (
                job_type, external_userid, owner_userid, run_after, status,
                attempt_count, payload_json, result_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            ("auto_assign_class_term", "wm_ext_v2_001", "sales_01", "2026-03-20 12:04:00", "running", 1, "{}", "{}"),
        )
        db.execute(
            """
            INSERT INTO user_ops_deferred_jobs (
                job_type, external_userid, owner_userid, run_after, status,
                attempt_count, payload_json, result_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            ("auto_assign_class_term", "wm_ext_v2_002", "sales_01", "2026-03-20 12:05:00", "failed", 1, "{}", "{}"),
        )
        db.execute(
            """
            INSERT INTO user_ops_deferred_jobs (
                job_type, external_userid, owner_userid, run_after, status,
                attempt_count, payload_json, result_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            ("auto_assign_class_term", "wm_ext_v2_003", "sales_01", "2026-03-20 12:06:00", "conflict", 1, "{}", "{}"),
        )
        db.execute(
            """
            INSERT INTO user_ops_deferred_jobs (
                job_type, external_userid, owner_userid, run_after, status,
                attempt_count, payload_json, result_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            ("auto_assign_class_term", "wm_ext_v2_004", "sales_01", "2026-03-20 12:07:00", "skipped", 1, "{}", "{}"),
        )
        db.commit()

    response = client.get("/api/ops/status", headers={"X-Request-Id": "ops-v2-request-id"})
    data = response.get_json()

    assert response.status_code == 200
    assert data["request_id"] == "ops-v2-request-id"
    assert data["release_sha"] == "release-test-sha"
    assert data["app_started_at"].endswith("Z")
    assert isinstance(data["uptime_seconds"], int)
    assert data["uptime_seconds"] >= 0
    assert data["background_async_enabled"] is False
    assert data["user_ops_deferred_jobs"] == {
        "total_count": 4,
        "pending_count": 0,
        "running_count": 1,
        "success_count": 0,
        "conflict_count": 1,
        "skipped_count": 1,
        "failed_count": 1,
    }
    assert data["env_file_path"].endswith(".env") or data["env_file_path"]


def test_archive_adapter_health(client, monkeypatch):
    monkeypatch.setattr("wecom_ability_service.routes.ArchiveAdapterClient", FakeArchiveAdapterClient)
    response = client.get("/api/archive/health")
    assert response.status_code == 200
    assert response.get_json()["adapter"]["mode"] == "official-sdk"


def test_archive_sync_and_query(client, app, monkeypatch):
    class InsertArchiveClient(FakeArchiveAdapterClient):
        def sync_messages(self, start_time, end_time, owner_userid, cursor=""):
            with app.app_context():
                db = get_db()
                db.execute(
                    """
                    INSERT INTO archived_messages
                    (seq, msgid, chat_type, external_userid, owner_userid, sender, receiver, msgtype, content, send_time, raw_payload)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT DO NOTHING
                    """,
                    (
                        11,
                        "msg-001",
                        "private",
                        "wm_ext_001",
                        "sales_01",
                        "wm_ext_001",
                        "sales_01",
                        "text",
                        "我想了解真实落地案例",
                        "2026-03-15 19:17:05",
                        '{"decrypted_message":{"from":"wm_ext_001","tolist":["sales_01"],"roomid":"","msgtype":"text"},"msgid":"msg-001"}',
                    ),
                )
                db.execute(
                    """
                    INSERT INTO archived_messages
                    (seq, msgid, chat_type, external_userid, owner_userid, sender, receiver, msgtype, content, send_time, raw_payload)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT DO NOTHING
                    """,
                    (
                        12,
                        "msg-002",
                        "private",
                        "wm_ext_001",
                        "sales_01",
                        "sales_01",
                        "wm_ext_001",
                        "text",
                        "可以，我发你一版方案",
                        "2026-03-15 19:20:00",
                        '{"decrypted_message":{"from":"sales_01","tolist":["wm_ext_001"],"roomid":"","msgtype":"text"},"msgid":"msg-002"}',
                    ),
                )
                db.commit()
            return {
                "fetched_count": 2,
                "inserted_count": 2,
                "has_more": False,
                "next_cursor": "12",
                "last_seq": 12,
            }

    monkeypatch.setattr("wecom_ability_service.routes.ArchiveAdapterClient", InsertArchiveClient)
    payload = {
        "start_time": "2026-03-15 00:00:00",
        "end_time": "2026-03-15 23:59:59",
        "owner_userid": "sales_01",
    }
    response = client.post("/api/archive/sync", json=payload)
    data = response.get_json()

    assert response.status_code == 200
    assert data["sync_run"]["fetched_count"] == 2
    assert data["sync_run"]["inserted_count"] == 2
    assert data["sync_run"]["last_seq"] == 12

    messages_response = client.get("/api/messages/wm_ext_001")
    messages = messages_response.get_json()["messages"]
    assert len(messages) == 2
    assert messages[0]["content"] == "我想了解真实落地案例"
    assert messages[0]["seq"] == 11
    assert messages[0]["chat_type"] == "private"
    assert messages[0]["from"] == "wm_ext_001"
    assert messages[0]["tolist"] == ["sales_01"]
    assert "receiver" not in messages[0]

    search_response = client.get("/api/messages/search?external_userid=wm_ext_001&keyword=方案")
    search_messages = search_response.get_json()["messages"]
    assert len(search_messages) == 1
    assert search_messages[0]["sender"] == "sales_01"

    recent_response = client.get("/api/messages/wm_ext_001/recent?limit=1")
    recent_messages = recent_response.get_json()["messages"]
    assert len(recent_messages) == 1
    assert recent_messages[0]["msgid"] == "msg-002"

    filtered_response = client.get("/api/messages/wm_ext_001?chat_type=private")
    filtered_messages = filtered_response.get_json()["messages"]
    assert len(filtered_messages) == 2
    assert all(message["chat_type"] == "private" for message in filtered_messages)

    filtered_recent_response = client.get("/api/messages/wm_ext_001/recent?limit=1&chat_type=private")
    filtered_recent_messages = filtered_recent_response.get_json()["messages"]
    assert len(filtered_recent_messages) == 1
    assert filtered_recent_messages[0]["chat_type"] == "private"

    archive_response = client.get(
        "/archive/messages?start_time=2026-03-15 00:00:00&end_time=2026-03-15 23:59:59&owner_userid=sales_01"
    )
    archive_data = archive_response.get_json()
    assert archive_response.status_code == 200
    assert len(archive_data["messages"]) == 2


def test_archive_sync_deduplicates_messages(client, app, monkeypatch):
    class DedupArchiveClient(FakeArchiveAdapterClient):
        calls = 0

        def sync_messages(self, start_time, end_time, owner_userid, cursor=""):
            self.__class__.calls += 1
            with app.app_context():
                db = get_db()
                inserted = db.execute(
                    """
                    INSERT INTO archived_messages
                    (seq, msgid, chat_type, external_userid, owner_userid, sender, receiver, msgtype, content, send_time, raw_payload)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT DO NOTHING
                    """,
                    (
                        11,
                        "msg-001",
                        "private",
                        "wm_ext_001",
                        "sales_01",
                        "wm_ext_001",
                        "sales_01",
                        "text",
                        "我想了解真实落地案例",
                        "2026-03-15 19:17:05",
                        '{"msgid":"msg-001"}',
                    ),
                ).rowcount
                db.commit()
            return {
                "fetched_count": 1,
                "inserted_count": inserted,
                "has_more": False,
                "next_cursor": str(10 + self.__class__.calls),
                "last_seq": 10 + self.__class__.calls,
            }

    monkeypatch.setattr("wecom_ability_service.routes.ArchiveAdapterClient", DedupArchiveClient)
    payload = {
        "start_time": "2026-03-15 00:00:00",
        "end_time": "2026-03-15 23:59:59",
        "owner_userid": "sales_01",
    }
    first = client.post("/api/archive/sync", json=payload).get_json()
    second = client.post("/api/archive/sync", json=payload).get_json()

    assert first["sync_run"]["inserted_count"] == 1
    assert second["sync_run"]["inserted_count"] == 0

    with app.app_context():
        rows = get_db().execute("SELECT COUNT(*) AS total FROM archived_messages").fetchone()
        assert rows["total"] == 1


def test_create_private_message_task(client, app, monkeypatch):
    monkeypatch.setattr("requests.get", fake_wecom_get)

    captured_payloads: list[dict[str, object]] = []

    def fake_post(url, params=None, json=None, timeout=None, files=None):
        if url.endswith("/cgi-bin/externalcontact/add_msg_template"):
            captured_payloads.append(json or {})
        return fake_wecom_post(url, params=params, json=json, timeout=timeout, files=files)

    monkeypatch.setattr("requests.post", fake_post)

    response = client.post(
        "/api/tasks/private-message",
        json={"text": {"content": "今天统一跟进"}, "sender": ["sales_01"]},
    )
    data = response.get_json()
    assert response.status_code == 200
    assert data["wecom_result"]["msgid"] == "task-msg-001"
    assert captured_payloads[0]["sender"] == "sales_01"

    with app.app_context():
        row = get_db().execute("SELECT COUNT(*) AS total FROM outbound_tasks").fetchone()
        assert row["total"] == 1


def test_create_private_message_task_keeps_emoji_and_image_attachment(client, app, monkeypatch):
    monkeypatch.setattr("requests.get", fake_wecom_get)

    captured_payloads: list[dict[str, object]] = []

    def fake_post(url, params=None, json=None, timeout=None, files=None):
        if url.endswith("/cgi-bin/externalcontact/add_msg_template"):
            captured_payloads.append(json or {})
        return fake_wecom_post(url, params=params, json=json, timeout=timeout, files=files)

    monkeypatch.setattr("requests.post", fake_post)

    response = client.post(
        "/api/tasks/private-message",
        json={
            "sender": ["sales_01"],
            "external_userid": ["wm_ext_001"],
            "text": {"content": "今天统一跟进🙂"},
            "images": [{"file_name": "emoji-proof.png", "data_url": _test_image_data_url("emoji")}],
        },
    )
    data = response.get_json()

    assert response.status_code == 200
    assert data["wecom_result"]["msgid"] == "task-msg-001"
    assert captured_payloads[0]["text"]["content"] == "今天统一跟进🙂"
    assert captured_payloads[0]["attachments"] == [{"msgtype": "image", "image": {"media_id": "media-emoji-proof.png"}}]

    with app.app_context():
        row = get_db().execute("SELECT request_payload FROM outbound_tasks ORDER BY id DESC LIMIT 1").fetchone()
        saved_payload = (row["request_payload"] if isinstance(row["request_payload"], (dict, list)) else json.loads(row["request_payload"]))
        assert saved_payload["text"]["content"] == "今天统一跟进🙂"
        assert saved_payload["attachments"] == [{"msgtype": "image", "image": {"media_id": "media-emoji-proof.png"}}]


def test_create_private_message_task_supports_pure_image_and_limits_to_three(client, monkeypatch):
    monkeypatch.setattr("requests.get", fake_wecom_get)
    monkeypatch.setattr("requests.post", fake_wecom_post)

    pure_image_response = client.post(
        "/api/tasks/private-message",
        json={
            "sender": ["sales_01"],
            "external_userid": ["wm_ext_001"],
            "images": [{"file_name": "only-image.png", "data_url": _test_image_data_url("only")}],
        },
    )
    pure_image_payload = pure_image_response.get_json()
    assert pure_image_response.status_code == 200
    assert pure_image_payload["wecom_result"]["msgid"] == "task-msg-001"

    three_images_response = client.post(
        "/api/tasks/private-message",
        json={
            "sender": ["sales_01"],
            "external_userid": ["wm_ext_001"],
            "images": [
                {"file_name": f"img-{index}.png", "data_url": _test_image_data_url(str(index))}
                for index in range(1, 4)
            ],
        },
    )
    three_images_payload = three_images_response.get_json()
    assert three_images_response.status_code == 200
    assert three_images_payload["wecom_result"]["msgid"] == "task-msg-001"

    four_images_response = client.post(
        "/api/tasks/private-message",
        json={
            "sender": ["sales_01"],
            "external_userid": ["wm_ext_001"],
            "images": [
                {"file_name": f"img-{index}.png", "data_url": _test_image_data_url(str(index))}
                for index in range(1, 5)
            ],
        },
    )
    four_images_payload = four_images_response.get_json()
    assert four_images_response.status_code == 400
    assert four_images_payload["ok"] is False
    assert four_images_payload["error"] == "at most 3 images are allowed"


def test_create_private_message_task_supports_text_with_three_images(client, monkeypatch):
    monkeypatch.setattr("requests.get", fake_wecom_get)
    monkeypatch.setattr("requests.post", fake_wecom_post)

    response = client.post(
        "/api/tasks/private-message",
        json={
            "sender": ["sales_01"],
            "external_userid": ["wm_ext_001"],
            "text": {"content": "今天统一跟进"},
            "images": [
                {"file_name": f"img-{index}.png", "data_url": _test_image_data_url(str(index))}
                for index in range(1, 4)
            ],
        },
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["wecom_result"]["msgid"] == "task-msg-001"


def test_create_private_message_task_supports_pure_attachment_and_text_with_attachment(client, app, monkeypatch):
    monkeypatch.setattr("requests.get", fake_wecom_get)

    captured_payloads: list[dict[str, object]] = []

    def fake_post(url, params=None, json=None, timeout=None, files=None):
        if url.endswith("/cgi-bin/externalcontact/add_msg_template"):
            captured_payloads.append(json or {})
        return fake_wecom_post(url, params=params, json=json, timeout=timeout, files=files)

    monkeypatch.setattr("requests.post", fake_post)

    pure_attachment_response = client.post(
        "/api/tasks/private-message",
        json={
            "sender": ["sales_01"],
            "external_userid": ["wm_ext_001"],
            "attachments": [{"msgtype": "file", "file": {"media_id": "file-media-001"}}],
        },
    )
    text_with_attachment_response = client.post(
        "/api/tasks/private-message",
        json={
            "sender": ["sales_01"],
            "external_userid": ["wm_ext_001"],
            "text": {"content": "文本 + 附件"},
            "attachments": [{"msgtype": "file", "file": {"media_id": "file-media-002"}}],
        },
    )

    assert pure_attachment_response.status_code == 200
    assert pure_attachment_response.get_json()["wecom_result"]["msgid"] == "task-msg-001"
    assert text_with_attachment_response.status_code == 200
    assert text_with_attachment_response.get_json()["wecom_result"]["msgid"] == "task-msg-001"
    assert captured_payloads[0]["attachments"] == [{"msgtype": "file", "file": {"media_id": "file-media-001"}}]
    assert captured_payloads[1]["text"]["content"] == "文本 + 附件"
    assert captured_payloads[1]["attachments"] == [{"msgtype": "file", "file": {"media_id": "file-media-002"}}]

    with app.app_context():
        rows = get_db().execute(
            "SELECT request_payload FROM outbound_tasks ORDER BY id DESC LIMIT 2"
        ).fetchall()
        latest_rows = list(reversed(rows))
        pure_saved_payload = (latest_rows[0]["request_payload"] if isinstance(latest_rows[0]["request_payload"], (dict, list)) else json.loads(latest_rows[0]["request_payload"]))
        text_saved_payload = (latest_rows[1]["request_payload"] if isinstance(latest_rows[1]["request_payload"], (dict, list)) else json.loads(latest_rows[1]["request_payload"]))
        assert pure_saved_payload["attachments"] == [{"msgtype": "file", "file": {"media_id": "file-media-001"}}]
        assert "text" not in pure_saved_payload
        assert text_saved_payload["text"]["content"] == "文本 + 附件"
        assert text_saved_payload["attachments"] == [{"msgtype": "file", "file": {"media_id": "file-media-002"}}]


def test_create_private_message_task_supports_text_image_and_attachment(client, monkeypatch):
    monkeypatch.setattr("requests.get", fake_wecom_get)

    captured_payloads: list[dict[str, object]] = []

    def fake_post(url, params=None, json=None, timeout=None, files=None):
        if url.endswith("/cgi-bin/externalcontact/add_msg_template"):
            captured_payloads.append(json or {})
        return fake_wecom_post(url, params=params, json=json, timeout=timeout, files=files)

    monkeypatch.setattr("requests.post", fake_post)

    response = client.post(
        "/api/tasks/private-message",
        json={
            "sender": ["sales_01"],
            "external_userid": ["wm_ext_001"],
            "text": {"content": "文本 + 图片 + 附件"},
            "images": [{"file_name": "combo.png", "data_url": _test_image_data_url("combo")}],
            "attachments": [{"msgtype": "file", "file": {"media_id": "file-media-003"}}],
        },
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["wecom_result"]["msgid"] == "task-msg-001"
    assert captured_payloads[0]["text"]["content"] == "文本 + 图片 + 附件"
    assert captured_payloads[0]["attachments"] == [
        {"msgtype": "file", "file": {"media_id": "file-media-003"}},
        {"msgtype": "image", "image": {"media_id": "media-combo.png"}},
    ]


def test_create_private_message_task_rejects_invalid_attachment_payload(client, monkeypatch):
    monkeypatch.setattr("requests.get", fake_wecom_get)
    monkeypatch.setattr("requests.post", fake_wecom_post)

    response = client.post(
        "/api/tasks/private-message",
        json={
            "sender": ["sales_01"],
            "external_userid": ["wm_ext_001"],
            "attachments": [{"msgtype": "file", "file": {"name": "missing-media-id"}}],
        },
    )
    payload = response.get_json()

    assert response.status_code == 400
    assert payload["ok"] is False
    assert payload["error"] == "file attachments must include media_id"


def test_create_moment_task(client, monkeypatch):
    monkeypatch.setattr("requests.get", fake_wecom_get)
    monkeypatch.setattr("requests.post", fake_wecom_post)

    response = client.post("/api/tasks/moment", json={"visible_range": {"sender_list": {"userid": ["sales_01"]}}})
    data = response.get_json()
    assert response.status_code == 200
    assert data["wecom_result"]["jobid"] == "moment-job-001"


def test_mark_and_unmark_tag(client, app, monkeypatch):
    monkeypatch.setattr("requests.get", fake_wecom_get)
    monkeypatch.setattr("requests.post", fake_wecom_post)

    list_response = client.get("/api/tags")
    assert list_response.status_code == 200
    assert len(list_response.get_json()["result"]["tag_group"]) == 2

    create_response = client.post("/api/tags", json={"group_name": "测试分组", "tag": [{"name": "高意向"}]})
    assert create_response.status_code == 200
    assert create_response.get_json()["result"]["tag_group"]["group_id"] == "g1"

    mark_payload = {"userid": "sales_01", "external_userid": "wm_ext_001", "add_tag": ["tag-001"]}
    response = client.post("/api/tags/mark", json=mark_payload)
    assert response.status_code == 200

    with app.app_context():
        row = get_db().execute("SELECT COUNT(*) AS total FROM contact_tags").fetchone()
        assert row["total"] == 1

    unmark_payload = {"userid": "sales_01", "external_userid": "wm_ext_001", "remove_tag": ["tag-001"]}
    response = client.post("/api/tags/unmark", json=unmark_payload)
    assert response.status_code == 200

    with app.app_context():
        row = get_db().execute("SELECT COUNT(*) AS total FROM contact_tags").fetchone()
        assert row["total"] == 0


def test_tag_error_category(client, monkeypatch):
    def fake_bad_post(url, params=None, json=None, timeout=None):
        if url.endswith("/cgi-bin/externalcontact/mark_tag"):
            return FakeResponse({"errcode": 40058, "errmsg": "invalid tag id"})
        return fake_wecom_post(url, params=params, json=json, timeout=timeout)

    monkeypatch.setattr("requests.get", fake_wecom_get)
    monkeypatch.setattr("requests.post", fake_bad_post)

    response = client.post(
        "/api/tags/mark",
        json={"userid": "sales_01", "external_userid": "wm_ext_001", "add_tag": ["bad-tag"]},
    )
    data = response.get_json()
    assert response.status_code == 502
    assert data["error_category"] == "标签不存在"


def test_admin_list_wecom_tags(client, monkeypatch):
    monkeypatch.setattr("requests.get", fake_wecom_get)
    monkeypatch.setattr("requests.post", fake_wecom_post)

    response = client.get("/api/admin/wecom/tags")
    data = response.get_json()
    assert response.status_code == 200
    assert data["items"] == [
        {"tag_id": "et-tag-002", "tag_name": "私域运营", "group_name": "业务标签", "group_id": "group-002"},
        {"tag_id": "et-tag-003", "tag_name": "低意向", "group_name": "客户分层", "group_id": "group-001"},
        {"tag_id": "et-tag-001", "tag_name": "高意向", "group_name": "客户分层", "group_id": "group-001"},
    ]


def test_class_user_management_bootstrap_creates_missing_lead_tag(client, app, monkeypatch):
    fake_post = make_signup_management_fake_wecom_post(include_lead_tag=False)
    monkeypatch.setattr("requests.get", fake_wecom_get)
    monkeypatch.setattr("requests.post", fake_post)

    response = client.post("/api/admin/class-user-management/bootstrap")
    payload = response.get_json()
    assert response.status_code == 200
    assert payload["created_tag_names"] == ["报名引流品"]
    assert {item["tag_name"] for item in payload["rules"]} == {"报名引流品", "已报名999", "已报名3999"}
    assert fake_post.state["created_payloads"][0]["group_id"] == "group-signup"
    assert fake_post.state["created_payloads"][0]["tag"] == [{"name": "报名引流品"}]

    with app.app_context():
        rows = get_db().execute(
            "SELECT tag_name, signup_status FROM signup_tag_rules ORDER BY signup_status ASC"
        ).fetchall()
        assert {row["tag_name"] for row in rows} == {"报名引流品", "已报名999", "已报名3999"}
        assert {row["signup_status"] for row in rows} == {"lead", "signed_999", "signed_3999"}


def test_sidebar_signup_tag_mark_is_mutually_exclusive(client, app, monkeypatch):
    fake_post = make_signup_management_fake_wecom_post(include_lead_tag=True)
    monkeypatch.setattr("requests.get", fake_wecom_get)
    monkeypatch.setattr("requests.post", fake_post)

    bootstrap_response = client.post("/api/admin/class-user-management/bootstrap")
    assert bootstrap_response.status_code == 200

    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            ("wm_ext_class_001", "班期客户A", "sales_01", "", "wm_ext_class_001"),
        )
        db.execute(
            """
            INSERT INTO contact_tags (external_userid, userid, tag_id, tag_name)
            VALUES (?, ?, ?, ?)
            """,
            ("wm_ext_class_001", "sales_01", "tag-lead", "报名引流品"),
        )
        db.execute(
            """
            INSERT INTO contact_tags (external_userid, userid, tag_id, tag_name)
            VALUES (?, ?, ?, ?)
            """,
            ("wm_ext_class_001", "sales_01", "tag-999", "已报名999"),
        )
        db.commit()

    response = client.post(
        "/api/sidebar/signup-tags/mark",
        json={"external_userid": "wm_ext_class_001", "owner_userid": "sales_01", "signup_status": "signed_3999"},
    )
    payload = response.get_json()
    assert response.status_code == 200
    assert payload["signup_status"] == "signed_3999"
    assert payload["current_tag"] == "已报名3999"
    assert set(payload["removed_tag_ids"]) == {"tag-lead", "tag-999"}
    assert fake_post.state["mark_payloads"][0]["userid"] == "sales_01"
    assert fake_post.state["mark_payloads"][0]["external_userid"] == "wm_ext_class_001"
    assert fake_post.state["mark_payloads"][0]["add_tag"] == ["tag-3999"]
    assert set(fake_post.state["mark_payloads"][0]["remove_tag"]) == {"tag-lead", "tag-999"}

    with app.app_context():
        rows = get_db().execute(
            """
            SELECT tag_id, tag_name
            FROM contact_tags
            WHERE external_userid = ? AND userid = ?
            ORDER BY tag_id ASC
            """,
            ("wm_ext_class_001", "sales_01"),
        ).fetchall()
        assert [dict(row) for row in rows] == [{"tag_id": "tag-3999", "tag_name": "已报名3999"}]


def test_class_user_management_list_export_and_ui(client, app, monkeypatch):
    fake_post = make_signup_management_fake_wecom_post(include_lead_tag=True)
    monkeypatch.setattr("requests.get", fake_wecom_get)
    monkeypatch.setattr("requests.post", fake_post)

    bootstrap_response = client.post("/api/admin/class-user-management/bootstrap")
    assert bootstrap_response.status_code == 200

    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO owner_role_map (userid, display_name, role, active)
            VALUES (?, ?, ?, ?)
            """,
            ("sales_01", "顾问一号", "sales", True),
        )
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("wm_ext_class_101", "学员甲", "sales_01", "", "wm_ext_class_101", "2026-03-23 10:00:00"),
        )
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("wm_ext_class_102", "学员乙", "sales_01", "", "wm_ext_class_102", "2026-03-24 11:00:00"),
        )
        db.execute(
            """
            INSERT INTO people (mobile, third_party_user_id, created_at, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            ("13800138001", ""),
        )
        person_id = db.execute("SELECT id FROM people WHERE mobile = ?", ("13800138001",)).fetchone()["id"]
        db.execute(
            """
            INSERT INTO external_contact_bindings (
                external_userid, person_id, first_bound_by_userid, first_owner_userid, last_owner_userid, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            ("wm_ext_class_101", person_id, "sales_01", "sales_01", "sales_01"),
        )
        db.execute(
            """
            INSERT INTO wecom_external_contact_follow_users (
                corp_id, external_userid, user_id, relation_status, is_primary, remark, description, raw_follow_user
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("ww-test", "wm_ext_class_101", "sales_01", "active", True, "", "", "{}"),
        )
        db.execute(
            """
            INSERT INTO wecom_external_contact_follow_users (
                corp_id, external_userid, user_id, relation_status, is_primary, remark, description, raw_follow_user
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("ww-test", "wm_ext_class_102", "sales_01", "active", True, "", "", "{}"),
        )
        db.execute(
            """
            INSERT INTO class_user_status_current (
                external_userid, signup_status, signup_label_name, customer_name_snapshot, owner_userid_snapshot,
                mobile_snapshot, set_by_userid, set_at, wecom_tag_sync_status, wecom_tag_sync_error, status_flags_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?)
            """,
            ("wm_ext_class_101", "lead", "报名引流品", "学员甲", "sales_01", "13800138001", "sales_01", "success", "", "{}"),
        )
        db.execute(
            """
            INSERT INTO class_user_status_current (
                external_userid, signup_status, signup_label_name, customer_name_snapshot, owner_userid_snapshot,
                mobile_snapshot, set_by_userid, set_at, wecom_tag_sync_status, wecom_tag_sync_error, status_flags_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?)
            """,
            ("wm_ext_class_102", "signed_999", "已报名999", "学员乙", "sales_01", "", "sales_01", "success", "", "{}"),
        )
        db.commit()

    list_response = client.get("/api/admin/class-user-management?signup_status=lead")
    list_payload = list_response.get_json()
    assert list_response.status_code == 200
    assert list_payload["total"] == 1
    assert list_payload["items"][0]["customer_name"] == "学员甲"
    assert list_payload["items"][0]["mobile"] == "13800138001"
    assert list_payload["items"][0]["follow_user_display_name"] == "顾问一号"
    assert list_payload["items"][0]["status_fields"]["current_tag_name"] == "报名引流品"
    stats = {item["signup_status"]: item["count"] for item in list_payload["stats"]}
    assert stats["lead"] == 1
    assert stats["signed_999"] == 1
    assert stats["signed_3999"] == 0
    assert "operation_flags" in list_payload["items"][0]["status_fields"]
    assert "reserved_filters" in list_payload["meta"]
    assert list_payload["tag_initialization"]["initialized"] is True

    export_response = client.get("/api/admin/class-user-management/export?signup_status=signed_999")
    export_text = export_response.get_data(as_text=True)
    assert export_response.status_code == 200
    assert "application/vnd.ms-excel" in export_response.headers["Content-Type"]
    assert "客户昵称" in export_text
    assert "学员乙" in export_text
    assert "报名引流品" not in export_text

    ui_response = client.get("/admin/class-user-management/ui", follow_redirects=False)
    assert ui_response.status_code == 410

    shell_response = client.get("/admin/class-users?tab=class-users")
    shell_text = shell_response.get_data(as_text=True)
    assert shell_response.status_code == 200
    assert "客户管理后台" in shell_text
    assert "运营管理" in shell_text
    assert "班级状态" in shell_text

    legacy_response = client.get("/admin/_legacy/class-user-management")
    assert legacy_response.status_code == 404


def test_admin_questionnaire_ui_redirects_to_management_page(client):
    response = client.get("/admin/questionnaires/ui", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/questionnaires")
    assert response.headers["X-Admin-Deprecated"] == "true"


def test_admin_questionnaire_legacy_ui_is_gone(client):
    response = client.get("/admin/_legacy/questionnaires", follow_redirects=False)

    assert response.status_code == 404


def test_admin_questionnaire_management_page_exists(client):
    response = client.get("/admin/questionnaires")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "客户管理后台" in text
    assert "问卷管理" in text
    assert "创建新问卷" in text
    assert "创建测评问卷" in text
    assert "多维测评" in text
    assert "问卷名称" in text
    assert "创建时间" in text
    assert "提交数" in text
    assert "还没有问卷" in text
    assert "没有匹配的问卷，请调整搜索词或筛选条件" in text
    assert 'data-action="delete"' in text
    assert "questionnaire-name-sub" not in text
    assert '<div class="workspace">' not in text


def test_admin_questionnaire_editor_new_page_contains_tag_picker_fallback(client):
    response = client.get("/admin/questionnaires/new")
    text = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "返回问卷管理" in text
    assert "新建问卷" in text
    assert "保存问卷" in text
    assert "重置当前" in text
    assert "题型" in text
    assert "手工填写" in text or "tag_id" in text
    assert "企微标签加载失败" in text
    assert "多维测评" in text
    assert "测评维度" in text
    assert "测评分型" in text
    assert "一键添加多维测评题目" in text
    assert "从空白模板开始搭建题目、标签和分数规则。" not in text
    assert '<div id="questionnaire-list"' not in text


def test_admin_questionnaire_editor_assessment_mode_prefills_config(client):
    response = client.get("/admin/questionnaires/new?mode=assessment")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'defaultAssessment: true' in text
    assert "小 IP 商业力测评" in text
    assert "用户获取" in text
    assert "用户成交" in text


def test_admin_questionnaire_editor_existing_page_contains_editor(client):
    create_response = client.post("/api/admin/questionnaires", json=_build_questionnaire_payload())
    questionnaire_id = create_response.get_json()["questionnaire"]["id"]

    response = client.get(f"/admin/questionnaires/{questionnaire_id}")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "返回问卷管理" in text
    assert "编辑问卷" in text
    assert "分享" in text
    assert "下载数据" in text
    assert "删除此问卷" in text or "删除" in text
    assert "从空白模板开始搭建题目、标签和分数规则。" not in text
    assert '<div id="questionnaire-list"' not in text


def test_admin_questionnaire_editor_page_script_has_valid_javascript(client):
    response = client.get("/admin/questionnaires/new")
    text = response.get_data(as_text=True)
    match = re.search(r"<script>(.*?)</script>", text, re.S)
    assert match is not None
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as handle:
        handle.write(match.group(1))
        script_path = handle.name
    completed = subprocess.run(["node", "--check", script_path], capture_output=True, text=True)
    Path(script_path).unlink(missing_ok=True)
    assert completed.returncode == 0, completed.stderr


def test_admin_questionnaire_editor_page_uses_scrollable_sticky_inspector(client):
    response = client.get("/admin/questionnaires/new")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "max-height: calc(100vh - 104px);" in text
    assert "min-height: 0;" in text
    assert "height: calc(100vh - 104px);" in text
    assert "overflow-y: auto;" in text
    assert "overscroll-behavior: contain;" in text


def test_class_user_backoffice_legacy_ui_is_gone(client):
    response = client.get("/admin/class-user-backoffice/ui", follow_redirects=False)

    assert response.status_code == 404

    shell_response = client.get("/admin/class-users?tab=class-users")
    shell_text = shell_response.get_data(as_text=True)
    assert shell_response.status_code == 200
    assert "班级状态" in shell_text


def test_questionnaire_preflight_returns_200_with_missing_config(client, app, monkeypatch):
    app.config.update(
        WECHAT_MP_APP_ID="",
        WECHAT_MP_APP_SECRET="",
        SECRET_KEY="",
        WECOM_CORP_ID="",
        WECOM_CONTACT_SECRET="",
        ENABLE_DEBUG_QUESTIONNAIRE_SESSION_API=False,
    )
    monkeypatch.setattr(
        "wecom_ability_service.application.questionnaire.queries.ListAvailableWeComTagsQuery.__call__",
        lambda self, dto=None: [],
    )

    response = client.get("/api/admin/questionnaires/preflight")
    data = response.get_json()
    assert response.status_code == 200
    assert data["wechat_oauth_configured"] is False
    assert data["wecom_contact_configured"] is False
    assert data["debug_session_api_enabled"] is False
    assert data["questionnaire_admin_ui_enabled"] is True
    assert data["wecom_tags_api_available"] is True


def test_customer_timeline_aggregates_events_with_desc_paging_and_messages_compat(client, app):
    event_time = int(datetime(2026, 3, 24, 14, 0, 0).timestamp())

    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("wm_ext_timeline_001", "时间线客户", "sales_01", "老客", "用于 timeline 聚合", "2026-03-24 09:00:00"),
        )
        db.execute(
            """
            INSERT INTO archived_messages (
                seq, msgid, chat_type, external_userid, owner_userid, sender, receiver, msgtype, content, send_time, raw_payload, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                9001,
                "timeline-msg-001",
                "private",
                "wm_ext_timeline_001",
                "sales_01",
                "sales_01",
                "wm_ext_timeline_001",
                "text",
                "第一条聊天记录",
                "2026-03-20 10:00:00",
                json.dumps({"decrypted_message": {"from": "sales_01", "tolist": ["wm_ext_timeline_001"]}}, ensure_ascii=False),
                "2026-03-20 10:00:01",
            ),
        )
        db.execute(
            """
            INSERT INTO questionnaires (slug, name, title, description, is_disabled, redirect_url, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "timeline-form",
                "线索摸底",
                "线索摸底问卷",
                "",
                False,
                "https://example.com/next",
                "2026-03-19 10:00:00",
                "2026-03-19 10:00:00",
            ),
        )
        questionnaire = db.execute("SELECT id FROM questionnaires WHERE slug = ?", ("timeline-form",)).fetchone()
        db.execute(
            """
            INSERT INTO questionnaire_submissions (
                questionnaire_id, respondent_key, openid, unionid, external_userid, follow_user_userid, matched_by,
                source_channel, campaign_id, staff_id, total_score, final_tags, redirect_url_snapshot, submitted_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(questionnaire["id"]),
                "union-timeline-001",
                "openid-timeline-001",
                "union-timeline-001",
                "wm_ext_timeline_001",
                "sales_01",
                "unionid",
                "朋友圈",
                "cmp-timeline",
                "staff-007",
                88.5,
                json.dumps(["high_intent", "ready_to_call"], ensure_ascii=False),
                "https://example.com/next",
                "2026-03-21 11:00:00",
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
                "wm_ext_timeline_001",
                "lead",
                "signed_999",
                "报名引流品",
                "已报名999",
                "时间线客户",
                "sales_01",
                "13800138000",
                "sales_01",
                "2026-03-23 13:00:00",
                "success",
                "",
                "{}",
                "2026-03-23 13:00:01",
            ),
        )
        db.execute(
            """
            INSERT INTO wecom_external_contact_event_logs (
                corp_id, event_type, change_type, external_userid, user_id, event_time,
                event_key, payload_xml, payload_json, process_status, retry_count, error_message, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ww-test",
                "change_external_contact",
                "add_external_contact",
                "wm_ext_timeline_001",
                "sales_01",
                event_time,
                "timeline-event-001",
                "<xml></xml>",
                json.dumps({"ChangeType": "add_external_contact"}, ensure_ascii=False),
                "success",
                0,
                "",
                "2026-03-24 14:00:01",
                "2026-03-24 14:00:01",
            ),
        )
        db.commit()

    response = client.get("/api/customers/wm_ext_timeline_001/timeline?limit=2&offset=0")
    data = response.get_json()
    assert response.status_code == 200
    assert data["ok"] is True
    assert data["timeline"]["external_userid"] == "wm_ext_timeline_001"
    assert data["timeline"]["total"] == 4
    assert data["timeline"]["count"] == 2
    assert data["timeline"]["limit"] == 2
    assert data["timeline"]["offset"] == 0
    assert data["timeline"]["filters"] == {"event_type": "", "limit": "2", "offset": "0"}
    assert [item["event_type"] for item in data["timeline"]["items"]] == ["wecom_event", "status_change"]

    next_response = client.get("/api/customers/wm_ext_timeline_001/timeline?limit=2&offset=2")
    next_data = next_response.get_json()
    assert next_response.status_code == 200
    assert next_data["timeline"]["count"] == 2
    assert [item["event_type"] for item in next_data["timeline"]["items"]] == ["questionnaire_submit", "message"]

    filtered_response = client.get("/api/customers/wm_ext_timeline_001/timeline?event_type=message")
    filtered_data = filtered_response.get_json()
    assert filtered_response.status_code == 200
    assert filtered_data["timeline"]["count"] == 1
    assert filtered_data["timeline"]["items"][0]["event_type"] == "message"
    assert filtered_data["timeline"]["items"][0]["metadata"]["content"] == "第一条聊天记录"

    final_response = client.get("/api/customers/wm_ext_timeline_001/timeline?limit=2&offset=4")
    final_data = final_response.get_json()
    assert final_response.status_code == 200
    assert final_data["timeline"]["count"] == 0
    assert final_data["timeline"]["items"] == []

    messages_response = client.get("/api/messages/wm_ext_timeline_001")
    messages_data = messages_response.get_json()
    assert messages_response.status_code == 200
    assert messages_data["ok"] is True
    assert len(messages_data["messages"]) == 1
    assert messages_data["messages"][0]["msgid"] == "timeline-msg-001"


def test_customer_timeline_returns_404_for_unknown_customer(client):
    response = client.get("/api/customers/wm_ext_missing_001/timeline")
    data = response.get_json()
    assert response.status_code == 404
    assert data["ok"] is False


def test_questionnaire_preflight_requires_non_default_secret_key(client, app, monkeypatch):
    app.config.update(
        WECHAT_MP_APP_ID="wx-live-test",
        WECHAT_MP_APP_SECRET="wx-live-secret",
        SECRET_KEY="dev-secret-key-change-me",
    )
    monkeypatch.setattr(
        "wecom_ability_service.application.questionnaire.queries.ListAvailableWeComTagsQuery.__call__",
        lambda self, dto=None: [],
    )

    response = client.get("/api/admin/questionnaires/preflight")
    data = response.get_json()
    assert response.status_code == 200
    assert data["wechat_oauth_configured"] is False


def test_questionnaire_preflight_handles_wecom_tags_error(client, monkeypatch):
    def _raise_tags_error(self, dto=None):
        raise RuntimeError("tags boom")

    monkeypatch.setattr(
        "wecom_ability_service.application.questionnaire.queries.ListAvailableWeComTagsQuery.__call__",
        _raise_tags_error,
    )

    response = client.get("/api/admin/questionnaires/preflight")
    data = response.get_json()
    assert response.status_code == 200
    assert data["wecom_tags_api_available"] is False
    assert "tags boom" in data["wecom_tags_api_error"]


def test_latest_submit_debug_returns_no_submission_found(client):
    create_response = client.post("/api/admin/questionnaires", json=_build_questionnaire_payload())
    questionnaire_id = create_response.get_json()["questionnaire"]["id"]

    response = client.get(f"/api/admin/questionnaires/{questionnaire_id}/latest-submit-debug")
    data = response.get_json()
    assert response.status_code == 200
    assert data["ok"] is False
    assert data["error"] == "no_submission_found"


def test_latest_submit_debug_returns_latest_submission_and_scrm_status(client, app):
    create_response = client.post("/api/admin/questionnaires", json=_build_questionnaire_payload())
    questionnaire_id = create_response.get_json()["questionnaire"]["id"]

    with app.app_context():
        db = get_db()
        identity_row = db.execute(
            """
            INSERT INTO wecom_external_contact_identity_map (
                corp_id, external_userid, unionid, openid, follow_user_userid, name, status, raw_profile
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id
            """,
            ("ww-test", "wm_ext_001", "unionid-001", "openid-001", "sales_01", "调试客户", "active", "{}"),
        ).fetchone()
        submission_row = db.execute(
            """
            INSERT INTO questionnaire_submissions (
                questionnaire_id, identity_map_id, respondent_key, openid, unionid, external_userid,
                follow_user_userid, matched_by, source_channel, campaign_id, staff_id,
                total_score, final_tags, redirect_url_snapshot, submitted_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            RETURNING id, submitted_at
            """,
            (
                questionnaire_id,
                identity_row["id"],
                "resp-001",
                "openid-001",
                "unionid-001",
                "wm_ext_001",
                "sales_01",
                "unionid",
                "wechat",
                "cmp-001",
                "staff-001",
                8,
                json.dumps(["tag_id_1", "tag_id_2"], ensure_ascii=False),
                "https://example.com/next",
            ),
        ).fetchone()
        db.execute(
            """
            INSERT INTO questionnaire_scrm_apply_logs (
                submission_id, external_userid, follow_user_userid, final_tags, status, error_message, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                submission_row["id"],
                "wm_ext_001",
                "sales_01",
                json.dumps(["tag_id_1", "tag_id_2"], ensure_ascii=False),
                "success",
                "",
            ),
        )
        db.commit()

    response = client.get(f"/api/admin/questionnaires/{questionnaire_id}/latest-submit-debug")
    data = response.get_json()
    assert response.status_code == 200
    assert data["ok"] is True
    assert data["questionnaire_id"] == questionnaire_id
    assert data["matched_by"] == "unionid"
    assert data["identity_map_id"] == identity_row["id"]
    assert data["external_userid"] == "wm_ext_001"
    assert data["follow_user_userid"] == "sales_01"
    assert data["total_score"] == 8.0
    assert data["final_tags"] == ["tag_id_1", "tag_id_2"]
    assert data["scrm_apply_status"] == "success"
    assert data["scrm_apply_error"] == ""


def test_contacts_sync_detail_and_description_update(client, app, monkeypatch):
    monkeypatch.setattr("requests.get", fake_wecom_get)
    monkeypatch.setattr("requests.post", fake_wecom_post)

    list_response = client.get("/api/contacts?owner_userid=sales_01")
    list_data = list_response.get_json()
    assert list_response.status_code == 200
    contacts_by_id = {item["external_userid"]: item for item in list_data["contacts"]}
    assert contacts_by_id["wm_ext_001"]["customer_name"] == "周青"

    detail_response = client.get("/api/contacts/wm_ext_001")
    detail_data = detail_response.get_json()
    assert detail_response.status_code == 200
    assert detail_data["contact"]["remark"] == "老同学介绍"
    assert detail_data["contact"]["description"] == "wm_ext_001"

    update_response = client.post(
        "/api/contacts/description",
        json={
            "userid": "sales_01",
            "external_userid": "wm_ext_001",
            "description": "wm_ext_001",
        },
    )
    update_data = update_response.get_json()
    assert update_response.status_code == 200
    assert update_data["result"]["errcode"] == 0
    assert update_data["contact"]["external_userid"] == "wm_ext_001"

    with app.app_context():
        row = get_db().execute(
            "SELECT external_userid, customer_name, owner_userid, remark, description FROM contacts WHERE external_userid = ?",
            ("wm_ext_001",),
        ).fetchone()
        assert row["customer_name"] == "周青"
        assert row["description"] == "wm_ext_001"


def test_contacts_full_sync_and_sync_new(client, app, monkeypatch):
    monkeypatch.setattr("requests.get", fake_wecom_get)
    monkeypatch.setattr("requests.post", fake_wecom_post)

    full_sync_response = client.post("/api/contacts/full-sync")
    full_sync_data = full_sync_response.get_json()
    assert full_sync_response.status_code == 200
    assert full_sync_data["fetched_count"] == 3
    assert full_sync_data["inserted_count"] == 3
    assert full_sync_data["updated_count"] == 0
    assert full_sync_data["description_updated_count"] == 1
    assert full_sync_data["contacts_total"] == 3

    with app.app_context():
        row = get_db().execute(
            "SELECT description FROM contacts WHERE external_userid = ?",
            ("wm_ext_002",),
        ).fetchone()
        assert row["description"] == "wm_ext_002"
        custom_row = get_db().execute(
            "SELECT description FROM contacts WHERE external_userid = ?",
            ("wm_ext_003",),
        ).fetchone()
        assert custom_row["description"] == "not-target"

    sync_new_response = client.post("/api/contacts/sync-new")
    sync_new_data = sync_new_response.get_json()
    assert sync_new_response.status_code == 200
    assert sync_new_data["fetched_count"] == 0
    assert sync_new_data["inserted_count"] == 0
    assert sync_new_data["updated_count"] == 0


def test_contacts_normalize_description(client, app, monkeypatch):
    monkeypatch.setattr("requests.get", fake_wecom_get)
    monkeypatch.setattr("requests.post", fake_wecom_post)

    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO owner_role_map (userid, display_name, role, active)
            VALUES (?, ?, ?, ?)
            """,
            ("sales_01", "销售一号", "sales", True),
        )
        db.execute(
            """
            INSERT INTO signup_tag_rules (tag_id, tag_name, signup_status, active)
            VALUES (?, ?, ?, ?)
            """,
            ("tag-999", "已报名999", "signed_999", True),
        )
        db.execute(
            """
            INSERT INTO signup_tag_rules (tag_id, tag_name, signup_status, active)
            VALUES (?, ?, ?, ?)
            """,
            ("tag-3999", "已报名3999", "signed_3999", True),
        )
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("wm_ext_legacy", "旧格式客户", "sales_01", "旧备注", "external_userid: wm_ext_legacy"),
        )
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("wm_ext_empty", "空描述客户", "sales_01", "空备注", ""),
        )
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("wm_ext_target", "正确客户", "sales_01", "对", "wm_ext_target"),
        )
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("wm_ext_custom", "人工客户", "sales_01", "人工", "手动备注"),
        )
        db.commit()

    response = client.post("/api/contacts/normalize-description")
    data = response.get_json()
    assert response.status_code == 200
    assert data["updated_count"] == 2
    assert data["untouched_count"] == 1
    assert data["skipped_count"] == 1

    with app.app_context():
        db = get_db()
        legacy = db.execute(
            "SELECT description FROM contacts WHERE external_userid = ?",
            ("wm_ext_legacy",),
        ).fetchone()
        empty = db.execute(
            "SELECT description FROM contacts WHERE external_userid = ?",
            ("wm_ext_empty",),
        ).fetchone()
        target = db.execute(
            "SELECT description FROM contacts WHERE external_userid = ?",
            ("wm_ext_target",),
        ).fetchone()
        custom = db.execute(
            "SELECT description FROM contacts WHERE external_userid = ?",
            ("wm_ext_custom",),
        ).fetchone()
        assert legacy["description"] == "wm_ext_legacy"
        assert empty["description"] == "wm_ext_empty"
        assert target["description"] == "wm_ext_target"
        assert custom["description"] == "手动备注"


def test_get_contact_paginates_follow_users(client, monkeypatch):
    monkeypatch.setattr("requests.get", fake_wecom_get)
    monkeypatch.setattr("requests.post", fake_wecom_post)

    response = client.get("/api/contacts/wm_ext_paged?owner_userid=sales_01")
    data = response.get_json()
    assert response.status_code == 200
    assert data["contact"]["external_userid"] == "wm_ext_paged"
    assert data["contact"]["remark"] == "分页命中"
    assert data["contact"]["description"] == "wm_ext_paged"


def test_mcp_tools_and_message_batches(client, app, monkeypatch):
    monkeypatch.setattr("requests.get", fake_wecom_get)
    monkeypatch.setattr("requests.post", fake_wecom_post)
    app.config["MCP_BEARER_TOKEN"] = "mcp-token"

    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO owner_role_map (userid, display_name, role, active)
            VALUES (?, ?, ?, ?)
            """,
            ("sales_01", "销售一号", "sales", True),
        )
        db.execute(
            """
            INSERT INTO signup_tag_rules (tag_id, tag_name, signup_status, active)
            VALUES (?, ?, ?, ?)
            """,
            ("tag-999", "已报名999", "signed_999", True),
        )
        db.execute(
            """
            INSERT INTO signup_tag_rules (tag_id, tag_name, signup_status, active)
            VALUES (?, ?, ?, ?)
            """,
            ("tag-3999", "已报名3999", "signed_3999", True),
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
            INSERT INTO people (mobile, third_party_user_id, created_at, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            ("13800138000", "tp-mcp-001"),
        )
        person_id = db.execute("SELECT id FROM people WHERE mobile = ?", ("13800138000",)).fetchone()["id"]
        db.execute(
            """
            INSERT INTO external_contact_bindings (
                external_userid, person_id, first_bound_by_userid, first_owner_userid, last_owner_userid, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            ("wm_ext_001", person_id, "sales_01", "sales_01", "sales_01"),
        )
        db.execute(
            """
            INSERT INTO group_chats (chat_id, group_name, owner_userid, notice, member_count, status, raw_payload)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("chat-001", "测试群", "sales_01", "", 2, "active", "{}"),
        )
        db.execute(
            """
            INSERT INTO contact_tags (external_userid, userid, tag_id, tag_name)
            VALUES (?, ?, ?, ?)
            """,
            ("wm_ext_001", "sales_01", "tag-999", "已报名999"),
        )
        db.execute(
            """
            INSERT INTO archived_messages (seq, msgid, chat_type, external_userid, owner_userid, sender, receiver, msgtype, content, send_time, raw_payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                "batch-msg-001",
                "private",
                "wm_ext_001",
                "sales_01",
                "wm_ext_001",
                "sales_01",
                "text",
                "你好",
                "2026-03-21 10:01:10",
                '{"decrypted_message":{"from":"wm_ext_001","tolist":["sales_01"],"roomid":""}}',
            ),
        )
        db.execute(
            """
            INSERT INTO archived_messages (seq, msgid, chat_type, external_userid, owner_userid, sender, receiver, msgtype, content, send_time, raw_payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                2,
                "batch-msg-002",
                "group",
                "wm_ext_001",
                "sales_01",
                "sales_01",
                "chat-001",
                "text",
                "群里同步一下",
                "2026-03-21 10:02:15",
                '{"decrypted_message":{"from":"sales_01","tolist":["wm_ext_001"],"roomid":"chat-001"}}',
            ),
        )
        db.commit()

    headers = {"Authorization": "Bearer mcp-token"}

    unauthorized = client.post("/mcp", json={"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {}})
    assert unauthorized.status_code == 401

    wrong_token = client.post(
        "/mcp",
        headers={"Authorization": "Bearer wrong-token"},
        json={"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {}},
    )
    assert wrong_token.status_code == 401
    assert wrong_token.get_json() == {"ok": False, "error": "invalid internal token"}

    init_resp = client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert init_resp.status_code == 200
    assert init_resp.get_json()["result"]["serverInfo"]["name"] == "openclaw-wecom-mcp"

    list_resp = client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    tools = list_resp.get_json()["result"]["tools"]
    tool_names = {tool["name"] for tool in tools}
    assert "resolve_customer" in tool_names
    assert "get_contact" in tool_names
    assert "get_pending_message_batches" in tool_names
    assert "get_owner_role_map" in tool_names
    assert "get_signup_tag_rules" in tool_names
    assert "get_routing_config" in tool_names

    contact_resp = client.post(
        "/mcp",
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": 21,
            "method": "tools/call",
            "params": {"name": "get_contact", "arguments": {"external_userid": "wm_ext_001"}},
        },
    )
    contact_payload = contact_resp.get_json()["result"]["structuredContent"]
    assert contact_payload["owner_role"] == "sales"
    assert contact_payload["tags"][0]["tag_id"] == "tag-999"
    assert contact_payload["signup_status"] == "signed_999"
    assert contact_payload["routing_context"]["routing_target"] == "sales_handle"

    routing_resp = client.post(
        "/mcp",
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": 22,
            "method": "tools/call",
            "params": {"name": "get_routing_config", "arguments": {}},
        },
    )
    routing_payload = routing_resp.get_json()["result"]["structuredContent"]
    assert routing_payload["owner_role_map"][0]["userid"] == "sales_01"
    assert routing_payload["signup_tag_rules"]["tag_group_name"] == "AI 产品报名情况"
    assert routing_payload["signup_tag_rules"]["items"][0]["tag_id"] in {"tag-999", "tag-3999"}
    assert routing_payload["routing_rules"]["signed_3999"]["when_owner_role_sales"] == "delivery_redirect"

    pending_resp = client.post(
        "/mcp",
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "get_pending_message_batches", "arguments": {"limit": 10}},
        },
    )
    pending_batches = pending_resp.get_json()["result"]["structuredContent"]
    assert len(pending_batches["items"]) == 1
    batch_id = pending_batches["items"][0]["id"]
    assert pending_batches["items"][0]["message_count"] == 2
    assert pending_batches["next_cursor"] == ""

    batch_resp = client.post(
        "/mcp",
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "get_message_batch", "arguments": {"batch_id": batch_id, "limit": 1}},
        },
    )
    batch_payload = batch_resp.get_json()["result"]["structuredContent"]
    assert batch_payload["batch"]["id"] == batch_id
    assert len(batch_payload["messages"]) == 1
    assert batch_payload["paging"]["next_cursor"] != ""

    batch_resp_page_2 = client.post(
        "/mcp",
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": 41,
            "method": "tools/call",
            "params": {
                "name": "get_message_batch",
                "arguments": {"batch_id": batch_id, "limit": 2, "cursor": batch_payload["paging"]["next_cursor"]},
            },
        },
    )
    batch_payload_page_2 = batch_resp_page_2.get_json()["result"]["structuredContent"]
    assert len(batch_payload_page_2["messages"]) == 1
    assert batch_payload_page_2["messages"][0]["group_name"] == "测试群"

    ack_resp = client.post(
        "/mcp",
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "ack_message_batch",
                "arguments": {"batch_id": batch_id, "ack_note": "openclaw-done", "acked_by": "openclaw"},
            },
        },
    )
    ack_payload = ack_resp.get_json()["result"]["structuredContent"]
    assert ack_payload["status"] == "acked"
    assert ack_payload["ack_note"] == "openclaw-done"
    assert ack_payload["acked_by"] == "openclaw"

    ack_resp_repeat = client.post(
        "/mcp",
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {
                "name": "ack_message_batch",
                "arguments": {"batch_id": batch_id, "ack_note": "confirmed", "acked_by": "openclaw"},
            },
        },
    )
    ack_payload_repeat = ack_resp_repeat.get_json()["result"]["structuredContent"]
    assert ack_payload_repeat["status"] == "acked"
    assert ack_payload_repeat["ack_note"] == "confirmed"

    recent_resp = client.post(
        "/mcp",
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {
                "name": "get_recent_messages",
                "arguments": {"external_userid": "wm_ext_001", "limit": 2},
            },
        },
    )
    recent_payload = recent_resp.get_json()["result"]["structuredContent"]
    assert recent_payload["external_userid"] == "wm_ext_001"
    assert isinstance(recent_payload["messages"], list)
    assert recent_payload["messages"][0]["external_userid"] == "wm_ext_001"


def test_mcp_resolve_customer_and_customer_ref_mobile(client, app, monkeypatch):
    monkeypatch.setattr("requests.get", fake_wecom_get)
    monkeypatch.setattr("requests.post", fake_wecom_post)
    app.config["MCP_BEARER_TOKEN"] = "mcp-token"

    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO owner_role_map (userid, display_name, role, active)
            VALUES (?, ?, ?, ?)
            """,
            ("sales_01", "销售一号", "sales", True),
        )
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            ("wm_ext_mobile_001", "手机号客户", "sales_01", "手机命中", "wm_ext_mobile_001"),
        )
        db.execute(
            """
            INSERT INTO people (mobile, third_party_user_id, created_at, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            ("13900000011", "tp-mobile-001"),
        )
        person_id = db.execute("SELECT id FROM people WHERE mobile = ?", ("13900000011",)).fetchone()["id"]
        db.execute(
            """
            INSERT INTO external_contact_bindings (
                external_userid, person_id, first_bound_by_userid, first_owner_userid, last_owner_userid, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            ("wm_ext_mobile_001", person_id, "sales_01", "sales_01", "sales_01"),
        )
        db.execute(
            """
            INSERT INTO class_user_status_current (
                external_userid, signup_status, signup_label_name, customer_name_snapshot, owner_userid_snapshot,
                mobile_snapshot, set_by_userid, set_at, wecom_tag_sync_status, wecom_tag_sync_error, status_flags_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?)
            """,
            ("wm_ext_mobile_001", "lead", "报名引流品", "手机号客户", "sales_01", "13900000011", "sales_01", "success", "", "{}"),
        )
        db.execute(
            """
            INSERT INTO archived_messages
            (seq, msgid, chat_type, external_userid, owner_userid, sender, receiver, msgtype, content, send_time, raw_payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                11,
                "mcp-mobile-msg-001",
                "private",
                "wm_ext_mobile_001",
                "sales_01",
                "wm_ext_mobile_001",
                "sales_01",
                "text",
                "手机号入口也能命中",
                "2026-03-24 10:00:00",
                '{"decrypted_message":{"from":"wm_ext_mobile_001","tolist":["sales_01"],"roomid":""}}',
            ),
        )
        db.commit()

    headers = {"Authorization": "Bearer mcp-token"}

    resolve_resp = client.post(
        "/mcp",
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": 101,
            "method": "tools/call",
            "params": {
                "name": "resolve_customer",
                "arguments": {"customer_ref": "13900000011", "include_context": True},
            },
        },
    )
    resolve_payload = resolve_resp.get_json()["result"]["structuredContent"]
    assert resolve_payload["ok"] is True
    assert resolve_payload["matched_by"] == "mobile"
    assert resolve_payload["external_userid"] == "wm_ext_mobile_001"
    assert resolve_payload["customer"]["mobile"] == "13900000011"
    assert resolve_payload["recent_messages"][0]["external_userid"] == "wm_ext_mobile_001"
    assert isinstance(resolve_payload["recent_timeline_events"], list)

    contact_resp = client.post(
        "/mcp",
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": 102,
            "method": "tools/call",
            "params": {"name": "get_contact", "arguments": {"customer_ref": "13900000011"}},
        },
    )
    contact_payload = contact_resp.get_json()["result"]["structuredContent"]
    assert contact_payload["external_userid"] == "wm_ext_mobile_001"
    assert contact_payload["owner_role"] == "sales"

    mark_resp = client.post(
        "/mcp",
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": 103,
            "method": "tools/call",
            "params": {
                "name": "mark_tags",
                "arguments": {"customer_ref": "13900000011", "userid": "sales_01", "add_tag": ["tag-001"]},
            },
        },
    )
    mark_payload = mark_resp.get_json()["result"]["structuredContent"]
    assert mark_payload["ok"] is True

    with app.app_context():
        row = get_db().execute(
            "SELECT external_userid, userid, tag_id FROM contact_tags WHERE external_userid = ?",
            ("wm_ext_mobile_001",),
        ).fetchone()
        assert row["external_userid"] == "wm_ext_mobile_001"
        assert row["userid"] == "sales_01"
        assert row["tag_id"] == "tag-001"


def test_group_chats_full_sync_and_message_enrichment(client, app, monkeypatch):
    monkeypatch.setattr("requests.get", fake_wecom_get)
    monkeypatch.setattr("requests.post", fake_wecom_post)

    sync_response = client.post("/api/group-chats/full-sync")
    sync_data = sync_response.get_json()
    assert sync_response.status_code == 200
    assert sync_data["fetched_count"] == 2
    assert sync_data["inserted_count"] == 2
    assert sync_data["group_chats_total"] == 2

    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO archived_messages
            (seq, msgid, chat_type, external_userid, owner_userid, sender, receiver, msgtype, content, send_time, raw_payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT DO NOTHING
            """,
            (
                21,
                "msg-group-001",
                "group",
                "wm_ext_001",
                "sales_01",
                "wm_ext_001",
                "sales_01,wm_ext_001",
                "text",
                "群里你好",
                "2026-03-15 21:00:00",
                '{"decrypted_message":{"from":"wm_ext_001","tolist":["sales_01","wm_ext_001"],"roomid":"chat-001","msgtype":"text"},"msgid":"msg-group-001"}',
            ),
        )
        db.commit()

    response = client.get("/api/messages/wm_ext_001?chat_type=group")
    messages = response.get_json()["messages"]
    assert messages[0]["chat_id"] == "chat-001"
    assert messages[0]["group_name"] == "高意向测试群"


def test_wecom_event_msgaudit_notify_triggers_incremental_sync(client, monkeypatch):
    triggered = {"called": 0}

    def fake_sync():
        triggered["called"] += 1
        return {"fetched_count": 1}

    monkeypatch.setattr("wecom_ability_service.routes._trigger_incremental_archive_sync", fake_sync)

    token = "callback-token"
    aes_key = "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG"
    corp_id = "ww-test"
    plain_xml = "<xml><Event>msgaudit_notify</Event></xml>"
    encrypted = encrypt_message(plain_xml, aes_key, corp_id)
    timestamp = "1774000000"
    nonce = "nonce-001"
    signature = compute_signature(token, timestamp, nonce, encrypted)
    body = f"<xml><Encrypt>{encrypted}</Encrypt></xml>"

    response = client.post(
        f"/api/wecom/events?msg_signature={signature}&timestamp={timestamp}&nonce={nonce}",
        data=body,
        content_type="application/xml",
    )
    assert response.status_code == 200
    assert triggered["called"] == 1


def test_wecom_event_group_dismiss_updates_status(client, app, monkeypatch):
    monkeypatch.setattr("requests.get", fake_wecom_get)
    monkeypatch.setattr("requests.post", fake_wecom_post)

    with app.app_context():
        from wecom_ability_service.services import upsert_group_chats

        upsert_group_chats(
            [
                {
                    "chat_id": "chat-001",
                    "group_name": "高意向测试群",
                    "owner_userid": "sales_01",
                    "notice": "群公告A",
                    "member_count": 2,
                    "status": "active",
                    "create_time": "2025-11-01 12:00:05",
                    "dismissed_at": "",
                    "raw_payload": "{}",
                }
            ]
        )

    token = "callback-token"
    aes_key = "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG"
    corp_id = "ww-test"
    plain_xml = "<xml><Event>change_external_chat</Event><ChangeType>dismiss</ChangeType><ChatId>chat-001</ChatId></xml>"
    encrypted = encrypt_message(plain_xml, aes_key, corp_id)
    timestamp = "1774000001"
    nonce = "nonce-002"
    signature = compute_signature(token, timestamp, nonce, encrypted)
    body = f"<xml><Encrypt>{encrypted}</Encrypt></xml>"

    response = client.post(
        f"/api/wecom/events?msg_signature={signature}&timestamp={timestamp}&nonce={nonce}",
        data=body,
        content_type="application/xml",
    )
    assert response.status_code == 200

    with app.app_context():
        row = get_db().execute("SELECT status FROM group_chats WHERE chat_id = ?", ("chat-001",)).fetchone()
        assert row["status"] == "dismissed"


def test_external_contact_full_sync_and_identity_bind(client, app, monkeypatch):
    monkeypatch.setattr("requests.get", fake_wecom_get)
    monkeypatch.setattr("requests.post", fake_wecom_post)

    response = client.post("/internal/wecom/external-contact/full-sync")
    data = response.get_json()
    assert response.status_code == 200
    assert data["fetched_count"] == 3
    assert data["inserted_count"] == 3
    assert data["updated_count"] == 0
    assert data["identity_map_total"] == 3

    with app.app_context():
        resolved = resolve_external_contact_identity("ww-test", unionid="union-001")
        assert resolved["external_userid"] == "wm_ext_001"
        assert resolved["follow_user_userid"] == "sales_01"
        follow_users = get_db().execute(
            """
            SELECT user_id, relation_status, is_primary
            FROM wecom_external_contact_follow_users
            WHERE corp_id = ? AND external_userid = ?
            ORDER BY user_id
            """,
            ("ww-test", "wm_ext_001"),
        ).fetchall()
        assert len(follow_users) == 2
        assert follow_users[0]["user_id"] == "sales_01"
        assert follow_users[0]["relation_status"] == "active"
        assert bool(follow_users[0]["is_primary"]) is True
        rebound = bind_openid_to_external_contact("ww-test", "wm_ext_001", "openid-001", unionid="union-001")
        assert rebound["openid"] == "openid-001"
        assert rebound["unionid"] == "union-001"


def test_external_contact_callback_logs_and_processes_event(client, app, monkeypatch):
    monkeypatch.setattr("requests.get", fake_wecom_get)
    monkeypatch.setattr("requests.post", fake_wecom_post)

    token = "callback-token"
    aes_key = "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG"
    corp_id = "ww-test"
    plain_xml = (
        "<xml>"
        "<Event>change_external_contact</Event>"
        "<ChangeType>add_external_contact</ChangeType>"
        "<ExternalUserID>wm_ext_001</ExternalUserID>"
        "<UserID>sales_01</UserID>"
        "<CreateTime>1774000100</CreateTime>"
        "</xml>"
    )
    encrypted = encrypt_message(plain_xml, aes_key, corp_id)
    timestamp = "1774000100"
    nonce = "nonce-ec-001"
    signature = compute_signature(token, timestamp, nonce, encrypted)
    body = f"<xml><Encrypt>{encrypted}</Encrypt></xml>"

    response = client.post(
        f"/wecom/external-contact/callback?msg_signature={signature}&timestamp={timestamp}&nonce={nonce}",
        data=body,
        content_type="application/xml",
    )
    assert response.status_code == 200

    with app.app_context():
        event_log = get_db().execute(
            """
            SELECT change_type, external_userid, user_id, process_status, retry_count
            FROM wecom_external_contact_event_logs
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        assert event_log["change_type"] == "add_external_contact"
        assert event_log["external_userid"] == "wm_ext_001"
        assert event_log["user_id"] == "sales_01"
        assert event_log["process_status"] == "success"
        identity = resolve_external_contact_identity("ww-test", external_userid="wm_ext_001")
        assert identity["follow_user_userid"] == "sales_01"
        relation = get_db().execute(
            """
            SELECT user_id, relation_status
            FROM wecom_external_contact_follow_users
            WHERE corp_id = ? AND external_userid = ? AND user_id = ?
            """,
            ("ww-test", "wm_ext_001", "sales_01"),
        ).fetchone()
        assert relation["relation_status"] == "active"


def test_external_contact_callback_uses_official_welcome_msg_when_welcome_code_present(client, app, monkeypatch):
    monkeypatch.setattr("requests.get", fake_wecom_get)
    welcome_calls: list[dict[str, object]] = []

    def _fake_post(url, params=None, json=None, timeout=None, files=None):
        if url.endswith("/cgi-bin/externalcontact/send_welcome_msg"):
            welcome_calls.append({"url": url, "json": dict(json or {}), "timeout": timeout})
        return fake_wecom_post(url, params=params, json=json, timeout=timeout, files=files)

    monkeypatch.setattr("requests.post", _fake_post)

    with app.app_context():
        get_db().execute(
            """
            INSERT INTO automation_channel (
                channel_code, channel_name, scene_value, owner_staff_id, status, welcome_message, auto_accept_friend, created_at, updated_at
            )
            VALUES ('default_qrcode', '默认渠道二维码', 'scene-default', 'QianLan', 'active', '欢迎添加，稍后我来跟进你。', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
        get_db().commit()

    token = "callback-token"
    aes_key = "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG"
    corp_id = "ww-test"
    plain_xml = (
        "<xml>"
        "<Event>change_external_contact</Event>"
        "<ChangeType>add_external_contact</ChangeType>"
        "<ExternalUserID>wm_ext_001</ExternalUserID>"
        "<UserID>sales_01</UserID>"
        "<WelcomeCode>WELCOME-CODE-API-001</WelcomeCode>"
        "<State>scene-default</State>"
        "<CreateTime>1774000100</CreateTime>"
        "</xml>"
    )
    encrypted = encrypt_message(plain_xml, aes_key, corp_id)
    timestamp = "1774000100"
    nonce = "nonce-ec-002"
    signature = compute_signature(token, timestamp, nonce, encrypted)
    body = f"<xml><Encrypt>{encrypted}</Encrypt></xml>"

    response = client.post(
        f"/wecom/external-contact/callback?msg_signature={signature}&timestamp={timestamp}&nonce={nonce}",
        data=body,
        content_type="application/xml",
    )
    assert response.status_code == 200
    expected_url = f"{app.config['WECOM_API_BASE'].rstrip('/')}/cgi-bin/externalcontact/send_welcome_msg"
    assert welcome_calls == [
        {
            "url": expected_url,
            "json": {
                "welcome_code": "WELCOME-CODE-API-001",
                "text": {"content": "欢迎添加，稍后我来跟进你。"},
            },
            "timeout": 15,
        }
    ]

    with app.app_context():
        events = get_db().execute(
            "SELECT action, operator_id, remark FROM automation_event ORDER BY id ASC"
        ).fetchall()
        assert [dict(item) for item in events[-2:]] == [
            {
                "action": "qrcode_enter",
                "operator_id": "sales_01",
                "remark": "",
            },
            {
                "action": "qrcode_welcome_sent",
                "operator_id": "sales_01",
                "remark": "official_send_welcome_msg",
            },
        ]


def test_extract_text_record():
    encrypted_record = {
        "seq": 123,
        "msgid": "sdk-msg-001",
        "publickey_ver": 1,
        "encrypt_random_key": "encrypted-key",
        "encrypt_chat_msg": "encrypted-msg",
    }
    decrypted_payload = {
        "msgid": "sdk-msg-001",
        "from": "wm_ext_001",
        "tolist": ["sales_01"],
        "msgtype": "text",
        "text": {"content": "你好，我想看案例"},
        "msgtime": 1761950405,
    }
    row = extract_text_record(123, encrypted_record, decrypted_payload)
    assert row is not None
    assert row["external_userid"] == "wm_ext_001"
    assert row["owner_userid"] == "sales_01"
    assert row["content"] == "你好，我想看案例"
    assert row["seq"] == 123
    assert row["chat_type"] == "private"


def test_normalize_timestamp():
    assert normalize_timestamp(1761950405000).startswith("2025-")


def _build_questionnaire_payload(**overrides) -> dict:
    payload = {
        "name": "线索打标问卷",
        "title": "来访测评",
        "description": "请根据你的实际情况填写。",
        "redirect_url": "https://example.com/next",
        "external_push_enabled": False,
        "external_push_url": "",
        "external_push_day": "",
        "external_push_frequency": "",
        "external_push_remark": "",
        "external_push_custom_params": [],
        "questions": [
            {
                "type": "single_choice",
                "title": "你的预算",
                "required": True,
                "sort_order": 1,
                "options": [
                    {"option_text": "10万以内", "score": 1, "tag_codes": ["budget_low"], "sort_order": 1},
                    {"option_text": "10-30万", "score": 3, "tag_codes": ["budget_mid"], "sort_order": 2},
                ],
            },
            {
                "type": "multi_choice",
                "title": "你的关注点",
                "required": False,
                "sort_order": 2,
                "options": [
                    {"option_text": "效果", "score": 2, "tag_codes": ["focus_result"], "sort_order": 1},
                    {"option_text": "服务", "score": 1, "tag_codes": ["focus_service"], "sort_order": 2},
                ],
            },
            {
                "type": "textarea",
                "title": "补充说明",
                "required": False,
                "sort_order": 3,
            },
        ],
        "score_rules": [
            {"min_score": 4, "max_score": 99, "tag_codes": ["score_high"], "sort_order": 1},
        ],
    }
    payload.update(overrides)
    return payload


def _build_questionnaire_payload_with_mobile(**overrides) -> dict:
    payload = _build_questionnaire_payload(**overrides)
    payload["questions"].append(
        {
            "type": "mobile",
            "title": "手机号",
            "required": True,
            "sort_order": 4,
        }
    )
    return payload


def _build_assessment_questionnaire_payload(**overrides) -> dict:
    payload = _build_questionnaire_payload(**overrides)
    payload["assessment_enabled"] = True
    payload["assessment_config"] = {
        "strength_count": 1,
        "weakness_count": 1,
        "overall_levels": [
            {"min_score": 0, "max_score": 4, "title": "待破局", "tag_codes": ["assessment_low"]},
            {
                "min_score": 5,
                "max_score": 99,
                "title": "进阶型",
                "summary": "已经有基础动作，可以继续补短板。",
                "tag_codes": ["assessment_high"],
            },
        ],
        "dimensions": [
            {
                "key": "deal",
                "name": "成交能力",
                "type_priority": ["push", "passive"],
                "types": [
                    {"key": "passive", "name": "被动型"},
                    {"key": "push", "name": "推销型", "summary": "成交动作主动但需要更稳。", "tag_codes": ["assessment_deal_push"]},
                ],
                "levels": [
                    {"min_score": 3, "max_score": 5, "title": "成交可用", "tag_codes": ["assessment_deal_ok"]},
                ],
            },
            {
                "key": "maintain",
                "name": "用户维护",
                "type_priority": ["nurture", "warm"],
                "types": [
                    {"key": "warm", "name": "暖男女型"},
                    {"key": "nurture", "name": "养鱼型", "tag_codes": ["assessment_maintain_nurture"]},
                ],
            },
        ],
        "recommendations": [
            {
                "dimension_key": "maintain",
                "max_score": 3,
                "title": "先补维护节奏",
                "summary": "把用户维护动作固定下来。",
                "tag_codes": ["assessment_reco_maintain"],
            }
        ],
    }
    payload["questions"][0]["assessment_dimension_key"] = "deal"
    payload["questions"][0]["options"][0]["assessment_type_key"] = "passive"
    payload["questions"][0]["options"][1]["assessment_type_key"] = "push"
    payload["questions"][1]["assessment_dimension_key"] = "maintain"
    payload["questions"][1]["options"][0]["assessment_type_key"] = "warm"
    payload["questions"][1]["options"][1]["assessment_type_key"] = "nurture"
    return payload


WECHAT_BROWSER_HEADERS = {"User-Agent": "Mozilla/5.0 MicroMessenger"}


def test_questionnaire_admin_routes_and_public_h5(client):
    create_response = client.post("/api/admin/questionnaires", json=_build_questionnaire_payload())
    assert create_response.status_code == 200
    questionnaire = create_response.get_json()["questionnaire"]
    questionnaire_id = questionnaire["id"]
    slug = questionnaire["slug"]

    list_response = client.get("/api/admin/questionnaires")
    list_payload = list_response.get_json()
    assert list_response.status_code == 200
    assert list_payload["questionnaires"][0]["public_path"] == f"/s/{slug}"
    assert list_payload["questionnaires"][0]["public_url"].endswith(f"/s/{slug}")

    detail_response = client.get(f"/api/admin/questionnaires/{questionnaire_id}")
    detail_payload = detail_response.get_json()["questionnaire"]
    assert detail_response.status_code == 200
    assert len(detail_payload["questions"]) == 3
    assert detail_payload["questions"][0]["options"][0]["tag_codes"] == ["budget_low"]

    blocked_public_response = client.get(f"/api/h5/questionnaires/{slug}")
    assert blocked_public_response.status_code == 403
    assert blocked_public_response.get_json() == {"ok": False, "error": "please_open_in_wechat"}

    public_response = client.get(f"/api/h5/questionnaires/{slug}", headers=WECHAT_BROWSER_HEADERS)
    public_payload = public_response.get_json()["questionnaire"]
    assert public_response.status_code == 200
    assert public_payload["title"] == "来访测评"
    assert "score_rules" not in public_payload

    h5_response = client.get(f"/s/{slug}")
    assert h5_response.status_code == 200
    assert "请在微信客户端打开" in h5_response.get_data(as_text=True)

    wechat_h5_response = client.get(f"/s/{slug}", headers=WECHAT_BROWSER_HEADERS)
    assert wechat_h5_response.status_code == 200
    assert "来访测评" in wechat_h5_response.get_data(as_text=True)

    disable_response = client.post(f"/api/admin/questionnaires/{questionnaire_id}/disable", json={"is_disabled": True})
    assert disable_response.status_code == 200
    assert disable_response.get_json()["questionnaire"]["is_disabled"] is True

    disabled_public = client.get(f"/api/h5/questionnaires/{slug}", headers=WECHAT_BROWSER_HEADERS)
    assert disabled_public.status_code == 404

    enable_response = client.post(f"/api/admin/questionnaires/{questionnaire_id}/disable", json={"is_disabled": False})
    assert enable_response.status_code == 200
    assert enable_response.get_json()["questionnaire"]["is_disabled"] is False


def test_questionnaire_open_questions_support_placeholder_text(client):
    payload = _build_questionnaire_payload_with_mobile()
    payload["questions"][2]["placeholder_text"] = "请补充你的实际需求，便于老师了解"
    payload["questions"][3]["placeholder_text"] = "请输入手机号，方便后续联系"

    create_response = client.post("/api/admin/questionnaires", json=payload)
    assert create_response.status_code == 200
    questionnaire = create_response.get_json()["questionnaire"]
    slug = questionnaire["slug"]

    questions_by_type = {item["type"]: item for item in questionnaire["questions"]}
    assert questions_by_type["textarea"]["placeholder_text"] == "请补充你的实际需求，便于老师了解"
    assert questions_by_type["mobile"]["placeholder_text"] == "请输入手机号，方便后续联系"

    public_response = client.get(f"/api/h5/questionnaires/{slug}", headers=WECHAT_BROWSER_HEADERS)
    assert public_response.status_code == 200
    public_questions_by_type = {item["type"]: item for item in public_response.get_json()["questionnaire"]["questions"]}
    assert public_questions_by_type["textarea"]["placeholder_text"] == "请补充你的实际需求，便于老师了解"
    assert public_questions_by_type["mobile"]["placeholder_text"] == "请输入手机号，方便后续联系"


def test_admin_delete_questionnaire_requires_disabled_state(client):
    create_response = client.post("/api/admin/questionnaires", json=_build_questionnaire_payload())
    questionnaire_id = create_response.get_json()["questionnaire"]["id"]

    enabled_delete_response = client.delete(f"/api/admin/questionnaires/{questionnaire_id}")
    assert enabled_delete_response.status_code == 400
    assert enabled_delete_response.get_json()["error"] == "请先停用问卷后再删除"

    disable_response = client.post(
        f"/api/admin/questionnaires/{questionnaire_id}/disable",
        json={"is_disabled": True},
    )
    assert disable_response.status_code == 200
    assert disable_response.get_json()["questionnaire"]["is_disabled"] is True

    delete_response = client.delete(f"/api/admin/questionnaires/{questionnaire_id}")
    assert delete_response.status_code == 200
    assert delete_response.get_json()["deleted"] is True

    detail_response = client.get(f"/api/admin/questionnaires/{questionnaire_id}")
    assert detail_response.status_code == 404


def test_non_wechat_browser_is_blocked_for_questionnaire_page(client):
    create_response = client.post("/api/admin/questionnaires", json=_build_questionnaire_payload())
    slug = create_response.get_json()["questionnaire"]["slug"]

    response = client.get(f"/s/{slug}")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "请在微信客户端打开" in body
    assert "请回到微信中点击原链接后访问问卷" in body


def test_non_wechat_browser_is_blocked_for_public_questionnaire_api(client):
    create_response = client.post("/api/admin/questionnaires", json=_build_questionnaire_payload())
    slug = create_response.get_json()["questionnaire"]["slug"]

    response = client.get(f"/api/h5/questionnaires/{slug}")

    assert response.status_code == 403
    assert response.get_json() == {"ok": False, "error": "please_open_in_wechat"}


def test_non_wechat_browser_is_blocked_for_questionnaire_submit(client):
    create_response = client.post("/api/admin/questionnaires", json=_build_questionnaire_payload())
    questionnaire = create_response.get_json()["questionnaire"]
    detail = client.get(f"/api/admin/questionnaires/{questionnaire['id']}").get_json()["questionnaire"]
    q1 = detail["questions"][0]

    response = client.post(
        f"/api/h5/questionnaires/{questionnaire['slug']}/submit",
        json={"answers": {str(q1["id"]): q1["options"][0]["id"]}},
    )

    assert response.status_code == 403
    assert response.get_json() == {"ok": False, "error": "please_open_in_wechat"}


def test_wechat_browser_can_continue_through_questionnaire_gate(client):
    create_response = client.post("/api/admin/questionnaires", json=_build_questionnaire_payload())
    slug = create_response.get_json()["questionnaire"]["slug"]

    response = client.get(f"/s/{slug}", headers=WECHAT_BROWSER_HEADERS)

    assert response.status_code == 200
    assert "请在微信客户端打开" not in response.get_data(as_text=True)


def test_questionnaire_h5_page_renders_title_and_description_only_once(client):
    create_response = client.post("/api/admin/questionnaires", json=_build_questionnaire_payload())
    slug = create_response.get_json()["questionnaire"]["slug"]
    with client.session_transaction() as session:
        session["questionnaire_h5_identity"] = {
            "openid": "openid-test-h5-render",
            "respondent_key": "openid-test-h5-render",
            "slug": slug,
        }

    response = client.get(f"/s/{slug}", headers=WECHAT_BROWSER_HEADERS)
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert '<title>来访测评</title>' in body
    assert '<h1 style="font-size:32px;">来访测评</h1>' in body
    assert 'questionnaire-head' not in body
    assert 'id="title"' not in body
    assert 'id="desc"' not in body
    assert 'id="questionnaire-form"' in body
    assert '你的预算' in body
    assert 'button type="submit" class="submit-btn">提交</button>' in body
    assert f'/api/h5/questionnaires/{slug}' in body
    assert f'/api/h5/questionnaires/{slug}/submit' in body


def test_questionnaire_h5_page_supports_html_form_fallback(client):
    create_response = client.post("/api/admin/questionnaires", json=_build_questionnaire_payload())
    questionnaire = create_response.get_json()["questionnaire"]
    slug = questionnaire["slug"]
    detail = client.get(f"/api/admin/questionnaires/{questionnaire['id']}").get_json()["questionnaire"]
    q1 = detail["questions"][0]

    with client.session_transaction() as session:
        session["questionnaire_h5_identity"] = {
            "openid": "openid-test-h5-fallback",
            "respondent_key": "openid-test-h5-fallback",
            "slug": slug,
        }

    response = client.get(
        f"/s/{slug}?external_userid=wm_ext_html_001&campaign_id=cmp-h5-001",
        headers=WECHAT_BROWSER_HEADERS,
    )
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert f'<form id="questionnaire-form" method="post" action="/api/h5/questionnaires/{slug}/submit">' in body
    assert 'type="hidden" name="external_userid" value="wm_ext_html_001"' in body
    assert 'type="hidden" name="campaign_id" value="cmp-h5-001"' in body
    assert f'name="q_{q1["id"]}"' in body


def test_questionnaire_client_diagnostics_logs_payload(client, caplog):
    create_response = client.post("/api/admin/questionnaires", json=_build_questionnaire_payload())
    slug = create_response.get_json()["questionnaire"]["slug"]

    with client.session_transaction() as session:
        session["questionnaire_h5_identity"] = {
            "openid": "openid-diagnostics-001",
            "unionid": "union-diagnostics-001",
            "respondent_key": "union-diagnostics-001",
            "slug": slug,
        }

    response = client.post(
        f"/api/h5/questionnaires/{slug}/client-diagnostics",
        json={
            "stage": "load_failed",
            "message": "render exploded",
            "extra": {"questionCount": 3, "apiUrl": f"/api/h5/questionnaires/{slug}"},
        },
        headers=WECHAT_BROWSER_HEADERS,
    )

    assert response.status_code == 200
    assert response.get_json() == {"ok": True}
    assert "questionnaire client diagnostics" in caplog.text
    assert "load_failed" in caplog.text
    assert "render exploded" in caplog.text


def test_questionnaire_html_form_submit_fallback_redirects(client):
    create_response = client.post("/api/admin/questionnaires", json=_build_questionnaire_payload())
    questionnaire = create_response.get_json()["questionnaire"]
    detail = client.get(f"/api/admin/questionnaires/{questionnaire['id']}").get_json()["questionnaire"]
    q1, q2, q3 = detail["questions"]

    with client.session_transaction() as session:
        session["questionnaire_h5_identity"] = {
            "openid": "openid-html-submit-001",
            "unionid": "union-html-submit-001",
            "respondent_key": "union-html-submit-001",
            "slug": questionnaire["slug"],
        }

    response = client.post(
        f"/api/h5/questionnaires/{questionnaire['slug']}/submit",
        data={
            f"q_{q1['id']}": str(q1["options"][0]["id"]),
            f"q_{q2['id']}": [str(q2["options"][0]["id"]), str(q2["options"][1]["id"])],
            f"q_{q3['id']}": "鸿蒙微信走表单兜底提交",
            "external_userid": "wm_html_submit_001",
            "campaign_id": "cmp-html-submit-001",
        },
        headers=WECHAT_BROWSER_HEADERS,
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"] == questionnaire["redirect_url"]

    public_response = client.get(
        f"/api/h5/questionnaires/{questionnaire['slug']}",
        headers=WECHAT_BROWSER_HEADERS,
    )
    assert public_response.status_code == 409
    assert public_response.get_json()["error"] == "already_submitted"


def test_questionnaire_html_form_submit_validation_error_preserves_values(client):
    create_response = client.post("/api/admin/questionnaires", json=_build_questionnaire_payload())
    questionnaire = create_response.get_json()["questionnaire"]
    detail = client.get(f"/api/admin/questionnaires/{questionnaire['id']}").get_json()["questionnaire"]
    q1, q2, q3 = detail["questions"]

    with client.session_transaction() as session:
        session["questionnaire_h5_identity"] = {
            "openid": "openid-html-invalid-001",
            "respondent_key": "openid-html-invalid-001",
            "slug": questionnaire["slug"],
        }

    response = client.post(
        f"/api/h5/questionnaires/{questionnaire['slug']}/submit",
        data={
            f"q_{q2['id']}": str(q2["options"][1]["id"]),
            f"q_{q3['id']}": "这段说明应该被保留",
            "external_userid": "wm_html_invalid_001",
        },
        headers=WECHAT_BROWSER_HEADERS,
    )
    body = response.get_data(as_text=True)

    assert response.status_code == 400
    assert "question &#39;你的预算&#39; is required" in body
    assert '这段说明应该被保留' in body
    assert f'name="q_{q2["id"]}"' in body
    assert f'value="{q2["options"][1]["id"]}"' in body
    assert "checked" in body
    assert 'type="hidden" name="external_userid" value="wm_html_invalid_001"' in body
    assert f'name="q_{q1["id"]}"' in body


def test_questionnaire_submit_matches_identity_and_marks_tags(client, app, monkeypatch):
    captured_mark_payloads = []

    def record_wecom_post(url, params=None, json=None, timeout=None):
        if url.endswith("/cgi-bin/externalcontact/mark_tag"):
            captured_mark_payloads.append(json or {})
        return fake_wecom_post(url, params=params, json=json, timeout=timeout)

    monkeypatch.setattr("requests.get", fake_wecom_get)
    monkeypatch.setattr("requests.post", record_wecom_post)

    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO wecom_external_contact_identity_map (
                corp_id, external_userid, unionid, openid, follow_user_userid, name, status, raw_profile
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("ww-test", "wm_ext_001", "union-001", "", "sales_01", "周青", "active", "{}"),
        )
        db.commit()

    create_response = client.post("/api/admin/questionnaires", json=_build_questionnaire_payload())
    questionnaire = create_response.get_json()["questionnaire"]
    slug = questionnaire["slug"]
    detail = client.get(f"/api/admin/questionnaires/{questionnaire['id']}").get_json()["questionnaire"]
    q1, q2, q3 = detail["questions"]

    submit_payload = {
        "unionid": "union-001",
        "openid": "openid-001",
        "source_channel": "朋友圈",
        "campaign_id": "cmp-001",
        "staff_id": "staff-007",
        "answers": {
            str(q1["id"]): q1["options"][1]["id"],
            str(q2["id"]): [q2["options"][0]["id"], q2["options"][1]["id"]],
            str(q3["id"]): "客户希望尽快沟通报价。",
        },
    }
    submit_response = client.post(
        f"/api/h5/questionnaires/{slug}/submit",
        json=submit_payload,
        headers=WECHAT_BROWSER_HEADERS,
    )
    submit_result = submit_response.get_json()
    assert submit_response.status_code == 200
    assert submit_result["success"] is True
    assert submit_result["redirect_url"] == "https://example.com/next"

    with app.app_context():
        db = get_db()
        submission = db.execute(
            """
            SELECT identity_map_id, respondent_key, openid, unionid, external_userid, follow_user_userid,
                   matched_by, source_channel, campaign_id, staff_id, total_score, final_tags
            FROM questionnaire_submissions
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        assert submission["identity_map_id"] is not None
        assert submission["respondent_key"] == "union-001"
        assert submission["openid"] == "openid-001"
        assert submission["unionid"] == "union-001"
        assert submission["external_userid"] == "wm_ext_001"
        assert submission["follow_user_userid"] == "sales_01"
        assert submission["matched_by"] == "unionid"
        assert submission["source_channel"] == "朋友圈"
        assert submission["campaign_id"] == "cmp-001"
        assert submission["staff_id"] == "staff-007"
        assert float(submission["total_score"]) == 6.0
        assert set(submission["final_tags"] if isinstance(submission["final_tags"], list) else json.loads(submission["final_tags"])) == {
            "budget_mid",
            "focus_result",
            "focus_service",
            "score_high",
        }

        identity = resolve_external_contact_identity("ww-test", external_userid="wm_ext_001")
        assert identity["openid"] == "openid-001"

        answers = db.execute(
            """
            SELECT question_type, question_title_snapshot, selected_option_texts_snapshot, text_value, score_contribution
            FROM questionnaire_submission_answers
            ORDER BY id ASC
            """
        ).fetchall()
        assert len(answers) == 3
        assert (answers[0]["selected_option_texts_snapshot"] if isinstance(answers[0]["selected_option_texts_snapshot"], (dict, list)) else json.loads(answers[0]["selected_option_texts_snapshot"])) == ["10-30万"]
        assert answers[1]["question_type"] == "multi_choice"
        assert (answers[1]["selected_option_texts_snapshot"] if isinstance(answers[1]["selected_option_texts_snapshot"], (dict, list)) else json.loads(answers[1]["selected_option_texts_snapshot"])) == ["效果", "服务"]
        assert answers[2]["text_value"] == "客户希望尽快沟通报价。"

        tag_rows = db.execute(
            """
            SELECT tag_id
            FROM contact_tags
            WHERE external_userid = ? AND userid = ?
            ORDER BY tag_id
            """,
            ("wm_ext_001", "sales_01"),
        ).fetchall()
        assert [row["tag_id"] for row in tag_rows] == [
            "budget_mid",
            "focus_result",
            "focus_service",
            "score_high",
        ]

    assert len(captured_mark_payloads) == 1
    assert captured_mark_payloads[0]["userid"] == "sales_01"
    assert captured_mark_payloads[0]["external_userid"] == "wm_ext_001"
    assert set(captured_mark_payloads[0]["add_tag"]) == {
        "budget_mid",
        "focus_result",
        "focus_service",
        "score_high",
    }


def test_assessment_questionnaire_saves_snapshot_and_renders_result_page(client, app):
    create_response = client.post("/api/admin/questionnaires", json=_build_assessment_questionnaire_payload())
    assert create_response.status_code == 200
    questionnaire = create_response.get_json()["questionnaire"]
    assert questionnaire["assessment_enabled"] is True
    assert questionnaire["questions"][0]["assessment_dimension_key"] == "deal"
    assert questionnaire["questions"][0]["options"][1]["assessment_type_key"] == "push"

    public_response = client.get(
        f"/api/h5/questionnaires/{questionnaire['slug']}",
        headers=WECHAT_BROWSER_HEADERS,
    )
    assert public_response.status_code == 200
    public_payload = public_response.get_json()["questionnaire"]
    assert "assessment_config" not in public_payload

    detail = client.get(f"/api/admin/questionnaires/{questionnaire['id']}").get_json()["questionnaire"]
    q1, q2, q3 = detail["questions"]
    submit_response = client.post(
        f"/api/h5/questionnaires/{questionnaire['slug']}/submit",
        json={
            "respondent_key": "assessment-user-001",
            "answers": {
                str(q1["id"]): q1["options"][1]["id"],
                str(q2["id"]): [q2["options"][0]["id"], q2["options"][1]["id"]],
                str(q3["id"]): "希望先看测评结果。",
            },
        },
        headers=WECHAT_BROWSER_HEADERS,
    )

    assert submit_response.status_code == 200
    submit_result = submit_response.get_json()
    assert submit_result["success"] is True
    assert submit_result["result_url"].startswith(f"/s/{questionnaire['slug']}/result/")
    assert submit_result["redirect_url"] == submit_result["result_url"]

    with app.app_context():
        submission = get_db().execute(
            """
            SELECT total_score, final_tags, assessment_result_snapshot, result_token, redirect_url_snapshot
            FROM questionnaire_submissions
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        assert float(submission["total_score"]) == 6.0
        assert submission["result_token"]
        assert submission["redirect_url_snapshot"] == submit_result["result_url"]
        final_tags = submission["final_tags"] if isinstance(submission["final_tags"], list) else json.loads(submission["final_tags"])
        assert {
            "budget_mid",
            "focus_result",
            "focus_service",
            "score_high",
            "assessment_high",
            "assessment_deal_push",
            "assessment_deal_ok",
            "assessment_maintain_nurture",
            "assessment_reco_maintain",
        }.issubset(set(final_tags))
        snapshot = (
            submission["assessment_result_snapshot"]
            if isinstance(submission["assessment_result_snapshot"], dict)
            else json.loads(submission["assessment_result_snapshot"])
        )
        assert snapshot["enabled"] is True
        assert snapshot["overall_level"]["title"] == "进阶型"
        assert [item["key"] for item in snapshot["dimensions"]] == ["deal", "maintain"]
        assert snapshot["dimensions"][0]["dominant_type"]["name"] == "推销型"
        assert snapshot["dimensions"][1]["dominant_type"]["name"] == "养鱼型"

    result_page = client.get(submit_result["result_url"])
    body = result_page.get_data(as_text=True)
    assert result_page.status_code == 200
    assert "进阶型" in body
    assert "成交能力" in body
    assert "用户维护" in body
    assert "养鱼型" in body


def test_questionnaire_submit_prefers_session_identity(client, app):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO wecom_external_contact_identity_map (
                corp_id, external_userid, unionid, openid, follow_user_userid, name, status, raw_profile
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("ww-test", "wm_ext_session_001", "union-session-001", "openid-session-001", "sales_01", "会话客户", "active", "{}"),
        )
        db.commit()

    create_response = client.post("/api/admin/questionnaires", json=_build_questionnaire_payload())
    questionnaire = create_response.get_json()["questionnaire"]
    detail = client.get(f"/api/admin/questionnaires/{questionnaire['id']}").get_json()["questionnaire"]
    q1 = detail["questions"][0]

    with client.session_transaction() as sess:
        sess["questionnaire_h5_identity"] = {
            "openid": "openid-session-001",
            "unionid": "union-session-001",
            "respondent_key": "respondent-session-001",
        }

    response = client.post(
        f"/api/h5/questionnaires/{questionnaire['slug']}/submit",
        json={
            "openid": "openid-payload-should-not-win",
            "unionid": "union-payload-should-not-win",
            "answers": {str(q1["id"]): q1["options"][0]["id"]},
        },
        headers=WECHAT_BROWSER_HEADERS,
    )
    assert response.status_code == 200

    with app.app_context():
        submission = get_db().execute(
            """
            SELECT respondent_key, openid, unionid, external_userid, matched_by
            FROM questionnaire_submissions
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        assert submission["respondent_key"] == "respondent-session-001"
        assert submission["openid"] == "openid-session-001"
        assert submission["unionid"] == "union-session-001"
        assert submission["external_userid"] == "wm_ext_session_001"
        assert submission["matched_by"] == "unionid"


def test_wechat_oauth_routes_and_wechat_h5_behavior(client, app, monkeypatch):
    monkeypatch.setattr("requests.get", fake_wecom_get)
    app.config.update(
        SECRET_KEY="test-secret-key-stable",
        WECHAT_MP_APP_ID="wx-test-appid",
        WECHAT_MP_APP_SECRET="wx-test-secret",
        WECHAT_MP_OAUTH_SCOPE="snsapi_base",
    )

    create_response = client.post("/api/admin/questionnaires", json=_build_questionnaire_payload())
    questionnaire = create_response.get_json()["questionnaire"]
    slug = questionnaire["slug"]

    wechat_headers = {"User-Agent": "Mozilla/5.0 MicroMessenger"}
    page_response = client.get(
        f"/s/{slug}?source_channel=朋友圈&campaign_id=cmp-001&staff_id=staff-007",
        headers=wechat_headers,
    )
    assert page_response.status_code == 200
    assert "点击下方授权，登记表单" in page_response.get_data(as_text=True)
    assert "立即授权并填写" in page_response.get_data(as_text=True)

    start_response = client.get(
        f"/api/h5/wechat/oauth/start?slug={slug}&source_channel=朋友圈&campaign_id=cmp-001&staff_id=staff-007"
    )
    assert start_response.status_code == 302
    assert start_response.headers["Location"].startswith("https://open.weixin.qq.com/connect/oauth2/authorize?")

    from urllib.parse import parse_qs, urlparse

    start_query = parse_qs(urlparse(start_response.headers["Location"]).query)
    callback_response = client.get(
        f"/api/h5/wechat/oauth/callback?code=oauth-code-001&state={start_query['state'][0]}"
    )
    assert callback_response.status_code == 302
    assert callback_response.headers["Location"] == f"/s/{slug}?source_channel=%E6%9C%8B%E5%8F%8B%E5%9C%88&campaign_id=cmp-001&staff_id=staff-007"

    with client.session_transaction() as sess:
        assert sess["questionnaire_h5_identity"]["openid"] == "openid-oauth-001"
        assert sess["questionnaire_h5_identity"]["unionid"] == "union-oauth-001"
        assert sess["questionnaire_h5_identity"]["respondent_key"] == "union-oauth-001"
        assert sess["questionnaire_h5_identity"]["slug"] == slug
        assert sess["questionnaire_h5_identity"]["oauth_at"]

    final_page = client.get(f"/s/{slug}", headers=wechat_headers)
    assert final_page.status_code == 200
    assert "当前为非微信环境，仅供测试。" not in final_page.get_data(as_text=True)
    assert "点击下方授权，登记表单" not in final_page.get_data(as_text=True)

    debug_response = client.get("/api/debug/questionnaire/session")
    assert debug_response.status_code == 200
    assert debug_response.get_json()["questionnaire_h5_identity"]["openid"] == "openid-oauth-001"


def test_wechat_oauth_userinfo_scope_fetches_unionid(client, app, monkeypatch):
    monkeypatch.setattr("requests.get", fake_wecom_get)
    app.config.update(
        SECRET_KEY="test-secret-key-stable",
        WECHAT_MP_APP_ID="wx-test-appid",
        WECHAT_MP_APP_SECRET="wx-test-secret",
        WECHAT_MP_OAUTH_SCOPE="snsapi_userinfo",
    )

    create_response = client.post("/api/admin/questionnaires", json=_build_questionnaire_payload())
    slug = create_response.get_json()["questionnaire"]["slug"]

    start_response = client.get(f"/api/h5/wechat/oauth/start?slug={slug}")
    assert start_response.status_code == 302

    from urllib.parse import parse_qs, urlparse

    start_query = parse_qs(urlparse(start_response.headers["Location"]).query)
    callback_response = client.get(
        f"/api/h5/wechat/oauth/callback?code=oauth-code-userinfo-001&state={start_query['state'][0]}"
    )
    assert callback_response.status_code == 302

    with client.session_transaction() as sess:
        assert sess["questionnaire_h5_identity"]["openid"] == "openid-userinfo-001"
        assert sess["questionnaire_h5_identity"]["unionid"] == "union-userinfo-001"
        assert sess["questionnaire_h5_identity"]["respondent_key"] == "union-userinfo-001"


def test_wechat_oauth_routes_return_501_when_unconfigured(client):
    create_response = client.post("/api/admin/questionnaires", json=_build_questionnaire_payload())
    slug = create_response.get_json()["questionnaire"]["slug"]

    start_response = client.get("/api/h5/wechat/oauth/start?slug=test-slug")
    assert start_response.status_code == 501
    assert start_response.get_json()["error"] == "wechat_oauth_not_configured"

    callback_response = client.get("/api/h5/wechat/oauth/callback?code=test&state=test")
    assert callback_response.status_code == 501
    assert callback_response.get_json()["error"] == "wechat_oauth_not_configured"

    page_response = client.get(f"/s/{slug}", headers={"User-Agent": "Mozilla/5.0 MicroMessenger"})
    assert page_response.status_code == 200
    assert "当前为微信环境，但未配置公众号 OAuth，当前页面仅供测试。" in page_response.get_data(as_text=True)


def test_required_multi_choice_must_select_one(client):
    payload = _build_questionnaire_payload()
    payload["questions"][1]["required"] = True
    create_response = client.post("/api/admin/questionnaires", json=payload)
    questionnaire = create_response.get_json()["questionnaire"]
    detail = client.get(f"/api/admin/questionnaires/{questionnaire['id']}").get_json()["questionnaire"]
    q1, _, q3 = detail["questions"]

    response = client.post(
        f"/api/h5/questionnaires/{questionnaire['slug']}/submit",
        json={
            "answers": {
                str(q1["id"]): q1["options"][0]["id"],
                str(q3["id"]): "没有选择多选题",
            }
        },
        headers=WECHAT_BROWSER_HEADERS,
    )
    assert response.status_code == 400
    assert "question '你的关注点' is required" in response.get_json()["error"]


def test_option_id_must_belong_to_question(client):
    create_response = client.post("/api/admin/questionnaires", json=_build_questionnaire_payload())
    questionnaire = create_response.get_json()["questionnaire"]
    detail = client.get(f"/api/admin/questionnaires/{questionnaire['id']}").get_json()["questionnaire"]
    q1, q2, _ = detail["questions"]

    response = client.post(
        f"/api/h5/questionnaires/{questionnaire['slug']}/submit",
        json={"answers": {str(q1["id"]): q2["options"][0]["id"]}},
        headers=WECHAT_BROWSER_HEADERS,
    )
    assert response.status_code == 400
    assert "question '你的预算' has an invalid option" in response.get_json()["error"]


def test_scrm_apply_failure_does_not_break_submit(client, app, monkeypatch):
    monkeypatch.setattr("requests.get", fake_wecom_get)

    def failing_wecom_post(url, params=None, json=None, timeout=None):
        if url.endswith("/cgi-bin/externalcontact/mark_tag"):
            raise RuntimeError("mark tag boom")
        return fake_wecom_post(url, params=params, json=json, timeout=timeout)

    monkeypatch.setattr("requests.post", failing_wecom_post)

    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO wecom_external_contact_identity_map (
                corp_id, external_userid, unionid, openid, follow_user_userid, name, status, raw_profile
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("ww-test", "wm_ext_fail_001", "union-fail-001", "openid-fail-001", "sales_01", "失败客户", "active", "{}"),
        )
        db.commit()

    create_response = client.post("/api/admin/questionnaires", json=_build_questionnaire_payload())
    questionnaire = create_response.get_json()["questionnaire"]
    detail = client.get(f"/api/admin/questionnaires/{questionnaire['id']}").get_json()["questionnaire"]
    q1 = detail["questions"][0]

    submit_response = client.post(
        f"/api/h5/questionnaires/{questionnaire['slug']}/submit",
        json={
            "openid": "openid-fail-001",
            "answers": {str(q1["id"]): q1["options"][1]["id"]},
        },
        headers=WECHAT_BROWSER_HEADERS,
    )
    assert submit_response.status_code == 200
    assert submit_response.get_json()["success"] is True

    with app.app_context():
        log_row = get_db().execute(
            """
            SELECT status, error_message
            FROM questionnaire_scrm_apply_logs
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        assert log_row["status"] == "failed"
        assert "mark tag boom" in log_row["error_message"]


def test_questionnaire_export_keeps_historical_snapshots(client):
    create_response = client.post(
        "/api/admin/questionnaires",
        json={
            "name": "导出快照问卷",
            "title": "导出快照问卷",
            "questions": [
                {
                    "type": "single_choice",
                    "title": "当前阶段",
                    "required": True,
                    "options": [
                        {"option_text": "旧选项", "score": 2, "tag_codes": ["tag_old"], "sort_order": 1},
                    ],
                }
            ],
            "score_rules": [{"min_score": 2, "max_score": 10, "tag_codes": ["score_tag"], "sort_order": 1}],
        },
    )
    questionnaire = create_response.get_json()["questionnaire"]
    questionnaire_id = questionnaire["id"]
    detail = client.get(f"/api/admin/questionnaires/{questionnaire_id}").get_json()["questionnaire"]
    question = detail["questions"][0]
    option = question["options"][0]

    submit_response = client.post(
        f"/api/h5/questionnaires/{questionnaire['slug']}/submit",
        json={"answers": {str(question["id"]): option["id"]}},
        headers=WECHAT_BROWSER_HEADERS,
    )
    assert submit_response.status_code == 200

    question["title"] = "新的题目标题"
    option["option_text"] = "新选项"
    update_payload = {
        "slug": detail["slug"],
        "name": detail["name"],
        "title": "导出快照问卷（已更新）",
        "description": detail["description"],
        "redirect_url": detail["redirect_url"],
        "is_disabled": detail["is_disabled"],
        "questions": [question],
        "score_rules": detail["score_rules"],
    }
    update_response = client.put(f"/api/admin/questionnaires/{questionnaire_id}", json=update_payload)
    assert update_response.status_code == 200

    export_response = client.get(f"/api/admin/questionnaires/{questionnaire_id}/export")
    export_text = export_response.get_data(as_text=True)
    assert export_response.status_code == 200
    assert export_response.headers["Content-Disposition"].endswith('.xls"')
    assert "旧选项" in export_text
    assert "新选项" not in export_text


def test_questionnaire_export_includes_mobile_question_text_value(client):
    create_response = client.post("/api/admin/questionnaires", json=_build_questionnaire_payload_with_mobile())
    questionnaire = create_response.get_json()["questionnaire"]
    detail = client.get(f"/api/admin/questionnaires/{questionnaire['id']}").get_json()["questionnaire"]
    single_question = detail["questions"][0]
    mobile_question = detail["questions"][-1]

    submit_response = client.post(
        f"/api/h5/questionnaires/{questionnaire['slug']}/submit",
        json={
            "answers": {
                str(single_question["id"]): single_question["options"][0]["id"],
                str(mobile_question["id"]): " 138 0013 8000 ",
            }
        },
        headers=WECHAT_BROWSER_HEADERS,
    )
    assert submit_response.status_code == 200

    export_response = client.get(f"/api/admin/questionnaires/{questionnaire['id']}/export")
    export_text = export_response.get_data(as_text=True)

    assert export_response.status_code == 200
    assert "13800138000" in export_text
    assert "补充说明" in export_text


def test_questionnaire_submitted_page_and_repeat_open_redirect(client, app):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO wecom_external_contact_identity_map (
                corp_id, external_userid, unionid, openid, follow_user_userid, name, status, raw_profile
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("ww-test", "wm_ext_repeat_001", "union-repeat-001", "openid-repeat-001", "sales_01", "重复客户", "active", "{}"),
        )
        db.commit()

    create_response = client.post("/api/admin/questionnaires", json=_build_questionnaire_payload())
    questionnaire = create_response.get_json()["questionnaire"]
    detail = client.get(f"/api/admin/questionnaires/{questionnaire['id']}").get_json()["questionnaire"]
    q1 = detail["questions"][0]

    with client.session_transaction() as sess:
        sess["questionnaire_h5_identity"] = {
            "openid": "openid-repeat-001",
            "unionid": "union-repeat-001",
            "respondent_key": "respondent-repeat-001",
        }

    first_submit = client.post(
        f"/api/h5/questionnaires/{questionnaire['slug']}/submit",
        json={"answers": {str(q1["id"]): q1["options"][0]["id"]}},
        headers=WECHAT_BROWSER_HEADERS,
    )
    assert first_submit.status_code == 200

    page_response = client.get(f"/s/{questionnaire['slug']}", headers=WECHAT_BROWSER_HEADERS, follow_redirects=False)
    assert page_response.status_code == 302
    assert page_response.headers["Location"] == "https://example.com/next"

    submitted_response = client.get(f"/s/{questionnaire['slug']}/submitted")
    assert submitted_response.status_code == 200
    assert "已经提交" in submitted_response.get_data(as_text=True)


def test_questionnaire_repeat_open_without_redirect_url_falls_back_to_submitted_page(client, app):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO wecom_external_contact_identity_map (
                corp_id, external_userid, unionid, openid, follow_user_userid, name, status, raw_profile
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("ww-test", "wm_ext_repeat_no_redirect_001", "union-repeat-no-redirect-001", "openid-repeat-no-redirect-001", "sales_01", "重复客户无跳转", "active", "{}"),
        )
        db.commit()

    create_response = client.post(
        "/api/admin/questionnaires",
        json=_build_questionnaire_payload(redirect_url=""),
    )
    questionnaire = create_response.get_json()["questionnaire"]
    detail = client.get(f"/api/admin/questionnaires/{questionnaire['id']}").get_json()["questionnaire"]
    q1 = detail["questions"][0]

    with client.session_transaction() as sess:
        sess["questionnaire_h5_identity"] = {
            "openid": "openid-repeat-no-redirect-001",
            "unionid": "union-repeat-no-redirect-001",
            "respondent_key": "respondent-repeat-no-redirect-001",
        }

    first_submit = client.post(
        f"/api/h5/questionnaires/{questionnaire['slug']}/submit",
        json={"answers": {str(q1["id"]): q1["options"][0]["id"]}},
        headers=WECHAT_BROWSER_HEADERS,
    )
    assert first_submit.status_code == 200

    page_response = client.get(f"/s/{questionnaire['slug']}", headers=WECHAT_BROWSER_HEADERS, follow_redirects=False)
    assert page_response.status_code == 302
    assert page_response.headers["Location"] == f"/s/{questionnaire['slug']}/submitted"


def test_public_questionnaire_get_returns_already_submitted(client, app):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO wecom_external_contact_identity_map (
                corp_id, external_userid, unionid, openid, follow_user_userid, name, status, raw_profile
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("ww-test", "wm_ext_repeat_get_001", "union-repeat-get-001", "openid-repeat-get-001", "sales_01", "重复查看客户", "active", "{}"),
        )
        db.commit()

    create_response = client.post("/api/admin/questionnaires", json=_build_questionnaire_payload())
    questionnaire = create_response.get_json()["questionnaire"]
    detail = client.get(f"/api/admin/questionnaires/{questionnaire['id']}").get_json()["questionnaire"]
    q1 = detail["questions"][0]

    with client.session_transaction() as sess:
        sess["questionnaire_h5_identity"] = {
            "openid": "openid-repeat-get-001",
            "unionid": "union-repeat-get-001",
            "respondent_key": "respondent-repeat-get-001",
        }

    first_submit = client.post(
        f"/api/h5/questionnaires/{questionnaire['slug']}/submit",
        json={"answers": {str(q1["id"]): q1["options"][0]["id"]}},
        headers=WECHAT_BROWSER_HEADERS,
    )
    assert first_submit.status_code == 200

    response = client.get(f"/api/h5/questionnaires/{questionnaire['slug']}", headers=WECHAT_BROWSER_HEADERS)
    assert response.status_code == 409
    assert response.get_json()["error"] == "already_submitted"
    assert response.get_json()["message"] == "已经提交"
    assert response.get_json()["redirect_url"] == "https://example.com/next"


def test_questionnaire_submit_rejects_duplicate_submission(client, app):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO wecom_external_contact_identity_map (
                corp_id, external_userid, unionid, openid, follow_user_userid, name, status, raw_profile
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("ww-test", "wm_ext_repeat_submit_001", "union-repeat-submit-001", "openid-repeat-submit-001", "sales_01", "重复提交客户", "active", "{}"),
        )
        db.commit()

    create_response = client.post("/api/admin/questionnaires", json=_build_questionnaire_payload())
    questionnaire = create_response.get_json()["questionnaire"]
    detail = client.get(f"/api/admin/questionnaires/{questionnaire['id']}").get_json()["questionnaire"]
    q1 = detail["questions"][0]

    with client.session_transaction() as sess:
        sess["questionnaire_h5_identity"] = {
            "openid": "openid-repeat-submit-001",
            "unionid": "union-repeat-submit-001",
            "respondent_key": "respondent-repeat-submit-001",
        }

    first_submit = client.post(
        f"/api/h5/questionnaires/{questionnaire['slug']}/submit",
        json={"answers": {str(q1["id"]): q1["options"][0]["id"]}},
        headers=WECHAT_BROWSER_HEADERS,
    )
    assert first_submit.status_code == 200

    second_submit = client.post(
        f"/api/h5/questionnaires/{questionnaire['slug']}/submit",
        json={"answers": {str(q1["id"]): q1["options"][0]["id"]}},
        headers=WECHAT_BROWSER_HEADERS,
    )
    assert second_submit.status_code == 409
    assert second_submit.get_json() == {
        "success": False,
        "error": "already_submitted",
        "message": "已经提交",
        "redirect_url": "https://example.com/next",
    }


def test_delete_questionnaire_submissions_by_slug_removes_existing_records(client, app):
    create_response = client.post("/api/admin/questionnaires", json=_build_questionnaire_payload(slug="ai"))
    questionnaire = create_response.get_json()["questionnaire"]
    detail = client.get(f"/api/admin/questionnaires/{questionnaire['id']}").get_json()["questionnaire"]
    q1 = detail["questions"][0]

    first_submit = client.post(
        f"/api/h5/questionnaires/{questionnaire['slug']}/submit",
        json={"answers": {str(q1["id"]): q1["options"][0]["id"]}},
        headers=WECHAT_BROWSER_HEADERS,
    )
    assert first_submit.status_code == 200

    with app.app_context():
        db = get_db()
        submission_id = db.execute(
            """
            SELECT id
            FROM questionnaire_submissions
            WHERE questionnaire_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (int(questionnaire["id"]),),
        ).fetchone()["id"]
        db.execute(
            """
            INSERT INTO questionnaire_external_push_logs (
                questionnaire_id, questionnaire_title_snapshot, submission_record_id,
                user_id, target_url, request_payload, status, failure_reason, created_at, updated_at
            )
            VALUES (?, ?, ?, '', 'https://example.com/webhook', '{}', 'failed', 'seed', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (int(questionnaire["id"]), questionnaire["title"], int(submission_id)),
        )
        db.commit()

        result = delete_questionnaire_submissions_by_slug("ai")
        assert result["slug"] == "ai"
        assert result["deleted_submission_count"] == 1
        assert result["deleted_answer_count"] == 3
        assert result["deleted_scrm_apply_log_count"] >= 1
        assert result["deleted_external_push_log_count"] == 1

        remaining = db.execute(
            "SELECT COUNT(*) AS total FROM questionnaire_submissions WHERE questionnaire_id = ?",
            (int(questionnaire["id"]),),
        ).fetchone()["total"]
        remaining_answers = db.execute(
            "SELECT COUNT(*) AS total FROM questionnaire_submission_answers"
        ).fetchone()["total"]
        remaining_logs = db.execute(
            "SELECT COUNT(*) AS total FROM questionnaire_external_push_logs"
        ).fetchone()["total"]
        assert remaining == 0
        assert remaining_answers == 0
        assert remaining_logs == 0


def test_questionnaire_mobile_answer_is_saved_to_submission_snapshot(client, app):
    create_response = client.post("/api/admin/questionnaires", json=_build_questionnaire_payload_with_mobile())
    questionnaire = create_response.get_json()["questionnaire"]
    detail = client.get(f"/api/admin/questionnaires/{questionnaire['id']}").get_json()["questionnaire"]
    q1 = detail["questions"][0]
    mobile_question = detail["questions"][-1]

    response = client.post(
        f"/api/h5/questionnaires/{questionnaire['slug']}/submit",
        json={
            "answers": {
                str(q1["id"]): q1["options"][0]["id"],
                str(mobile_question["id"]): " 138 0013 8000 ",
            }
        },
        headers=WECHAT_BROWSER_HEADERS,
    )
    assert response.status_code == 200

    with app.app_context():
        submission = get_db().execute(
            """
            SELECT mobile_snapshot
            FROM questionnaire_submissions
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        answer = get_db().execute(
            """
            SELECT question_type, text_value
            FROM questionnaire_submission_answers
            WHERE question_type = 'mobile'
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        assert submission["mobile_snapshot"] == "13800138000"
        assert answer["text_value"] == "13800138000"


def test_questionnaire_required_mobile_question_rejects_empty_answer(client):
    create_response = client.post("/api/admin/questionnaires", json=_build_questionnaire_payload_with_mobile())
    questionnaire = create_response.get_json()["questionnaire"]
    detail = client.get(f"/api/admin/questionnaires/{questionnaire['id']}").get_json()["questionnaire"]
    q1 = detail["questions"][0]
    mobile_question = detail["questions"][-1]

    response = client.post(
        f"/api/h5/questionnaires/{questionnaire['slug']}/submit",
        json={
            "answers": {
                str(q1["id"]): q1["options"][0]["id"],
                str(mobile_question["id"]): "",
            }
        },
        headers=WECHAT_BROWSER_HEADERS,
    )

    assert response.status_code == 400
    assert response.get_json() == {"success": False, "error": "question '手机号' is required"}


def test_questionnaire_submit_without_external_push_does_not_send_or_write_push_log(client, app, monkeypatch):
    create_response = client.post("/api/admin/questionnaires", json=_build_questionnaire_payload_with_mobile())
    questionnaire = create_response.get_json()["questionnaire"]
    detail = client.get(f"/api/admin/questionnaires/{questionnaire['id']}").get_json()["questionnaire"]
    q1 = detail["questions"][0]
    mobile_question = detail["questions"][-1]
    push_calls: list[dict[str, object]] = []

    def fake_push_post(url, json=None, headers=None, timeout=None):
        push_calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return FakeResponse({"ok": True}, status_code=200)

    monkeypatch.setattr("wecom_ability_service.domains.questionnaire.service.requests.post", fake_push_post)

    response = client.post(
        f"/api/h5/questionnaires/{questionnaire['slug']}/submit",
        json={
            "unionid": "union-external-push-disabled-001",
            "answers": {
                str(q1["id"]): q1["options"][0]["id"],
                str(mobile_question["id"]): "13800138011",
            },
        },
        headers=WECHAT_BROWSER_HEADERS,
    )

    assert response.status_code == 200
    assert push_calls == []

    with app.app_context():
        row = get_db().execute("SELECT COUNT(*) AS total FROM questionnaire_external_push_logs").fetchone()
        assert int(row["total"] or 0) == 0


def test_questionnaire_submit_external_push_success_uses_fixed_payload_and_logs_success(client, app, monkeypatch):
    with app.app_context():
        set_settings({"QUESTIONNAIRE_EXTERNAL_PUSH_GLOBAL_ENABLED": "true"})
    create_response = client.post(
        "/api/admin/questionnaires",
        json=_build_questionnaire_payload_with_mobile(
            external_push_enabled=True,
            external_push_url="https://hooks.example.com/questionnaire/apply",
            external_push_day=20,
            external_push_frequency=20,
            external_push_remark="黄小璨 499 用户激活",
            external_push_custom_params=[
                {"name": "source_name", "value": "黄小璨激活"},
            ],
        ),
    )
    questionnaire = create_response.get_json()["questionnaire"]
    detail = client.get(f"/api/admin/questionnaires/{questionnaire['id']}").get_json()["questionnaire"]
    q1, q2, q3, mobile_question = detail["questions"]
    push_calls: list[dict[str, object]] = []

    def fake_push_post(url, json=None, headers=None, timeout=None):
        push_calls.append({"url": url, "json": json, "headers": dict(headers or {}), "timeout": timeout})
        return FakeResponse({"success": False, "message": "ignored"}, status_code=200)

    monkeypatch.setattr("wecom_ability_service.domains.questionnaire.service.requests.post", fake_push_post)

    response = client.post(
        f"/api/h5/questionnaires/{questionnaire['slug']}/submit",
        json={
            "unionid": "union-external-push-success-001",
            "answers": {
                str(q1["id"]): q1["options"][1]["id"],
                str(q2["id"]): [q2["options"][0]["id"]],
                str(q3["id"]): "",
                str(mobile_question["id"]): "13800138012",
            },
        },
        headers=WECHAT_BROWSER_HEADERS,
    )

    assert response.status_code == 200
    assert response.get_json()["success"] is True
    assert len(push_calls) == 1
    assert push_calls[0]["url"] == "https://hooks.example.com/questionnaire/apply"
    assert push_calls[0]["headers"]["Content-Type"] == "application/json"
    assert push_calls[0]["timeout"] == 3
    assert push_calls[0]["json"] == {
        "user_id": "union-external-push-success-001",
        "questionnaire_title": "来访测评",
        "submitted_at": push_calls[0]["json"]["submitted_at"],
        "phone_number": "13800138012",
        "day": 20,
        "frequency": 20,
        "remark": "黄小璨 499 用户激活",
        "source_name": "黄小璨激活",
        "answers": [
            {"title": "你的预算", "answer": "10-30万"},
            {"title": "你的关注点", "answer": ["效果"]},
            {"title": "补充说明", "answer": ""},
            {"title": "手机号", "answer": "13800138012"},
        ],
    }
    # PG TIMESTAMPTZ returns UTC (+00:00); _format_iso_datetime preserves
    # existing timezone so the suffix depends on the database backend.
    import re as _re
    assert _re.search(r"[+-]\d{2}:\d{2}$", push_calls[0]["json"]["submitted_at"]), \
        f"submitted_at should end with a timezone offset, got: {push_calls[0]['json']['submitted_at']}"

    with app.app_context():
        row = get_db().execute(
            """
            SELECT questionnaire_id, user_id, target_url, response_status_code, status, failure_reason, request_payload, response_body
            FROM questionnaire_external_push_logs
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        assert int(row["questionnaire_id"]) == int(questionnaire["id"])
        assert row["user_id"] == "union-external-push-success-001"
        assert row["target_url"] == "https://hooks.example.com/questionnaire/apply"
        assert int(row["response_status_code"]) == 200
        assert row["status"] == "success"
        assert row["failure_reason"] == ""
        assert (row["request_payload"] if isinstance(row["request_payload"], (dict, list)) else json.loads(row["request_payload"]))["phone_number"] == "13800138012"
        assert (row["request_payload"] if isinstance(row["request_payload"], (dict, list)) else json.loads(row["request_payload"]))["day"] == 20
        assert (row["request_payload"] if isinstance(row["request_payload"], (dict, list)) else json.loads(row["request_payload"]))["frequency"] == 20
        assert (row["request_payload"] if isinstance(row["request_payload"], (dict, list)) else json.loads(row["request_payload"]))["remark"] == "黄小璨 499 用户激活"
        assert (row["request_payload"] if isinstance(row["request_payload"], (dict, list)) else json.loads(row["request_payload"]))["source_name"] == "黄小璨激活"
        assert (row["request_payload"] if isinstance(row["request_payload"], (dict, list)) else json.loads(row["request_payload"]))["answers"][1]["answer"] == ["效果"]
        assert (row["request_payload"] if isinstance(row["request_payload"], (dict, list)) else json.loads(row["request_payload"]))["answers"][2]["answer"] == ""
        assert '"success": false' in row["response_body"]


def test_questionnaire_submit_external_push_without_mobile_question_sends_null_phone_number(client, app, monkeypatch):
    with app.app_context():
        set_settings({"QUESTIONNAIRE_EXTERNAL_PUSH_GLOBAL_ENABLED": "true"})
    create_response = client.post(
        "/api/admin/questionnaires",
        json=_build_questionnaire_payload(
            external_push_enabled=True,
            external_push_url="https://hooks.example.com/questionnaire/apply",
        ),
    )
    questionnaire = create_response.get_json()["questionnaire"]
    detail = client.get(f"/api/admin/questionnaires/{questionnaire['id']}").get_json()["questionnaire"]
    q1, q2, q3 = detail["questions"]
    push_calls: list[dict[str, object]] = []

    def fake_push_post(url, json=None, headers=None, timeout=None):
        push_calls.append({"url": url, "json": json, "headers": dict(headers or {}), "timeout": timeout})
        return FakeResponse({"ok": True}, status_code=200)

    monkeypatch.setattr("wecom_ability_service.domains.questionnaire.service.requests.post", fake_push_post)

    response = client.post(
        f"/api/h5/questionnaires/{questionnaire['slug']}/submit",
        json={
            "unionid": "union-external-push-no-mobile-001",
            "answers": {
                str(q1["id"]): q1["options"][0]["id"],
                str(q2["id"]): [q2["options"][0]["id"]],
                str(q3["id"]): "没有手机号题",
            },
        },
        headers=WECHAT_BROWSER_HEADERS,
    )

    assert response.status_code == 200
    assert response.get_json()["success"] is True
    assert len(push_calls) == 1
    assert push_calls[0]["json"]["phone_number"] == "NULL"

    with app.app_context():
        row = get_db().execute(
            """
            SELECT request_payload
            FROM questionnaire_external_push_logs
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        assert (row["request_payload"] if isinstance(row["request_payload"], (dict, list)) else json.loads(row["request_payload"]))["phone_number"] == "NULL"


def test_questionnaire_external_push_rejects_invalid_fixed_number_and_reserved_custom_param_name(client):
    invalid_number_response = client.post(
        "/api/admin/questionnaires",
        json=_build_questionnaire_payload(external_push_enabled=True, external_push_url="https://hooks.example.com/q", external_push_day="abc"),
    )
    assert invalid_number_response.status_code == 400
    assert invalid_number_response.get_json() == {
        "ok": False,
        "error": "external_push_day must be an integer",
    }

    reserved_name_response = client.post(
        "/api/admin/questionnaires",
        json=_build_questionnaire_payload(
            external_push_enabled=True,
            external_push_url="https://hooks.example.com/q",
            external_push_custom_params=[{"name": "remark", "value": "bad"}],
        ),
    )
    assert reserved_name_response.status_code == 400
    assert reserved_name_response.get_json() == {
        "ok": False,
        "error": "external_push_custom_params name 'remark' is reserved",
    }

    phone_number_reserved_response = client.post(
        "/api/admin/questionnaires",
        json=_build_questionnaire_payload(
            external_push_enabled=True,
            external_push_url="https://hooks.example.com/q",
            external_push_custom_params=[{"name": "phone_number", "value": "bad"}],
        ),
    )
    assert phone_number_reserved_response.status_code == 400
    assert phone_number_reserved_response.get_json() == {
        "ok": False,
        "error": "external_push_custom_params name 'phone_number' is reserved",
    }


def test_questionnaire_submit_external_push_global_switch_off_skips_without_breaking_submit(client, app, monkeypatch):
    with app.app_context():
        set_settings({"QUESTIONNAIRE_EXTERNAL_PUSH_GLOBAL_ENABLED": "false"})
    create_response = client.post(
        "/api/admin/questionnaires",
        json=_build_questionnaire_payload_with_mobile(
            external_push_enabled=True,
            external_push_url="https://hooks.example.com/questionnaire/apply",
        ),
    )
    questionnaire = create_response.get_json()["questionnaire"]
    detail = client.get(f"/api/admin/questionnaires/{questionnaire['id']}").get_json()["questionnaire"]
    q1 = detail["questions"][0]
    mobile_question = detail["questions"][-1]
    push_calls: list[dict[str, object]] = []

    def fake_push_post(url, json=None, headers=None, timeout=None):
        push_calls.append({"url": url, "json": json, "headers": dict(headers or {}), "timeout": timeout})
        return FakeResponse({"ok": True}, status_code=200)

    monkeypatch.setattr("wecom_ability_service.domains.questionnaire.service.requests.post", fake_push_post)

    response = client.post(
        f"/api/h5/questionnaires/{questionnaire['slug']}/submit",
        json={
            "unionid": "union-external-push-global-off-001",
            "answers": {
                str(q1["id"]): q1["options"][0]["id"],
                str(mobile_question["id"]): "13800138020",
            },
        },
        headers=WECHAT_BROWSER_HEADERS,
    )

    assert response.status_code == 200
    assert response.get_json()["success"] is True
    assert push_calls == []

    with app.app_context():
        row = get_db().execute(
            """
            SELECT status, failure_reason, target_url, request_payload, response_status_code
            FROM questionnaire_external_push_logs
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        assert row["status"] == "skipped"
        assert row["failure_reason"] == "skipped by global external push switch"
        assert row["target_url"] == "https://hooks.example.com/questionnaire/apply"
        assert row["response_status_code"] is None
        assert (row["request_payload"] if isinstance(row["request_payload"], (dict, list)) else json.loads(row["request_payload"]))["user_id"] == "union-external-push-global-off-001"


def test_questionnaire_submit_external_push_non_200_records_failed_without_breaking_submit(client, app, monkeypatch):
    create_response = client.post(
        "/api/admin/questionnaires",
        json=_build_questionnaire_payload_with_mobile(
            external_push_enabled=True,
            external_push_url="https://hooks.example.com/questionnaire/apply",
        ),
    )
    questionnaire = create_response.get_json()["questionnaire"]
    detail = client.get(f"/api/admin/questionnaires/{questionnaire['id']}").get_json()["questionnaire"]
    q1 = detail["questions"][0]
    mobile_question = detail["questions"][-1]

    def fake_push_post(url, json=None, headers=None, timeout=None):
        return FakeResponse({"error": "server exploded"}, status_code=500)

    monkeypatch.setattr("wecom_ability_service.domains.questionnaire.service.requests.post", fake_push_post)

    response = client.post(
        f"/api/h5/questionnaires/{questionnaire['slug']}/submit",
        json={
            "unionid": "union-external-push-failed-001",
            "answers": {
                str(q1["id"]): q1["options"][0]["id"],
                str(mobile_question["id"]): "13800138013",
            },
        },
        headers=WECHAT_BROWSER_HEADERS,
    )

    assert response.status_code == 200
    assert response.get_json()["success"] is True

    with app.app_context():
        row = get_db().execute(
            """
            SELECT response_status_code, response_body, status, failure_reason
            FROM questionnaire_external_push_logs
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        assert int(row["response_status_code"]) == 500
        assert row["status"] == "failed"
        assert row["failure_reason"] == "HTTP 500"
        assert '"server exploded"' in row["response_body"]


def test_questionnaire_submit_external_push_timeout_records_failed_without_breaking_submit(client, app, monkeypatch):
    create_response = client.post(
        "/api/admin/questionnaires",
        json=_build_questionnaire_payload_with_mobile(
            external_push_enabled=True,
            external_push_url="https://hooks.example.com/questionnaire/apply",
        ),
    )
    questionnaire = create_response.get_json()["questionnaire"]
    detail = client.get(f"/api/admin/questionnaires/{questionnaire['id']}").get_json()["questionnaire"]
    q1 = detail["questions"][0]
    mobile_question = detail["questions"][-1]

    def fake_push_post(url, json=None, headers=None, timeout=None):
        raise requests.Timeout("push timed out")

    monkeypatch.setattr("wecom_ability_service.domains.questionnaire.service.requests.post", fake_push_post)

    response = client.post(
        f"/api/h5/questionnaires/{questionnaire['slug']}/submit",
        json={
            "unionid": "union-external-push-timeout-001",
            "answers": {
                str(q1["id"]): q1["options"][0]["id"],
                str(mobile_question["id"]): "13800138014",
            },
        },
        headers=WECHAT_BROWSER_HEADERS,
    )

    assert response.status_code == 200
    assert response.get_json()["success"] is True

    with app.app_context():
        row = get_db().execute(
            """
            SELECT status, failure_reason
            FROM questionnaire_external_push_logs
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        assert row["status"] == "failed"
        assert row["failure_reason"] == "request timeout"


def test_questionnaire_external_push_requires_url_when_enabled(client):
    create_response = client.post(
        "/api/admin/questionnaires",
        json=_build_questionnaire_payload(external_push_enabled=True, external_push_url=""),
    )
    assert create_response.status_code == 400
    assert create_response.get_json() == {
        "ok": False,
        "error": "external_push_url is required when external_push_enabled is enabled",
    }

    valid_create = client.post("/api/admin/questionnaires", json=_build_questionnaire_payload())
    questionnaire_id = valid_create.get_json()["questionnaire"]["id"]
    update_response = client.put(
        f"/api/admin/questionnaires/{questionnaire_id}",
        json=_build_questionnaire_payload(external_push_enabled=True, external_push_url=""),
    )
    assert update_response.status_code == 400
    assert update_response.get_json() == {
        "ok": False,
        "error": "external_push_url is required when external_push_enabled is enabled",
    }


def test_questionnaire_create_auto_dedupes_generated_slug_when_name_collides(client):
    payload = {
        "name": "黄小璨AI激活问卷",
        "title": "填写问卷激活黄小璨AI",
        "description": "您在问卷中填写的信息会被录入黄小璨进行对黄小璨的初始设置",
        "redirect_url": "",
        "questions": [
            {
                "type": "mobile",
                "title": "请输入手机号",
                "required": True,
                "sort_order": 1,
                "placeholder_text": "请输入登录AI分身的唯一手机号码",
            }
        ],
        "score_rules": [],
    }

    first_response = client.post("/api/admin/questionnaires", json=payload)
    second_response = client.post("/api/admin/questionnaires", json=payload)

    assert first_response.status_code == 200
    assert second_response.status_code == 200

    first_slug = first_response.get_json()["questionnaire"]["slug"]
    second_slug = second_response.get_json()["questionnaire"]["slug"]
    assert first_slug == "ai"
    assert second_slug != first_slug
    assert second_slug.startswith("ai-")


def test_questionnaire_external_push_failed_log_can_be_retried_and_reuses_original_payload(client, app, monkeypatch):
    create_response = client.post(
        "/api/admin/questionnaires",
        json=_build_questionnaire_payload_with_mobile(
            external_push_enabled=True,
            external_push_url="https://hooks.example.com/questionnaire/apply",
        ),
    )
    questionnaire = create_response.get_json()["questionnaire"]
    detail = client.get(f"/api/admin/questionnaires/{questionnaire['id']}").get_json()["questionnaire"]
    q1 = detail["questions"][0]
    mobile_question = detail["questions"][-1]
    push_calls: list[dict[str, object]] = []
    responses = [
        FakeResponse({"error": "server exploded"}, status_code=500),
        FakeResponse({"ok": True}, status_code=200),
    ]

    def fake_push_post(url, json=None, headers=None, timeout=None):
        push_calls.append({"url": url, "json": json, "headers": dict(headers or {}), "timeout": timeout})
        return responses.pop(0)

    monkeypatch.setattr("wecom_ability_service.domains.questionnaire.service.requests.post", fake_push_post)

    submit_response = client.post(
        f"/api/h5/questionnaires/{questionnaire['slug']}/submit",
        json={
            "unionid": "union-external-push-retry-001",
            "answers": {
                str(q1["id"]): q1["options"][0]["id"],
                str(mobile_question["id"]): "13800138015",
            },
        },
        headers=WECHAT_BROWSER_HEADERS,
    )

    assert submit_response.status_code == 200

    with app.app_context():
        original = get_db().execute(
            """
            SELECT id, retry_from_log_id, retry_attempt, status, target_url, request_payload
            FROM questionnaire_external_push_logs
            ORDER BY id ASC
            LIMIT 1
            """
        ).fetchone()
        original_id = int(original["id"])
        original_payload = (original["request_payload"] if isinstance(original["request_payload"], (dict, list)) else json.loads(original["request_payload"]))
        assert original["status"] == "failed"
        assert original["retry_from_log_id"] is None
        assert int(original["retry_attempt"] or 0) == 0

    retry_response = client.post(
        f"/admin/questionnaires/{questionnaire['id']}/external-push-logs/{original_id}/retry",
        data={"status": "failed", "limit": "10"},
        follow_redirects=True,
    )

    assert retry_response.status_code == 200
    retry_html = retry_response.get_data(as_text=True)
    assert "补发已执行，请查看最近结果。" in retry_html
    assert "补发成功" in retry_html
    assert len(push_calls) == 2
    assert push_calls[0]["json"] == push_calls[1]["json"]

    with app.app_context():
        rows = get_db().execute(
            """
            SELECT id, retry_from_log_id, retry_attempt, status, response_status_code, target_url, request_payload
            FROM questionnaire_external_push_logs
            ORDER BY id ASC
            """
        ).fetchall()
        assert len(rows) == 2
        assert rows[1]["retry_from_log_id"] == original_id
        assert int(rows[1]["retry_attempt"] or 0) == 1
        assert rows[1]["status"] == "success"
        assert int(rows[1]["response_status_code"]) == 200
        assert rows[1]["target_url"] == rows[0]["target_url"]
        assert (rows[1]["request_payload"] if isinstance(rows[1]["request_payload"], (dict, list)) else json.loads(rows[1]["request_payload"])) == original_payload


def test_questionnaire_external_push_failed_log_retry_can_fail_again(client, app, monkeypatch):
    create_response = client.post(
        "/api/admin/questionnaires",
        json=_build_questionnaire_payload_with_mobile(
            external_push_enabled=True,
            external_push_url="https://hooks.example.com/questionnaire/apply",
        ),
    )
    questionnaire = create_response.get_json()["questionnaire"]
    detail = client.get(f"/api/admin/questionnaires/{questionnaire['id']}").get_json()["questionnaire"]
    q1 = detail["questions"][0]
    mobile_question = detail["questions"][-1]
    responses = [
        FakeResponse({"error": "server exploded"}, status_code=500),
        FakeResponse({"error": "still broken"}, status_code=502),
    ]

    def fake_push_post(url, json=None, headers=None, timeout=None):
        return responses.pop(0)

    monkeypatch.setattr("wecom_ability_service.domains.questionnaire.service.requests.post", fake_push_post)

    submit_response = client.post(
        f"/api/h5/questionnaires/{questionnaire['slug']}/submit",
        json={
            "unionid": "union-external-push-retry-002",
            "answers": {
                str(q1["id"]): q1["options"][0]["id"],
                str(mobile_question["id"]): "13800138016",
            },
        },
        headers=WECHAT_BROWSER_HEADERS,
    )
    assert submit_response.status_code == 200

    with app.app_context():
        original = get_db().execute(
            "SELECT id FROM questionnaire_external_push_logs ORDER BY id ASC LIMIT 1"
        ).fetchone()
        original_id = int(original["id"])

    retry_response = client.post(
        f"/admin/questionnaires/{questionnaire['id']}/external-push-logs/{original_id}/retry",
        data={"status": "failed", "limit": "10"},
        follow_redirects=True,
    )
    assert retry_response.status_code == 200
    retry_html = retry_response.get_data(as_text=True)
    assert "补发仍失败" in retry_html
    assert "HTTP 502" in retry_html

    with app.app_context():
        rows = get_db().execute(
            """
            SELECT retry_from_log_id, retry_attempt, status, response_status_code, failure_reason
            FROM questionnaire_external_push_logs
            ORDER BY id ASC
            """
        ).fetchall()
        assert len(rows) == 2
        assert rows[1]["retry_from_log_id"] == original_id
        assert int(rows[1]["retry_attempt"] or 0) == 1
        assert rows[1]["status"] == "failed"
        assert int(rows[1]["response_status_code"]) == 502
        assert rows[1]["failure_reason"] == "HTTP 502"


def test_questionnaire_external_push_success_log_cannot_be_retried(client, app, monkeypatch):
    create_response = client.post(
        "/api/admin/questionnaires",
        json=_build_questionnaire_payload_with_mobile(
            external_push_enabled=True,
            external_push_url="https://hooks.example.com/questionnaire/apply",
        ),
    )
    questionnaire = create_response.get_json()["questionnaire"]
    detail = client.get(f"/api/admin/questionnaires/{questionnaire['id']}").get_json()["questionnaire"]
    q1 = detail["questions"][0]
    mobile_question = detail["questions"][-1]

    monkeypatch.setattr(
        "wecom_ability_service.domains.questionnaire.service.requests.post",
        lambda url, json=None, headers=None, timeout=None: FakeResponse({"ok": True}, status_code=200),
    )

    submit_response = client.post(
        f"/api/h5/questionnaires/{questionnaire['slug']}/submit",
        json={
            "unionid": "union-external-push-retry-003",
            "answers": {
                str(q1["id"]): q1["options"][0]["id"],
                str(mobile_question["id"]): "13800138017",
            },
        },
        headers=WECHAT_BROWSER_HEADERS,
    )
    assert submit_response.status_code == 200

    with app.app_context():
        row = get_db().execute(
            "SELECT id FROM questionnaire_external_push_logs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        log_id = int(row["id"])

    retry_response = client.post(
        f"/admin/questionnaires/{questionnaire['id']}/external-push-logs/{log_id}/retry",
        data={"status": "", "limit": "10"},
        follow_redirects=True,
    )

    assert retry_response.status_code == 200
    retry_html = retry_response.get_data(as_text=True)
    assert "only failed external push logs can be retried" in retry_html

    with app.app_context():
        total = get_db().execute("SELECT COUNT(*) AS total FROM questionnaire_external_push_logs").fetchone()
        assert int(total["total"] or 0) == 1


def test_questionnaire_external_push_failed_logs_can_be_retried_in_batch_with_summary(client, app, monkeypatch):
    create_response = client.post(
        "/api/admin/questionnaires",
        json=_build_questionnaire_payload_with_mobile(
            external_push_enabled=True,
            external_push_url="https://hooks.example.com/questionnaire/apply",
        ),
    )
    questionnaire = create_response.get_json()["questionnaire"]
    detail = client.get(f"/api/admin/questionnaires/{questionnaire['id']}").get_json()["questionnaire"]
    q1 = detail["questions"][0]
    mobile_question = detail["questions"][-1]
    responses = [
        FakeResponse({"error": "fail-1"}, status_code=500),
        FakeResponse({"error": "fail-2"}, status_code=502),
        FakeResponse({"ok": True}, status_code=200),
        FakeResponse({"error": "still broken"}, status_code=503),
    ]

    def fake_push_post(url, json=None, headers=None, timeout=None):
        return responses.pop(0)

    monkeypatch.setattr("wecom_ability_service.domains.questionnaire.service.requests.post", fake_push_post)

    for unionid, mobile in [
        ("union-external-push-batch-001", "13800138018"),
        ("union-external-push-batch-002", "13800138019"),
    ]:
        response = client.post(
            f"/api/h5/questionnaires/{questionnaire['slug']}/submit",
            json={
                "unionid": unionid,
                "answers": {
                    str(q1["id"]): q1["options"][0]["id"],
                    str(mobile_question["id"]): mobile,
                },
            },
            headers=WECHAT_BROWSER_HEADERS,
        )
        assert response.status_code == 200

    with app.app_context():
        rows = get_db().execute(
            """
            SELECT id, status
            FROM questionnaire_external_push_logs
            WHERE retry_from_log_id IS NULL
            ORDER BY id ASC
            """
        ).fetchall()
        failed_ids = [str(row["id"]) for row in rows]
        assert [row["status"] for row in rows] == ["failed", "failed"]

    retry_response = client.post(
        f"/admin/questionnaires/{questionnaire['id']}/external-push-logs/retry-batch",
        data={"status": "failed_current", "limit": "20", "push_log_ids": failed_ids},
        follow_redirects=True,
    )
    retry_html = retry_response.get_data(as_text=True)

    assert retry_response.status_code == 200
    assert "批量补发已执行：选中 2 条，实际补发 2 条，成功 1 条，失败 1 条。" in retry_html
    assert "补发成功" in retry_html
    assert "补发仍失败（待补发）" in retry_html

    with app.app_context():
        rows = get_db().execute(
            """
            SELECT retry_from_log_id, retry_attempt, status, response_status_code, failure_reason
            FROM questionnaire_external_push_logs
            ORDER BY id ASC
            """
        ).fetchall()
        assert len(rows) == 4
        assert rows[2]["retry_from_log_id"] is not None
        assert rows[3]["retry_from_log_id"] is not None
        assert int(rows[2]["retry_attempt"] or 0) == 1
        assert int(rows[3]["retry_attempt"] or 0) == 1
        assert rows[2]["status"] == "success"
        assert int(rows[2]["response_status_code"]) == 200
        assert rows[3]["status"] == "failed"
        assert int(rows[3]["response_status_code"]) == 503
        assert rows[3]["failure_reason"] == "HTTP 503"


def test_questionnaire_submit_success_sends_identity_webhook(client, app, monkeypatch):
    monkeypatch.setattr(
        "wecom_ability_service.domains.user_ops.service._resolve_third_party_user_id_by_mobile",
        lambda mobile: f"tp_{mobile}",
    )

    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            ("wm_ext_questionnaire_webhook_001", "问卷 webhook 客户", "sales_88", "问卷线索", "wm_ext_questionnaire_webhook_001"),
        )
        db.execute(
            """
            INSERT INTO wecom_external_contact_identity_map (
                corp_id, external_userid, unionid, openid, follow_user_userid, name, status, raw_profile
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ww-test",
                "wm_ext_questionnaire_webhook_001",
                "union-questionnaire-webhook-001",
                "openid-questionnaire-webhook-001",
                "sales_88",
                "问卷 webhook 客户",
                "active",
                "{}",
            ),
        )
        db.commit()

    app.config["QUESTIONNAIRE_SUBMIT_WEBHOOK_URL"] = "https://hooks.local/questionnaire-submit"
    app.config["AUTOMATION_INTERNAL_API_TOKEN"] = "internal-token"
    app.config["QUESTIONNAIRE_SUBMIT_WEBHOOK_TOKEN"] = "questionnaire-token"
    app.config["QUESTIONNAIRE_SUBMIT_WEBHOOK_TIMEOUT_SECONDS"] = 6
    webhook_calls: list[dict[str, object]] = []

    def fake_post(url, json=None, headers=None, timeout=None):
        webhook_calls.append(
            {
                "url": url,
                "json": dict(json or {}),
                "headers": dict(headers or {}),
                "timeout": timeout,
            }
        )
        return FakeResponse({"ok": True}, status_code=202)

    monkeypatch.setattr("wecom_ability_service.domains.outbound_webhook.service.requests.post", fake_post)

    create_response = client.post("/api/admin/questionnaires", json=_build_questionnaire_payload_with_mobile())
    questionnaire = create_response.get_json()["questionnaire"]
    detail = client.get(f"/api/admin/questionnaires/{questionnaire['id']}").get_json()["questionnaire"]
    q1 = detail["questions"][0]
    mobile_question = detail["questions"][-1]

    response = client.post(
        f"/api/h5/questionnaires/{questionnaire['slug']}/submit",
        json={
            "unionid": "union-questionnaire-webhook-001",
            "answers": {
                str(q1["id"]): q1["options"][0]["id"],
                str(mobile_question["id"]): "176 4005 0003",
            },
        },
        headers=WECHAT_BROWSER_HEADERS,
    )

    assert response.status_code == 200
    assert len(webhook_calls) == 1
    assert webhook_calls[0]["url"] == "https://hooks.local/questionnaire-submit"
    assert webhook_calls[0]["headers"]["Authorization"] == "Bearer questionnaire-token"
    assert webhook_calls[0]["timeout"] == 6
    assert webhook_calls[0]["json"] == {
        "mobile": "17640050003",
        "userid": "sales_88",
        "unionid": "union-questionnaire-webhook-001",
    }
    with app.app_context():
        row = get_db().execute(
            """
            SELECT event_type, status, attempt_count, response_status_code, source_key
            FROM outbound_webhook_deliveries
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        assert row["event_type"] == "questionnaire_submit"
        assert row["status"] == "success"
        assert int(row["attempt_count"]) == 1
        assert int(row["response_status_code"]) == 202
        assert row["source_key"] == "submission_id"


def test_questionnaire_submit_webhook_failure_does_not_break_submit(client, app, monkeypatch):
    monkeypatch.setattr(
        "wecom_ability_service.domains.user_ops.service._resolve_third_party_user_id_by_mobile",
        lambda mobile: f"tp_{mobile}",
    )

    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            ("wm_ext_questionnaire_webhook_002", "问卷 webhook 失败客户", "sales_89", "问卷线索", "wm_ext_questionnaire_webhook_002"),
        )
        db.execute(
            """
            INSERT INTO wecom_external_contact_identity_map (
                corp_id, external_userid, unionid, openid, follow_user_userid, name, status, raw_profile
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ww-test",
                "wm_ext_questionnaire_webhook_002",
                "union-questionnaire-webhook-002",
                "openid-questionnaire-webhook-002",
                "sales_89",
                "问卷 webhook 失败客户",
                "active",
                "{}",
            ),
        )
        db.commit()

    app.config["QUESTIONNAIRE_SUBMIT_WEBHOOK_URL"] = "https://hooks.local/questionnaire-submit"
    app.config["QUESTIONNAIRE_SUBMIT_WEBHOOK_TIMEOUT_SECONDS"] = 6
    app.config["OUTBOUND_WEBHOOK_RETRY_ENABLED"] = True
    app.config["OUTBOUND_WEBHOOK_RETRY_MAX_ATTEMPTS"] = 3

    def fake_post(url, json=None, headers=None, timeout=None):
        raise requests.RequestException("webhook boom")

    monkeypatch.setattr("wecom_ability_service.domains.outbound_webhook.service.requests.post", fake_post)

    create_response = client.post("/api/admin/questionnaires", json=_build_questionnaire_payload_with_mobile())
    questionnaire = create_response.get_json()["questionnaire"]
    detail = client.get(f"/api/admin/questionnaires/{questionnaire['id']}").get_json()["questionnaire"]
    q1 = detail["questions"][0]
    mobile_question = detail["questions"][-1]

    response = client.post(
        f"/api/h5/questionnaires/{questionnaire['slug']}/submit",
        json={
            "unionid": "union-questionnaire-webhook-002",
            "answers": {
                str(q1["id"]): q1["options"][0]["id"],
                str(mobile_question["id"]): "17640050004",
            },
        },
        headers=WECHAT_BROWSER_HEADERS,
    )

    assert response.status_code == 200
    assert response.get_json()["success"] is True

    with app.app_context():
        submission = get_db().execute(
            """
            SELECT mobile_snapshot, unionid, follow_user_userid
            FROM questionnaire_submissions
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        assert submission["mobile_snapshot"] == "17640050004"
        assert submission["unionid"] == "union-questionnaire-webhook-002"
        assert submission["follow_user_userid"] == "sales_89"
        delivery = get_db().execute(
            """
            SELECT event_type, status, attempt_count, next_retry_at, last_error
            FROM outbound_webhook_deliveries
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        assert delivery["event_type"] == "questionnaire_submit"
        assert delivery["status"] == "retry_scheduled"
        assert int(delivery["attempt_count"]) == 1
        assert delivery["next_retry_at"] != ""
        assert delivery["last_error"] == "webhook boom"


def test_questionnaire_submit_webhook_retry_due_succeeds(client, app, monkeypatch):
    monkeypatch.setattr(
        "wecom_ability_service.domains.user_ops.service._resolve_third_party_user_id_by_mobile",
        lambda mobile: f"tp_{mobile}",
    )

    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            ("wm_ext_questionnaire_webhook_003", "问卷 webhook 重试客户", "sales_90", "问卷线索", "wm_ext_questionnaire_webhook_003"),
        )
        db.execute(
            """
            INSERT INTO wecom_external_contact_identity_map (
                corp_id, external_userid, unionid, openid, follow_user_userid, name, status, raw_profile
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ww-test",
                "wm_ext_questionnaire_webhook_003",
                "union-questionnaire-webhook-003",
                "openid-questionnaire-webhook-003",
                "sales_90",
                "问卷 webhook 重试客户",
                "active",
                "{}",
            ),
        )
        db.commit()

    app.config["QUESTIONNAIRE_SUBMIT_WEBHOOK_URL"] = "https://hooks.local/questionnaire-submit"
    app.config["QUESTIONNAIRE_SUBMIT_WEBHOOK_TIMEOUT_SECONDS"] = 6
    app.config["OUTBOUND_WEBHOOK_RETRY_ENABLED"] = True
    app.config["OUTBOUND_WEBHOOK_RETRY_MAX_ATTEMPTS"] = 3
    call_count = {"value": 0}

    def fake_post(url, json=None, headers=None, timeout=None):
        call_count["value"] += 1
        if call_count["value"] == 1:
            raise requests.RequestException("retry later")
        return FakeResponse({"ok": True}, status_code=202)

    monkeypatch.setattr("wecom_ability_service.domains.outbound_webhook.service.requests.post", fake_post)

    create_response = client.post("/api/admin/questionnaires", json=_build_questionnaire_payload_with_mobile())
    questionnaire = create_response.get_json()["questionnaire"]
    detail = client.get(f"/api/admin/questionnaires/{questionnaire['id']}").get_json()["questionnaire"]
    q1 = detail["questions"][0]
    mobile_question = detail["questions"][-1]
    response = client.post(
        f"/api/h5/questionnaires/{questionnaire['slug']}/submit",
        json={
            "unionid": "union-questionnaire-webhook-003",
            "answers": {
                str(q1["id"]): q1["options"][0]["id"],
                str(mobile_question["id"]): "17640050005",
            },
        },
        headers=WECHAT_BROWSER_HEADERS,
    )
    assert response.status_code == 200

    with app.app_context():
        db = get_db()
        delivery = db.execute(
            "SELECT id, status, attempt_count FROM outbound_webhook_deliveries ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert delivery["status"] == "retry_scheduled"
        delivery_id = int(delivery["id"])
        db.execute(
            "UPDATE outbound_webhook_deliveries SET next_retry_at = '2000-01-01 00:00:00' WHERE id = ?",
            (delivery_id,),
        )
        db.commit()

    retry_response = client.post(
        "/api/customers/automation/webhook-deliveries/retry-due",
        headers={"Authorization": "Bearer internal-token"},
        json={"limit": 5},
    )
    assert retry_response.status_code == 200
    assert retry_response.get_json()["count"] >= 1

    with app.app_context():
        delivery = get_db().execute(
            "SELECT status, attempt_count, response_status_code FROM outbound_webhook_deliveries WHERE id = ?",
            (delivery_id,),
        ).fetchone()
        assert delivery["status"] == "success"
        assert int(delivery["attempt_count"]) == 2
        assert int(delivery["response_status_code"]) == 202


def test_questionnaire_submit_webhook_retry_due_rejects_invalid_internal_token(client, app):
    app.config["AUTOMATION_INTERNAL_API_TOKEN"] = "internal-token"

    response = client.post(
        "/api/customers/automation/webhook-deliveries/retry-due",
        headers={"Authorization": "Bearer wrong-token"},
        json={"limit": 5},
    )

    assert response.status_code == 401
    assert response.get_json() == {"ok": False, "error": "invalid internal token"}


def test_questionnaire_submit_webhook_without_url_records_unconfigured_delivery(client, app, monkeypatch):
    monkeypatch.setattr(
        "wecom_ability_service.domains.user_ops.service._resolve_third_party_user_id_by_mobile",
        lambda mobile: f"tp_{mobile}",
    )

    create_response = client.post("/api/admin/questionnaires", json=_build_questionnaire_payload_with_mobile())
    questionnaire = create_response.get_json()["questionnaire"]
    detail = client.get(f"/api/admin/questionnaires/{questionnaire['id']}").get_json()["questionnaire"]
    q1 = detail["questions"][0]
    mobile_question = detail["questions"][-1]
    app.config["QUESTIONNAIRE_SUBMIT_WEBHOOK_URL"] = ""

    response = client.post(
        f"/api/h5/questionnaires/{questionnaire['slug']}/submit",
        json={
            "answers": {
                str(q1["id"]): q1["options"][0]["id"],
                str(mobile_question["id"]): "17640050006",
            },
        },
        headers=WECHAT_BROWSER_HEADERS,
    )

    assert response.status_code == 200
    with app.app_context():
        delivery = get_db().execute(
            """
            SELECT event_type, status, attempt_count, last_error, target_url
            FROM outbound_webhook_deliveries
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        assert delivery["event_type"] == "questionnaire_submit"
        assert delivery["status"] == "failed"
        assert int(delivery["attempt_count"]) == 0
        assert delivery["last_error"] == "webhook_not_configured"
        assert delivery["target_url"] == ""


def test_questionnaire_without_mobile_question_does_not_fill_mobile_snapshot(client, app):
    create_response = client.post("/api/admin/questionnaires", json=_build_questionnaire_payload())
    questionnaire = create_response.get_json()["questionnaire"]
    detail = client.get(f"/api/admin/questionnaires/{questionnaire['id']}").get_json()["questionnaire"]
    q1 = detail["questions"][0]

    response = client.post(
        f"/api/h5/questionnaires/{questionnaire['slug']}/submit",
        json={"answers": {str(q1["id"]): q1["options"][0]["id"]}},
        headers=WECHAT_BROWSER_HEADERS,
    )
    assert response.status_code == 200

    with app.app_context():
        submission = get_db().execute(
            """
            SELECT mobile_snapshot
            FROM questionnaire_submissions
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        assert submission["mobile_snapshot"] == ""


def test_questionnaire_mobile_submission_binds_contact_and_overwrites_old_mobile(client, app, monkeypatch):
    monkeypatch.setattr(
        "wecom_ability_service.domains.user_ops.service._resolve_third_party_user_id_by_mobile",
        lambda mobile: f"tp_{mobile}",
    )

    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            ("wm_ext_mobile_bind_001", "问卷手机号客户", "sales_22", "问卷线索", "wm_ext_mobile_bind_001"),
        )
        db.execute(
            """
            INSERT INTO wecom_external_contact_identity_map (
                corp_id, external_userid, unionid, openid, follow_user_userid, name, status, raw_profile
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("ww-test", "wm_ext_mobile_bind_001", "union-mobile-bind-001", "openid-mobile-bind-001", "sales_22", "问卷手机号客户", "active", "{}"),
        )
        db.execute(
            """
            INSERT INTO people (mobile, third_party_user_id, created_at, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            ("13900000000", "tp_old"),
        )
        person_id = db.execute("SELECT id FROM people WHERE mobile = ?", ("13900000000",)).fetchone()["id"]
        db.execute(
            """
            INSERT INTO external_contact_bindings (
                external_userid, person_id, first_bound_by_userid, first_owner_userid, last_owner_userid, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            ("wm_ext_mobile_bind_001", person_id, "sales_22", "sales_22", "sales_22"),
        )
        db.commit()

    create_response = client.post("/api/admin/questionnaires", json=_build_questionnaire_payload_with_mobile())
    questionnaire = create_response.get_json()["questionnaire"]
    detail = client.get(f"/api/admin/questionnaires/{questionnaire['id']}").get_json()["questionnaire"]
    q1 = detail["questions"][0]
    mobile_question = detail["questions"][-1]

    response = client.post(
        f"/api/h5/questionnaires/{questionnaire['slug']}/submit",
        json={
            "unionid": "union-mobile-bind-001",
            "answers": {
                str(q1["id"]): q1["options"][0]["id"],
                str(mobile_question["id"]): "17640050002",
            },
        },
        headers=WECHAT_BROWSER_HEADERS,
    )
    assert response.status_code == 200

    with app.app_context():
        db = get_db()
        submission = db.execute(
            """
            SELECT external_userid, follow_user_userid, mobile_snapshot
            FROM questionnaire_submissions
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        binding = db.execute(
            """
            SELECT b.external_userid, p.mobile, p.third_party_user_id
            FROM external_contact_bindings b
            JOIN people p ON p.id = b.person_id
            WHERE b.external_userid = ?
            """,
            ("wm_ext_mobile_bind_001",),
        ).fetchone()
        assert submission["external_userid"] == "wm_ext_mobile_bind_001"
        assert submission["follow_user_userid"] == "sales_22"
        assert submission["mobile_snapshot"] == "17640050002"
        assert binding["mobile"] == "17640050002"
        assert binding["third_party_user_id"] == "tp_17640050002"


def test_questionnaire_mobile_submission_without_identity_still_saves_snapshot(client, app):
    create_response = client.post("/api/admin/questionnaires", json=_build_questionnaire_payload_with_mobile())
    questionnaire = create_response.get_json()["questionnaire"]
    detail = client.get(f"/api/admin/questionnaires/{questionnaire['id']}").get_json()["questionnaire"]
    q1 = detail["questions"][0]
    mobile_question = detail["questions"][-1]

    response = client.post(
        f"/api/h5/questionnaires/{questionnaire['slug']}/submit",
        json={
            "answers": {
                str(q1["id"]): q1["options"][0]["id"],
                str(mobile_question["id"]): "17640055576",
            }
        },
        headers=WECHAT_BROWSER_HEADERS,
    )
    assert response.status_code == 200

    with app.app_context():
        submission = get_db().execute(
            """
            SELECT external_userid, mobile_snapshot
            FROM questionnaire_submissions
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        binding = get_db().execute("SELECT COUNT(*) AS total FROM external_contact_bindings").fetchone()
        assert submission["external_userid"] == ""
        assert submission["mobile_snapshot"] == "17640055576"
        assert int(binding["total"]) == 0


def test_sidebar_contact_binding_flow(client, app):
    status_response = client.get(
        "/api/sidebar/contact-binding-status",
        query_string={"external_userid": "wm_ext_sidebar_001"},
    )
    assert status_response.status_code == 200
    assert status_response.get_json() == {
        "ok": True,
        "is_bound": False,
        "external_userid": "wm_ext_sidebar_001",
        "owner_userid": "",
        "customer_name": "",
        "remark": "",
        "display_name": "客户 ar_001",
    }

    bind_response = client.post(
        "/api/sidebar/bind-mobile",
        json={
            "external_userid": "wm_ext_sidebar_001",
            "owner_userid": "sales_01",
            "bind_by_userid": "sales_01",
            "mobile": "13800138000",
        },
    )
    assert bind_response.status_code == 200
    binding = bind_response.get_json()["binding"]
    assert binding["person_id"] == 1
    assert binding["external_userid"] == "wm_ext_sidebar_001"
    assert binding["owner_userid"] == "sales_01"
    assert binding["mobile"] == "13800138000"
    assert binding["third_party_user_id"] == "mocktp_13800138000"
    assert binding["detail_url"] == "https://www.youcangogogo.com/person/1"

    repeat_bind = client.post(
        "/api/sidebar/bind-mobile",
        json={
            "external_userid": "wm_ext_sidebar_001",
            "owner_userid": "sales_02",
            "bind_by_userid": "sales_02",
            "mobile": "13800138000",
        },
    )
    assert repeat_bind.status_code == 200
    repeat_binding = repeat_bind.get_json()["binding"]
    assert repeat_binding["person_id"] == 1
    assert repeat_binding["owner_userid"] == "sales_02"
    assert repeat_binding["mobile"] == "13800138000"

    bound_status = client.get(
        "/api/sidebar/contact-binding-status",
        query_string={"external_userid": "wm_ext_sidebar_001"},
    )
    assert bound_status.status_code == 200
    assert bound_status.get_json()["is_bound"] is True
    assert bound_status.get_json()["person_id"] == 1
    assert bound_status.get_json()["mobile"] == "13800138000"
    assert bound_status.get_json()["third_party_user_id"] == "mocktp_13800138000"
    assert bound_status.get_json()["detail_url"] == "https://www.youcangogogo.com/person/1"
    assert bound_status.get_json()["display_name"] == "客户 ar_001"

    with app.app_context():
        db = get_db()
        people = db.execute("SELECT id, mobile, third_party_user_id FROM people ORDER BY id ASC").fetchall()
        bindings = db.execute(
            """
            SELECT external_userid, person_id, first_bound_by_userid, first_owner_userid, last_owner_userid
            FROM external_contact_bindings
            ORDER BY external_userid ASC
            """
        ).fetchall()
        assert people == [{"id": 1, "mobile": "13800138000", "third_party_user_id": "mocktp_13800138000"}]
        assert bindings == [
            {
                "external_userid": "wm_ext_sidebar_001",
                "person_id": 1,
                "first_bound_by_userid": "sales_01",
                "first_owner_userid": "sales_01",
                "last_owner_userid": "sales_01",
            }
        ]


def test_sidebar_contact_binding_conflict_and_people_reuse(client, app):
    first_bind = client.post(
        "/api/sidebar/bind-mobile",
        json={
            "external_userid": "wm_ext_sidebar_002",
            "owner_userid": "sales_01",
            "bind_by_userid": "sales_01",
            "mobile": "13900001111",
        },
    )
    assert first_bind.status_code == 200

    second_bind = client.post(
        "/api/sidebar/bind-mobile",
        json={
            "external_userid": "wm_ext_sidebar_003",
            "owner_userid": "sales_02",
            "bind_by_userid": "sales_02",
            "mobile": "+86 13900001111",
        },
    )
    assert second_bind.status_code == 200
    assert second_bind.get_json()["binding"]["person_id"] == 1

    conflict = client.post(
        "/api/sidebar/bind-mobile",
        json={
            "external_userid": "wm_ext_sidebar_002",
            "owner_userid": "sales_01",
            "bind_by_userid": "sales_01",
            "mobile": "13700002222",
        },
    )
    assert conflict.status_code == 409
    assert conflict.get_json() == {
        "ok": False,
        "error": "external_userid already bound to another mobile",
    }


def test_sidebar_jssdk_config_returns_signatures(client, monkeypatch):
    monkeypatch.setattr("requests.get", fake_wecom_get)
    response = client.get(
        "/api/sidebar/jssdk-config",
        query_string={"url": "https://www.youcangogogo.com/sidebar/bind-mobile?foo=1#debug"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["corp_id"] == "ww-test"
    assert payload["agent_id"] == "1000002"
    assert payload["config"]["url"] == "https://www.youcangogogo.com/sidebar/bind-mobile?foo=1"
    assert payload["agent_config"]["url"] == "https://www.youcangogogo.com/sidebar/bind-mobile?foo=1"
    assert payload["config"]["signature"]
    assert payload["agent_config"]["signature"]
    assert payload["config"]["nonceStr"]
    assert payload["agent_config"]["nonceStr"]


def test_sidebar_page_contains_jssdk_debug_chain(client):
    response = client.get("/sidebar/bind-mobile")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "wx.config success" in body
    assert "wx.agentConfig success" in body
    assert "getCurExternalContact success" in body
    assert "/api/sidebar/jssdk-config" in body
    assert "客户档案绑定" in body
    assert "debugWrap.classList.toggle('hidden', !debugEnabled);" in body
    assert "自动化转化操作区" in body
    assert "是否在自动化转化池" in body
    assert "当前池子" in body
    assert "当前阶段" in body
    assert "当前目标" in body
    assert "最近 AI 推送时间" in body
    assert "实时标签" in body
    assert "已填写问卷及答案" in body
    assert "放入自动化转化池" in body
    assert "移除自动化转化池" in body
    assert "转化为重点跟进" in body
    assert "转化为普通跟进" in body
    assert "确认已成交" in body
    assert "移除已成交" in body
    assert "一键自动化写话术" in body
    assert "/api/admin/automation-conversion/member" in body
    assert "/api/admin/automation-conversion/member/put-in-pool" in body
    assert "/api/admin/automation-conversion/member/remove-from-pool" in body
    assert "/api/admin/automation-conversion/member/set-focus" in body
    assert "/api/admin/automation-conversion/member/set-normal" in body
    assert "/api/admin/automation-conversion/member/mark-won" in body
    assert "/api/admin/automation-conversion/member/unmark-won" in body
    assert "/api/admin/automation-conversion/member/push-openclaw" in body
    assert "/api/admin/customers/profile/tags" in body
    assert "/api/admin/customers/profile/questionnaire-answers" in body
    assert "const singleCustomerAutomationEnabled = true;" in body
    assert "const legacySidebarCardsEnabled = false;" in body
    assert "自动化转化卡片" not in body
    assert "班期快捷设置" not in body
    assert "/api/sidebar/marketing-status" not in body
    assert "/api/sidebar/lead-pool/status" not in body


def test_sidebar_page_hides_debug_and_uses_customer_display_name(client, app):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            ("wm_ext_sidebar_010", "周青", "sales_01", "老同学介绍", "wm_ext_sidebar_010"),
        )
        db.commit()

    status_response = client.get(
        "/api/sidebar/contact-binding-status",
        query_string={"external_userid": "wm_ext_sidebar_010"},
    )
    assert status_response.status_code == 200
    assert status_response.get_json()["display_name"] == "周青"
    assert status_response.get_json()["owner_userid"] == "sales_01"

    page_response = client.get("/sidebar/bind-mobile")
    body = page_response.get_data(as_text=True)
    assert "当前未识别到客户信息，请从企微客户侧边栏重新打开。" in body
    assert "客户昵称：识别中" in body


def test_sidebar_bind_mobile_fills_missing_owner_from_contacts(client, app):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            ("wm_ext_sidebar_020", "王敏", "sales_09", "渠道客户", "wm_ext_sidebar_020"),
        )
        db.commit()

    bind_response = client.post(
        "/api/sidebar/bind-mobile",
        json={
            "external_userid": "wm_ext_sidebar_020",
            "mobile": "13600003333",
        },
    )
    assert bind_response.status_code == 200
    binding = bind_response.get_json()["binding"]
    assert binding["owner_userid"] == "sales_09"
    assert binding["display_name"] == "王敏"


def test_sidebar_bind_mobile_succeeds_when_third_party_sync_fails(client, app, monkeypatch):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            ("wm_ext_sidebar_030", "赵宁", "sales_10", "直播间", "wm_ext_sidebar_030"),
        )
        db.commit()

    def fail_sync(_: str) -> str:
        raise ThirdPartyUserSyncError("third-party resolver is not configured")

    monkeypatch.setattr(
        "wecom_ability_service.domains.user_ops.service._resolve_third_party_user_id_by_mobile",
        fail_sync,
    )

    response = client.post(
        "/api/sidebar/bind-mobile",
        json={
            "external_userid": "wm_ext_sidebar_030",
            "mobile": "17640055576",
        },
    )
    assert response.status_code == 200
    binding = response.get_json()["binding"]
    assert binding["external_userid"] == "wm_ext_sidebar_030"
    assert binding["mobile"] == "17640055576"
    assert binding["owner_userid"] == "sales_10"
    assert binding["third_party_user_id"] == ""
    assert binding["third_party_sync_status"] == "pending"
    assert binding["third_party_sync_error"] == "third-party resolver is not configured"

    with app.app_context():
        db = get_db()
        person = db.execute("SELECT mobile, third_party_user_id FROM people WHERE mobile = ?", ("17640055576",)).fetchone()
        binding_row = db.execute(
            "SELECT external_userid, person_id, first_owner_userid FROM external_contact_bindings WHERE external_userid = ?",
            ("wm_ext_sidebar_030",),
        ).fetchone()
        assert dict(person) == {"mobile": "17640055576", "third_party_user_id": ""}
        assert binding_row["external_userid"] == "wm_ext_sidebar_030"
        assert binding_row["first_owner_userid"] == "sales_10"


def test_sidebar_bind_mobile_force_rebind_updates_binding(client, app, monkeypatch):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            ("wm_ext_sidebar_040", "林安", "sales_11", "老客户", "wm_ext_sidebar_040"),
        )
        db.commit()

    def fail_sync(_: str) -> str:
        raise ThirdPartyUserSyncError("third-party resolver is not configured")

    monkeypatch.setattr(
        "wecom_ability_service.domains.user_ops.service._resolve_third_party_user_id_by_mobile",
        fail_sync,
    )

    first = client.post(
        "/api/sidebar/bind-mobile",
        json={"external_userid": "wm_ext_sidebar_040", "mobile": "17640050001"},
    )
    assert first.status_code == 200

    second = client.post(
        "/api/sidebar/bind-mobile",
        json={"external_userid": "wm_ext_sidebar_040", "mobile": "17640050002", "force_rebind": True},
    )
    assert second.status_code == 200
    binding = second.get_json()["binding"]
    assert binding["mobile"] == "17640050002"
    assert binding["owner_userid"] == "sales_11"

    with app.app_context():
        db = get_db()
        old_person = db.execute("SELECT mobile FROM people WHERE mobile = ?", ("17640050001",)).fetchone()
        new_person = db.execute("SELECT mobile FROM people WHERE mobile = ?", ("17640050002",)).fetchone()
        binding_row = db.execute(
            "SELECT person_id FROM external_contact_bindings WHERE external_userid = ?",
            ("wm_ext_sidebar_040",),
        ).fetchone()
        assert old_person["mobile"] == "17640050001"
        assert new_person["mobile"] == "17640050002"
        assert binding_row["person_id"] == db.execute(
            "SELECT id FROM people WHERE mobile = ?",
            ("17640050002",),
        ).fetchone()["id"]


def test_identity_resolve_supports_external_userid_and_mobile(client, app):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO signup_tag_rules (tag_id, tag_name, signup_status, active)
            VALUES (?, ?, ?, ?)
            """,
            ("tag-sign-999", "已购999", "signed_999", True),
        )
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            ("wm_ext_identity_001", "周青", "sales_01", "老同学介绍", "wm_ext_identity_001"),
        )
        db.execute(
            """
            INSERT INTO contact_tags (external_userid, userid, tag_id, tag_name, created_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            ("wm_ext_identity_001", "sales_01", "tag-sign-999", "已购999"),
        )
        db.execute(
            """
            INSERT INTO wecom_external_contact_identity_map (
                corp_id, external_userid, unionid, openid, follow_user_userid, name, status, raw_profile
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ww-test",
                "wm_ext_identity_001",
                "union-identity-001",
                "openid-identity-001",
                "sales_follow_01",
                "周青",
                "active",
                json.dumps({"external_userid": "wm_ext_identity_001"}, ensure_ascii=False),
            ),
        )
        db.execute(
            """
            INSERT INTO people (mobile, third_party_user_id, created_at, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            ("13800138000", ""),
        )
        person_id = db.execute("SELECT id FROM people WHERE mobile = ?", ("13800138000",)).fetchone()["id"]
        db.execute(
            """
            INSERT INTO external_contact_bindings (
                external_userid, person_id, first_bound_by_userid, first_owner_userid, last_owner_userid, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            ("wm_ext_identity_001", person_id, "sales_01", "sales_01", "sales_01"),
        )
        db.commit()

    by_external = client.get(
        "/api/identity/resolve",
        query_string={"external_userid": "wm_ext_identity_001"},
    )
    assert by_external.status_code == 200
    external_payload = by_external.get_json()
    assert external_payload["ok"] is True
    assert external_payload["person_id"] == person_id
    assert external_payload["mobile"] == "13800138000"
    assert external_payload["external_userid"] == "wm_ext_identity_001"
    assert external_payload["customer_name"] == "周青"
    assert external_payload["owner_userid"] == "sales_01"
    assert external_payload["remark"] == "老同学介绍"
    assert external_payload["unionid"] == "union-identity-001"
    assert external_payload["openid"] == "openid-identity-001"
    assert external_payload["follow_user_userid"] == "sales_follow_01"
    assert external_payload["signup_status"] == "signed_999"
    assert external_payload["is_bound"] is True

    by_mobile = client.get(
        "/api/identity/resolve",
        query_string={"mobile": "13800138000"},
    )
    assert by_mobile.status_code == 200
    mobile_payload = by_mobile.get_json()
    assert mobile_payload["ok"] is True
    assert mobile_payload["person_id"] == person_id
    assert mobile_payload["mobile"] == "13800138000"
    assert mobile_payload["external_userid"] == "wm_ext_identity_001"
    assert mobile_payload["customer_name"] == "周青"
    assert mobile_payload["owner_userid"] == "sales_01"
    assert mobile_payload["remark"] == "老同学介绍"
    assert mobile_payload["unionid"] == "union-identity-001"
    assert mobile_payload["openid"] == "openid-identity-001"
    assert mobile_payload["follow_user_userid"] == "sales_follow_01"
    assert mobile_payload["signup_status"] == "signed_999"
    assert mobile_payload["is_bound"] is True


def test_identity_resolve_supports_unionid(client, app):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO owner_role_map (userid, display_name, role, active)
            VALUES (?, ?, ?, ?)
            """,
            ("sales_01", "顾问一号", "sales", True),
        )
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            ("wm_ext_union_001", "家恺", "sales_01", "union 反查", "wm_ext_union_001"),
        )
        db.execute(
            """
            INSERT INTO wecom_external_contact_identity_map (
                corp_id, external_userid, unionid, openid, follow_user_userid, name, status, raw_profile
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ww-test",
                "wm_ext_union_001",
                "union-lookup-001",
                "openid-union-001",
                "sales_follow_01",
                "家恺",
                "active",
                json.dumps({"external_userid": "wm_ext_union_001"}, ensure_ascii=False),
            ),
        )
        db.commit()

    response = client.get(
        "/api/identity/resolve",
        query_string={"unionid": "union-lookup-001"},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["person_id"] is None
    assert payload["mobile"] == ""
    assert payload["external_userid"] == "wm_ext_union_001"
    assert payload["customer_name"] == "家恺"
    assert payload["owner_userid"] == "sales_01"
    assert payload["remark"] == "union 反查"
    assert payload["unionid"] == "union-lookup-001"
    assert payload["openid"] == "openid-union-001"
    assert payload["follow_user_userid"] == "sales_follow_01"
    assert payload["is_bound"] is False


def test_identity_resolve_requires_external_userid_mobile_or_unionid(client):
    response = client.get("/api/identity/resolve")
    assert response.status_code == 400
    assert response.get_json() == {"ok": False, "error": "external_userid, mobile or unionid is required"}


def test_customer_center_list_supports_filters(client, app):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO owner_role_map (userid, display_name, role, active)
            VALUES (?, ?, ?, ?)
            """,
            ("sales_01", "顾问一号", "sales", True),
        )
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("wm_customer_001", "客户甲", "sales_01", "重点客户", "wm_customer_001", "2026-03-24 10:00:00"),
        )
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("wm_customer_002", "客户乙", "sales_02", "未绑定", "wm_customer_002", "2026-03-24 09:00:00"),
        )
        db.execute(
            """
            INSERT INTO people (mobile, third_party_user_id, created_at, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            ("13900000001", ""),
        )
        person_id = db.execute("SELECT id FROM people WHERE mobile = ?", ("13900000001",)).fetchone()["id"]
        db.execute(
            """
            INSERT INTO external_contact_bindings (
                external_userid, person_id, first_bound_by_userid, first_owner_userid, last_owner_userid, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            ("wm_customer_001", person_id, "sales_01", "sales_01", "sales_01"),
        )
        db.execute(
            """
            INSERT INTO contact_tags (external_userid, userid, tag_id, tag_name, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("wm_customer_001", "sales_01", "tag-customer-a", "高意向", "2026-03-24 10:00:00"),
        )
        db.execute(
            """
            INSERT INTO class_user_status_current (
                external_userid, signup_status, signup_label_name, customer_name_snapshot, owner_userid_snapshot,
                mobile_snapshot, set_by_userid, set_at, wecom_tag_sync_status, wecom_tag_sync_error, status_flags_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?)
            """,
            ("wm_customer_001", "signed_999", "已报名999", "客户甲", "sales_01", "13900000001", "sales_01", "success", "", "{}"),
        )
        db.execute(
            """
            INSERT INTO wecom_external_contact_identity_map (
                corp_id, external_userid, unionid, openid, follow_user_userid, name, status, raw_profile
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("ww-test", "wm_customer_001", "union-customer-001", "openid-customer-001", "sales_01", "客户甲", "active", "{}"),
        )
        db.commit()

    response = client.get(
        "/api/customers",
        query_string={
            "owner": "sales_01",
            "tag": "高意向",
            "status": "signed_999",
            "is_bound": "true",
            "mobile": "1390",
            "keyword": "客户甲",
        },
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["total"] == 1
    item = payload["items"][0]
    assert item["external_userid"] == "wm_customer_001"
    assert item["customer_name"] == "客户甲"
    assert item["owner_userid"] == "sales_01"
    assert item["owner_display_name"] == "顾问一号"
    assert item["mobile"] == "13900000001"
    assert item["is_bound"] is True
    assert item["signup_status"] == "signed_999"
    assert item["signup_label_name"] == "已报名999"


def test_customers_detail_regression_endpoint_still_works(client, app):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO owner_role_map (userid, display_name, role, active)
            VALUES (?, ?, ?, ?)
            """,
            ("sales_regression", "回归顾问", "sales", True),
        )
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            ("wm_customers_regression_001", "回归客户", "sales_regression", "回归备注", "wm_customers_regression_001"),
        )
        db.commit()

    response = client.get("/api/customers/wm_customers_regression_001")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["customer"]["external_userid"] == "wm_customers_regression_001"
    assert payload["customer"]["customer_name"] == "回归客户"
    assert payload["customer"]["owner_userid"] == "sales_regression"


def test_customer_center_detail_aggregates_sidebar_related_data(client, app):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO owner_role_map (userid, display_name, role, active)
            VALUES (?, ?, ?, ?)
            """,
            ("sales_09", "顾问九号", "sales", True),
        )
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            ("wm_customer_detail_001", "客户详情", "sales_09", "来源朋友圈", "wm_customer_detail_001"),
        )
        db.execute(
            """
            INSERT INTO people (mobile, third_party_user_id, created_at, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            ("13700000009", "tp_9001"),
        )
        person_id = db.execute("SELECT id FROM people WHERE mobile = ?", ("13700000009",)).fetchone()["id"]
        db.execute(
            """
            INSERT INTO external_contact_bindings (
                external_userid, person_id, first_bound_by_userid, first_owner_userid, last_owner_userid, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            ("wm_customer_detail_001", person_id, "sales_09", "sales_09", "sales_09"),
        )
        db.execute(
            """
            INSERT INTO wecom_external_contact_identity_map (
                corp_id, external_userid, unionid, openid, follow_user_userid, name, status, raw_profile
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("ww-test", "wm_customer_detail_001", "union-detail-001", "openid-detail-001", "sales_09", "客户详情", "active", "{}"),
        )
        db.execute(
            """
            INSERT INTO wecom_external_contact_follow_users (
                corp_id, external_userid, user_id, relation_status, is_primary, remark, description, raw_follow_user
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("ww-test", "wm_customer_detail_001", "sales_09", "active", True, "详情备注", "wm_customer_detail_001", "{}"),
        )
        db.execute(
            """
            INSERT INTO contact_tags (external_userid, userid, tag_id, tag_name, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("wm_customer_detail_001", "sales_09", "tag-detail-001", "高净值", "2026-03-24 10:10:00"),
        )
        db.execute(
            """
            INSERT INTO class_user_status_current (
                external_userid, signup_status, signup_label_name, customer_name_snapshot, owner_userid_snapshot,
                mobile_snapshot, set_by_userid, set_at, wecom_tag_sync_status, wecom_tag_sync_error, status_flags_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?)
            """,
            ("wm_customer_detail_001", "lead", "报名引流品", "客户详情", "sales_09", "13700000009", "sales_09", "success", "", "{\"added_wecom\": true}"),
        )
        db.commit()

    response = client.get("/api/customers/wm_customer_detail_001")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    customer = payload["customer"]
    assert customer["external_userid"] == "wm_customer_detail_001"
    assert customer["customer_name"] == "客户详情"
    assert customer["owner_userid"] == "sales_09"
    assert customer["owner_display_name"] == "顾问九号"
    assert customer["mobile"] == "13700000009"
    assert customer["binding"]["is_bound"] is True
    assert customer["binding"]["third_party_user_id"] == "tp_9001"
    assert customer["identity"]["unionid"] == "union-detail-001"
    assert customer["class_status"]["signup_status"] == "lead"
    assert customer["class_status"]["signup_label_name"] == "报名引流品"
    assert customer["sidebar_context"]["signup_tag_status"]["current_signup_status"] == "lead"
    assert customer["tags"][0]["tag_name"] == "高净值"
    assert customer["follow_users"][0]["userid"] == "sales_09"
