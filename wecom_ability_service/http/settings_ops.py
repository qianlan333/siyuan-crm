from __future__ import annotations

from flask import jsonify, request

from ..domains.admin_config import list_settings_snapshot_compat, update_settings_compat


def _operator_from_request() -> str:
    return (
        str(request.headers.get("X-Admin-Operator") or "").strip()
        or str((request.get_json(silent=True) or {}).get("operator") or "").strip()
        or "api_settings"
    )


def _request_confirmed() -> bool:
    return str((request.get_json(silent=True) or {}).get("confirm") or "").strip().lower() in {"1", "true", "yes", "on"}


def get_settings():
    return jsonify({"ok": True, "settings": list_settings_snapshot_compat()})


def update_settings():
    payload = request.get_json(silent=True) or {}
    settings = payload.get("settings") or {}
    if not isinstance(settings, dict):
        return jsonify({"ok": False, "error": "settings must be an object"}), 400
    if not _request_confirmed():
        return jsonify({"ok": False, "error": "confirm is required before saving app settings"}), 400
    try:
        snapshot = update_settings_compat(settings, operator=_operator_from_request())
        return jsonify({"ok": True, "settings": snapshot})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def register_routes(bp):
    bp.route('/api/settings', methods=['GET'])(get_settings)
    bp.route('/api/settings', methods=['PUT'])(update_settings)
