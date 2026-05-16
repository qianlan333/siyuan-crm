from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UPLOAD_CLIENT = ROOT / "wecom_ability_service" / "static" / "admin_console" / "image_upload_client.js"
IMAGE_PICKER = ROOT / "wecom_ability_service" / "static" / "admin_console" / "image_picker.js"
MINIPROGRAM_TEMPLATE = ROOT / "wecom_ability_service" / "templates" / "admin_console" / "miniprogram_library.html"
CLOUD_CAMPAIGNS_TEMPLATE = (
    ROOT / "wecom_ability_service" / "templates" / "admin_console" / "cloud_campaigns_workspace.html"
)


def test_image_upload_client_handles_non_json_413():
    source = UPLOAD_CLIENT.read_text(encoding="utf-8")

    assert "DIRECT_UPLOAD_BYTES = 900 * 1024" in source
    assert "response.status === 413" in source
    assert "服务返回了非 JSON" in source
    assert "prepareImageForUpload" in source


def test_image_upload_client_compresses_before_post():
    source = UPLOAD_CLIENT.read_text(encoding="utf-8")

    assert "canvas.toBlob" in source
    assert "image/jpeg" in source
    assert "compressed: true" in source
    assert "MAX_SOURCE_BYTES = 2 * 1024 * 1024" in source
    assert "只能上传 JPG/PNG 图片" in source
    assert "图片大小不能超过 2MB" in source


def test_image_picker_uses_shared_upload_client():
    source = IMAGE_PICKER.read_text(encoding="utf-8")

    assert "ImageUploadClient.requestJson" in source
    assert "ImageUploadClient.prepareImageForUpload" in source
    assert "resp.json()" not in source


def test_image_picker_consumers_load_upload_client_first():
    for template in (MINIPROGRAM_TEMPLATE, CLOUD_CAMPAIGNS_TEMPLATE):
        source = template.read_text(encoding="utf-8")
        assert source.index("image_upload_client.js") < source.index("image_picker.js")
