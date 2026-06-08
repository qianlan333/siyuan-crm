from __future__ import annotations

from pathlib import Path


def test_sidebar_jssdk_inventory_covers_frontend_api_backend_contract() -> None:
    inventory = Path("docs/architecture/sidebar_jssdk_route_inventory.md").read_text(encoding="utf-8")

    for marker in [
        "Frontend ↔ API ↔ Backend Contract Matrix",
        "/sidebar/bind-mobile",
        "sidebar_customer_workbench.html",
        "sidebar_workbench.js",
        "/api/sidebar/jssdk-config",
        "url",
        "debug",
        "agentid",
        "ok",
        "appId",
        "corpId",
        "timestamp",
        "nonceStr",
        "signature",
        "jsApiList",
        "source_status",
        "adapter_mode",
        "route_owner",
        "fallback_used",
        "real_external_call_executed",
        "fake",
        "sandbox",
        "real_blocked",
        "real_enabled",
        "page smoke",
        "API smoke",
    ]:
        assert marker in inventory
