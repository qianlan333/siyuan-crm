from __future__ import annotations

from flask import jsonify, request

from ..domains.automation_conversion.focus_send_service import create_focus_send_batch
from ..domains.automation_conversion.manual_send_service import (
    preview_stage_manual_send,
    send_stage_manual_message,
)
from ..domains.automation_conversion.service import (
    get_member_detail,
    mark_won,
    put_in_pool,
    push_openclaw,
    remove_from_pool,
    set_follow_type,
    unmark_won,
)
from ._routes_helpers import _operator_from_request, _query_text
from .automation_conversion_uploads import _stage_send_images_from_request


def api_admin_automation_conversion_member():
    external_contact_id = _query_text("external_contact_id")
    phone = _query_text("phone")
    if not external_contact_id and not phone:
        return jsonify({"ok": False, "error": "external_contact_id or phone is required"}), 400
    return jsonify({"ok": True, "detail": get_member_detail(external_contact_id=external_contact_id, phone=phone)})


def _json_action_payload() -> dict[str, str]:
    payload = request.get_json(silent=True) or {}
    return {
        "external_contact_id": str(payload.get("external_contact_id") or "").strip(),
        "phone": str(payload.get("phone") or "").strip(),
        "operator_id": _operator_from_request(),
    }


def _run_member_action(action_fn):
    payload = _json_action_payload()
    try:
        result = action_fn(**payload)
        return jsonify({"ok": True, **result})
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def api_admin_automation_conversion_put_in_pool():
    return _run_member_action(put_in_pool)


def api_admin_automation_conversion_remove_from_pool():
    return _run_member_action(remove_from_pool)


def api_admin_automation_conversion_set_focus():
    return _run_member_action(lambda **payload: set_follow_type(**payload, follow_type="focus"))


def api_admin_automation_conversion_set_normal():
    return _run_member_action(lambda **payload: set_follow_type(**payload, follow_type="normal"))


def api_admin_automation_conversion_mark_won():
    return _run_member_action(mark_won)


def api_admin_automation_conversion_unmark_won():
    return _run_member_action(unmark_won)


def api_admin_automation_conversion_push_openclaw():
    payload = _json_action_payload()
    try:
        result = push_openclaw(**payload)
        if result.get("accepted"):
            return jsonify({"ok": True, **result}), 202
        if result.get("status") == "cooldown_blocked":
            return jsonify({"ok": False, "error": f"OpenClaw 冷却中，还剩 {result.get('remaining_seconds') or 0} 秒", **result}), 429
        return jsonify({"ok": False, "error": str(result.get("error") or "OpenClaw 推送失败"), **result}), 400
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def api_admin_automation_conversion_stage_manual_send_preview(stage_key: str):
    try:
        images = _stage_send_images_from_request()
        payload = preview_stage_manual_send(
            route_key=stage_key,
            content=str(request.form.get("content") or request.values.get("content") or "").strip(),
            image_media_ids=list((request.form.getlist("image_media_ids") or request.values.getlist("image_media_ids") or [])),
            images=images,
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify(payload)


def api_admin_automation_conversion_stage_manual_send(stage_key: str):
    payload = request.get_json(silent=True) if request.is_json else {}
    try:
        result = send_stage_manual_message(
            route_key=stage_key,
            content=str((payload or {}).get("content") or request.values.get("content") or "").strip(),
            image_media_ids=list((payload or {}).get("image_media_ids") or []),
            images=list((payload or {}).get("images") or []),
            attachments=list((payload or {}).get("attachments") or []),
            operator_id=_operator_from_request(),
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify(result)


def api_admin_automation_conversion_focus_send_batch_create(stage_key: str):
    try:
        result = create_focus_send_batch(
            route_key=stage_key,
            operator_id=_operator_from_request(),
            operator_type="user",
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify(result), 201
