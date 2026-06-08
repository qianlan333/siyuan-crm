from __future__ import annotations

from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from aicrm_next.admin_shell import shell_context

from .application import GetQuestionnaireEditorQuery, GetQuestionnairePreflightQuery, ListQuestionnairesQuery
from .external_push_logs import (
    QuestionnaireExternalPushLogReadService,
    QuestionnaireExternalPushRetryBatchCommand,
    QuestionnaireExternalPushRetryCommand,
    QuestionnaireExternalPushRetryService,
)

router = APIRouter()
_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_ADMIN_SHELL_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "admin_shell" / "templates"
templates = Jinja2Templates(directory=[_TEMPLATES_DIR, _ADMIN_SHELL_TEMPLATES_DIR])


def _is_assessment_template_asset(questionnaire: dict | None) -> bool:
    if not questionnaire or not questionnaire.get("assessment_enabled"):
        return False
    config = questionnaire.get("assessment_config") if isinstance(questionnaire.get("assessment_config"), dict) else {}
    asset_kind = str(config.get("asset_kind") or "").strip()
    if asset_kind:
        return asset_kind == "assessment_template"
    return str(config.get("template_id") or "").strip() == "siyuan_ip_business"


def _placeholder_response(
    request: Request,
    *,
    page_title: str,
    page_summary: str,
    state_title: str,
    state_body: str,
    state_items: list[str],
    status_code: int,
    page_error: str = "",
) -> Response:
    context = shell_context(
        request=request,
        page_title=page_title,
        page_summary=page_summary,
        active_endpoint="api.admin_questionnaires",
    )
    context.update(
        {
            "breadcrumbs": [
                {"label": "客户管理后台", "href": "/admin"},
                {"label": "问卷管理", "href": "/admin/questionnaires"},
                {"label": page_title, "href": ""},
            ],
            "state_title": state_title,
            "state_body": state_body,
            "state_items": state_items,
            "actions": [{"label": "返回问卷管理", "href": "/admin/questionnaires", "variant": "secondary"}],
            "page_error": page_error,
        }
    )
    return templates.TemplateResponse(request, "admin_console/questionnaire_state.html", context, status_code=status_code)


def _questionnaire_editor_response(
    request: Request,
    *,
    questionnaire_id: int | None = None,
) -> Response:
    payload: dict | None = None
    page_error = ""
    if questionnaire_id is not None:
        try:
            payload = GetQuestionnaireEditorQuery()(questionnaire_id)
        except Exception as exc:
            return _placeholder_response(
                request,
                page_title="问卷不存在",
                page_summary="当前没有找到这个问卷。",
                state_title="问卷不存在",
                state_body="请确认问卷编号是否正确，或稍后重试。",
                state_items=["问卷可能已被删除", "当前环境也可能还没有初始化相关数据"],
                status_code=404,
                page_error=f"未找到问卷：{exc}",
            )
        if payload.get("source_status") == "production_unavailable":
            return _placeholder_response(
                request,
                page_title="问卷数据不可用",
                page_summary="当前生产问卷读模型不可用。",
                state_title="生产问卷数据不可用",
                state_body=str(payload.get("page_error") or "请确认生产问卷读模型已经完成同步。"),
                state_items=["source_status=production_unavailable", "fallback_used=false", "route_owner=ai_crm_next"],
                status_code=503,
                page_error=str(payload.get("page_error") or ""),
            )

    questionnaire = jsonable_encoder((payload or {}).get("questionnaire")) if payload else None
    if questionnaire is not None and isinstance(payload, dict):
        questionnaire["questions"] = jsonable_encoder(questionnaire.get("questions") or payload.get("questions") or [])
    default_assessment = (
        (questionnaire_id is None and str(request.query_params.get("mode") or "").strip() == "assessment")
        or _is_assessment_template_asset(questionnaire)
    )
    new_heading = "创建测评问卷模板" if default_assessment else "新建问卷"
    edit_heading = "编辑测评问卷模板" if default_assessment else "编辑问卷"
    new_subtitle = (
        "配置测评题目、维度分型和结果页规则，保存后可作为普通问卷的整组引用模板。"
        if default_assessment
        else "从空白模板开始搭建题目、标签和分数规则。"
    )
    edit_subtitle = (
        "维护这个测评模板的题目、维度分型和结果页规则。"
        if default_assessment
        else "维护当前问卷的题目、分数规则和发布设置。"
    )
    return templates.TemplateResponse(
        request,
        "admin_questionnaires.html",
        {
            "request": request,
            "editor_mode": "edit" if questionnaire_id is not None else "new",
            "editor_page_title": (questionnaire or {}).get("title")
            or (questionnaire or {}).get("name")
            or (edit_heading if questionnaire_id is not None else new_heading),
            "editor_heading": edit_heading if questionnaire_id is not None else new_heading,
            "editor_subtitle": edit_subtitle if questionnaire_id is not None else new_subtitle,
            "editor_back_href": "/admin/questionnaires",
            "editor_default_assessment": default_assessment,
            "initial_questionnaire": questionnaire,
            "initial_questionnaire_id": questionnaire_id,
            "page_error": page_error,
        },
    )


@router.get("/admin/questionnaires", name="api.admin_questionnaires")
def admin_questionnaires(request: Request) -> Response:
    list_payload = ListQuestionnairesQuery()(limit=100, offset=0)
    preflight_error = str(list_payload.get("page_error") or "") if list_payload.get("degraded") else ""
    preflight_payload = GetQuestionnairePreflightQuery()()
    context = shell_context(
        request=request,
        page_title="问卷管理",
        page_summary="读取生产问卷列表，保留新建、编辑、停用、删除和导出入口。",
        active_endpoint="api.admin_questionnaires",
    )
    context["breadcrumbs"] = [
        {"label": "客户管理后台", "href": "/admin"},
        {"label": "问卷管理", "href": ""},
    ]
    context["page_actions"] = [
        {"label": "创建新问卷", "href": "/admin/questionnaires/new", "variant": "primary"},
        {"label": "创建测评问卷模板", "href": "/admin/questionnaires/new?mode=assessment", "variant": "secondary"},
        {"label": "刷新", "href": "/admin/questionnaires", "variant": "ghost"},
    ]
    questionnaires = jsonable_encoder(list_payload.get("questionnaires") or list_payload.get("items") or [])
    context["questionnaire_payload"] = {
        "questionnaires": questionnaires,
        "preflight": preflight_payload["checks"],
        "preflight_error": preflight_error,
        "total": list_payload.get("total", len(questionnaires)),
        "source_status": list_payload.get("source_status", "local_contract_probe"),
        "read_model_status": list_payload.get("read_model_status", ""),
        "route_owner": list_payload.get("route_owner", "ai_crm_next"),
        "fallback_used": bool(list_payload.get("fallback_used", False)),
        "degraded": bool(list_payload.get("degraded", False)),
    }
    if preflight_error:
        context["page_error"] = preflight_error
    return templates.TemplateResponse(request, "admin_console/questionnaires.html", context)


@router.get("/admin/questionnaires/ui", name="api.admin_console_questionnaires")
def admin_questionnaires_legacy_ui_alias() -> RedirectResponse:
    return RedirectResponse("/admin/questionnaires", status_code=302)


@router.get("/admin/questionnaires/new", name="api.admin_console_questionnaire_new")
def admin_questionnaire_new(request: Request) -> Response:
    return _questionnaire_editor_response(request)


@router.get("/admin/questionnaires/{questionnaire_id:int}", name="api.admin_console_questionnaire_detail")
def admin_questionnaire_detail(request: Request, questionnaire_id: int) -> Response:
    return _questionnaire_editor_response(request, questionnaire_id=questionnaire_id)


def _render_questionnaire_external_push_logs(request: Request) -> Response:
    questionnaire_id = request.path_params.get("questionnaire_id")
    service = QuestionnaireExternalPushLogReadService()
    if questionnaire_id:
        payload = service.questionnaire_logs(
            int(questionnaire_id),
            status=str(request.query_params.get("status") or ""),
            limit=str(request.query_params.get("limit") or "50"),
        )
        if payload is None:
            return JSONResponse({"ok": False, "error": "questionnaire not found", "source_status": "not_found"}, status_code=404)
    else:
        payload = service.global_logs(
            questionnaire_id=str(request.query_params.get("questionnaire_id") or ""),
            questionnaire_title=str(request.query_params.get("questionnaire_title") or ""),
            status=str(request.query_params.get("status") or ""),
            user_id=str(request.query_params.get("user_id") or ""),
            target_url=str(request.query_params.get("target_url") or ""),
            limit=str(request.query_params.get("limit") or "50"),
        )
    context = shell_context(
        request=request,
        page_title="问卷外推记录",
        page_summary="查看问卷提交后的外部推送结果、失败原因和补发计划。",
        active_endpoint="api.admin_questionnaires",
    )
    context["breadcrumbs"] = [
        {"label": "客户管理后台", "href": "/admin"},
        {"label": "问卷管理", "href": "/admin/questionnaires"},
        {"label": "问卷外推记录", "href": ""},
    ]
    context["logs_payload"] = payload
    return templates.TemplateResponse(request, "admin_console/questionnaire_external_push_logs.html", context)


async def _handle_questionnaire_external_push_retry(request: Request) -> Response:
    form = await request.form()
    service = QuestionnaireExternalPushRetryService()
    push_log_id = request.path_params.get("push_log_id")
    if push_log_id:
        result = service.retry_one(
            QuestionnaireExternalPushRetryCommand(
                push_log_id=int(push_log_id),
                actor_id=str(request.headers.get("X-AICRM-Actor-Id") or "questionnaire_admin"),
                actor_type=str(request.headers.get("X-AICRM-Actor-Type") or "user"),
                source_route=str(request.url.path),
                idempotency_key=str(request.headers.get("Idempotency-Key") or ""),
            )
        )
    else:
        result = service.retry_batch(
            QuestionnaireExternalPushRetryBatchCommand(
                push_log_ids=[int(item) for item in form.getlist("push_log_ids") if str(item).strip().isdigit()],
                questionnaire_id=int(request.path_params["questionnaire_id"]) if request.path_params.get("questionnaire_id") else None,
                actor_id=str(request.headers.get("X-AICRM-Actor-Id") or "questionnaire_admin"),
                actor_type=str(request.headers.get("X-AICRM-Actor-Type") or "user"),
                source_route=str(request.url.path),
                idempotency_key=str(request.headers.get("Idempotency-Key") or ""),
            )
        )
    if "application/json" in str(request.headers.get("accept") or "").lower():
        return JSONResponse(result)
    return RedirectResponse(_external_push_logs_redirect_url(request, form), status_code=303)


def _external_push_logs_redirect_url(request: Request, form: object) -> str:
    questionnaire_id = request.path_params.get("questionnaire_id")
    base = (
        f"/admin/questionnaires/{int(questionnaire_id)}/external-push-logs"
        if questionnaire_id
        else "/admin/questionnaires/external-push-logs"
    )
    query: dict[str, str] = {}
    for key in ["questionnaire_id", "questionnaire_title", "status", "user_id", "target_url", "limit"]:
        value = getattr(form, "get", lambda *_: "")(key)
        if value not in (None, ""):
            query[key] = str(value)
    return base + (f"?{urlencode(query)}" if query else "")


@router.api_route(
    "/admin/questionnaires/external-push-logs",
    methods=["GET"],
    name="api.admin_console_global_questionnaire_external_push_logs",
)
@router.api_route(
    "/admin/questionnaires/external-push-logs/retry-batch",
    methods=["POST"],
    name="api.admin_console_global_questionnaire_external_push_logs_retry_batch",
)
@router.api_route(
    "/admin/questionnaires/external-push-logs/{push_log_id:int}/retry",
    methods=["POST"],
    name="api.admin_console_global_questionnaire_external_push_logs_retry",
)
@router.api_route(
    "/admin/questionnaires/{questionnaire_id:int}/external-push-logs",
    methods=["GET"],
    name="api.admin_console_questionnaire_external_push_logs",
)
@router.api_route(
    "/admin/questionnaires/{questionnaire_id:int}/external-push-logs/retry-batch",
    methods=["POST"],
    name="api.admin_console_questionnaire_external_push_logs_retry_batch",
)
@router.api_route(
    "/admin/questionnaires/{questionnaire_id:int}/external-push-logs/{push_log_id:int}/retry",
    methods=["POST"],
    name="api.admin_console_questionnaire_external_push_logs_retry",
)
async def admin_questionnaire_external_push_logs(request: Request) -> Response:
    if request.method == "POST":
        return await _handle_questionnaire_external_push_retry(request)
    return _render_questionnaire_external_push_logs(request)
