from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(slots=True)
class FeishuBotConfig:
    app_id: str
    app_secret: str
    verification_token: str = ""
    api_base: str = "https://open.feishu.cn"
    request_timeout_seconds: float = 10.0
    bot_name: str = "OpenClaw"

    @classmethod
    def from_env(cls) -> "FeishuBotConfig":
        return cls(
            app_id=os.getenv("FEISHU_APP_ID", "").strip(),
            app_secret=os.getenv("FEISHU_APP_SECRET", "").strip(),
            verification_token=os.getenv("FEISHU_VERIFICATION_TOKEN", "").strip(),
            api_base=os.getenv("FEISHU_API_BASE", "https://open.feishu.cn").rstrip("/"),
            request_timeout_seconds=float(os.getenv("FEISHU_REQUEST_TIMEOUT_SECONDS", "10")),
            bot_name=os.getenv("FEISHU_BOT_NAME", "OpenClaw").strip() or "OpenClaw",
        )

    def missing_required(self) -> list[str]:
        missing: list[str] = []
        if not self.app_id:
            missing.append("FEISHU_APP_ID")
        if not self.app_secret:
            missing.append("FEISHU_APP_SECRET")
        return missing
