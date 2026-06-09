from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.automation_engine import channels_api
from aicrm_next.main import create_app


def _client(monkeypatch) -> TestClient:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("SECRET_KEY", "qrcode-download-consistency")
    channels_api._FIXTURE_CHANNELS.clear()
    channels_api._FIXTURE_PROGRAM_BINDINGS.clear()
    channels_api._NEXT_ID = 1
    channels_api._NEXT_BINDING_ID = 1
    return TestClient(create_app(), raise_server_exceptions=False)


def test_un_generated_qrcode_channel_cannot_download_old_url(monkeypatch):
    client = _client(monkeypatch)
    channel = client.post("/api/admin/channels", json={"channel_name": "未生成二维码", "channel_code": "fake_scene"}).json()["channel"]

    response = client.get(f"/api/admin/channels/{channel['id']}/qrcode/download", follow_redirects=False)

    assert response.status_code == 409
    assert response.json()["reason"] == "qrcode_not_generated"


def test_download_returns_attachment_for_current_active_asset(monkeypatch):
    client = _client(monkeypatch)
    channel = client.post("/api/admin/channels", json={"channel_name": "已生成二维码", "channel_code": "signup"}).json()["channel"]
    channel_id = int(channel["id"])
    channels_api._FIXTURE_CHANNELS[channel_id]["scene_value"] = "aqr_current"
    channels_api._FIXTURE_CHANNELS[channel_id]["qr_url"] = "https://wework.qpic.cn/current"
    channels_api._FIXTURE_CHANNELS[channel_id]["_active_qrcode_asset"] = {
        "id": 9,
        "channel_id": channel_id,
        "scene_value": "aqr_current",
        "qr_url": "https://wework.qpic.cn/current",
        "status": "active",
    }
    requested_urls: list[str] = []

    class ProviderResponse:
        content = b"qr-image"
        headers = {"content-type": "image/jpeg"}

        def raise_for_status(self):
            return None

    def fake_get(url: str, **kwargs):
        requested_urls.append(url)
        return ProviderResponse()

    monkeypatch.setattr(channels_api.requests, "get", fake_get)

    response = client.get(f"/api/admin/channels/{channel_id}/qrcode/download", follow_redirects=False)

    assert response.status_code == 200
    assert response.content == b"qr-image"
    assert requested_urls == ["https://wework.qpic.cn/current"]
    assert response.headers["content-type"] == "image/jpeg"
    assert "attachment;" in response.headers["content-disposition"]
    assert "%E5%B7%B2%E7%94%9F%E6%88%90%E4%BA%8C%E7%BB%B4%E7%A0%81" in response.headers["content-disposition"]
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-aicrm-channel-id"] == str(channel_id)
    assert response.headers["x-aicrm-qr-scene"] == "aqr_current"
    assert response.headers["x-aicrm-qr-asset-id"] == "9"


def test_auto_accept_change_marks_generated_qrcode_stale(monkeypatch):
    client = _client(monkeypatch)
    channel = client.post(
        "/api/admin/channels",
        json={"channel_name": "自动通过渠道", "channel_code": "signup", "auto_accept_friend": False},
    ).json()["channel"]
    channel_id = int(channel["id"])
    channels_api._FIXTURE_CHANNELS[channel_id]["scene_value"] = "aqr_current"
    channels_api._FIXTURE_CHANNELS[channel_id]["qr_url"] = "https://wework.qpic.cn/current"
    channels_api._FIXTURE_CHANNELS[channel_id]["_active_qrcode_asset"] = {
        "id": 9,
        "channel_id": channel_id,
        "scene_value": "aqr_current",
        "qr_url": "https://wework.qpic.cn/current",
        "status": "active",
    }

    updated = client.patch(
        f"/api/admin/channels/{channel_id}",
        json={
            "channel_name": "自动通过渠道",
            "channel_code": "signup",
            "auto_accept_friend": True,
        },
    )
    status = client.get(f"/api/admin/channels/{channel_id}/qrcode/status")
    download = client.get(f"/api/admin/channels/{channel_id}/qrcode/download", follow_redirects=False)

    assert updated.status_code == 200
    assert updated.json()["channel"]["auto_accept_friend"] is True
    assert updated.json()["channel"]["qrcode_status"] not in {"active", "generated"}
    assert status.status_code == 200
    assert status.json()["downloadable"] is False
    assert status.json()["reason"] == "qrcode_asset_not_downloadable"
    assert download.status_code == 409
    assert download.json()["reason"] == "qrcode_asset_not_downloadable"


def test_download_rejects_channel_cache_and_asset_mismatch(monkeypatch):
    client = _client(monkeypatch)
    channel = client.post("/api/admin/channels", json={"channel_name": "错配二维码", "channel_code": "signup"}).json()["channel"]
    channel_id = int(channel["id"])
    channels_api._FIXTURE_CHANNELS[channel_id]["scene_value"] = "program_3_default_qrcode"
    channels_api._FIXTURE_CHANNELS[channel_id]["qr_url"] = "https://wework.qpic.cn/stale"
    channels_api._FIXTURE_CHANNELS[channel_id]["_active_qrcode_asset"] = {
        "id": 10,
        "channel_id": channel_id,
        "scene_value": "aqr_actual",
        "qr_url": "https://wework.qpic.cn/actual",
        "status": "active",
    }

    response = client.get(f"/api/admin/channels/{channel_id}/qrcode/download", follow_redirects=False)

    assert response.status_code == 409
    assert response.json()["reason"] == "qrcode_asset_mismatch"
