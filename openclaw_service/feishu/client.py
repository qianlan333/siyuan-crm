from __future__ import annotations

import json
from typing import Any

import requests

from .config import FeishuBotConfig


class FeishuBotClient:
    def __init__(self, config: FeishuBotConfig, *, session: requests.Session | None = None) -> None:
        self.config = config
        self.session = session or requests.Session()

    def get_tenant_access_token(self) -> str:
        response = self.session.post(
            f"{self.config.api_base}/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": self.config.app_id, "app_secret": self.config.app_secret},
            timeout=self.config.request_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 0:
            raise RuntimeError(payload.get("msg") or "failed to get tenant access token")
        token = str(payload.get("tenant_access_token") or "").strip()
        if not token:
            raise RuntimeError("tenant_access_token missing in Feishu auth response")
        return token

    def send_text_message(self, chat_id: str, text: str) -> dict[str, Any]:
        token = self.get_tenant_access_token()
        response = self.session.post(
            f"{self.config.api_base}/open-apis/im/v1/messages",
            params={"receive_id_type": "chat_id"},
            headers={"Authorization": f"Bearer {token}"},
            json={
                "receive_id": chat_id,
                "msg_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            },
            timeout=self.config.request_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 0:
            raise RuntimeError(payload.get("msg") or "failed to send Feishu message")
        return payload
