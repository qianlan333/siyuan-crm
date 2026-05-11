from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

from wecom_ability_service.domains.admin_auth import save_admin_user


@pytest.fixture()
def app(tmp_path):
    from tests.conftest import build_pg_test_app

    with build_pg_test_app(
        tmp_path,
        MCP_BEARER_TOKEN="mcp-token",
        SECRET_KEY="test-secret-key",
    ) as app:
        save_admin_user(
            {
                "wecom_userid": "root.admin",
                "display_name": "Root Admin",
                "wecom_corpid": "ww-test",
                "role_codes": ["super_admin"],
                "is_active": "1",
            },
            operator="test-suite",
        )
        yield app


@pytest.fixture()
def client(app):
    return app.test_client()


def _login(client, monkeypatch):
    start = client.get("/auth/wecom/start?mode=qr&next=/admin/api-docs", follow_redirects=False)
    state = parse_qs(urlparse(start.headers["Location"]).query)["state"][0]
    monkeypatch.setattr(
        "wecom_ability_service.http.internal_auth.exchange_code_for_wecom_user",
        lambda code: {
            "wecom_userid": "root.admin",
            "display_name": "Root Admin",
            "wecom_corpid": "ww-test",
            "raw_identity": {"UserId": "root.admin"},
        },
    )
    callback = client.get(f"/auth/wecom/callback?code=mock-code&state={state}", follow_redirects=False)
    assert callback.status_code == 302


def test_admin_mcp_console_redirects_to_api_docs(client):
    response = client.get("/admin/mcp")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/api-docs")


def test_admin_api_docs_page_renders_human_readable_sections(client, monkeypatch):
    _login(client, monkeypatch)
    response = client.get("/admin/api-docs")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "API 文档" in html
    assert "认证" in html
    assert "自动化运营" in html
    assert "问卷" in html
    assert "错误码" in html


def test_admin_mcp_preflight_redirects_to_api_docs(client):
    response = client.post("/admin/mcp/preflight", data={"operator": "tester-mcp"})

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/api-docs")


def test_admin_mcp_sample_call_redirects_to_api_docs(client):
    response = client.post(
        "/admin/mcp/sample-call",
        data={
            "tool_name": "create_private_message_task",
            "operator": "tester-live",
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/api-docs")
