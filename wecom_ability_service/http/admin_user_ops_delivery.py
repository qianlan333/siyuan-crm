from __future__ import annotations

import base64
import json

from flask import jsonify, request

from ..domains.tasks.private_message import MAX_PRIVATE_MESSAGE_IMAGES
from ..domains.user_ops.page_service import (
    execute_user_ops_batch_send,
    get_user_ops_send_record_detail,
    list_user_ops_send_records,
    preview_user_ops_batch_send,
    refresh_user_ops_send_record_status,
    set_user_ops_do_not_disturb,
)
from ..domains.wecom_media_limits import validate_wecom_image_upload
from ..wecom_client import WeComClientError
from .common import _coerce_request_bool, _wecom_error_response


def _parse_json_form_field(field_name: str, default):
    raw = str(request.form.get(field_name) or "").strip()
    if not raw:
        return default
    try:
        return json.loads(raw)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be valid json") from exc


def _normalize_one_time_batch_send_images():
    files = [item for item in list(request.files.getlist("images") or []) if getattr(item, "filename", "")]
    if len(files) > MAX_PRIVATE_MESSAGE_IMAGES:
        raise ValueError(f"at most {MAX_PRIVATE_MESSAGE_IMAGES} images are allowed")

    images = []
    for index, file_storage in enumerate(files, start=1):
        file_name = str(getattr(file_storage, "filename", "") or f"image-{index}.png").strip() or f"image-{index}.png"
        mime_type = str(getattr(file_storage, "mimetype", "") or "").strip().lower()
        if not mime_type.startswith("image/"):
            raise ValueError("only image files are allowed")
        file_bytes = file_storage.read()
        content_type = validate_wecom_image_upload(
            file_bytes,
            file_name=file_name,
            mime_type=mime_type,
        )
        images.append(
            {
                "file_name": file_name,
                "content_type": content_type,
                "data_base64": base64.b64encode(file_bytes).decode("ascii"),
            }
        )
    return images


def _batch_send_payload_from_request() -> dict:
    if request.is_json:
        return request.get_json(silent=True) or {}

    payload = {
        "selection_mode": str(request.form.get("selection_mode") or "").strip(),
        "content": str(request.form.get("content") or "").strip(),
        "include_do_not_disturb": _coerce_request_bool(request.form.get("include_do_not_disturb"), default=False),
        "confirm": _coerce_request_bool(request.form.get("confirm"), default=False),
        "operator": str(request.form.get("operator") or "").strip(),
        "filters": _parse_json_form_field("filters_json", {}),
        "selected_ids": _parse_json_form_field("selected_ids_json", []),
        "excluded_ids": _parse_json_form_field("excluded_ids_json", []),
    }
    images = _normalize_one_time_batch_send_images()
    if images:
        payload["images"] = images
    attachments = _parse_json_form_field("attachments_json", [])
    if attachments:
        payload["attachments"] = attachments
    return payload


def admin_user_ops_do_not_disturb():
    payload_json = request.get_json(silent=True) or {}
    try:
        payload = set_user_ops_do_not_disturb(payload_json)
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **payload})


def admin_user_ops_batch_send_preview():
    try:
        payload_json = _batch_send_payload_from_request()
        payload = preview_user_ops_batch_send(payload_json)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **payload})


def admin_user_ops_batch_send_execute():
    try:
        payload_json = _batch_send_payload_from_request()
        payload = execute_user_ops_batch_send(payload_json)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except WeComClientError as exc:
        return _wecom_error_response(exc)
    return jsonify({"ok": True, **payload})


def admin_user_ops_send_records():
    try:
        limit = int(request.args.get("limit", "20").strip() or "20")
        offset = int(request.args.get("offset", "0").strip() or "0")
    except ValueError:
        return jsonify({"ok": False, "error": "limit and offset must be integers"}), 400
    payload = list_user_ops_send_records(limit=limit, offset=offset)
    return jsonify({"ok": True, **payload})


def admin_user_ops_send_record_detail(record_id: int):
    try:
        payload = get_user_ops_send_record_detail(record_id)
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, **payload})


def admin_user_ops_send_record_refresh(record_id: int):
    try:
        payload = refresh_user_ops_send_record_status(record_id)
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, **payload})


def register_routes(bp):
    bp.route('/api/admin/user-ops/do-not-disturb', methods=['POST'])(admin_user_ops_do_not_disturb)
    bp.route('/api/admin/user-ops/batch-send/preview', methods=['POST'])(admin_user_ops_batch_send_preview)
    bp.route('/api/admin/user-ops/batch-send/execute', methods=['POST'])(admin_user_ops_batch_send_execute)
    bp.route('/api/admin/user-ops/send-records', methods=['GET'])(admin_user_ops_send_records)
    bp.route('/api/admin/user-ops/send-records/<int:record_id>', methods=['GET'])(admin_user_ops_send_record_detail)
    bp.route('/api/admin/user-ops/send-records/<int:record_id>/refresh', methods=['POST'])(admin_user_ops_send_record_refresh)
