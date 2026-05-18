from __future__ import annotations

from flask import jsonify, redirect, request, url_for

from ..application.automation_engine.commands import (
    RecomputeSignupConversionCustomersCommand,
    SaveSignupConversionConfigCommand,
)
from ..application.automation_engine.dto import (
    SignupConversionConfigCommandDTO,
    SignupConversionConfigQueryDTO,
    SignupConversionPreviewQueryDTO,
    SignupConversionRecomputeCommandDTO,
)
from ..application.automation_engine.queries import (
    GetSignupConversionConfigQuery,
    ListAutomationConversionDispatchHistoryQuery,
    PreviewSignupConversionCustomerQuery,
)
from .admin_config import _query_int, _query_text


def admin_marketing_automation_ui():
    target = url_for("api.admin_automation_conversion")
    query_string = request.query_string.decode("utf-8").strip()
    if query_string:
        target = f"{target}?{query_string}"
    return redirect(target, code=302)


def api_admin_marketing_automation_config():
    try:
        return jsonify(
            {
                "ok": True,
                "config": GetSignupConversionConfigQuery()(SignupConversionConfigQueryDTO()),
            }
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def api_admin_marketing_automation_save_config():
    payload = request.get_json(silent=True) or {}
    try:
        saved = SaveSignupConversionConfigCommand()(
            SignupConversionConfigCommandDTO(payload=dict(payload or {}))
        )
        return jsonify({"ok": True, "config": saved})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def api_admin_marketing_automation_preview():
    payload = request.get_json(silent=True) or {}
    try:
        preview = PreviewSignupConversionCustomerQuery()(
            SignupConversionPreviewQueryDTO(
                external_userid=str(payload.get("external_userid", "") or ""),
                person_id=payload.get("person_id"),
            )
        )
        return jsonify({"ok": True, "preview": preview})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404


def api_admin_marketing_automation_recompute():
    payload = request.get_json(silent=True) or {}
    try:
        result = RecomputeSignupConversionCustomersCommand()(
            SignupConversionRecomputeCommandDTO(
                external_userid=str(payload.get("external_userid", "") or ""),
                person_id=payload.get("person_id"),
                external_userids=payload.get("external_userids") or [],
                person_ids=payload.get("person_ids") or [],
            )
        )
        return jsonify({"ok": True, "recompute": result})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404


def api_admin_marketing_automation_dispatch_history():
    return jsonify(
        {
            "ok": True,
            "dispatch_history": ListAutomationConversionDispatchHistoryQuery()(
                status=_query_text("status"),
                limit=_query_int("limit", default=50, minimum=1, maximum=200),
            ),
        }
    )


def api_admin_config_signup_conversion():
    return api_admin_marketing_automation_config()


def api_admin_config_save_signup_conversion():
    return api_admin_marketing_automation_save_config()


def register_routes(bp):
    bp.route("/admin/marketing-automation/ui", methods=["GET"])(admin_marketing_automation_ui)
    bp.route("/api/admin/marketing-automation/config", methods=["GET"])(api_admin_marketing_automation_config)
    bp.route("/api/admin/marketing-automation/config", methods=["PUT"])(api_admin_marketing_automation_save_config)
    bp.route("/api/admin/marketing-automation/config/preview", methods=["POST"])(api_admin_marketing_automation_preview)
    bp.route("/api/admin/marketing-automation/dispatch-history", methods=["GET"])(api_admin_marketing_automation_dispatch_history)
    bp.route("/api/admin/marketing-automation/recompute", methods=["POST"])(api_admin_marketing_automation_recompute)
    bp.route("/api/admin/config/marketing-automation/signup-conversion", methods=["GET"])(api_admin_config_signup_conversion)
    bp.route("/api/admin/config/marketing-automation/signup-conversion", methods=["PUT"])(api_admin_config_save_signup_conversion)
