from __future__ import annotations

import json

from flask import abort, current_app, jsonify, request, session

from .public_questionnaires import _load_public_questionnaire, _resolve_public_questionnaire_identity
from .questionnaire_support import (
    _mask_identity_value,
    _questionnaire_logger,
    _questionnaire_session_identity,
)


def public_questionnaire_client_diagnostics(slug: str):
    questionnaire = _load_public_questionnaire(slug)
    if not questionnaire:
        return jsonify({"ok": False, "error": "questionnaire not found"}), 404

    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        payload = {}
    identity = _resolve_public_questionnaire_identity(session_identity=_questionnaire_session_identity())
    stage = str(payload.get("stage") or "").strip()[:64]
    message = str(payload.get("message") or "").strip()[:500]
    extra = payload.get("extra")
    extra_text = ""
    if extra not in (None, "", {}, []):
        try:
            extra_text = json.dumps(extra, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError):
            extra_text = str(extra)
        extra_text = extra_text[:1200]

    _questionnaire_logger().warning(
        "questionnaire client diagnostics slug=%s questionnaire_id=%s stage=%s message=%s "
        "respondent_key=%s openid=%s unionid=%s external_userid=%s ua=%s extra=%s",
        slug,
        int(questionnaire["id"]),
        stage or "-",
        message or "-",
        _mask_identity_value(identity.get("respondent_key", "")),
        _mask_identity_value(identity.get("openid", "")),
        _mask_identity_value(identity.get("unionid", "")),
        _mask_identity_value(identity.get("external_userid", "")),
        str(request.headers.get("User-Agent") or "").strip()[:240],
        extra_text,
    )
    return jsonify({"ok": True})


def debug_questionnaire_session():
    if not current_app.config.get("ENABLE_DEBUG_QUESTIONNAIRE_SESSION_API"):
        abort(404)
    return jsonify({"ok": True, "questionnaire_h5_identity": session.get("questionnaire_h5_identity") or {}})


def register_routes(bp):
    bp.route('/api/h5/questionnaires/<slug>/client-diagnostics', methods=['POST'])(public_questionnaire_client_diagnostics)
    bp.route('/api/debug/questionnaire/session', methods=['GET'])(debug_questionnaire_session)
