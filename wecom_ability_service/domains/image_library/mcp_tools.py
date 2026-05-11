"""image_library 的 MCP 工具集 — 让外部 Skill 通过 MCP 协议读写图片素材库。

设计目标：CRM 不调任何 LLM，只暴露数据 + 操作。所有 AI 决策（看图打标 /
聊天上下文推荐）由外部 Claude Skill 完成，Skill 通过 MCP HTTP 端点 ``/mcp``
连过来调下面 5 个工具。

两个出口（沿用 ``cloud_orchestrator/mcp_tools.py`` 范式）：
- ``list_image_library_tool_specs()`` 返回工具规格列表，被
  ``mcp_adapter.TOOL_DEFS.extend(...)`` 合并到全局 tool catalog
- ``dispatch_image_library_tool(tool_name, arguments)`` 路由到 domain 函数

5 个工具：
- ``image_library_list``        — 列出 / 检索图片元数据（不含 base64）
- ``image_library_get``          — 拿单张图，with_data=true 时附 base64
- ``image_library_update_metadata`` — 写元数据；overwrite=false 时只填空字段
- ``image_library_upload``       — base64 直传新图 + 元数据，一站式入库
- ``image_library_facets``       — 当前已用的 categories + tags 池

工具命名前缀 ``image_library_`` 跟 cloud_orchestrator tool（``query_*`` /
``search_*`` / ``draft_*``）做语义隔离，便于 Skill 聚焦本域工具集。
"""
from __future__ import annotations

import logging
from typing import Any

from . import (
    create_image_from_base64,
    get_image,
    list_categories_and_tags,
    list_images,
    update_image,
)


logger = logging.getLogger(__name__)


_TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "image_library_list",
        "side_effect": "read",
        "description": (
            "列出 / 检索图片素材库的元数据记录（默认不返回 base64，避免拉爆上下文）。"
            "支持按关键词（命中 name + description）、tags（OR 语义）、category（精确）、"
            "only_unlabeled（缺 description / tags / category 任一）过滤。"
            "Skill 推荐场景：(1) 给聊天上下文找候选图：传 tags+category；"
            "(2) 给未打标图批量补元数据：only_unlabeled=true。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "q": {"type": "string", "description": "在 name + description 上做大小写不敏感的子串匹配"},
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "标签数组，命中任一返回（OR 语义）",
                },
                "category": {"type": "string", "description": "精确匹配某个分类"},
                "only_unlabeled": {
                    "type": "boolean",
                    "description": "True 时只返回 description / tags / category 任一为空的记录",
                },
                "enabled_only": {"type": "boolean", "description": "默认 true；false 时含已停用"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 500},
            },
        },
    },
    {
        "name": "image_library_get",
        "side_effect": "read",
        "description": (
            "拿单张图的完整记录。with_data=true 时返回 data_base64（外链类型则用 source_url），"
            "适合喂给 vision 模型分析画面内容。with_data=false 时只返回元数据，节省 token。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "image_id": {"type": "integer", "minimum": 1},
                "with_data": {"type": "boolean", "description": "默认 false。true 时附 base64 原图"},
            },
            "required": ["image_id"],
        },
    },
    {
        "name": "image_library_update_metadata",
        "side_effect": "write",
        "description": (
            "更新已存在图片的语义元数据（不改文件本身）。partial-update：参数传 null 表示不动，"
            "传空数组 / 空对象表示清空。overwrite=false 时只填**当前空**的字段，"
            "用于保护人工已编辑过的内容；overwrite=true（默认）会覆盖。"
            "Skill 自动打标时建议 overwrite=false 安全起见。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "image_id": {"type": "integer", "minimum": 1},
                "description": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "category": {"type": "string"},
                "ai_metadata": {"type": "object", "description": "AI 分析的结构化扩展信息"},
                "overwrite": {
                    "type": "boolean",
                    "description": "默认 true。false 时只填当前为空的字段",
                },
            },
            "required": ["image_id"],
        },
    },
    {
        "name": "image_library_upload",
        "side_effect": "write",
        "description": (
            "上传新图片（base64 编码字节）并一次性写入语义元数据。AI 自助上传场景常用："
            "Skill 拿到图 → vision 分析 → 直接带 description/tags/category 入库，避免后续打标往返。"
            "图片大小限制 5MB；mime_type 必须是 image/*。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "data_base64": {"type": "string", "description": "图片 base64 字节（不要带 data: URL 头也行，自动剥）"},
                "file_name": {"type": "string"},
                "mime_type": {"type": "string", "description": "默认 image/png"},
                "name": {"type": "string", "description": "运营备注名"},
                "description": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "category": {"type": "string"},
                "ai_metadata": {"type": "object"},
            },
            "required": ["data_base64"],
        },
    },
    {
        "name": "image_library_facets",
        "side_effect": "read",
        "description": (
            "返回当前已用的 categories（分类）和 tags（标签）池。Skill 给图打标 / 选标签前调一次，"
            "尽量复用已有词汇而不是造新词，避免标签碎片化。返回的两个字段都是排序后的字符串数组。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "enabled_only": {"type": "boolean", "description": "默认 true；false 时含已停用记录的标签"},
            },
        },
    },
]


def list_image_library_tool_specs() -> list[dict[str, Any]]:
    """给 mcp_adapter.TOOL_DEFS.extend(...) 用的 tool 规格快照。"""
    return list(_TOOL_SPECS)


# ---------- partial-update 辅助 ---------- #

def _filter_empty_only(*, image_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    """overwrite=false 时只保留当前为空的字段。

    description / category：当前为空字符串才填
    tags：当前为空数组才填
    ai_metadata：当前为空 dict 才填
    """
    current = get_image(int(image_id))
    if not current:
        raise ValueError(f"image_library id={image_id} not found")
    out: dict[str, Any] = {}
    if "description" in payload and not (current.get("description") or "").strip():
        out["description"] = payload["description"]
    if "tags" in payload and not (current.get("tags") or []):
        out["tags"] = payload["tags"]
    if "category" in payload and not (current.get("category") or "").strip():
        out["category"] = payload["category"]
    if "ai_metadata" in payload and not (current.get("ai_metadata") or {}):
        out["ai_metadata"] = payload["ai_metadata"]
    return out


# ---------- dispatcher ---------- #

def dispatch_image_library_tool(
    *,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """把 MCP tools/call 路由到 domain 函数。

    返回统一形态 ``{"ok": bool, "data": ...}``（出错时 ``{"ok": false, "error": str}``），
    跟 mcp_adapter 既有 cloud orchestrator dispatch 的语义保持一致。
    """
    args = arguments or {}
    try:
        if tool_name == "image_library_list":
            items = list_images(
                enabled_only=bool(args.get("enabled_only", True)),
                limit=int(args.get("limit") or 50),
                q=args.get("q") or None,
                tags=args.get("tags"),
                category=args.get("category") or None,
                only_unlabeled=bool(args.get("only_unlabeled", False)),
            )
            return {"ok": True, "items": items, "count": len(items)}

        if tool_name == "image_library_get":
            image_id = int(args.get("image_id") or 0)
            if not image_id:
                return {"ok": False, "error": "image_id is required"}
            item = get_image(image_id, include_data=bool(args.get("with_data", False)))
            if not item:
                return {"ok": False, "error": f"image_library id={image_id} not found"}
            return {"ok": True, "item": item}

        if tool_name == "image_library_update_metadata":
            image_id = int(args.get("image_id") or 0)
            if not image_id:
                return {"ok": False, "error": "image_id is required"}
            # 收集调用方实际传了哪些字段（None 表示不改，所以用 in args 判断）
            payload: dict[str, Any] = {}
            for key in ("description", "tags", "category", "ai_metadata"):
                if key in args:
                    payload[key] = args[key]
            if not payload:
                # 没传任何字段：直接返回现状，不算错
                item = get_image(image_id)
                if not item:
                    return {"ok": False, "error": f"image_library id={image_id} not found"}
                return {"ok": True, "item": item, "applied": []}
            overwrite = bool(args.get("overwrite", True))
            if not overwrite:
                payload = _filter_empty_only(image_id=image_id, payload=payload)
            applied = sorted(payload.keys())
            item = update_image(image_id, **payload)
            return {"ok": True, "item": item, "applied": applied}

        if tool_name == "image_library_upload":
            data_b64 = str(args.get("data_base64") or "")
            if not data_b64:
                return {"ok": False, "error": "data_base64 is required"}
            item = create_image_from_base64(
                data_base64=data_b64,
                file_name=str(args.get("file_name") or ""),
                mime_type=str(args.get("mime_type") or "image/png"),
                name=str(args.get("name") or ""),
                description=str(args.get("description") or ""),
                tags=args.get("tags"),
                category=str(args.get("category") or ""),
                ai_metadata=args.get("ai_metadata"),
            )
            return {"ok": True, "item": item}

        if tool_name == "image_library_facets":
            facets = list_categories_and_tags(
                enabled_only=bool(args.get("enabled_only", True))
            )
            return {"ok": True, **facets}

        return {"ok": False, "error": f"unknown tool: {tool_name}"}
    except ValueError as exc:
        # domain 层抛 ValueError 表示参数 / 状态非法，原样回传给 Skill 让它修正
        return {"ok": False, "error": str(exc)}
    except Exception as exc:
        # 兜底：写日志但不暴露内部 trace 给 Skill
        logger.exception("image_library MCP dispatch failed tool=%s", tool_name)
        return {"ok": False, "error": f"internal error: {exc}"}


__all__ = [
    "list_image_library_tool_specs",
    "dispatch_image_library_tool",
]
