from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

from wecom_ability_service import create_app
from wecom_ability_service.db import init_db
from wecom_ability_service.domains.admin_auth import save_admin_user


@pytest.fixture()
def app(tmp_path):
    db_path = tmp_path / "admin-mcp-console.sqlite3"
    private_key_path = tmp_path / "wecom_private_key.pem"
    sdk_lib_path = tmp_path / "libWeWorkFinanceSdk_C.so"
    private_key_path.write_text("fake-key", encoding="utf-8")
    sdk_lib_path.write_text("fake-so", encoding="utf-8")

    app = create_app(
        {
            "TESTING": True,
            "DATABASE_PATH": str(db_path),
            "RELEASE_SHA": "release-test-sha",
            "WECOM_CORP_ID": "ww-test",
            "WECOM_CONTACT_SECRET": "contact-secret-test",
            "WECOM_SECRET": "secret-test",
            "WECOM_AGENT_ID": "1000002",
            "WECOM_ARCHIVE_SECRET": "archive-secret",
            "WECOM_API_BASE": "http://fake-wecom.local",
            "WECOM_PRIVATE_KEY_PATH": str(private_key_path),
            "WECOM_SDK_LIB_PATH": str(sdk_lib_path),
            "WECOM_CALLBACK_TOKEN": "callback-token",
            "WECOM_CALLBACK_AES_KEY": "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
            "MCP_BEARER_TOKEN": "mcp-token",
            "SECRET_KEY": "test-secret-key",
        }
    )
    with app.app_context():
        init_db()
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
    assert "企业微信自建应用登录" in html
    assert "自动化运营核心接口" in html
    assert "问卷核心接口" in html
    assert "常见错误码" in html


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
