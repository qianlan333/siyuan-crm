from __future__ import annotations

from flask import Response, jsonify, request

from ..domains.cloud_orchestrator import media as media_module


def cloud_orchestrator_upload_image() -> Response:
    """运营本地选图 -> 上传到企微素材库 -> 返回 media_id 给前端写进 step。"""

    file = request.files.get("image")
    if not file or not file.filename:
        return jsonify({"ok": False, "error": "missing image"}), 400
    try:
        payload = media_module.upload_cloud_orchestrator_image(
            file_name=file.filename,
            file_bytes=file.read(),
            content_type=file.mimetype or "",
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except media_module.CloudOrchestratorMediaUploadError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 502
    return jsonify({"ok": True, **payload})


__all__ = ["cloud_orchestrator_upload_image"]
