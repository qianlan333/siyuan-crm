from __future__ import annotations

from flask import Response, jsonify, request

from ..domains.segments import service as segments_service


def cloud_orchestrator_list_segments() -> Response:
    status = (request.args.get("status") or "active").strip()
    keyword = (request.args.get("keyword") or "").strip()
    limit = int(request.args.get("limit") or 200)
    rows = segments_service.list_segments(
        status=status,
        keyword=keyword,
        source_type=(request.args.get("source_type") or "").strip(),
        limit=limit,
    )
    return jsonify({"ok": True, "segments": rows})


def cloud_orchestrator_get_segment(segment_code: str) -> Response:
    seg = segments_service.get_segment(segment_code=segment_code)
    if not seg:
        return jsonify({"ok": False, "error": "segment_not_found"}), 404
    return jsonify({"ok": True, "segment": seg})


def cloud_orchestrator_preview_segment(segment_code: str) -> Response:
    try:
        result = segments_service.preview_segment_members(
            segment_code=segment_code,
            limit=int(request.args.get("limit") or 50),
        )
        return jsonify({"ok": True, "preview": result})
    except (ValueError, LookupError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


__all__ = [
    "cloud_orchestrator_get_segment",
    "cloud_orchestrator_list_segments",
    "cloud_orchestrator_preview_segment",
]
