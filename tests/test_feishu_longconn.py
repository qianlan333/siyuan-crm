from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from openclaw_service.feishu.longconn import handle_bot_p2p_chat_entered_event, handle_im_message_event


class FakeBotClient:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    def send_text_message(self, chat_id: str, text: str) -> dict:
        self.sent.append({"chat_id": chat_id, "text": text})
        return {"code": 0}


def test_longconn_event_replies_to_text_message(monkeypatch) -> None:
    bot = FakeBotClient()
    monkeypatch.setattr(
        "openclaw_service.feishu.longconn.handle_text_command",
        lambda text, chat_id="": f"reply:{text}:{chat_id}",
    )
    payload = SimpleNamespace(
        event=SimpleNamespace(
            sender=SimpleNamespace(sender_type="user"),
            message=SimpleNamespace(
                message_type="text",
                chat_id="oc_123",
                content=json.dumps({"text": "/help"}, ensure_ascii=False),
            ),
        )
    )

    result = handle_im_message_event(payload, bot_client=bot)

    assert result == "reply:/help:oc_123"
    assert bot.sent == [{"chat_id": "oc_123", "text": "reply:/help:oc_123"}]


def test_longconn_event_ignores_app_sender() -> None:
    bot = FakeBotClient()
    payload = SimpleNamespace(
        event=SimpleNamespace(
            sender=SimpleNamespace(sender_type="app"),
            message=SimpleNamespace(
                message_type="text",
                chat_id="oc_123",
                content=json.dumps({"text": "/help"}, ensure_ascii=False),
            ),
        )
    )

    result = handle_im_message_event(payload, bot_client=bot)

    assert result == "ignored:self message"
    assert bot.sent == []


def test_longconn_event_rejects_missing_chat_id() -> None:
    bot = FakeBotClient()
    payload = SimpleNamespace(
        event=SimpleNamespace(
            sender=SimpleNamespace(sender_type="user"),
            message=SimpleNamespace(
                message_type="text",
                chat_id="",
                content=json.dumps({"text": "/help"}, ensure_ascii=False),
            ),
        )
    )

    with pytest.raises(ValueError, match="missing chat_id"):
        handle_im_message_event(payload, bot_client=bot)


def test_longconn_p2p_entered_event_sends_help_reply(monkeypatch) -> None:
    bot = FakeBotClient()
    monkeypatch.setattr(
        "openclaw_service.feishu.longconn.handle_text_command",
        lambda text, chat_id="": f"reply:{text}:{chat_id}",
    )
    payload = SimpleNamespace(
        event=SimpleNamespace(
            chat_id="oc_456",
        )
    )

    result = handle_bot_p2p_chat_entered_event(payload, bot_client=bot)

    assert result == "reply:/help:oc_456"
    assert bot.sent == [{"chat_id": "oc_456", "text": "reply:/help:oc_456"}]
