from __future__ import annotations

from copy import deepcopy
from typing import Any

from aicrm_next.customer_read_model.application import GetCustomerChatContextQuery
from aicrm_next.customer_read_model.dto import CustomerChatContextRequest
from aicrm_next.identity_contact.application import ResolvePersonIdentityQuery
from aicrm_next.identity_contact.dto import ResolvePersonIdentityRequest
from aicrm_next.integration_gateway.automation_adapters import (
    build_automation_activation_gateway,
    build_automation_agent_runtime_adapter,
    build_automation_workflow_runtime_adapter,
    build_automation_write_gateway,
    build_openclaw_webhook_adapter,
)
from aicrm_next.integration_gateway.mcp_openclaw_adapters import build_openclaw_legacy_bridge_adapter
from aicrm_next.shared.errors import ContractError, NotFoundError
from aicrm_next.shared.repository_provider import RepositoryProviderError, blocked_production_payload
from aicrm_next.shared.runtime import production_data_ready, production_environment
from aicrm_next.send_content.application import NormalizeSendContentPackageCommand

from .action_templates import action_template_side_effect_safety
from .agent_outputs import agent_output_run_projection, agent_output_side_effect_safety
from .agent_runs import agent_run_side_effect_safety
from .action_template_repository import (
    ActionTemplateIdempotencyConflict,
    build_action_template_repository,
    action_template_sqlalchemy_enabled,
)
from .agents import agent_side_effect_safety
from .domain import execution_record_projection, overview_cards, pool_summary
from .dto import (
    ActivationWebhookRequest,
    ApplyActivationFactRequest,
    ApplyQuestionnaireResultRequest,
    ApplyTrialOpenedFactRequest,
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
    OverrideFollowupTypeRequest,
    ProfileSegmentTemplateCreateRequest,
    ProfileSegmentTemplateListRequest,
    ProfileSegmentTemplateUpdateRequest,
    PushOpenClawContextRequest,
    BehaviorSegmentSendContentUpdateRequest,
    ProfileSegmentSendContentUpdateRequest,
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
from .profile_segments import profile_segment_side_effect_safety
from .profile_segment_repository import (
    ProfileSegmentTemplateIdempotencyConflict,
    build_profile_segment_template_repository,
    profile_segment_template_sqlalchemy_enabled,
)
from .repo import AutomationRepository, agent_postgres_enabled, build_automation_repository, task_postgres_enabled
from .state_machine import apply_transition, normalize_followup_type
from .task_groups import task_group_side_effect_safety
from .tasks import task_side_effect_safety
from .workflow_nodes import workflow_node_side_effect_safety
from .workflows import workflow_side_effect_safety
from .workflow import default_workflow_registry


def _filters_snapshot(**filters: Any) -> dict[str, str]:
    return {key: str(value or "") for key, value in filters.items()}


def _automation_side_effect_safety(**overrides: bool) -> dict[str, bool]:
    safety = {
        "real_automation_write_executed": False,
        "real_activation_webhook_executed": False,
        "real_external_call_executed": False,
        "real_wecom_call_executed": False,
        "real_openclaw_call_executed": False,
        "real_mcp_call_executed": False,
        "real_timer_executed": False,
        "real_outbound_send_executed": False,
        "real_customer_pool_state_changed": False,
        "real_openclaw_push_executed": False,
        "real_workflow_runtime_executed": False,
        "real_agent_runtime_executed": False,
        "real_external_webhook_executed": False,
    }
    safety.update({key: bool(value) for key, value in overrides.items() if key in safety})
    return safety


def _profile_segment_production_unavailable_payload(detail: str | None = None) -> dict[str, Any]:
    payload = blocked_production_payload(
        capability_owner="aicrm_next.automation_engine",
        detail=detail
        or "profile segment template production repository is not enabled; legacy production_compat fallback remains the production owner.",
    )
    payload.update(
        {
            "status_code": 503,
            "error_code": "production_repository_not_enabled",
            "route_owner": "ai_crm_next",
            "side_effect_safety": profile_segment_side_effect_safety(),
        }
    )
    return payload


def _action_template_production_unavailable_payload(detail: str | None = None) -> dict[str, Any]:
    payload = blocked_production_payload(
        capability_owner="aicrm_next.automation_engine",
        detail=detail
        or "action template production repository is not enabled; legacy production_compat fallback remains the production owner.",
    )
    payload.update(
        {
            "status_code": 503,
            "error_code": "production_repository_not_enabled",
            "route_owner": "ai_crm_next",
            "side_effect_safety": action_template_side_effect_safety(),
        }
    )
    return payload


def _task_group_production_unavailable_payload(detail: str | None = None) -> dict[str, Any]:
    payload = blocked_production_payload(
        capability_owner="aicrm_next.automation_engine",
        detail=detail
        or "task group production repository is not enabled; legacy production_compat fallback remains the production owner.",
    )
    payload.update(
        {
            "status_code": 503,
            "error_code": "production_repository_not_enabled",
            "route_owner": "ai_crm_next",
            "side_effect_safety": task_group_side_effect_safety(),
        }
    )
    return payload


def _workflow_production_unavailable_payload(detail: str | None = None) -> dict[str, Any]:
    payload = blocked_production_payload(
        capability_owner="aicrm_next.automation_engine",
        detail=detail
        or "workflow production repository is not enabled; legacy production_compat fallback remains the production owner.",
    )
    payload.update(
        {
            "status_code": 503,
            "error_code": "production_repository_not_enabled",
            "route_owner": "ai_crm_next",
            "side_effect_safety": workflow_side_effect_safety(),
        }
    )
    return payload


def _workflow_node_production_unavailable_payload(detail: str | None = None) -> dict[str, Any]:
    payload = blocked_production_payload(
        capability_owner="aicrm_next.automation_engine",
        detail=detail
        or "workflow node production repository is not enabled; legacy production_compat fallback remains the production owner.",
    )
    payload.update(
        {
            "status_code": 503,
            "error_code": "production_repository_not_enabled",
            "route_owner": "ai_crm_next",
            "side_effect_safety": workflow_node_side_effect_safety(),
        }
    )
    return payload


def _task_production_unavailable_payload(detail: str | None = None) -> dict[str, Any]:
    payload = blocked_production_payload(
        capability_owner="aicrm_next.automation_engine",
        detail=detail
        or "task production repository is not enabled; legacy production_compat fallback remains the production owner.",
    )
    payload.update(
        {
            "status_code": 503,
            "error_code": "production_repository_not_enabled",
            "route_owner": "ai_crm_next",
            "side_effect_safety": task_side_effect_safety(),
        }
    )
    return payload


def _agent_production_unavailable_payload(detail: str | None = None) -> dict[str, Any]:
    payload = blocked_production_payload(
        capability_owner="aicrm_next.automation_engine",
        detail=detail
        or "agent production repository is not enabled; legacy production_compat fallback remains the production owner.",
    )
    payload.update(
        {
            "status_code": 503,
            "error_code": "production_repository_not_enabled",
            "route_owner": "ai_crm_next",
            "side_effect_safety": agent_side_effect_safety(),
        }
    )
    return payload


def _agent_output_production_unavailable_payload(detail: str | None = None) -> dict[str, Any]:
    payload = blocked_production_payload(
        capability_owner="aicrm_next.automation_engine",
        detail=detail
        or "agent output production repository is not enabled; legacy production_compat fallback remains the production owner.",
    )
    payload.update(
        {
            "status_code": 503,
            "error_code": "production_repository_not_enabled",
            "route_owner": "ai_crm_next",
            "side_effect_safety": agent_output_side_effect_safety(),
        }
    )
    return payload


def _agent_run_production_unavailable_payload(detail: str | None = None) -> dict[str, Any]:
    payload = blocked_production_payload(
        capability_owner="aicrm_next.automation_engine",
        detail=detail
        or "agent run production repository is not enabled; legacy production_compat fallback remains the production owner.",
    )
    payload.update(
        {
            "status_code": 503,
            "error_code": "production_repository_not_enabled",
            "route_owner": "ai_crm_next",
            "side_effect_safety": agent_run_side_effect_safety(),
        }
    )
    return payload


def _profile_segment_response(payload: dict[str, Any], *, status_code: int = 200) -> dict[str, Any]:
    return {
        "ok": True,
        "source_status": "fixture_local_contract",
        "route_owner": "ai_crm_next",
        "status_code": status_code,
        "side_effect_safety": profile_segment_side_effect_safety(),
        **payload,
    }


def _action_template_response(payload: dict[str, Any], *, status_code: int = 200) -> dict[str, Any]:
    return {
        "ok": True,
        "source_status": "fixture_local_contract",
        "route_owner": "ai_crm_next",
        "status_code": status_code,
        "side_effect_safety": action_template_side_effect_safety(),
        **payload,
    }


def _task_group_response(payload: dict[str, Any], *, status_code: int = 200) -> dict[str, Any]:
    return {
        "ok": True,
        "source_status": "fixture_local_contract",
        "route_owner": "ai_crm_next",
        "status_code": status_code,
        "side_effect_safety": task_group_side_effect_safety(),
        **payload,
    }


def _workflow_response(payload: dict[str, Any], *, status_code: int = 200) -> dict[str, Any]:
    return {
        "ok": True,
        "source_status": "fixture_local_contract",
        "route_owner": "ai_crm_next",
        "status_code": status_code,
        "side_effect_safety": workflow_side_effect_safety(),
        **payload,
    }


def _workflow_node_response(payload: dict[str, Any], *, status_code: int = 200) -> dict[str, Any]:
    return {
        "ok": True,
        "source_status": "fixture_local_contract",
        "route_owner": "ai_crm_next",
        "status_code": status_code,
        "side_effect_safety": workflow_node_side_effect_safety(),
        **payload,
    }


def _task_response(payload: dict[str, Any], *, status_code: int = 200) -> dict[str, Any]:
    return {
        "ok": True,
        "source_status": "fixture_local_contract",
        "route_owner": "ai_crm_next",
        "status_code": status_code,
        "side_effect_safety": task_side_effect_safety(),
        **payload,
    }


def _agent_response(payload: dict[str, Any], *, status_code: int = 200) -> dict[str, Any]:
    return {
        "ok": True,
        "source_status": "fixture_local_contract",
        "route_owner": "ai_crm_next",
        "status_code": status_code,
        "side_effect_safety": agent_side_effect_safety(),
        **payload,
    }


def _agent_output_response(payload: dict[str, Any], *, status_code: int = 200) -> dict[str, Any]:
    return {
        "ok": True,
        "source_status": "fixture_local_contract",
        "route_owner": "ai_crm_next",
        "status_code": status_code,
        "side_effect_safety": agent_output_side_effect_safety(),
        **payload,
    }


def _agent_run_response(payload: dict[str, Any], *, status_code: int = 200) -> dict[str, Any]:
    return {
        "ok": True,
        "source_status": "fixture_local_contract",
        "route_owner": "ai_crm_next",
        "status_code": status_code,
        "side_effect_safety": agent_run_side_effect_safety(),
        **payload,
    }


def _request_dump(request: Any, *, exclude_unset: bool = False) -> dict[str, Any]:
    dump = getattr(request, "model_dump", None)
    if callable(dump):
        return dump(exclude_unset=exclude_unset)
    return request.dict(exclude_unset=exclude_unset)


CONTENT_MODES = {"unified", "profile_layered", "behavior_layered", "agent"}
OPERATION_CONTENT_KEYS = {
    "content_mode",
    "profile_segment_template_id",
    "unified_content_json",
    "segment_contents_json",
    "agent_config_json",
}
BEHAVIOR_SEGMENT_NAMES = {
    "lt_2": "消息少于 2",
    "between_2_9": "消息 2-9",
    "gte_10": "消息大于等于 10",
}


def _normalize_content_mode(mode: str) -> str:
    value = str(mode or "").strip()
    if value not in CONTENT_MODES:
        raise ContractError("content_mode 必须是 unified、profile_layered、behavior_layered 或 agent")
    return value


def _operation_content_from_task(task: dict[str, Any]) -> dict[str, Any]:
    config = task.get("config") if isinstance(task.get("config"), dict) else {}
    existing = config.get("operation_content") if isinstance(config.get("operation_content"), dict) else {}
    return {
        "content_mode": str(existing.get("content_mode") or "unified"),
        "profile_segment_template_id": int(existing.get("profile_segment_template_id") or 0),
        "unified_content_json": existing.get("unified_content_json") if isinstance(existing.get("unified_content_json"), dict) else {},
        "segment_contents_json": existing.get("segment_contents_json") if isinstance(existing.get("segment_contents_json"), list) else [],
        "agent_config_json": existing.get("agent_config_json") if isinstance(existing.get("agent_config_json"), dict) else {},
        **{key: value for key, value in existing.items() if key not in OPERATION_CONTENT_KEYS},
    }


def _content_patch_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    patch: dict[str, Any] = {}
    for source in (
        payload,
        payload.get("config") if isinstance(payload.get("config"), dict) else {},
        payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
    ):
        if not isinstance(source, dict):
            continue
        operation_content = source.get("operation_content") if isinstance(source.get("operation_content"), dict) else {}
        for container in (source, operation_content):
            for key in OPERATION_CONTENT_KEYS:
                if key in container:
                    patch[key] = container[key]
    if "content_mode" in patch:
        patch["content_mode"] = _normalize_content_mode(patch["content_mode"])
    if "profile_segment_template_id" in patch and patch["profile_segment_template_id"] in (None, ""):
        patch["profile_segment_template_id"] = 0
    return patch


def _task_patch_with_operation_content(task: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    config = deepcopy(task.get("config") if isinstance(task.get("config"), dict) else {})
    metadata = deepcopy(task.get("metadata") if isinstance(task.get("metadata"), dict) else {})
    if isinstance(payload.get("config"), dict):
        config = deepcopy(payload["config"])
    if isinstance(payload.get("metadata"), dict):
        metadata = deepcopy(payload["metadata"])
    operation_patch = _content_patch_from_payload(payload)
    if operation_patch:
        operation_content = _operation_content_from_task({"config": config})
        operation_content.update(operation_patch)
        config["operation_content"] = operation_content
    return {"config": config, "metadata": metadata, "operator": payload.get("operator") or "system"}


def _update_task_operation_content(
    owner: _TaskRepositoryOwner,
    task_id: int,
    operation_patch: dict[str, Any],
    *,
    operator: str = "system",
) -> dict[str, Any]:
    repo = owner._repo_or_none()
    if repo is None:
        return _task_production_unavailable_payload()
    try:
        current = repo.get_task(int(task_id))
        if not current:
            raise NotFoundError("automation task not found")
        config = deepcopy(current.get("config") if isinstance(current.get("config"), dict) else {})
        operation_content = _operation_content_from_task(current)
        operation_content.update(operation_patch)
        if "content_mode" in operation_content:
            operation_content["content_mode"] = _normalize_content_mode(operation_content["content_mode"])
        config["operation_content"] = operation_content
        result = repo.update_task(
            int(task_id),
            {"config": config, "metadata": current.get("metadata") or {}, "operator": operator},
            operator=operator,
        )
    except RepositoryProviderError as exc:
        return owner._blocked_payload(exc)
    return _task_response({"source_status": getattr(repo, "source_status", "fixture_local_contract"), **result})


def _current_agent_config(owner: _TaskRepositoryOwner, task_id: int) -> dict[str, Any]:
    repo = owner._repo_or_none()
    if repo is None:
        return {}
    current = repo.get_task(int(task_id))
    if not current:
        raise NotFoundError("automation task not found")
    return dict(_operation_content_from_task(current).get("agent_config_json") or {})


def _update_task_segment_content(
    owner: _TaskRepositoryOwner,
    task_id: int,
    *,
    mode: str,
    segment_key: str,
    segment_name: str,
    content_package: dict[str, Any],
    operator: str,
    extra_operation_patch: dict[str, Any] | None = None,
) -> dict[str, Any]:
    repo = owner._repo_or_none()
    if repo is None:
        return _task_production_unavailable_payload()
    try:
        current = repo.get_task(int(task_id))
        if not current:
            raise NotFoundError("automation task not found")
        config = deepcopy(current.get("config") if isinstance(current.get("config"), dict) else {})
        operation_content = _operation_content_from_task(current)
        rows = [dict(row) for row in operation_content.get("segment_contents_json") or [] if isinstance(row, dict)]
        next_row = {
            "segment_key": segment_key,
            "segment_name": str(segment_name or segment_key).strip() or segment_key,
            "content_package": content_package,
        }
        next_rows: list[dict[str, Any]] = []
        replaced = False
        for row in rows:
            if str(row.get("segment_key") or "") == segment_key:
                if not replaced:
                    next_rows.append(next_row)
                    replaced = True
                continue
            next_rows.append(row)
        if not replaced:
            next_rows.append(next_row)
        operation_content.update(extra_operation_patch or {})
        operation_content["content_mode"] = mode
        operation_content["segment_contents_json"] = next_rows
        config["operation_content"] = operation_content
        result = repo.update_task(
            int(task_id),
            {"config": config, "metadata": current.get("metadata") or {}, "operator": operator},
            operator=operator,
        )
    except RepositoryProviderError as exc:
        return owner._blocked_payload(exc)
    return _task_response({"source_status": getattr(repo, "source_status", "fixture_local_contract"), **result})


class _ProfileSegmentRepositoryOwner:
    def __init__(self, repo: AutomationRepository | None = None) -> None:
        self._repo = repo

    def _repo_or_none(self) -> AutomationRepository | None:
        if (production_environment() or production_data_ready()) and self._repo is None:
            if not profile_segment_template_sqlalchemy_enabled():
                return None
        if self._repo is None:
            self._repo = build_profile_segment_template_repository()
        return self._repo

    def _blocked_payload(self, exc: Exception | None = None) -> dict[str, Any]:
        detail = str(exc) if exc else None
        return _profile_segment_production_unavailable_payload(detail)


class _ActionTemplateRepositoryOwner:
    def __init__(self, repo: Any | None = None) -> None:
        self._repo = repo

    def _repo_or_none(self) -> Any | None:
        if (production_environment() or production_data_ready()) and self._repo is None:
            if not action_template_sqlalchemy_enabled():
                return None
        if self._repo is None:
            self._repo = build_action_template_repository()
        return self._repo

    def _blocked_payload(self, exc: Exception | None = None) -> dict[str, Any]:
        detail = str(exc) if exc else None
        return _action_template_production_unavailable_payload(detail)

    def _repo_or_blocked_payload(self) -> Any | dict[str, Any]:
        try:
            repo = self._repo_or_none()
        except RepositoryProviderError as exc:
            return self._blocked_payload(exc)
        if repo is None:
            return None
        return repo


class _TaskGroupRepositoryOwner:
    def __init__(self, repo: AutomationRepository | None = None) -> None:
        self._repo = repo

    def _repo_or_none(self) -> AutomationRepository | None:
        if (production_environment() or production_data_ready()) and self._repo is None:
            return None
        if self._repo is None:
            self._repo = build_automation_repository()
        return self._repo

    def _blocked_payload(self, exc: Exception | None = None) -> dict[str, Any]:
        detail = str(exc) if exc else None
        return _task_group_production_unavailable_payload(detail)


class _WorkflowRepositoryOwner:
    def __init__(self, repo: AutomationRepository | None = None) -> None:
        self._repo = repo

    def _repo_or_none(self) -> AutomationRepository | None:
        if (production_environment() or production_data_ready()) and self._repo is None:
            return None
        if self._repo is None:
            self._repo = build_automation_repository()
        return self._repo

    def _blocked_payload(self, exc: Exception | None = None) -> dict[str, Any]:
        detail = str(exc) if exc else None
        return _workflow_production_unavailable_payload(detail)


class _WorkflowNodeRepositoryOwner:
    def __init__(self, repo: AutomationRepository | None = None) -> None:
        self._repo = repo

    def _repo_or_none(self) -> AutomationRepository | None:
        if (production_environment() or production_data_ready()) and self._repo is None:
            return None
        if self._repo is None:
            self._repo = build_automation_repository()
        return self._repo

    def _blocked_payload(self, exc: Exception | None = None) -> dict[str, Any]:
        detail = str(exc) if exc else None
        return _workflow_node_production_unavailable_payload(detail)


class _TaskRepositoryOwner:
    def __init__(self, repo: AutomationRepository | None = None) -> None:
        self._repo = repo

    def _repo_or_none(self) -> AutomationRepository | None:
        if (production_environment() or production_data_ready()) and self._repo is None:
            if not task_postgres_enabled():
                return None
            self._repo = build_automation_repository(task_backend="postgres")
        if self._repo is None:
            self._repo = build_automation_repository()
        return self._repo

    def _blocked_payload(self, exc: Exception | None = None) -> dict[str, Any]:
        detail = str(exc) if exc else None
        return _task_production_unavailable_payload(detail)


class _AgentRepositoryOwner:
    def __init__(self, repo: AutomationRepository | None = None) -> None:
        self._repo = repo

    def _repo_or_none(self) -> AutomationRepository | None:
        if (production_environment() or production_data_ready()) and self._repo is None:
            if not agent_postgres_enabled():
                return None
            self._repo = build_automation_repository(agent_backend="postgres")
        if self._repo is None:
            self._repo = build_automation_repository()
        return self._repo

    def _blocked_payload(self, exc: Exception | None = None) -> dict[str, Any]:
        detail = str(exc) if exc else None
        return _agent_production_unavailable_payload(detail)


class _AgentOutputRepositoryOwner:
    def __init__(self, repo: AutomationRepository | None = None) -> None:
        self._repo = repo

    def _repo_or_none(self) -> AutomationRepository | None:
        if (production_environment() or production_data_ready()) and self._repo is None:
            return None
        if self._repo is None:
            self._repo = build_automation_repository()
        return self._repo

    def _blocked_payload(self, exc: Exception | None = None) -> dict[str, Any]:
        detail = str(exc) if exc else None
        return _agent_output_production_unavailable_payload(detail)


class _AgentRunRepositoryOwner:
    def __init__(self, repo: AutomationRepository | None = None) -> None:
        self._repo = repo

    def _repo_or_none(self) -> AutomationRepository | None:
        if (production_environment() or production_data_ready()) and self._repo is None:
            return None
        if self._repo is None:
            self._repo = build_automation_repository()
        return self._repo

    def _blocked_payload(self, exc: Exception | None = None) -> dict[str, Any]:
        detail = str(exc) if exc else None
        return _agent_run_production_unavailable_payload(detail)


class GetAutomationRuntimeContractQuery:
    def __init__(self, repo: AutomationRepository | None = None) -> None:
        self._repo = repo or build_automation_repository()

    def execute(self) -> dict[str, Any]:
        return {"ok": True, "pools": self._repo.list_pools(), "workflows": default_workflow_registry(), "status": "partial"}

    __call__ = execute


class ListActionTemplatesQuery(_ActionTemplateRepositoryOwner):
    def execute(self, request: ActionTemplateListRequest) -> dict[str, Any]:
        repo = self._repo_or_blocked_payload()
        if isinstance(repo, dict):
            return repo
        if repo is None:
            return _action_template_production_unavailable_payload()
        try:
            rows, total = repo.list_action_templates(_request_dump(request))
        except RepositoryProviderError as exc:
            return self._blocked_payload(exc)
        return _action_template_response(
            {
                "items": rows,
                "templates": rows,
                "total": total,
                "count": len(rows),
                "limit": request.limit,
                "offset": request.offset,
                "filters": {
                    "template_source": request.template_source,
                    "category": request.category,
                    "keyword": request.keyword,
                    "include_archived": request.include_archived,
                },
            }
        )

    __call__ = execute


class CreateActionTemplateCommand(_ActionTemplateRepositoryOwner):
    def execute(self, request: ActionTemplateCreateRequest) -> dict[str, Any]:
        repo = self._repo_or_blocked_payload()
        if isinstance(repo, dict):
            return repo
        if repo is None:
            return _action_template_production_unavailable_payload()
        payload = _request_dump(request)
        idempotency_key = str(payload.get("idempotency_key") or "").strip()
        if not idempotency_key:
            raise ContractError("idempotency_key is required")
        try:
            result = repo.create_action_template(
                payload,
                idempotency_key=idempotency_key,
                operator=str(payload.get("operator") or "system"),
            )
        except ActionTemplateIdempotencyConflict as exc:
            return {
                "ok": False,
                "status_code": 409,
                "error_code": "idempotency_conflict",
                "message": str(exc),
                "route_owner": "ai_crm_next",
                "side_effect_safety": action_template_side_effect_safety(),
            }
        except RepositoryProviderError as exc:
            return self._blocked_payload(exc)
        return _action_template_response(result, status_code=201)

    __call__ = execute


class ListTaskGroupsQuery(_TaskGroupRepositoryOwner):
    def execute(self, request: TaskGroupListRequest) -> dict[str, Any]:
        repo = self._repo_or_none()
        if repo is None:
            return _task_group_production_unavailable_payload()
        try:
            rows, total = repo.list_task_groups(_request_dump(request))
        except RepositoryProviderError as exc:
            return self._blocked_payload(exc)
        return _task_group_response(
            {
                "items": rows,
                "groups": rows,
                "total": total,
                "count": len(rows),
                "limit": request.limit,
                "offset": request.offset,
                "filters": {
                    "program_id": request.program_id,
                    "include_archived": request.include_archived,
                },
            }
        )

    __call__ = execute


class CreateTaskGroupCommand(_TaskGroupRepositoryOwner):
    def execute(self, request: TaskGroupCreateRequest) -> dict[str, Any]:
        repo = self._repo_or_none()
        if repo is None:
            return _task_group_production_unavailable_payload()
        payload = _request_dump(request)
        idempotency_key = str(payload.get("idempotency_key") or "").strip()
        if not idempotency_key:
            raise ContractError("idempotency_key is required")
        try:
            result = repo.create_task_group(
                payload,
                idempotency_key=idempotency_key,
                operator=str(payload.get("operator") or "system"),
            )
        except RepositoryProviderError as exc:
            return self._blocked_payload(exc)
        return _task_group_response(result, status_code=201)

    __call__ = execute


class ListWorkflowsQuery(_WorkflowRepositoryOwner):
    def execute(self, request: WorkflowListRequest) -> dict[str, Any]:
        repo = self._repo_or_none()
        if repo is None:
            return _workflow_production_unavailable_payload()
        try:
            rows, total = repo.list_workflows(_request_dump(request))
        except RepositoryProviderError as exc:
            return self._blocked_payload(exc)
        return _workflow_response(
            {
                "items": rows,
                "workflows": rows,
                "total": total,
                "count": len(rows),
                "limit": request.limit,
                "offset": request.offset,
                "filters": {
                    "program_id": request.program_id,
                    "status": request.status,
                    "include_archived": request.include_archived,
                },
            }
        )

    __call__ = execute


class CreateWorkflowCommand(_WorkflowRepositoryOwner):
    def execute(self, request: WorkflowCreateRequest) -> dict[str, Any]:
        repo = self._repo_or_none()
        if repo is None:
            return _workflow_production_unavailable_payload()
        payload = _request_dump(request)
        idempotency_key = str(payload.get("idempotency_key") or "").strip()
        if not idempotency_key:
            raise ContractError("idempotency_key is required")
        try:
            result = repo.create_workflow(
                payload,
                idempotency_key=idempotency_key,
                operator=str(payload.get("operator") or "system"),
            )
        except RepositoryProviderError as exc:
            return self._blocked_payload(exc)
        return _workflow_response(result, status_code=201)

    __call__ = execute


class ListWorkflowNodesQuery(_WorkflowNodeRepositoryOwner):
    def execute(self, request: WorkflowNodeListRequest) -> dict[str, Any]:
        repo = self._repo_or_none()
        if repo is None:
            return _workflow_node_production_unavailable_payload()
        try:
            rows, total = repo.list_workflow_nodes(_request_dump(request))
        except RepositoryProviderError as exc:
            return self._blocked_payload(exc)
        return _workflow_node_response(
            {
                "items": rows,
                "nodes": rows,
                "total": total,
                "count": len(rows),
                "limit": request.limit,
                "offset": request.offset,
                "filters": {
                    "program_id": request.program_id,
                    "workflow_id": request.workflow_id,
                    "node_type": request.node_type,
                    "status": request.status,
                    "include_archived": request.include_archived,
                },
            }
        )

    __call__ = execute


class CreateWorkflowNodeCommand(_WorkflowNodeRepositoryOwner):
    def execute(self, request: WorkflowNodeCreateRequest) -> dict[str, Any]:
        repo = self._repo_or_none()
        if repo is None:
            return _workflow_node_production_unavailable_payload()
        payload = _request_dump(request)
        idempotency_key = str(payload.get("idempotency_key") or "").strip()
        if not idempotency_key:
            raise ContractError("idempotency_key is required")
        try:
            result = repo.create_workflow_node(
                payload,
                idempotency_key=idempotency_key,
                operator=str(payload.get("operator") or "system"),
            )
        except RepositoryProviderError as exc:
            return self._blocked_payload(exc)
        return _workflow_node_response(result, status_code=201)

    __call__ = execute


class UpdateWorkflowNodeCommand(_WorkflowNodeRepositoryOwner):
    def execute(self, node_id: int, request: WorkflowNodeUpdateRequest) -> dict[str, Any]:
        repo = self._repo_or_none()
        if repo is None:
            return _workflow_node_production_unavailable_payload()
        payload = _request_dump(request, exclude_unset=True)
        try:
            result = repo.update_workflow_node(
                int(node_id),
                payload,
                operator=str(payload.get("operator") or "system"),
            )
        except RepositoryProviderError as exc:
            return self._blocked_payload(exc)
        return _workflow_node_response({"source_status": getattr(repo, "source_status", "fixture_local_contract"), **result})

    __call__ = execute


class DeleteWorkflowNodeCommand(_WorkflowNodeRepositoryOwner):
    def execute(self, node_id: int, *, operator: str = "system") -> dict[str, Any]:
        repo = self._repo_or_none()
        if repo is None:
            return _workflow_node_production_unavailable_payload()
        try:
            result = repo.delete_workflow_node(int(node_id), operator=operator)
        except RepositoryProviderError as exc:
            return self._blocked_payload(exc)
        return _workflow_node_response({"source_status": getattr(repo, "source_status", "fixture_local_contract"), **result})

    __call__ = execute


class ListTasksQuery(_TaskRepositoryOwner):
    def execute(self, request: TaskListRequest) -> dict[str, Any]:
        repo = self._repo_or_none()
        if repo is None:
            return _task_production_unavailable_payload()
        try:
            rows, total = repo.list_tasks(_request_dump(request))
        except RepositoryProviderError as exc:
            return self._blocked_payload(exc)
        return _task_response(
            {
                "items": rows,
                "tasks": rows,
                "total": total,
                "count": len(rows),
                "limit": request.limit,
                "offset": request.offset,
                "filters": {
                    "program_id": request.program_id,
                    "workflow_id": request.workflow_id,
                    "node_id": request.node_id,
                    "group_id": request.group_id,
                    "task_type": request.task_type,
                    "status": request.status,
                    "include_archived": request.include_archived,
                },
            }
        )

    __call__ = execute


class CreateTaskCommand(_TaskRepositoryOwner):
    def execute(self, request: TaskCreateRequest) -> dict[str, Any]:
        repo = self._repo_or_none()
        if repo is None:
            return _task_production_unavailable_payload()
        payload = _request_dump(request)
        idempotency_key = str(payload.get("idempotency_key") or "").strip()
        if not idempotency_key:
            raise ContractError("idempotency_key is required")
        try:
            result = repo.create_task(
                payload,
                idempotency_key=idempotency_key,
                operator=str(payload.get("operator") or "system"),
            )
        except RepositoryProviderError as exc:
            return self._blocked_payload(exc)
        return _task_response(result, status_code=201)

    __call__ = execute


class GetTaskDetailQuery(_TaskRepositoryOwner):
    def execute(self, task_id: int) -> dict[str, Any]:
        repo = self._repo_or_none()
        if repo is None:
            return _task_production_unavailable_payload()
        try:
            task = repo.get_task(int(task_id))
        except RepositoryProviderError as exc:
            return self._blocked_payload(exc)
        if not task:
            raise NotFoundError("automation task not found")
        return _task_response({"source_status": getattr(repo, "source_status", "fixture_local_contract"), "task": task})

    __call__ = execute


class UpdateTaskCommand(_TaskRepositoryOwner):
    def execute(self, task_id: int, request: TaskUpdateRequest) -> dict[str, Any]:
        repo = self._repo_or_none()
        if repo is None:
            return _task_production_unavailable_payload()
        payload = _request_dump(request, exclude_unset=True)
        try:
            current = repo.get_task(int(task_id))
            if not current:
                raise NotFoundError("automation task not found")
            patch = _task_patch_with_operation_content(current, payload)
            result = repo.update_task(
                int(task_id),
                patch,
                operator=str(payload.get("operator") or "system"),
            )
        except RepositoryProviderError as exc:
            return self._blocked_payload(exc)
        return _task_response({"source_status": getattr(repo, "source_status", "fixture_local_contract"), **result})

    __call__ = execute


class UpdateTaskSendStrategyCommand(_TaskRepositoryOwner):
    def execute(self, task_id: int, request: SendStrategyUpdateRequest) -> dict[str, Any]:
        mode = _normalize_content_mode(request.content_mode)
        operation_patch: dict[str, Any] = {"content_mode": mode}
        if mode == "profile_layered":
            template_id = int(request.profile_segment_template_id or 0)
            if template_id <= 0:
                raise ContractError("profile_layered 模式必须提供 profile_segment_template_id")
            operation_patch["profile_segment_template_id"] = template_id
        if mode == "behavior_layered":
            operation_patch.setdefault("behavior_rule_key", "default_message_count")
        if mode == "agent":
            agent_code = str(request.agent_code or "").strip()
            if not agent_code:
                raise ContractError("agent 模式必须提供 agent_code")
            agent_config = _current_agent_config(self, int(task_id))
            agent_config["agent_code"] = agent_code
            operation_patch["agent_config_json"] = agent_config
        return _update_task_operation_content(
            self,
            task_id,
            operation_patch,
            operator=request.operator,
        )

    __call__ = execute


class SaveUnifiedSendContentCommand(_TaskRepositoryOwner):
    def execute(self, task_id: int, request: UnifiedSendContentUpdateRequest) -> dict[str, Any]:
        content_package = NormalizeSendContentPackageCommand()(
            request.content_package,
            text_enabled=True,
            require_body=False,
        )
        return _update_task_operation_content(
            self,
            task_id,
            {"content_mode": "unified", "unified_content_json": content_package},
            operator=request.operator,
        )

    __call__ = execute


class SaveProfileSegmentSendContentCommand(_TaskRepositoryOwner):
    def execute(self, task_id: int, segment_key: str, request: ProfileSegmentSendContentUpdateRequest) -> dict[str, Any]:
        key = str(segment_key or "").strip()
        if not key:
            raise ContractError("segment_key 不能为空")
        template_id = int(request.profile_segment_template_id or 0)
        if template_id <= 0:
            raise ContractError("画像分层内容必须提供 profile_segment_template_id")
        template_payload = GetProfileSegmentTemplateQuery()(template_id)
        if template_payload.get("ok") is False:
            return template_payload
        content_package = NormalizeSendContentPackageCommand()(
            request.content_package,
            text_enabled=True,
            require_body=False,
        )
        return _update_task_segment_content(
            self,
            task_id,
            mode="profile_layered",
            segment_key=key,
            segment_name=request.segment_name,
            content_package=content_package,
            operator=request.operator,
            extra_operation_patch={"profile_segment_template_id": template_id},
        )

    __call__ = execute


class SaveBehaviorSegmentSendContentCommand(_TaskRepositoryOwner):
    def execute(self, task_id: int, segment_key: str, request: BehaviorSegmentSendContentUpdateRequest) -> dict[str, Any]:
        key = str(segment_key or "").strip()
        if key not in BEHAVIOR_SEGMENT_NAMES:
            raise ContractError("消息数分层 segment_key 必须是 lt_2、between_2_9 或 gte_10")
        content_package = NormalizeSendContentPackageCommand()(
            request.content_package,
            text_enabled=True,
            require_body=False,
        )
        return _update_task_segment_content(
            self,
            task_id,
            mode="behavior_layered",
            segment_key=key,
            segment_name=request.segment_name or BEHAVIOR_SEGMENT_NAMES[key],
            content_package=content_package,
            operator=request.operator,
            extra_operation_patch={"behavior_rule_key": "default_message_count"},
        )

    __call__ = execute


class SaveAgentMaterialsCommand(_TaskRepositoryOwner):
    def execute(self, task_id: int, request: AgentMaterialsUpdateRequest) -> dict[str, Any]:
        agent_code = str(request.agent_code or "").strip()
        if not agent_code:
            raise ContractError("agent_code 不能为空")
        content_package = NormalizeSendContentPackageCommand()(
            request.content_package,
            text_enabled=True,
            require_body=False,
        )
        agent_config = _current_agent_config(self, int(task_id))
        agent_config.update(
            {
                "agent_code": agent_code,
                "image_library_ids": content_package["image_library_ids"],
                "miniprogram_library_ids": content_package["miniprogram_library_ids"],
                "attachment_library_ids": content_package["attachment_library_ids"],
            }
        )
        for key in ("requirement", "fallback_content", "prompt", "material_prompt"):
            value = str(getattr(request, key, "") or "").strip()
            if value or key not in agent_config:
                agent_config[key] = value
        content_text = str(content_package.get("content_text") or "").strip()
        if content_text and not str(agent_config.get("requirement") or "").strip():
            agent_config["requirement"] = content_text
        return _update_task_operation_content(
            self,
            task_id,
            {
                "content_mode": "agent",
                "agent_config_json": agent_config,
            },
            operator=request.operator,
        )

    __call__ = execute


class GetBehaviorSegmentRulesQuery:
    def execute(self) -> dict[str, Any]:
        return {
            "ok": True,
            "rules": [
                {
                    "rule_key": "default_message_count",
                    "rule_name": "默认消息数三层",
                    "segments": [
                        {"segment_key": "lt_2", "segment_name": "消息少于 2"},
                        {"segment_key": "between_2_9", "segment_name": "消息 2-9"},
                        {"segment_key": "gte_10", "segment_name": "消息大于等于 10"},
                    ],
                }
            ],
        }

    __call__ = execute


class ListAgentsQuery(_AgentRepositoryOwner):
    def execute(self, request: AgentListRequest) -> dict[str, Any]:
        repo = self._repo_or_none()
        if repo is None:
            return _agent_production_unavailable_payload()
        try:
            rows, total = repo.list_agents(_request_dump(request))
        except RepositoryProviderError as exc:
            return self._blocked_payload(exc)
        options = [
            {
                **item,
                "value": item.get("agent_code") or item.get("code") or "",
                "label": item.get("agent_name") or item.get("name") or item.get("agent_code") or "",
            }
            for item in rows
        ]
        return _agent_response(
            {
                "items": rows,
                "agents": rows,
                "options": options,
                "total": total,
                "count": len(rows),
                "limit": request.limit,
                "offset": request.offset,
                "filters": {
                    "program_id": request.program_id,
                    "workflow_id": request.workflow_id,
                    "node_id": request.node_id,
                    "task_id": request.task_id,
                    "agent_type": request.agent_type,
                    "status": request.status,
                    "include_archived": request.include_archived,
                },
            }
        )

    __call__ = execute


class CreateAgentCommand(_AgentRepositoryOwner):
    def execute(self, request: AgentCreateRequest) -> dict[str, Any]:
        repo = self._repo_or_none()
        if repo is None:
            return _agent_production_unavailable_payload()
        payload = _request_dump(request)
        idempotency_key = str(payload.get("idempotency_key") or "").strip()
        if not idempotency_key:
            raise ContractError("idempotency_key is required")
        try:
            result = repo.create_agent(
                payload,
                idempotency_key=idempotency_key,
                operator=str(payload.get("operator") or "system"),
            )
        except RepositoryProviderError as exc:
            return self._blocked_payload(exc)
        return _agent_response(result, status_code=201)

    __call__ = execute


class ListAgentOutputsQuery(_AgentOutputRepositoryOwner):
    def execute(self, request: AgentOutputListRequest) -> dict[str, Any]:
        repo = self._repo_or_none()
        if repo is None:
            return _agent_output_production_unavailable_payload()
        try:
            rows, total, filters = repo.list_agent_outputs(_request_dump(request))
        except RepositoryProviderError as exc:
            return self._blocked_payload(exc)
        return _agent_output_response(
            {
                "items": rows,
                "rows": rows,
                "outputs": rows,
                "total": total,
                "count": len(rows),
                "page": filters["page"],
                "page_size": filters["page_size"],
                "filters": {
                    "request_id": filters["request_id"],
                    "external_contact_id": filters["external_contact_id"],
                    "userid": filters["userid"],
                    "agent_code": filters["agent_code"],
                    "output_type": filters["output_type"],
                    "applied_status": filters["applied_status"],
                    "min_confidence": filters["min_confidence"],
                    "max_confidence": filters["max_confidence"],
                    "has_error": filters["has_error"],
                    "visibility": filters["visibility"],
                },
            }
        )

    __call__ = execute


class GetAgentOutputDetailQuery(_AgentOutputRepositoryOwner):
    def execute(self, request: AgentOutputDetailRequest) -> dict[str, Any]:
        repo = self._repo_or_none()
        if repo is None:
            return _agent_output_production_unavailable_payload()
        try:
            output = repo.get_agent_output(request.output_id, _request_dump(request))
        except RepositoryProviderError as exc:
            return self._blocked_payload(exc)
        if not output:
            raise NotFoundError("agent output not found")
        return _agent_output_response(
            {
                "output": output,
                "run": agent_output_run_projection(output, visibility=output.get("visibility") or "masked"),
            }
        )

    __call__ = execute


class ListAgentRunsQuery(_AgentRunRepositoryOwner):
    def execute(self, request: AgentRunListRequest) -> dict[str, Any]:
        repo = self._repo_or_none()
        if repo is None:
            return _agent_run_production_unavailable_payload()
        try:
            rows, total, filters = repo.list_agent_runs(_request_dump(request))
        except RepositoryProviderError as exc:
            return self._blocked_payload(exc)
        return _agent_run_response(
            {
                "items": rows,
                "rows": rows,
                "runs": rows,
                "total": total,
                "count": len(rows),
                "page": filters["page"],
                "page_size": filters["page_size"],
                "filters": {
                    "request_id": filters["request_id"],
                    "run_id": filters["run_id"],
                    "agent_code": filters["agent_code"],
                    "run_status": filters["run_status"],
                    "trigger_source": filters["trigger_source"],
                    "external_contact_id": filters["external_contact_id"],
                    "userid": filters["userid"],
                    "task_id": filters["task_id"],
                    "workflow_id": filters["workflow_id"],
                    "started_after": filters["started_after"],
                    "started_before": filters["started_before"],
                    "has_error": filters["has_error"],
                    "visibility": filters["visibility"],
                },
            }
        )

    __call__ = execute


class GetAgentRunDetailQuery(_AgentRunRepositoryOwner):
    def execute(self, request: AgentRunDetailRequest) -> dict[str, Any]:
        repo = self._repo_or_none()
        if repo is None:
            return _agent_run_production_unavailable_payload()
        try:
            run = repo.get_agent_run(request.run_id, _request_dump(request))
        except RepositoryProviderError as exc:
            return self._blocked_payload(exc)
        if not run:
            raise NotFoundError("agent run not found")
        return _agent_run_response({"run": run})

    __call__ = execute


class GetProfileSegmentTemplateCatalogQuery(_ProfileSegmentRepositoryOwner):
    def execute(self) -> dict[str, Any]:
        repo = self._repo_or_none()
        if repo is None:
            return _profile_segment_production_unavailable_payload()
        try:
            return _profile_segment_response(repo.profile_segment_template_catalog())
        except RepositoryProviderError as exc:
            return self._blocked_payload(exc)

    __call__ = execute


class ListProfileSegmentTemplatesQuery(_ProfileSegmentRepositoryOwner):
    def execute(self, request: ProfileSegmentTemplateListRequest) -> dict[str, Any]:
        repo = self._repo_or_none()
        if repo is None:
            return _profile_segment_production_unavailable_payload()
        try:
            rows, total = repo.list_profile_segment_templates(
                enabled_only=request.enabled_only,
                program_id=request.program_id,
                limit=request.limit,
                offset=request.offset,
            )
        except RepositoryProviderError as exc:
            return self._blocked_payload(exc)
        source_status = getattr(repo, "source_status", "fixture_local_contract")
        return _profile_segment_response(
            {
                "source_status": source_status,
                "items": rows,
                "templates": rows,
                "total": total,
                "count": len(rows),
                "limit": request.limit,
                "offset": request.offset,
                "filters": {"enabled_only": request.enabled_only, "program_id": request.program_id},
            }
        )

    __call__ = execute


class GetProfileSegmentTemplateOptionsQuery(_ProfileSegmentRepositoryOwner):
    def execute(self, request: ProfileSegmentTemplateListRequest) -> dict[str, Any]:
        repo = self._repo_or_none()
        if repo is None:
            return _profile_segment_production_unavailable_payload()
        try:
            rows, total = repo.list_profile_segment_templates(
                enabled_only=request.enabled_only,
                program_id=request.program_id,
                limit=request.limit,
                offset=request.offset,
            )
        except RepositoryProviderError as exc:
            return self._blocked_payload(exc)
        source_status = getattr(repo, "source_status", "fixture_local_contract")
        options = [
            {
                "id": item["id"],
                "template_id": item["template_id"],
                "label": item["name"],
                "name": item["name"],
                "value": item["id"],
                "code": item["code"],
                "status": item["status"],
            }
            for item in rows
        ]
        return _profile_segment_response({"source_status": source_status, "items": options, "options": options, "total": total, "count": len(options)})

    __call__ = execute


class GetProfileSegmentTemplateQuery(_ProfileSegmentRepositoryOwner):
    def execute(self, template_id: int) -> dict[str, Any]:
        repo = self._repo_or_none()
        if repo is None:
            return _profile_segment_production_unavailable_payload()
        try:
            template = repo.get_profile_segment_template(template_id)
        except RepositoryProviderError as exc:
            return self._blocked_payload(exc)
        if not template:
            raise NotFoundError("profile segment template not found")
        return _profile_segment_response(
            {
                "source_status": getattr(repo, "source_status", "fixture_local_contract"),
                "template": template,
                "template_bundle": {"template": template},
            }
        )

    __call__ = execute


class CreateProfileSegmentTemplateCommand(_ProfileSegmentRepositoryOwner):
    def execute(self, request: ProfileSegmentTemplateCreateRequest) -> dict[str, Any]:
        repo = self._repo_or_none()
        if repo is None:
            return _profile_segment_production_unavailable_payload()
        payload = _request_dump(request)
        idempotency_key = str(payload.get("idempotency_key") or "").strip()
        if not idempotency_key:
            raise ContractError("idempotency_key is required")
        try:
            result = repo.create_profile_segment_template(
                payload,
                idempotency_key=idempotency_key,
                operator=str(payload.get("operator") or "system"),
            )
        except ProfileSegmentTemplateIdempotencyConflict as exc:
            return {
                "ok": False,
                "status_code": 409,
                "error_code": "idempotency_conflict",
                "message": str(exc),
                "route_owner": "ai_crm_next",
                "side_effect_safety": profile_segment_side_effect_safety(),
            }
        except RepositoryProviderError as exc:
            return self._blocked_payload(exc)
        return _profile_segment_response(result, status_code=201)

    __call__ = execute


class UpdateProfileSegmentTemplateCommand(_ProfileSegmentRepositoryOwner):
    def execute(self, template_id: int, request: ProfileSegmentTemplateUpdateRequest) -> dict[str, Any]:
        repo = self._repo_or_none()
        if repo is None:
            return _profile_segment_production_unavailable_payload()
        payload = _request_dump(request, exclude_unset=True)
        try:
            result = repo.update_profile_segment_template(
                int(template_id),
                payload,
                operator=str(payload.get("operator") or "system"),
            )
        except RepositoryProviderError as exc:
            return self._blocked_payload(exc)
        return _profile_segment_response(result)

    __call__ = execute


class GetAutomationOverviewQuery:
    def __init__(self, repo: AutomationRepository | None = None) -> None:
        self._repo = repo or build_automation_repository()

    def execute(self) -> dict[str, Any]:
        members, total = self._repo.list_members(limit=500, offset=0)
        return {
            "ok": True,
            "cards": overview_cards(members),
            "total": total,
            "filters": {},
            "generated_at": "fixture",
            "status": "partial",
        }

    __call__ = execute


class ListAutomationPoolsQuery:
    def __init__(self, repo: AutomationRepository | None = None) -> None:
        self._repo = repo or build_automation_repository()

    def execute(self) -> dict[str, Any]:
        members, _ = self._repo.list_members(limit=500, offset=0)
        return {"ok": True, "pools": pool_summary(members), "total": len(self._repo.list_pools()), "generated_at": "fixture"}

    __call__ = execute


class ListAutomationMembersQuery:
    def __init__(self, repo: AutomationRepository | None = None) -> None:
        self._repo = repo or build_automation_repository()

    def execute(
        self,
        *,
        current_pool: str = "",
        followup_type: str = "",
        owner_userid: str = "",
        keyword: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        filters = _filters_snapshot(current_pool=current_pool, followup_type=followup_type, owner_userid=owner_userid, keyword=keyword)
        rows, total = self._repo.list_members(
            {"current_pool": current_pool, "followup_type": followup_type, "owner_userid": owner_userid, "keyword": keyword},
            limit=limit,
            offset=offset,
        )
        return {"ok": True, "items": rows, "total": total, "limit": limit, "offset": offset, "filters": filters}

    __call__ = execute


class GetAutomationMemberDetailQuery:
    def __init__(
        self,
        repo: AutomationRepository | None = None,
        customer_context_query: GetCustomerChatContextQuery | None = None,
    ) -> None:
        self._repo = repo or build_automation_repository()
        self._customer_context_query = customer_context_query or GetCustomerChatContextQuery()

    def execute(self, member_id: str) -> dict[str, Any]:
        member = self._repo.get_member(member_id)
        if not member:
            raise NotFoundError("automation member not found")
        customer_context = {}
        recent_timeline_events: list[dict[str, Any]] = []
        warnings = list(member.get("warnings") or [])
        external_userid = str(member.get("external_userid") or "")
        if external_userid:
            try:
                context = self._customer_context_query(
                    CustomerChatContextRequest(external_userid=external_userid, timeline_limit=5, recent_message_limit=5)
                )
                customer_context = context.get("customer") or {}
                recent_timeline_events = context.get("recent_timeline_events") or []
            except Exception:
                warnings.append("customer_context_unavailable")
        return {
            "ok": True,
            "member": member,
            "history": self._repo.list_history(member_id),
            "customer_context": customer_context,
            "recent_timeline_events": recent_timeline_events,
            "warnings": warnings,
        }

    __call__ = execute


class ApplyQuestionnaireResultCommand:
    def __init__(self, repo: AutomationRepository | None = None) -> None:
        self._repo = repo or build_automation_repository()

    def execute(self, request: ApplyQuestionnaireResultRequest) -> dict[str, Any]:
        followup_type = normalize_followup_type(request.followup_type)
        member = self._repo.find_member(
            external_userid=request.external_userid,
            mobile=request.mobile,
            person_id=request.person_id,
        )
        is_new_member = False
        if not member:
            create_member = getattr(self._repo, "create_member_from_questionnaire", None)
            if not create_member:
                raise NotFoundError("automation member not found")
            member = create_member(request.model_dump())
            is_new_member = True
        if not is_new_member and self._should_ignore_questionnaire_reroute(member):
            updated, history = apply_transition(
                member,
                trigger="questionnaire_result_ignored",
                source=request.source,
                operator=request.operator,
                reason="questionnaire_result_received_after_initial_split",
                patch={
                    "last_ignored_questionnaire_result": {
                        "incoming_followup_type": followup_type,
                        "questionnaire_id": request.questionnaire_id,
                        "submission_id": request.submission_id,
                        "final_tags": request.final_tags,
                    }
                },
            )
            self._repo.save_member(updated)
            self._repo.create_execution_record(
                {
                    "record_type": "questionnaire_event",
                    "member_id": updated["member_id"],
                    "trigger": "questionnaire_result_ignored",
                    "status": "succeeded",
                    "status_label": "已记录问卷结果，未重新分流",
                    "payload_preview": {
                        "incoming_followup_type": followup_type,
                        "effective_followup_type": updated["followup_type"],
                        "after_pool": updated["current_pool"],
                    },
                }
            )
            return {"ok": True, "member": updated, "history": history, "source_status": "fixture_boundary", "rerouted": False}
        updated, history = apply_transition(
            member,
            trigger="questionnaire_result",
            source=request.source,
            operator=request.operator,
            reason=request.reason,
            patch={
                "questionnaire_followup_type": followup_type,
                "followup_type": followup_type,
                "last_questionnaire_id": request.questionnaire_id,
                "last_submission_id": request.submission_id,
                "last_final_tags": request.final_tags,
            },
        )
        self._repo.save_member(updated)
        self._repo.create_execution_record(
            {
                "record_type": "questionnaire_event",
                "member_id": updated["member_id"],
                "trigger": "questionnaire_result",
                "status": "succeeded",
                "status_label": "已记录问卷分流",
                "payload_preview": {"followup_type": followup_type, "after_pool": updated["current_pool"]},
            }
        )
        return {"ok": True, "member": updated, "history": history, "source_status": "fixture_boundary"}

    __call__ = execute

    def _should_ignore_questionnaire_reroute(self, member: dict[str, Any]) -> bool:
        has_questionnaire_split = bool(str(member.get("questionnaire_followup_type") or "").strip())
        has_manual_override = bool(str(member.get("manual_followup_type") or "").strip())
        already_left_initial_pool = str(member.get("current_pool") or "new_user") != "new_user"
        return has_questionnaire_split or has_manual_override or already_left_initial_pool


class ApplyTrialOpenedFactCommand:
    def __init__(self, repo: AutomationRepository | None = None) -> None:
        self._repo = repo or build_automation_repository()

    def execute(self, request: ApplyTrialOpenedFactRequest) -> dict[str, Any]:
        member = self._repo.get_member(request.member_id)
        if not member:
            raise NotFoundError("automation member not found")
        updated, history = apply_transition(
            member,
            trigger="trial_opened",
            source=request.source,
            operator=request.operator,
            reason=request.reason,
            occurred_at=request.occurred_at,
            patch={"trial_opened": True},
        )
        self._repo.save_member(updated)
        return {"ok": True, "member": updated, "history": history}

    __call__ = execute


class ApplyActivationFactCommand:
    def __init__(
        self,
        repo: AutomationRepository | None = None,
        identity_query: ResolvePersonIdentityQuery | None = None,
    ) -> None:
        self._repo = repo or build_automation_repository()
        self._identity_query = identity_query or ResolvePersonIdentityQuery()

    def execute(self, request: ApplyActivationFactRequest) -> dict[str, Any]:
        member = self._resolve_member(member_id=request.member_id, external_userid=request.external_userid, mobile=request.mobile)
        previous_pool = member["current_pool"]
        updated, history = apply_transition(
            member,
            trigger="activation_fact",
            source=request.source,
            operator=request.operator,
            reason=request.reason,
            occurred_at=request.activated_at,
            patch={"activated": True, "trial_opened": True},
        )
        self._repo.save_member(updated)
        self._repo.create_execution_record(
            {
                "record_type": "activation_webhook",
                "member_id": updated["member_id"],
                "trigger": "activation_fact",
                "status": "succeeded",
                "status_label": "已记录激活",
                "payload_preview": {"previous_pool": previous_pool, "current_pool": updated["current_pool"]},
            }
        )
        return {"ok": True, "member": updated, "previous_pool": previous_pool, "current_pool": updated["current_pool"], "history": history, "warnings": []}

    def _resolve_member(self, *, member_id: str | None, external_userid: str | None, mobile: str | None) -> dict[str, Any]:
        if member_id:
            member = self._repo.get_member(member_id)
            if member:
                return member
        if external_userid or mobile:
            identity = self._identity_query(ResolvePersonIdentityRequest(external_userid=external_userid, mobile=mobile))
            member = self._repo.find_member(
                external_userid=external_userid or (identity.external_userid if identity else None),
                mobile=mobile or (identity.mobile if identity else None),
                person_id=identity.person_id if identity else None,
            )
            if member:
                return member
        raise NotFoundError("automation member not found")

    __call__ = execute


class OverrideFollowupTypeCommand:
    def __init__(self, repo: AutomationRepository | None = None, write_gateway: Any | None = None) -> None:
        self._repo = repo or build_automation_repository()
        self._write_gateway = write_gateway or build_automation_write_gateway()

    def execute(self, member_id: str, request: OverrideFollowupTypeRequest) -> dict[str, Any]:
        member = self._repo.get_member(member_id)
        if not member:
            raise NotFoundError("automation member not found")
        followup_type = normalize_followup_type(request.followup_type)
        adapter_result = self._write_gateway.override_followup_type(
            member_id=member_id,
            external_userid=str(member.get("external_userid") or ""),
            followup_type=followup_type,
            operator=request.operator,
            reason=request.reason,
        )
        updated, history = apply_transition(
            member,
            trigger="manual_override",
            source="admin",
            operator=request.operator,
            reason=request.reason,
            patch={"manual_followup_type": followup_type, "followup_type": followup_type},
        )
        self._repo.save_member(updated)
        return {
            "ok": True,
            "member": updated,
            "history": history,
            "adapter_contract": {"automation_write": adapter_result},
            "side_effect_safety": _automation_side_effect_safety(
                real_automation_write_executed=bool(adapter_result.get("side_effect_executed"))
            ),
        }

    __call__ = execute


class ConfirmConversionCommand:
    def __init__(self, repo: AutomationRepository | None = None, write_gateway: Any | None = None) -> None:
        self._repo = repo or build_automation_repository()
        self._write_gateway = write_gateway or build_automation_write_gateway()

    def execute(self, member_id: str, request: AutomationActionRequest) -> dict[str, Any]:
        return self._action(member_id, request, trigger="confirm_conversion")

    def _action(self, member_id: str, request: AutomationActionRequest, *, trigger: str) -> dict[str, Any]:
        member = self._repo.get_member(member_id)
        if not member:
            raise NotFoundError("automation member not found")
        adapter_result = self._write_boundary(trigger=trigger, member=member, member_id=member_id, request=request)
        updated, history = apply_transition(member, trigger=trigger, source="admin", operator=request.operator, reason=request.reason)
        self._repo.save_member(updated)
        return {
            "ok": True,
            "member": updated,
            "history": history,
            "adapter_contract": {"automation_write": adapter_result},
            "side_effect_safety": _automation_side_effect_safety(
                real_automation_write_executed=bool(adapter_result.get("side_effect_executed"))
            ),
        }

    def _write_boundary(self, *, trigger: str, member: dict[str, Any], member_id: str, request: AutomationActionRequest) -> dict[str, Any]:
        kwargs = {
            "member_id": member_id,
            "external_userid": str(member.get("external_userid") or ""),
            "operator": request.operator,
            "reason": request.reason,
        }
        if trigger == "confirm_conversion":
            return self._write_gateway.confirm_conversion(**kwargs)
        if trigger == "enter_silent":
            return self._write_gateway.enter_silent(**kwargs)
        if trigger == "exit_marketing":
            return self._write_gateway.exit_marketing(**kwargs)
        return self._write_gateway.build_write_preview(operation=trigger, member_id=member_id, external_userid=kwargs["external_userid"])

    __call__ = execute


class EnterSilentPoolCommand(ConfirmConversionCommand):
    def execute(self, member_id: str, request: AutomationActionRequest) -> dict[str, Any]:
        return self._action(member_id, request, trigger="enter_silent")

    __call__ = execute


class ExitMarketingCommand(ConfirmConversionCommand):
    def execute(self, member_id: str, request: AutomationActionRequest) -> dict[str, Any]:
        return self._action(member_id, request, trigger="exit_marketing")

    __call__ = execute


class PushMemberContextToOpenClawCommand:
    def __init__(
        self,
        repo: AutomationRepository | None = None,
        openclaw_adapter: Any | None = None,
        legacy_bridge_adapter: Any | None = None,
    ) -> None:
        self._repo = repo or build_automation_repository()
        self._openclaw_adapter = openclaw_adapter or build_openclaw_webhook_adapter()
        self._legacy_bridge_adapter = legacy_bridge_adapter or build_openclaw_legacy_bridge_adapter()

    def execute(self, member_id: str, request: PushOpenClawContextRequest) -> dict[str, Any]:
        detail = GetAutomationMemberDetailQuery(self._repo)(member_id)
        payload_preview = {
            "member_id": member_id,
            "customer_context": detail.get("customer_context") or {},
            "questionnaire_summary": {
                "questionnaire_followup_type": detail["member"].get("questionnaire_followup_type"),
                "manual_followup_type": detail["member"].get("manual_followup_type"),
            },
            "current_pool": detail["member"].get("current_pool"),
            "recent_timeline_events": detail.get("recent_timeline_events") or [],
        }
        adapter_result = self._openclaw_adapter.push_member_context(
            member_id=member_id,
            external_userid=str(detail["member"].get("external_userid") or ""),
            payload_summary=payload_preview,
        )
        legacy_bridge_result = self._legacy_bridge_adapter.push_context_to_openclaw(
            member_id=member_id,
            external_userid=str(detail["member"].get("external_userid") or ""),
            payload_summary=payload_preview,
        )
        record = self._repo.create_execution_record(
            {
                "record_type": "openclaw_push",
                "member_id": member_id,
                "trigger": "push_openclaw_context",
                "status": "succeeded",
                "status_label": "Fake 推送已记录",
                "delivery_status": "fake",
                "payload_preview": payload_preview,
            }
        )
        return {
            "ok": True,
            "delivery_status": "fake",
            "payload_preview": payload_preview,
            "warnings": ["openclaw_not_called"],
            "record": record,
            "adapter_contract": {"openclaw": adapter_result, "openclaw_legacy_bridge": legacy_bridge_result},
            "side_effect_safety": _automation_side_effect_safety(
                real_openclaw_push_executed=bool(adapter_result.get("side_effect_executed") or legacy_bridge_result.get("side_effect_executed")),
                real_external_webhook_executed=bool(adapter_result.get("side_effect_executed") or legacy_bridge_result.get("side_effect_executed")),
            ),
        }

    __call__ = execute


class ListAutomationExecutionRecordsQuery:
    def __init__(self, repo: AutomationRepository | None = None) -> None:
        self._repo = repo or build_automation_repository()

    def execute(self, *, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        rows, total = self._repo.list_execution_records(limit=limit, offset=offset)
        return {"ok": True, "items": [execution_record_projection(item) for item in rows], "total": total, "limit": limit, "offset": offset}

    __call__ = execute


class ApplyActivationWebhookCommand:
    def __init__(self, repo: AutomationRepository | None = None, activation_gateway: Any | None = None) -> None:
        self._repo = repo or build_automation_repository()
        self._activation_gateway = activation_gateway or build_automation_activation_gateway()

    def execute(self, request: ActivationWebhookRequest) -> dict[str, Any]:
        if not (request.mobile or request.external_userid):
            raise ContractError("mobile or external_userid is required")
        activation_result = self._activation_gateway.receive_activation_event(
            external_userid=request.external_userid,
            mobile=request.mobile,
            source=request.source,
        )
        result = ApplyActivationFactCommand(self._repo)(
            ApplyActivationFactRequest(
                mobile=request.mobile,
                external_userid=request.external_userid,
                activated_at=request.activated_at,
                source=request.source,
                operator=request.operator,
                reason="activation_webhook",
            )
        )
        result["adapter_contract"] = {"activation": activation_result}
        result["side_effect_safety"] = _automation_side_effect_safety(
            real_activation_webhook_executed=bool(activation_result.get("side_effect_executed"))
        )
        return result

    __call__ = execute


class EnqueueWorkflowRunCommand:
    def __init__(self, workflow_runtime_adapter: Any | None = None) -> None:
        self._workflow_runtime_adapter = workflow_runtime_adapter or build_automation_workflow_runtime_adapter()

    def execute(self, *, workflow_id: str, member_id: str = "", execution_id: str = "", program_id: str = "") -> dict[str, Any]:
        adapter_result = self._workflow_runtime_adapter.enqueue_workflow_run(
            workflow_id=workflow_id,
            member_id=member_id,
            execution_id=execution_id,
            program_id=program_id,
        )
        return {"ok": adapter_result["ok"], "adapter_contract": {"workflow_runtime": adapter_result}, "side_effect_safety": _automation_side_effect_safety()}

    __call__ = execute


class RunWorkflowNodeCommand:
    def __init__(self, workflow_runtime_adapter: Any | None = None) -> None:
        self._workflow_runtime_adapter = workflow_runtime_adapter or build_automation_workflow_runtime_adapter()

    def execute(self, *, workflow_id: str, node_id: str, member_id: str = "", execution_id: str = "") -> dict[str, Any]:
        adapter_result = self._workflow_runtime_adapter.run_workflow_node(
            workflow_id=workflow_id,
            node_id=node_id,
            member_id=member_id,
            execution_id=execution_id,
        )
        return {"ok": adapter_result["ok"], "adapter_contract": {"workflow_runtime": adapter_result}, "side_effect_safety": _automation_side_effect_safety()}

    __call__ = execute


class RunDueWorkflowsCommand:
    def __init__(self, workflow_runtime_adapter: Any | None = None) -> None:
        self._workflow_runtime_adapter = workflow_runtime_adapter or build_automation_workflow_runtime_adapter()

    def execute(self, *, workflow_id: str = "", program_id: str = "", limit: int = 50) -> dict[str, Any]:
        adapter_result = self._workflow_runtime_adapter.run_due_workflows(workflow_id=workflow_id, program_id=program_id, limit=limit)
        return {"ok": adapter_result["ok"], "adapter_contract": {"workflow_runtime": adapter_result}, "side_effect_safety": _automation_side_effect_safety()}

    __call__ = execute


class RunAgentTaskCommand:
    def __init__(self, agent_runtime_adapter: Any | None = None) -> None:
        self._agent_runtime_adapter = agent_runtime_adapter or build_automation_agent_runtime_adapter()

    def execute(self, *, agent_task_id: str, member_id: str = "", workflow_id: str = "", execution_id: str = "") -> dict[str, Any]:
        adapter_result = self._agent_runtime_adapter.run_agent_task(
            agent_task_id=agent_task_id,
            member_id=member_id,
            workflow_id=workflow_id,
            execution_id=execution_id,
        )
        return {"ok": adapter_result["ok"], "adapter_contract": {"agent_runtime": adapter_result}, "side_effect_safety": _automation_side_effect_safety()}

    __call__ = execute


class GenerateAgentOutputCommand:
    def __init__(self, agent_runtime_adapter: Any | None = None) -> None:
        self._agent_runtime_adapter = agent_runtime_adapter or build_automation_agent_runtime_adapter()

    def execute(self, *, agent_task_id: str, member_id: str = "", workflow_id: str = "", execution_id: str = "") -> dict[str, Any]:
        adapter_result = self._agent_runtime_adapter.generate_agent_output(
            agent_task_id=agent_task_id,
            member_id=member_id,
            workflow_id=workflow_id,
            execution_id=execution_id,
        )
        return {"ok": adapter_result["ok"], "adapter_contract": {"agent_runtime": adapter_result}, "side_effect_safety": _automation_side_effect_safety()}

    __call__ = execute


class ReviewAgentOutputCommand:
    def __init__(self, agent_runtime_adapter: Any | None = None) -> None:
        self._agent_runtime_adapter = agent_runtime_adapter or build_automation_agent_runtime_adapter()

    def execute(self, *, agent_task_id: str, output_id: str = "", reviewer: str = "system", decision: str = "preview") -> dict[str, Any]:
        adapter_result = self._agent_runtime_adapter.review_agent_output(
            agent_task_id=agent_task_id,
            output_id=output_id,
            reviewer=reviewer,
            decision=decision,
        )
        return {"ok": adapter_result["ok"], "adapter_contract": {"agent_runtime": adapter_result}, "side_effect_safety": _automation_side_effect_safety()}

    __call__ = execute
