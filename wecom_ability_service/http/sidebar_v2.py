from __future__ import annotations

from flask import Response, jsonify, redirect, request

from ..domains import sidebar_v2


def _json_error(message: str, status: int = 400):
    return jsonify({"ok": False, "error": message}), status


def sidebar_v2_workbench():
    try:
        return jsonify(
            sidebar_v2.get_sidebar_workbench(
                external_userid=request.args.get("external_userid", ""),
                owner_userid=request.args.get("owner_userid", ""),
            )
        )
    except ValueError as exc:
        return _json_error(str(exc))


def sidebar_v2_update_profile():
    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(
            sidebar_v2.update_profile(
                external_userid=str(payload.get("external_userid") or ""),
                source=str(payload.get("source") or ""),
                industry=str(payload.get("industry") or ""),
                industry_description=str(payload.get("industry_description") or ""),
                needs_blockers_followup=str(payload.get("needs_blockers_followup") or ""),
                updated_by=str(payload.get("updated_by") or payload.get("operator") or ""),
            )
        )
    except ValueError as exc:
        return _json_error(str(exc))


def sidebar_v2_questionnaires():
    try:
        return jsonify(sidebar_v2.get_questionnaires(external_userid=request.args.get("external_userid", "")))
    except ValueError as exc:
        return _json_error(str(exc))


def sidebar_v2_materials():
    try:
        return jsonify(
            sidebar_v2.list_materials(
                material_type=request.args.get("type", ""),
                limit=request.args.get("limit") or 50,
            )
        )
    except ValueError as exc:
        return _json_error(str(exc))


def sidebar_v2_image_thumbnail(image_id: int):
    try:
        payload = sidebar_v2.get_image_thumbnail(image_id)
    except LookupError as exc:
        return _json_error(str(exc), 404)
    except ValueError as exc:
        return _json_error(str(exc))
    redirect_url = str(payload.get("redirect_url") or "").strip()
    if redirect_url:
        return redirect(redirect_url, code=302)
    response = Response(payload.get("body") or b"", mimetype=str(payload.get("mime_type") or "image/png"))
    response.headers["Cache-Control"] = "private, max-age=86400"
    return response


def sidebar_v2_send_material():
    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(
            sidebar_v2.send_material(
                external_userid=str(payload.get("external_userid") or ""),
                owner_userid=str(payload.get("owner_userid") or ""),
                material_type=str(payload.get("type") or ""),
                material_id=payload.get("material_id"),
                operator=str(payload.get("operator") or ""),
                delivery_mode=str(payload.get("delivery_mode") or ""),
            )
        )
    except ValueError as exc:
        return _json_error(str(exc))


def sidebar_v2_other_staff_messages():
    try:
        return jsonify(
            sidebar_v2.get_other_staff_messages(
                external_userid=request.args.get("external_userid", ""),
                current_userid=request.args.get("current_userid", "") or request.args.get("owner_userid", ""),
                limit=request.args.get("limit") or 20,
            )
        )
    except ValueError as exc:
        return _json_error(str(exc))


def sidebar_v2_products():
    try:
        return jsonify(sidebar_v2.get_products(external_userid=request.args.get("external_userid", "")))
    except ValueError as exc:
        return _json_error(str(exc))


def sidebar_v2_orders():
    try:
        return jsonify(sidebar_v2.get_orders(external_userid=request.args.get("external_userid", "")))
    except ValueError as exc:
        return _json_error(str(exc))


def register_routes(bp):
    bp.route("/api/sidebar/v2/workbench", methods=["GET"])(sidebar_v2_workbench)
    bp.route("/api/sidebar/v2/profile", methods=["PUT"])(sidebar_v2_update_profile)
    bp.route("/api/sidebar/v2/questionnaires", methods=["GET"])(sidebar_v2_questionnaires)
    bp.route("/api/sidebar/v2/materials", methods=["GET"])(sidebar_v2_materials)
    bp.route("/api/sidebar/v2/materials/image/<int:image_id>/thumbnail", methods=["GET"])(sidebar_v2_image_thumbnail)
    bp.route("/api/sidebar/v2/materials/send", methods=["POST"])(sidebar_v2_send_material)
    bp.route("/api/sidebar/v2/other-staff-messages", methods=["GET"])(sidebar_v2_other_staff_messages)
    bp.route("/api/sidebar/v2/products", methods=["GET"])(sidebar_v2_products)
    bp.route("/api/sidebar/v2/orders", methods=["GET"])(sidebar_v2_orders)
