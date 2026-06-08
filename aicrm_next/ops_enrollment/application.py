from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from aicrm_next.integration_gateway.user_ops_adapters import (
    UserOpsBatchSendGateway,
    UserOpsDeferredJobGateway,
    UserOpsDndWriteGateway,
    WeComMessageDispatchAdapter,
    build_user_ops_batch_send_gateway,
    build_user_ops_deferred_job_gateway,
    build_user_ops_dnd_gateway,
    build_wecom_message_dispatch_adapter,
)
from aicrm_next.platform_foundation.audit_ledger import InMemoryAuditLedger
from aicrm_next.platform_foundation.command_bus import Command, CommandBus, CommandContext, CommandResult
from aicrm_next.platform_foundation.side_effects import InMemorySideEffectPlanRepository, SideEffectPlan
from aicrm_next.shared.config import get_settings
from aicrm_next.shared.errors import ContractError, NotFoundError
from aicrm_next.shared.runtime import fixture_mode
from aicrm_next.shared.typing import JsonDict

from .dto import BatchSendRequest, BroadcastPreviewRequest, DoNotDisturbRequest, ExportPreviewRequest, UserOpsListRequest
from .repo import UserOpsRepository, build_user_ops_repository
from .user_ops import apply_filters, build_overview_cards, normalize_filters, resolve_batch_targets

_REPO: UserOpsRepository | None = None
_audit_ledger = InMemoryAuditLedger()
_side_effect_plans = InMemorySideEffectPlanRepository()
LOGGER = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _filter_options(rows: list[JsonDict]) -> JsonDict:
    return {
        "class_term_no": sorted({row["class_term_no"] for row in rows if row.get("class_term_no")}),
        "owner_userid": sorted({row["owner_userid"] for row in rows if row.get("owner_userid")}),
        "tag": sorted({str(tag) for row in rows for tag in (row.get("tags") or []) if tag}),
        "wecom_status": ["all", "added", "not_added"],
        "mobile_binding_status": ["all", "bound", "unbound"],
        "activation_bucket": ["all", "activated", "not_activated", "pending_input"],
    }


def reset_user_ops_fixture_state() -> None:
    global _REPO, _audit_ledger, _side_effect_plans, _command_bus
    if not fixture_mode() or not _user_ops_repo_cache_enabled():
        return
    if _REPO is None:
        _REPO = build_user_ops_repository()
    _REPO.reset()
    _audit_ledger = InMemoryAuditLedger()
    _side_effect_plans = InMemorySideEffectPlanRepository()
    _command_bus = CommandBus(audit_hook=_audit_hook)
    _register_preview_handlers()


def _user_ops_repo_cache_enabled() -> bool:
    backend = os.getenv("USER_OPS_REPO_BACKEND", get_settings().user_ops_repo_backend).strip().lower()
    return backend not in {"sql", "sqlalchemy", "postgres", "postgresql"}


def _default_repo() -> UserOpsRepository:
    global _REPO
    if not _user_ops_repo_cache_enabled():
        return build_user_ops_repository()
    if _REPO is None:
        _REPO = build_user_ops_repository()
    return _REPO


def _close_repository(repo: UserOpsRepository | None) -> None:
    close = getattr(repo, "close", None)
    if not callable(close):
        return
    try:
        close()
    except Exception:
        LOGGER.warning("failed to close user ops repository", exc_info=True)


def _should_close_repo(repo_owner: UserOpsRepository | None) -> bool:
    return repo_owner is None


def _readonly_meta() -> JsonDict:
    return {
        "route_owner": "ai_crm_next",
        "fallback_used": False,
        "runtime_owner": "next_native",
        "real_external_call_executed": False,
    }


def _media_refs_from_batch_request(request: BatchSendRequest) -> list[JsonDict]:
    refs: list[JsonDict] = []
    refs.extend({"kind": "image", "index": index} for index, _ in enumerate(request.images))
    refs.extend({"kind": "attachment", "index": index} for index, _ in enumerate(request.attachments))
    return refs


def _user_ops_side_effect_safety() -> JsonDict:
    return {
        "user_ops_dnd_mode": build_user_ops_dnd_gateway().mode,
        "user_ops_batch_send_mode": build_user_ops_batch_send_gateway().mode,
        "wecom_dispatch_mode": build_wecom_message_dispatch_adapter().mode,
        "user_ops_deferred_jobs_mode": build_user_ops_deferred_job_gateway().mode,
        "real_dnd_write_executed": False,
        "real_batch_send_executed": False,
        "real_wecom_dispatch_executed": False,
        "real_deferred_jobs_executed": False,
        "real_wecom_media_upload_executed": False,
        "side_effect_executed": False,
    }


def _audit_hook(command: Command, result: CommandResult) -> None:
    _audit_ledger.record_event(
        event_type=f"{command.command_name}.{result.status}",
        actor_id=result.actor_id,
        actor_type=result.actor_type,
        target_type="user_ops",
        target_id=str(command.payload.get("target_id") or ""),
        source_route=result.source_route,
        command_id=result.command_id,
        trace_id=result.trace_id,
        payload={
            "status": result.status,
            "preview_only": True,
            "real_external_call_executed": False,
        },
    )


_command_bus = CommandBus(audit_hook=_audit_hook)


def _plan_response(plan: SideEffectPlan) -> JsonDict:
    payload = plan.to_dict()
    summary = dict(payload.pop("payload") or {})
    payload["payload_summary"] = summary.get("payload_summary") or {}
    payload["next_step"] = summary.get("next_step") or "requires_approval"
    payload["real_external_call_executed"] = False
    return payload


def _create_preview_plan(
    *,
    command: Command,
    effect_type: str,
    adapter_name: str,
    target_id: str,
    payload_summary: JsonDict,
    risk_level: str = "medium",
) -> JsonDict:
    plan = _side_effect_plans.create_plan(
        command_id=command.command_id,
        effect_type=effect_type,
        adapter_name=adapter_name,
        adapter_mode="real_blocked",
        target_type="user_ops_preview",
        target_id=target_id,
        payload={"payload_summary": payload_summary, "next_step": "requires_approval", "real_external_call_executed": False},
        status="planned",
        risk_level=risk_level,
        requires_approval=True,
    )
    return _plan_response(plan)


def _filters_are_empty(filters: JsonDict) -> bool:
    return not any(str(value or "").strip() for value in filters.values())


def _register_preview_handlers() -> None:
    _command_bus.register("user_ops.broadcast.preview", _handle_broadcast_preview)
    _command_bus.register("user_ops.export.preview", _handle_export_preview)


def get_user_ops_audit_events() -> list[JsonDict]:
    return [event.to_dict() for event in _audit_ledger.list_events()]


def get_user_ops_side_effect_plans() -> list[JsonDict]:
    return [_plan_response(plan) for plan in _side_effect_plans.list_plans()]


def _message_preview(text: str, limit: int = 120) -> str:
    text = str(text or "").strip()
    return text if len(text) <= limit else text[:limit] + "..."


def _mask_value(field: str, value: object) -> str:
    text = str(value or "")
    if not text:
        return ""
    if field == "mobile":
        return f"{text[:3]}****{text[-4:]}" if len(text) >= 7 else "***"
    if field == "external_userid":
        return f"{text[:4]}***{text[-3:]}" if len(text) >= 8 else "***"
    if field in {"customer_name", "name"}:
        return text[0] + "*" if text else ""
    return "***" if text else ""


def _customer_summary(row: JsonDict) -> JsonDict:
    return {
        "id": row["id"],
        "external_userid": row["external_userid"],
        "customer_name": row["customer_name"],
        "mobile_masked": _mask_value("mobile", row.get("mobile")),
        "owner_userid": row["owner_userid"],
        "owner_display_name": row.get("owner_display_name") or "",
        "class_term_no": row.get("class_term_no") or "",
        "class_term_label": row.get("class_term_label") or "",
        "activation_bucket": row.get("activation_bucket") or "",
        "activation_bucket_label": row.get("activation_bucket_label") or "",
        "is_added_wecom": bool(row.get("is_added_wecom")),
        "is_mobile_bound": bool(row.get("is_mobile_bound")),
        "do_not_disturb": bool(row.get("do_not_disturb")),
        "tags": list(row.get("tags") or []),
        "updated_at": row.get("updated_at") or "",
    }


def _timeline_for_customer(row: JsonDict) -> list[JsonDict]:
    events = [
        {
            "event_id": f"user_ops_created_{row['id']}",
            "event_type": "lead_pool.created",
            "title": "进入 User Ops 池",
            "occurred_at": row.get("created_at") or "",
            "source": row.get("source_type") or "lead_pool",
        },
        {
            "event_id": f"user_ops_activation_{row['id']}",
            "event_type": "activation.status",
            "title": row.get("activation_bucket_label") or row.get("activation_bucket") or "激活状态",
            "occurred_at": row.get("updated_at") or "",
            "source": "ops_projection",
        },
    ]
    if row.get("do_not_disturb"):
        events.append(
            {
                "event_id": f"user_ops_dnd_{row['id']}",
                "event_type": "do_not_disturb.active",
                "title": "免打扰规则生效",
                "occurred_at": row.get("updated_at") or "",
                "source": "ops_projection",
            }
        )
    return events


def _find_projected_row(repo: UserOpsRepository, *, external_userid: str) -> JsonDict | None:
    for row in repo.list_rows():
        if str(row.get("external_userid") or "") == external_userid:
            return row
    return None


class GetUserOpsOverviewQuery:
    def __init__(self, repo: UserOpsRepository | None = None) -> None:
        self._repo = repo

    def execute(self, request: UserOpsListRequest) -> JsonDict:
        repo = self._repo or _default_repo()
        try:
            normalized_filters = normalize_filters(request.filters)
            base_rows = repo.list_rows()
            rows = apply_filters(base_rows, normalized_filters)
            return {
                "ok": True,
                **_readonly_meta(),
                "filters": normalized_filters.model_dump(),
                "cards": build_overview_cards(rows),
                "metrics": {"lead_pool_total_count": len(base_rows), "filtered_total": len(rows)},
                "generated_at": _now_iso(),
                "class_term_options": sorted({row["class_term_no"] for row in base_rows if row.get("class_term_no")}),
            }
        finally:
            if _should_close_repo(self._repo):
                _close_repository(repo)

    __call__ = execute


class GetUserOpsCardsQuery:
    def __init__(self, repo: UserOpsRepository | None = None) -> None:
        self._repo = repo

    def execute(self, request: UserOpsListRequest) -> JsonDict:
        repo = self._repo or _default_repo()
        try:
            normalized_filters = normalize_filters(request.filters)
            rows = apply_filters(repo.list_rows(), normalized_filters)
            return {
                "ok": True,
                **_readonly_meta(),
                "cards": build_overview_cards(rows),
                "filters": normalized_filters.model_dump(),
                "generated_at": _now_iso(),
            }
        finally:
            if _should_close_repo(self._repo):
                _close_repository(repo)

    __call__ = execute


class GetUserOpsFilterOptionsQuery:
    def __init__(self, repo: UserOpsRepository | None = None) -> None:
        self._repo = repo

    def execute(self) -> JsonDict:
        repo = self._repo or _default_repo()
        try:
            rows = repo.list_rows()
            return {
                "ok": True,
                **_readonly_meta(),
                "filter_options": _filter_options(rows),
                "generated_at": _now_iso(),
            }
        finally:
            if _should_close_repo(self._repo):
                _close_repository(repo)

    __call__ = execute


class ListLeadPoolQuery:
    def __init__(self, repo: UserOpsRepository | None = None) -> None:
        self._repo = repo

    def execute(self, request: UserOpsListRequest) -> JsonDict:
        repo = self._repo or _default_repo()
        try:
            normalized_filters = normalize_filters(request.filters)
            base_rows = repo.list_rows()
            rows = apply_filters(base_rows, normalized_filters)
            total = len(rows)
            page = rows[request.offset : request.offset + request.limit]
            return {
                "ok": True,
                **_readonly_meta(),
                "items": page,
                "total": total,
                "count": len(page),
                "limit": request.limit,
                "offset": request.offset,
                "filters": normalized_filters.model_dump(),
                "filter_options": _filter_options(base_rows),
                "meta": {"source": "aicrm_next", "generated_at": _now_iso()},
            }
        finally:
            if _should_close_repo(self._repo):
                _close_repository(repo)

    __call__ = execute


class ListUserOpsCustomersQuery(ListLeadPoolQuery):
    pass


class GetUserOpsCustomerQuery:
    def __init__(self, repo: UserOpsRepository | None = None) -> None:
        self._repo = repo

    def execute(self, external_userid: str) -> JsonDict:
        repo = self._repo or _default_repo()
        try:
            row = _find_projected_row(repo, external_userid=external_userid)
            if row is None:
                raise NotFoundError("user ops customer not found")
            projected = _customer_summary(row)
            return {
                "ok": True,
                **_readonly_meta(),
                "customer": projected,
                "profile": {
                    "external_userid": projected["external_userid"],
                    "customer_name": projected["customer_name"],
                    "owner_userid": projected["owner_userid"],
                    "mobile_masked": projected["mobile_masked"],
                },
                "drawer": {
                    "sections": [
                        {"key": "profile", "title": "客户资料", "items": projected},
                        {"key": "ops", "title": "运营状态", "items": {"activation_bucket": projected["activation_bucket"], "do_not_disturb": projected["do_not_disturb"]}},
                    ]
                },
            }
        finally:
            if _should_close_repo(self._repo):
                _close_repository(repo)

    __call__ = execute


class GetUserOpsCustomerTimelineQuery:
    def __init__(self, repo: UserOpsRepository | None = None) -> None:
        self._repo = repo

    def execute(self, external_userid: str, *, limit: int = 20, offset: int = 0) -> JsonDict:
        repo = self._repo or _default_repo()
        try:
            row = _find_projected_row(repo, external_userid=external_userid)
            if row is None:
                raise NotFoundError("user ops customer not found")
            events = _timeline_for_customer(row)
            page = events[offset : offset + limit]
            return {
                "ok": True,
                **_readonly_meta(),
                "external_userid": external_userid,
                "items": page,
                "timeline": page,
                "total": len(events),
                "count": len(page),
                "limit": limit,
                "offset": offset,
            }
        finally:
            if _should_close_repo(self._repo):
                _close_repository(repo)

    __call__ = execute


class PreviewUserOpsBatchSendCommand:
    def __init__(
        self,
        repo: UserOpsRepository | None = None,
        batch_gateway: UserOpsBatchSendGateway | None = None,
    ) -> None:
        self._repo = repo
        self._batch_gateway = batch_gateway or build_user_ops_batch_send_gateway()

    def execute(self, request: BatchSendRequest) -> JsonDict:
        repo = self._repo or _default_repo()
        try:
            request.filters = normalize_filters(request.filters)
            rows = apply_filters(repo.list_rows(), request.filters)
            preview = resolve_batch_targets(rows, request)
            gateway_result = self._batch_gateway.build_batch_send_preview(
                selection_mode=request.selection_mode,
                filters=preview["filters"],
                selected_ids=request.selected_ids,
                excluded_ids=request.excluded_ids,
                content=request.content,
                targets=preview["final_targets"],
                owner_buckets=preview["owner_buckets"],
                include_do_not_disturb=preview["include_do_not_disturb"],
                media_refs=_media_refs_from_batch_request(request),
            )
            if not gateway_result["ok"]:
                raise ContractError(gateway_result["error_message"] or gateway_result["error_code"])
            return {
                "ok": True,
                **preview,
                "side_effect_safety": _user_ops_side_effect_safety(),
                "adapter_contract": {
                    "batch_send": gateway_result,
                },
            }
        finally:
            if _should_close_repo(self._repo):
                _close_repository(repo)

    __call__ = execute


class PreviewUserOpsBroadcastCommand:
    command_name = "user_ops.broadcast.preview"

    def __init__(self, repo: UserOpsRepository | None = None) -> None:
        self._repo = repo

    def execute(self, request: BroadcastPreviewRequest, *, idempotency_key: str = "") -> JsonDict:
        if self._repo is not None:
            return _build_broadcast_preview_response(
                Command(
                    command_name=self.command_name,
                    payload={"request": request.model_dump(), "target_id": "broadcast_preview"},
                    idempotency_key=idempotency_key,
                    context=CommandContext(
                        actor_id=request.operator,
                        actor_type="admin",
                        source_route="/api/admin/user-ops/broadcast/preview",
                    ),
                ),
                request=request,
                repo=self._repo,
            )
        command = Command(
            command_name=self.command_name,
            payload={"request": request.model_dump(), "target_id": "broadcast_preview"},
            idempotency_key=idempotency_key,
            context=CommandContext(
                actor_id=request.operator,
                actor_type="admin",
                source_route="/api/admin/user-ops/broadcast/preview",
            ),
        )
        result = _command_bus.execute(command)
        if result.status == "failed":
            raise ContractError(result.error)
        return dict(result.payload)

    __call__ = execute


class PreviewUserOpsExportCommand:
    command_name = "user_ops.export.preview"

    def __init__(self, repo: UserOpsRepository | None = None) -> None:
        self._repo = repo

    def execute(self, request: ExportPreviewRequest, *, idempotency_key: str = "") -> JsonDict:
        if self._repo is not None:
            return _build_export_preview_response(
                Command(
                    command_name=self.command_name,
                    payload={"request": request.model_dump(), "target_id": "export_preview"},
                    idempotency_key=idempotency_key,
                    context=CommandContext(
                        actor_id=request.operator,
                        actor_type="admin",
                        source_route="/api/admin/user-ops/export/preview",
                    ),
                ),
                request=request,
                repo=self._repo,
            )
        command = Command(
            command_name=self.command_name,
            payload={"request": request.model_dump(), "target_id": "export_preview"},
            idempotency_key=idempotency_key,
            context=CommandContext(
                actor_id=request.operator,
                actor_type="admin",
                source_route="/api/admin/user-ops/export/preview",
            ),
        )
        result = _command_bus.execute(command)
        if result.status == "failed":
            raise ContractError(result.error)
        return dict(result.payload)

    __call__ = execute


def _build_broadcast_preview_response(command: Command, *, request: BroadcastPreviewRequest, repo: UserOpsRepository) -> JsonDict:
    filters = normalize_filters(request.filters)
    filter_payload = filters.model_dump()
    is_controlled_default = not request.model_fields_set or (_filters_are_empty(filter_payload) and not request.message.text.strip())
    rows = apply_filters(repo.list_rows(), filters)
    batch_request = BatchSendRequest(
        selection_mode=request.selection_mode,
        filters=filters,
        selected_ids=request.selected_ids,
        excluded_ids=request.excluded_ids,
        content=request.message.text,
        include_do_not_disturb=request.include_do_not_disturb,
        operator=request.operator,
    )
    preview = resolve_batch_targets(rows, batch_request)
    side_effect_plan = _create_preview_plan(
        command=command,
        effect_type="wecom.broadcast.preview",
        adapter_name="wecom",
        target_id="broadcast_preview",
        payload_summary={
            "candidate_count": preview["selected_count"],
            "eligible_count": preview["eligible_count"],
            "message_preview": _message_preview(request.message.text),
        },
        risk_level="medium",
    )
    return {
        "ok": True,
        "preview_id": f"user_ops_broadcast_preview_{command.command_id[:16]}",
        "route_owner": "ai_crm_next",
        "fallback_used": False,
        "source_status": "next_command",
        "preview_status": "controlled_default_preview" if is_controlled_default else "controlled_preview",
        "candidate_count": preview["selected_count"],
        "eligible_count": preview["eligible_count"],
        "excluded_count": preview["skipped_count"],
        "excluded_reasons": preview["skipped_summary"],
        "sample_customers": [
            {**item, "mobile": _mask_value("mobile", item.get("mobile")), "mobile_masked": _mask_value("mobile", item.get("mobile"))}
            for item in preview["sendable_samples"]
        ],
        "message_preview": _message_preview(request.message.text),
        "side_effect_plan": side_effect_plan,
        "real_external_call_executed": False,
        "audit_recorded": True,
        "adapter_mode": "real_blocked",
        "filters": filter_payload,
    }


def _handle_broadcast_preview(command: Command) -> JsonDict:
    request = BroadcastPreviewRequest(**dict(command.payload.get("request") or {}))
    repo = _default_repo()
    try:
        return _build_broadcast_preview_response(command, request=request, repo=repo)
    finally:
        _close_repository(repo)


def _build_export_preview_response(command: Command, *, request: ExportPreviewRequest, repo: UserOpsRepository) -> JsonDict:
    filters = normalize_filters(request.filters)
    filter_payload = filters.model_dump()
    rows = apply_filters(repo.list_rows(), filters)
    requested_fields = [field.strip() for field in request.fields if field.strip()]
    is_controlled_default = _filters_are_empty(filter_payload) and not requested_fields
    allowed_fields = ["external_userid", "customer_name", "mobile", "owner_userid", "class_term_no", "activation_bucket"]
    fields = [field for field in requested_fields if field in allowed_fields] or allowed_fields[:4]
    masked_sample = [
        {
            field: _mask_value(field, row.get(field)) if field in {"external_userid", "customer_name", "mobile"} else str(row.get(field) or "")
            for field in fields
        }
        for row in rows[:5]
    ]
    side_effect_plan = _create_preview_plan(
        command=command,
        effect_type="user_ops.export.file",
        adapter_name="storage",
        target_id="export_preview",
        payload_summary={"estimated_count": len(rows), "fields": fields},
        risk_level="medium",
    )
    return {
        "ok": True,
        "preview_id": f"user_ops_export_preview_{command.command_id[:16]}",
        "route_owner": "ai_crm_next",
        "fallback_used": False,
        "source_status": "next_command",
        "preview_status": "controlled_default_preview" if is_controlled_default else "controlled_preview",
        "estimated_count": len(rows),
        "fields": fields,
        "masked_sample": masked_sample,
        "requires_approval": True,
        "side_effect_plan": side_effect_plan,
        "real_external_call_executed": False,
        "audit_recorded": True,
        "adapter_mode": "real_blocked",
        "filters": filter_payload,
    }


def _handle_export_preview(command: Command) -> JsonDict:
    request = ExportPreviewRequest(**dict(command.payload.get("request") or {}))
    repo = _default_repo()
    try:
        return _build_export_preview_response(command, request=request, repo=repo)
    finally:
        _close_repository(repo)


class ExecuteUserOpsBatchSendCommand:
    def __init__(
        self,
        repo: UserOpsRepository | None = None,
        batch_gateway: UserOpsBatchSendGateway | None = None,
        dispatch_adapter: WeComMessageDispatchAdapter | None = None,
    ) -> None:
        self._repo = repo
        self._batch_gateway = batch_gateway or build_user_ops_batch_send_gateway()
        self._dispatch_adapter = dispatch_adapter or build_wecom_message_dispatch_adapter()

    def execute(self, request: BatchSendRequest) -> JsonDict:
        repo = self._repo or _default_repo()
        try:
            if not request.confirm:
                raise ContractError("confirm=true is required")
            preview = PreviewUserOpsBatchSendCommand(repo, batch_gateway=self._batch_gateway)(request)
            if not preview["has_body"]:
                raise ContractError("content is required")

            media_refs = _media_refs_from_batch_request(request)
            execute_gateway_result = self._batch_gateway.execute_batch_send(
                content=request.content,
                targets=preview["final_targets"],
                owner_buckets=preview["owner_buckets"],
                operator=request.operator,
                media_refs=media_refs,
            )
            if not execute_gateway_result["ok"]:
                raise ContractError(execute_gateway_result["error_message"] or execute_gateway_result["error_code"])

            task_results: list[JsonDict] = []
            sender_userids: list[str] = []
            for bucket in preview["owner_buckets"]:
                dispatch_result = self._dispatch_adapter.send_private_message(
                    owner_userid=str(bucket.get("owner_userid") or ""),
                    external_userids=list(bucket.get("external_userids") or []),
                    content=request.content,
                    media_refs=media_refs,
                )
                if not dispatch_result["ok"]:
                    raise ContractError(dispatch_result["error_message"] or dispatch_result["error_code"])
                dispatch_payload = dispatch_result["result"]
                sender_userid = str(bucket.get("sender_userid") or bucket.get("owner_userid") or "")
                sender_userids.append(sender_userid)
                task_results.append(
                    {
                        "owner_userid": bucket["owner_userid"],
                        "sender_userid": sender_userid,
                        "owner_display_name": bucket.get("owner_display_name") or sender_userid,
                        "external_userids": bucket["external_userids"],
                        "external_userid_count": len(bucket["external_userids"]),
                        "target_count": bucket["target_count"],
                        "task_id": dispatch_payload["task_id"],
                        "status": dispatch_payload["status"],
                        "status_label": dispatch_payload["status_label"],
                        "error_message": dispatch_payload["error_message"],
                        "dispatch_adapter": dispatch_payload["dispatch_adapter"],
                        "adapter_contract": dispatch_result,
                    }
                )

            sent_count = sum(result["target_count"] for result in task_results)
            record_payload = {
                "selected_count": preview["selected_count"],
                "eligible_count": preview["eligible_count"],
                "sent_count": sent_count,
                "skipped_count": preview["skipped_count"],
                "skipped_reasons": preview["skipped_by_reason"],
                "skipped_by_reason": preview["skipped_by_reason"],
                "skipped_summary": preview["skipped_summary"],
                "skip_summary": preview["skip_summary"],
                "include_do_not_disturb": preview["include_do_not_disturb"],
                "content_preview": preview["content_preview"],
                "image_count": preview["image_count"],
                "sender_userids": sorted(set(sender_userids)),
                "filter_snapshot": preview["filters"],
                "operator": request.operator,
                "status": "created",
                "status_label": "已创建任务",
                "task_results": task_results,
            }
            record_gateway_result = self._batch_gateway.create_send_record(payload=record_payload)
            if not record_gateway_result["ok"]:
                raise ContractError(record_gateway_result["error_message"] or record_gateway_result["error_code"])
            record = repo.create_send_record(record_payload)
            summary_gateway_result = self._batch_gateway.build_send_result_summary(
                record_id=record["record_id"],
                task_results=task_results,
                sent_count=sent_count,
                skipped_count=preview["skipped_count"],
            )
            if not summary_gateway_result["ok"]:
                raise ContractError(summary_gateway_result["error_message"] or summary_gateway_result["error_code"])
            execution_summary = {
                "dispatch_adapter": "fake_wecom",
                "task_count": len(task_results),
                "sent_count": sent_count,
                "delivery_status_supported": False,
                "adapter_contract": summary_gateway_result,
                "side_effect_safety": _user_ops_side_effect_safety(),
            }
            return {
                "ok": True,
                **preview,
                "record_id": record["record_id"],
                "sent_count": sent_count,
                "execution_summary": execution_summary,
                "task_results": task_results,
                "side_effect_safety": _user_ops_side_effect_safety(),
                "adapter_contract": {
                    "batch_send_execute": execute_gateway_result,
                    "send_record": record_gateway_result,
                },
            }
        finally:
            if _should_close_repo(self._repo):
                _close_repository(repo)

    __call__ = execute


class ListUserOpsSendRecordsQuery:
    def __init__(self, repo: UserOpsRepository | None = None) -> None:
        self._repo = repo

    def execute(self, limit: int = 20, offset: int = 0) -> JsonDict:
        repo = self._repo or _default_repo()
        try:
            records = repo.list_send_records()
            page = records[offset : offset + limit]
            summaries = [{key: value for key, value in record.items() if key != "task_results"} for record in page]
            return {
                "ok": True,
                **_readonly_meta(),
                "items": summaries,
                "records": summaries,
                "count": len(summaries),
                "total": len(records),
                "limit": limit,
                "offset": offset,
            }
        finally:
            if _should_close_repo(self._repo):
                _close_repository(repo)

    __call__ = execute


class GetUserOpsSendRecordQuery:
    def __init__(self, repo: UserOpsRepository | None = None) -> None:
        self._repo = repo

    def execute(self, record_id: str) -> JsonDict:
        repo = self._repo or _default_repo()
        try:
            record = repo.get_send_record(record_id)
            if record is None:
                raise NotFoundError("send record not found")
            task_results = record.get("task_results", [])
            record_summary = {key: value for key, value in record.items() if key != "task_results"}
            return {
                "ok": True,
                **_readonly_meta(),
                "record": record_summary,
                "task_results": task_results,
                "delivery_status_supported": False,
                "status_note": "当前只支持 fake dispatch 任务创建结果，不轮询企业微信送达状态。",
            }
        finally:
            if _should_close_repo(self._repo):
                _close_repository(repo)

    __call__ = execute


class RefreshUserOpsSendRecordStatusCommand:
    def __init__(self, repo: UserOpsRepository | None = None) -> None:
        self._repo = repo

    def execute(self, record_id: str) -> JsonDict:
        repo = self._repo or _default_repo()
        try:
            detail = GetUserOpsSendRecordQuery(repo)(record_id)
            return {"ok": True, **detail, "refreshed": False}
        finally:
            if _should_close_repo(self._repo):
                _close_repository(repo)

    __call__ = execute


class EnqueueUserOpsDeferredJobCommand:
    def __init__(self, gateway: UserOpsDeferredJobGateway | None = None) -> None:
        self._gateway = gateway or build_user_ops_deferred_job_gateway()

    def execute(self, *, job_id: str = "", job_type: str = "", run_at: str = "", target: JsonDict | None = None, payload_summary: JsonDict | None = None) -> JsonDict:
        return self._gateway.enqueue_deferred_job(job_id=job_id, job_type=job_type, run_at=run_at, target=target or {}, payload_summary=payload_summary or {})

    __call__ = execute


class RunDueUserOpsDeferredJobsCommand:
    def __init__(self, gateway: UserOpsDeferredJobGateway | None = None) -> None:
        self._gateway = gateway or build_user_ops_deferred_job_gateway()

    def execute(self, *, now: str = "", limit: int = 100, job_ids: list[str] | None = None) -> JsonDict:
        return self._gateway.run_due_jobs(now=now, limit=limit, job_ids=job_ids or [])

    __call__ = execute


class SetUserOpsDoNotDisturbCommand:
    def __init__(
        self,
        repo: UserOpsRepository | None = None,
        dnd_gateway: UserOpsDndWriteGateway | None = None,
    ) -> None:
        self._repo = repo
        self._dnd_gateway = dnd_gateway or build_user_ops_dnd_gateway()

    def execute(self, request: DoNotDisturbRequest) -> JsonDict:
        repo = self._repo or _default_repo()
        try:
            external_userid = request.external_userid.strip()
            mobile = request.mobile.strip()
            if not external_userid and not mobile:
                raise ContractError("external_userid or mobile is required")

            action = request.action.strip().lower()
            is_active = request.is_active
            if is_active is None:
                is_active = action not in {"disable", "cancel", "clear", "remove"}

            gateway_result = (
                self._dnd_gateway.enable_do_not_disturb(
                    external_userid=external_userid,
                    mobile=mobile,
                    reason_code=request.reason_code.strip() or "manual_set",
                    reason_text=request.reason_text.strip() or "运营设置",
                    operator=request.operator,
                )
                if is_active
                else self._dnd_gateway.cancel_do_not_disturb(
                    external_userid=external_userid,
                    mobile=mobile,
                    reason_code=request.reason_code.strip() or "manual_set",
                    reason_text=request.reason_text.strip() or "运营设置",
                    operator=request.operator,
                )
            )
            if not gateway_result["ok"]:
                raise ContractError(gateway_result["error_message"] or gateway_result["error_code"])

            row = repo.set_do_not_disturb(
                external_userid=external_userid,
                mobile=mobile,
                reason_code=request.reason_code.strip() or "manual_set",
                reason_text=request.reason_text.strip() or "运营设置",
                is_active=bool(is_active),
                operator=request.operator,
            )
            if row is None:
                raise NotFoundError("target is not in user_ops_pool_current")
            return {
                "ok": True,
                "target": {
                    "id": row["id"],
                    "external_userid": row["external_userid"],
                    "mobile": row["mobile"],
                },
                "do_not_disturb": row["do_not_disturb"],
                "do_not_disturb_reasons": row["do_not_disturb_reasons"],
                "side_effect_safety": _user_ops_side_effect_safety(),
                "adapter_contract": {
                    "dnd_write": gateway_result,
                },
            }
        finally:
            if _should_close_repo(self._repo):
                _close_repository(repo)

    __call__ = execute


_register_preview_handlers()
