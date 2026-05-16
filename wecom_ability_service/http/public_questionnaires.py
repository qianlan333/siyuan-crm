from __future__ import annotations

import json
from typing import Any

from flask import abort, current_app, jsonify, redirect, render_template, request, session

from ..application.questionnaire.commands import (
    CompleteQuestionnaireOauthCallbackCommand,
    QuestionnaireOauthExchangePayloadError,
    SubmitQuestionnaireCommand,
)
from ..application.questionnaire.dto import (
    GetPublicQuestionnaireBySlugQueryDTO,
    GetQuestionnaireAssessmentResultByTokenQueryDTO,
    HasQuestionnaireSubmissionQueryDTO,
    SubmitQuestionnaireCommandDTO,
)
from ..application.questionnaire.queries import (
    GetPublicQuestionnaireBySlugQuery,
    GetQuestionnaireAssessmentResultByTokenQuery,
    HasQuestionnaireSubmissionQuery,
    ResolveQuestionnaireRespondentIdentityQuery,
)
from ..infra.wechat_oauth import WeChatOAuthRequestError
from ..application.questionnaire import QuestionnaireAlreadySubmittedError
from .questionnaire_support import (
    _build_questionnaire_page_state,
    _is_wechat_browser,
    _mask_identity_value,
    _parse_questionnaire_form_payload,
    _questionnaire_logger,
    _questionnaire_oauth_start_url,
    _questionnaire_public_path,
    _questionnaire_request_identity_hints,
    _questionnaire_request_meta,
    _questionnaire_session_identity,
    _questionnaire_source_params,
    _questionnaire_submitted_path,
    _require_wechat_browser_api,
    _require_wechat_browser_page,
    _wechat_oauth_callback_url,
    _wechat_oauth_authorize_url,
    _wechat_oauth_is_configured,
    _wechat_oauth_scope,
    _decode_oauth_state,
    _encode_oauth_state,
)


def _load_public_questionnaire(slug: str) -> dict[str, Any] | None:
    return GetPublicQuestionnaireBySlugQuery()(
        GetPublicQuestionnaireBySlugQueryDTO(slug=str(slug or "").strip())
    )


def _load_questionnaire_assessment_result(slug: str, result_token: str) -> dict[str, Any] | None:
    return GetQuestionnaireAssessmentResultByTokenQuery()(
        GetQuestionnaireAssessmentResultByTokenQueryDTO(
            slug=str(slug or "").strip(),
            result_token=str(result_token or "").strip(),
        )
    )


def _has_public_submission(questionnaire_id: int, identity: dict[str, Any] | None) -> bool:
    return HasQuestionnaireSubmissionQuery()(
        HasQuestionnaireSubmissionQueryDTO(
            questionnaire_id=int(questionnaire_id),
            identity=dict(identity or {}) if identity else None,
        )
    )


def _submit_public_questionnaire(
    *,
    slug: str,
    payload: dict[str, Any],
    hidden_identity: dict[str, Any] | None = None,
    source_params: dict[str, Any] | None = None,
    request_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return SubmitQuestionnaireCommand()(
        SubmitQuestionnaireCommandDTO(
            slug=str(slug or "").strip(),
            payload=dict(payload or {}),
            hidden_identity=dict(hidden_identity or {}) if hidden_identity else None,
            source_params=dict(source_params or {}) if source_params else None,
            request_meta=dict(request_meta or {}) if request_meta else None,
        )
    )


def _resolve_public_questionnaire_identity(
    *,
    session_identity: dict[str, Any] | None = None,
) -> dict[str, str]:
    return ResolveQuestionnaireRespondentIdentityQuery()(
        session_identity=dict(session_identity or {}) if session_identity else None,
        request_identity=_questionnaire_request_identity_hints(),
    )


def _complete_public_oauth_callback(*, code: str, state_payload: dict[str, str]) -> dict[str, Any]:
    return CompleteQuestionnaireOauthCallbackCommand()(
        code=code,
        state_payload=state_payload,
        app_id=current_app.config["WECHAT_MP_APP_ID"],
        app_secret=current_app.config["WECHAT_MP_APP_SECRET"],
        oauth_scope=_wechat_oauth_scope(),
    )


def _render_questionnaire_form_page(
    questionnaire: dict[str, Any],
    *,
    page_mode: str,
    env_notice: str,
    oauth_start_url: str,
    is_wechat_browser: bool,
    is_authorized: bool,
    form_error: str = "",
    prefill_payload: dict[str, Any] | None = None,
    status_code: int = 200,
):
    page_state = _build_questionnaire_page_state(
        questionnaire,
        page_mode=page_mode,
        env_notice=env_notice,
        oauth_start_url=oauth_start_url,
        is_wechat_browser=is_wechat_browser,
        is_authorized=is_authorized,
        form_error=form_error,
        prefill_payload=prefill_payload,
    )
    return render_template("questionnaire_h5_page.html", page_state=page_state), status_code


def questionnaire_h5_page(slug: str):
    questionnaire = _load_public_questionnaire(slug)
    if not questionnaire:
        abort(404)
    wechat_gate = _require_wechat_browser_page()
    source_params = _questionnaire_source_params()
    session_identity = _questionnaire_session_identity()
    request_identity = _resolve_public_questionnaire_identity(session_identity=session_identity)
    if _has_public_submission(int(questionnaire["id"]), request_identity):
        redirect_url = str(questionnaire.get("redirect_url") or "").strip()
        if redirect_url:
            return redirect(redirect_url, code=302)
        return redirect(_questionnaire_submitted_path(slug), code=302)
    if wechat_gate is not None:
        return wechat_gate
    is_wechat_browser = _is_wechat_browser()
    oauth_start_url = _questionnaire_oauth_start_url(slug, source_params)
    page_mode = "questionnaire"
    env_notice = ""
    if is_wechat_browser and not session_identity.get("openid"):
        page_mode = "auth_gate"
        if _wechat_oauth_is_configured():
            env_notice = "授权后即可填写问卷信息。"
        else:
            env_notice = "当前为微信环境，但未配置公众号 OAuth，当前页面仅供测试。"
    return render_template(
        "questionnaire_h5_page.html",
        page_state=_build_questionnaire_page_state(
            questionnaire,
            page_mode=page_mode,
            env_notice=env_notice,
            oauth_start_url=oauth_start_url,
            is_wechat_browser=is_wechat_browser,
            is_authorized=bool(session_identity.get("openid")),
        ),
    )


def questionnaire_h5_submitted(slug: str):
    questionnaire = _load_public_questionnaire(slug)
    if not questionnaire:
        abort(404)
    return render_template("questionnaire_h5_submitted.html")


def questionnaire_h5_assessment_result(slug: str, result_token: str):
    result_payload = _load_questionnaire_assessment_result(slug, result_token)
    if not result_payload:
        abort(404)
    return render_template("questionnaire_h5_result.html", result_payload=result_payload)


def public_get_questionnaire(slug: str):
    wechat_gate = _require_wechat_browser_api()
    if wechat_gate is not None:
        return wechat_gate
    questionnaire = _load_public_questionnaire(slug)
    if not questionnaire:
        return jsonify({"ok": False, "error": "questionnaire not found"}), 404
    if _has_public_submission(
        int(questionnaire["id"]),
        _resolve_public_questionnaire_identity(session_identity=_questionnaire_session_identity()),
    ):
        return jsonify(
            {
                "ok": False,
                "error": "already_submitted",
                "message": "已经提交",
                "redirect_url": str(questionnaire.get("redirect_url") or "").strip(),
            }
        ), 409
    return jsonify({"ok": True, "questionnaire": questionnaire})


def public_submit_questionnaire(slug: str):
    is_form_submit = not request.is_json
    wechat_gate = _require_wechat_browser_api()
    if wechat_gate is not None:
        return wechat_gate
    questionnaire = _load_public_questionnaire(slug)
    if not questionnaire:
        if is_form_submit:
            abort(404)
        return jsonify({"success": False, "error": "questionnaire not found"}), 404
    payload = request.get_json(silent=True) or {}
    if is_form_submit:
        payload = _parse_questionnaire_form_payload(questionnaire)
    request_meta = _questionnaire_request_meta()
    is_wechat_browser = _is_wechat_browser()
    session_identity = _questionnaire_session_identity()
    resolved_identity = _resolve_public_questionnaire_identity(session_identity=session_identity)
    source_params = _questionnaire_source_params()
    oauth_start_url = _questionnaire_oauth_start_url(slug, source_params)
    try:
        result = _submit_public_questionnaire(
            slug=slug,
            payload=payload,
            hidden_identity=resolved_identity,
            source_params=source_params,
            request_meta=request_meta,
        )
        if is_form_submit:
            target = str(result.get("redirect_url") or "").strip() or _questionnaire_submitted_path(slug)
            return redirect(target, code=302)
        return jsonify(result)
    except LookupError as exc:
        if is_form_submit:
            abort(404)
        return jsonify({"success": False, "error": str(exc)}), 404
    except QuestionnaireAlreadySubmittedError as exc:
        if is_form_submit:
            target = str(questionnaire.get("redirect_url") or "").strip() or _questionnaire_submitted_path(slug)
            return redirect(target, code=302)
        return (
            jsonify(
                {
                    "success": False,
                    "error": "already_submitted",
                    "message": str(exc) or "已经提交",
                    "redirect_url": str(questionnaire.get("redirect_url") or "").strip(),
                }
            ),
            409,
        )
    except ValueError as exc:
        if is_form_submit:
            return _render_questionnaire_form_page(
                questionnaire,
                page_mode="questionnaire",
                env_notice="",
                oauth_start_url=oauth_start_url,
                is_wechat_browser=is_wechat_browser,
                is_authorized=bool(session_identity.get("openid")),
                form_error=str(exc).strip() or "提交失败，请稍后重试",
                prefill_payload=payload,
                status_code=400,
            )
        return jsonify({"success": False, "error": str(exc)}), 400


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


def h5_wechat_oauth_start():
    if not _wechat_oauth_is_configured():
        return jsonify({"ok": False, "error": "wechat_oauth_not_configured"}), 501
    slug = request.args.get("slug", "").strip()
    if not slug:
        return jsonify({"ok": False, "error": "slug is required"}), 400
    source_params = _questionnaire_source_params()
    state = _encode_oauth_state({"slug": slug, **source_params})
    redirect_uri = _wechat_oauth_callback_url()
    _questionnaire_logger().info(
        "oauth start slug=%s source_channel=%s campaign_id=%s staff_id=%s redirect_uri=%s",
        slug,
        source_params.get("source_channel", ""),
        source_params.get("campaign_id", ""),
        source_params.get("staff_id", ""),
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
    bp.route('/s/<slug>', methods=['GET'])(questionnaire_h5_page)
    bp.route('/s/<slug>/submitted', methods=['GET'])(questionnaire_h5_submitted)
    bp.route('/s/<slug>/result/<result_token>', methods=['GET'])(questionnaire_h5_assessment_result)
    bp.route('/api/h5/questionnaires/<slug>', methods=['GET'])(public_get_questionnaire)
    bp.route('/api/h5/questionnaires/<slug>/submit', methods=['POST'])(public_submit_questionnaire)
    bp.route('/api/h5/questionnaires/<slug>/client-diagnostics', methods=['POST'])(public_questionnaire_client_diagnostics)
    bp.route('/api/debug/questionnaire/session', methods=['GET'])(debug_questionnaire_session)
    bp.route('/api/h5/wechat/oauth/start', methods=['GET'])(h5_wechat_oauth_start)
    bp.route('/api/h5/wechat/oauth/callback', methods=['GET'])(h5_wechat_oauth_callback)
