"""图片素材库 admin 端点。

集中管理被各处复用的图片：小程序卡片缩略图、campaign 群发配图、欢迎语 / SOP
配图等。前端有专门的「图片素材库」管理页，每个需要选图的位置（小程序卡片
表单、step 编辑表单、群发任务表单）都可以打开同一个 picker 复用素材库。
"""
from __future__ import annotations

import logging
from typing import Any

from flask import Response, jsonify, render_template, request

from ..domains import image_library
from ..domains.admin_dashboard.service import build_admin_shell_status, list_admin_navigation


logger = logging.getLogger(__name__)


def admin_image_library_workspace() -> Response:
    try:
        shell_status = build_admin_shell_status()
    except Exception:  # pragma: no cover - defensive
        shell_status = None
    return render_template(
        "admin_console/image_library.html",
        page_title="图片素材库",
        page_summary="集中维护可被群发 / 卡片 / 自动化欢迎语等场景引用的图片，支持上传和外链。",
        nav_items=list_admin_navigation("image_library"),
        shell_status=shell_status,
        show_shell_meta=False,
        show_page_header=True,
        breadcrumbs=[
            {"label": "客户管理后台", "href": "/admin"},
            {"label": "图片素材库"},
        ],
        page_actions=[],
    )


def _parse_bool_arg(raw: Any, *, default: bool = False) -> bool:
    if raw is None:
        return default
    return str(raw).strip().lower() not in ("0", "false", "no", "")


def _parse_tags_arg(raw: Any) -> list[str]:
    """从 query string / form 解析 tags：支持逗号分隔字符串 或 JSON 数组字符串。

    domain 层 ``_normalize_tags`` 也认这两种，但前置在这里解 JSON 形态可以
    让多 tag 包含逗号的边缘 case 正确（运营少见，但留口子）。
    """
    if raw is None:
        return []
    text = str(raw).strip()
    if not text:
        return []
    if text.startswith("["):
        import json
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(s) for s in parsed]
        except (TypeError, ValueError):
            pass
    return [s for s in (p.strip() for p in text.split(",")) if s]


def admin_image_library_list() -> Response:
    enabled_only_flag = _parse_bool_arg(request.args.get("enabled_only"), default=True)
    only_unlabeled_flag = _parse_bool_arg(request.args.get("only_unlabeled"), default=False)
    limit = int(request.args.get("limit") or 200)
    items = image_library.list_images(
        enabled_only=enabled_only_flag,
        limit=limit,
        q=request.args.get("q") or None,
        tags=_parse_tags_arg(request.args.get("tags")),
        category=request.args.get("category") or None,
        only_unlabeled=only_unlabeled_flag,
    )
    return jsonify({"ok": True, "items": items})


def admin_image_library_facets() -> Response:
    """返回当前已启用图片中存在的分类和标签池，给前端筛选器和 Skill 用。"""
    enabled_only_flag = _parse_bool_arg(request.args.get("enabled_only"), default=True)
    facets = image_library.list_categories_and_tags(enabled_only=enabled_only_flag)
    return jsonify({"ok": True, **facets})


def admin_image_library_get(image_id: int) -> Response:
    """详情接口默认带 data_base64，给前端 thumbnail 预览用。"""
    item = image_library.get_image(int(image_id), include_data=True)
    if not item:
        return jsonify({"ok": False, "error": "not_found"}), 404
    return jsonify({"ok": True, "item": item})


def _form_metadata_kwargs() -> dict[str, Any]:
    """从 multipart form 提 description/tags/category/ai_metadata。

    tags 接受逗号分隔或 JSON 数组字符串（``_parse_tags_arg`` 处理）。
    ai_metadata 接受 JSON object 字符串，解析失败留给 domain 层标准化为 ``{}``。
    """
    return {
        "description": (request.form.get("description") or "").strip(),
        "tags": _parse_tags_arg(request.form.get("tags")),
        "category": (request.form.get("category") or "").strip(),
        "ai_metadata": request.form.get("ai_metadata"),
    }


def _json_metadata_kwargs(body: dict) -> dict[str, Any]:
    """从 JSON body 提 description/tags/category/ai_metadata，原样透传给 domain 层。"""
    return {
        "description": str(body.get("description") or ""),
        "tags": body.get("tags"),
        "category": str(body.get("category") or ""),
        "ai_metadata": body.get("ai_metadata"),
    }


def admin_image_library_upload() -> Response:
    """multipart 上传：``image`` 文件 + 可选 ``name`` / ``description`` /
    ``tags`` (csv 或 JSON) / ``category`` / ``ai_metadata`` (JSON)。"""
    file = request.files.get("image")
    if not file or not file.filename:
        return jsonify({"ok": False, "error": "missing image"}), 400
    file_bytes = file.read()
    name = (request.form.get("name") or "").strip()
    try:
        item = image_library.create_image_from_upload(
            file_bytes=file_bytes,
            file_name=file.filename,
            mime_type=(file.mimetype or "").lower(),
            name=name,
            **_form_metadata_kwargs(),
        )
        return jsonify({"ok": True, "item": item})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def admin_image_library_create_url() -> Response:
    """JSON body：``{url, name?, description?, tags?, category?, ai_metadata?}``。"""
    body = request.get_json(silent=True) or {}
    try:
        item = image_library.create_image_from_url(
            url=str(body.get("url") or ""),
            name=str(body.get("name") or ""),
            **_json_metadata_kwargs(body),
        )
        return jsonify({"ok": True, "item": item})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def admin_image_library_create_base64() -> Response:
    """JSON body：``{data_base64, file_name?, mime_type?, name?, description?,
    tags?, category?, ai_metadata?}``。"""
    body = request.get_json(silent=True) or {}
    try:
        item = image_library.create_image_from_base64(
            data_base64=str(body.get("data_base64") or ""),
            file_name=str(body.get("file_name") or ""),
            mime_type=str(body.get("mime_type") or "image/png"),
            name=str(body.get("name") or ""),
            **_json_metadata_kwargs(body),
        )
        return jsonify({"ok": True, "item": item})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def admin_image_library_update(image_id: int) -> Response:
    """JSON body：``{name?, enabled?, description?, tags?, category?, ai_metadata?}``。

    传 ``null`` 表示不改；要清空 description/category 传空串，要清空 tags/
    ai_metadata 传 ``[]``/``{}``。
    """
    body = request.get_json(silent=True) or {}
    try:
        item = image_library.update_image(
            int(image_id),
            name=body.get("name"),
            enabled=body.get("enabled"),
            description=body.get("description"),
            tags=body.get("tags"),
            category=body.get("category"),
            ai_metadata=body.get("ai_metadata"),
        )
        return jsonify({"ok": True, "item": item})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def admin_image_library_delete(image_id: int) -> Response:
    """硬删 image_library 记录。

    - 默认拒绝有引用的删除，返回 409 + ``references`` 列表给前端展示
    - ``?force=true`` 强删 + cascade 清理引用方
    """
    force = _parse_bool_arg(request.args.get("force"), default=False)
    try:
        result = image_library.delete_image(int(image_id), force=force)
        return jsonify(result)
    except ValueError as exc:
        msg = str(exc)
        # 区分"找不到记录"（404）和"被引用拒删"（409）
        if "not found" in msg:
            return jsonify({"ok": False, "error": msg}), 404
        # 把引用列表也带上，前端弹二次确认时直接展示
        try:
            refs = image_library.find_image_references(int(image_id))
        except Exception:  # pragma: no cover - defensive
            refs = {}
        return jsonify({"ok": False, "error": msg, "references": refs}), 409


def admin_image_library_references(image_id: int) -> Response:
    """查这张图被哪些表引用，给前端在删除前预览用。"""
    refs = image_library.find_image_references(int(image_id))
    return jsonify({"ok": True, "references": refs})


def admin_image_library_test_resolve(image_id: int) -> Response:
    try:
        media_id = image_library.resolve_image_media_id(int(image_id))
        return jsonify({"ok": True, "media_id": media_id})
    except (ValueError, RuntimeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def register_routes(bp) -> None:
    bp.route("/admin/image-library", methods=["GET"])(admin_image_library_workspace)
    bp.route("/api/admin/image-library", methods=["GET"])(admin_image_library_list)
    bp.route("/api/admin/image-library/facets", methods=["GET"])(admin_image_library_facets)
    bp.route("/api/admin/image-library/upload", methods=["POST"])(admin_image_library_upload)
    bp.route("/api/admin/image-library/from-url", methods=["POST"])(admin_image_library_create_url)
    bp.route("/api/admin/image-library/from-base64", methods=["POST"])(admin_image_library_create_base64)
    bp.route("/api/admin/image-library/<int:image_id>", methods=["GET"])(admin_image_library_get)
    bp.route("/api/admin/image-library/<int:image_id>", methods=["PUT"])(admin_image_library_update)
    bp.route("/api/admin/image-library/<int:image_id>", methods=["DELETE"])(admin_image_library_delete)
    bp.route("/api/admin/image-library/<int:image_id>/references", methods=["GET"])(admin_image_library_references)
    bp.route(
        "/api/admin/image-library/<int:image_id>/test-resolve",
        methods=["POST"],
    )(admin_image_library_test_resolve)


__all__ = ["register_routes"]
