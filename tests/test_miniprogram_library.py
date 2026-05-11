"""miniprogram 群发能力的核心单元测试。

覆盖：
- private_message normalize 对 miniprogram 的字段校验
- miniprogram_library service：CRUD、resolve_thumb_media_id 缓存命中/过期重传
- expand_attachments_with_library：library_id 占位 → 完整 attachment
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from wecom_ability_service import create_app
from wecom_ability_service.db import init_db
from wecom_ability_service.domains import miniprogram_library
from wecom_ability_service.domains.tasks.private_message import (
    SUPPORTED_PRIVATE_MESSAGE_ATTACHMENT_TYPES,
    normalize_private_message_attachments,
)


@pytest.fixture()
def app(tmp_path):
    from tests.conftest import build_pg_test_app

    with build_pg_test_app(
        tmp_path,
        MCP_BEARER_TOKEN="mcp-token",
        AUTOMATION_INTERNAL_API_TOKEN="internal-token",
    ) as app:
        yield app


def test_supported_msgtypes_include_miniprogram():
    assert "miniprogram" in SUPPORTED_PRIVATE_MESSAGE_ATTACHMENT_TYPES
    assert "file" in SUPPORTED_PRIVATE_MESSAGE_ATTACHMENT_TYPES


def test_normalize_miniprogram_attachment_full_payload_pass():
    payload = {
        "attachments": [
            {
                "msgtype": "miniprogram",
                "miniprogram": {
                    "appid": "wxabc123",
                    "pagepath": "pages/index?from=crm",
                    "title": "体验课卡片",
                    "thumb_media_id": "media-xxx",
                },
            }
        ]
    }
    result = normalize_private_message_attachments(payload)
    assert len(result) == 1
    assert result[0]["msgtype"] == "miniprogram"
    assert result[0]["miniprogram"]["appid"] == "wxabc123"
    assert result[0]["miniprogram"]["thumb_media_id"] == "media-xxx"


@pytest.mark.parametrize(
    "missing_field",
    ["appid", "pagepath", "title", "thumb_media_id"],
)
def test_normalize_miniprogram_missing_required_field(missing_field):
    base = {
        "appid": "wxabc",
        "pagepath": "pages/x",
        "title": "卡片",
        "thumb_media_id": "media-1",
    }
    base[missing_field] = ""
    payload = {"attachments": [{"msgtype": "miniprogram", "miniprogram": base}]}
    with pytest.raises(ValueError):
        normalize_private_message_attachments(payload)


def test_miniprogram_library_create_and_get(app):
    with app.app_context():
        item = miniprogram_library.create_miniprogram(
            {
                "name": "卡片1",
                "appid": "wx-1",
                "pagepath": "pages/a",
                "title": "测试卡片",
                "thumb_image_base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkAAEAAAcAAekVCC0AAAAASUVORK5CYII=",
            }
        )
        assert item["id"] > 0
        assert item["appid"] == "wx-1"
        fetched = miniprogram_library.get_miniprogram(item["id"])
        assert fetched["title"] == "测试卡片"


def test_resolve_thumb_media_id_uses_cache_when_valid(app):
    with app.app_context():
        item = miniprogram_library.create_miniprogram(
            {
                "appid": "wx-2",
                "pagepath": "pages/x",
                "title": "缓存命中",
                "thumb_image_base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkAAEAAAcAAekVCC0AAAAASUVORK5CYII=",
            }
        )
        future = datetime.now(tz=timezone.utc) + timedelta(days=1)
        from wecom_ability_service.domains.miniprogram_library import _persist_thumb_media_id

        _persist_thumb_media_id(item["id"], "cached-media", future)

        called = []

        def _fail(*args, **kwargs):
            called.append(args)
            return "should-not-be-called"

        media_id = miniprogram_library.resolve_thumb_media_id(item["id"], upload_image=_fail)
        assert media_id == "cached-media"
        assert called == []


def test_resolve_thumb_media_id_re_uploads_when_expired(app):
    with app.app_context():
        item = miniprogram_library.create_miniprogram(
            {
                "appid": "wx-3",
                "pagepath": "pages/y",
                "title": "缓存过期",
                "thumb_image_base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkAAEAAAcAAekVCC0AAAAASUVORK5CYII=",
            }
        )
        from wecom_ability_service.domains.miniprogram_library import _persist_thumb_media_id

        past = datetime.now(tz=timezone.utc) - timedelta(days=4)
        _persist_thumb_media_id(item["id"], "stale-media", past)

        upload_calls = []

        def _fake_upload(file_name, file_bytes, content_type):
            upload_calls.append((file_name, len(file_bytes), content_type))
            return "fresh-media"

        media_id = miniprogram_library.resolve_thumb_media_id(
            item["id"], upload_image=_fake_upload
        )
        assert media_id == "fresh-media"
        assert len(upload_calls) == 1
        refreshed = miniprogram_library.get_miniprogram(item["id"])
        assert refreshed["thumb_media_id"] == "fresh-media"


def test_expand_attachments_with_library_substitutes_placeholder(app):
    with app.app_context():
        item = miniprogram_library.create_miniprogram(
            {
                "appid": "wx-4",
                "pagepath": "pages/default",
                "title": "默认标题",
                "thumb_image_base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkAAEAAAcAAekVCC0AAAAASUVORK5CYII=",
            }
        )

        def _fake_upload(file_name, file_bytes, content_type):
            return "media-from-test"

        attachments = [
            {
                "msgtype": "miniprogram",
                "miniprogram": {
                    "library_id": item["id"],
                    "pagepath": "pages/override?x=1",
                },
            },
            {"msgtype": "file", "file": {"media_id": "file-1"}},
        ]
        expanded = miniprogram_library.expand_attachments_with_library(
            attachments, upload_image=_fake_upload
        )
        assert expanded[0]["msgtype"] == "miniprogram"
        assert expanded[0]["miniprogram"]["appid"] == "wx-4"
        assert expanded[0]["miniprogram"]["pagepath"] == "pages/override?x=1"
        assert expanded[0]["miniprogram"]["title"] == "默认标题"
        assert expanded[0]["miniprogram"]["thumb_media_id"] == "media-from-test"
        assert expanded[1] == {"msgtype": "file", "file": {"media_id": "file-1"}}


def test_expand_attachments_passes_through_already_resolved(app):
    with app.app_context():
        attachments = [
            {
                "msgtype": "miniprogram",
                "miniprogram": {
                    "appid": "wx-explicit",
                    "pagepath": "pages/x",
                    "title": "已展开",
                    "thumb_media_id": "explicit-media",
                },
            }
        ]
        expanded = miniprogram_library.expand_attachments_with_library(attachments)
        assert expanded == attachments


def test_update_miniprogram_invalidates_thumb_cache(app):
    with app.app_context():
        item = miniprogram_library.create_miniprogram(
            {
                "appid": "wx-5",
                "pagepath": "pages/z",
                "title": "测试更新",
                "thumb_image_url": "https://example.com/old.png",
            }
        )
        future = datetime.now(tz=timezone.utc) + timedelta(days=1)
        from wecom_ability_service.domains.miniprogram_library import _persist_thumb_media_id

        _persist_thumb_media_id(item["id"], "old-media", future)
        miniprogram_library.update_miniprogram(
            item["id"],
            {"thumb_image_url": "https://example.com/new.png"},
        )
        refreshed = miniprogram_library.get_miniprogram(item["id"])
        assert refreshed["thumb_media_id"] == ""
        assert refreshed["thumb_media_id_expires_at"] == ""
