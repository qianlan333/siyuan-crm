from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from aicrm_next.platform_foundation.internal_run_due_guard import maybe_guard_internal_run_due_request
from aicrm_next.shared.errors import ContractError, NotFoundError

from .application import (
    ApplyActivationWebhookCommand,
    GetBehaviorSegmentRulesQuery,
    ConfirmConversionCommand,
    CreateAgentCommand,
    CreateTaskCommand,
    CreateWorkflowCommand,
    CreateWorkflowNodeCommand,
    DeleteWorkflowNodeCommand,
    EnterSilentPoolCommand,
    ExitMarketingCommand,
    CreateActionTemplateCommand,
    CreateProfileSegmentTemplateCommand,
    CreateTaskGroupCommand,
    GetAgentOutputDetailQuery,
    GetAgentRunDetailQuery,
    GetTaskDetailQuery,
    ListActionTemplatesQuery,
    ListAgentsQuery,
    ListAgentOutputsQuery,
    ListAgentRunsQuery,
    ListTasksQuery,
    ListTaskGroupsQuery,
    ListWorkflowsQuery,
    ListWorkflowNodesQuery,
    GetProfileSegmentTemplateCatalogQuery,
    GetProfileSegmentTemplateOptionsQuery,
    GetProfileSegmentTemplateQuery,
    GetAutomationMemberDetailQuery,
    GetAutomationRuntimeContractQuery,
    ListProfileSegmentTemplatesQuery,
    ListAutomationExecutionRecordsQuery,
    ListAutomationMembersQuery,
    OverrideFollowupTypeCommand,
    PushMemberContextToOpenClawCommand,
    SaveAgentMaterialsCommand,
    SaveBehaviorSegmentSendContentCommand,
    SaveProfileSegmentSendContentCommand,
    SaveUnifiedSendContentCommand,
    UpdateTaskCommand,
    UpdateWorkflowNodeCommand,
    UpdateTaskSendStrategyCommand,
    UpdateProfileSegmentTemplateCommand,
)
from .signup_conversion_read_model import SignupConversionReadModel
from .programs import (
    AutomationProgramDataUnavailable,
    copy_automation_program_operation_task,
    create_automation_program_operation_task,
    create_automation_program_operation_task_group,
    delete_automation_program_operation_task_group,
    get_automation_program_members_payload,
    get_automation_program_overview_payload,
    list_automation_programs_payload,
    list_automation_program_operation_tasks,
    preview_automation_program_operation_task_audience,
    publish_automation_program_entry,
    publish_automation_program_full,
    save_automation_program_audience_entry_rule,
    save_automation_program_operation_task_content,
    save_automation_program_segmentation,
    set_automation_program_operation_task_status,
    update_automation_program_operation_task,
    update_automation_program_operation_task_send_strategy,
)
from .timers import (
    AutomationTimerInputError,
    PlanAutomationJobsRunDueCommand,
    PlanReplyMonitorCaptureCommand,
    PlanReplyMonitorRunDueCommand,
    PreviewAutomationJobsRunDueCommand,
    diagnostics_payload as timer_diagnostics_payload,
    execute_automation_timer_command,
    normalize_batch_size as normalize_timer_batch_size,
    normalize_job_codes,
    normalize_limit as normalize_timer_limit,
)
from .workspace_runtime import (
    AutomationWorkspaceRuntimeInputError,
    PlanAutomationExecutionItemOutboundDispatchCommand,
    PlanAutomationOperationTasksRunDueCommand,
    diagnostics_payload as workspace_runtime_diagnostics_payload,
    execute_workspace_runtime_command,
    normalize_execution_item_id,
    normalize_program_id,
)
from .member_actions import (
    AutomationMemberActionCommand,
    AutomationMemberActionInputError,
    GetAutomationMemberDetailQuery as GetAutomationMemberSafeDetailQuery,
    MarkAutomationMemberWonCommand,
    PlanAutomationMemberOpenClawPushCommand,
    PutAutomationMemberInPoolCommand,
    RemoveAutomationMemberFromPoolCommand,
    SetAutomationMemberFocusCommand,
    SetAutomationMemberNormalCommand,
    UnmarkAutomationMemberWonCommand,
    diagnostics_payload as member_action_diagnostics_payload,
    execute_member_action_command,
    normalize_actor as normalize_member_action_actor,
    normalize_identity as normalize_member_action_identity,
    read_automation_member_detail,
)
from .customer_webhooks import (
    ApplyCustomerActivationWebhookCommand,
    CustomerAutomationWebhookInputError,
    PlanCustomerWebhookDeliveryRetryCommand,
    PlanCustomerWebhookDeliveryRetryDueCommand,
    diagnostics_payload as customer_webhook_diagnostics_payload,
    execute_customer_webhook_command,
    normalize_actor as normalize_customer_webhook_actor,
    normalize_delivery_id,
    normalize_limit as normalize_customer_webhook_limit,
    normalize_mobile,
)
from .dto import (
    ActivationWebhookRequest,
    AgentMaterialsUpdateRequest,
    AgentCreateRequest,
    AgentListRequest,
    AgentOutputDetailRequest,
    AgentOutputListRequest,
    AgentRunDetailRequest,
    AgentRunListRequest,
    ActionTemplateCreateRequest,
    ActionTemplateListRequest,
    AutomationActionRequest,
    BehaviorSegmentSendContentUpdateRequest,
    OverrideFollowupTypeRequest,
    ProfileSegmentSendContentUpdateRequest,
    ProfileSegmentTemplateCreateRequest,
    ProfileSegmentTemplateListRequest,
    ProfileSegmentTemplateUpdateRequest,
    PushOpenClawContextRequest,
    SendStrategyUpdateRequest,
    TaskCreateRequest,
    TaskGroupCreateRequest,
    TaskGroupListRequest,
    TaskListRequest,
    TaskUpdateRequest,
    UnifiedSendContentUpdateRequest,
    WorkflowCreateRequest,
    WorkflowListRequest,
    WorkflowNodeCreateRequest,
    WorkflowNodeListRequest,
    WorkflowNodeUpdateRequest,
)
from .group_ops.api import router as group_ops_router
from .overview_read_model import AutomationOverviewReadModel, AutomationPoolReadModel

router = APIRouter()
router.include_router(group_ops_router)

_TIMER_HEADERS = {
    "X-AICRM-Route-Owner": "ai_crm_next",
    "X-AICRM-Fallback-Used": "false",
    "X-AICRM-Real-External-Call-Executed": "false",
    "X-AICRM-Automation-Runtime-Executed": "false",
    "X-AICRM-WeCom-Send-Executed": "false",
}
_WORKSPACE_RUNTIME_HEADERS = {
    "X-AICRM-Route-Owner": "ai_crm_next",
    "X-AICRM-Fallback-Used": "false",
    "X-AICRM-Real-External-Call-Executed": "false",
    "X-AICRM-Automation-Runtime-Executed": "false",
    "X-AICRM-Operation-Tasks-Executed": "false",
    "X-AICRM-bazhuayu-Send-Executed": "false",
    "X-AICRM-WeCom-Send-Executed": "false",
}
_MEMBER_ACTION_HEADERS = {
    "X-AICRM-Route-Owner": "ai_crm_next",
    "X-AICRM-Fallback-Used": "false",
    "X-AICRM-Real-External-Call-Executed": "false",
    "X-AICRM-Automation-Runtime-Executed": "false",
    "X-AICRM-OpenClaw-Push-Executed": "false",
    "X-AICRM-WeCom-Send-Executed": "false",
}
_CUSTOMER_WEBHOOK_HEADERS = {
    "X-AICRM-Route-Owner": "ai_crm_next",
    "X-AICRM-Fallback-Used": "false",
    "X-AICRM-Real-External-Call-Executed": "false",
    "X-AICRM-Outbound-Webhook-Executed": "false",
    "X-AICRM-Automation-Runtime-Executed": "false",
    "X-AICRM-WeCom-Send-Executed": "false",
}
_AUTOMATION_READ_MODEL_HEADERS = {
    "X-AICRM-Route-Owner": "ai_crm_next",
    "X-AICRM-Fallback-Used": "false",
}
_AUTOMATION_PROGRAM_HEADERS = {
    "X-AICRM-Route-Owner": "ai_crm_next",
    "X-AICRM-Fallback-Used": "false",
}


def _raise_http(exc: Exception) -> None:
    if isinstance(exc, NotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ContractError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail=str(exc)) from exc


def _json_result(payload: dict) -> JSONResponse:
    status_code = int(payload.get("status_code") or 200)
    return JSONResponse(payload, status_code=status_code)


def _timer_error(error: str, *, source_status: str, status_code: int = 400) -> JSONResponse:
    payload = timer_diagnostics_payload(source_status)
    payload.update(
        {
            "ok": False,
            "error": error,
            "planned_count": 0,
            "processed_count": 0,
            "captured_count": 0,
            "sent_count": 0,
            "failed_count": 0,
            "skipped_count": 0,
            "candidate_count": 0,
            "candidates": [],
            "job_codes": [],
            "estimated_actions": {
                "planned_action_count": 0,
                "runtime_execution_count": 0,
                "external_call_count": 0,
                "blocked_external_call_count": 0,
            },
        }
    )
    return JSONResponse(payload, status_code=status_code, headers=_TIMER_HEADERS)


def _bool_payload(value: Any, *, default: bool) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


async def _timer_payload(request: Request) -> dict[str, Any]:
    if request.headers.get("content-type", "").lower().startswith("application/json"):
        try:
            payload = await request.json()
        except Exception as exc:
            raise AutomationTimerInputError("payload must be valid JSON") from exc
    else:
        body = await request.body()
        payload = {} if not body else await request.json()
    if payload is None:
        merged: dict[str, Any] = {}
    elif isinstance(payload, dict):
        merged = dict(payload)
    else:
        raise AutomationTimerInputError("payload must be an object")
    for key in (
        "limit",
        "batch_size",
        "jobs",
        "job_codes",
        "dry_run",
        "preview",
        "scheduled_safe_mode",
        "allow_task_ids",
        "allow_workflow_ids",
        "allow_node_ids",
        "expected_due_count",
        "due_count",
    ):
        if key not in merged and key in request.query_params:
            merged[key] = request.query_params.get(key)
    return merged


def _timer_actor(request: Request, payload: dict[str, Any]) -> str:
    return str(payload.get("operator") or payload.get("actor_id") or request.headers.get("X-AICRM-Actor") or "timer").strip()


def _timer_common(request: Request, payload: dict[str, Any], source_route: str, *, default_limit: int) -> dict[str, Any]:
    limit = normalize_timer_limit(payload.get("limit"), default=default_limit)
    return {
        "idempotency_key": str(request.headers.get("Idempotency-Key") or payload.get("idempotency_key") or "").strip(),
        "actor_id": _timer_actor(request, payload),
        "actor_type": str(payload.get("actor_type") or "timer").strip(),
        "limit": limit,
        "batch_size": normalize_timer_batch_size(payload.get("batch_size"), default=limit),
        "job_codes": normalize_job_codes(payload.get("job_codes"), payload.get("jobs")),
        "dry_run": _bool_payload(payload.get("dry_run"), default=True),
        "source_route": source_route,
        "trace_id": str(request.headers.get("X-AICRM-Trace-Id") or payload.get("trace_id") or "").strip(),
    }


def _timer_response(command, *, source_status: str) -> JSONResponse:
    try:
        payload = execute_automation_timer_command(command)
    except AutomationTimerInputError as exc:
        return _timer_error(str(exc) or "input_error", source_status=source_status, status_code=400)
    except Exception as exc:
        return _timer_error(str(exc) or "timer_unavailable", source_status=source_status, status_code=503)
    return JSONResponse(payload, headers=_TIMER_HEADERS)


def _workspace_runtime_error(error: str, *, source_status: str, status_code: int = 400) -> JSONResponse:
    payload = workspace_runtime_diagnostics_payload(source_status)
    payload.update(
        {
            "ok": False,
            "error": error,
            "status": "input_error" if status_code == 400 else "error",
            "planned_count": 0,
            "processed_count": 0,
            "sent_count": 0,
            "failed_count": 0,
            "skipped_count": 0,
            "candidate_count": 0,
            "candidates": [],
            "estimated_actions": {
                "planned_action_count": 0,
                "runtime_execution_count": 0,
                "outbound_dispatch_count": 0,
                "blocked_external_call_count": 0,
            },
        }
    )
    return JSONResponse(payload, status_code=status_code, headers=_WORKSPACE_RUNTIME_HEADERS)


async def _workspace_runtime_payload(request: Request) -> dict[str, Any]:
    if request.headers.get("content-type", "").lower().startswith("application/json"):
        try:
            payload = await request.json()
        except Exception as exc:
            raise AutomationWorkspaceRuntimeInputError("payload must be valid JSON") from exc
    else:
        body = await request.body()
        payload = {} if not body else await request.json()
    if payload is None:
        merged: dict[str, Any] = {}
    elif isinstance(payload, dict):
        merged = dict(payload)
    else:
        raise AutomationWorkspaceRuntimeInputError("payload must be an object")
    for key in ("program_id", "dry_run"):
        if key not in merged and key in request.query_params:
            merged[key] = request.query_params.get(key)
    return merged


def _workspace_runtime_actor(request: Request, payload: dict[str, Any]) -> str:
    return str(payload.get("operator") or payload.get("actor_id") or request.headers.get("X-AICRM-Actor") or "workspace_runtime").strip()


def _workspace_runtime_common(request: Request, payload: dict[str, Any], source_route: str) -> dict[str, Any]:
    return {
        "idempotency_key": str(request.headers.get("Idempotency-Key") or payload.get("idempotency_key") or "").strip(),
        "actor_id": _workspace_runtime_actor(request, payload),
        "actor_type": str(payload.get("actor_type") or "timer").strip(),
        "program_id": normalize_program_id(payload.get("program_id")),
        "dry_run": _bool_payload(payload.get("dry_run"), default=True),
        "source_route": source_route,
        "trace_id": str(request.headers.get("X-AICRM-Trace-Id") or payload.get("trace_id") or "").strip(),
    }


def _workspace_runtime_response(command, *, source_status: str) -> JSONResponse:
    try:
        payload = execute_workspace_runtime_command(command)
    except AutomationWorkspaceRuntimeInputError as exc:
        return _workspace_runtime_error(str(exc) or "input_error", source_status=source_status, status_code=400)
    except Exception as exc:
        return _workspace_runtime_error(str(exc) or "workspace_runtime_unavailable", source_status=source_status, status_code=503)
    return JSONResponse(payload, headers=_WORKSPACE_RUNTIME_HEADERS)


def _member_action_error(error: str, *, source_status: str = "next_command", status_code: int = 400) -> JSONResponse:
    payload = member_action_diagnostics_payload(source_status)
    payload.update(
        {
            "ok": False,
            "error": error,
            "status": "input_error" if status_code == 400 else "error",
            "planned_count": 0,
            "processed_count": 0,
            "sent_count": 0,
            "failed_count": 0,
            "skipped_count": 0,
        }
    )
    return JSONResponse(payload, status_code=status_code, headers=_MEMBER_ACTION_HEADERS)


async def _member_action_payload(request: Request) -> dict[str, Any]:
    if request.headers.get("content-type", "").lower().startswith("application/json"):
        try:
            payload = await request.json()
        except Exception as exc:
            raise AutomationMemberActionInputError("payload must be valid JSON") from exc
    else:
        body = await request.body()
        payload = {} if not body else await request.json()
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise AutomationMemberActionInputError("payload must be an object")
    return dict(payload)


def _member_action_common(
    request: Request,
    payload: dict[str, Any],
    source_route: str,
) -> dict[str, Any]:
    identity = normalize_member_action_identity(
        external_contact_id=payload.get("external_contact_id") or payload.get("external_userid"),
        phone=payload.get("phone") or payload.get("mobile"),
    )
    return {
        "idempotency_key": str(request.headers.get("Idempotency-Key") or payload.get("idempotency_key") or "").strip(),
        "actor_id": normalize_member_action_actor(payload.get("operator_id") or payload.get("operator") or payload.get("actor_id") or request.headers.get("X-AICRM-Actor")),
        "actor_type": str(payload.get("actor_type") or "user").strip(),
        "external_contact_id": identity["external_contact_id"],
        "phone": identity["phone"],
        "source_route": source_route,
        "trace_id": str(request.headers.get("X-AICRM-Trace-Id") or payload.get("trace_id") or "").strip(),
        "dry_run": _bool_payload(payload.get("dry_run"), default=True),
    }


def _member_action_response(command: AutomationMemberActionCommand) -> JSONResponse:
    try:
        payload = execute_member_action_command(command)
    except AutomationMemberActionInputError as exc:
        return _member_action_error(str(exc) or "input_error", status_code=400)
    except Exception as exc:
        return _member_action_error(str(exc) or "automation_member_action_unavailable", status_code=503)
    return JSONResponse(payload, headers=_MEMBER_ACTION_HEADERS)


def _customer_webhook_error(error: str, *, source_status: str, status_code: int = 400) -> JSONResponse:
    payload = customer_webhook_diagnostics_payload(source_status)
    payload.update(
        {
            "ok": False,
            "error": error,
            "status": "input_error" if status_code == 400 else "error",
            "planned_count": 0,
            "processed_count": 0,
            "sent_count": 0,
            "failed_count": 0,
            "skipped_count": 0,
            "candidate_count": 0,
            "candidates": [],
            "estimated_actions": {
                "planned_action_count": 0,
                "external_call_count": 0,
                "blocked_external_call_count": 0,
                "local_projection_count": 0,
            },
        }
    )
    return JSONResponse(payload, status_code=status_code, headers=_CUSTOMER_WEBHOOK_HEADERS)


async def _customer_webhook_payload(request: Request) -> dict[str, Any]:
    if request.headers.get("content-type", "").lower().startswith("application/json"):
        try:
            payload = await request.json()
        except Exception as exc:
            raise CustomerAutomationWebhookInputError("payload must be valid JSON") from exc
    else:
        body = await request.body()
        payload = {} if not body else await request.json()
    if payload is None:
        merged: dict[str, Any] = {}
    elif isinstance(payload, dict):
        merged = dict(payload)
    else:
        raise CustomerAutomationWebhookInputError("payload must be an object")
    for key in ("mobile", "phone", "activated_at", "source", "limit", "dry_run"):
        if key not in merged and key in request.query_params:
            merged[key] = request.query_params.get(key)
    return merged


def _customer_webhook_common(request: Request, payload: dict[str, Any], source_route: str) -> dict[str, Any]:
    return {
        "idempotency_key": str(request.headers.get("Idempotency-Key") or payload.get("idempotency_key") or "").strip(),
        "actor_id": normalize_customer_webhook_actor(
            payload.get("operator_id") or payload.get("operator") or payload.get("actor_id") or request.headers.get("X-AICRM-Actor")
        ),
        "actor_type": str(payload.get("actor_type") or "system").strip(),
        "source_route": source_route,
        "trace_id": str(request.headers.get("X-AICRM-Trace-Id") or payload.get("trace_id") or "").strip(),
        "dry_run": _bool_payload(payload.get("dry_run"), default=True),
    }


def _customer_webhook_response(command, *, source_status: str) -> JSONResponse:
    try:
        payload = execute_customer_webhook_command(command)
    except CustomerAutomationWebhookInputError as exc:
        return _customer_webhook_error(str(exc) or "input_error", source_status=source_status, status_code=400)
    except Exception as exc:
        return _customer_webhook_error(str(exc) or "customer_automation_webhook_unavailable", source_status=source_status, status_code=503)
    return JSONResponse(payload, headers=_CUSTOMER_WEBHOOK_HEADERS)


@router.options("/api/customers/automation/activation-webhook")
def api_customer_automation_activation_webhook_options() -> JSONResponse:
    return JSONResponse(
        customer_webhook_diagnostics_payload("next_customer_activation_webhook"),
        headers=_CUSTOMER_WEBHOOK_HEADERS,
    )


@router.post("/api/customers/automation/activation-webhook")
async def api_customer_automation_activation_webhook(request: Request) -> JSONResponse:
    source_status = "next_customer_activation_webhook"
    try:
        payload = await _customer_webhook_payload(request)
        command = ApplyCustomerActivationWebhookCommand(
            **_customer_webhook_common(request, payload, "/api/customers/automation/activation-webhook"),
            mobile=normalize_mobile(payload.get("mobile") or payload.get("phone")),
            activated_at=str(payload.get("activated_at") or "").strip(),
            source=str(payload.get("source") or "").strip(),
            raw_payload=payload,
        )
    except CustomerAutomationWebhookInputError as exc:
        return _customer_webhook_error(str(exc) or "input_error", source_status=source_status, status_code=400)
    return _customer_webhook_response(command, source_status=source_status)


@router.options("/api/customers/automation/webhook-deliveries/{delivery_id:int}/retry")
def api_customer_automation_webhook_delivery_retry_options(delivery_id: int) -> JSONResponse:
    payload = customer_webhook_diagnostics_payload("next_customer_webhook_retry_plan")
    payload["delivery_id"] = delivery_id
    return JSONResponse(payload, headers=_CUSTOMER_WEBHOOK_HEADERS)


@router.post("/api/customers/automation/webhook-deliveries/{delivery_id:int}/retry")
async def api_plan_customer_automation_webhook_delivery_retry(delivery_id: int, request: Request) -> JSONResponse:
    source_status = "next_customer_webhook_retry_plan"
    try:
        payload = await _customer_webhook_payload(request)
        command = PlanCustomerWebhookDeliveryRetryCommand(
            **_customer_webhook_common(
                request,
                payload,
                f"/api/customers/automation/webhook-deliveries/{delivery_id}/retry",
            ),
            delivery_id=normalize_delivery_id(delivery_id),
        )
    except CustomerAutomationWebhookInputError as exc:
        return _customer_webhook_error(str(exc) or "input_error", source_status=source_status, status_code=400)
    return _customer_webhook_response(command, source_status=source_status)


@router.options("/api/customers/automation/webhook-deliveries/retry-due")
def api_customer_automation_webhook_delivery_retry_due_options() -> JSONResponse:
    return JSONResponse(
        customer_webhook_diagnostics_payload("next_customer_webhook_retry_due_plan"),
        headers=_CUSTOMER_WEBHOOK_HEADERS,
    )


@router.post("/api/customers/automation/webhook-deliveries/retry-due")
async def api_plan_customer_automation_webhook_delivery_retry_due(request: Request) -> JSONResponse:
    source_status = "next_customer_webhook_retry_due_plan"
    try:
        payload = await _customer_webhook_payload(request)
        command = PlanCustomerWebhookDeliveryRetryDueCommand(
            **_customer_webhook_common(request, payload, "/api/customers/automation/webhook-deliveries/retry-due"),
            limit=normalize_customer_webhook_limit(payload.get("limit"), default=20),
        )
    except CustomerAutomationWebhookInputError as exc:
        return _customer_webhook_error(str(exc) or "input_error", source_status=source_status, status_code=400)
    return _customer_webhook_response(command, source_status=source_status)


@router.api_route("/api/admin/automation-conversion/member", methods=["GET", "HEAD"])
def api_automation_member_detail(external_contact_id: str = "", phone: str = "") -> JSONResponse:
    try:
        payload = read_automation_member_detail(
            GetAutomationMemberSafeDetailQuery(
                external_contact_id=external_contact_id,
                phone=phone,
            )
        )
    except AutomationMemberActionInputError as exc:
        return _member_action_error(str(exc) or "input_error", source_status="next_automation_member_read", status_code=400)
    except Exception as exc:
        return _member_action_error(str(exc) or "automation_member_read_unavailable", source_status="production_unavailable", status_code=503)
    return JSONResponse(payload, headers=_MEMBER_ACTION_HEADERS)


def _member_action_options() -> JSONResponse:
    return JSONResponse(member_action_diagnostics_payload("next_command"), headers=_MEMBER_ACTION_HEADERS)


@router.options("/api/admin/automation-conversion/member/put-in-pool")
def api_automation_member_put_in_pool_options() -> JSONResponse:
    return _member_action_options()


@router.post("/api/admin/automation-conversion/member/put-in-pool")
async def api_plan_automation_member_put_in_pool(request: Request) -> JSONResponse:
    try:
        payload = await _member_action_payload(request)
        command = PutAutomationMemberInPoolCommand(**_member_action_common(request, payload, "/api/admin/automation-conversion/member/put-in-pool"))
    except AutomationMemberActionInputError as exc:
        return _member_action_error(str(exc) or "input_error")
    return _member_action_response(command)


@router.options("/api/admin/automation-conversion/member/remove-from-pool")
def api_automation_member_remove_from_pool_options() -> JSONResponse:
    return _member_action_options()


@router.post("/api/admin/automation-conversion/member/remove-from-pool")
async def api_plan_automation_member_remove_from_pool(request: Request) -> JSONResponse:
    try:
        payload = await _member_action_payload(request)
        command = RemoveAutomationMemberFromPoolCommand(**_member_action_common(request, payload, "/api/admin/automation-conversion/member/remove-from-pool"))
    except AutomationMemberActionInputError as exc:
        return _member_action_error(str(exc) or "input_error")
    return _member_action_response(command)


@router.options("/api/admin/automation-conversion/member/set-focus")
def api_automation_member_set_focus_options() -> JSONResponse:
    return _member_action_options()


@router.post("/api/admin/automation-conversion/member/set-focus")
async def api_plan_automation_member_set_focus(request: Request) -> JSONResponse:
    try:
        payload = await _member_action_payload(request)
        command = SetAutomationMemberFocusCommand(**_member_action_common(request, payload, "/api/admin/automation-conversion/member/set-focus"))
    except AutomationMemberActionInputError as exc:
        return _member_action_error(str(exc) or "input_error")
    return _member_action_response(command)


@router.options("/api/admin/automation-conversion/member/set-normal")
def api_automation_member_set_normal_options() -> JSONResponse:
    return _member_action_options()


@router.post("/api/admin/automation-conversion/member/set-normal")
async def api_plan_automation_member_set_normal(request: Request) -> JSONResponse:
    try:
        payload = await _member_action_payload(request)
        command = SetAutomationMemberNormalCommand(**_member_action_common(request, payload, "/api/admin/automation-conversion/member/set-normal"))
    except AutomationMemberActionInputError as exc:
        return _member_action_error(str(exc) or "input_error")
    return _member_action_response(command)


@router.options("/api/admin/automation-conversion/member/mark-won")
def api_automation_member_mark_won_options() -> JSONResponse:
    return _member_action_options()


@router.post("/api/admin/automation-conversion/member/mark-won")
async def api_plan_automation_member_mark_won(request: Request) -> JSONResponse:
    try:
        payload = await _member_action_payload(request)
        command = MarkAutomationMemberWonCommand(**_member_action_common(request, payload, "/api/admin/automation-conversion/member/mark-won"))
    except AutomationMemberActionInputError as exc:
        return _member_action_error(str(exc) or "input_error")
    return _member_action_response(command)


@router.options("/api/admin/automation-conversion/member/unmark-won")
def api_automation_member_unmark_won_options() -> JSONResponse:
    return _member_action_options()


@router.post("/api/admin/automation-conversion/member/unmark-won")
async def api_plan_automation_member_unmark_won(request: Request) -> JSONResponse:
    try:
        payload = await _member_action_payload(request)
        command = UnmarkAutomationMemberWonCommand(**_member_action_common(request, payload, "/api/admin/automation-conversion/member/unmark-won"))
    except AutomationMemberActionInputError as exc:
        return _member_action_error(str(exc) or "input_error")
    return _member_action_response(command)


@router.options("/api/admin/automation-conversion/member/push-openclaw")
def api_automation_member_push_openclaw_options() -> JSONResponse:
    return _member_action_options()


@router.post("/api/admin/automation-conversion/member/push-openclaw")
async def api_plan_automation_member_push_openclaw(request: Request) -> JSONResponse:
    try:
        payload = await _member_action_payload(request)
        command = PlanAutomationMemberOpenClawPushCommand(**_member_action_common(request, payload, "/api/admin/automation-conversion/member/push-openclaw"))
    except AutomationMemberActionInputError as exc:
        return _member_action_error(str(exc) or "input_error")
    return _member_action_response(command)


@router.options("/api/admin/automation-conversion/tasks/run-due")
def api_automation_workspace_tasks_run_due_options() -> JSONResponse:
    return JSONResponse(workspace_runtime_diagnostics_payload("next_automation_tasks_run_due_plan"), headers=_WORKSPACE_RUNTIME_HEADERS)


@router.post("/api/admin/automation-conversion/tasks/run-due")
async def api_plan_automation_workspace_tasks_run_due(request: Request) -> JSONResponse:
    source_status = "next_automation_tasks_run_due_plan"
    try:
        payload = await _workspace_runtime_payload(request)
        command = PlanAutomationOperationTasksRunDueCommand(
            **_workspace_runtime_common(
                request,
                payload,
                "/api/admin/automation-conversion/tasks/run-due",
            )
        )
    except AutomationWorkspaceRuntimeInputError as exc:
        return _workspace_runtime_error(str(exc) or "input_error", source_status=source_status, status_code=400)
    return _workspace_runtime_response(command, source_status=source_status)


@router.options("/api/admin/automation-conversion/execution-items/{execution_item_id}/send-via-bazhuayu")
def api_automation_workspace_execution_item_outbound_options(execution_item_id: int) -> JSONResponse:
    source_status = "next_bazhuayu_dispatch_plan"
    try:
        normalize_execution_item_id(execution_item_id)
    except AutomationWorkspaceRuntimeInputError as exc:
        return _workspace_runtime_error(str(exc) or "input_error", source_status=source_status, status_code=400)
    payload = workspace_runtime_diagnostics_payload(source_status)
    payload["execution_item_id"] = int(execution_item_id)
    return JSONResponse(payload, headers=_WORKSPACE_RUNTIME_HEADERS)


@router.post("/api/admin/automation-conversion/execution-items/{execution_item_id}/send-via-bazhuayu")
async def api_plan_automation_workspace_execution_item_outbound(execution_item_id: int, request: Request) -> JSONResponse:
    source_status = "next_bazhuayu_dispatch_plan"
    try:
        payload = await _workspace_runtime_payload(request)
        command = PlanAutomationExecutionItemOutboundDispatchCommand(
            execution_item_id=normalize_execution_item_id(execution_item_id),
            **_workspace_runtime_common(
                request,
                payload,
                "/api/admin/automation-conversion/execution-items/{execution_item_id}/send-via-bazhuayu",
            ),
        )
    except AutomationWorkspaceRuntimeInputError as exc:
        return _workspace_runtime_error(str(exc) or "input_error", source_status=source_status, status_code=400)
    return _workspace_runtime_response(command, source_status=source_status)


@router.options("/api/admin/automation-conversion/reply-monitor/capture")
def api_automation_conversion_reply_monitor_capture_options() -> JSONResponse:
    return JSONResponse(timer_diagnostics_payload("next_reply_monitor_capture_plan"), headers=_TIMER_HEADERS)


@router.post("/api/admin/automation-conversion/reply-monitor/capture")
async def api_plan_automation_conversion_reply_monitor_capture(request: Request) -> JSONResponse:
    source_status = "next_reply_monitor_capture_plan"
    try:
        payload = await _timer_payload(request)
        guard_response = maybe_guard_internal_run_due_request(
            request=request,
            payload=payload,
            source_route="/api/admin/automation-conversion/reply-monitor/capture",
            route_kind="automation_reply_monitor_capture",
        )
        if guard_response is not None:
            return guard_response
        command = PlanReplyMonitorCaptureCommand(
            **_timer_common(
                request,
                payload,
                "/api/admin/automation-conversion/reply-monitor/capture",
                default_limit=500,
            )
        )
    except AutomationTimerInputError as exc:
        return _timer_error(str(exc) or "input_error", source_status=source_status, status_code=400)
    return _timer_response(command, source_status=source_status)


@router.options("/api/admin/automation-conversion/reply-monitor/run-due")
def api_automation_conversion_reply_monitor_run_due_options() -> JSONResponse:
    return JSONResponse(timer_diagnostics_payload("next_reply_monitor_run_due_plan"), headers=_TIMER_HEADERS)


@router.post("/api/admin/automation-conversion/reply-monitor/run-due")
async def api_plan_automation_conversion_reply_monitor_run_due(request: Request) -> JSONResponse:
    source_status = "next_reply_monitor_run_due_plan"
    try:
        payload = await _timer_payload(request)
        guard_response = maybe_guard_internal_run_due_request(
            request=request,
            payload=payload,
            source_route="/api/admin/automation-conversion/reply-monitor/run-due",
            route_kind="automation_reply_monitor_run_due",
        )
        if guard_response is not None:
            return guard_response
        command = PlanReplyMonitorRunDueCommand(
            **_timer_common(
                request,
                payload,
                "/api/admin/automation-conversion/reply-monitor/run-due",
                default_limit=20,
            )
        )
    except AutomationTimerInputError as exc:
        return _timer_error(str(exc) or "input_error", source_status=source_status, status_code=400)
    return _timer_response(command, source_status=source_status)


@router.options("/api/admin/automation-conversion/jobs/run-due/preview")
def api_automation_conversion_jobs_run_due_preview_options() -> JSONResponse:
    return JSONResponse(timer_diagnostics_payload("next_jobs_run_due_preview"), headers=_TIMER_HEADERS)


@router.post("/api/admin/automation-conversion/jobs/run-due/preview")
async def api_preview_automation_conversion_jobs_run_due(request: Request) -> JSONResponse:
    source_status = "next_jobs_run_due_preview"
    try:
        payload = await _timer_payload(request)
        guard_response = maybe_guard_internal_run_due_request(
            request=request,
            payload=payload,
            source_route="/api/admin/automation-conversion/jobs/run-due/preview",
            route_kind="automation_jobs_run_due_preview",
        )
        if guard_response is not None:
            return guard_response
        command = PreviewAutomationJobsRunDueCommand(
            **_timer_common(
                request,
                payload,
                "/api/admin/automation-conversion/jobs/run-due/preview",
                default_limit=100,
            )
        )
    except AutomationTimerInputError as exc:
        return _timer_error(str(exc) or "input_error", source_status=source_status, status_code=400)
    return _timer_response(command, source_status=source_status)


@router.options("/api/admin/automation-conversion/jobs/run-due")
def api_automation_conversion_jobs_run_due_options() -> JSONResponse:
    return JSONResponse(timer_diagnostics_payload("next_jobs_run_due_plan"), headers=_TIMER_HEADERS)


@router.post("/api/admin/automation-conversion/jobs/run-due")
async def api_plan_automation_conversion_jobs_run_due(request: Request) -> JSONResponse:
    source_status = "next_jobs_run_due_plan"
    try:
        payload = await _timer_payload(request)
        guard_response = maybe_guard_internal_run_due_request(
            request=request,
            payload=payload,
            source_route="/api/admin/automation-conversion/jobs/run-due",
            route_kind="automation_jobs_run_due",
        )
        if guard_response is not None:
            return guard_response
        command_cls = PreviewAutomationJobsRunDueCommand if bool(payload.get("preview")) else PlanAutomationJobsRunDueCommand
        source_status = "next_jobs_run_due_preview" if bool(payload.get("preview")) else source_status
        command = command_cls(
            **_timer_common(
                request,
                payload,
                "/api/admin/automation-conversion/jobs/run-due",
                default_limit=100,
            )
        )
    except AutomationTimerInputError as exc:
        return _timer_error(str(exc) or "input_error", source_status=source_status, status_code=400)
    return _timer_response(command, source_status=source_status)


@router.get("/api/admin/automation-conversion/contract")
def automation_contract() -> dict:
    return GetAutomationRuntimeContractQuery()()


@router.get("/api/admin/automation-conversion/overview")
def automation_overview() -> JSONResponse:
    try:
        return JSONResponse(AutomationOverviewReadModel().execute(), headers=_AUTOMATION_READ_MODEL_HEADERS)
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/automation-conversion/pools")
def automation_pools() -> JSONResponse:
    try:
        return JSONResponse(AutomationPoolReadModel().execute(), headers=_AUTOMATION_READ_MODEL_HEADERS)
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/automation-conversion/programs")
def automation_programs() -> JSONResponse:
    try:
        return JSONResponse(list_automation_programs_payload(), headers=_AUTOMATION_PROGRAM_HEADERS)
    except AutomationProgramDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/api/admin/automation-conversion/programs/{program_id}/overview")
def automation_program_data_overview(program_id: int) -> JSONResponse:
    try:
        return JSONResponse(get_automation_program_overview_payload(int(program_id)), headers=_AUTOMATION_PROGRAM_HEADERS)
    except AutomationProgramDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/api/admin/automation-conversion/programs/{program_id}/members")
def automation_program_members(
    program_id: int,
    stage: str = "all",
    page: int = 1,
    page_size: int = 50,
    keyword: str | None = None,
) -> JSONResponse:
    try:
        payload = get_automation_program_members_payload(
            int(program_id),
            stage_key=stage,
            page=page,
            page_size=page_size,
            keyword=keyword,
        )
        return JSONResponse(payload, headers=_AUTOMATION_PROGRAM_HEADERS)
    except AutomationProgramDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post(
    "/api/admin/automation-conversion/programs/{program_id}/setup/segmentation",
    name="api_admin_automation_program_setup_segmentation",
)
def save_automation_program_setup_segmentation(program_id: int, payload: dict) -> dict:
    try:
        result = save_automation_program_segmentation(int(program_id), payload, operator_id="admin")
    except AutomationProgramDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "source_status": "ai_crm_next", "route_owner": "ai_crm_next", **result}


@router.post(
    "/api/admin/automation-conversion/programs/{program_id}/setup/audience-entry-rule",
    name="api_admin_automation_program_setup_audience_entry_rule",
)
def save_automation_program_setup_audience_entry_rule(program_id: int, payload: dict) -> dict:
    try:
        result = save_automation_program_audience_entry_rule(int(program_id), payload, operator_id="admin")
    except AutomationProgramDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "source_status": "ai_crm_next", "route_owner": "ai_crm_next", **result}


@router.post(
    "/api/admin/automation-conversion/programs/{program_id}/publish-entry",
    name="api_admin_automation_program_publish_entry",
)
def publish_automation_program_entry_api(program_id: int) -> dict:
    try:
        result = publish_automation_program_entry(int(program_id), operator_id="admin")
    except AutomationProgramDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "source_status": "ai_crm_next", "route_owner": "ai_crm_next", **result}


@router.post(
    "/api/admin/automation-conversion/programs/{program_id}/publish-full",
    name="api_admin_automation_program_publish_full",
)
def publish_automation_program_full_api(program_id: int) -> dict:
    try:
        result = publish_automation_program_full(int(program_id), operator_id="admin")
    except AutomationProgramDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "source_status": "ai_crm_next", "route_owner": "ai_crm_next", **result}


@router.get(
    "/api/admin/automation-conversion/programs/{program_id}/setup/operation-tasks",
    name="api_admin_automation_program_setup_operation_tasks",
)
def list_automation_program_setup_operation_tasks(program_id: int) -> dict:
    try:
        return list_automation_program_operation_tasks(int(program_id))
    except AutomationProgramDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post(
    "/api/admin/automation-conversion/programs/{program_id}/setup/operation-task-groups",
    name="api_admin_automation_program_setup_operation_task_groups_create",
)
def create_automation_program_setup_operation_task_group(program_id: int, payload: dict) -> dict:
    try:
        return create_automation_program_operation_task_group(int(program_id), payload, operator_id="admin")
    except AutomationProgramDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete(
    "/api/admin/automation-conversion/programs/{program_id}/setup/operation-task-groups/{group_id}",
    name="api_admin_automation_program_setup_operation_task_groups_delete",
)
def delete_automation_program_setup_operation_task_group(program_id: int, group_id: int) -> dict:
    try:
        return delete_automation_program_operation_task_group(int(program_id), int(group_id), operator_id="admin")
    except AutomationProgramDataUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/api/admin/automation-conversion/programs/{program_id}/setup/operation-tasks",
    name="api_admin_automation_program_setup_operation_tasks_create",
)
def create_automation_program_setup_operation_task(program_id: int, payload: dict) -> dict:
    try:
        return create_automation_program_operation_task(int(program_id), payload, operator_id="admin")
    except AutomationProgramDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/api/admin/automation-conversion/programs/{program_id}/setup/operation-tasks/{task_id}",
    name="api_admin_automation_program_setup_operation_tasks_get",
)
def get_automation_program_setup_operation_task(program_id: int, task_id: int) -> dict:
    try:
        result = list_automation_program_operation_tasks(int(program_id))
    except AutomationProgramDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    task = next((item for item in list(result.get("tasks") or result.get("items") or []) if int(item.get("id") or 0) == int(task_id)), None)
    if not task:
        raise HTTPException(status_code=404, detail=f"operation task {task_id} not found")
    return {"ok": True, "route_owner": "ai_crm_next", "source_status": result.get("source_status") or "ai_crm_next", "task": task}


@router.put(
    "/api/admin/automation-conversion/programs/{program_id}/setup/operation-tasks/{task_id}",
    name="api_admin_automation_program_setup_operation_tasks_update",
)
def update_automation_program_setup_operation_task(program_id: int, task_id: int, payload: dict) -> dict:
    try:
        return update_automation_program_operation_task(int(program_id), int(task_id), payload, operator_id="admin")
    except AutomationProgramDataUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/api/admin/automation-conversion/programs/{program_id}/setup/operation-tasks/{task_id}/copy",
    name="api_admin_automation_program_setup_operation_tasks_copy",
)
def copy_automation_program_setup_operation_task(program_id: int, task_id: int) -> dict:
    try:
        return copy_automation_program_operation_task(int(program_id), int(task_id), operator_id="admin")
    except AutomationProgramDataUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/api/admin/automation-conversion/programs/{program_id}/setup/operation-tasks/{task_id}/activate",
    name="api_admin_automation_program_setup_operation_tasks_activate",
)
def activate_automation_program_setup_operation_task(program_id: int, task_id: int) -> dict:
    try:
        return set_automation_program_operation_task_status(int(program_id), int(task_id), "active", operator_id="admin")
    except AutomationProgramDataUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/api/admin/automation-conversion/programs/{program_id}/setup/operation-tasks/{task_id}/pause",
    name="api_admin_automation_program_setup_operation_tasks_pause",
)
def pause_automation_program_setup_operation_task(program_id: int, task_id: int) -> dict:
    try:
        return set_automation_program_operation_task_status(int(program_id), int(task_id), "paused", operator_id="admin")
    except AutomationProgramDataUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete(
    "/api/admin/automation-conversion/programs/{program_id}/setup/operation-tasks/{task_id}",
    name="api_admin_automation_program_setup_operation_tasks_archive",
)
def archive_automation_program_setup_operation_task(program_id: int, task_id: int) -> dict:
    try:
        return set_automation_program_operation_task_status(int(program_id), int(task_id), "archived", operator_id="admin")
    except AutomationProgramDataUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/api/admin/automation-conversion/programs/{program_id}/setup/operation-tasks/{task_id}/preview-audience",
    name="api_admin_automation_program_setup_operation_tasks_preview_audience",
)
def preview_automation_program_setup_operation_task_audience(program_id: int, task_id: int, payload: dict) -> dict:
    del task_id
    try:
        return preview_automation_program_operation_task_audience(int(program_id), payload)
    except AutomationProgramDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.put(
    "/api/admin/automation-conversion/programs/{program_id}/setup/operation-tasks/{task_id}/send-strategy",
    name="api_admin_automation_program_setup_operation_tasks_send_strategy",
)
def update_automation_program_setup_operation_task_send_strategy(program_id: int, task_id: int, payload: dict) -> dict:
    try:
        return update_automation_program_operation_task_send_strategy(int(program_id), int(task_id), payload, operator_id="admin")
    except AutomationProgramDataUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put(
    "/api/admin/automation-conversion/programs/{program_id}/setup/operation-tasks/{task_id}/send-content/unified",
    name="api_admin_automation_program_setup_operation_tasks_send_content_unified",
)
def save_automation_program_setup_operation_task_unified_content(program_id: int, task_id: int, payload: dict) -> dict:
    try:
        return save_automation_program_operation_task_content(
            int(program_id), int(task_id), payload, content_kind="unified", operator_id="admin"
        )
    except AutomationProgramDataUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put(
    "/api/admin/automation-conversion/programs/{program_id}/setup/operation-tasks/{task_id}/send-content/profile-segments/{segment_key}",
    name="api_admin_automation_program_setup_operation_tasks_send_content_profile",
)
def save_automation_program_setup_operation_task_profile_content(program_id: int, task_id: int, segment_key: str, payload: dict) -> dict:
    try:
        return save_automation_program_operation_task_content(
            int(program_id), int(task_id), payload, content_kind="profile", segment_key=segment_key, operator_id="admin"
        )
    except AutomationProgramDataUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put(
    "/api/admin/automation-conversion/programs/{program_id}/setup/operation-tasks/{task_id}/send-content/behavior-segments/{segment_key}",
    name="api_admin_automation_program_setup_operation_tasks_send_content_behavior",
)
def save_automation_program_setup_operation_task_behavior_content(program_id: int, task_id: int, segment_key: str, payload: dict) -> dict:
    try:
        return save_automation_program_operation_task_content(
            int(program_id), int(task_id), payload, content_kind="behavior", segment_key=segment_key, operator_id="admin"
        )
    except AutomationProgramDataUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put(
    "/api/admin/automation-conversion/programs/{program_id}/setup/operation-tasks/{task_id}/send-content/agent-materials",
    name="api_admin_automation_program_setup_operation_tasks_send_content_agent",
)
def save_automation_program_setup_operation_task_agent_content(program_id: int, task_id: int, payload: dict) -> dict:
    try:
        return save_automation_program_operation_task_content(
            int(program_id), int(task_id), payload, content_kind="agent", operator_id="admin"
        )
    except AutomationProgramDataUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/admin/automation-conversion/action-templates")
def list_action_templates(
    template_source: str = "",
    category: str = "",
    keyword: str = "",
    include_archived: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> JSONResponse:
    request = ActionTemplateListRequest(
        template_source=template_source,
        category=category,
        keyword=keyword,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    return _json_result(ListActionTemplatesQuery()(request))


@router.post("/api/admin/automation-conversion/action-templates")
def create_action_template(payload: ActionTemplateCreateRequest) -> JSONResponse:
    try:
        return _json_result(CreateActionTemplateCommand()(payload))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/automation-conversion/task-groups")
def list_task_groups(
    program_id: int | None = None,
    include_archived: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> JSONResponse:
    request = TaskGroupListRequest(
        program_id=program_id,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    return _json_result(ListTaskGroupsQuery()(request))


@router.post("/api/admin/automation-conversion/task-groups")
def create_task_group(payload: TaskGroupCreateRequest) -> JSONResponse:
    try:
        return _json_result(CreateTaskGroupCommand()(payload))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/automation-conversion/workflows")
def list_workflows(
    program_id: int | None = None,
    status: str = "",
    include_archived: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> JSONResponse:
    request = WorkflowListRequest(
        program_id=program_id,
        status=status,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    return _json_result(ListWorkflowsQuery()(request))


@router.post("/api/admin/automation-conversion/workflows")
def create_workflow(payload: WorkflowCreateRequest) -> JSONResponse:
    try:
        return _json_result(CreateWorkflowCommand()(payload))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/automation-conversion/workflow-nodes")
def list_workflow_nodes(
    program_id: int | None = None,
    workflow_id: int | None = None,
    node_type: str = "",
    status: str = "",
    include_archived: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> JSONResponse:
    request = WorkflowNodeListRequest(
        program_id=program_id,
        workflow_id=workflow_id,
        node_type=node_type,
        status=status,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    return _json_result(ListWorkflowNodesQuery()(request))


@router.post("/api/admin/automation-conversion/workflow-nodes")
def create_workflow_node(payload: WorkflowNodeCreateRequest) -> JSONResponse:
    try:
        return _json_result(CreateWorkflowNodeCommand()(payload))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/automation-conversion/workflows/{workflow_id}/nodes")
def list_workflow_nodes_for_workflow(
    workflow_id: int,
    program_id: int | None = None,
    node_type: str = "",
    status: str = "",
    include_archived: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> JSONResponse:
    request = WorkflowNodeListRequest(
        program_id=program_id,
        workflow_id=workflow_id,
        node_type=node_type,
        status=status,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    return _json_result(ListWorkflowNodesQuery()(request))


@router.post("/api/admin/automation-conversion/workflows/{workflow_id}/nodes")
def create_workflow_node_for_workflow(workflow_id: int, payload: WorkflowNodeCreateRequest) -> JSONResponse:
    try:
        request = payload.model_copy(update={"workflow_id": workflow_id})
        return _json_result(CreateWorkflowNodeCommand()(request))
    except Exception as exc:
        _raise_http(exc)


@router.put("/api/admin/automation-conversion/workflow-nodes/{node_id}")
def update_workflow_node(node_id: int, payload: WorkflowNodeUpdateRequest) -> JSONResponse:
    try:
        return _json_result(UpdateWorkflowNodeCommand()(node_id, payload))
    except Exception as exc:
        _raise_http(exc)


@router.delete("/api/admin/automation-conversion/workflow-nodes/{node_id}")
def delete_workflow_node(node_id: int, operator: str = "system") -> JSONResponse:
    try:
        return _json_result(DeleteWorkflowNodeCommand()(node_id, operator=operator))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/automation-conversion/tasks")
def list_tasks(
    program_id: int | None = None,
    workflow_id: int | None = None,
    node_id: int | None = None,
    group_id: int | None = None,
    task_type: str = "",
    status: str = "",
    include_archived: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> JSONResponse:
    request = TaskListRequest(
        program_id=program_id,
        workflow_id=workflow_id,
        node_id=node_id,
        group_id=group_id,
        task_type=task_type,
        status=status,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    return _json_result(ListTasksQuery()(request))


@router.post("/api/admin/automation-conversion/tasks")
def create_task(payload: TaskCreateRequest) -> JSONResponse:
    try:
        return _json_result(CreateTaskCommand()(payload))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/automation-conversion/tasks/{task_id}")
def get_task_detail(task_id: int) -> JSONResponse:
    try:
        return _json_result(GetTaskDetailQuery()(task_id))
    except Exception as exc:
        _raise_http(exc)


@router.put("/api/admin/automation-conversion/tasks/{task_id}")
def update_task(task_id: int, payload: TaskUpdateRequest) -> JSONResponse:
    try:
        return _json_result(UpdateTaskCommand()(task_id, payload))
    except Exception as exc:
        _raise_http(exc)


@router.put("/api/admin/automation-conversion/tasks/{task_id}/send-strategy")
def update_task_send_strategy(task_id: int, payload: SendStrategyUpdateRequest) -> JSONResponse:
    try:
        return _json_result(UpdateTaskSendStrategyCommand()(task_id, payload))
    except Exception as exc:
        _raise_http(exc)


@router.put("/api/admin/automation-conversion/tasks/{task_id}/send-content/unified")
def save_unified_send_content(task_id: int, payload: UnifiedSendContentUpdateRequest) -> JSONResponse:
    try:
        return _json_result(SaveUnifiedSendContentCommand()(task_id, payload))
    except Exception as exc:
        _raise_http(exc)


@router.put("/api/admin/automation-conversion/tasks/{task_id}/send-content/profile-segments/{segment_key}")
def save_profile_segment_send_content(task_id: int, segment_key: str, payload: ProfileSegmentSendContentUpdateRequest) -> JSONResponse:
    try:
        return _json_result(SaveProfileSegmentSendContentCommand()(task_id, segment_key, payload))
    except Exception as exc:
        _raise_http(exc)


@router.put("/api/admin/automation-conversion/tasks/{task_id}/send-content/behavior-segments/{segment_key}")
def save_behavior_segment_send_content(task_id: int, segment_key: str, payload: BehaviorSegmentSendContentUpdateRequest) -> JSONResponse:
    try:
        return _json_result(SaveBehaviorSegmentSendContentCommand()(task_id, segment_key, payload))
    except Exception as exc:
        _raise_http(exc)


@router.put("/api/admin/automation-conversion/tasks/{task_id}/send-content/agent-materials")
def save_agent_materials(task_id: int, payload: AgentMaterialsUpdateRequest) -> JSONResponse:
    try:
        return _json_result(SaveAgentMaterialsCommand()(task_id, payload))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/automation-conversion/behavior-segment-rules")
def behavior_segment_rules() -> JSONResponse:
    return _json_result(GetBehaviorSegmentRulesQuery()())


@router.get("/api/admin/automation-conversion/agents")
def list_agents(
    program_id: int | None = None,
    workflow_id: int | None = None,
    node_id: int | None = None,
    task_id: int | None = None,
    agent_type: str = "",
    status: str = "",
    include_archived: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> JSONResponse:
    request = AgentListRequest(
        program_id=program_id,
        workflow_id=workflow_id,
        node_id=node_id,
        task_id=task_id,
        agent_type=agent_type,
        status=status,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    return _json_result(ListAgentsQuery()(request))


@router.get("/api/admin/automation-conversion/agents/options")
def agent_options(
    program_id: int | None = None,
    workflow_id: int | None = None,
    node_id: int | None = None,
    task_id: int | None = None,
    agent_type: str = "",
    status: str = "",
    include_archived: bool = False,
    limit: int = 200,
    offset: int = 0,
) -> JSONResponse:
    request = AgentListRequest(
        program_id=program_id,
        workflow_id=workflow_id,
        node_id=node_id,
        task_id=task_id,
        agent_type=agent_type,
        status=status,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    return _json_result(ListAgentsQuery()(request))


@router.post("/api/admin/automation-conversion/agents")
def create_agent(payload: AgentCreateRequest) -> JSONResponse:
    try:
        return _json_result(CreateAgentCommand()(payload))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/automation-conversion/agent-outputs")
def list_agent_outputs(
    page: int = 1,
    page_size: int = 50,
    request_id: str = "",
    external_contact_id: str = "",
    userid: str = "",
    agent_code: str = "",
    output_type: str = "",
    applied_status: str = "",
    min_confidence: float | None = None,
    max_confidence: float | None = None,
    has_error: bool | None = None,
    visibility: str = "masked",
) -> JSONResponse:
    request = AgentOutputListRequest(
        page=page,
        page_size=page_size,
        request_id=request_id,
        external_contact_id=external_contact_id,
        userid=userid,
        agent_code=agent_code,
        output_type=output_type,
        applied_status=applied_status,
        min_confidence=min_confidence,
        max_confidence=max_confidence,
        has_error=has_error,
        visibility=visibility,
    )
    try:
        return _json_result(ListAgentOutputsQuery()(request))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/automation-conversion/agent-outputs/{output_id}")
def get_agent_output_detail(output_id: str, visibility: str = "masked") -> JSONResponse:
    request = AgentOutputDetailRequest(output_id=output_id, visibility=visibility)
    try:
        return _json_result(GetAgentOutputDetailQuery()(request))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/automation-conversion/agent-runs")
def list_agent_runs(
    page: int = 1,
    page_size: int = 50,
    request_id: str = "",
    run_id: str = "",
    agent_code: str = "",
    run_status: str = "",
    trigger_source: str = "",
    external_contact_id: str = "",
    userid: str = "",
    task_id: int | None = None,
    workflow_id: int | None = None,
    started_after: str = "",
    started_before: str = "",
    has_error: bool | None = None,
    visibility: str = "masked",
) -> JSONResponse:
    request = AgentRunListRequest(
        page=page,
        page_size=page_size,
        request_id=request_id,
        run_id=run_id,
        agent_code=agent_code,
        run_status=run_status,
        trigger_source=trigger_source,
        external_contact_id=external_contact_id,
        userid=userid,
        task_id=task_id,
        workflow_id=workflow_id,
        started_after=started_after,
        started_before=started_before,
        has_error=has_error,
        visibility=visibility,
    )
    try:
        return _json_result(ListAgentRunsQuery()(request))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/automation-conversion/agent-runs/{run_id}")
def get_agent_run_detail(run_id: str, visibility: str = "masked") -> JSONResponse:
    request = AgentRunDetailRequest(run_id=run_id, visibility=visibility)
    try:
        return _json_result(GetAgentRunDetailQuery()(request))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/automation-conversion/profile-segment-templates/catalog")
def profile_segment_template_catalog() -> JSONResponse:
    return _json_result(GetProfileSegmentTemplateCatalogQuery()())


@router.get("/api/admin/automation-conversion/profile-segment-templates")
def list_profile_segment_templates(
    enabled_only: bool = False,
    program_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> JSONResponse:
    request = ProfileSegmentTemplateListRequest(
        enabled_only=enabled_only,
        program_id=program_id,
        limit=limit,
        offset=offset,
    )
    return _json_result(ListProfileSegmentTemplatesQuery()(request))


@router.get("/api/admin/automation-conversion/profile-segment-templates/options")
def profile_segment_template_options(
    enabled_only: bool = True,
    program_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> JSONResponse:
    request = ProfileSegmentTemplateListRequest(
        enabled_only=enabled_only,
        program_id=program_id,
        limit=limit,
        offset=offset,
    )
    return _json_result(GetProfileSegmentTemplateOptionsQuery()(request))


@router.get("/api/admin/automation-conversion/profile-segment-templates/{template_id}")
def get_profile_segment_template(template_id: int) -> JSONResponse:
    try:
        return _json_result(GetProfileSegmentTemplateQuery()(template_id))
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/admin/automation-conversion/profile-segment-templates")
def create_profile_segment_template(payload: ProfileSegmentTemplateCreateRequest) -> JSONResponse:
    try:
        return _json_result(CreateProfileSegmentTemplateCommand()(payload))
    except Exception as exc:
        _raise_http(exc)


@router.put("/api/admin/automation-conversion/profile-segment-templates/{template_id}")
def update_profile_segment_template(template_id: int, payload: ProfileSegmentTemplateUpdateRequest) -> JSONResponse:
    try:
        return _json_result(UpdateProfileSegmentTemplateCommand()(template_id, payload))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/automation-conversion/members")
def automation_members(
    current_pool: str = "",
    followup_type: str = "",
    owner_userid: str = "",
    keyword: str = "",
    limit: int = 50,
    offset: int = 0,
) -> dict:
    return ListAutomationMembersQuery()(
        current_pool=current_pool,
        followup_type=followup_type,
        owner_userid=owner_userid,
        keyword=keyword,
        limit=limit,
        offset=offset,
    )


@router.get("/api/admin/automation-conversion/members/{member_id}")
def automation_member_detail(member_id: str) -> dict:
    try:
        return GetAutomationMemberDetailQuery()(member_id)
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/admin/automation-conversion/members/{member_id}/override-followup-type")
def automation_override_followup_type(member_id: str, payload: OverrideFollowupTypeRequest) -> dict:
    try:
        return OverrideFollowupTypeCommand()(member_id, payload)
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/admin/automation-conversion/members/{member_id}/confirm-conversion")
def automation_confirm_conversion(member_id: str, payload: AutomationActionRequest | None = None) -> dict:
    try:
        return ConfirmConversionCommand()(member_id, payload or AutomationActionRequest())
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/admin/automation-conversion/members/{member_id}/enter-silent")
def automation_enter_silent(member_id: str, payload: AutomationActionRequest | None = None) -> dict:
    try:
        return EnterSilentPoolCommand()(member_id, payload or AutomationActionRequest())
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/admin/automation-conversion/members/{member_id}/exit-marketing")
def automation_exit_marketing(member_id: str, payload: AutomationActionRequest | None = None) -> dict:
    try:
        return ExitMarketingCommand()(member_id, payload or AutomationActionRequest())
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/admin/automation-conversion/members/{member_id}/push-openclaw-context")
def automation_push_openclaw_context(member_id: str, payload: PushOpenClawContextRequest | None = None) -> dict:
    try:
        return PushMemberContextToOpenClawCommand()(member_id, payload or PushOpenClawContextRequest())
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/automation-conversion/execution-records")
def automation_execution_records(limit: int = 50, offset: int = 0) -> dict:
    return ListAutomationExecutionRecordsQuery()(limit=limit, offset=offset)


@router.post("/api/customer-automation/activation-webhook")
def activation_webhook(payload: ActivationWebhookRequest) -> dict:
    try:
        return ApplyActivationWebhookCommand()(payload)
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/customers/automation/signup-conversion/batches")
def signup_conversion_batches(limit: int = 20, cursor: str = "") -> JSONResponse:
    try:
        payload = SignupConversionReadModel().list_batches(limit=limit, cursor=cursor)
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc), "route_owner": "ai_crm_next"}, status_code=400)
    except Exception as exc:
        return JSONResponse(
            {
                "ok": False,
                "degraded": True,
                "source_status": "production_unavailable",
                "error_code": "signup_conversion_batches_unavailable",
                "page_error": str(exc),
                "route_owner": "ai_crm_next",
            },
            status_code=503,
        )
    return JSONResponse({"ok": True, "automation_batches": payload, "route_owner": "ai_crm_next"})


@router.get("/api/customers/automation/signup-conversion/batches/{batch_id}")
def signup_conversion_batch(batch_id: int) -> JSONResponse:
    try:
        payload = SignupConversionReadModel().batch_detail(batch_id)
    except Exception as exc:
        return JSONResponse(
            {
                "ok": False,
                "degraded": True,
                "source_status": "production_unavailable",
                "error_code": "signup_conversion_batch_unavailable",
                "page_error": str(exc),
                "route_owner": "ai_crm_next",
            },
            status_code=503,
        )
    if not payload:
        return JSONResponse({"ok": False, "error": "batch not found", "route_owner": "ai_crm_next"}, status_code=404)
    return JSONResponse({"ok": True, "automation_batch": payload, "route_owner": "ai_crm_next"})


@router.get("/api/customers/automation/webhook-deliveries")
def customer_automation_webhook_deliveries(
    event_type: str = "",
    status: str = "",
    limit: int = 50,
) -> JSONResponse:
    try:
        payload = SignupConversionReadModel().list_webhook_deliveries(event_type=event_type, status=status, limit=limit)
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc), "route_owner": "ai_crm_next"}, status_code=400)
    except Exception as exc:
        return JSONResponse(
            {
                "ok": False,
                "degraded": True,
                "source_status": "production_unavailable",
                "error_code": "webhook_deliveries_unavailable",
                "page_error": str(exc),
                "route_owner": "ai_crm_next",
            },
            status_code=503,
        )
    return JSONResponse({"ok": True, "deliveries": payload, "route_owner": "ai_crm_next"})
