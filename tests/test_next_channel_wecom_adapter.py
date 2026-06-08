from __future__ import annotations

import pytest

from aicrm_next.channel_entry.wecom_adapter import (
    ProductionWeComAdapter,
    WeComAdapterBlocked,
    get_wecom_adapter,
    set_wecom_adapter,
    wecom_adapter_diagnostics,
)


class _Response:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return dict(self._payload)


def test_get_wecom_adapter_enables_production_adapter_only_with_flag_and_config(monkeypatch):
    monkeypatch.setenv("AICRM_NEXT_WECOM_REAL_CALLS_ENABLED", "true")
    monkeypatch.setenv("WECOM_CORP_ID", "ww-test")
    monkeypatch.setenv("WECOM_CONTACT_SECRET", "secret")
    set_wecom_adapter(None)
    try:
        adapter = get_wecom_adapter()
        diagnosis = wecom_adapter_diagnostics()
    finally:
        set_wecom_adapter(None)

    assert isinstance(adapter, ProductionWeComAdapter)
    assert diagnosis["real_wecom_adapter_enabled"] is True
    assert diagnosis["can_send_welcome"] is True
    assert diagnosis["can_mark_tag"] is True
    assert diagnosis["can_create_contact_way"] is True


def test_get_wecom_adapter_blocks_when_flag_disabled_or_config_missing(monkeypatch):
    monkeypatch.delenv("AICRM_NEXT_WECOM_REAL_CALLS_ENABLED", raising=False)
    monkeypatch.setenv("WECOM_CORP_ID", "ww-test")
    monkeypatch.setenv("WECOM_CONTACT_SECRET", "secret")
    set_wecom_adapter(None)
    try:
        with pytest.raises(WeComAdapterBlocked) as disabled:
            get_wecom_adapter().send_welcome_msg({"welcome_code": "wc"})
        disabled_diagnosis = wecom_adapter_diagnostics()

        monkeypatch.setenv("AICRM_NEXT_WECOM_REAL_CALLS_ENABLED", "true")
        monkeypatch.delenv("WECOM_CONTACT_SECRET", raising=False)
        monkeypatch.delenv("WECOM_SECRET", raising=False)
        with pytest.raises(WeComAdapterBlocked) as missing:
            get_wecom_adapter().create_contact_way({"state": "aqr"})
        missing_diagnosis = wecom_adapter_diagnostics()
    finally:
        set_wecom_adapter(None)

    assert disabled.value.reason == "wecom_real_calls_disabled"
    assert disabled_diagnosis["real_wecom_adapter_reason"] == "wecom_real_calls_disabled"
    assert missing.value.reason == "missing_wecom_config"
    assert missing_diagnosis["missing_config"] == ["WECOM_CONTACT_SECRET"]


def test_production_wecom_adapter_contract_posts_real_wecom_endpoints(monkeypatch):
    calls: list[dict] = []

    def fake_request(method, url, **kwargs):
        calls.append({"method": method, "url": url, **kwargs})
        if url.endswith("/cgi-bin/gettoken"):
            return _Response({"errcode": 0, "access_token": "token", "expires_in": 7200})
        if url.endswith("/cgi-bin/externalcontact/add_contact_way"):
            return _Response({"errcode": 0, "config_id": "cfg", "qr_code": "https://qr"})
        return _Response({"errcode": 0, "errmsg": "ok"})

    monkeypatch.setattr("aicrm_next.channel_entry.wecom_adapter.requests.request", fake_request)

    adapter = ProductionWeComAdapter(corp_id="ww-test", secret="secret", api_base="https://qyapi.weixin.qq.com")
    welcome = adapter.send_welcome_msg({"welcome_code": "wc", "text": {"content": "hi"}})
    tag = adapter.mark_external_contact_tags(external_userid="wm", follow_user_userid="owner", add_tags=["tag"], remove_tags=[])
    qrcode = adapter.create_contact_way({"state": "aqr", "user": ["owner"]})
    detail = adapter.get_external_contact_detail("wm")

    assert welcome["errcode"] == 0
    assert tag["errcode"] == 0
    assert qrcode["config_id"] == "cfg"
    assert detail["errcode"] == 0
    assert [call["url"].split("qyapi.weixin.qq.com", 1)[1].split("?", 1)[0] for call in calls] == [
        "/cgi-bin/gettoken",
        "/cgi-bin/externalcontact/send_welcome_msg",
        "/cgi-bin/externalcontact/mark_tag",
        "/cgi-bin/externalcontact/add_contact_way",
        "/cgi-bin/externalcontact/get",
    ]
    assert calls[2]["json"] == {"userid": "owner", "external_userid": "wm", "add_tag": ["tag"]}
