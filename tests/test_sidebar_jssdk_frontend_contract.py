from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from aicrm_next.main import create_app


TEMPLATE = Path("aicrm_next/frontend_compat/templates/sidebar_customer_workbench.html")
SCRIPT = Path("aicrm_next/frontend_compat/static/sidebar_workbench/sidebar_workbench.js")


def test_frontend_declares_and_consumes_jssdk_config_contract() -> None:
    template = TEMPLATE.read_text(encoding="utf-8")
    script = SCRIPT.read_text(encoding="utf-8")

    assert 'data-jssdk-config-url="/api/sidebar/jssdk-config"' in template
    assert "jssdkConfigUrl()" in script
    assert 'url.searchParams.set("external_userid", state.external_userid)' in script
    assert "applySidebarOwnerToken(configPayload)" in script
    assert '"X-AICRM-Sidebar-Owner-Token": state.sidebar_owner_token' in script
    assert "configPayload.corp_id" in script
    assert "configPayload.agent_id" in script
    assert "configPayload.config.timestamp" in script
    assert "configPayload.config.nonceStr" in script
    assert "configPayload.config.signature" in script
    assert "configPayload.agent_config.signature" in script
    assert "sendChatMessage" in script


def test_frontend_refreshes_owner_token_after_external_userid_resolution() -> None:
    script = SCRIPT.read_text(encoding="utf-8")

    assert "if (!state.owner_userid && !state.external_userid) return false;" in script
    assert "await refreshSidebarOwnerToken();" in script
    assert "if (!state.sidebar_owner_token) {" in script
    assert 'firstQueryValue(["owner_userid", "ownerUserid", "viewer_userid", "viewerUserId", "operator_userid", "operatorUserId", "userid"])' in script
    assert "if (hasQuery && !state.sidebar_owner_token && !state.owner_userid)" in script
    assert "renderOwnerPendingWorkbench(ownerPendingMessage())" not in script
    assert "await loadWorkbench();" in script


def test_sidebar_page_and_jssdk_api_contract_are_compatible(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "sidebar-jssdk-frontend")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    client = TestClient(create_app(), raise_server_exceptions=False)

    page = client.get("/sidebar/bind-mobile")
    api = client.get("/api/sidebar/jssdk-config", params={"url": "http://127.0.0.1:5001/sidebar/bind-mobile"})
    payload = api.json()

    assert page.status_code == 200
    assert "客户侧边栏 V2 工作台" in page.text
    assert "/api/sidebar/jssdk-config" in page.text
    assert api.status_code == 200
    assert payload["corp_id"] == payload["appId"] == payload["corpId"]
    assert payload["agent_id"] == payload["agentId"]
    assert payload["config"]["timestamp"] == payload["timestamp"]
    assert payload["config"]["nonceStr"] == payload["nonceStr"]
    assert payload["config"]["signature"] == payload["signature"]
    assert payload["agent_config"]["signature"]
