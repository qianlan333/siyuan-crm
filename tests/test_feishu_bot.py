from __future__ import annotations

import json

from openclaw_service.feishu.app import create_app
from openclaw_service.feishu.commands import handle_text_command
from openclaw_service.feishu.openclaw_agent import build_feishu_session_id


def test_handle_text_command_context_uses_operator_service() -> None:
    captured: dict = {}

    def fake_context_loader(external_userid: str, **kwargs) -> dict:
        captured["external_userid"] = external_userid
        captured["kwargs"] = kwargs
        return {
            "external_userid": external_userid,
            "customer": {
                "external_userid": external_userid,
                "name": "Alice",
                "status": "active",
                "tags": ["高意向"],
            },
            "recent_messages": [{"id": "m-1"}, {"id": "m-2"}],
            "recent_timeline_events": [{"event_id": "e-1"}],
            "source_status": "live",
            "degraded": False,
            "warnings": [],
        }

    text = handle_text_command("/context wm_ext_001", context_loader=fake_context_loader)

    assert captured["external_userid"] == "wm_ext_001"
    assert captured["kwargs"] == {"recent_message_limit": 10, "timeline_limit": 10}
    assert "客户：Alice" in text
    assert "标签：高意向" in text


def test_handle_text_command_preflight_uses_preflight_runner(monkeypatch) -> None:
    captured: dict = {}

    def fake_preflight_runner(external_userid: str, **kwargs) -> dict:
        captured["external_userid"] = external_userid
        captured.update(kwargs)
        return {
            "ok": True,
            "external_userid": external_userid,
            "source_status": "fallback",
            "degraded": True,
            "warnings": ["timeline fallback in use"],
            "customer_present": True,
            "recent_messages_count": 3,
            "recent_timeline_events_count": 1,
            "error": "",
        }

    text = handle_text_command("/preflight wm_ext_002", preflight_runner=fake_preflight_runner)

    assert captured["external_userid"] == "wm_ext_002"
    assert "Customer Chat Context Preflight" in text
    assert "source_status: fallback" in text


def test_handle_text_command_routes_natural_language_to_crm_router() -> None:
    captured: dict = {}

    def fake_router(text: str, *, context_loader=None) -> str:
        captured["text"] = text
        captured["context_loader"] = context_loader
        return "crm reply"

    text = handle_text_command("看看这个用户 wmb123 什么情况", crm_router=fake_router)

    assert text == "crm reply"
    assert captured["text"] == "看看这个用户 wmb123 什么情况"


def test_build_feishu_session_id_sanitizes_chat_id() -> None:
    assert build_feishu_session_id("oc:chat/001") == "feishu_oc_chat_001"


def test_feishu_event_url_verification() -> None:
    app = create_app({"TESTING": True, "FEISHU_VERIFICATION_TOKEN": "verify-token"})
    client = app.test_client()

    response = client.post(
        "/feishu/events",
        json={"challenge": "abc123", "token": "verify-token", "type": "url_verification"},
    )

    assert response.status_code == 200
    assert response.get_json() == {"challenge": "abc123"}


def test_feishu_event_message_replies(monkeypatch) -> None:
    app = create_app({"TESTING": True, "FEISHU_APP_ID": "cli_xxx", "FEISHU_APP_SECRET": "sec_xxx"})
    client = app.test_client()
    sent: dict = {}

    monkeypatch.setattr(
        "openclaw_service.feishu.app.handle_text_command",
        lambda text, chat_id="": f"reply from openclaw:{chat_id}",
    )

    class FakeClient:
        def send_text_message(self, chat_id: str, text: str) -> dict:
            sent["chat_id"] = chat_id
            sent["text"] = text
            return {"code": 0}

    monkeypatch.setattr(
        "openclaw_service.feishu.app._build_client",
        lambda app: FakeClient(),
    )

    response = client.post(
        "/feishu/events",
        json={
            "schema": "2.0",
            "header": {"event_type": "im.message.receive_v1"},
            "event": {
                "sender": {"sender_type": "user"},
                "message": {
                    "chat_id": "oc_123",
                    "message_type": "text",
                    "content": json.dumps({"text": "/help"}, ensure_ascii=False),
                },
            },
        },
    )

    assert response.status_code == 200
    assert response.get_json() == {"ok": True}
    assert sent == {"chat_id": "oc_123", "text": "reply from openclaw:oc_123"}
