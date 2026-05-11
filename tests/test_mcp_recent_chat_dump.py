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
    return app.test_client()


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


def _insert_contact(app, *, external_userid: str, customer_name: str, owner_userid: str) -> None:
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (external_userid, customer_name, owner_userid, "", external_userid),
        )
        db.commit()


def _insert_group_chat(app, *, chat_id: str, group_name: str, owner_userid: str) -> None:
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO group_chats (chat_id, group_name, owner_userid, raw_payload)
            VALUES (?, ?, ?, ?)
            """,
            (chat_id, group_name, owner_userid, json.dumps({"group_chat": {"chat_id": chat_id, "name": group_name}}, ensure_ascii=False)),
        )
        db.commit()


def _insert_archived_message(
    app,
    *,
    seq: int,
    msgid: str,
    chat_type: str,
    external_userid: str,
    owner_userid: str,
    sender: str,
    receiver: str,
    content: str,
    send_time: str,
    roomid: str = "",
    tolist: list[str] | None = None,
) -> None:
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO archived_messages
            (seq, msgid, chat_type, external_userid, owner_userid, sender, receiver, msgtype, content, send_time, raw_payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                seq,
                msgid,
                chat_type,
                external_userid,
                owner_userid,
                sender,
                receiver,
                "text",
                content,
                send_time,
                json.dumps(
                    {
                        "decrypted_message": {
                            "from": sender,
                            "tolist": tolist or [receiver],
                            "roomid": roomid,
                            "msgtype": "text",
                        }
                    },
                    ensure_ascii=False,
                ),
            ),
        )
        db.commit()


def _ts(minutes_ago: int) -> str:
    return (datetime.now() - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%d %H:%M:%S")


def test_get_owner_recent_chat_dump_groups_private_messages_by_external_userid(client, app):
    _insert_contact(app, external_userid="wm_private_001", customer_name="老方", owner_userid="ZhaoYanFang")
    _insert_archived_message(
        app,
        seq=1,
        msgid="private-msg-001",
        chat_type="private",
        external_userid="wm_private_001",
        owner_userid="ZhaoYanFang",
        sender="wm_private_001",
        receiver="ZhaoYanFang",
        content="老师你好",
        send_time=_ts(20),
    )
    _insert_archived_message(
        app,
        seq=2,
        msgid="private-msg-002",
        chat_type="private",
        external_userid="wm_private_001",
        owner_userid="ZhaoYanFang",
        sender="ZhaoYanFang",
        receiver="wm_private_001",
        content="收到，我来跟进",
        send_time=_ts(10),
    )

    response = _mcp_call(
        client,
        "get_owner_recent_chat_dump",
        {"owner_userid": "ZhaoYanFang", "lookback_minutes": 60},
    )

    payload = response.get_json()["result"]["structuredContent"]
    assert response.status_code == 200
    assert payload["owner_userid"] == "ZhaoYanFang"
    assert payload["group_conversations"] == []
    assert len(payload["private_conversations"]) == 1
    conversation = payload["private_conversations"][0]
    assert conversation["external_userid"] == "wm_private_001"
    assert conversation["customer_name"] == "老方"
    assert [item["sender_role"] for item in conversation["messages"]] == ["customer", "staff"]
    assert [item["content"] for item in conversation["messages"]] == ["老师你好", "收到，我来跟进"]


def test_get_owner_recent_chat_dump_groups_group_messages_by_roomid(client, app):
    _insert_contact(app, external_userid="wm_group_001", customer_name="客户甲", owner_userid="ZhaoYanFang")
    _insert_group_chat(app, chat_id="chat-001", group_name="转化测试群", owner_userid="ZhaoYanFang")
    _insert_archived_message(
        app,
        seq=1,
        msgid="group-msg-001",
        chat_type="group",
        external_userid="wm_group_001",
        owner_userid="ZhaoYanFang",
        sender="wm_group_001",
        receiver="ZhaoYanFang,wm_group_001",
        content="群里问一下",
        send_time=_ts(25),
        roomid="chat-001",
        tolist=["ZhaoYanFang", "wm_group_001"],
    )
    _insert_archived_message(
        app,
        seq=2,
        msgid="group-msg-002",
        chat_type="group",
        external_userid="wm_group_001",
        owner_userid="ZhaoYanFang",
        sender="ZhaoYanFang",
        receiver="ZhaoYanFang,wm_group_001",
        content="群里回复一下",
        send_time=_ts(5),
        roomid="chat-001",
        tolist=["ZhaoYanFang", "wm_group_001"],
    )

    response = _mcp_call(
        client,
        "get_owner_recent_chat_dump",
        {"owner_userid": "ZhaoYanFang", "lookback_minutes": 60},
    )

    payload = response.get_json()["result"]["structuredContent"]
    assert response.status_code == 200
    assert len(payload["group_conversations"]) == 1
    conversation = payload["group_conversations"][0]
    assert conversation["roomid"] == "chat-001"
    assert conversation["chat_id"] == "chat-001"
    assert conversation["group_name"] == "转化测试群"
    assert [item["sender_role"] for item in conversation["messages"]] == ["customer", "staff"]
    assert [item["external_userid"] for item in conversation["messages"]] == ["wm_group_001", "wm_group_001"]


def test_get_owner_recent_chat_dump_filters_by_owner_userid(client, app):
    _insert_contact(app, external_userid="wm_owner_a", customer_name="顾问A客户", owner_userid="ZhaoYanFang")
    _insert_contact(app, external_userid="wm_owner_b", customer_name="顾问B客户", owner_userid="QianLan")
    _insert_archived_message(
        app,
        seq=1,
        msgid="owner-a-msg-001",
        chat_type="private",
        external_userid="wm_owner_a",
        owner_userid="ZhaoYanFang",
        sender="wm_owner_a",
        receiver="ZhaoYanFang",
        content="只属于赵顾问",
        send_time=_ts(15),
    )
    _insert_archived_message(
        app,
        seq=2,
        msgid="owner-b-msg-001",
        chat_type="private",
        external_userid="wm_owner_b",
        owner_userid="QianLan",
        sender="wm_owner_b",
        receiver="QianLan",
        content="不该混进来",
        send_time=_ts(15),
    )

    response = _mcp_call(client, "get_owner_recent_chat_dump", {"owner_userid": "ZhaoYanFang"})

    payload = response.get_json()["result"]["structuredContent"]
    external_userids = [item["external_userid"] for item in payload["private_conversations"]]
    assert external_userids == ["wm_owner_a"]


def test_get_owner_recent_chat_dump_respects_lookback_minutes(client, app):
    _insert_contact(app, external_userid="wm_window_001", customer_name="窗口客户", owner_userid="ZhaoYanFang")
    _insert_archived_message(
        app,
        seq=1,
        msgid="window-msg-001",
        chat_type="private",
        external_userid="wm_window_001",
        owner_userid="ZhaoYanFang",
        sender="wm_window_001",
        receiver="ZhaoYanFang",
        content="窗口内消息",
        send_time=_ts(30),
    )
    _insert_archived_message(
        app,
        seq=2,
        msgid="window-msg-002",
        chat_type="private",
        external_userid="wm_window_001",
        owner_userid="ZhaoYanFang",
        sender="wm_window_001",
        receiver="ZhaoYanFang",
        content="窗口外消息",
        send_time=_ts(120),
    )

    response = _mcp_call(
        client,
        "get_owner_recent_chat_dump",
        {"owner_userid": "ZhaoYanFang", "lookback_minutes": 60},
    )

    payload = response.get_json()["result"]["structuredContent"]
    messages = payload["private_conversations"][0]["messages"]
    assert len(messages) == 1
    assert messages[0]["content"] == "窗口内消息"


def test_get_owner_recent_chat_dump_respects_private_and_group_switches(client, app):
    _insert_contact(app, external_userid="wm_mix_001", customer_name="混合客户", owner_userid="ZhaoYanFang")
    _insert_group_chat(app, chat_id="chat-mix-001", group_name="混合群", owner_userid="ZhaoYanFang")
    _insert_archived_message(
        app,
        seq=1,
        msgid="mix-private-001",
        chat_type="private",
        external_userid="wm_mix_001",
        owner_userid="ZhaoYanFang",
        sender="wm_mix_001",
        receiver="ZhaoYanFang",
        content="私聊消息",
        send_time=_ts(12),
    )
    _insert_archived_message(
        app,
        seq=2,
        msgid="mix-group-001",
        chat_type="group",
        external_userid="wm_mix_001",
        owner_userid="ZhaoYanFang",
        sender="wm_mix_001",
        receiver="ZhaoYanFang,wm_mix_001",
        content="群聊消息",
        send_time=_ts(8),
        roomid="chat-mix-001",
        tolist=["ZhaoYanFang", "wm_mix_001"],
    )

    private_only = _mcp_call(
        client,
        "get_owner_recent_chat_dump",
        {"owner_userid": "ZhaoYanFang", "include_group": False},
    ).get_json()["result"]["structuredContent"]
    group_only = _mcp_call(
        client,
        "get_owner_recent_chat_dump",
        {"owner_userid": "ZhaoYanFang", "include_private": False},
    ).get_json()["result"]["structuredContent"]

    assert len(private_only["private_conversations"]) == 1
    assert private_only["group_conversations"] == []
    assert group_only["private_conversations"] == []
    assert len(group_only["group_conversations"]) == 1
