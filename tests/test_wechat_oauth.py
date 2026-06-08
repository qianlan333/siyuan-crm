from __future__ import annotations

import json

from wecom_ability_service.infra import wechat_oauth


class _FakeResponse:
    status_code = 200

    def __init__(self, payload: dict):
        self.content = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def raise_for_status(self):
        return None

    def json(self):
        return {"nickname": "æ›¾å¾·é’§", "openid": "wrong-decoder"}


class _FakeClient:
    def __init__(self, payload: dict):
        self.payload = payload

    def get(self, url: str, **kwargs):
        return _FakeResponse(self.payload)


def test_fetch_wechat_userinfo_decodes_utf8_bytes(monkeypatch):
    monkeypatch.setattr(
        wechat_oauth,
        "_client",
        lambda timeout: _FakeClient({"openid": "op_test", "nickname": "曾德钧"}),
    )

    payload = wechat_oauth.fetch_wechat_userinfo(access_token="token", openid="op_test")

    assert payload["openid"] == "op_test"
    assert payload["nickname"] == "曾德钧"


def test_exchange_wechat_oauth_code_decodes_utf8_bytes(monkeypatch):
    monkeypatch.setattr(
        wechat_oauth,
        "_client",
        lambda timeout: _FakeClient({"openid": "op_test", "scope": "snsapi_userinfo"}),
    )

    payload = wechat_oauth.exchange_wechat_oauth_code(app_id="wx-app", app_secret="secret", code="code")

    assert payload == {"openid": "op_test", "scope": "snsapi_userinfo"}
