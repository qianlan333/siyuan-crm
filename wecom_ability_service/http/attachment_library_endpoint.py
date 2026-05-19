"""附件素材库 admin 端点。"""
from __future__ import annotations

from typing import Any

from flask import Response, jsonify, render_template, request

from ..domains import attachment_library
from ..domains.admin_dashboard.service import build_admin_shell_status, list_admin_navigation
from ..domains.wecom_media_limits import WECOM_ATTACHMENT_ALLOWED_EXTENSIONS, WECOM_ATTACHMENT_MAX_MB
from .image_library_endpoint import _parse_bool_arg, _parse_tags_arg


def admin_attachment_library_workspace() -> Response:
    try:
        shell_status = build_admin_shell_status()
    except Exception:  # pragma: no cover - defensive
        shell_status = None
    return render_template(
        "admin_console/attachment_library.html",
        page_title="附件素材库",
        page_summary="集中维护欢迎语可发送的 PDF / 文档 / 表格等附件，发送前自动上传企微并缓存 media_id。",
        nav_items=list_admin_navigation("attachment_library"),
        shell_status=shell_status,
        show_shell_meta=False,
        show_page_header=True,
        breadcrumbs=[
            {"label": "客户管理后台", "href": "/admin"},
            {"label": "附件素材库"},
        ],
        page_actions=[],
        allowed_extensions=", ".join(sorted(WECOM_ATTACHMENT_ALLOWED_EXTENSIONS)),
        max_mb=WECOM_ATTACHMENT_MAX_MB,
    )


def _metadata_kwargs() -> dict[str, Any]:
    return {
        "description": (request.form.get("description") or "").strip(),
        "tags": _parse_tags_arg(request.form.get("tags")),
    }


def admin_attachment_library_list() -> Response:
    items = attachment_library.list_attachments(
        enabled_only=_parse_bool_arg(request.args.get("enabled_only"), default=True),
        limit=int(request.args.get("limit") or 200),
        q=request.args.get("q") or None,
        tags=_parse_tags_arg(request.args.get("tags")),
    )
    return jsonify({"ok": True, "items": items})


def admin_attachment_library_get(attachment_id: int) -> Response:
    item = attachment_library.get_attachment(int(attachment_id), include_data=False)
    if not item:
        return jsonify({"ok": False, "error": "not_found"}), 404
    return jsonify({"ok": True, "item": item})


def admin_attachment_library_upload() -> Response:
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"ok": False, "error": "missing file"}), 400
    try:
        item = attachment_library.create_attachment_from_upload(
            file_bytes=file.read(),
            file_name=file.filename,
            mime_type=(file.mimetype or "").lower(),
            name=(request.form.get("name") or "").strip(),
            **_metadata_kwargs(),
        )
        return jsonify({"ok": True, "item": item})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def admin_attachment_library_update(attachment_id: int) -> Response:
    body = request.get_json(silent=True) or {}
    try:
        item = attachment_library.update_attachment(
            int(attachment_id),
            name=body.get("name"),
            enabled=body.get("enabled"),
            description=body.get("description"),
            tags=body.get("tags"),
        )
        return jsonify({"ok": True, "item": item})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def admin_attachment_library_delete(attachment_id: int) -> Response:
    force = _parse_bool_arg(request.args.get("force"), default=False)
    try:
        return jsonify(attachment_library.delete_attachment(int(attachment_id), force=force))
    except ValueError as exc:
        status = 404 if "not found" in str(exc) else 409
        refs = attachment_library.find_attachment_references(int(attachment_id)) if status == 409 else {}
        return jsonify({"ok": False, "error": str(exc), "references": refs}), status


def admin_attachment_library_references(attachment_id: int) -> Response:
    return jsonify({"ok": True, "references": attachment_library.find_attachment_references(int(attachment_id))})


def admin_attachment_library_test_resolve(attachment_id: int) -> Response:
    try:
        media_id = attachment_library.resolve_attachment_media_id(int(attachment_id))
        return jsonify({"ok": True, "media_id": media_id})
    except (ValueError, RuntimeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def register_routes(bp) -> None:
    bp.route("/admin/attachment-library", methods=["GET"])(admin_attachment_library_workspace)
    bp.route("/api/admin/attachment-library", methods=["GET"])(admin_attachment_library_list)
    bp.route("/api/admin/attachment-library/upload", methods=["POST"])(admin_attachment_library_upload)
    bp.route("/api/admin/attachment-library/<int:attachment_id>", methods=["GET"])(admin_attachment_library_get)
    bp.route("/api/admin/attachment-library/<int:attachment_id>", methods=["PUT"])(admin_attachment_library_update)
    bp.route("/api/admin/attachment-library/<int:attachment_id>", methods=["DELETE"])(admin_attachment_library_delete)
    bp.route("/api/admin/attachment-library/<int:attachment_id>/references", methods=["GET"])(admin_attachment_library_references)
    bp.route("/api/admin/attachment-library/<int:attachment_id>/test-resolve", methods=["POST"])(admin_attachment_library_test_resolve)


__all__ = ["register_routes"]
