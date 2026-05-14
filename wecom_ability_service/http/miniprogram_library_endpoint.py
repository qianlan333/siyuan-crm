"""小程序素材库 admin 端点。

CRUD 接口给运营人员配置可被各群发链路（AI 群发 / 自动化工作流 /
SOP / 欢迎语 / 手动 user_ops）引用的小程序卡片素材。
"""
from __future__ import annotations

import logging
from typing import Any

from flask import Response, jsonify, render_template, request

from ..domains import miniprogram_library
from ..domains.admin_dashboard.service import build_admin_shell_status, list_admin_navigation


logger = logging.getLogger(__name__)


def _serialize_for_api(item: dict[str, Any]) -> dict[str, Any]:
    if not item:
        return {}
    payload = dict(item)
    payload.pop("thumb_image_base64", None)
    return payload


def admin_miniprogram_library_workspace() -> Response:
    try:
        shell_status = build_admin_shell_status()
    except Exception:  # pragma: no cover - defensive
        shell_status = None
    return render_template(
        "admin_console/miniprogram_library.html",
        page_title="小程序素材库",
        page_summary="集中维护可被群发引用的小程序卡片：appid、跳转路径、标题、缩略图。",
        nav_items=list_admin_navigation("miniprogram_library"),
        shell_status=shell_status,
        show_shell_meta=False,
        show_page_header=True,
        breadcrumbs=[
            {"label": "客户管理后台", "href": "/admin"},
            {"label": "素材库"},
        ],
        page_actions=[],
    )


def admin_miniprogram_library_list() -> Response:
    enabled_only = request.args.get("enabled_only")
    enabled_only_flag = True
    if enabled_only is not None:
        enabled_only_flag = str(enabled_only).strip().lower() not in ("0", "false", "no", "")
    items = miniprogram_library.list_miniprograms(enabled_only=enabled_only_flag)
    return jsonify({"ok": True, "items": [_serialize_for_api(it) for it in items]})


def admin_miniprogram_library_get(library_id: int) -> Response:
    item = miniprogram_library.get_miniprogram(int(library_id))
    if not item:
        return jsonify({"ok": False, "error": "not_found"}), 404
    return jsonify({"ok": True, "item": _serialize_for_api(item)})


def admin_miniprogram_library_create() -> Response:
    body = request.get_json(silent=True) or {}
    try:
        item = miniprogram_library.create_miniprogram(body)
        return jsonify({"ok": True, "item": _serialize_for_api(item)})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:  # pragma: no cover - defensive production envelope
        logger.exception("miniprogram_library_create failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


def admin_miniprogram_library_update(library_id: int) -> Response:
    body = request.get_json(silent=True) or {}
    try:
        item = miniprogram_library.update_miniprogram(int(library_id), body)
        return jsonify({"ok": True, "item": _serialize_for_api(item)})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:  # pragma: no cover - defensive production envelope
        logger.exception("miniprogram_library_update failed library_id=%s", library_id)
        return jsonify({"ok": False, "error": str(exc)}), 500


def admin_miniprogram_library_delete(library_id: int) -> Response:
    ok = miniprogram_library.delete_miniprogram(int(library_id))
    return jsonify({"ok": ok})


def admin_miniprogram_library_test_resolve(library_id: int) -> Response:
    try:
        media_id = miniprogram_library.resolve_thumb_media_id(int(library_id))
        return jsonify({"ok": True, "thumb_media_id": media_id})
    except (ValueError, RuntimeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def register_routes(bp) -> None:
    bp.route("/admin/miniprogram-library", methods=["GET"])(admin_miniprogram_library_workspace)
    bp.route("/api/admin/miniprogram-library", methods=["GET"])(admin_miniprogram_library_list)
    bp.route("/api/admin/miniprogram-library", methods=["POST"])(admin_miniprogram_library_create)
    bp.route("/api/admin/miniprogram-library/<int:library_id>", methods=["GET"])(
        admin_miniprogram_library_get
    )
    bp.route("/api/admin/miniprogram-library/<int:library_id>", methods=["PUT"])(
        admin_miniprogram_library_update
    )
    bp.route("/api/admin/miniprogram-library/<int:library_id>", methods=["DELETE"])(
        admin_miniprogram_library_delete
    )
    bp.route(
        "/api/admin/miniprogram-library/<int:library_id>/test-resolve",
        methods=["POST"],
    )(admin_miniprogram_library_test_resolve)


__all__ = ["register_routes"]
