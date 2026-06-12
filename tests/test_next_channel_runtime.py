from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.automation_engine import channels_api
from aicrm_next.main import create_app


def _client(monkeypatch) -> TestClient:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    monkeypatch.setenv("SECRET_KEY", "next-channel-runtime-test")
    channels_api._FIXTURE_CHANNELS.clear()
    channels_api._FIXTURE_PROGRAM_BINDINGS.clear()
    channels_api._NEXT_ID = 1
    channels_api._NEXT_BINDING_ID = 1
    return TestClient(create_app(), raise_server_exceptions=False)


def test_next_channel_center_page_and_channel_crud_routes(monkeypatch):
    client = _client(monkeypatch)

    page = client.get("/admin/channels")
    assert page.status_code == 200
    assert "渠道码中心" in page.text
    assert "/api/admin/channels?limit=300" in page.text

    created = client.post(
        "/api/admin/channels",
        json={
            "channel_name": "Next 普通二维码",
            "channel_code": "aqr_next_runtime",
            "status": "active",
        },
    )
    assert created.status_code == 201
    channel = created.json()["channel"]
    channel_id = int(channel["id"])
    assert channel["scene_value"] == ""
    assert channel["qr_url"] == ""
    assert channel["qrcode_status"] == "not_generated"
    channels_api._FIXTURE_CHANNELS[channel_id]["scene_value"] = "aqr_next_runtime"
    channels_api._FIXTURE_CHANNELS[channel_id]["qr_url"] = "https://wework.qpic.cn/next-runtime-qr"
    channels_api._FIXTURE_CHANNELS[channel_id]["_active_qrcode_asset"] = {
        "id": 77,
        "channel_id": channel_id,
        "scene_value": "aqr_next_runtime",
        "qr_url": "https://wework.qpic.cn/next-runtime-qr",
        "status": "active",
    }
    channels_api._FIXTURE_CHANNELS[channel_id]["historical_scene_values"] = ["aqr_legacy_runtime"]

    listed = client.get("/api/admin/channels")
    assert listed.status_code == 200
    listed_channel = next(item for item in listed.json()["channels"] if int(item["id"]) == channel_id)
    assert listed_channel["historical_scene_values"] == ["aqr_legacy_runtime"]

    detail = client.get(f"/api/admin/channels/{channel_id}")
    assert detail.status_code == 200
    assert detail.json()["channel"]["channel_name"] == "Next 普通二维码"
    assert detail.json()["channel"]["historical_scene_values"] == ["aqr_legacy_runtime"]

    edit_page = client.get(f"/admin/channels/{channel_id}/edit")
    assert edit_page.status_code == 200
    assert "历史回调 State" in edit_page.text
    assert "aqr_legacy_runtime" in edit_page.text

    updated = client.patch(f"/api/admin/channels/{channel_id}", json={"channel_name": "Next 普通二维码已更新"})
    assert updated.status_code == 200
    assert updated.json()["channel"]["channel_name"] == "Next 普通二维码已更新"
    assert updated.json()["channel"]["historical_scene_values"] == ["aqr_legacy_runtime"]

    contacts = client.get(f"/api/admin/channels/{channel_id}/contacts")
    assert contacts.status_code == 200
    assert contacts.json()["contacts"] == []

    qrcode = client.get(f"/api/admin/channels/{channel_id}/qrcode/download", follow_redirects=False)
    assert qrcode.status_code == 302
    assert qrcode.headers["location"] == "https://wework.qpic.cn/next-runtime-qr"
    assert qrcode.headers["x-aicrm-qr-scene"] == "aqr_next_runtime"

    link_created = client.post(
        "/api/admin/channels",
        json={
            "channel_type": "wecom_customer_acquisition",
            "carrier_type": "link",
            "channel_name": "Next 获客助手",
            "channel_code": "wca_next_runtime",
            "customer_channel": "wca_next_runtime",
            "link_url": "https://work.weixin.qq.com/ca/next-runtime",
            "status": "active",
        },
    )
    assert link_created.status_code == 201
    link_id = int(link_created.json()["channel"]["id"])

    share = client.get(f"/api/admin/channels/{link_id}/share-link")
    assert share.status_code == 200
    assert "customer_channel=wca_next_runtime" in share.json()["share_url"]

    rejected_download = client.get(f"/api/admin/channels/{link_id}/qrcode/download")
    assert rejected_download.status_code == 400
    assert rejected_download.json()["reason"] == "link_channel_does_not_support_qrcode_download"

    materials = client.get("/api/admin/channel-welcome-materials?type=all&keyword=欢迎")
    assert materials.status_code == 200
    assert materials.json()["reason"] == "channel_welcome_materials_listed"


def test_next_program_entry_channel_page_and_bindings_api(monkeypatch):
    client = _client(monkeypatch)

    qrcode = client.post(
        "/api/admin/channels",
        json={
            "channel_name": "方案二维码入口",
            "channel_code": "aqr_program_runtime",
        },
    ).json()["channel"]
    link = client.post(
        "/api/admin/channels",
        json={
            "channel_type": "wecom_customer_acquisition",
            "carrier_type": "link",
            "channel_name": "方案获客入口",
            "channel_code": "wca_program_runtime",
            "customer_channel": "wca_program_runtime",
            "link_url": "https://work.weixin.qq.com/ca/program-runtime",
        },
    ).json()["channel"]
    candidate = client.post(
        "/api/admin/channels",
        json={
            "channel_name": "候选二维码入口",
            "channel_code": "aqr_program_candidate",
        },
    ).json()["channel"]

    bound = client.post(
        "/api/admin/automation-conversion/programs/1/channel-bindings",
        json={"channel_ids": [qrcode["id"], link["id"]]},
    )
    assert bound.status_code == 201
    assert len(bound.json()["bindings"]) == 2

    rebound = client.post(
        "/api/admin/automation-conversion/programs/1/channel-bindings",
        json={"channel_ids": [link["id"], candidate["id"]]},
    )
    assert rebound.status_code == 201
    rebound_ids = {int(item["channel_id"]) for item in rebound.json()["bindings"]}
    assert rebound_ids == {int(qrcode["id"]), int(link["id"]), int(candidate["id"])}
    assert len(rebound.json()["bindings"]) == 3

    bindings = client.get("/api/admin/automation-conversion/programs/1/channel-bindings")
    assert bindings.status_code == 200
    bound_names = {item["channel"]["channel_name"] for item in bindings.json()["bindings"]}
    assert bound_names == {"方案二维码入口", "方案获客入口", "候选二维码入口"}

    other_program_channel = client.post(
        "/api/admin/channels",
        json={
            "channel_name": "其他方案占用渠道",
            "channel_code": "aqr_other_program_bound",
        },
    ).json()["channel"]
    other_bound = client.post(
        "/api/admin/automation-conversion/programs/2/channel-bindings",
        json={"channel_ids": [other_program_channel["id"]]},
    )
    assert other_bound.status_code == 201

    qrcode_bindings = client.get(f"/api/admin/channels/{qrcode['id']}/bindings")
    assert qrcode_bindings.status_code == 200
    assert qrcode_bindings.json()["reason"] == "channel_bindings_listed"

    page = client.get("/admin/automation-conversion/programs/1/entry-channels")
    assert page.status_code == 200
    assert "方案二维码入口" in page.text
    assert "方案获客入口" in page.text
    assert "候选二维码入口" in page.text
    assert "/api/admin/automation-conversion/programs/1/channel-bindings" in page.text

    available = client.get("/api/admin/channels?available_for_program_id=1")
    assert available.status_code == 200
    available_ids = {int(item["id"]) for item in available.json()["channels"]}
    assert int(qrcode["id"]) not in available_ids
    assert int(candidate["id"]) not in available_ids
    assert int(other_program_channel["id"]) not in available_ids

    qrcode_binding = next(item for item in bindings.json()["bindings"] if int(item["channel_id"]) == int(qrcode["id"]))
    first_binding_id = int(qrcode_binding["id"])
    deleted = client.request(
        "DELETE",
        f"/api/admin/automation-conversion/programs/1/channel-bindings/{first_binding_id}",
        json={},
    )
    assert deleted.status_code == 200
    assert deleted.json()["reason"] == "program_channel_unbound"
    assert deleted.json()["binding"]["binding_status"] == "archived"

    after_delete = client.get("/api/admin/automation-conversion/programs/1/channel-bindings")
    assert after_delete.status_code == 200
    after_delete_ids = {int(item["channel_id"]) for item in after_delete.json()["bindings"]}
    assert int(qrcode["id"]) not in after_delete_ids

    available_after_delete = client.get("/api/admin/channels?available_for_program_id=1")
    assert available_after_delete.status_code == 200
    available_after_delete_ids = {int(item["id"]) for item in available_after_delete.json()["channels"]}
    assert int(qrcode["id"]) in available_after_delete_ids
