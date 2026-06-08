from __future__ import annotations

from flask import Response, jsonify, request

from ..domains import image_library
from .image_library_support import _form_metadata_kwargs


def api_admin_image_library_upload() -> Response:
    file = request.files.get("image")
    if not file or not file.filename:
        return jsonify({"ok": False, "error": "missing image"}), 400
    try:
        item = image_library.create_image_from_upload(
            file_bytes=file.read(),
            file_name=file.filename,
            mime_type=file.mimetype or "",
            name=(request.form.get("name") or file.filename).strip(),
            **_form_metadata_kwargs(),
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "item": item}), 201


def register_routes(bp) -> None:
    bp.route("/api/admin/image-library/upload", methods=["POST"])(api_admin_image_library_upload)

