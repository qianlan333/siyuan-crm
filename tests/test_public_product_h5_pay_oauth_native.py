from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from aicrm_next.integration_gateway.wechat_oauth_client import WeChatOAuthClientError
from aicrm_next.main import create_app
from aicrm_next.public_product import h5_wechat_pay


def _client(monkeypatch) -> TestClient:
    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    monkeypatch.setenv("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.setenv("AICRM_NEXT_ACTION_TOKEN_SECRET", "h5-pay-oauth-native-test-secret")
    monkeypatch.setenv("SECRET_KEY", "h5-pay-oauth-native-fallback-secret")
    monkeypatch.setenv("WECHAT_MP_APP_ID", "wx-pay-oauth-app")
    monkeypatch.setenv("WECHAT_MP_APP_SECRET", "pay-oauth-app-secret")
    return TestClient(create_app(), raise_server_exceptions=False, base_url="https://pay.example.test")


def _state(return_url: str = "/pay/demo") -> str:
    now = int(datetime.now(timezone.utc).timestamp())
    return h5_wechat_pay._signed_blob(
        {
            "return_url": return_url,
            "nonce": "native-oauth-test",
            "iat": now,
            "exp": now + h5_wechat_pay.STATE_TTL_SECONDS,
        }
    )


def _cookie_payload(client: TestClient) -> dict:
    cookie = client.cookies.get(h5_wechat_pay.COOKIE_NAME)
    assert cookie
    return h5_wechat_pay._load_signed_blob(cookie)


@pytest.fixture(autouse=True)
def _reset_oauth_client_factory():
    h5_wechat_pay.reset_h5_wechat_pay_oauth_client_factory()
    yield
    h5_wechat_pay.reset_h5_wechat_pay_oauth_client_factory()


def test_h5_pay_oauth_start_preserves_userinfo_scope(monkeypatch) -> None:
    monkeypatch.delenv("WECHAT_PAY_OAUTH_SCOPE", raising=False)
    response = _client(monkeypatch).get(
        "/api/h5/wechat-pay/oauth/start?return_url=/pay/demo",
        follow_redirects=False,
    )

    assert response.status_code == 302
    location = response.headers["location"]
    parsed = urlparse(location)
    query = parse_qs(parsed.query)
    assert query["scope"] == ["snsapi_userinfo"]
    assert query["appid"] == ["wx-pay-oauth-app"]
    assert query["redirect_uri"] == ["https://pay.example.test/api/h5/wechat-pay/oauth/callback"]
    assert query["state"][0]


def test_h5_pay_oauth_callback_uses_native_client_and_sets_cookie(monkeypatch) -> None:
    calls: dict[str, object] = {}

    class FakeOAuthClient:
        def exchange_code(self, *, app_id: str, app_secret: str, code: str):
            calls["exchange"] = {"app_id": app_id, "app_secret": app_secret, "code": code}
            return {"openid": "op_pay_001", "unionid": "un_pay_001", "access_token": "token_should_not_be_cookie"}

        def fetch_userinfo(self, *, access_token: str, openid: str):
            calls["userinfo"] = {"access_token": access_token, "openid": openid}
            return {"openid": "op_pay_001", "unionid": "un_pay_001", "nickname": "支付昵称"}

    h5_wechat_pay.set_h5_wechat_pay_oauth_client_factory(lambda: FakeOAuthClient())
    client = _client(monkeypatch)
    response = client.get(
        f"/api/h5/wechat-pay/oauth/callback?state={_state('/pay/demo')}&code=oauth-code-001",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == "/pay/demo"
    assert h5_wechat_pay.COOKIE_NAME in response.headers["set-cookie"]
    payload = _cookie_payload(client)
    assert payload["openid"] == "op_pay_001"
    assert payload["unionid"] == "un_pay_001"
    assert payload["payer_name"] == "支付昵称"
    assert "access_token" not in payload
    assert calls["exchange"] == {
        "app_id": "wx-pay-oauth-app",
        "app_secret": "pay-oauth-app-secret",
        "code": "oauth-code-001",
    }
    assert calls["userinfo"] == {"access_token": "token_should_not_be_cookie", "openid": "op_pay_001"}


def test_h5_pay_oauth_start_skips_wechat_when_identity_cookie_exists(monkeypatch) -> None:
    class FakeOAuthClient:
        def exchange_code(self, *, app_id: str, app_secret: str, code: str):
            return {"openid": "op_pay_cached", "unionid": "un_pay_cached", "access_token": "token_cached"}

        def fetch_userinfo(self, *, access_token: str, openid: str):
            return {"openid": openid, "unionid": "un_pay_cached", "nickname": "已授权用户"}

    h5_wechat_pay.set_h5_wechat_pay_oauth_client_factory(lambda: FakeOAuthClient())
    client = _client(monkeypatch)
    callback = client.get(
        f"/api/h5/wechat-pay/oauth/callback?state={_state('/pay/demo')}&code=oauth-code-cached",
        follow_redirects=False,
    )
    assert callback.status_code == 302

    response = client.get(
        "/api/h5/wechat-pay/oauth/start?return_url=/pay/demo",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == "/pay/demo"
    assert "open.weixin.qq.com" not in response.headers["location"]


def test_h5_pay_oauth_callback_fetches_userinfo_when_unionid_missing(monkeypatch) -> None:
    class FakeOAuthClient:
        def exchange_code(self, *, app_id: str, app_secret: str, code: str):
            return {"openid": "op_pay_002", "access_token": "token_002"}

        def fetch_userinfo(self, *, access_token: str, openid: str):
            return {"openid": openid, "unionid": "un_from_userinfo", "nickname": "用户信息昵称"}

    h5_wechat_pay.set_h5_wechat_pay_oauth_client_factory(lambda: FakeOAuthClient())
    client = _client(monkeypatch)
    response = client.get(
        f"/api/h5/wechat-pay/oauth/callback?state={_state()}&code=oauth-code-002",
        follow_redirects=False,
    )

    assert response.status_code == 302
    payload = _cookie_payload(client)
    assert payload["openid"] == "op_pay_002"
    assert payload["unionid"] == "un_from_userinfo"
    assert payload["payer_name"] == "用户信息昵称"


def test_h5_pay_oauth_callback_base_scope_does_not_fetch_userinfo(monkeypatch) -> None:
    monkeypatch.setenv("WECHAT_PAY_OAUTH_SCOPE", "snsapi_base")

    class FakeOAuthClient:
        def exchange_code(self, *, app_id: str, app_secret: str, code: str):
            return {"openid": "op_pay_base", "unionid": "un_pay_base", "access_token": "token_base"}

        def fetch_userinfo(self, *, access_token: str, openid: str):
            raise AssertionError("userinfo must not be fetched for snsapi_base")

    h5_wechat_pay.set_h5_wechat_pay_oauth_client_factory(lambda: FakeOAuthClient())
    client = _client(monkeypatch)
    response = client.get(
        f"/api/h5/wechat-pay/oauth/callback?state={_state()}&code=oauth-code-base",
        follow_redirects=False,
    )

    assert response.status_code == 302
    payload = _cookie_payload(client)
    assert payload["openid"] == "op_pay_base"
    assert payload["unionid"] == "un_pay_base"
    assert payload["payer_name"] == ""


def test_h5_pay_oauth_callback_client_error_is_controlled(monkeypatch) -> None:
    raw_code = "raw-sensitive-code"
    raw_secret = "pay-oauth-app-secret"
    raw_token = "sensitive-access-token"

    class FakeOAuthClient:
        def exchange_code(self, *, app_id: str, app_secret: str, code: str):
            raise WeChatOAuthClientError(f"failed with {code} {app_secret} {raw_token}")

    h5_wechat_pay.set_h5_wechat_pay_oauth_client_factory(lambda: FakeOAuthClient())
    response = _client(monkeypatch).get(
        f"/api/h5/wechat-pay/oauth/callback?state={_state()}&code={raw_code}",
        follow_redirects=False,
    )

    body = response.text
    assert response.status_code == 502
    assert response.json()["error"] == "wechat_oauth_failed"
    assert raw_code not in body
    assert raw_secret not in body
    assert raw_token not in body


def test_h5_pay_oauth_callback_wechat_error_payload(monkeypatch) -> None:
    class FakeOAuthClient:
        def exchange_code(self, *, app_id: str, app_secret: str, code: str):
            return {"errcode": 40029, "errmsg": "invalid code"}

    h5_wechat_pay.set_h5_wechat_pay_oauth_client_factory(lambda: FakeOAuthClient())
    response = _client(monkeypatch).get(
        f"/api/h5/wechat-pay/oauth/callback?state={_state()}&code=bad-code",
        follow_redirects=False,
    )

    assert response.status_code == 502
    assert response.json()["error"] == "invalid code"


def test_h5_pay_oauth_callback_missing_openid_does_not_loop_to_checkout(monkeypatch) -> None:
    class FakeOAuthClient:
        def exchange_code(self, *, app_id: str, app_secret: str, code: str):
            return {"access_token": "token_without_openid"}

        def fetch_userinfo(self, *, access_token: str, openid: str):
            raise AssertionError("userinfo cannot be fetched without openid")

    h5_wechat_pay.set_h5_wechat_pay_oauth_client_factory(lambda: FakeOAuthClient())
    response = _client(monkeypatch).get(
        f"/api/h5/wechat-pay/oauth/callback?state={_state('/pay/test-product')}&code=missing-openid",
        follow_redirects=False,
    )

    assert response.status_code == 502
    assert response.json()["error"] == "wechat_oauth_openid_missing"
    assert "location" not in response.headers
    assert h5_wechat_pay.COOKIE_NAME not in response.headers.get("set-cookie", "")


def test_empty_material_checkout_oauth_round_trip_enters_pay_without_auth_loop(monkeypatch) -> None:
    class FakeOAuthClient:
        def exchange_code(self, *, app_id: str, app_secret: str, code: str):
            return {"openid": "op_empty_material", "unionid": "un_empty_material", "access_token": "token_empty_material"}

        def fetch_userinfo(self, *, access_token: str, openid: str):
            return {"openid": openid, "unionid": "un_empty_material", "nickname": "无素材支付用户"}

    h5_wechat_pay.set_h5_wechat_pay_oauth_client_factory(lambda: FakeOAuthClient())
    client = _client(monkeypatch)

    product = client.get("/p/test-product", follow_redirects=False)
    assert product.status_code == 302
    assert product.headers["location"] == "/pay/test-product"

    before_auth = client.get(product.headers["location"], follow_redirects=False)
    assert before_auth.status_code == 200
    assert ">授权登录</a>" in before_auth.text

    start = client.get("/api/h5/wechat-pay/oauth/start?return_url=/pay/test-product", follow_redirects=False)
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    callback = client.get(
        f"/api/h5/wechat-pay/oauth/callback?state={state}&code=empty-material-code",
        follow_redirects=False,
    )
    assert callback.status_code == 302
    assert callback.headers["location"] == "/pay/test-product"
    assert h5_wechat_pay.COOKIE_NAME in callback.headers["set-cookie"]

    after_auth = client.get(callback.headers["location"], follow_redirects=False)
    assert after_auth.status_code == 200
    assert ">授权登录</a>" not in after_auth.text
    assert '<button id="payButton"' in after_auth.text


def test_h5_pay_runtime_has_no_legacy_oauth_helper() -> None:
    source = Path("aicrm_next/public_product/h5_wechat_pay.py").read_text(encoding="utf-8")
    forbidden = [
        "wecom_ability" + "_service.infra." + "wechat_oauth",
        "exchange_wechat_" + "oauth_code",
        "fetch_wechat_" + "userinfo",
        "WeChatOAuth" + "RequestError",
    ]

    for marker in forbidden:
        assert marker not in source
