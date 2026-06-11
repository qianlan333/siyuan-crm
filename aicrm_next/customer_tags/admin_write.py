from __future__ import annotations

import os
from typing import Any

from aicrm_next.integration_gateway.wecom_tag_live_gateway import build_wecom_tag_live_gateway
from aicrm_next.platform_foundation.audit_ledger import InMemoryAuditLedger
from aicrm_next.platform_foundation.command_bus import Command, CommandBus, CommandContext, CommandResult
from aicrm_next.platform_foundation.side_effects import InMemorySideEffectPlanRepository, SideEffectPlan
from aicrm_next.shared.runtime import production_data_ready, production_environment

from .commands import (
    CreateWeComTagCommand,
    CreateWeComTagGroupCommand,
    DeleteWeComTagCommand,
    DeleteWeComTagGroupCommand,
    SyncWeComTagCatalogCommand,
    UpdateWeComTagCommand,
    UpdateWeComTagGroupCommand,
    WeComTagWriteCommand,
)
from .sync_service import execute_wecom_tag_catalog_sync
from .write_repo import WeComTagWriteRepository


class WeComTagWriteInputError(ValueError):
    pass


class WeComTagWriteNotFoundError(LookupError):
    pass


class WeComTagWriteProductionUnavailableError(RuntimeError):
    pass


_repo = WeComTagWriteRepository()
_audit_ledger = InMemoryAuditLedger()
_side_effect_plans = InMemorySideEffectPlanRepository()


def _audit_hook(command: Command, result: CommandResult) -> None:
    real_external_call_executed = bool(result.payload.get("real_external_call_executed") or False)
    sync_executed = bool(result.payload.get("sync_executed") or False)
    _audit_ledger.record_event(
        event_type=f"{command.command_name}.{result.status}",
        actor_id=result.actor_id,
        actor_type=result.actor_type,
        target_type=_target_type(command.command_name),
        target_id=str(command.payload.get("target_id") or result.payload.get("target_id") or ""),
        source_route=result.source_route,
        command_id=result.command_id,
        trace_id=result.trace_id,
        payload={
            "status": result.status,
            "write_model_status": result.payload.get("write_model_status") or "",
            "fallback_used": False,
            "real_external_call_executed": real_external_call_executed,
            "sync_executed": sync_executed,
        },
    )


_command_bus = CommandBus(audit_hook=_audit_hook)


def reset_wecom_tag_write_fixture_state() -> None:
    global _repo, _audit_ledger, _side_effect_plans, _command_bus
    _repo = WeComTagWriteRepository()
    _audit_ledger = InMemoryAuditLedger()
    _side_effect_plans = InMemorySideEffectPlanRepository()
    _command_bus = CommandBus(audit_hook=_audit_hook)
    _register_handlers()


def get_wecom_tag_write_audit_events() -> list[dict[str, Any]]:
    return [event.to_dict() for event in _audit_ledger.list_events()]


def get_wecom_tag_write_side_effect_plans() -> list[dict[str, Any]]:
    return [_plan_response(plan) for plan in _side_effect_plans.list_plans()]


def get_wecom_tag_write_projection_events() -> list[dict[str, Any]]:
    return _repo.list_writes()


def execute_wecom_tag_write(command: WeComTagWriteCommand) -> dict[str, Any]:
    _validate_command(command)
    if production_environment() and not production_data_ready():
        raise WeComTagWriteProductionUnavailableError("wecom tag write model is not production-ready for command execution")
    if production_data_ready() and not wecom_tag_live_crud_enabled():
        raise WeComTagWriteProductionUnavailableError("wecom tag write model is not production-ready for command execution")

    platform_command = Command(
        command_name=command.command_name,
        payload=command.to_payload(),
        command_id=command.command_id,
        idempotency_key=command.idempotency_key,
        context=CommandContext(
            actor_id=command.actor_id,
            actor_type=command.actor_type,
            trace_id=command.trace_id,
            source_route=command.source_route,
            dry_run=command.dry_run,
        ),
    )
    result = _command_bus.execute(platform_command)
    if result.status == "failed":
        if "not found" in result.error:
            raise WeComTagWriteNotFoundError(result.error)
        if "is required" in result.error or "already exists" in result.error:
            raise WeComTagWriteInputError(result.error)
        raise WeComTagWriteProductionUnavailableError(result.error)

    payload = dict(result.payload)
    payload.setdefault("write_model_status", "local_projection_updated")
    return _response_from_result(result, payload)


def _register_handlers() -> None:
    _command_bus.register(CreateWeComTagCommand.command_name, _handle_create_tag)
    _command_bus.register(UpdateWeComTagCommand.command_name, _handle_update_tag)
    _command_bus.register(DeleteWeComTagCommand.command_name, _handle_delete_tag)
    _command_bus.register(CreateWeComTagGroupCommand.command_name, _handle_create_group)
    _command_bus.register(UpdateWeComTagGroupCommand.command_name, _handle_update_group)
    _command_bus.register(DeleteWeComTagGroupCommand.command_name, _handle_delete_group)
    _command_bus.register(SyncWeComTagCatalogCommand.command_name, _handle_sync_catalog)


def _validate_command(command: WeComTagWriteCommand) -> None:
    if not command.command_id.strip():
        raise WeComTagWriteInputError("command_id is required")
    if not command.source_route.strip():
        raise WeComTagWriteInputError("source_route is required")
    if not command.actor_id.strip():
        raise WeComTagWriteInputError("actor_id is required")
    if command.command_name in {
        UpdateWeComTagCommand.command_name,
        DeleteWeComTagCommand.command_name,
        UpdateWeComTagGroupCommand.command_name,
        DeleteWeComTagGroupCommand.command_name,
    } and not command.target_id.strip():
        raise WeComTagWriteInputError("target_id is required")


def _handle_create_tag(command: Command) -> dict[str, Any]:
    requested = dict(command.payload.get("payload") or {})
    if _live_crud_should_execute():
        return _handle_live_create_tag(command, requested)
    if not str(requested.get("group_id") or "").strip():
        raise ValueError("group_id is required")
    tag = _repo.create_tag(
        command_id=command.command_id,
        group_id=str(requested.get("group_id") or "").strip(),
        tag_name=str(requested.get("tag_name") or "").strip(),
    )
    plan = _create_side_effect_plan(command=command, effect_type="wecom.tag.create", target_type="wecom_tag", target_id=tag["tag_id"], payload_summary={"group_id": tag["group_id"], "tag_name": tag["tag_name"]}, risk_level="medium")
    return {"target_id": tag["tag_id"], "tag": tag, "write_model_status": "local_projection_updated", "local_projection_updated": True, "side_effect_plan": _plan_response(plan)}


def _handle_update_tag(command: Command) -> dict[str, Any]:
    requested = dict(command.payload.get("payload") or {})
    if _live_crud_should_execute():
        return _handle_live_update_tag(command, requested)
    tag = _repo.update_tag(command_id=command.command_id, tag_id=str(command.payload.get("target_id") or ""), tag_name=str(requested.get("tag_name") or "").strip())
    plan = _create_side_effect_plan(command=command, effect_type="wecom.tag.update", target_type="wecom_tag", target_id=tag["tag_id"], payload_summary={"tag_id": tag["tag_id"], "tag_name": tag["tag_name"]}, risk_level="medium")
    return {"target_id": tag["tag_id"], "tag": tag, "write_model_status": "local_projection_updated", "local_projection_updated": True, "side_effect_plan": _plan_response(plan)}


def _handle_delete_tag(command: Command) -> dict[str, Any]:
    if _live_crud_should_execute():
        return _handle_live_delete_tag(command)
    tag = _repo.delete_tag(command_id=command.command_id, tag_id=str(command.payload.get("target_id") or ""))
    plan = _create_side_effect_plan(command=command, effect_type="wecom.tag.delete", target_type="wecom_tag", target_id=tag["tag_id"], payload_summary={"tag_id": tag["tag_id"], "group_id": tag["group_id"]}, risk_level="high")
    return {"target_id": tag["tag_id"], "tag": tag, "deleted": True, "write_model_status": "local_projection_updated", "local_projection_updated": True, "side_effect_plan": _plan_response(plan)}


def _handle_create_group(command: Command) -> dict[str, Any]:
    requested = dict(command.payload.get("payload") or {})
    if _live_crud_should_execute():
        return _handle_live_create_group(command, requested)
    result = _repo.create_group(
        command_id=command.command_id,
        group_name=str(requested.get("group_name") or "").strip(),
        first_tag_name=str(requested.get("first_tag_name") or "").strip(),
    )
    group = result["group"]
    plan = _create_side_effect_plan(command=command, effect_type="wecom.tag_group.create", target_type="wecom_tag_group", target_id=group["group_id"], payload_summary={"group_name": group["group_name"], "first_tag_requested": bool(requested.get("first_tag_name"))}, risk_level="medium")
    return {"target_id": group["group_id"], "group": group, "tags": result.get("tags") or [], "write_model_status": "local_projection_updated", "local_projection_updated": True, "side_effect_plan": _plan_response(plan)}


def _handle_update_group(command: Command) -> dict[str, Any]:
    requested = dict(command.payload.get("payload") or {})
    if _live_crud_should_execute():
        return _handle_live_update_group(command, requested)
    group = _repo.update_group(command_id=command.command_id, group_id=str(command.payload.get("target_id") or ""), group_name=str(requested.get("group_name") or "").strip())
    plan = _create_side_effect_plan(command=command, effect_type="wecom.tag_group.update", target_type="wecom_tag_group", target_id=group["group_id"], payload_summary={"group_id": group["group_id"], "group_name": group["group_name"]}, risk_level="medium")
    return {"target_id": group["group_id"], "group": group, "write_model_status": "local_projection_updated", "local_projection_updated": True, "side_effect_plan": _plan_response(plan)}


def _handle_delete_group(command: Command) -> dict[str, Any]:
    if _live_crud_should_execute():
        return _handle_live_delete_group(command)
    result = _repo.delete_group(command_id=command.command_id, group_id=str(command.payload.get("target_id") or ""))
    group = result["group"]
    plan = _create_side_effect_plan(command=command, effect_type="wecom.tag_group.delete", target_type="wecom_tag_group", target_id=group["group_id"], payload_summary={"group_id": group["group_id"], "deleted_tag_count": len(result.get("deleted_tag_ids") or [])}, risk_level="high")
    return {"target_id": group["group_id"], "group": group, "deleted": True, "deleted_tag_ids": result.get("deleted_tag_ids") or [], "write_model_status": "local_projection_updated", "local_projection_updated": True, "side_effect_plan": _plan_response(plan)}


def _handle_sync_catalog(command: Command) -> dict[str, Any]:
    sync = _repo.sync_catalog(command_id=command.command_id)
    plan = _create_side_effect_plan(command=command, effect_type="wecom.tag.sync", target_type="wecom_tag_catalog", target_id="catalog", payload_summary={"operation": "sync_catalog", "local_only": True}, risk_level="high")
    return {"target_id": "catalog", "sync": sync, "write_model_status": "local_projection_updated", "local_projection_updated": True, "sync_executed": False, "side_effect_plan": _plan_response(plan)}


def wecom_tag_live_crud_enabled() -> bool:
    return _env_flag("AICRM_WECOM_TAG_CRUD_LIVE_ENABLED")


def _env_flag(name: str, *, default: bool = False) -> bool:
    value = str(os.getenv(name, "") or "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


def _live_crud_should_execute() -> bool:
    return production_data_ready() and wecom_tag_live_crud_enabled()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _live_gateway() -> Any:
    return build_wecom_tag_live_gateway()


def _refresh_live_catalog(*, gateway: Any, operator: str) -> dict[str, Any]:
    return execute_wecom_tag_catalog_sync(operator=operator, gateway=gateway)


def _live_response(
    *,
    command: Command,
    target_id: str,
    effect_type: str,
    target_type: str,
    wecom_result: dict[str, Any],
    catalog_refresh: dict[str, Any],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload_summary = {
        "target_id": target_id,
        "wecom_errcode": wecom_result.get("errcode"),
        "sync_run_id": catalog_refresh.get("sync_run_id"),
    }
    plan = _side_effect_plans.create_plan(
        command_id=command.command_id,
        effect_type=effect_type,
        adapter_name="wecom_tag_admin",
        adapter_mode="real_live",
        target_type=target_type,
        target_id=target_id,
        payload={
            "payload_summary": payload_summary,
            "real_external_call_executed": True,
            "wecom_api_called": True,
        },
        status="executed",
        risk_level="high" if effect_type.endswith(".delete") else "medium",
        requires_approval=False,
    )
    response = {
        "target_id": target_id,
        "write_model_status": "live_wecom_executed",
        "local_projection_updated": False,
        "real_external_call_executed": True,
        "wecom_api_called": True,
        "sync_executed": True,
        "local_only": False,
        "adapter_mode": "real_live",
        "wecom_result": wecom_result,
        "catalog_refresh": catalog_refresh,
        "side_effect_plan": _plan_response(plan),
    }
    response.update(extra or {})
    return response


def _created_tag_group_id(payload: dict[str, Any]) -> str:
    groups = _tag_group_items(payload)
    if groups:
        group = dict(groups[0] or {})
        return _text(group.get("group_id") or group.get("id"))
    return _text(payload.get("group_id") or payload.get("id"))


def _created_tag_id(payload: dict[str, Any]) -> str:
    groups = _tag_group_items(payload)
    if groups:
        group = dict(groups[0] or {})
        tags = _tag_items(group)
        if tags:
            tag = dict(tags[0] or {})
            return _text(tag.get("id") or tag.get("tag_id"))
    tags = _tag_items(payload)
    if tags:
        tag = dict(tags[0] or {})
        return _text(tag.get("id") or tag.get("tag_id"))
    return _text(payload.get("tag_id") or payload.get("id"))


def _tag_group_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    value = payload.get("tag_group")
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, dict)]
    return []


def _tag_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    value = payload.get("tag")
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, dict)]
    return []


def _handle_live_create_tag(command: Command, requested: dict[str, Any]) -> dict[str, Any]:
    group_id = _text(requested.get("group_id"))
    group_name = _text(requested.get("group_name"))
    tag_name = _text(requested.get("tag_name"))
    if not tag_name:
        raise ValueError("tag_name is required")
    if not group_id and not group_name:
        raise ValueError("group_id is required")
    gateway = _live_gateway()
    wecom_result = gateway.create_tag_live(group_id=group_id, group_name=group_name, tag_name=tag_name)
    refresh = _refresh_live_catalog(gateway=gateway, operator=command.context.actor_id)
    tag_id = _created_tag_id(wecom_result) or _text(command.payload.get("target_id")) or tag_name
    return _live_response(
        command=command,
        target_id=tag_id,
        effect_type="wecom.tag.create",
        target_type="wecom_tag",
        wecom_result=wecom_result,
        catalog_refresh=refresh,
        extra={"tag": {"tag_id": tag_id, "tag_name": tag_name, "group_id": group_id, "group_name": group_name}},
    )


def _handle_live_update_tag(command: Command, requested: dict[str, Any]) -> dict[str, Any]:
    tag_id = _text(command.payload.get("target_id"))
    tag_name = _text(requested.get("tag_name"))
    if not tag_id:
        raise ValueError("target_id is required")
    if not tag_name:
        raise ValueError("tag_name is required")
    gateway = _live_gateway()
    wecom_result = gateway.update_tag_live(tag_id=tag_id, tag_name=tag_name)
    refresh = _refresh_live_catalog(gateway=gateway, operator=command.context.actor_id)
    return _live_response(
        command=command,
        target_id=tag_id,
        effect_type="wecom.tag.update",
        target_type="wecom_tag",
        wecom_result=wecom_result,
        catalog_refresh=refresh,
        extra={"tag": {"tag_id": tag_id, "tag_name": tag_name}},
    )


def _handle_live_delete_tag(command: Command) -> dict[str, Any]:
    tag_id = _text(command.payload.get("target_id"))
    if not tag_id:
        raise ValueError("target_id is required")
    gateway = _live_gateway()
    wecom_result = gateway.delete_tag_live(tag_id=tag_id)
    refresh = _refresh_live_catalog(gateway=gateway, operator=command.context.actor_id)
    return _live_response(
        command=command,
        target_id=tag_id,
        effect_type="wecom.tag.delete",
        target_type="wecom_tag",
        wecom_result=wecom_result,
        catalog_refresh=refresh,
        extra={"tag": {"tag_id": tag_id}, "deleted": True},
    )


def _handle_live_create_group(command: Command, requested: dict[str, Any]) -> dict[str, Any]:
    group_name = _text(requested.get("group_name"))
    first_tag_name = _text(requested.get("first_tag_name"))
    tag_names = [_text(item) for item in list(requested.get("tag_names") or [])]
    tag_names = [item for item in tag_names if item]
    if first_tag_name and first_tag_name not in tag_names:
        tag_names.insert(0, first_tag_name)
    if not group_name:
        raise ValueError("group_name is required")
    if not tag_names:
        raise ValueError("first_tag_name is required")
    gateway = _live_gateway()
    wecom_result = gateway.create_tag_group_live(group_name=group_name, tag_names=tag_names)
    refresh = _refresh_live_catalog(gateway=gateway, operator=command.context.actor_id)
    group_id = _created_tag_group_id(wecom_result) or group_name
    return _live_response(
        command=command,
        target_id=group_id,
        effect_type="wecom.tag_group.create",
        target_type="wecom_tag_group",
        wecom_result=wecom_result,
        catalog_refresh=refresh,
        extra={"group": {"group_id": group_id, "group_name": group_name}, "tags": [{"tag_name": item} for item in tag_names]},
    )


def _handle_live_update_group(command: Command, requested: dict[str, Any]) -> dict[str, Any]:
    group_id = _text(command.payload.get("target_id"))
    group_name = _text(requested.get("group_name"))
    if not group_id:
        raise ValueError("target_id is required")
    if not group_name:
        raise ValueError("group_name is required")
    gateway = _live_gateway()
    wecom_result = gateway.update_tag_group_live(group_id=group_id, group_name=group_name)
    refresh = _refresh_live_catalog(gateway=gateway, operator=command.context.actor_id)
    return _live_response(
        command=command,
        target_id=group_id,
        effect_type="wecom.tag_group.update",
        target_type="wecom_tag_group",
        wecom_result=wecom_result,
        catalog_refresh=refresh,
        extra={"group": {"group_id": group_id, "group_name": group_name}},
    )


def _handle_live_delete_group(command: Command) -> dict[str, Any]:
    group_id = _text(command.payload.get("target_id"))
    if not group_id:
        raise ValueError("target_id is required")
    gateway = _live_gateway()
    wecom_result = gateway.delete_tag_group_live(group_id=group_id)
    refresh = _refresh_live_catalog(gateway=gateway, operator=command.context.actor_id)
    return _live_response(
        command=command,
        target_id=group_id,
        effect_type="wecom.tag_group.delete",
        target_type="wecom_tag_group",
        wecom_result=wecom_result,
        catalog_refresh=refresh,
        extra={"group": {"group_id": group_id}, "deleted": True},
    )


def _create_side_effect_plan(
    *,
    command: Command,
    effect_type: str,
    target_type: str,
    target_id: str,
    payload_summary: dict[str, Any],
    risk_level: str,
) -> SideEffectPlan:
    return _side_effect_plans.create_plan(
        command_id=command.command_id,
        effect_type=effect_type,
        adapter_name="wecom_tag_admin",
        adapter_mode="real_blocked",
        target_type=target_type,
        target_id=target_id,
        payload={
            "payload_summary": payload_summary,
            "real_external_call_executed": False,
        },
        status="planned",
        risk_level=risk_level,
        requires_approval=True,
    )


def _plan_response(plan: SideEffectPlan) -> dict[str, Any]:
    payload = plan.to_dict()
    summary = dict(payload.pop("payload") or {})
    payload["payload_summary"] = summary.get("payload_summary") or {}
    payload["real_external_call_executed"] = bool(summary.get("real_external_call_executed") or False)
    payload["wecom_api_called"] = bool(summary.get("wecom_api_called") or False)
    return payload


def _response_from_result(result: CommandResult, payload: dict[str, Any]) -> dict[str, Any]:
    response = {
        "ok": result.status in {"completed", "dry_run"},
        "command_id": result.command_id,
        "command_name": result.command_name,
        "idempotency_key": result.idempotency_key,
        "source_status": "next_command",
        "write_model_status": payload.get("write_model_status") or "local_projection_updated",
        "route_owner": "ai_crm_next",
        "fallback_used": False,
        "real_external_call_executed": bool(payload.get("real_external_call_executed") or False),
        "sync_executed": bool(payload.get("sync_executed") or False),
        "local_only": bool(payload.get("local_only", True)),
        "audit_recorded": True,
        "command_result_status": result.status,
        "target_id": payload.get("target_id") or "",
    }
    response.update(payload)
    return response


def _target_type(command_name: str) -> str:
    if "tag_group" in command_name:
        return "wecom_tag_group"
    if command_name.endswith(".sync"):
        return "wecom_tag_catalog"
    return "wecom_tag"


reset_wecom_tag_write_fixture_state()
