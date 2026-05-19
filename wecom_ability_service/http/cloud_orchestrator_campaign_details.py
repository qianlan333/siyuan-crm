from __future__ import annotations

from flask import Response, jsonify, request

from ..domains.campaigns import service as campaign_service


def cloud_orchestrator_delete_campaign_step(campaign_code: str, step_index: str) -> Response:
    camp = campaign_service.get_campaign(campaign_code=campaign_code)
    if not camp:
        return jsonify({"ok": False, "error": "campaign_not_found"}), 404
    try:
        result = campaign_service.delete_campaign_step(
            campaign_id=int(camp["id"]),
            step_index=int(step_index),
        )
        return jsonify({"ok": True, **result})
    except (LookupError, PermissionError, ValueError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def cloud_orchestrator_add_campaign_step(campaign_code: str) -> Response:
    camp = campaign_service.get_campaign(campaign_code=campaign_code)
    if not camp:
        return jsonify({"ok": False, "error": "campaign_not_found"}), 404
    body = request.get_json(silent=True) or {}
    seg_id = int(body.get("campaign_segment_id") or 0)
    if not seg_id:
        return jsonify({"ok": False, "error": "campaign_segment_id required"}), 400
    try:
        result = campaign_service.append_campaign_step(
            campaign_id=int(camp["id"]),
            campaign_segment_id=seg_id,
            day_offset=int(body.get("day_offset") or 0),
            send_time=str(body.get("send_time") or "10:00"),
            content_text=str(body.get("content_text") or ""),
            stop_on_reply=bool(body.get("stop_on_reply", True)),
        )
        return jsonify({"ok": True, **result})
    except (LookupError, PermissionError, ValueError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def cloud_orchestrator_update_campaign_step(campaign_code: str, step_index: str) -> Response:
    camp = campaign_service.get_campaign(campaign_code=campaign_code)
    if not camp:
        return jsonify({"ok": False, "error": "campaign_not_found"}), 404
    body = request.get_json(silent=True) or {}
    try:
        result = campaign_service.update_campaign_step(
            campaign_id=int(camp["id"]),
            step_index=int(step_index),
            content_text=body.get("content_text"),
            send_time=body.get("send_time"),
            day_offset=body.get("day_offset"),
            stop_on_reply=body.get("stop_on_reply"),
            image_library_ids=body.get("image_library_ids"),
            image_media_ids=body.get("image_media_ids"),
            miniprogram_library_ids=body.get("miniprogram_library_ids"),
            attachment_library_ids=body.get("attachment_library_ids"),
        )
        return jsonify({"ok": True, **result})
    except (LookupError, PermissionError, ValueError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def cloud_orchestrator_list_campaign_members(campaign_code: str) -> Response:
    camp = campaign_service.get_campaign(campaign_code=campaign_code)
    if not camp:
        return jsonify({"ok": False, "error": "campaign_not_found"}), 404
    status = (request.args.get("status") or "").strip()
    limit = int(request.args.get("limit") or 100)
    offset = int(request.args.get("offset") or 0)
    result = campaign_service.list_campaign_members(
        campaign_id=int(camp["id"]),
        status=status,
        limit=limit,
        offset=offset,
    )
    return jsonify({"ok": True, **result})


__all__ = [
    "cloud_orchestrator_add_campaign_step",
    "cloud_orchestrator_delete_campaign_step",
    "cloud_orchestrator_list_campaign_members",
    "cloud_orchestrator_update_campaign_step",
]
