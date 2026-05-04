from __future__ import annotations

import base64
import json
import logging

from flask import current_app, jsonify, render_template, request, session, url_for

from ..infra.wechat_oauth import fetch_wechat_userinfo


def _questionnaire_public_path(slug: str) -> str:
    return f"/s/{slug}"


def _questionnaire_submitted_path(slug: str) -> str:
    return f"/s/{slug}/submitted"


def _external_base_url() -> str:
    forwarded_proto = (request.headers.get("X-Forwarded-Proto") or "").split(",")[0].strip()
    forwarded_host = (request.headers.get("X-Forwarded-Host") or "").split(",")[0].strip()
    scheme = forwarded_proto or request.scheme or "http"
    host = forwarded_host or request.host
    return f"{scheme}://{host}".rstrip("/")


def _questionnaire_public_url(slug: str) -> str:
    return f"{_external_base_url()}{_questionnaire_public_path(slug)}"


def _attach_questionnaire_links(item: dict) -> dict:
    enriched = dict(item)
    slug = enriched.get("slug", "")
    if slug:
        enriched["public_path"] = _questionnaire_public_path(slug)
        enriched["public_url"] = _questionnaire_public_url(slug)
    return enriched


def _wechat_oauth_is_configured() -> bool:
    secret_key = str(current_app.config.get("SECRET_KEY", "") or "").strip()
    return bool(
        current_app.config.get("WECHAT_MP_APP_ID")
        and current_app.config.get("WECHAT_MP_APP_SECRET")
        and secret_key
        and secret_key != "dev-secret-key-change-me"
    )


def _questionnaire_source_params() -> dict[str, str]:
    payload = {}
    for key in ["source_channel", "campaign_id", "staff_id"]:
        value = request.args.get(key, "").strip()
        if value:
            payload[key] = value
    return payload


def _mask_identity_value(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    if len(normalized) <= 6:
        return "*" * len(normalized)
    return f"{normalized[:3]}***{normalized[-2:]}"


def _questionnaire_session_identity() -> dict[str, str]:
    identity = session.get("questionnaire_h5_identity") or {}
    if not isinstance(identity, dict):
        return {}
    return {
        "openid": str(identity.get("openid") or "").strip(),
        "unionid": str(identity.get("unionid") or "").strip(),
        "respondent_key": str(identity.get("respondent_key") or "").strip(),
    }


def _questionnaire_request_identity_hints() -> dict[str, str]:
    return {
        "respondent_key": request.args.get("respondent_key", "").strip(),
        "openid": request.args.get("openid", "").strip(),
        "unionid": request.args.get("unionid", "").strip(),
        "external_userid": request.args.get("external_userid", "").strip(),
    }


def _is_wechat_browser() -> bool:
    user_agent = (request.headers.get("User-Agent") or "").lower()
    return "micromessenger" in user_agent


def _require_wechat_browser_page():
    if _is_wechat_browser():
        return None
    return render_template("open_in_wechat.html"), 200


def _require_wechat_browser_api():
    if _is_wechat_browser():
        return None
    return jsonify({"ok": False, "error": "please_open_in_wechat"}), 403


def _encode_oauth_state(payload: dict[str, str]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _decode_oauth_state(value: str) -> dict[str, str]:
    if not value:
        return {}
    padded = value + "=" * (-len(value) % 4)
    try:
        decoded = base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8")
        payload = json.loads(decoded)
    except (ValueError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {str(key): str(item) for key, item in payload.items() if item not in (None, "")}


def _wechat_oauth_callback_url() -> str:
    return _external_base_url() + url_for("api.h5_wechat_oauth_callback")


def _questionnaire_logger() -> logging.Logger:
    return logging.getLogger("questionnaire")


def _wechat_oauth_scope() -> str:
    return str(current_app.config.get("WECHAT_MP_OAUTH_SCOPE", "snsapi_base") or "snsapi_base").strip() or "snsapi_base"


def _fetch_wechat_userinfo(access_token: str, openid: str) -> dict:
    return fetch_wechat_userinfo(access_token=access_token, openid=openid)
