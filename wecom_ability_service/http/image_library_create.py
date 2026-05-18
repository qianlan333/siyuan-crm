from __future__ import annotations

from flask import Response, jsonify, request

from ..domains import image_library
from .image_library_support import _form_metadata_kwargs, _json_metadata_kwargs


def admin_image_library_upload() -> Response:
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
