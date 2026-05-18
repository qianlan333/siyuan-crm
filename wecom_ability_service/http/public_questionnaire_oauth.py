from __future__ import annotations

from typing import Any

from flask import current_app, jsonify, redirect, request, session

from ..application.questionnaire.commands import (
    CompleteQuestionnaireOauthCallbackCommand,
    QuestionnaireOauthExchangePayloadError,
)
from ..infra.wechat_oauth import WeChatOAuthRequestError
from .questionnaire_support import (
    _decode_oauth_state,
    _encode_oauth_state,
    _mask_identity_value,
    _questionnaire_logger,
    _questionnaire_public_path,
    _questionnaire_source_params,
    _wechat_oauth_authorize_url,
    _wechat_oauth_callback_url,
    _wechat_oauth_is_configured,
    _wechat_oauth_scope,
)


def _complete_public_oauth_callback(*, code: str, state_payload: dict[str, str]) -> dict[str, Any]:
    return CompleteQuestionnaireOauthCallbackCommand()(
        code=code,
        state_payload=state_payload,
        app_id=current_app.config["WECHAT_MP_APP_ID"],
        app_secret=current_app.config["WECHAT_MP_APP_SECRET"],
        oauth_scope=_wechat_oauth_scope(),
    )


def h5_wechat_oauth_start():
    if not _wechat_oauth_is_configured():
        return jsonify({"ok": False, "error": "wechat_oauth_not_configured"}), 501
    slug = request.args.get("slug", "").strip()
    if not slug:
        return jsonify({"ok": False, "error": "slug is required"}), 400
    state = _encode_oauth_state({"slug": slug, **_questionnaire_source_params()})
    redirect_uri = _wechat_oauth_callback_url()
    _questionnaire_logger().info(
        "oauth start slug=%s source_channel=%s campaign_id=%s staff_id=%s redirect_uri=%s",
        slug,
        request.args.get("source_channel", "").strip(),
        request.args.get("campaign_id", "").strip(),
        request.args.get("staff_id", "").strip(),
        redirect_uri,
    )
    authorize_url = _wechat_oauth_authorize_url(
        app_id=current_app.config["WECHAT_MP_APP_ID"],
        redirect_uri=redirect_uri,
        scope=_wechat_oauth_scope(),
        state=state,
    )
    return redirect(authorize_url)


def h5_wechat_oauth_callback():
    if not _wechat_oauth_is_configured():
        return jsonify({"ok": False, "error": "wechat_oauth_not_configured"}), 501
    code = request.args.get("code", "").strip()
    state_payload = _decode_oauth_state(request.args.get("state", "").strip())
    try:
        oauth_result = _complete_public_oauth_callback(code=code, state_payload=state_payload)
    except ValueError as exc:
        reason = "missing_code" if str(exc) == "code is required" else "invalid_state"
        _questionnaire_logger().warning("oauth callback failed reason=%s", reason)
        return jsonify({"ok": False, "error": str(exc)}), 400
    except WeChatOAuthRequestError as exc:
        slug = str(state_payload.get("slug") or "").strip()
        _questionnaire_logger().exception("oauth callback failed slug=%s code=%s", slug, code)
        return jsonify({"ok": False, "error": f"wechat_oauth_exchange_failed: {exc}"}), 502
    except QuestionnaireOauthExchangePayloadError as exc:
        slug = str(state_payload.get("slug") or "").strip()
        _questionnaire_logger().warning(
            "oauth callback failed slug=%s code=%s wechat_payload=%s",
            slug,
            code,
            exc.payload,
        )
        return jsonify({"ok": False, "error": "wechat_oauth_exchange_failed", "wechat_payload": exc.payload}), 502

    slug = str(oauth_result.get("slug") or "").strip()
    session["questionnaire_h5_identity"] = dict(oauth_result.get("session_identity") or {})
    session.modified = True
    _questionnaire_logger().info(
        "oauth session written slug=%s respondent_key=%s openid=%s unionid=%s",
        slug,
        _mask_identity_value(str(session["questionnaire_h5_identity"].get("respondent_key") or "")),
        _mask_identity_value(str(session["questionnaire_h5_identity"].get("openid") or "")),
        _mask_identity_value(str(session["questionnaire_h5_identity"].get("unionid") or "")),
    )
    _questionnaire_logger().info(
        "oauth callback success slug=%s openid=%s unionid=%s",
        slug,
        _mask_identity_value(str(oauth_result.get("openid") or "")),
        _mask_identity_value(str(oauth_result.get("unionid") or "")),
    )
    return redirect(str(oauth_result.get("redirect_target") or _questionnaire_public_path(slug)), code=302)


def register_routes(bp):
    bp.route('/api/h5/wechat/oauth/start', methods=['GET'])(h5_wechat_oauth_start)
    bp.route('/api/h5/wechat/oauth/callback', methods=['GET'])(h5_wechat_oauth_callback)
