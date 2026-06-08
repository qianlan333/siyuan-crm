from __future__ import annotations

from typing import Any

from flask import abort, jsonify, redirect, render_template, request

from ..application.questionnaire.commands import SubmitQuestionnaireCommand
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
from ..application.questionnaire import QuestionnaireAlreadySubmittedError
from .questionnaire_support import (
    _build_questionnaire_page_state,
    capture_sidebar_questionnaire_context,
    _is_wechat_browser,
    _parse_questionnaire_form_payload,
    _questionnaire_oauth_start_url,
    _questionnaire_request_identity_hints,
    _questionnaire_request_meta,
    _questionnaire_session_identity,
    _questionnaire_source_params,
    _questionnaire_submitted_path,
    _require_wechat_browser_api,
    _require_wechat_browser_page,
    _wechat_oauth_is_configured,
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
    capture_sidebar_questionnaire_context()
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
    capture_sidebar_questionnaire_context()
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
    sidebar_context = capture_sidebar_questionnaire_context(payload)
    if sidebar_context:
        request_meta["signed_sidebar_context"] = sidebar_context
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


def register_routes(bp):
    bp.route('/api/h5/questionnaires/<slug>/submit', methods=['POST'])(public_submit_questionnaire)
