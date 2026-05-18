from __future__ import annotations

from flask import jsonify, request

from .sidebar_marketing_support import (
    mark_enrolled,
    marketing_status_payload,
    preview_signup_conversion_customer,
    set_manual_followup_segment,
    sidebar_marketing_target_exists,
    unmark_enrolled,
)


def sidebar_marketing_status():
    external_userid = request.args.get("external_userid", "").strip()
    if not external_userid:
        return jsonify({"ok": False, "error": "external_userid is required"}), 400
    if not sidebar_marketing_target_exists(external_userid):
        return jsonify({"ok": False, "error": "customer not found"}), 404
    try:
        preview = preview_signup_conversion_customer(external_userid=external_userid)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except LookupError:
        return jsonify({"ok": False, "error": "customer not found"}), 404
    return jsonify({"ok": True, "marketing_status": marketing_status_payload(preview)})


def sidebar_marketing_status_mark_enrolled():
    payload = request.get_json(silent=True) or {}
    external_userid = str(payload.get("external_userid") or "").strip()
    if not external_userid:
        return jsonify({"ok": False, "error": "external_userid is required"}), 400
    if not sidebar_marketing_target_exists(external_userid):
        return jsonify({"ok": False, "error": "customer not found"}), 404
    try:
        conversion = mark_enrolled(
            external_userid=external_userid,
            owner_userid=str(payload.get("owner_userid") or "").strip(),
            operator=str(payload.get("operator") or "").strip(),
            source="sidebar_manual",
            signup_status=str(payload.get("signup_status") or "").strip() or "signed_999",
        )
        preview = preview_signup_conversion_customer(external_userid=external_userid)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except LookupError:
        return jsonify({"ok": False, "error": "customer not found"}), 404
    return jsonify({"ok": True, "marketing_status": marketing_status_payload(preview), "conversion": conversion})


def sidebar_marketing_status_unmark_enrolled():
    payload = request.get_json(silent=True) or {}
    external_userid = str(payload.get("external_userid") or "").strip()
    if not external_userid:
        return jsonify({"ok": False, "error": "external_userid is required"}), 400
    if not sidebar_marketing_target_exists(external_userid):
        return jsonify({"ok": False, "error": "customer not found"}), 404
    try:
        conversion = unmark_enrolled(
            external_userid=external_userid,
            owner_userid=str(payload.get("owner_userid") or "").strip(),
            operator=str(payload.get("operator") or "").strip(),
            source="sidebar_manual",
            restore_signup_status=str(payload.get("restore_signup_status") or "").strip(),
        )
        preview = preview_signup_conversion_customer(external_userid=external_userid)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except LookupError:
        return jsonify({"ok": False, "error": "customer not found"}), 404
    return jsonify({"ok": True, "marketing_status": marketing_status_payload(preview), "conversion": conversion})


def sidebar_marketing_status_set_followup_segment():
    payload = request.get_json(silent=True) or {}
    external_userid = str(payload.get("external_userid") or "").strip()
    if not external_userid:
        return jsonify({"ok": False, "error": "external_userid is required"}), 400
    if not sidebar_marketing_target_exists(external_userid):
        return jsonify({"ok": False, "error": "customer not found"}), 404
    try:
        override = set_manual_followup_segment(
            external_userid=external_userid,
            followup_segment=str(payload.get("followup_segment") or "").strip(),
            owner_userid=str(payload.get("owner_userid") or "").strip(),
            operator=str(payload.get("operator") or "").strip(),
            source="sidebar_manual",
        )
        preview = preview_signup_conversion_customer(external_userid=external_userid)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except LookupError:
        return jsonify({"ok": False, "error": "customer not found"}), 404
    return jsonify({"ok": True, "marketing_status": marketing_status_payload(preview), "override": override})


def register_routes(bp):
    bp.route('/api/sidebar/marketing-status', methods=['GET'])(sidebar_marketing_status)
    bp.route('/api/sidebar/marketing-status/set-followup-segment', methods=['POST'])(sidebar_marketing_status_set_followup_segment)
    bp.route('/api/sidebar/marketing-status/mark-enrolled', methods=['POST'])(sidebar_marketing_status_mark_enrolled)
    bp.route('/api/sidebar/marketing-status/unmark-enrolled', methods=['POST'])(sidebar_marketing_status_unmark_enrolled)
