from __future__ import annotations

import logging
from typing import Any

from flask import jsonify, request

from ..domains.tags import service as tags_service
from ..wecom_client import WeComClientError

logger = logging.getLogger("wecom_api")


def _json_payload() -> dict[str, Any]:
    return dict(request.get_json(silent=True) or {})


def _message_from_wecom_error(exc: WeComClientError, fallback: str) -> str:
    category = str(exc.category or "").strip()
    if category in {"token"}:
        return "企微标签同步失败，请检查企微配置或稍后重试。"
    if "权限" in category:
        return "企微接口权限不足，请检查应用权限后重试。"
    if "secret" in category or "配置" in category:
        return "企微配置不可用，请检查企微配置后重试。"
    return fallback


def _admin_tag_error_response(exc: WeComClientError, *, fallback: str):
    logger.error(
        "admin wecom tag api failed stage=%s category=%s errcode=%s errmsg=%s",
        exc.stage or "",
        exc.category or "",
        (exc.payload or {}).get("errcode"),
        (exc.payload or {}).get("errmsg") or str(exc),
    )
    return jsonify({"ok": False, "error": _message_from_wecom_error(exc, fallback)}), 502


def _value_error_response(exc: ValueError):
    return jsonify({"ok": False, "error": str(exc)}), 400


def _ensure_can_create_tag() -> tuple[bool, str | None]:
    catalog = tags_service.list_wecom_tag_catalog()
    if int(catalog.get("total_tags") or 0) >= int(catalog.get("tag_limit") or 0):
        return False, "标签数量已达到 1000 上限，不能继续新增标签。"
    return True, None


def admin_wecom_tag_management_payload():
    try:
        catalog = tags_service.list_wecom_tag_catalog()
        return jsonify({"ok": True, **catalog})
    except WeComClientError as exc:
        return _admin_tag_error_response(exc, fallback="企微标签同步失败，请检查企微配置或稍后重试。")


def admin_create_wecom_tag_group():
    payload = _json_payload()
    try:
        can_create, reason = _ensure_can_create_tag()
        if not can_create:
            return jsonify({"ok": False, "error": reason}), 400
        result = tags_service.create_wecom_tag_group(
            group_name=payload.get("group_name", ""),
            first_tag_name=payload.get("first_tag_name", ""),
        )
        return jsonify({"ok": True, "result": result})
    except ValueError as exc:
        return _value_error_response(exc)
    except WeComClientError as exc:
        return _admin_tag_error_response(exc, fallback="标签组创建失败，请检查名称是否重复或企微接口权限。")


def admin_update_wecom_tag_group(group_id: str):
    payload = _json_payload()
    try:
        result = tags_service.update_wecom_tag_group(group_id=group_id, group_name=payload.get("group_name", ""))
        return jsonify({"ok": True, "result": result})
    except ValueError as exc:
        return _value_error_response(exc)
    except WeComClientError as exc:
        return _admin_tag_error_response(exc, fallback="标签组更新失败，请检查企微接口权限或名称是否重复。")


def admin_delete_wecom_tag_group(group_id: str):
    try:
        result = tags_service.delete_wecom_tag_group(group_id=group_id)
        return jsonify({"ok": True, "result": result})
    except ValueError as exc:
        return _value_error_response(exc)
    except WeComClientError as exc:
        return _admin_tag_error_response(exc, fallback="标签组删除失败，请稍后重试。")


def admin_create_wecom_tag():
    payload = _json_payload()
    try:
        can_create, reason = _ensure_can_create_tag()
        if not can_create:
            return jsonify({"ok": False, "error": reason}), 400
        result = tags_service.create_wecom_tag_in_group(
            group_id=payload.get("group_id", ""),
            group_name=payload.get("group_name", ""),
            tag_name=payload.get("tag_name", ""),
        )
        return jsonify({"ok": True, "result": result})
    except ValueError as exc:
        return _value_error_response(exc)
    except WeComClientError as exc:
        return _admin_tag_error_response(exc, fallback="标签创建失败，请检查名称是否重复或企微接口权限。")


def admin_update_wecom_tag(tag_id: str):
    payload = _json_payload()
    try:
        result = tags_service.update_wecom_tag(tag_id=tag_id, tag_name=payload.get("tag_name", ""))
        return jsonify({"ok": True, "result": result})
    except ValueError as exc:
        return _value_error_response(exc)
    except WeComClientError as exc:
        return _admin_tag_error_response(exc, fallback="标签更新失败，请检查名称是否重复或企微接口权限。")


def admin_delete_wecom_tag(tag_id: str):
    try:
        result = tags_service.delete_wecom_tag(tag_id=tag_id)
        return jsonify({"ok": True, "result": result})
    except ValueError as exc:
        return _value_error_response(exc)
    except WeComClientError as exc:
        return _admin_tag_error_response(exc, fallback="标签删除失败，请稍后重试。")


def register_routes(bp):
    bp.route("/api/admin/wecom/tags", methods=["GET"])(admin_wecom_tag_management_payload)
    bp.route("/api/admin/wecom/tag-groups", methods=["POST"])(admin_create_wecom_tag_group)
    bp.route("/api/admin/wecom/tag-groups/<group_id>", methods=["PUT"])(admin_update_wecom_tag_group)
    bp.route("/api/admin/wecom/tag-groups/<group_id>", methods=["DELETE"])(admin_delete_wecom_tag_group)
    bp.route("/api/admin/wecom/tags", methods=["POST"])(admin_create_wecom_tag)
    bp.route("/api/admin/wecom/tags/<tag_id>", methods=["PUT"])(admin_update_wecom_tag)
    bp.route("/api/admin/wecom/tags/<tag_id>", methods=["DELETE"])(admin_delete_wecom_tag)
