"""image_library 语义字段（description / tags / category / ai_metadata）单元测试。

覆盖：
- 工具函数 _normalize_tags / _normalize_ai_metadata / _to_jsonb_text / _decode_jsonb
- create_image_from_upload / from_url / from_base64 写入新字段
- update_image partial 更新（None 不改、空数组清空）
- list_images 按 q / tags / category / only_unlabeled 过滤
- list_categories_and_tags 聚合 facets
"""
from __future__ import annotations

import base64

import pytest

from wecom_ability_service.domains import image_library
from wecom_ability_service.domains.image_library import (
    _decode_jsonb,
    _normalize_ai_metadata,
    _normalize_tags,
    _to_jsonb_text,
)
from wecom_ability_service.domains.wecom_media_limits import WECOM_IMAGE_MAX_BYTES


# 1x1 PNG，已知工作的最小 base64
_TINY_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkAAEAAAcAAekVCC0AAAAASUVORK5CYII="
)
_TINY_PNG_B64 = base64.b64encode(_TINY_PNG_BYTES).decode("ascii")


@pytest.fixture()
def app(tmp_path):
    from tests.conftest import build_pg_test_app

    with build_pg_test_app(
        tmp_path,
        MCP_BEARER_TOKEN="mcp-token",
        AUTOMATION_INTERNAL_API_TOKEN="internal-token",
    ) as app:
        yield app


# ---------- 工具函数 ---------- #

def test_normalize_tags_supports_csv_and_list():
    assert _normalize_tags("好评, 信任建立 ,, ") == ["好评", "信任建立"]
    assert _normalize_tags(["好评", " 信任", "好评"]) == ["好评", "信任"]
    assert _normalize_tags(None) == []
    assert _normalize_tags(123) == []


def test_normalize_tags_clips_to_64_chars_and_50_items():
    huge = "x" * 200
    assert _normalize_tags([huge])[0] == "x" * 64
    too_many = [f"t{i}" for i in range(80)]
    assert len(_normalize_tags(too_many)) == 50


def test_normalize_ai_metadata_dict_passthrough():
    assert _normalize_ai_metadata({"k": 1}) == {"k": 1}
    assert _normalize_ai_metadata("not-a-dict") == {}
    assert _normalize_ai_metadata('{"k": 2}') == {"k": 2}
    assert _normalize_ai_metadata(["nope"]) == {}
    assert _normalize_ai_metadata(None) == {}


def test_to_jsonb_text_handles_dict_list_str_none():
    assert _to_jsonb_text(["a", "b"], default="[]") == '["a", "b"]'
    assert _to_jsonb_text({"k": 1}, default="{}") == '{"k": 1}'
    assert _to_jsonb_text(None, default="[]") == "[]"
    # 已经是 JSON 字符串：原样返回
    assert _to_jsonb_text('["a"]', default="[]") == '["a"]'
    # 空字符串走 default
    assert _to_jsonb_text("", default="[]") == "[]"


def test_decode_jsonb_handles_str_dict_list_empty():
    assert _decode_jsonb('["a"]', default=[]) == ["a"]
    assert _decode_jsonb({"k": 1}, default={}) == {"k": 1}
    assert _decode_jsonb(None, default=[]) == []
    assert _decode_jsonb("", default=[]) == []
    # 烂 JSON：fallback 到 default
    assert _decode_jsonb("{not-json", default={}) == {}


# ---------- 创建：新字段写入 ---------- #

def test_create_from_upload_stores_metadata(app):
    with app.app_context():
        item = image_library.create_image_from_upload(
            file_bytes=_TINY_PNG_BYTES,
            file_name="hi.png",
            mime_type="image/png",
            name="测试图",
            description="一张 1x1 小图",
            tags=["好评", "信任建立"],
            category="好评截图",
            ai_metadata={"objects": ["small_pixel"]},
        )
        assert item["id"] > 0
        assert item["description"] == "一张 1x1 小图"
        assert item["tags"] == ["好评", "信任建立"]
        assert item["category"] == "好评截图"
        assert item["ai_metadata"] == {"objects": ["small_pixel"]}


def test_create_from_url_stores_metadata(app):
    with app.app_context():
        item = image_library.create_image_from_url(
            url="https://cdn.example.com/a.png",
            name="外链图",
            description="某产品截图",
            tags="活动海报,五月新品",  # csv 形态
            category="活动海报",
        )
        assert item["tags"] == ["活动海报", "五月新品"]
        assert item["category"] == "活动海报"
        assert item["description"] == "某产品截图"
        assert item["ai_metadata"] == {}  # 默认空 dict


def test_create_from_base64_stores_metadata(app):
    with app.app_context():
        item = image_library.create_image_from_base64(
            data_base64=_TINY_PNG_B64,
            file_name="b64.png",
            mime_type="image/png",
            tags=["产品"],
        )
        assert item["tags"] == ["产品"]
        assert item["description"] == ""
        assert item["category"] == ""


def test_create_defaults_empty_metadata_when_omitted(app):
    """老调用方不传新字段时全部默认为空，不能拒收。"""
    with app.app_context():
        item = image_library.create_image_from_upload(
            file_bytes=_TINY_PNG_BYTES,
            file_name="legacy.png",
            mime_type="image/png",
        )
        assert item["description"] == ""
        assert item["tags"] == []
        assert item["category"] == ""
        assert item["ai_metadata"] == {}


def test_create_from_upload_rejects_images_over_wecom_limit(app):
    oversized_png = b"\x89PNG\r\n\x1a\n" + (b"0" * WECOM_IMAGE_MAX_BYTES)
    with app.app_context():
        with pytest.raises(ValueError, match="max 2MB"):
            image_library.create_image_from_upload(
                file_bytes=oversized_png,
                file_name="too-large.png",
                mime_type="image/png",
            )


def test_create_from_upload_rejects_unsupported_wecom_image_type(app):
    gif_bytes = b"GIF89a" + (b"0" * 32)
    with app.app_context():
        with pytest.raises(ValueError, match="JPG/PNG"):
            image_library.create_image_from_upload(
                file_bytes=gif_bytes,
                file_name="animated.gif",
                mime_type="image/gif",
            )


def test_create_from_base64_normalizes_jpg_alias(app):
    jpeg_bytes = b"\xff\xd8\xff" + (b"0" * 32)
    jpeg_b64 = base64.b64encode(jpeg_bytes).decode("ascii")
    with app.app_context():
        item = image_library.create_image_from_base64(
            data_base64=f"data:image/jpg;base64,{jpeg_b64}",
            file_name="alias.jpg",
            mime_type="image/jpg",
        )
        assert item["mime_type"] == "image/jpeg"


def test_create_from_url_rejects_explicit_unsupported_mime(app):
    with app.app_context():
        with pytest.raises(ValueError, match="JPG/PNG"):
            image_library.create_image_from_url(
                url="https://cdn.example.com/a.gif",
                mime_type="image/gif",
            )


def test_resolve_image_media_id_rejects_legacy_oversized_record_before_upload(app):
    oversized_png = b"\x89PNG\r\n\x1a\n" + (b"0" * WECOM_IMAGE_MAX_BYTES)
    called = []

    with app.app_context():
        image_id = image_library._insert_image(
            name="历史超限图",
            file_name="legacy-too-large.png",
            source="upload",
            source_url="",
            data_base64=base64.b64encode(oversized_png).decode("ascii"),
            mime_type="image/png",
            file_size=len(oversized_png),
        )

        def _upload(*args):
            called.append(args)
            return "should-not-upload"

        with pytest.raises(ValueError, match="max 2MB"):
            image_library.resolve_image_media_id(image_id, upload_image=_upload)
        assert called == []


# ---------- update：partial 语义 ---------- #

def test_update_image_partial_only_changes_specified(app):
    with app.app_context():
        created = image_library.create_image_from_upload(
            file_bytes=_TINY_PNG_BYTES,
            file_name="x.png",
            mime_type="image/png",
            description="原描述",
            tags=["a", "b"],
            category="原分类",
        )
        # 只改 description，其他保留
        updated = image_library.update_image(
            created["id"], description="新描述"
        )
        assert updated["description"] == "新描述"
        assert updated["tags"] == ["a", "b"]
        assert updated["category"] == "原分类"


def test_update_image_clear_tags_via_empty_list(app):
    with app.app_context():
        created = image_library.create_image_from_upload(
            file_bytes=_TINY_PNG_BYTES,
            file_name="x.png",
            mime_type="image/png",
            tags=["t1", "t2"],
        )
        updated = image_library.update_image(created["id"], tags=[])
        assert updated["tags"] == []


def test_update_image_clear_metadata_via_empty_dict(app):
    with app.app_context():
        created = image_library.create_image_from_upload(
            file_bytes=_TINY_PNG_BYTES,
            file_name="x.png",
            mime_type="image/png",
            ai_metadata={"k": 1},
        )
        updated = image_library.update_image(created["id"], ai_metadata={})
        assert updated["ai_metadata"] == {}


# ---------- list 过滤 ---------- #

def _seed_three_records(app):
    with app.app_context():
        a = image_library.create_image_from_upload(
            file_bytes=_TINY_PNG_BYTES,
            file_name="a.png",
            mime_type="image/png",
            name="好评截图A",
            description="客户表达满意的好评聊天截图",
            tags=["好评", "信任建立"],
            category="好评截图",
        )
        b = image_library.create_image_from_upload(
            file_bytes=_TINY_PNG_BYTES,
            file_name="b.png",
            mime_type="image/png",
            name="活动海报B",
            description="五月活动主图",
            tags=["活动海报"],
            category="活动海报",
        )
        c = image_library.create_image_from_upload(
            file_bytes=_TINY_PNG_BYTES,
            file_name="c.png",
            mime_type="image/png",
            name="未打标C",
        )
        return a, b, c


def test_list_filter_by_q_matches_name_and_description(app):
    a, b, c = _seed_three_records(app)
    with app.app_context():
        # 命中 description
        items = image_library.list_images(q="满意")
        assert {it["id"] for it in items} == {a["id"]}
        # 命中 name
        items = image_library.list_images(q="海报")
        assert {it["id"] for it in items} == {b["id"]}


def test_list_filter_by_tags_or_semantics(app):
    a, b, _c = _seed_three_records(app)
    with app.app_context():
        # 命中任一即返回
        items = image_library.list_images(tags=["好评", "活动海报"])
        assert {it["id"] for it in items} == {a["id"], b["id"]}
        # 单 tag 也工作
        items = image_library.list_images(tags=["信任建立"])
        assert {it["id"] for it in items} == {a["id"]}


def test_list_filter_by_category_exact(app):
    a, _b, _c = _seed_three_records(app)
    with app.app_context():
        items = image_library.list_images(category="好评截图")
        assert {it["id"] for it in items} == {a["id"]}


def test_list_only_unlabeled_returns_empty_metadata_records(app):
    _a, _b, c = _seed_three_records(app)
    with app.app_context():
        items = image_library.list_images(only_unlabeled=True)
        # 只有 c 三个字段都空
        assert {it["id"] for it in items} == {c["id"]}


def test_list_combines_filters_with_and(app):
    a, b, _c = _seed_three_records(app)
    with app.app_context():
        # tags 命中 a 和 b，但 category 只有 a 是好评截图 → 只有 a
        items = image_library.list_images(
            tags=["好评", "活动海报"], category="好评截图"
        )
        assert {it["id"] for it in items} == {a["id"]}


# ---------- facets ---------- #

def test_list_categories_and_tags_returns_distinct_sorted(app):
    with app.app_context():
        image_library.create_image_from_upload(
            file_bytes=_TINY_PNG_BYTES,
            file_name="a.png",
            mime_type="image/png",
            tags=["好评", "信任"],
            category="好评截图",
        )
        image_library.create_image_from_upload(
            file_bytes=_TINY_PNG_BYTES,
            file_name="b.png",
            mime_type="image/png",
            tags=["好评", "活动"],
            category="活动海报",
        )
        # 停用的不进 facets
        c = image_library.create_image_from_upload(
            file_bytes=_TINY_PNG_BYTES,
            file_name="c.png",
            mime_type="image/png",
            tags=["disabled-tag"],
            category="禁用分类",
        )
        image_library.update_image(c["id"], enabled=False)

        facets = image_library.list_categories_and_tags()
        assert facets["categories"] == ["好评截图", "活动海报"]
        # tag 去重 + 排序，停用记录的 disabled-tag 不出现
        assert facets["tags"] == ["信任", "好评", "活动"]


def test_list_categories_and_tags_can_include_disabled(app):
    with app.app_context():
        c = image_library.create_image_from_upload(
            file_bytes=_TINY_PNG_BYTES,
            file_name="c.png",
            mime_type="image/png",
            tags=["disabled-tag"],
            category="禁用分类",
        )
        image_library.update_image(c["id"], enabled=False)
        facets = image_library.list_categories_and_tags(enabled_only=False)
        assert "禁用分类" in facets["categories"]
        assert "disabled-tag" in facets["tags"]


# ---------- 老 API 行为不被破坏 ---------- #

def test_legacy_list_images_still_works(app):
    """老调用方只传 enabled_only/limit 必须照常工作。"""
    with app.app_context():
        image_library.create_image_from_upload(
            file_bytes=_TINY_PNG_BYTES,
            file_name="x.png",
            mime_type="image/png",
        )
        items = image_library.list_images(enabled_only=True, limit=10)
        assert len(items) == 1
        assert items[0]["tags"] == []
        assert "description" in items[0]


def test_get_image_returns_new_fields(app):
    with app.app_context():
        created = image_library.create_image_from_upload(
            file_bytes=_TINY_PNG_BYTES,
            file_name="x.png",
            mime_type="image/png",
            description="d",
            tags=["t"],
            category="c",
            ai_metadata={"k": "v"},
        )
        fetched = image_library.get_image(created["id"])
        assert fetched["description"] == "d"
        assert fetched["tags"] == ["t"]
        assert fetched["category"] == "c"
        assert fetched["ai_metadata"] == {"k": "v"}
        # include_data 路径也要带新字段
        with_data = image_library.get_image(created["id"], include_data=True)
        assert with_data["tags"] == ["t"]
        assert "data_base64" in with_data


# ---------- HTTP endpoint smoke：facets endpoint 不需要 admin 登录(只读) ---------- #
# admin 鉴权 fixture 很重；这里只验证 endpoint 解析参数的简单单元（domain
# 已经覆盖业务逻辑）。完整 HTTP 集成测试在 PR-B 加（前端要走 client.post）。

def test_endpoint_parse_tags_arg_csv_and_json():
    from wecom_ability_service.http.image_library_support import _parse_tags_arg

    assert _parse_tags_arg("好评,信任") == ["好评", "信任"]
    assert _parse_tags_arg('["好评", "信任"]') == ["好评", "信任"]
    assert _parse_tags_arg(None) == []
    assert _parse_tags_arg("") == []
    # 非法 JSON 退化成 csv
    assert _parse_tags_arg("[bad-json") == ["[bad-json"]


def test_endpoint_parse_bool_arg():
    from wecom_ability_service.http.image_library_support import _parse_bool_arg

    assert _parse_bool_arg("true") is True
    assert _parse_bool_arg("0") is False
    assert _parse_bool_arg("false") is False
    assert _parse_bool_arg(None, default=True) is True
    assert _parse_bool_arg("", default=True) is False


# ---------- ai_metadata 序列化往返 ---------- #

def test_ai_metadata_roundtrip_complex_dict(app):
    """嵌套结构、unicode、数字等类型都要原样回来。"""
    with app.app_context():
        payload = {
            "objects": ["产品", "logo"],
            "ocr": "限时优惠",
            "score": 0.87,
            "nested": {"a": [1, 2, 3]},
        }
        created = image_library.create_image_from_upload(
            file_bytes=_TINY_PNG_BYTES,
            file_name="x.png",
            mime_type="image/png",
            ai_metadata=payload,
        )
        assert created["ai_metadata"] == payload
        from wecom_ability_service.db import get_db

        cur = get_db().cursor()
        cur.execute(
            "SELECT ai_metadata FROM image_library WHERE id = ?",
            (created["id"],),
        )
        row = cur.fetchone()
        assert dict(row)["ai_metadata"] == payload
