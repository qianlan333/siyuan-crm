from __future__ import annotations

import csv
import json
import logging
from io import StringIO
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from aicrm_next.shared.errors import ContractError, NotFoundError
from aicrm_next.shared.runtime import production_data_ready

from .admin_write import (
    QuestionnaireAdminWriteCommand,
    QuestionnaireAdminWriteInputError,
    QuestionnaireAdminWriteNotFoundError,
    QuestionnaireAdminWriteProductionUnavailableError,
    execute_questionnaire_admin_write,
)
from .h5_write import (
    QuestionnaireH5AlreadySubmittedError,
    QuestionnaireClientDiagnosticsCommand,
    QuestionnaireH5SubmitCommand,
    QuestionnaireH5WriteInputError,
    QuestionnaireH5WriteNotFoundError,
    QuestionnaireH5WriteProductionUnavailableError,
    execute_questionnaire_client_diagnostics,
    execute_questionnaire_h5_submit,
)
from .application import (
    CompleteWechatOAuthCallbackCommand,
    GetPublicQuestionnaireQuery,
    GetPublicQuestionnaireSubmissionStatusQuery,
    GetQuestionnaireDetailQuery,
    GetQuestionnaireOAuthConfigQuery,
    GetQuestionnairePreflightQuery,
    GetQuestionnaireShareQuery,
    GetQuestionnaireResultsSummaryQuery,
    GetSubmissionResultQuery,
    LatestSubmitDebugQuery,
    ListQuestionnaireQuestionsQuery,
    ListQuestionnaireSubmissionsQuery,
    ListQuestionnairesQuery,
    StartWechatOAuthQuery,
    build_questionnaire_share_payload,
)
from .dto import OAuthCallbackRequest, OAuthStartRequest
from .oauth import COOKIE_NAME, questionnaire_oauth_state_context
from .public_access import QuestionnaireRespondentIdentityService

router = APIRouter()
logger = logging.getLogger(__name__)
_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "frontend_compat" / "templates"
templates = Jinja2Templates(directory=_TEMPLATES_DIR)

_QUESTIONNAIRE_IDENTITY_HINT_FIELDS = (
    "respondent_key",
    "openid",
    "unionid",
    "external_userid",
)
_QUESTIONNAIRE_SOURCE_PARAM_FIELDS = (
    "source_channel",
    "campaign_id",
    "staff_id",
)
_QUESTIONNAIRE_META_FIELDS = _QUESTIONNAIRE_IDENTITY_HINT_FIELDS + _QUESTIONNAIRE_SOURCE_PARAM_FIELDS
def _raise_http(exc: Exception) -> None:
    if isinstance(exc, NotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ContractError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail=str(exc)) from exc


def _read_response(payload: dict[str, Any]) -> dict[str, Any] | JSONResponse:
    if payload.get("source_status") == "production_unavailable":
        return JSONResponse(jsonable_encoder(payload), status_code=503)
    return payload


def _csv_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if value is None:
        return ""
    return value


def _csv_download_response(payload: dict[str, Any]) -> Response:
    export_payload = dict(payload.get("export_download") or {})
    fields = [str(field) for field in export_payload.get("fields") or []]
    rows = export_payload.get("rows") if isinstance(export_payload.get("rows"), list) else []
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        row_payload = row if isinstance(row, dict) else {}
        writer.writerow({field: _csv_value(row_payload.get(field)) for field in fields})
    filename = str(export_payload.get("filename") or "questionnaire-submissions.csv").replace('"', "")
    content = "\ufeff" + buffer.getvalue()
    return Response(
        content=content.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-AICRM-Route-Owner": "ai_crm_next",
            "X-AICRM-Source-Status": str(payload.get("source_status") or "next_command"),
            "X-AICRM-Fallback-Used": "false",
        },
    )


async def _execute_admin_write(
    request: Request,
    command_name: str,
    *,
    questionnaire_id: int | None = None,
    body: dict[str, Any] | None = None,
) -> Response:
    try:
        payload = body if body is not None else await _json_body(request)
        command = QuestionnaireAdminWriteCommand(
            command_name=command_name,
            questionnaire_id=questionnaire_id,
            payload={
                key: value
                for key, value in payload.items()
                if key not in {"actor_id", "actor_type", "idempotency_key", "dry_run", "trace_id", "command_id"}
            },
            command_id=str(payload.get("command_id") or uuid4().hex),
            idempotency_key=str(request.headers.get("Idempotency-Key") or payload.get("idempotency_key") or "").strip(),
            actor_id=str(payload.get("actor_id") or request.headers.get("X-AICRM-Actor-Id") or "questionnaire_admin"),
            actor_type=str(payload.get("actor_type") or request.headers.get("X-AICRM-Actor-Type") or "user"),
            dry_run=_as_bool(payload.get("dry_run")),
            source_route=request.url.path,
            trace_id=str(payload.get("trace_id") or request.headers.get("X-Request-Id") or uuid4().hex),
        )
        response = execute_questionnaire_admin_write(command)
        return JSONResponse(jsonable_encoder(response), status_code=200)
    except QuestionnaireAdminWriteInputError as exc:
        return _write_error(str(exc), status_code=400, source_status="input_error", write_model_status="input_error")
    except QuestionnaireAdminWriteNotFoundError as exc:
        return _write_error(str(exc), status_code=404, source_status="not_found", write_model_status="not_found")
    except QuestionnaireAdminWriteProductionUnavailableError as exc:
        return _write_error(
            str(exc),
            status_code=503,
            source_status="production_unavailable",
            write_model_status="unavailable",
            degraded=True,
        )


async def _json_body(request: Request) -> dict[str, Any]:
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise QuestionnaireAdminWriteInputError("json object body is required")
    return payload


async def _h5_json_body(request: Request) -> dict[str, Any]:
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise QuestionnaireH5WriteInputError("json object body is required")
    return payload


def _as_bool(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _is_redirect_response_mode(response_mode: str | None, browser_redirect: Any = None) -> bool:
    mode = str(response_mode or "").strip().lower()
    return mode == "redirect" or _as_bool(browser_redirect)


def _safe_questionnaire_return_url(value: str | None, slug: str | None) -> str:
    target = str(value or "").strip()
    if target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    slug_value = str(slug or "").strip()
    return f"/s/{slug_value}" if slug_value else "/"


def _safe_oauth_success_redirect_url(value: str | None, slug: str | None) -> str:
    target = str(value or "").strip()
    if target.startswith(("http://", "https://")):
        return target
    return _safe_questionnaire_return_url(target, slug)


def _oauth_html_error(
    *,
    title: str,
    message: str,
    return_url: str | None,
    slug: str | None = None,
    status_code: int = 400,
) -> HTMLResponse:
    from html import escape

    safe_return_url = _safe_questionnaire_return_url(return_url, slug)
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>
    body {{ margin: 0; min-height: 100vh; display: grid; place-items: center; padding: 24px; background: #f2f3f5; color: #1f2329; font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Helvetica Neue", sans-serif; }}
    main {{ width: min(100%, 420px); padding: 28px 22px; border: 1px solid #dee0e3; border-radius: 20px; background: #fff; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
    h1 {{ margin: 0 0 12px; font-size: 22px; line-height: 1.35; }}
    p {{ margin: 0; color: #646a73; font-size: 15px; line-height: 1.7; }}
    a {{ display: inline-flex; align-items: center; justify-content: center; margin-top: 22px; min-height: 44px; padding: 0 20px; border-radius: 999px; background: #3370ff; color: #fff; font-weight: 700; text-decoration: none; }}
  </style>
</head>
<body>
  <main>
    <h1>{escape(title)}</h1>
    <p>{escape(message)}</p>
    <a href="{escape(safe_return_url, quote=True)}">返回问卷</a>
  </main>
</body>
</html>"""
    return HTMLResponse(html, status_code=status_code)


def _write_error(
    message: str,
    *,
    status_code: int,
    source_status: str,
    write_model_status: str,
    degraded: bool = False,
) -> JSONResponse:
    return JSONResponse(
        {
            "ok": False,
            "error": message,
            "source_status": source_status,
            "write_model_status": write_model_status,
            "route_owner": "ai_crm_next",
            "fallback_used": False,
            "real_external_call_executed": False,
            "degraded": degraded,
        },
        status_code=status_code,
    )


def _h5_write_error(
    message: str,
    *,
    status_code: int,
    source_status: str,
    write_model_status: str,
    degraded: bool = False,
) -> JSONResponse:
    return JSONResponse(
        {
            "ok": False,
            "error": message,
            "source_status": source_status,
            "write_model_status": write_model_status,
            "route_owner": "ai_crm_next",
            "fallback_used": False,
            "real_external_call_executed": False,
            "degraded": degraded,
        },
        status_code=status_code,
    )


def _h5_identity_payload(payload: dict[str, Any]) -> dict[str, Any]:
    identity: dict[str, Any] = {}
    for key in ["respondent_identity", "identity"]:
        value = payload.get(key)
        if isinstance(value, dict):
            identity.update(value)
    for key in ["external_userid", "openid", "unionid", "mobile", "respondent_key"]:
        if payload.get(key) not in (None, ""):
            identity[key] = payload.get(key)
    return identity


def _h5_submit_identity_payload(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    identity = _questionnaire_identity_from_request(request)
    identity.update(_h5_identity_payload(payload))
    return identity


def _h5_source_payload(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    source = dict(payload.get("source") or {}) if isinstance(payload.get("source"), dict) else {}
    for key in ["source_channel", "campaign_id", "staff_id"]:
        value = request.query_params.get(key) or payload.get(key)
        if value not in (None, ""):
            source[key] = value
    source.setdefault("route", request.url.path)
    return source


async def _execute_h5_submit(request: Request, slug: str) -> Response:
    try:
        payload = await _h5_json_body(request)
        identity_result = _questionnaire_identity_result_from_request(request)
        request_identity = dict(identity_result.get("identity") or {})
        if _wechat_submit_requires_oauth(request, request_identity=request_identity, identity_result=identity_result):
            return JSONResponse(
                {
                    "ok": False,
                    "error": "oauth_required",
                    "message": "请先完成微信授权后再提交问卷",
                    "redirect_url": _questionnaire_oauth_start_url(slug, _request_values(request, _QUESTIONNAIRE_SOURCE_PARAM_FIELDS)),
                    "source_status": "oauth_required",
                    "write_model_status": "blocked",
                    "route_owner": "ai_crm_next",
                    "fallback_used": False,
                    "real_external_call_executed": False,
                    "degraded": False,
                },
                status_code=401,
            )
        submit_identity = dict(request_identity)
        submit_identity.update(_h5_identity_payload(payload))
        command = QuestionnaireH5SubmitCommand(
            questionnaire_slug=slug,
            answers=dict(payload.get("answers") or {}),
            identity=submit_identity,
            source=_h5_source_payload(payload, request),
            command_id=str(payload.get("command_id") or uuid4().hex),
            idempotency_key=str(request.headers.get("Idempotency-Key") or payload.get("idempotency_key") or "").strip(),
            actor_id=str(payload.get("actor_id") or request.headers.get("X-AICRM-Actor-Id") or "anonymous"),
            actor_type=str(payload.get("actor_type") or request.headers.get("X-AICRM-Actor-Type") or "h5_client"),
            dry_run=_as_bool(payload.get("dry_run")),
            source_route=request.url.path,
            trace_id=str(payload.get("trace_id") or request.headers.get("X-Request-Id") or uuid4().hex),
        )
        response = execute_questionnaire_h5_submit(command)
        return JSONResponse(jsonable_encoder(response), status_code=200)
    except QuestionnaireH5WriteInputError as exc:
        return _h5_write_error(str(exc), status_code=400, source_status="input_error", write_model_status="input_error")
    except QuestionnaireH5AlreadySubmittedError as exc:
        return _h5_write_error(str(exc), status_code=409, source_status="already_submitted", write_model_status="already_submitted")
    except QuestionnaireH5WriteNotFoundError as exc:
        return _h5_write_error(str(exc), status_code=404, source_status="not_found", write_model_status="not_found")
    except QuestionnaireH5WriteProductionUnavailableError as exc:
        return _h5_write_error(
            str(exc),
            status_code=503,
            source_status="production_unavailable",
            write_model_status="unavailable",
            degraded=True,
        )


async def _execute_h5_diagnostics(request: Request, slug: str) -> Response:
    try:
        payload = await _h5_json_body(request)
        diagnostics = dict(payload.get("diagnostics") or payload)
        for key in ["identity", "respondent_identity", "source", "command_id", "idempotency_key", "actor_id", "actor_type", "dry_run", "trace_id"]:
            diagnostics.pop(key, None)
        command = QuestionnaireClientDiagnosticsCommand(
            questionnaire_slug=slug,
            diagnostics=diagnostics,
            identity=_h5_identity_payload(payload),
            source=_h5_source_payload(payload, request),
            command_id=str(payload.get("command_id") or uuid4().hex),
            idempotency_key=str(request.headers.get("Idempotency-Key") or payload.get("idempotency_key") or "").strip(),
            actor_id=str(payload.get("actor_id") or request.headers.get("X-AICRM-Actor-Id") or "anonymous"),
            actor_type=str(payload.get("actor_type") or request.headers.get("X-AICRM-Actor-Type") or "h5_client"),
            dry_run=_as_bool(payload.get("dry_run")),
            source_route=request.url.path,
            trace_id=str(payload.get("trace_id") or request.headers.get("X-Request-Id") or uuid4().hex),
        )
        response = execute_questionnaire_client_diagnostics(command)
        return JSONResponse(jsonable_encoder(response), status_code=200)
    except QuestionnaireH5WriteInputError as exc:
        return _h5_write_error(str(exc), status_code=400, source_status="input_error", write_model_status="input_error")
    except QuestionnaireH5WriteProductionUnavailableError as exc:
        return _h5_write_error(
            str(exc),
            status_code=503,
            source_status="production_unavailable",
            write_model_status="unavailable",
            degraded=True,
        )


def _h5_options_response() -> JSONResponse:
    return JSONResponse(
        {
            "ok": True,
            "source_status": "next_command",
            "route_owner": "ai_crm_next",
            "fallback_used": False,
            "real_external_call_executed": False,
        }
    )


def _oauth_options_response() -> JSONResponse:
    return JSONResponse(
        {
            "ok": True,
            "source_status": "next_oauth_adapter",
            "adapter_mode": "real_blocked" if production_data_ready() else "fake",
            "route_owner": "ai_crm_next",
            "fallback_used": False,
            "real_external_call_executed": False,
        }
    )


def _questionnaire_payload_with_nested_questions(payload: dict[str, Any]) -> dict[str, Any]:
    questionnaire = payload.get("questionnaire")
    questions = payload.get("questions")
    if not isinstance(questionnaire, dict) or not isinstance(questions, list):
        return payload
    if isinstance(questionnaire.get("questions"), list):
        return payload
    return {**payload, "questionnaire": {**questionnaire, "questions": questions}}


def _public_questionnaire_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = _questionnaire_payload_with_nested_questions(payload)
    questions = normalized.get("questions")
    if not isinstance(questions, list):
        return normalized
    public_questions = [
        {key: value for key, value in question.items() if key != "sidebar_profile_field"}
        if isinstance(question, dict)
        else question
        for question in questions
    ]
    questionnaire = normalized.get("questionnaire")
    if isinstance(questionnaire, dict):
        questionnaire = {
            **questionnaire,
            "questions": [
                {key: value for key, value in question.items() if key != "sidebar_profile_field"}
                if isinstance(question, dict)
                else question
                for question in questionnaire.get("questions", [])
            ],
        }
    return {**normalized, "questionnaire": questionnaire, "questions": public_questions}


def _is_wechat_browser(request: Request) -> bool:
    return "micromessenger" in str(request.headers.get("user-agent") or "").lower()


def _is_anonymous_respondent_key(value: Any) -> bool:
    return str(value or "").strip().startswith("anon_")


def _is_authorized_identity(identity: dict[str, Any], identity_result: dict[str, Any] | None = None) -> bool:
    respondent_key = str(identity.get("respondent_key") or "").strip()
    return bool(
        identity.get("openid")
        or identity.get("unionid")
        or identity.get("external_userid")
        or (respondent_key and not _is_anonymous_respondent_key(respondent_key) and not (identity_result or {}).get("anonymous"))
    )


def _wechat_submit_requires_oauth(
    request: Request,
    *,
    request_identity: dict[str, Any],
    identity_result: dict[str, Any],
) -> bool:
    if not _is_wechat_browser(request):
        return False
    if _is_authorized_identity(request_identity, identity_result):
        return False
    oauth_config = GetQuestionnaireOAuthConfigQuery()()
    return bool(oauth_config.get("configured"))


def _request_values(request: Request, fields: tuple[str, ...]) -> dict[str, str]:
    payload: dict[str, str] = {}
    for key in fields:
        value = str(request.query_params.get(key) or "").strip()
        if value:
            payload[key] = value
    return payload


def _questionnaire_oauth_start_url(slug: str, source_params: dict[str, str]) -> str:
    slug_value = str(slug or "").strip()
    query = {"slug": slug_value, "response_mode": "redirect", "redirect": f"/s/{slug_value}", **source_params}
    return f"/api/h5/wechat/oauth/start?{urlencode(query)}"


def _questionnaire_identity_from_request(request: Request) -> dict[str, str]:
    return _questionnaire_identity_result_from_request(request)["identity"]


def _questionnaire_identity_result_from_request(request: Request) -> dict[str, Any]:
    return QuestionnaireRespondentIdentityService().resolve(
        cookies=request.cookies,
        request_identity=_request_values(request, _QUESTIONNAIRE_IDENTITY_HINT_FIELDS),
        slug=str(request.path_params.get("slug") or request.query_params.get("slug") or ""),
    )


def _with_identity_cookie(response: Response, identity_result: dict[str, Any]) -> Response:
    cookie_value = str(identity_result.get("cookie_value") or "")
    if cookie_value:
        response.set_cookie(
            str(identity_result.get("cookie_name") or COOKIE_NAME),
            cookie_value,
            httponly=True,
            secure=False,
            samesite="lax",
            max_age=60 * 60 * 24 * 365,
            path="/",
        )
    return response


def _questionnaire_share_url(request: Request, questionnaire: dict[str, Any]) -> str:
    public_url = str(questionnaire.get("public_url") or "").strip()
    if public_url.startswith(("http://", "https://")):
        return public_url
    public_path = str(questionnaire.get("public_path") or public_url or "").strip()
    if not public_path:
        slug = str(questionnaire.get("slug") or "").strip()
        public_path = f"/s/{slug}" if slug else ""
    if not public_path:
        return ""
    if not public_path.startswith("/"):
        public_path = f"/{public_path}"
    return f"{str(request.base_url).rstrip('/')}{public_path}"


@router.get("/api/admin/questionnaires", response_model=None)
def list_questionnaires(limit: int = 50, offset: int = 0) -> Any:
    return _read_response(ListQuestionnairesQuery()(limit=limit, offset=offset))


@router.get("/api/admin/questionnaires/preflight", response_model=None)
async def questionnaire_preflight(request: Request) -> dict | Response:
    return GetQuestionnairePreflightQuery()()


@router.post("/api/admin/questionnaires")
async def create_questionnaire(request: Request) -> Response:
    return await _execute_admin_write(request, "questionnaire.admin.create")


@router.get("/api/admin/questionnaires/{questionnaire_id}", response_model=None)
def get_questionnaire(questionnaire_id: int) -> Any:
    try:
        return _read_response(_questionnaire_payload_with_nested_questions(GetQuestionnaireDetailQuery()(questionnaire_id)))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/questionnaires/{questionnaire_id}/questions", response_model=None)
def get_questionnaire_questions(questionnaire_id: int) -> Any:
    try:
        return _read_response(ListQuestionnaireQuestionsQuery()(questionnaire_id))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/questionnaires/{questionnaire_id}/results", response_model=None)
def get_questionnaire_results(questionnaire_id: int) -> Any:
    try:
        return _read_response(GetQuestionnaireResultsSummaryQuery()(questionnaire_id))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/questionnaires/{questionnaire_id}/submissions", response_model=None)
def get_questionnaire_submissions(questionnaire_id: int, limit: int = 20, offset: int = 0) -> Any:
    try:
        return _read_response(ListQuestionnaireSubmissionsQuery()(questionnaire_id, limit=limit, offset=offset))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/questionnaires/{questionnaire_id}/share")
def get_questionnaire_share(questionnaire_id: int, request: Request) -> dict:
    try:
        detail = GetQuestionnaireDetailQuery()(questionnaire_id)
        questionnaire = detail["questionnaire"]
        return GetQuestionnaireShareQuery()(
            questionnaire_id,
            share_url=_questionnaire_share_url(request, questionnaire),
        )
    except Exception as exc:
        _raise_http(exc)


@router.put("/api/admin/questionnaires/{questionnaire_id}")
@router.patch("/api/admin/questionnaires/{questionnaire_id}")
async def update_questionnaire(questionnaire_id: int, request: Request) -> Response:
    return await _execute_admin_write(request, "questionnaire.admin.update", questionnaire_id=questionnaire_id)


@router.post("/api/admin/questionnaires/{questionnaire_id}/duplicate")
async def duplicate_questionnaire(questionnaire_id: int, request: Request) -> Response:
    return await _execute_admin_write(request, "questionnaire.admin.duplicate", questionnaire_id=questionnaire_id)


@router.post("/api/admin/questionnaires/{questionnaire_id}/publish")
async def publish_questionnaire(questionnaire_id: int, request: Request) -> Response:
    return await _execute_admin_write(request, "questionnaire.admin.publish", questionnaire_id=questionnaire_id)


@router.post("/api/admin/questionnaires/{questionnaire_id}/disable")
async def disable_questionnaire(questionnaire_id: int, request: Request) -> Response:
    body = await _json_body(request)
    enabled = not bool(body.get("is_disabled", True))
    command_name = "questionnaire.admin.enable" if enabled else "questionnaire.admin.disable"
    return await _execute_admin_write(request, command_name, questionnaire_id=questionnaire_id, body=body)


@router.post("/api/admin/questionnaires/{questionnaire_id}/enable")
async def enable_questionnaire(questionnaire_id: int, request: Request) -> Response:
    return await _execute_admin_write(request, "questionnaire.admin.enable", questionnaire_id=questionnaire_id)


@router.delete("/api/admin/questionnaires/{questionnaire_id}")
async def delete_questionnaire(questionnaire_id: int, request: Request) -> Response:
    return await _execute_admin_write(request, "questionnaire.admin.delete", questionnaire_id=questionnaire_id)


@router.get("/api/admin/questionnaires/{questionnaire_id}/export")
async def export_questionnaire(questionnaire_id: int, request: Request) -> Response:
    try:
        command = QuestionnaireAdminWriteCommand(
            command_name="questionnaire.admin.export_download",
            questionnaire_id=questionnaire_id,
            payload={"limit": 10000},
            idempotency_key=str(request.headers.get("Idempotency-Key") or request.query_params.get("idempotency_key") or "").strip(),
            actor_id=str(request.headers.get("X-AICRM-Actor-Id") or "questionnaire_admin"),
            actor_type=str(request.headers.get("X-AICRM-Actor-Type") or "user"),
            source_route=request.url.path,
            trace_id=str(request.headers.get("X-Request-Id") or uuid4().hex),
        )
        response = execute_questionnaire_admin_write(command)
        return _csv_download_response(response)
    except QuestionnaireAdminWriteInputError as exc:
        return _write_error(str(exc), status_code=400, source_status="input_error", write_model_status="input_error")
    except QuestionnaireAdminWriteNotFoundError as exc:
        return _write_error(str(exc), status_code=404, source_status="not_found", write_model_status="not_found")
    except QuestionnaireAdminWriteProductionUnavailableError as exc:
        return _write_error(
            str(exc),
            status_code=503,
            source_status="production_unavailable",
            write_model_status="unavailable",
            degraded=True,
        )


@router.post("/api/admin/questionnaires/{questionnaire_id}/export/preview")
async def export_questionnaire_preview(questionnaire_id: int, request: Request) -> Response:
    return await _execute_admin_write(request, "questionnaire.admin.export_preview", questionnaire_id=questionnaire_id)


@router.get("/api/admin/questionnaires/{questionnaire_id}/latest-submit-debug")
def latest_submit_debug(questionnaire_id: int) -> dict:
    try:
        return LatestSubmitDebugQuery()(questionnaire_id)
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/h5/questionnaires/{slug}")
def public_get_questionnaire(request: Request, slug: str) -> Response:
    try:
        identity_result = _questionnaire_identity_result_from_request(request)
        submission_status = GetPublicQuestionnaireSubmissionStatusQuery()(slug, identity=identity_result["identity"])
        if submission_status.get("submitted"):
            return _with_identity_cookie(JSONResponse(
                {
                    "ok": False,
                    "error": "already_submitted",
                    "message": "已经提交过该问卷",
                    "redirect_url": submission_status.get("redirect_url") or submission_status.get("submitted_url"),
                },
                status_code=409,
            ), identity_result)
        return _with_identity_cookie(JSONResponse(jsonable_encoder(GetPublicQuestionnaireQuery()(slug))), identity_result)
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/h5/questionnaires/{slug}/submit")
async def public_submit_questionnaire(slug: str, request: Request) -> Response:
    return await _execute_h5_submit(request, slug)


@router.options("/api/h5/questionnaires/{slug}/submit")
def public_submit_questionnaire_options(slug: str) -> Response:
    return _h5_options_response()


@router.post("/api/h5/questionnaires/{slug}/client-diagnostics")
async def public_questionnaire_client_diagnostics(slug: str, request: Request) -> Response:
    return await _execute_h5_diagnostics(request, slug)


@router.options("/api/h5/questionnaires/{slug}/client-diagnostics")
def public_questionnaire_client_diagnostics_options(slug: str) -> Response:
    return _h5_options_response()


@router.get("/api/h5/questionnaires/{slug}/result/{submission_id}")
def public_submission_result(slug: str, submission_id: str) -> dict:
    try:
        return GetSubmissionResultQuery()(slug, submission_id)
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/h5/wechat/oauth/start", response_model=None)
def wechat_oauth_start(
    slug: str | None = None,
    state: str | None = None,
    redirect: str | None = None,
    scene: str | None = None,
    response_mode: str | None = None,
    browser_redirect: str | None = None,
    source_channel: str | None = None,
    campaign_id: str | None = None,
    staff_id: str | None = None,
    openid: str | None = None,
    unionid: str | None = None,
    external_userid: str | None = None,
) -> Any:
    browser_mode = _is_redirect_response_mode(response_mode, browser_redirect)
    payload = StartWechatOAuthQuery()(
        OAuthStartRequest(
            slug=slug,
            state=state,
            redirect=redirect,
            scene=scene,
            browser_redirect=browser_mode,
            source_channel=source_channel,
            campaign_id=campaign_id,
            staff_id=staff_id,
            openid=openid,
            unionid=unionid,
            external_userid=external_userid,
        )
    )
    if not browser_mode:
        return payload
    if payload.get("ok") and payload.get("redirect_url") and payload.get("adapter_mode") != "real_blocked" and not payload.get("external_call_blocked"):
        return RedirectResponse(str(payload["redirect_url"]), status_code=302)
    logger.warning(
        "questionnaire oauth start browser redirect unavailable",
        extra={
            "slug": slug,
            "adapter_mode": payload.get("adapter_mode"),
            "error": payload.get("error"),
            "source_status": payload.get("source_status"),
        },
    )
    return _oauth_html_error(
        title="当前微信授权配置未完成",
        message="当前微信授权配置未完成，请联系管理员。",
        return_url=redirect,
        slug=slug or state,
        status_code=503,
    )


@router.options("/api/h5/wechat/oauth/start")
def wechat_oauth_start_options() -> Response:
    return _oauth_options_response()


@router.get("/api/h5/wechat/oauth/callback")
def wechat_oauth_callback(
    code: str | None = None,
    state: str | None = None,
    redirect: str | None = None,
    response_mode: str | None = None,
    browser_redirect: str | None = None,
    error: str | None = None,
    errcode: str | None = None,
    openid: str | None = None,
    unionid: str | None = None,
    external_userid: str | None = None,
) -> Response:
    state_context = questionnaire_oauth_state_context(state)
    browser_mode = _is_redirect_response_mode(response_mode, browser_redirect) or bool(state_context.get("browser_redirect"))
    payload = CompleteWechatOAuthCallbackCommand()(
        OAuthCallbackRequest(
            code=code,
            state=state,
            redirect=redirect,
            error=error,
            errcode=errcode,
            openid=openid,
            unionid=unionid,
            external_userid=external_userid,
        )
    )
    signed_cookie = str(payload.pop("session_cookie", "") or "")
    status_code = int(payload.pop("status_code", 200 if payload.get("ok") else 400) or 400)
    if browser_mode:
        if payload.get("ok"):
            redirect_target = str(payload.get("redirect_url") or state_context.get("redirect_url") or redirect or "")
            redirect_response = RedirectResponse(
                _safe_oauth_success_redirect_url(redirect_target, str(payload.get("slug") or state_context.get("slug") or "")),
                status_code=302,
            )
            if signed_cookie:
                redirect_response.set_cookie(
                    COOKIE_NAME,
                    signed_cookie,
                    httponly=True,
                    secure=False,
                    samesite="lax",
                    max_age=3600,
                    path="/",
                )
            return redirect_response
        logger.warning(
            "questionnaire oauth callback browser redirect failed",
            extra={
                "slug": payload.get("slug") or state_context.get("slug"),
                "adapter_mode": payload.get("adapter_mode"),
                "error": payload.get("error"),
                "source_status": payload.get("source_status"),
            },
        )
        return _oauth_html_error(
            title="授权未完成",
            message="授权未完成，请重新进入问卷。",
            return_url=str(state_context.get("redirect_url") or redirect or ""),
            slug=str(payload.get("slug") or state_context.get("slug") or ""),
            status_code=status_code,
        )
    json_response = JSONResponse(jsonable_encoder(payload), status_code=status_code)
    if payload.get("ok") and signed_cookie:
        json_response.set_cookie(
            COOKIE_NAME,
            signed_cookie,
            httponly=True,
            secure=False,
            samesite="lax",
            max_age=3600,
            path="/",
        )
    return json_response


@router.options("/api/h5/wechat/oauth/callback")
def wechat_oauth_callback_options() -> Response:
    return _oauth_options_response()


@router.get("/s/{slug}", response_class=HTMLResponse)
def public_questionnaire_h5_page(request: Request, slug: str):
    try:
        payload = GetPublicQuestionnaireQuery()(slug)
    except Exception as exc:
        _raise_http(exc)
    questionnaire = jsonable_encoder(payload["questionnaire"])
    questions = jsonable_encoder(payload.get("questions") or [])
    source_params = _request_values(request, _QUESTIONNAIRE_SOURCE_PARAM_FIELDS)
    request_hints = _request_values(request, _QUESTIONNAIRE_META_FIELDS)
    identity_result = _questionnaire_identity_result_from_request(request)
    identity = dict(identity_result.get("identity") or {})
    request_hints = {**request_hints, **{key: value for key, value in identity.items() if value}}
    is_wechat_browser = _is_wechat_browser(request)
    is_authorized = _is_authorized_identity(identity, identity_result)
    oauth_config = GetQuestionnaireOAuthConfigQuery()()
    oauth_configured = bool(oauth_config.get("configured"))
    should_require_oauth = is_wechat_browser and oauth_configured and not is_authorized
    submission_status = GetPublicQuestionnaireSubmissionStatusQuery()(slug, identity=identity)
    if submission_status.get("submitted") and not should_require_oauth:
        redirect_url = str(
            submission_status.get("redirect_url") or submission_status.get("submitted_url") or f"/s/{slug}/submitted"
        ).strip()
        return _with_identity_cookie(RedirectResponse(redirect_url, status_code=302), identity_result)
    page_mode = "auth_gate" if should_require_oauth else "questionnaire"
    env_notice = ""
    if page_mode == "auth_gate":
        env_notice = "授权后即可填写问卷信息。" if oauth_configured else "当前微信登录配置未完成，请联系管理员。"
    page_state = {
        "mode": page_mode,
        "slug": slug,
        "title": questionnaire["title"],
        "description": questionnaire.get("description") or "",
        "env_notice": env_notice,
        "oauth_start_url": _questionnaire_oauth_start_url(slug, source_params) if oauth_configured else "",
        "submit_url": f"/api/h5/questionnaires/{slug}/submit",
        "api_url": f"/api/h5/questionnaires/{slug}",
        "diagnostics_url": f"/api/h5/questionnaires/{slug}/client-diagnostics",
        "submitted_url": f"/s/{slug}/submitted",
        "request_hints": request_hints,
        "initial_questionnaire": {**questionnaire, "questions": questions} if page_mode == "questionnaire" else None,
        "answer_display_mode": questionnaire.get("answer_display_mode") or "all_in_one",
        "prefill_fields": {},
        "form_error": "",
        "is_wechat_browser": is_wechat_browser,
        "is_authorized": is_authorized,
    }
    response = templates.TemplateResponse(
        request,
        "questionnaire_h5_page.html",
        {"request": request, "page_state": page_state},
    )
    return _with_identity_cookie(response, identity_result)


@router.get("/s/{slug}/submitted", response_class=HTMLResponse)
def public_questionnaire_submitted(request: Request, slug: str):
    return templates.TemplateResponse(request, "questionnaire_h5_submitted.html", {"request": request})
