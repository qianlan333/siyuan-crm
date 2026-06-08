from __future__ import annotations

import base64
from datetime import datetime, timezone
from html import escape
import json
import logging
from typing import Any
from urllib.parse import urlencode

from flask import current_app, jsonify, render_template, request, session, url_for
from itsdangerous import BadSignature, URLSafeSerializer

from ..infra.wechat_oauth import fetch_wechat_userinfo

QUESTIONNAIRE_IDENTITY_HINT_FIELDS = (
    "respondent_key",
    "openid",
    "unionid",
    "external_userid",
)
QUESTIONNAIRE_SOURCE_PARAM_FIELDS = (
    "source_channel",
    "campaign_id",
    "staff_id",
)
QUESTIONNAIRE_SIGNED_CONTEXT_FIELDS = (
    "sidebar_context_token",
    "sidebar_context",
)
QUESTIONNAIRE_META_FIELDS = QUESTIONNAIRE_IDENTITY_HINT_FIELDS + QUESTIONNAIRE_SOURCE_PARAM_FIELDS + QUESTIONNAIRE_SIGNED_CONTEXT_FIELDS
QUESTIONNAIRE_SIDEBAR_CONTEXT_SESSION_KEY = "questionnaire_sidebar_context"
QUESTIONNAIRE_SIDEBAR_CONTEXT_SALT = "aicrm-sidebar-questionnaire-context-v1"


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


def _sidebar_context_secret() -> str:
    return str(current_app.config.get("SECRET_KEY", "") or "").strip() or "dev-secret-key-change-me"


def _sidebar_context_serializer() -> URLSafeSerializer:
    return URLSafeSerializer(_sidebar_context_secret(), salt=QUESTIONNAIRE_SIDEBAR_CONTEXT_SALT)


def build_sidebar_questionnaire_context_token(
    *,
    external_userid: str,
    owner_userid: str = "",
    follow_user_userid: str = "",
    bind_by_userid: str = "",
    max_age_seconds: int = 86400,
) -> str:
    now = int(datetime.now(timezone.utc).timestamp())
    ttl = max(60, min(int(max_age_seconds or 86400), 7 * 86400))
    payload = {
        "external_userid": str(external_userid or "").strip(),
        "owner_userid": str(owner_userid or "").strip(),
        "follow_user_userid": str(follow_user_userid or owner_userid or "").strip(),
        "bind_by_userid": str(bind_by_userid or owner_userid or follow_user_userid or "").strip(),
        "source": "sidebar_questionnaire_link",
        "issued_at": now,
        "expires_at": now + ttl,
    }
    if not payload["external_userid"]:
        raise ValueError("external_userid is required")
    return _sidebar_context_serializer().dumps(payload)


def _normalize_sidebar_context(payload: dict[str, Any] | None) -> dict[str, str]:
    source = dict(payload or {}) if isinstance(payload, dict) else {}
    now = int(datetime.now(timezone.utc).timestamp())
    expires_at = int(source.get("expires_at") or 0)
    external_userid = str(source.get("external_userid") or "").strip()
    if not external_userid:
        return {}
    if expires_at and expires_at < now:
        return {}
    return {
        "external_userid": external_userid,
        "owner_userid": str(source.get("owner_userid") or source.get("follow_user_userid") or "").strip(),
        "follow_user_userid": str(source.get("follow_user_userid") or source.get("owner_userid") or "").strip(),
        "bind_by_userid": str(source.get("bind_by_userid") or source.get("owner_userid") or source.get("follow_user_userid") or "").strip(),
        "source": "sidebar_questionnaire_link",
        "issued_at": str(source.get("issued_at") or ""),
        "expires_at": str(source.get("expires_at") or ""),
    }


def load_sidebar_questionnaire_context_token(token: str) -> dict[str, str]:
    normalized_token = str(token or "").strip()
    if not normalized_token:
        return {}
    try:
        payload = _sidebar_context_serializer().loads(normalized_token)
    except (BadSignature, ValueError, TypeError):
        return {}
    return _normalize_sidebar_context(payload)


def _request_sidebar_context_token(payload: dict[str, Any] | None = None) -> str:
    for key in QUESTIONNAIRE_SIGNED_CONTEXT_FIELDS:
        value = str((payload or {}).get(key) or "").strip() if isinstance(payload, dict) else ""
        if value:
            return value
    for key in QUESTIONNAIRE_SIGNED_CONTEXT_FIELDS:
        value = str(request.values.get(key) or "").strip()
        if value:
            return value
    return ""


def capture_sidebar_questionnaire_context(payload: dict[str, Any] | None = None) -> dict[str, str]:
    token = _request_sidebar_context_token(payload)
    context = load_sidebar_questionnaire_context_token(token)
    if context:
        session[QUESTIONNAIRE_SIDEBAR_CONTEXT_SESSION_KEY] = context
        return context
    session_context = session.get(QUESTIONNAIRE_SIDEBAR_CONTEXT_SESSION_KEY) or {}
    return _normalize_sidebar_context(session_context if isinstance(session_context, dict) else {})


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
    for key in QUESTIONNAIRE_SOURCE_PARAM_FIELDS:
        value = request.args.get(key, "").strip()
        if value:
            payload[key] = value
    return payload


def _questionnaire_request_hints() -> dict[str, str]:
    payload: dict[str, str] = {}
    for key in QUESTIONNAIRE_META_FIELDS:
        value = str(request.values.get(key) or "").strip()
        if value:
            payload[key] = value
    return payload


def _questionnaire_request_meta() -> dict[str, str]:
    return {
        "ip": (request.headers.get("X-Forwarded-For", "").split(",")[0] or request.remote_addr or "").strip(),
        "user_agent": request.headers.get("User-Agent", ""),
    }


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
        identity = {}
    sidebar_context = session.get(QUESTIONNAIRE_SIDEBAR_CONTEXT_SESSION_KEY) or {}
    if not isinstance(sidebar_context, dict):
        sidebar_context = {}
    return {
        "openid": str(identity.get("openid") or "").strip(),
        "unionid": str(identity.get("unionid") or "").strip(),
        "external_userid": str(identity.get("external_userid") or sidebar_context.get("external_userid") or "").strip(),
        "respondent_key": str(identity.get("respondent_key") or sidebar_context.get("external_userid") or "").strip(),
    }


def _questionnaire_request_identity_hints() -> dict[str, str]:
    return {
        key: request.args.get(key, "").strip()
        for key in QUESTIONNAIRE_IDENTITY_HINT_FIELDS
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


def _oauth_browser_error_page(
    *,
    title: str,
    message: str,
    return_url: str = "/",
    button_label: str = "返回",
    status_code: int = 400,
):
    safe_return_url = escape(str(return_url or "/"), quote=True)
    safe_title = escape(str(title or "授权未完成"))
    safe_message = escape(str(message or "授权未完成，请重新进入页面。"))
    safe_button_label = escape(str(button_label or "返回"))
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_title}</title>
  <style>
    body {{ margin: 0; min-height: 100vh; display: grid; place-items: center; padding: 24px; background: #f6f7fb; color: #1f2937; font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Segoe UI", sans-serif; }}
    main {{ width: min(100%, 420px); padding: 28px 22px; border: 1px solid #e5e7eb; border-radius: 18px; background: #fff; text-align: center; box-shadow: 0 2px 8px rgba(15, 23, 42, 0.08); }}
    h1 {{ margin: 0 0 12px; font-size: 22px; line-height: 1.35; }}
    p {{ margin: 0; color: #6b7280; font-size: 15px; line-height: 1.7; }}
    a {{ display: inline-flex; align-items: center; justify-content: center; margin-top: 22px; min-height: 44px; padding: 0 20px; border-radius: 999px; background: #2563eb; color: #fff; font-weight: 700; text-decoration: none; }}
  </style>
</head>
<body>
  <main>
    <h1>{safe_title}</h1>
    <p>{safe_message}</p>
    <a href="{safe_return_url}">{safe_button_label}</a>
  </main>
</body>
</html>"""
    return html, status_code, {"Content-Type": "text/html; charset=utf-8"}


def _questionnaire_oauth_start_url(slug: str, source_params: dict[str, Any] | None = None) -> str:
    oauth_query = {"slug": str(slug or "").strip(), **dict(source_params or {})}
    return f"{url_for('api.h5_wechat_oauth_start')}?{urlencode(oauth_query)}"


def _wechat_oauth_authorize_url(*, app_id: str, redirect_uri: str, scope: str, state: str) -> str:
    query = urlencode(
        {
            "appid": str(app_id or "").strip(),
            "redirect_uri": str(redirect_uri or "").strip(),
            "response_type": "code",
            "scope": str(scope or "").strip() or "snsapi_base",
            "state": str(state or "").strip(),
        }
    )
    return f"https://open.weixin.qq.com/connect/oauth2/authorize?{query}#wechat_redirect"


def _normalize_prefill_fields(questionnaire: dict[str, Any], payload: dict[str, Any] | None = None) -> dict[str, Any]:
    answers = payload.get("answers") if isinstance(payload, dict) else None
    if not isinstance(answers, dict):
        return {}

    prefill_fields: dict[str, Any] = {}
    for question in questionnaire.get("questions") or []:
        field_name = f"q_{question.get('id')}"
        answer = answers.get(str(question.get("id")))
        if answer in (None, "", []):
            continue
        if question.get("type") == "multi_choice":
            if isinstance(answer, list):
                prefill_fields[field_name] = [str(item).strip() for item in answer if str(item).strip()]
            else:
                normalized = str(answer).strip()
                if normalized:
                    prefill_fields[field_name] = [normalized]
            continue
        if isinstance(answer, list):
            answer = answer[0] if answer else ""
        normalized = str(answer).strip()
        if normalized:
            prefill_fields[field_name] = normalized
    return prefill_fields


def _build_questionnaire_page_state(
    questionnaire: dict[str, Any],
    *,
    page_mode: str,
    env_notice: str,
    oauth_start_url: str,
    is_wechat_browser: bool,
    is_authorized: bool,
    form_error: str = "",
    prefill_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    slug = str(questionnaire.get("slug") or "").strip()
    return {
        "slug": slug,
        "mode": page_mode,
        "api_url": f"/api/h5/questionnaires/{slug}",
        "submit_url": f"/api/h5/questionnaires/{slug}/submit",
        "diagnostics_url": f"/api/h5/questionnaires/{slug}/client-diagnostics",
        "submitted_url": _questionnaire_submitted_path(slug),
        "title": questionnaire.get("title", ""),
        "description": questionnaire.get("description", ""),
        "answer_display_mode": questionnaire.get("answer_display_mode") or "all_in_one",
        "env_notice": env_notice,
        "oauth_start_url": oauth_start_url if _wechat_oauth_is_configured() else "",
        "is_wechat_browser": is_wechat_browser,
        "is_authorized": is_authorized,
        "initial_questionnaire": questionnaire if page_mode == "questionnaire" else None,
        "request_hints": _questionnaire_request_hints(),
        "prefill_fields": _normalize_prefill_fields(questionnaire, prefill_payload),
        "form_error": form_error,
    }


def _parse_questionnaire_form_payload(questionnaire: dict[str, Any]) -> dict[str, Any]:
    payload = _questionnaire_request_hints()
    answers: dict[str, Any] = {}

    for question in questionnaire.get("questions") or []:
        question_id = str(question.get("id") or "").strip()
        if not question_id:
            continue
        field_name = f"q_{question_id}"
        question_type = str(question.get("type") or "").strip()
        if question_type == "single_choice":
            raw_value = str(request.form.get(field_name) or "").strip()
            if raw_value:
                try:
                    answers[question_id] = int(raw_value)
                except ValueError:
                    answers[question_id] = raw_value
            continue
        if question_type == "multi_choice":
            raw_values = [str(item).strip() for item in request.form.getlist(field_name)]
            normalized_values = [item for item in raw_values if item]
            if normalized_values:
                parsed_values: list[Any] = []
                for item in normalized_values:
                    try:
                        parsed_values.append(int(item))
                    except ValueError:
                        parsed_values.append(item)
                answers[question_id] = parsed_values
            continue
        raw_value = str(request.form.get(field_name) or "").strip()
        if raw_value:
            answers[question_id] = raw_value

    payload["answers"] = answers
    return payload


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
