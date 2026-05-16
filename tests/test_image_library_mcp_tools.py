"""image_library 的 MCP 工具集测试。

覆盖：
- list_image_library_tool_specs() 形态正确，5 个 tool 全部到位
- dispatch_image_library_tool 路由到 5 个 tool 的参数解析 + domain 调用
- update_metadata 的 overwrite=false 只填空字段
- upload 的 base64 入库
- facets 返回 categories + tags
- mcp_adapter 把 image_library tool 合并进 TOOL_DEFS、execute_mcp_tool_runtime
  能正确分发
"""
from __future__ import annotations

import base64

import pytest

from wecom_ability_service.domains import image_library
from wecom_ability_service.domains.image_library import mcp_tools as ml


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


# ---------- spec 形态 ---------- #

def test_tool_specs_returns_five_tools_with_required_keys():
    specs = ml.list_image_library_tool_specs()
    names = [s["name"] for s in specs]
    assert names == [
        "image_library_list",
        "image_library_get",
        "image_library_update_metadata",
        "image_library_upload",
        "image_library_facets",
    ]
    for spec in specs:
        # 必备键：name / description / input_schema / side_effect
        assert spec["description"]
        assert "input_schema" in spec
        assert spec["side_effect"] in {"read", "write"}


def test_tool_specs_input_schema_marks_required_fields():
    specs = {s["name"]: s for s in ml.list_image_library_tool_specs()}
    assert specs["image_library_get"]["input_schema"]["required"] == ["image_id"]
    assert specs["image_library_update_metadata"]["input_schema"]["required"] == ["image_id"]
    assert specs["image_library_upload"]["input_schema"]["required"] == ["data_base64"]


def test_tool_specs_returns_independent_copies():
    """两次调用必须返回不同的 list 对象，调用方不能改到内部 _TOOL_SPECS。"""
    a = ml.list_image_library_tool_specs()
    b = ml.list_image_library_tool_specs()
    assert a is not b
    a.append({"name": "evil", "description": "x"})
    c = ml.list_image_library_tool_specs()
    assert "evil" not in [t["name"] for t in c]


# ---------- list ---------- #

def test_dispatch_list_returns_items_and_count(app):
    with app.app_context():
        image_library.create_image_from_upload(
            file_bytes=_TINY_PNG_BYTES, file_name="a.png", mime_type="image/png",
            tags=["好评"], category="好评截图",
        )
        image_library.create_image_from_upload(
            file_bytes=_TINY_PNG_BYTES, file_name="b.png", mime_type="image/png",
        )
        result = ml.dispatch_image_library_tool(tool_name="image_library_list", arguments={})
        assert result["ok"] is True
        assert result["count"] == 2
        # 列表里默认不含 base64
        assert all("data_base64" not in it for it in result["items"])


def test_dispatch_list_filters_by_tags_and_category(app):
    with app.app_context():
        image_library.create_image_from_upload(
            file_bytes=_TINY_PNG_BYTES, file_name="a.png", mime_type="image/png",
            tags=["好评"], category="好评截图",
        )
        image_library.create_image_from_upload(
            file_bytes=_TINY_PNG_BYTES, file_name="b.png", mime_type="image/png",
            tags=["活动"], category="活动海报",
        )
        result = ml.dispatch_image_library_tool(
            tool_name="image_library_list",
            arguments={"tags": ["好评"], "category": "好评截图"},
        )
        assert result["ok"] is True
        assert result["count"] == 1
        assert result["items"][0]["file_name"] == "a.png"


def test_dispatch_list_only_unlabeled(app):
    with app.app_context():
        labeled = image_library.create_image_from_upload(
            file_bytes=_TINY_PNG_BYTES, file_name="a.png", mime_type="image/png",
            tags=["好评"], category="好评截图", description="desc",
        )
        unlabeled = image_library.create_image_from_upload(
            file_bytes=_TINY_PNG_BYTES, file_name="b.png", mime_type="image/png",
        )
        result = ml.dispatch_image_library_tool(
            tool_name="image_library_list",
            arguments={"only_unlabeled": True},
        )
        assert {it["id"] for it in result["items"]} == {unlabeled["id"]}
        # labeled 不在
        assert labeled["id"] not in {it["id"] for it in result["items"]}


# ---------- get ---------- #

def test_dispatch_get_with_data_returns_base64(app):
    with app.app_context():
        created = image_library.create_image_from_upload(
            file_bytes=_TINY_PNG_BYTES, file_name="a.png", mime_type="image/png",
        )
        result = ml.dispatch_image_library_tool(
            tool_name="image_library_get",
            arguments={"image_id": created["id"], "with_data": True},
        )
        assert result["ok"] is True
        assert "data_base64" in result["item"]
        assert result["item"]["data_base64"]


def test_dispatch_get_without_data_omits_base64(app):
    with app.app_context():
        created = image_library.create_image_from_upload(
            file_bytes=_TINY_PNG_BYTES, file_name="a.png", mime_type="image/png",
        )
        result = ml.dispatch_image_library_tool(
            tool_name="image_library_get",
            arguments={"image_id": created["id"]},
        )
        assert result["ok"] is True
        assert "data_base64" not in result["item"]


def test_dispatch_get_missing_image_id_errors():
    result = ml.dispatch_image_library_tool(
        tool_name="image_library_get",
        arguments={},
    )
    assert result["ok"] is False
    assert "image_id" in result["error"]


def test_dispatch_get_not_found_returns_error(app):
    with app.app_context():
        result = ml.dispatch_image_library_tool(
            tool_name="image_library_get",
            arguments={"image_id": 99999},
        )
        assert result["ok"] is False
        assert "not found" in result["error"]


# ---------- update_metadata ---------- #

def test_dispatch_update_metadata_writes_fields(app):
    with app.app_context():
        created = image_library.create_image_from_upload(
            file_bytes=_TINY_PNG_BYTES, file_name="a.png", mime_type="image/png",
        )
        result = ml.dispatch_image_library_tool(
            tool_name="image_library_update_metadata",
            arguments={
                "image_id": created["id"],
                "description": "宝妈表达对效果质疑时的回复",
                "tags": ["好评", "信任建立"],
                "category": "好评截图",
                "ai_metadata": {"objects": ["chat_screenshot"]},
            },
        )
        assert result["ok"] is True
        assert set(result["applied"]) == {"description", "tags", "category", "ai_metadata"}
        assert result["item"]["category"] == "好评截图"
        assert result["item"]["tags"] == ["好评", "信任建立"]


def test_dispatch_update_metadata_overwrite_false_skips_filled_fields(app):
    """overwrite=false 时，已经有内容的字段不动，只填空字段。"""
    with app.app_context():
        created = image_library.create_image_from_upload(
            file_bytes=_TINY_PNG_BYTES, file_name="a.png", mime_type="image/png",
            description="人工写过的描述",  # 已经有
            # tags + category 留空，AI 应该能填
        )
        result = ml.dispatch_image_library_tool(
            tool_name="image_library_update_metadata",
            arguments={
                "image_id": created["id"],
                "description": "AI 重写的描述",  # 要被跳过
                "tags": ["AI 加的"],
                "category": "AI 加的分类",
                "overwrite": False,
            },
        )
        assert result["ok"] is True
        # description 已有 → 不在 applied 里
        assert "description" not in result["applied"]
        # tags / category 之前空 → 应被填入
        assert "tags" in result["applied"]
        assert "category" in result["applied"]
        # 验证人工写过的 description 没被 AI 覆盖
        assert result["item"]["description"] == "人工写过的描述"
        assert result["item"]["tags"] == ["AI 加的"]


def test_dispatch_update_metadata_no_payload_returns_existing(app):
    """什么字段都没传不算错，直接回当前状态。"""
    with app.app_context():
        created = image_library.create_image_from_upload(
            file_bytes=_TINY_PNG_BYTES, file_name="a.png", mime_type="image/png",
        )
        result = ml.dispatch_image_library_tool(
            tool_name="image_library_update_metadata",
            arguments={"image_id": created["id"]},
        )
        assert result["ok"] is True
        assert result["applied"] == []


def test_dispatch_update_metadata_clear_via_empty_array(app):
    """传空数组 / 空对象表示清空。"""
    with app.app_context():
        created = image_library.create_image_from_upload(
            file_bytes=_TINY_PNG_BYTES, file_name="a.png", mime_type="image/png",
            tags=["原标签"], ai_metadata={"k": 1},
        )
        result = ml.dispatch_image_library_tool(
            tool_name="image_library_update_metadata",
            arguments={
                "image_id": created["id"],
                "tags": [],
                "ai_metadata": {},
            },
        )
        assert result["ok"] is True
        assert result["item"]["tags"] == []
        assert result["item"]["ai_metadata"] == {}


# ---------- upload ---------- #

def test_dispatch_upload_creates_with_metadata(app):
    with app.app_context():
        result = ml.dispatch_image_library_tool(
            tool_name="image_library_upload",
            arguments={
                "data_base64": _TINY_PNG_B64,
                "file_name": "from_ai.png",
                "mime_type": "image/png",
                "name": "AI 自助上传",
                "description": "客户对产品犹豫时回复用",
                "tags": ["决策辅助", "案例"],
                "category": "聊天话术配图",
                "ai_metadata": {"vision_model": "claude-opus-4-7"},
            },
        )
        assert result["ok"] is True
        item = result["item"]
        assert item["id"] > 0
        assert item["category"] == "聊天话术配图"
        assert item["tags"] == ["决策辅助", "案例"]
        assert item["ai_metadata"] == {"vision_model": "claude-opus-4-7"}


def test_dispatch_upload_missing_data_errors():
    result = ml.dispatch_image_library_tool(
        tool_name="image_library_upload",
        arguments={"file_name": "x.png"},
    )
    assert result["ok"] is False
    assert "data_base64" in result["error"]


# ---------- facets ---------- #

def test_dispatch_facets_returns_categories_and_tags(app):
    with app.app_context():
        image_library.create_image_from_upload(
            file_bytes=_TINY_PNG_BYTES, file_name="a.png", mime_type="image/png",
            tags=["好评", "信任"], category="好评截图",
        )
        image_library.create_image_from_upload(
            file_bytes=_TINY_PNG_BYTES, file_name="b.png", mime_type="image/png",
            tags=["活动"], category="活动海报",
        )
        result = ml.dispatch_image_library_tool(
            tool_name="image_library_facets",
            arguments={},
        )
        assert result["ok"] is True
        assert result["categories"] == ["好评截图", "活动海报"]
        assert "好评" in result["tags"]
        assert "活动" in result["tags"]


# ---------- 错误兜底 ---------- #

def test_dispatch_unknown_tool_returns_error():
    result = ml.dispatch_image_library_tool(
        tool_name="image_library_does_not_exist",
        arguments={},
    )
    assert result["ok"] is False
    assert "unknown tool" in result["error"]


# ---------- mcp_adapter 集成 ---------- #

def test_mcp_adapter_registers_image_library_tools_in_tool_defs():
    from wecom_ability_service.mcp_adapter import TOOL_DEFS
    names = {t["name"] for t in TOOL_DEFS}
    for expected in [
        "image_library_list",
        "image_library_get",
        "image_library_update_metadata",
        "image_library_upload",
        "image_library_facets",
    ]:
        assert expected in names, f"{expected} 没注册到 TOOL_DEFS"


def test_mcp_adapter_marks_write_tools_with_prefix():
    """update_metadata / upload 必须在 description 前打 [WRITE] 标记，
    让 Skill / 调用方一眼看出。"""
    from wecom_ability_service.mcp_adapter import TOOL_DEFS
    by_name = {t["name"]: t for t in TOOL_DEFS}
    assert by_name["image_library_update_metadata"]["description"].startswith("[WRITE]")
    assert by_name["image_library_upload"]["description"].startswith("[WRITE]")
    # read 工具不能加 [WRITE]
    assert not by_name["image_library_list"]["description"].startswith("[WRITE]")


def test_mcp_adapter_execute_runtime_routes_to_image_library(app):
    """execute_mcp_tool_runtime 必须能识别 image_library_* 走我们的 dispatcher。"""
    from wecom_ability_service.mcp_adapter import execute_mcp_tool_runtime
    with app.app_context():
        created = image_library.create_image_from_upload(
            file_bytes=_TINY_PNG_BYTES, file_name="a.png", mime_type="image/png",
            tags=["t1"],
        )
        result = execute_mcp_tool_runtime(
            "image_library_get",
            {"image_id": created["id"]},
        )
        # mcp_adapter 包了一层 ``{"tool": name, ...}``
        assert result["tool"] == "image_library_get"
        assert result["ok"] is True
        assert result["item"]["id"] == created["id"]


def test_mcp_adapter_execute_runtime_passes_through_errors(app):
    """domain 层 ValueError 必须以 ``{"ok": false, "error": ...}`` 形态回传，
    不能让 exception 冒出来导致 MCP 协议层返回 -32000。"""
    from wecom_ability_service.mcp_adapter import execute_mcp_tool_runtime
    with app.app_context():
        result = execute_mcp_tool_runtime(
            "image_library_get",
            {"image_id": 99999},
        )
        assert result["ok"] is False
        assert "not found" in result["error"]
