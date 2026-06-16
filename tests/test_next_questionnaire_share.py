from __future__ import annotations

from urllib.parse import unquote

from fastapi.testclient import TestClient

from aicrm_next.main import create_app


def _client(monkeypatch) -> TestClient:
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("SECRET_KEY", "next-questionnaire-share-test")
    return TestClient(create_app())


def test_questionnaire_share_endpoint_returns_public_link_and_qr(monkeypatch):
    response = _client(monkeypatch).get("/api/admin/questionnaires/1/share")

    assert response.status_code == 200
    share = response.json()["share"]
    assert share["questionnaire_id"] == 1
    assert share["slug"] == "hxc-activation-v1"
    assert share["url"] == "http://testserver/s/hxc-activation-v1"
    assert share["qr_data_url"].startswith("data:image/svg+xml;charset=UTF-8,")
    assert 'xmlns="http://www.w3.org/2000/svg"' in unquote(share["qr_data_url"])


def test_public_api_uses_next_identity_status_and_filters_backend_fields(monkeypatch):
    response = _client(monkeypatch).get("/api/h5/questionnaires/hxc-activation-v1")

    assert response.status_code == 200
    assert "X-AICRM-Compatibility-Facade" not in response.headers
    assert "questionnaire_h5_identity=" in response.headers.get("set-cookie", "")
    body = response.json()
    assert body["source_status"] == "local_contract_probe"
    assert body["route_owner"] == "ai_crm_next"
    assert body["fallback_used"] is False
    assert body["questionnaire"]["slug"] == "hxc-activation-v1"
    assert "sidebar_profile_field" not in response.text


def test_public_api_returns_already_submitted_for_query_identity(monkeypatch):
    response = _client(monkeypatch).get(
        "/api/h5/questionnaires/hxc-activation-v1",
        params={"external_userid": "external_user_masked_fixture"},
    )

    assert response.status_code == 409
    assert "X-AICRM-Compatibility-Facade" not in response.headers
    assert response.json()["error"] == "already_submitted"
    assert response.json()["redirect_url"] == "/s/hxc-activation-v1/submitted"


def test_public_page_sets_anonymous_identity_and_redirects_after_submit(monkeypatch):
    client = _client(monkeypatch)
    first_page = client.get("/s/hxc-activation-v1", follow_redirects=False)

    assert first_page.status_code == 200
    assert "questionnaire_h5_identity=" in first_page.headers.get("set-cookie", "")
    assert "name=\"respondent_key\"" in first_page.text
    assert "黄小璨激活问卷" in first_page.text

    submit = client.post("/api/h5/questionnaires/hxc-activation-v1/submit", json={"answers": {"q_activation": "activated"}})
    assert submit.status_code == 200, submit.text

    second_api = client.get("/api/h5/questionnaires/hxc-activation-v1")
    assert second_api.status_code == 409
    assert second_api.json()["error"] == "already_submitted"

    second_page = client.get("/s/hxc-activation-v1", follow_redirects=False)
    assert second_page.status_code == 302
    assert second_page.headers["location"] == "/s/hxc-activation-v1/submitted"


def test_wechat_browser_without_authorized_identity_shows_auth_gate(monkeypatch):
    response = _client(monkeypatch).get(
        "/s/hxc-activation-v1",
        headers={"User-Agent": "Mozilla/5.0 MicroMessenger"},
    )

    assert response.status_code == 200
    assert "认证成功后即可填写并提交问卷" in response.text
    assert "/api/h5/wechat/oauth/start?" in response.text
    assert "questionnaire_h5_identity=" in response.headers.get("set-cookie", "")


def test_wechat_browser_with_query_identity_can_open_questionnaire(monkeypatch):
    response = _client(monkeypatch).get(
        "/s/hxc-activation-v1",
        params={"openid": "openid-next-public-001"},
        headers={"User-Agent": "Mozilla/5.0 MicroMessenger"},
    )

    assert response.status_code == 200
    assert "认证成功后即可填写并提交问卷" not in response.text
    assert "黄小璨激活问卷" in response.text
    assert "name=\"openid\" value=\"openid-next-public-001\"" in response.text


def test_public_page_redirects_local_already_submitted_identity(monkeypatch):
    response = _client(monkeypatch).get(
        "/s/hxc-activation-v1",
        params={"external_userid": "external_user_masked_fixture"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "X-AICRM-Compatibility-Facade" not in response.headers
    assert response.headers["location"] == "/s/hxc-activation-v1/submitted"


def test_public_read_disabled_and_missing_slug_return_404(monkeypatch):
    client = _client(monkeypatch)

    disabled = client.get("/api/h5/questionnaires/disabled-demo")
    missing = client.get("/api/h5/questionnaires/missing-slug")

    assert disabled.status_code == 404
    assert missing.status_code == 404


def test_questionnaire_admin_page_renders_share_modal(monkeypatch):
    response = _client(monkeypatch).get("/admin/questionnaires")

    assert response.status_code == 200
    html = response.text
    assert 'id="questionnaire-share-modal"' in html
    assert "问卷链接" in html
    assert "问卷二维码" in html
    assert "保存二维码" in html
    assert "/api/admin/questionnaires/${item.id}/share" in html
