from __future__ import annotations

import json

from flask import Flask, jsonify, request

from .client import FeishuBotClient
from .commands import handle_text_command
from .config import FeishuBotConfig


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)
    config = FeishuBotConfig.from_env()
    app.config.from_mapping(
        FEISHU_APP_ID=config.app_id,
        FEISHU_APP_SECRET=config.app_secret,
        FEISHU_VERIFICATION_TOKEN=config.verification_token,
        FEISHU_API_BASE=config.api_base,
        FEISHU_REQUEST_TIMEOUT_SECONDS=config.request_timeout_seconds,
        FEISHU_BOT_NAME=config.bot_name,
    )
    if test_config:
        app.config.update(test_config)

    @app.get("/health")
    def health():
        return jsonify({"ok": True, "service": "openclaw-feishu-bot"})

    @app.post("/feishu/events")
    def feishu_events():
        payload = request.get_json(silent=True) or {}

        challenge = payload.get("challenge")
        if challenge:
            if not _verify_token(app, payload):
                return jsonify({"code": 403, "msg": "invalid verification token"}), 403
            return jsonify({"challenge": challenge})

        event = payload.get("event") or {}
        message = event.get("message") or {}
        sender = event.get("sender") or {}
        header = payload.get("header") or {}
        event_type = header.get("event_type") or payload.get("type") or ""

        if event_type != "im.message.receive_v1":
            return jsonify({"ok": True, "ignored": True, "reason": "unsupported event"})

        if message.get("message_type") != "text":
            return jsonify({"ok": True, "ignored": True, "reason": "unsupported message type"})

        if str(sender.get("sender_type") or "").lower() == "app":
            return jsonify({"ok": True, "ignored": True, "reason": "self message"})

        chat_id = str(message.get("chat_id") or "").strip()
        if not chat_id:
            return jsonify({"ok": False, "error": "missing chat_id"}), 400

        text = _extract_text(message.get("content"))
        reply_text = handle_text_command(text, chat_id=chat_id)
        client = _build_client(app)
        client.send_text_message(chat_id, reply_text)
        return jsonify({"ok": True})

    return app


def _verify_token(app: Flask, payload: dict) -> bool:
    expected = str(app.config.get("FEISHU_VERIFICATION_TOKEN") or "").strip()
    if not expected:
        return True
    actual = str(payload.get("token") or "").strip()
    return actual == expected


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


def _build_client(app: Flask) -> FeishuBotClient:
    config = FeishuBotConfig(
        app_id=str(app.config.get("FEISHU_APP_ID") or "").strip(),
        app_secret=str(app.config.get("FEISHU_APP_SECRET") or "").strip(),
        verification_token=str(app.config.get("FEISHU_VERIFICATION_TOKEN") or "").strip(),
        api_base=str(app.config.get("FEISHU_API_BASE") or "https://open.feishu.cn").rstrip("/"),
        request_timeout_seconds=float(app.config.get("FEISHU_REQUEST_TIMEOUT_SECONDS") or 10),
        bot_name=str(app.config.get("FEISHU_BOT_NAME") or "OpenClaw").strip() or "OpenClaw",
    )
    missing = config.missing_required()
    if missing:
        raise RuntimeError(f"missing required env: {', '.join(missing)}")
    return FeishuBotClient(config)
