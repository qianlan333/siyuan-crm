from __future__ import annotations

import json
import logging
from typing import Any, Protocol

from .client import FeishuBotClient
from .commands import handle_text_command
from .config import FeishuBotConfig

logger = logging.getLogger("openclaw.feishu")


class SupportsSendText(Protocol):
    def send_text_message(self, chat_id: str, text: str) -> dict[str, Any]:
        ...


def create_ws_client(
    *,
    config: FeishuBotConfig | None = None,
    bot_client: SupportsSendText | None = None,
) -> Any:
    import lark_oapi as lark

    config = config or FeishuBotConfig.from_env()
    missing = config.missing_required()
    if missing:
        raise RuntimeError(f"missing required env: {', '.join(missing)}")

    sender = bot_client or FeishuBotClient(config)
    event_handler = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_chat_access_event_bot_p2p_chat_entered_v1(
            lambda data: handle_bot_p2p_chat_entered_event(data, bot_client=sender)
        )
        .register_p2_im_message_receive_v1(lambda data: handle_im_message_event(data, bot_client=sender))
        .build()
    )
    return lark.ws.Client(
        config.app_id,
        config.app_secret,
        event_handler=event_handler,
        log_level=lark.LogLevel.INFO,
    )


def run_ws_client(
    *,
    config: FeishuBotConfig | None = None,
    bot_client: SupportsSendText | None = None,
) -> None:
    client = create_ws_client(config=config, bot_client=bot_client)
    client.start()


def handle_im_message_event(
    data: Any,
    *,
    bot_client: SupportsSendText,
) -> str:
    event = getattr(data, "event", None)
    if event is None:
        raise ValueError("missing event payload")

    sender = getattr(event, "sender", None)
    if str(getattr(sender, "sender_type", "") or "").lower() == "app":
        return "ignored:self message"

    message = getattr(event, "message", None)
    if message is None:
        raise ValueError("missing message payload")

    if str(getattr(message, "message_type", "") or "").lower() != "text":
        return "ignored:unsupported message type"

    chat_id = str(getattr(message, "chat_id", "") or "").strip()
    if not chat_id:
        raise ValueError("missing chat_id")

    text = _extract_text(getattr(message, "content", None))
    logger.info("feishu text message received chat_id=%s text=%s", chat_id, text[:200])
    reply_text = handle_text_command(text, chat_id=chat_id)
    bot_client.send_text_message(chat_id, reply_text)
    logger.info("feishu text message replied chat_id=%s chars=%s", chat_id, len(reply_text))
    return reply_text


def handle_bot_p2p_chat_entered_event(
    data: Any,
    *,
    bot_client: SupportsSendText,
) -> str:
    event = getattr(data, "event", None)
    if event is None:
        raise ValueError("missing event payload")

    chat_id = str(getattr(event, "chat_id", "") or "").strip()
    if not chat_id:
        raise ValueError("missing chat_id")

    reply_text = handle_text_command("/help", chat_id=chat_id)
    bot_client.send_text_message(chat_id, reply_text)
    logger.info("feishu p2p entered replied chat_id=%s chars=%s", chat_id, len(reply_text))
    return reply_text


def _extract_text(content: object) -> str:
    if isinstance(content, str):
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            return content.strip()
        return str(payload.get("text") or "").strip()
    if isinstance(content, dict):
        return str(content.get("text") or "").strip()
    return ""
