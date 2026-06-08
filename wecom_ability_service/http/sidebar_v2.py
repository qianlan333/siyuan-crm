from __future__ import annotations

from flask import Response, jsonify, request

from aicrm_next.customer_read_model.sidebar_v2 import (
    SidebarCommerceReadModel,
    SidebarMaterialReadModel,
    SidebarOtherStaffMessagesReadModel,
    SidebarQuestionnaireReadModel,
    SidebarWorkbenchReadModel,
)
from aicrm_next.shared.errors import NotFoundError

from ..domains import sidebar_v2 as sidebar_v2_writes


def _json_error(message: str, status: int = 400):
    return jsonify({"ok": False, "error": message}), status


def _sidebar_error(message: str, status: int, *, source_status: str, read_model_status: str):
    return (
        jsonify(
            {
                "ok": False,
                "error": message,
                "source_status": source_status,
                "read_model_status": read_model_status,
                "route_owner": "ai_crm_next",
                "fallback_used": False,
                "degraded": status >= 500,
            }
        ),
        status,
    )


def _sidebar_input_error(message: str):
    return _sidebar_error(message, 400, source_status="input_error", read_model_status="input_error")


def _sidebar_lookup_error(message: str):
    return _sidebar_error(message, 404, source_status="not_found", read_model_status="not_found")


def _sidebar_read_unavailable(exc: Exception):
    return _sidebar_error(
        str(exc).strip() or exc.__class__.__name__,
        503,
        source_status="production_unavailable",
        read_model_status="unavailable",
    )


def _get_limit(default: int, *, maximum: int) -> int:
    try:
        limit = int(request.args.get("limit") or default)
    except (TypeError, ValueError):
        limit = default
    return max(1, min(limit, maximum))


def sidebar_v2_workbench():
    external_userid = str(request.args.get("external_userid") or "").strip()
    if not external_userid:
        return _sidebar_input_error("external_userid is required")
    try:
        payload = SidebarWorkbenchReadModel()(
            external_userid=external_userid,
            owner_userid=str(request.args.get("owner_userid") or "").strip(),
        )
    except NotFoundError as exc:
        return _sidebar_lookup_error(str(exc) or "customer not found")
    except ValueError as exc:
        return _sidebar_input_error(str(exc))
    except Exception as exc:
        return _sidebar_read_unavailable(exc)
    return jsonify({"ok": True, **payload, "route_owner": "ai_crm_next"})


def sidebar_v2_update_profile():
    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(
            sidebar_v2_writes.update_profile(
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
    external_userid = str(request.args.get("external_userid") or "").strip()
    if not external_userid:
        return _sidebar_input_error("external_userid is required")
    try:
        payload = SidebarQuestionnaireReadModel()(external_userid=external_userid)
    except NotFoundError as exc:
        return _sidebar_lookup_error(str(exc) or "customer not found")
    except ValueError as exc:
        return _sidebar_input_error(str(exc))
    except Exception as exc:
        return _sidebar_read_unavailable(exc)
    return jsonify({"ok": True, **payload, "route_owner": "ai_crm_next"})


def sidebar_v2_materials():
    try:
        payload = SidebarMaterialReadModel()(
            material_type=str(request.args.get("type") or "").strip(),
            limit=_get_limit(50, maximum=200),
        )
    except ValueError as exc:
        return _sidebar_input_error(str(exc))
    except Exception as exc:
        return _sidebar_read_unavailable(exc)
    return jsonify({"ok": True, **payload, "route_owner": "ai_crm_next"})


def sidebar_v2_image_thumbnail(image_id: int):
    try:
        payload = SidebarMaterialReadModel().thumbnail(image_id)
    except LookupError as exc:
        return _sidebar_lookup_error(str(exc) or "image not found")
    except ValueError as exc:
        return _sidebar_input_error(str(exc))
    except Exception as exc:
        return _sidebar_read_unavailable(exc)
    response = Response(payload.get("body") or b"", mimetype=str(payload.get("mime_type") or "image/png"))
    response.headers["Cache-Control"] = "private, max-age=86400"
    return response


def sidebar_v2_send_material():
    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(
            sidebar_v2_writes.send_material(
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
    external_userid = str(request.args.get("external_userid") or "").strip()
    if not external_userid:
        return _sidebar_input_error("external_userid is required")
    try:
        payload = SidebarOtherStaffMessagesReadModel()(
            external_userid=external_userid,
            current_userid=str(request.args.get("current_userid") or request.args.get("owner_userid") or "").strip(),
            limit=_get_limit(20, maximum=100),
        )
    except ValueError as exc:
        return _sidebar_input_error(str(exc))
    except Exception as exc:
        return _sidebar_read_unavailable(exc)
    return jsonify({"ok": True, **payload, "route_owner": "ai_crm_next"})


def sidebar_v2_products():
    external_userid = str(request.args.get("external_userid") or "").strip()
    if not external_userid:
        return _sidebar_input_error("external_userid is required")
    try:
        payload = SidebarCommerceReadModel().products(
            external_userid=external_userid,
            owner_userid=str(request.args.get("owner_userid") or "").strip(),
            bind_by_userid=str(request.args.get("bind_by_userid") or "").strip(),
        )
    except ValueError as exc:
        return _sidebar_input_error(str(exc))
    except Exception as exc:
        return _sidebar_read_unavailable(exc)
    return jsonify({"ok": True, **payload, "route_owner": "ai_crm_next"})


def sidebar_v2_orders():
    external_userid = str(request.args.get("external_userid") or "").strip()
    if not external_userid:
        return _sidebar_input_error("external_userid is required")
    try:
        payload = SidebarCommerceReadModel().orders(
            external_userid=external_userid,
            owner_userid=str(request.args.get("owner_userid") or "").strip(),
        )
    except NotFoundError as exc:
        return _sidebar_lookup_error(str(exc) or "customer not found")
    except ValueError as exc:
        return _sidebar_input_error(str(exc))
    except Exception as exc:
        return _sidebar_read_unavailable(exc)
    return jsonify({"ok": True, **payload, "route_owner": "ai_crm_next"})


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
