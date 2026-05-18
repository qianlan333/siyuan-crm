from __future__ import annotations

from flask import abort, jsonify, request

from ..domains.admin_config import (
    build_config_home_payload,
    list_admin_app_settings,
    list_mcp_tool_settings,
    save_admin_app_settings,
    save_mcp_tool_setting,
)
from .admin_config import _operator_from_request, _query_bool, _query_text, _request_confirmed


def api_admin_config_overview():
    return jsonify({"ok": True, "overview": build_config_home_payload()})


def api_admin_config_routing():
    abort(404)


def api_admin_config_save_owner_role():
    abort(404)


def api_admin_config_save_routing_rule():
    abort(404)


def api_admin_config_signup_tags():
    abort(404)


def api_admin_config_save_signup_tag():
    abort(404)


def api_admin_config_class_term_tags():
    abort(404)


def api_admin_config_save_class_term_tag():
    abort(404)


def api_admin_config_app_settings():
    return jsonify({"ok": True, "config": list_admin_app_settings(query=_query_text("q"), scope=_query_text("scope"))})


def api_admin_config_save_app_settings():
    payload = request.get_json(silent=True) or {}
    settings = payload.get("settings") or {}
    if not isinstance(settings, dict):
        return jsonify({"ok": False, "error": "settings must be an object"}), 400
    if not _request_confirmed():
        return jsonify({"ok": False, "error": "confirm is required before saving app settings"}), 400
    try:
        changed = save_admin_app_settings(settings, operator=_operator_from_request())
        return jsonify({"ok": True, "changed": changed, "config": list_admin_app_settings(query="", scope="")})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def api_admin_config_mcp_tools():
    return jsonify({"ok": True, "config": list_mcp_tool_settings(query=_query_text("q"), enabled_only=_query_bool("enabled_only"))})


def api_admin_config_save_mcp_tool():
    payload = request.get_json(silent=True) or {}
    try:
        saved = save_mcp_tool_setting(payload, operator=_operator_from_request())
        return jsonify({"ok": True, "item": saved})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def register_routes(bp):
    bp.route("/api/admin/config/overview", methods=["GET"])(api_admin_config_overview)
    bp.route("/api/admin/config/routing", methods=["GET"])(api_admin_config_routing)
    bp.route("/api/admin/config/routing/owner-role", methods=["POST"])(api_admin_config_save_owner_role)
    bp.route("/api/admin/config/routing/rule", methods=["POST"])(api_admin_config_save_routing_rule)
    bp.route("/api/admin/config/signup-tags", methods=["GET"])(api_admin_config_signup_tags)
    bp.route("/api/admin/config/signup-tags", methods=["POST"])(api_admin_config_save_signup_tag)
    bp.route("/api/admin/config/class-term-tags", methods=["GET"])(api_admin_config_class_term_tags)
    bp.route("/api/admin/config/class-term-tags", methods=["POST"])(api_admin_config_save_class_term_tag)
    bp.route("/api/admin/config/app-settings", methods=["GET"])(api_admin_config_app_settings)
    bp.route("/api/admin/config/app-settings", methods=["PUT"])(api_admin_config_save_app_settings)
    bp.route("/api/admin/config/mcp-tools", methods=["GET"])(api_admin_config_mcp_tools)
    bp.route("/api/admin/config/mcp-tools", methods=["POST"])(api_admin_config_save_mcp_tool)
