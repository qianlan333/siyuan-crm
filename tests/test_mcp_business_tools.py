from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from wecom_ability_service import create_app
from wecom_ability_service.db import get_db, init_db
from wecom_ability_service.domains.automation_conversion import create_conversion_profile_segment_template


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http error: {self.status_code}")


@pytest.fixture()
def app(tmp_path):
    db_path = tmp_path / "mcp-business.sqlite3"
    private_key_path = tmp_path / "wecom_private_key.pem"
    sdk_lib_path = tmp_path / "libWeWorkFinanceSdk_C.so"
    private_key_path.write_text("fake-key", encoding="utf-8")
    sdk_lib_path.write_text("fake-so", encoding="utf-8")

    app = create_app(
        {
            "TESTING": True,
            "DATABASE_PATH": str(db_path),
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
    yield app


@pytest.fixture()
def client(app):
    return app.test_client()


def fake_wecom_get(url, params=None, timeout=None):
    if url.endswith("/cgi-bin/gettoken"):
        return FakeResponse({"errcode": 0, "errmsg": "ok", "access_token": "token-123", "expires_in": 7200})
    raise AssertionError(f"unexpected GET url: {url}")


def fake_wecom_post(url, params=None, json=None, timeout=None):
    if url.endswith("/cgi-bin/externalcontact/add_msg_template"):
        return FakeResponse({"errcode": 0, "errmsg": "ok", "msgid": "task-msg-001"})
    if url.endswith("/cgi-bin/externalcontact/add_moment_task"):
        return FakeResponse({"errcode": 0, "errmsg": "ok", "jobid": "moment-job-001"})
    if url.endswith("/cgi-bin/externalcontact/mark_tag"):
        return FakeResponse({"errcode": 0, "errmsg": "ok"})
    raise AssertionError(f"unexpected POST url: {url}")


def _insert_customer(
    app,
    *,
    external_userid: str,
    mobile: str,
    customer_name: str,
    owner_userid: str,
    signup_status: str = "lead",
    signup_label_name: str = "报名引流品",
    tags: list[tuple[str, str]] | None = None,
    messages: list[tuple[str, str, str]] | None = None,
):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT OR IGNORE INTO owner_role_map (userid, display_name, role, active)
            VALUES (?, ?, ?, ?)
            """,
            (owner_userid, owner_userid, "sales", 1),
        )
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (external_userid, customer_name, owner_userid, f"{customer_name}来源", external_userid),
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
        for index, (tag_id, tag_name) in enumerate(tags or [], start=1):
            db.execute(
                """
                INSERT INTO contact_tags (external_userid, userid, tag_id, tag_name, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (external_userid, owner_userid, tag_id, tag_name, f"2026-03-25 10:00:0{index}"),
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


def _mcp_rpc(client, method: str, params: dict | None = None):
    return client.post(
        "/mcp",
        headers={"Authorization": "Bearer mcp-token"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params or {},
        },
    )


def _mcp_call(client, name: str, arguments: dict):
    return _mcp_rpc(client, "tools/call", {"name": name, "arguments": arguments})


def _seed_settings_questionnaire(app, *, questionnaire_id: int = 901) -> dict[str, object]:
    choice_question_id = questionnaire_id * 100 + 1
    mobile_question_id = questionnaire_id * 100 + 2
    option_ids = [questionnaire_id * 1000 + 1, questionnaire_id * 1000 + 2]
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO questionnaires (
                id, slug, name, title, description, is_disabled, redirect_url, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, '', 0, '', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                questionnaire_id,
                f"mcp-settings-{questionnaire_id}",
                f"mcp-settings-{questionnaire_id}",
                f"MCP 自动化设置问卷 {questionnaire_id}",
            ),
        )
        db.execute(
            """
            INSERT INTO questionnaire_questions (
                id, questionnaire_id, type, title, required, sort_order, created_at, updated_at
            )
            VALUES (?, ?, 'single_choice', '你当前更关注什么？', 1, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
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
        db.execute(
            """
            INSERT INTO questionnaire_questions (
                id, questionnaire_id, type, title, required, sort_order, created_at, updated_at
            )
            VALUES (?, ?, 'mobile', '请填写手机号', 1, 2, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (mobile_question_id, questionnaire_id),
        )
        db.commit()
    return {
        "questionnaire_id": questionnaire_id,
        "choice_question_id": choice_question_id,
        "option_ids": option_ids,
        "mobile_question_id": mobile_question_id,
    }


def _seed_profile_segment_template(app, *, questionnaire_id: int = 901, template_name: str = "MCP 画像模板") -> dict[str, object]:
    questionnaire_seed = _seed_settings_questionnaire(app, questionnaire_id=questionnaire_id)
    with app.app_context():
        result = create_conversion_profile_segment_template(
            {
                "template_name": template_name,
                "questionnaire_id": questionnaire_seed["questionnaire_id"],
                "segmentation_question_id": questionnaire_seed["choice_question_id"],
                "categories": [
                    {
                        "category_key": "efficiency",
                        "category_name": "效率型",
                        "option_ids": [questionnaire_seed["option_ids"][0]],
                    },
                    {
                        "category_key": "closing",
                        "category_name": "成交型",
                        "option_ids": [questionnaire_seed["option_ids"][1]],
                    },
                ],
            },
            operator_id="tester-mcp",
        )
    return {
        **questionnaire_seed,
        "template_id": int(((result.get("template_bundle") or {}).get("template") or {}).get("id") or 0),
    }


def _seed_test_agent_config(app, *, agent_code: str, display_name: str = "") -> None:
    with app.app_context():
        get_db().execute(
            """
            INSERT INTO automation_agent_config (
                agent_code,
                display_name,
                pool_keys_json,
                enabled,
                draft_role_prompt,
                draft_task_prompt,
                draft_variables_json,
                draft_output_schema_json,
                published_role_prompt,
                published_task_prompt,
                published_variables_json,
                published_output_schema_json,
                draft_version,
                published_version,
                last_change_summary,
                created_at,
                updated_at
            )
            VALUES (?, ?, '[]', 1, '', '', '[]', '[]', '', '', '[]', '[]', 1, 1, '', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(agent_code) DO UPDATE SET
                display_name = excluded.display_name,
                enabled = 1,
                published_version = MAX(automation_agent_config.published_version, 1),
                updated_at = CURRENT_TIMESTAMP
            """,
            (agent_code, display_name or agent_code),
        )
        get_db().commit()


class _FakeRefreshTagsClient:
    def __init__(self, details: dict[str, dict[str, object]]):
        self._details = details

    def get_contact(self, external_userid: str) -> dict[str, object]:
        assert external_userid in self._details
        return dict(self._details[external_userid])


def test_mcp_initialize_returns_protocol_schema(client):
    response = _mcp_rpc(client, "initialize")

    payload = response.get_json()["result"]
    assert response.status_code == 200
    assert payload["protocolVersion"] == "2025-03-26"
    assert payload["capabilities"]["tools"]["listChanged"] is False
    assert payload["serverInfo"]["name"] == "openclaw-wecom-mcp"


def test_mcp_tools_list_returns_enabled_runtime_tools(client):
    response = _mcp_rpc(client, "tools/list")

    payload = response.get_json()["result"]
    tool_names = {item["name"] for item in payload["tools"]}
    assert response.status_code == 200
    assert "resolve_customer" in tool_names
    assert "get_customer_context" in tool_names


def test_resolve_customer_returns_available_actions(client, app):
    _insert_customer(
        app,
        external_userid="wm_resolve_001",
        mobile="13800138066",
        customer_name="解析客户",
        owner_userid="sales_09",
    )

    response = _mcp_call(
        client,
        "resolve_customer",
        {"customer_ref": "13800138066"},
    )

    payload = response.get_json()["result"]["structuredContent"]
    assert payload["ok"] is True
    assert payload["external_userid"] == "wm_resolve_001"
    assert payload["matched_by"] == "mobile"
    assert "get_customer_context" in payload["available_actions"]
    assert "send_pool_private_message" in payload["available_actions"]


def test_create_private_message_task_resolves_mobile_then_executes(client, app, monkeypatch):
    monkeypatch.setattr("requests.get", fake_wecom_get)
    monkeypatch.setattr("requests.post", fake_wecom_post)
    _insert_customer(
        app,
        external_userid="wm_private_001",
        mobile="13800138000",
        customer_name="私信客户",
        owner_userid="sales_01",
    )

    response = _mcp_call(
        client,
        "create_private_message_task",
        {"customer_ref": "13800138000", "content": "你好，来跟进一下", "dry_run": False, "confirm": True},
    )

    payload = response.get_json()["result"]["structuredContent"]
    assert payload["ok"] is True
    assert payload["external_userid"] == "wm_private_001"
    assert payload["userid"] == "sales_01"
    assert payload["wecom_result"]["msgid"] == "task-msg-001"

    with app.app_context():
        row = get_db().execute(
            "SELECT request_payload FROM outbound_tasks WHERE task_type = 'private_message' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        request_payload = json.loads(row["request_payload"])
        assert request_payload["chat_type"] == "single"
        assert request_payload["external_userid"] == ["wm_private_001"]
        assert request_payload["sender"] == "sales_01"
        assert request_payload["text"]["content"] == "你好，来跟进一下"


def test_create_group_message_task_supports_customer_ref_list(client, app, monkeypatch):
    monkeypatch.setattr("requests.get", fake_wecom_get)
    monkeypatch.setattr("requests.post", fake_wecom_post)
    _insert_customer(
        app,
        external_userid="wm_group_001",
        mobile="13800138001",
        customer_name="群发客户一",
        owner_userid="sales_01",
    )
    _insert_customer(
        app,
        external_userid="wm_group_002",
        mobile="13800138002",
        customer_name="群发客户二",
        owner_userid="sales_01",
    )

    response = _mcp_call(
        client,
        "create_group_message_task",
        {
            "customer_refs": ["13800138001", "wm_group_002"],
            "content": "今晚八点直播提醒",
            "dry_run": False,
            "confirm": True,
        },
    )

    payload = response.get_json()["result"]["structuredContent"]
    assert payload["ok"] is True
    assert payload["external_userids"] == ["wm_group_001", "wm_group_002"]
    assert payload["userid"] == "sales_01"

    with app.app_context():
        row = get_db().execute(
            "SELECT request_payload FROM outbound_tasks WHERE task_type = 'group_message' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        request_payload = json.loads(row["request_payload"])
        assert request_payload["chat_type"] == "group"
        assert request_payload["external_userid"] == ["wm_group_001", "wm_group_002"]
        assert request_payload["sender"] == ["sales_01"]
        assert request_payload["text"]["content"] == "今晚八点直播提醒"


def test_create_moment_task_supports_customer_ref_list(client, app, monkeypatch):
    monkeypatch.setattr("requests.get", fake_wecom_get)
    monkeypatch.setattr("requests.post", fake_wecom_post)
    _insert_customer(
        app,
        external_userid="wm_moment_001",
        mobile="13800138003",
        customer_name="朋友圈客户一",
        owner_userid="sales_01",
    )
    _insert_customer(
        app,
        external_userid="wm_moment_002",
        mobile="13800138004",
        customer_name="朋友圈客户二",
        owner_userid="sales_02",
    )

    response = _mcp_call(
        client,
        "create_moment_task",
        {
            "customer_refs": ["13800138003", "13800138004"],
            "content": "今天有新活动说明",
            "dry_run": False,
            "confirm": True,
        },
    )

    payload = response.get_json()["result"]["structuredContent"]
    assert payload["ok"] is True
    assert payload["external_userids"] == ["wm_moment_001", "wm_moment_002"]
    assert payload["userids"] == ["sales_01", "sales_02"]
    assert payload["wecom_result"]["jobid"] == "moment-job-001"

    with app.app_context():
        row = get_db().execute(
            "SELECT request_payload FROM outbound_tasks WHERE task_type = 'moment' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        request_payload = json.loads(row["request_payload"])
        assert request_payload["visible_range"]["sender_list"]["userid"] == ["sales_01", "sales_02"]
        assert request_payload["text"]["content"] == "今天有新活动说明"


def test_get_hourly_followup_candidates_returns_ranked_payload(client, app, monkeypatch):
    monkeypatch.setattr("requests.get", fake_wecom_get)
    monkeypatch.setattr("requests.post", fake_wecom_post)
    now = datetime.now()
    recent_customer_time = (now - timedelta(minutes=20)).strftime("%Y-%m-%d %H:%M:%S")
    recent_reply_time = (now - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
    older_customer_time = (now - timedelta(hours=4)).strftime("%Y-%m-%d %H:%M:%S")

    _insert_customer(
        app,
        external_userid="wm_followup_001",
        mobile="13800138005",
        customer_name="高意向客户",
        owner_userid="sales_01",
        signup_status="lead",
        signup_label_name="报名引流品",
        tags=[("tag-001", "高意向")],
        messages=[
            ("sales_01", "我先发资料给你", recent_reply_time),
            ("wm_followup_001", "可以，麻烦发我", recent_customer_time),
        ],
    )
    _insert_customer(
        app,
        external_userid="wm_followup_002",
        mobile="13800138006",
        customer_name="普通客户",
        owner_userid="sales_02",
        signup_status="lead",
        signup_label_name="报名引流品",
        messages=[
            ("wm_followup_002", "有空再联系", older_customer_time),
        ],
    )

    response = _mcp_call(
        client,
        "get_hourly_followup_candidates",
        {"limit": 5, "lookback_hours": 24},
    )

    payload = response.get_json()["result"]["structuredContent"]
    assert payload["ok"] is True
    assert payload["limit"] == 5
    assert payload["lookback_hours"] == 24
    assert len(payload["candidates"]) >= 1
    first = payload["candidates"][0]
    assert first["rank"] == 1
    assert first["external_userid"] == "wm_followup_001"
    assert first["customer_name"] == "高意向客户"
    assert first["reason"]
    assert first["suggested_action"] in {"contact_now", "review_context"}
    assert first["last_message_at"]
    assert "高意向" in first["tags"]
    assert first["class_user_status"]["signup_status"] == "lead"


def test_task_returns_clear_error_when_mobile_cannot_be_resolved(client, monkeypatch):
    monkeypatch.setattr("requests.get", fake_wecom_get)
    monkeypatch.setattr("requests.post", fake_wecom_post)

    response = _mcp_call(
        client,
        "create_private_message_task",
        {"customer_ref": "13999999999", "content": "你好"},
    )

    payload = response.get_json()
    assert "error" in payload
    assert payload["error"]["message"] == "customer not found for mobile: 13999999999"


def test_get_customer_context_supports_legacy_timeline_signature(client, app, monkeypatch):
    _insert_customer(
        app,
        external_userid="wm_context_001",
        mobile="13800138007",
        customer_name="上下文客户",
        owner_userid="sales_03",
        messages=[
            ("wm_context_001", "你好", "2026-03-25 09:00:00"),
            ("sales_03", "你好，欢迎咨询", "2026-03-25 09:05:00"),
        ],
    )

    def fake_legacy_timeline(external_userid):
        assert external_userid == "wm_context_001"
        return {
            "external_userid": external_userid,
            "items": [
                {"event_id": "evt-1", "event_type": "message", "event_time": "2026-03-25 09:00:00"},
                {"event_id": "evt-2", "event_type": "message", "event_time": "2026-03-25 08:59:00"},
            ],
            "total": 2,
        }

    monkeypatch.setattr("wecom_ability_service.application.integration_gateway.mcp_dispatch.get_customer_timeline", fake_legacy_timeline)

    response = _mcp_call(
        client,
        "get_customer_context",
        {"customer_ref": "13800138007", "recent_message_limit": 5, "timeline_limit": 1},
    )

    payload = response.get_json()["result"]["structuredContent"]
    assert payload["ok"] is True
    assert payload["customer"]["customer_name"] == "上下文客户"
    assert len(payload["recent_messages"]) == 2
    assert len(payload["recent_timeline_events"]) == 1
    assert payload["timeline"]["count"] == 1
    assert payload["degraded"] is False
    assert payload["warnings"]


def test_get_customer_context_refresh_tags_false_keeps_existing_snapshot(client, app, monkeypatch):
    _insert_customer(
        app,
        external_userid="wm_context_tags_001",
        mobile="13800138120",
        customer_name="标签上下文客户",
        owner_userid="sales_21",
        tags=[("tag-old", "旧快照标签")],
    )

    fake_client = _FakeRefreshTagsClient(
        {
            "wm_context_tags_001": {
                "external_contact": {"external_userid": "wm_context_tags_001", "name": "标签上下文客户"},
                "follow_user": [
                    {
                        "userid": "sales_21",
                        "tags": [{"id": "tag-new", "name": "新实时标签"}],
                    }
                ],
            }
        }
    )
    monkeypatch.setattr("wecom_ability_service.services._user_ops_contact_client", lambda: fake_client)

    response = _mcp_call(
        client,
        "get_customer_context",
        {"customer_ref": "13800138120", "refresh_tags": False},
    )

    payload = response.get_json()["result"]["structuredContent"]
    assert payload["ok"] is True
    assert payload["refresh_tags"] is False
    assert [tag["tag_id"] for tag in payload["customer"]["tags"]] == ["tag-old"]


def test_get_customer_context_refresh_tags_true_returns_refreshed_tags(client, app, monkeypatch):
    _insert_customer(
        app,
        external_userid="wm_context_tags_002",
        mobile="13800138121",
        customer_name="标签刷新客户",
        owner_userid="sales_22",
        tags=[("tag-old", "旧快照标签")],
    )

    fake_client = _FakeRefreshTagsClient(
        {
            "wm_context_tags_002": {
                "external_contact": {"external_userid": "wm_context_tags_002", "name": "标签刷新客户"},
                "follow_user": [
                    {
                        "userid": "sales_22",
                        "tags": [
                            {"id": "tag-new-1", "name": "新实时标签1"},
                            {"id": "tag-new-2", "name": "新实时标签2"},
                        ],
                    }
                ],
            }
        }
    )
    monkeypatch.setattr("wecom_ability_service.services._user_ops_contact_client", lambda: fake_client)

    response = _mcp_call(
        client,
        "get_customer_context",
        {"customer_ref": "13800138121", "refresh_tags": True},
    )

    payload = response.get_json()["result"]["structuredContent"]
    assert payload["ok"] is True
    assert payload["refresh_tags"] is True
    assert [tag["tag_id"] for tag in payload["customer"]["tags"]] == ["tag-new-1", "tag-new-2"]


def test_get_contact_refresh_tags_true_returns_refreshed_tags(client, app, monkeypatch):
    _insert_customer(
        app,
        external_userid="wm_contact_tags_001",
        mobile="13800138122",
        customer_name="联系人标签客户",
        owner_userid="sales_23",
        tags=[("tag-old", "旧快照标签")],
    )

    fake_client = _FakeRefreshTagsClient(
        {
            "wm_contact_tags_001": {
                "external_contact": {"external_userid": "wm_contact_tags_001", "name": "联系人标签客户"},
                "follow_user": [
                    {
                        "userid": "sales_23",
                        "tags": [{"id": "tag-contact-new", "name": "联系人新标签"}],
                    }
                ],
            }
        }
    )
    monkeypatch.setattr("wecom_ability_service.services._user_ops_contact_client", lambda: fake_client)

    response = _mcp_call(
        client,
        "get_contact",
        {"customer_ref": "13800138122", "refresh_tags": True},
    )

    payload = response.get_json()["result"]["structuredContent"]
    assert payload["external_userid"] == "wm_contact_tags_001"
    assert [tag["tag_id"] for tag in payload["tags"]] == ["tag-contact-new"]


def test_create_private_message_task_defaults_to_dry_run(client, app, monkeypatch):
    monkeypatch.setattr("requests.get", fake_wecom_get)
    monkeypatch.setattr("requests.post", fake_wecom_post)
    _insert_customer(
        app,
        external_userid="wm_private_preview",
        mobile="13800138100",
        customer_name="私信预览客户",
        owner_userid="sales_11",
    )

    response = _mcp_call(
        client,
        "create_private_message_task",
        {"customer_ref": "13800138100", "content": "预览一下"},
    )

    payload = response.get_json()["result"]["structuredContent"]
    assert payload["ok"] is True
    assert payload["dry_run"] is True
    assert payload["would_execute"] is True
    assert payload["task_type"] == "private_message"
    assert payload["resolved_customer"]["external_userid"] == "wm_private_preview"
    assert payload["resolved_external_userids"] == ["wm_private_preview"]
    assert payload["resolved_owner_userids"] == ["sales_11"]
    assert payload["preview_payload"]["text"]["content"] == "预览一下"

    with app.app_context():
        row = get_db().execute("SELECT COUNT(*) AS total FROM outbound_tasks").fetchone()
        assert row["total"] == 0


def test_create_group_message_task_defaults_to_dry_run(client, app, monkeypatch):
    monkeypatch.setattr("requests.get", fake_wecom_get)
    monkeypatch.setattr("requests.post", fake_wecom_post)
    _insert_customer(
        app,
        external_userid="wm_group_preview_001",
        mobile="13800138101",
        customer_name="群发预览客户一",
        owner_userid="sales_12",
    )
    _insert_customer(
        app,
        external_userid="wm_group_preview_002",
        mobile="13800138102",
        customer_name="群发预览客户二",
        owner_userid="sales_12",
    )

    response = _mcp_call(
        client,
        "create_group_message_task",
        {"customer_refs": ["13800138101", "13800138102"], "content": "预览群发"},
    )

    payload = response.get_json()["result"]["structuredContent"]
    assert payload["ok"] is True
    assert payload["dry_run"] is True
    assert payload["would_execute"] is True
    assert payload["task_type"] == "group_message"
    assert payload["resolved_external_userids"] == ["wm_group_preview_001", "wm_group_preview_002"]
    assert payload["resolved_owner_userids"] == ["sales_12"]
    assert payload["preview_payload"]["external_userid"] == ["wm_group_preview_001", "wm_group_preview_002"]


def test_create_moment_task_defaults_to_dry_run(client, app, monkeypatch):
    monkeypatch.setattr("requests.get", fake_wecom_get)
    monkeypatch.setattr("requests.post", fake_wecom_post)
    _insert_customer(
        app,
        external_userid="wm_moment_preview_001",
        mobile="13800138103",
        customer_name="朋友圈预览客户一",
        owner_userid="sales_13",
    )
    _insert_customer(
        app,
        external_userid="wm_moment_preview_002",
        mobile="13800138104",
        customer_name="朋友圈预览客户二",
        owner_userid="sales_14",
    )

    response = _mcp_call(
        client,
        "create_moment_task",
        {"customer_refs": ["13800138103", "13800138104"], "content": "预览朋友圈"},
    )

    payload = response.get_json()["result"]["structuredContent"]
    assert payload["ok"] is True
    assert payload["dry_run"] is True
    assert payload["would_execute"] is True
    assert payload["task_type"] == "moment"
    assert payload["resolved_external_userids"] == ["wm_moment_preview_001", "wm_moment_preview_002"]
    assert payload["resolved_owner_userids"] == ["sales_13", "sales_14"]
    assert payload["preview_payload"]["visible_range"]["sender_list"]["userid"] == ["sales_13", "sales_14"]


def test_task_requires_confirm_when_dry_run_is_false(client, app, monkeypatch):
    monkeypatch.setattr("requests.get", fake_wecom_get)
    monkeypatch.setattr("requests.post", fake_wecom_post)
    _insert_customer(
        app,
        external_userid="wm_confirm_001",
        mobile="13800138105",
        customer_name="确认客户",
        owner_userid="sales_15",
    )

    response = _mcp_call(
        client,
        "create_private_message_task",
        {"customer_ref": "13800138105", "content": "真的发", "dry_run": False},
    )

    payload = response.get_json()
    assert payload["error"]["message"] == "confirm=true is required when dry_run=false"


def test_crm_automation_workflow_tools_can_list_and_create_workflows_and_nodes(client):
    _seed_test_agent_config(client.application, agent_code="questionnaire_followup_agent", display_name="问卷提交 Agent")
    registry_response = _mcp_call(client, "crm.automation.get_workflow_registry", {})
    registry_payload = registry_response.get_json()["result"]["structuredContent"]
    assert registry_payload["audiences"]
    assert registry_payload["recipient_filter_bases"]
    assert registry_payload["generation_modes"]
    assert registry_payload["node_trigger_modes"]

    empty_list_response = _mcp_call(client, "crm.automation.list_workflows", {})
    empty_list_payload = empty_list_response.get_json()["result"]["structuredContent"]
    assert empty_list_payload["total"] == 0
    assert empty_list_payload["items"] == []

    create_workflow_response = _mcp_call(
        client,
        "crm.automation.create_workflow",
        {
            "workflow_name": "新客欢迎流",
            "workflow_code": "welcome_flow",
            "description": "给运营池新客的欢迎任务流",
            "status": "draft",
            "segmentation_basis": "none",
            "generation_mode": "personalized_single",
            "audiences": ["operating"],
            "agent_bindings": [
                {
                    "binding_scope": "personalized",
                    "segment_key": "",
                    "agent_code": "questionnaire_followup_agent",
                }
            ],
            "operator": "tester-workflow",
        },
    )
    workflow_bundle = create_workflow_response.get_json()["result"]["structuredContent"]["workflow_bundle"]
    workflow_id = workflow_bundle["workflow"]["id"]
    assert workflow_bundle["workflow"]["workflow_code"] == "welcome_flow"
    assert workflow_bundle["workflow"]["workflow_name"] == "新客欢迎流"
    assert workflow_bundle["workflow"]["recipient_filter_basis"] == "none"
    assert workflow_bundle["workflow"]["recipient_behavior_tier_keys"] == []
    assert workflow_bundle["workflow"]["content_segmentation_basis"] == "none"
    assert workflow_bundle["workflow"]["content_profile_segment_template_id"] is None
    assert workflow_bundle["nodes"] == []

    create_node_response = _mcp_call(
        client,
        "crm.automation.create_workflow_node",
        {
            "workflow_id": workflow_id,
            "node_name": "欢迎首触达",
            "node_code": "welcome_touch_1",
            "target_audience_code": "operating",
            "trigger_mode": "audience_entered",
            "operator": "tester-workflow",
        },
    )
    node_payload = create_node_response.get_json()["result"]["structuredContent"]["node"]
    assert node_payload["node_code"] == "welcome_touch_1"
    assert node_payload["node_name"] == "欢迎首触达"
    assert node_payload["target_audience_code"] == "operating"
    assert node_payload["content_mode"] == "personalized_single"

    nodes_response = _mcp_call(
        client,
        "crm.automation.get_workflow_nodes",
        {"workflow_id": workflow_id},
    )
    nodes_payload = nodes_response.get_json()["result"]["structuredContent"]
    assert nodes_payload["total"] == 1
    assert nodes_payload["items"][0]["node_code"] == "welcome_touch_1"

    list_response = _mcp_call(client, "crm.automation.list_workflows", {"status": "draft"})
    list_payload = list_response.get_json()["result"]["structuredContent"]
    assert list_payload["total"] == 1
    assert list_payload["items"][0]["workflow"]["workflow_code"] == "welcome_flow"
    assert list_payload["items"][0]["nodes"][0]["node_code"] == "welcome_touch_1"


def test_crm_automation_create_workflow_supports_split_recipient_and_content_fields(client, app):
    template_seed = _seed_profile_segment_template(app, questionnaire_id=902, template_name="MCP 拆维画像模板")
    _seed_test_agent_config(app, agent_code="efficiency_agent", display_name="效率 Agent")
    _seed_test_agent_config(app, agent_code="closing_agent", display_name="成交 Agent")

    response = _mcp_call(
        client,
        "crm.automation.create_workflow",
        {
            "workflow_name": "拆维欢迎流",
            "workflow_code": "split_flow",
            "status": "draft",
            "recipient_filter_basis": "behavior",
            "recipient_behavior_tier_keys": ["lt_2"],
            "content_segmentation_basis": "profile",
            "content_profile_segment_template_id": template_seed["template_id"],
            "generation_mode": "auto_layered_rewrite",
            "audiences": ["operating"],
            "agent_bindings": [
                {"binding_scope": "profile_category", "segment_key": "efficiency", "agent_code": "efficiency_agent"},
                {"binding_scope": "profile_category", "segment_key": "closing", "agent_code": "closing_agent"},
            ],
            "operator": "tester-workflow",
        },
    )

    payload = response.get_json()["result"]["structuredContent"]["workflow_bundle"]
    workflow = payload["workflow"]
    assert workflow["workflow_code"] == "split_flow"
    assert workflow["recipient_filter_basis"] == "behavior"
    assert workflow["recipient_behavior_tier_keys"] == ["lt_2"]
    assert workflow["content_segmentation_basis"] == "profile"
    assert workflow["content_profile_segment_template_id"] == template_seed["template_id"]
    assert workflow["segmentation_basis"] == "profile"
    assert workflow["profile_segment_template_id"] == template_seed["template_id"]
    assert json.loads(workflow["behavior_tier_scheme"]) == {
        "recipient_filter_basis": "behavior",
        "recipient_behavior_tier_keys": ["lt_2"],
    }

    list_response = _mcp_call(client, "crm.automation.list_workflows", {"status": "draft"})
    list_payload = list_response.get_json()["result"]["structuredContent"]
    saved_workflow = next(item["workflow"] for item in list_payload["items"] if item["workflow"]["workflow_code"] == "split_flow")
    assert saved_workflow["recipient_filter_basis"] == "behavior"
    assert saved_workflow["recipient_behavior_tier_keys"] == ["lt_2"]
    assert saved_workflow["content_segmentation_basis"] == "profile"
    assert saved_workflow["content_profile_segment_template_id"] == template_seed["template_id"]


def test_crm_automation_create_workflow_keeps_legacy_segmentation_basis_payload_compatible(client):
    _seed_test_agent_config(client.application, agent_code="tier_lt_2_agent", display_name="小于 2 Agent")
    _seed_test_agent_config(client.application, agent_code="tier_2_9_agent", display_name="2~9 Agent")
    _seed_test_agent_config(client.application, agent_code="tier_gte_10_agent", display_name="10+ Agent")
    response = _mcp_call(
        client,
        "crm.automation.create_workflow",
        {
            "workflow_name": "旧写法行为流",
            "workflow_code": "legacy_behavior_flow",
            "status": "draft",
            "segmentation_basis": "behavior",
            "generation_mode": "auto_layered_rewrite",
            "audiences": ["operating"],
            "agent_bindings": [
                {"binding_scope": "behavior_tier", "segment_key": "lt_2", "agent_code": "tier_lt_2_agent"},
                {"binding_scope": "behavior_tier", "segment_key": "between_2_9", "agent_code": "tier_2_9_agent"},
                {"binding_scope": "behavior_tier", "segment_key": "gte_10", "agent_code": "tier_gte_10_agent"},
            ],
            "operator": "tester-workflow",
        },
    )

    workflow = response.get_json()["result"]["structuredContent"]["workflow_bundle"]["workflow"]
    assert workflow["workflow_code"] == "legacy_behavior_flow"
    assert workflow["recipient_filter_basis"] == "none"
    assert workflow["recipient_behavior_tier_keys"] == []
    assert workflow["content_segmentation_basis"] == "behavior"
    assert workflow["content_profile_segment_template_id"] is None
    assert workflow["segmentation_basis"] == "behavior"
    assert workflow["behavior_tier_scheme"] == "fixed_v1"
