from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .navigation import admin_path_for, nav_items


@dataclass(frozen=True)
class AdminShellApiClient:
    active_endpoint: str = ""

    def shell_status(self) -> dict[str, Any]:
        return {
            "environment": {"tone": "prod", "label": "AI-CRM Next"},
            "health": {"state": "ok", "label": "OK", "detail": "next_admin_shell"},
            "release_sha": "unknown",
        }

    def dashboard_cards(self) -> list[dict[str, Any]]:
        return [
            {
                "label": "客户",
                "value": "postgres",
                "description": "客户列表走生产 PostgreSQL。",
                "href": admin_path_for("api.admin_console_customers"),
            },
            {
                "label": "自动化运营",
                "value": "postgres",
                "description": "自动化运营页优先使用生产数据。",
                "href": admin_path_for("api.admin_automation_conversion"),
            },
        ]

    def shell_context_payload(self) -> dict[str, Any]:
        shell_status = self.shell_status()
        navigation = nav_items(self.active_endpoint)
        return {
            "ok": True,
            "source_status": "next_admin_shell",
            "fallback_used": False,
            "real_external_call_executed": False,
            "environment": shell_status["environment"],
            "health": shell_status["health"],
            "shell_status": shell_status,
            "navigation": navigation,
            "nav_groups": navigation,
            "dashboard_cards": self.dashboard_cards(),
            "loading_state": {"enabled": True, "label": "加载后台导航"},
            "empty_state": {"title": "暂无后台事项", "body": "当前没有需要优先处理的问题。"},
            "error_state": {"title": "后台壳加载失败", "body": "请刷新页面或联系管理员。"},
        }
