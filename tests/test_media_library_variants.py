from __future__ import annotations

import base64
from io import BytesIO

from fastapi.testclient import TestClient

from aicrm_next.main import create_app


TINY_PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x04\x00\x00\x00\xb5\x1c\x0c\x02"
    b"\x00\x00\x00\x0bIDATx\xdac`\x00\x01\x00\x00\x07\x00\x01\xe9\x15\x08-"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def make_client() -> TestClient:
    return TestClient(create_app())


def test_image_upload_returns_variant_urls_and_variant_endpoint_is_cacheable() -> None:
    client = make_client()
    uploaded = client.post(
        "/api/admin/image-library/upload",
        files={"image": ("hero.png", BytesIO(TINY_PNG), "image/png")},
        data={"name": "variant hero"},
    ).json()["item"]

    assert uploaded["thumb_160_url"].endswith("/variants/thumb_160")
    assert uploaded["thumb_320_url"].endswith("/variants/thumb_320")
    assert uploaded["preview_url"].endswith("/variants/mobile_1080")
    assert uploaded["mobile_1080_url"].endswith("/variants/mobile_1080")

    listed = client.get("/api/admin/image-library", params={"enabled_only": "true"}).json()
    row = next(item for item in listed["items"] if item["id"] == uploaded["id"])
    assert row["thumb_url"].endswith("/variants/thumb_320")
    assert "data_base64" not in row

    variant = client.get(uploaded["thumb_160_url"])
    assert variant.status_code == 200
    assert variant.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert variant.headers.get("etag")
    assert variant.headers["content-type"].startswith("image/")
    assert len(variant.content) < len(TINY_PNG) * 20

    cached = client.get(uploaded["thumb_160_url"], headers={"If-None-Match": variant.headers["etag"]})
    assert cached.status_code == 304


def test_image_detail_requires_include_data_for_original_base64() -> None:
    client = make_client()
    uploaded = client.post(
        "/api/admin/image-library/upload",
        files={"image": ("hero.png", BytesIO(TINY_PNG), "image/png")},
    ).json()["item"]

    detail = client.get(f"/api/admin/image-library/{uploaded['id']}").json()
    assert detail["ok"] is True
    assert "data_base64" not in detail["item"]

    with_data = client.get(f"/api/admin/image-library/{uploaded['id']}?include_data=true").json()
    assert with_data["ok"] is True
    assert with_data["item"]["data_base64"]


def test_image_list_and_thumbnail_endpoint_support_legacy_base64() -> None:
    client = make_client()
    created = client.post(
        "/api/admin/image-library/from-base64",
        json={
            "data_base64": base64.b64encode(TINY_PNG).decode("ascii"),
            "file_name": "legacy.png",
            "name": "legacy base64",
        },
    ).json()["item"]

    listed = client.get("/api/admin/image-library", params={"enabled_only": "true"}).json()
    row = next(item for item in listed["items"] if item["id"] == created["id"])
    assert row["thumb_160_url"]
    assert row["thumb_320_url"]
    assert row["thumb_url"]
    assert row["preview_url"]
    assert "data_base64" not in row

    thumb = client.get(f"/api/admin/image-library/{created['id']}/thumbnail?size=160")
    assert thumb.status_code == 200
    assert thumb.headers["content-type"].split(";")[0] in {"image/png", "image/jpeg"}
    assert thumb.headers.get("etag")
    assert "max-age" in thumb.headers.get("cache-control", "")


def test_thumbnail_endpoint_returns_json_errors() -> None:
    client = make_client()

    invalid_size = client.get("/api/admin/image-library/image_masked_001/thumbnail?size=123")
    assert invalid_size.status_code == 400
    assert invalid_size.headers["content-type"].startswith("application/json")
    assert invalid_size.json()["ok"] is False

    missing = client.get("/api/admin/image-library/missing/thumbnail?size=160")
    assert missing.status_code == 404
    assert missing.headers["content-type"].startswith("application/json")
    assert missing.json()["ok"] is False

    created = client.post(
        "/api/admin/image-library/from-base64",
        json={"data_base64": "not-base64", "file_name": "bad.png", "name": "bad base64"},
    ).json()["item"]
    bad = client.get(f"/api/admin/image-library/{created['id']}/thumbnail?size=160")
    assert bad.status_code == 400
    assert bad.headers["content-type"].startswith("application/json")
    assert bad.json()["ok"] is False
    assert "image data" in bad.json()["error"]
