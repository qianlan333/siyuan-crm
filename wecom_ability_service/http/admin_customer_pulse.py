from __future__ import annotations

from typing import Mapping

from flask import jsonify, request, url_for

from ..application.ai_assist import (
    CustomerPulseCardEvidenceQueryDTO,
    CustomerPulseCardQueryDTO,
    CustomerPulseCustomerDetailQueryDTO,
    CustomerPulseFeatureGateQueryDTO,
    CustomerPulseInboxQueryDTO,
    CustomerPulseMetricsQueryDTO,
    EnqueueCustomerPulseRecomputeCommand,
    EnqueueCustomerPulseRecomputeCommandDTO,
    ExecuteCustomerActionCommand,
    ExecuteCustomerActionCommandDTO,
    GetCustomerPulseCardEvidenceQuery,
    GetCustomerPulseCardQuery,
    GetCustomerPulseCustomerDetailQuery,
    GetCustomerPulseFeatureGateQuery,
    GetCustomerPulseInboxQuery,
    GetCustomerPulseMetricsQuery,
    PreviewCustomerActionCommand,
    PreviewCustomerActionCommandDTO,
    RefreshCustomerPulseCardsCommand,
    RefreshCustomerPulseCardsCommandDTO,
    RunDueCustomerPulseSnapshotJobCommand,
    RunDueCustomerPulseSnapshotJobCommandDTO,
    SubmitCustomerPulseFeedbackCommand,
    SubmitCustomerPulseFeedbackCommandDTO,
    UndoCustomerPulseCardActionCommand,
    UndoCustomerPulseCardActionCommandDTO,
)
from ..domains.admin_config import repo as admin_config_repo
from ..domains.customer_pulse import repo as customer_pulse_repo
from ..domains.customer_pulse.access import (
    CUSTOMER_PULSE_PERMISSION_VIEW_INBOX,
    CUSTOMER_PULSE_PERMISSION_VIEW_WIDGET,
    CustomerPulseAccessDenied,
    CustomerPulseTenantContext,
    assert_customer_pulse_any_permission,
    assert_customer_pulse_evidence_view,
    assert_customer_pulse_feedback_permission,
    assert_customer_pulse_internal_job_access,
    assert_customer_pulse_inbox_view,
    assert_customer_pulse_page_visible,
    assert_customer_pulse_request_context,
    assert_customer_pulse_target_owner_access,
    current_customer_pulse_request_access_context,
    customer_pulse_tenant_context_summary,
    customer_pulse_template_access_payload,
    resolve_customer_pulse_read_scope,
)
from .admin_console import _breadcrumb_items, _render_admin_template
from .internal_auth import ensure_admin_console_action_token, require_internal_api_token, validate_admin_console_action_token

CUSTOMER_PULSE_AUDIT_TARGET_ACCESS = "customer_pulse_access"
CUSTOMER_PULSE_AUDIT_TARGET_ACTION = "customer_pulse_action"
CUSTOMER_PULSE_AUDIT_TARGET_JOB = "customer_pulse_job"
CUSTOMER_PULSE_AUDIT_TARGET_EVIDENCE = "customer_pulse_evidence"
_CUSTOMER_PULSE_UNAUTHORIZED_SECURITY_CODES = {
    "action_permission_denied",
    "action_permission_unmapped",
    "actor_owner_scope_forbidden",
    "card_view_forbidden",
    "customer_pulse_detail_forbidden",
    "evidence_view_forbidden",
    "feedback_permission_forbidden",
    "inbox_view_forbidden",
    "internal_role_forbidden",
    "operator_role_forbidden",
    "owner_scope_forbidden",
    "page_permission_forbidden",
    "viewer_role_forbidden",
    "widget_view_forbidden",
}
_CUSTOMER_PULSE_CROSS_TENANT_SECURITY_CODES = {"cross_tenant_owner_scope"}


def _request_payload() -> dict:
    json_payload = request.get_json(silent=True) or {}
    if request.method == "POST" and request.form:
        return {**json_payload, **request.form.to_dict(flat=True)}
    return json_payload or request.args.to_dict(flat=True)


def _normalized_text(value: object) -> str:
    return str(value or "").strip()


def _operator(payload: dict) -> str:
    access_context = current_customer_pulse_request_access_context()
    return (
        _normalized_text(payload.get("operator"))
        or _normalized_text(access_context.get("operator"))
        or _normalized_text(request.headers.get("X-Admin-Operator"))
        or "crm_console"
    )


def _truthy(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _inbox_filters(source: dict) -> dict:
    return {
        "limit": 50,
        "owner_userid": _normalized_text(source.get("owner_userid")),
        "external_userid": _normalized_text(source.get("external_userid")),
        "operator": _normalized_text(source.get("operator") or request.headers.get("X-Admin-Operator")),
        "scope": _normalized_text(source.get("scope") or "all") or "all",
        "stage": _normalized_text(source.get("stage")),
        "risk": _normalized_text(source.get("risk")),
        "overdue_only": _truthy(source.get("overdue_only")),
        "draft_only": _truthy(source.get("draft_only")),
        "high_priority_only": _truthy(source.get("high_priority_only")),
        "search": _normalized_text(source.get("search")),
    }


def _customer_pulse_access_context() -> CustomerPulseTenantContext:
    return current_customer_pulse_request_access_context()


def _audit_actor_summary(
    *,
    tenant_context: Mapping[str, object] | None = None,
    operator: str = "",
) -> dict[str, str]:
    access_context = dict(tenant_context or {})
    return {
        "actor_userid": _normalized_text(access_context.get("actor_userid") or access_context.get("user_id")),
        "actor_role": _normalized_text(access_context.get("actor_role") or access_context.get("role")),
        "operator": _normalized_text(operator) or _normalized_text(access_context.get("operator")),
        "auth_mode": _normalized_text(access_context.get("auth_mode") or access_context.get("mode")),
        "source": _normalized_text(access_context.get("source")),
    }


def _audit_resource_summary(*, target_type: str, target_id: str) -> dict[str, str]:
    return {
        "resource_type": _normalized_text(target_type),
        "resource_id": _normalized_text(target_id),
    }


def _audit_customer_pulse_operation(
    *,
    operator: str,
    action_type: str,
    target_type: str,
    target_id: str,
    tenant_context: Mapping[str, object] | None = None,
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    audit_tenant_context = customer_pulse_tenant_context_summary(tenant_context or _customer_pulse_access_context())
    actor = _audit_actor_summary(tenant_context=tenant_context, operator=operator)
    resource = _audit_resource_summary(target_type=target_type, target_id=target_id)
    admin_config_repo.insert_admin_operation_log(
        operator=_normalized_text(operator) or "crm_console",
        action_type=_normalized_text(action_type),
        target_type=_normalized_text(target_type),
        target_id=_normalized_text(target_id),
        before_json={**dict(before or {}), "tenant_context": audit_tenant_context, "actor": actor, "resource": resource},
        after_json={**dict(after or {}), "tenant_context": audit_tenant_context, "actor": actor, "resource": resource},
    )


def _request_audit_target() -> tuple[str, str, str]:
    view_args = request.view_args or {}
    if request.path.endswith("/evidence"):
        return "deny_card_evidence", CUSTOMER_PULSE_AUDIT_TARGET_EVIDENCE, str(view_args.get("card_id") or "")
    if request.path.endswith("/actions/preview"):
        return "deny_preview_card_action", CUSTOMER_PULSE_AUDIT_TARGET_ACTION, str(view_args.get("card_id") or "")
    if request.path.endswith("/actions/execute"):
        return "deny_execute_card_action", CUSTOMER_PULSE_AUDIT_TARGET_ACTION, str(view_args.get("card_id") or "")
    if request.path.endswith("/feedback"):
        return "deny_submit_card_feedback", CUSTOMER_PULSE_AUDIT_TARGET_ACTION, str(view_args.get("card_id") or "")
    if "/executions/" in request.path and request.path.endswith("/undo"):
        return "deny_undo_execution", CUSTOMER_PULSE_AUDIT_TARGET_ACTION, str(view_args.get("execution_id") or "")
    if request.path.endswith("/run-due"):
        return "deny_run_due_jobs", CUSTOMER_PULSE_AUDIT_TARGET_JOB, "run_due"
    if request.path.endswith("/recompute"):
        return "deny_recompute", CUSTOMER_PULSE_AUDIT_TARGET_JOB, "recompute"
    if "/customers/" in request.path:
        return (
            "deny_customer_detail",
            CUSTOMER_PULSE_AUDIT_TARGET_ACCESS,
            _normalized_text(view_args.get("external_userid")),
        )
    if "/cards/" in request.path:
        return "deny_card_detail", CUSTOMER_PULSE_AUDIT_TARGET_ACCESS, str(view_args.get("card_id") or "")
    return "deny_inbox_access", CUSTOMER_PULSE_AUDIT_TARGET_ACCESS, "inbox"


def _record_customer_pulse_security_metric(
    *,
    event_type: str,
    event_source: str,
    tenant_context: Mapping[str, object] | None = None,
    operator: str = "",
    action_type: str = "",
    target_id: str = "",
    payload: dict | None = None,
) -> None:
    audit_tenant_context = customer_pulse_tenant_context_summary(tenant_context or _customer_pulse_access_context())
    tenant_key = _normalized_text(audit_tenant_context.get("tenant_key"))
    if not tenant_key or not _normalized_text(event_type):
        return
    try:
        customer_pulse_repo.insert_customer_pulse_metric_event(
            external_userid="",
            owner_userid="",
            action_type=_normalized_text(action_type),
            event_type=_normalized_text(event_type),
            event_source=_normalized_text(event_source),
            tenant_key=tenant_key,
            operator=_normalized_text(operator) or "crm_console",
            payload={
                **dict(payload or {}),
                "target_id": _normalized_text(target_id),
                "path": request.path,
                "method": request.method,
                "actor": _audit_actor_summary(tenant_context=tenant_context, operator=operator),
                "tenant_context": audit_tenant_context,
            },
        )
    except Exception:
        return


def _audit_customer_pulse_access_denied(exc: CustomerPulseAccessDenied) -> None:
    access_context = _customer_pulse_access_context()
    payload = _request_payload()
    action_type, target_type, target_id = _request_audit_target()
    operator = _operator(payload)
    normalized_code = _normalized_text(exc.code)
    _audit_customer_pulse_operation(
        operator=operator,
        action_type=action_type,
        target_type=target_type,
        target_id=target_id,
        tenant_context=access_context,
        before={
            "path": request.path,
            "method": request.method,
            "request_fields": sorted(str(key) for key in payload.keys()),
        },
        after={
            "result": "denied",
            "error_code": normalized_code,
            "error": str(exc),
            "http_status": int(exc.http_status),
        },
    )
    _record_customer_pulse_security_metric(
        event_type="access_denied",
        event_source="admin_customer_pulse_access",
        tenant_context=access_context,
        operator=operator,
        action_type=action_type,
        target_id=target_id,
        payload={"error_code": normalized_code, "http_status": int(exc.http_status)},
    )
    if normalized_code in _CUSTOMER_PULSE_UNAUTHORIZED_SECURITY_CODES:
        _record_customer_pulse_security_metric(
            event_type="unauthorized_denied",
            event_source="admin_customer_pulse_access",
            tenant_context=access_context,
            operator=operator,
            action_type=action_type,
            target_id=target_id,
            payload={"error_code": normalized_code, "http_status": int(exc.http_status)},
        )
    if normalized_code in _CUSTOMER_PULSE_CROSS_TENANT_SECURITY_CODES:
        _record_customer_pulse_security_metric(
            event_type="cross_tenant_denied",
            event_source="admin_customer_pulse_access",
            tenant_context=access_context,
            operator=operator,
            action_type=action_type,
            target_id=target_id,
            payload={"error_code": normalized_code, "http_status": int(exc.http_status)},
        )


def _access_error_json(exc: CustomerPulseAccessDenied):
    _audit_customer_pulse_access_denied(exc)
    return jsonify({"ok": False, "error": str(exc), "code": _normalized_text(exc.code)}), int(exc.http_status)


def _feature_gate_result(access_context: Mapping[str, object] | None = None) -> dict[str, object]:
    return GetCustomerPulseFeatureGateQuery()(
        CustomerPulseFeatureGateQueryDTO(
            access_context=dict(access_context or _customer_pulse_access_context()),
        )
    )


def _feature_gate(access_context: Mapping[str, object] | None = None) -> dict[str, object]:
    feature_gate = (_feature_gate_result(access_context) or {}).get("feature_gate")
    return dict(feature_gate) if isinstance(feature_gate, Mapping) else {}


def _pulse_feature_enabled(access_context: Mapping[str, object] | None = None) -> bool:
    return bool((_feature_gate_result(access_context) or {}).get("enabled"))


def _feature_disabled_json():
    gate = _feature_gate()
    return (
        jsonify(
            {
                "ok": False,
                "error": "当前租户或角色未启用 AI推进",
                "code": "feature_disabled",
                "feature_gate": gate,
            }
        ),
        403,
    )


def _feature_disabled_page(*, page_notice: str = "", page_error: str = ""):
    gate = _feature_gate()
    global_disabled = _normalized_text(gate.get("reason")) == "global_disabled"
    return _render_admin_template(
        "placeholder.html",
        active_nav="customer_pulse",
        page_title="AI推进",
        page_summary="当前租户或角色尚未进入 Customer Pulse 灰度范围。" if not global_disabled else "当前 feature flag 关闭，暂不展示 AI 推进页。",
        breadcrumbs=_breadcrumb_items(("客户管理后台", url_for("api.admin_console_home")), ("AI推进", None)),
        actions=[{"label": "返回工作台", "href": url_for("api.admin_console_home"), "variant": "secondary"}],
        state_title="功能未启用" if global_disabled else "灰度未开放",
        state_body="请先在系统设置中开启 ai_customer_pulse，再进入收件箱页。"
        if global_disabled
        else f"feature gate reason={_normalized_text(gate.get('reason')) or 'feature_disabled'}",
        state_items=[
            "全局 ai_customer_pulse 开关仍是第一层总开关。",
            "在 request-scoped 模式下，还会继续校验 tenant / role / userid 灰度策略。",
        ],
        page_notice=page_notice,
        page_error=page_error,
    )


def _record_cross_tenant_probe(*, resource_type: str, resource_id: str, observed_tenant_key: str) -> None:
    access_context = _customer_pulse_access_context()
    operator = _normalized_text(access_context.get("operator")) or "crm_console"
    _audit_customer_pulse_operation(
        operator=operator,
        action_type="deny_cross_tenant_probe",
        target_type=resource_type,
        target_id=resource_id,
        tenant_context=access_context,
        before={"path": request.path, "method": request.method},
        after={
            "result": "denied",
            "error_code": "cross_tenant_owner_scope",
            "observed_tenant_key": observed_tenant_key,
        },
    )
    _record_customer_pulse_security_metric(
        event_type="cross_tenant_denied",
        event_source="admin_customer_pulse_cross_tenant_probe",
        tenant_context=access_context,
        operator=operator,
        action_type=f"probe_{resource_type}",
        target_id=resource_id,
        payload={"resource_type": resource_type, "observed_tenant_key": observed_tenant_key},
    )


def _render_customer_pulse_access_denied_page(exc: CustomerPulseAccessDenied):
    return _render_admin_template(
        "placeholder.html",
        active_nav="customer_pulse",
        page_title="AI推进",
        page_summary="当前租户或角色没有访问 Customer Pulse 的权限。",
        breadcrumbs=_breadcrumb_items(("客户管理后台", url_for("api.admin_console_home")), ("AI推进", None)),
        actions=[{"label": "返回工作台", "href": url_for("api.admin_console_home"), "variant": "secondary"}],
        state_title="无权访问",
        state_body=str(exc),
        state_items=[
            "request-scoped tenant mode 下，Customer Pulse 默认拒绝无 tenant、越权和跨租户访问。",
            "如需继续访问，请补齐 tenant context、后台角色和 tenant owner scope。",
        ],
        page_error=str(exc),
    ), int(exc.http_status)


def _resolve_read_scope(filters: dict) -> dict:
    access_context = assert_customer_pulse_request_context(_customer_pulse_access_context())
    return resolve_customer_pulse_read_scope(
        requested_owner_userid=_normalized_text(filters.get("owner_userid")),
        access_context=access_context,
    )


def _resolve_operator_scope(filters: dict) -> dict:
    access_context = assert_customer_pulse_request_context(_customer_pulse_access_context())
    read_scope = resolve_customer_pulse_read_scope(
        requested_owner_userid=_normalized_text(filters.get("owner_userid")),
        access_context=access_context,
    )
    if access_context.get("legacy_mode"):
        return read_scope
    operator_roles = {
        _normalized_text(item)
        for item in access_context.get("operator_roles", [])
        if _normalized_text(item)
    }
    actor_role = _normalized_text(access_context.get("actor_role"))
    if actor_role not in operator_roles:
        raise CustomerPulseAccessDenied(
            "当前角色没有执行 Customer Pulse 动作的权限。",
            code="operator_role_forbidden",
            http_status=403,
        )
    return read_scope


def _card_access_scope(card_id: int, *, require_operator: bool) -> tuple[dict, dict]:
    access_context = assert_customer_pulse_request_context(_customer_pulse_access_context())
    tenant_key = _normalized_text(access_context.get("tenant_key"))
    card = customer_pulse_repo.get_customer_pulse_card(int(card_id), tenant_key=tenant_key)
    if not card:
        card_any_tenant = customer_pulse_repo.get_customer_pulse_card_any_tenant(int(card_id)) or {}
        if card_any_tenant and _normalized_text(card_any_tenant.get("tenant_key")) != tenant_key:
            _record_cross_tenant_probe(
                resource_type=CUSTOMER_PULSE_AUDIT_TARGET_ACCESS,
                resource_id=str(card_id),
                observed_tenant_key=_normalized_text(card_any_tenant.get("tenant_key")),
            )
        raise LookupError("card not found")
    access_scope = assert_customer_pulse_target_owner_access(
        _normalized_text(card.get("owner_userid")),
        require_operator=require_operator,
        access_context=access_context,
    )
    return card, access_scope


def _execution_access_scope(execution_id: int, *, require_operator: bool) -> tuple[dict, dict, dict]:
    access_context = assert_customer_pulse_request_context(_customer_pulse_access_context())
    tenant_key = _normalized_text(access_context.get("tenant_key"))
    execution = customer_pulse_repo.get_customer_pulse_execution_log(int(execution_id), tenant_key=tenant_key)
    if not execution:
        execution_any_tenant = customer_pulse_repo.get_customer_pulse_execution_log_any_tenant(int(execution_id)) or {}
        if execution_any_tenant and _normalized_text(execution_any_tenant.get("tenant_key")) != tenant_key:
            _record_cross_tenant_probe(
                resource_type=CUSTOMER_PULSE_AUDIT_TARGET_ACTION,
                resource_id=str(execution_id),
                observed_tenant_key=_normalized_text(execution_any_tenant.get("tenant_key")),
            )
        raise LookupError("execution not found")
    card = customer_pulse_repo.get_customer_pulse_card(int(execution.get("card_id") or 0), tenant_key=tenant_key)
    if not card:
        raise LookupError("card not found")
    access_scope = assert_customer_pulse_target_owner_access(
        _normalized_text(card.get("owner_userid")),
        require_operator=require_operator,
        access_context=access_context,
    )
    return execution, card, access_scope


def _render_customer_pulse_page(
    *,
    page_notice: str = "",
    page_error: str = "",
    action_result: dict | None = None,
    filters: dict | None = None,
):
    access_context = _customer_pulse_access_context()
    try:
        assert_customer_pulse_request_context(access_context)
    except CustomerPulseAccessDenied as exc:
        return _render_customer_pulse_access_denied_page(exc)
    if not _pulse_feature_enabled(access_context):
        return _feature_disabled_page(page_notice=page_notice, page_error=page_error)
    resolved_filters = dict(filters or _inbox_filters(request.args))
    try:
        assert_customer_pulse_page_visible(access_context)
        assert_customer_pulse_inbox_view(access_context)
        read_scope = _resolve_read_scope(resolved_filters)
    except CustomerPulseAccessDenied as exc:
        _audit_customer_pulse_operation(
            operator=_normalized_text(access_context.get("operator")) or "crm_console",
            action_type="deny_inbox_page",
            target_type=CUSTOMER_PULSE_AUDIT_TARGET_ACCESS,
            target_id="inbox_page",
            tenant_context=access_context,
            before={"path": request.path, "filters": resolved_filters},
            after={
                "tenant_key": _normalized_text(access_context.get("tenant_key")),
                "actor_userid": _normalized_text(access_context.get("actor_userid")),
                "actor_role": _normalized_text(access_context.get("actor_role")),
                "error_code": _normalized_text(exc.code),
            },
        )
        return _render_customer_pulse_access_denied_page(exc)
    resolved_filters["operator"] = _normalized_text(read_scope.get("operator"))
    return _render_admin_template(
        "customer_pulse_inbox.html",
        active_nav="customer_pulse",
        page_title="AI推进",
        page_summary="把今天该做什么收敛成行动卡流，优先复用现有客户、会话、营销阶段、标签与 AI 能力。",
        breadcrumbs=_breadcrumb_items(("客户管理后台", url_for("api.admin_console_home")), ("AI推进", None)),
        inbox_payload=GetCustomerPulseInboxQuery()(
            CustomerPulseInboxQueryDTO(
                filters={
                    **resolved_filters,
                    "owner_userid": _normalized_text(read_scope.get("owner_userid_filter")),
                    "track_metrics": True,
                    "tenant_key": _normalized_text(read_scope.get("tenant_key")),
                    "allowed_owner_userids": read_scope.get("allowed_owner_userids") or [],
                },
                access_context=dict(read_scope.get("tenant_context") or {}),
                metric_source="admin_customer_pulse_page",
            )
        ),
        admin_action_token=ensure_admin_console_action_token(),
        customer_pulse_access=customer_pulse_template_access_payload(access_context),
        page_notice=page_notice,
        page_error=page_error,
        action_result=action_result or {},
    )


def _stats_days(source: Mapping[str, object]) -> int:
    try:
        return max(1, min(int(_normalized_text(source.get("days")) or "7"), 90))
    except (TypeError, ValueError):
        return 7


def admin_customer_pulse_inbox():
    return _render_customer_pulse_page(filters=_inbox_filters(request.args))


def admin_customer_pulse_refresh_action():
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return _render_customer_pulse_page(page_error=action_token_error), 400
    payload = _request_payload()
    try:
        scope = _resolve_operator_scope(_inbox_filters(payload))
        result = RefreshCustomerPulseCardsCommand()(
            RefreshCustomerPulseCardsCommandDTO(
                operator=_normalized_text(scope.get("operator")) or _operator(payload),
                access_context=dict(scope.get("tenant_context") or {}),
            )
        )
        _audit_customer_pulse_operation(
            operator=_normalized_text(scope.get("operator")) or _operator(payload),
            action_type="refresh_cards",
            target_type=CUSTOMER_PULSE_AUDIT_TARGET_ACTION,
            target_id="inbox",
            tenant_context=scope.get("tenant_context"),
            before={"filters": _inbox_filters(payload), "tenant_key": _normalized_text(scope.get("tenant_key"))},
            after={
                "processed_count": int(result.get("processed_count") or 0),
                "created_count": int(result.get("created_count") or 0),
                "updated_count": int(result.get("updated_count") or 0),
            },
        )
    except CustomerPulseAccessDenied as exc:
        return _render_customer_pulse_access_denied_page(exc)
    return _render_customer_pulse_page(
        page_notice="客户推进收件箱已刷新。",
        action_result=result,
        filters=_inbox_filters(payload),
    )


def admin_customer_pulse_card_execute_action(card_id: int):
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return _render_customer_pulse_page(page_error=action_token_error), 400
    payload = _request_payload()
    try:
        card, access_scope = _card_access_scope(card_id, require_operator=False)
        result = ExecuteCustomerActionCommand()(
            ExecuteCustomerActionCommandDTO(
                card_id=card_id,
                action_type=_normalized_text(payload.get("action_type")),
                action_payload=payload,
                operator=_normalized_text(access_scope.get("operator")) or _operator(payload),
                access_context=dict(access_scope.get("tenant_context") or {}),
            )
        )
        _audit_customer_pulse_operation(
            operator=_normalized_text(access_scope.get("operator")) or _operator(payload),
            action_type="execute_card_action",
            target_type=CUSTOMER_PULSE_AUDIT_TARGET_ACTION,
            target_id=str(card_id),
            tenant_context=access_scope.get("tenant_context"),
            before={
                "tenant_key": _normalized_text(access_scope.get("tenant_key")),
                "owner_userid": _normalized_text(card.get("owner_userid")),
                "action_type": _normalized_text(payload.get("action_type")),
            },
            after={
                "execution_id": int((result.get("execution") or {}).get("id") or 0),
                "execution_status": _normalized_text((result.get("execution") or {}).get("execution_status")),
            },
        )
        return _render_customer_pulse_page(
            page_notice="行动卡已执行。",
            action_result=result,
            filters=_inbox_filters(payload),
        )
    except CustomerPulseAccessDenied as exc:
        return _render_customer_pulse_access_denied_page(exc)
    except (LookupError, ValueError) as exc:
        return _render_customer_pulse_page(page_error=str(exc), filters=_inbox_filters(payload)), 400
    except Exception:
        return _render_customer_pulse_page(page_error="当前无法执行行动卡", filters=_inbox_filters(payload)), 500


def admin_customer_pulse_card_feedback_action(card_id: int):
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return _render_customer_pulse_page(page_error=action_token_error), 400
    payload = _request_payload()
    try:
        access_context = _customer_pulse_access_context()
        assert_customer_pulse_feedback_permission(access_context)
        card, access_scope = _card_access_scope(card_id, require_operator=False)
        result = SubmitCustomerPulseFeedbackCommand()(
            SubmitCustomerPulseFeedbackCommandDTO(
                card_id=card_id,
                feedback_type=_normalized_text(payload.get("feedback_type")),
                feedback_payload=payload,
                operator=_normalized_text(access_scope.get("operator")) or _operator(payload),
                access_context=dict(access_scope.get("tenant_context") or {}),
            )
        )
        _audit_customer_pulse_operation(
            operator=_normalized_text(access_scope.get("operator")) or _operator(payload),
            action_type="submit_card_feedback",
            target_type=CUSTOMER_PULSE_AUDIT_TARGET_ACTION,
            target_id=str(card_id),
            tenant_context=access_scope.get("tenant_context"),
            before={
                "tenant_key": _normalized_text(access_scope.get("tenant_key")),
                "owner_userid": _normalized_text(card.get("owner_userid")),
            },
            after={"feedback_type": _normalized_text(payload.get("feedback_type"))},
        )
        return _render_customer_pulse_page(
            page_notice="行动卡反馈已记录。",
            action_result=result,
            filters=_inbox_filters(payload),
        )
    except CustomerPulseAccessDenied as exc:
        return _render_customer_pulse_access_denied_page(exc)
    except (LookupError, ValueError) as exc:
        return _render_customer_pulse_page(page_error=str(exc), filters=_inbox_filters(payload)), 400
    except Exception:
        return _render_customer_pulse_page(page_error="当前无法记录反馈", filters=_inbox_filters(payload)), 500


def admin_customer_pulse_api():
    filters = _inbox_filters(request.args)
    access_context = _customer_pulse_access_context()
    try:
        assert_customer_pulse_inbox_view(access_context)
        if not _pulse_feature_enabled(access_context):
            return _feature_disabled_json()
        read_scope = _resolve_read_scope(filters)
        filters["operator"] = _normalized_text(read_scope.get("operator"))
        return jsonify(
            {
                "ok": True,
                "inbox": GetCustomerPulseInboxQuery()(
                    CustomerPulseInboxQueryDTO(
                        filters={
                            **filters,
                            "owner_userid": _normalized_text(read_scope.get("owner_userid_filter")),
                            "track_metrics": True,
                            "tenant_key": _normalized_text(read_scope.get("tenant_key")),
                            "allowed_owner_userids": read_scope.get("allowed_owner_userids") or [],
                        },
                        access_context=dict(read_scope.get("tenant_context") or {}),
                        metric_source="admin_customer_pulse_api",
                    )
                ),
            }
        )
    except CustomerPulseAccessDenied as exc:
        _audit_customer_pulse_operation(
            operator=_normalized_text(access_context.get("operator")) or "crm_console",
            action_type="deny_inbox_api",
            target_type=CUSTOMER_PULSE_AUDIT_TARGET_ACCESS,
            target_id="inbox_api",
            tenant_context=access_context,
            before={"path": request.path, "filters": filters},
            after={"error_code": _normalized_text(exc.code), "tenant_key": _normalized_text(access_context.get("tenant_key"))},
        )
        return _access_error_json(exc)


def admin_customer_pulse_stats_api():
    filters = _inbox_filters(request.args)
    access_context = _customer_pulse_access_context()
    try:
        assert_customer_pulse_inbox_view(access_context)
        if not _pulse_feature_enabled(access_context):
            return _feature_disabled_json()
        read_scope = _resolve_read_scope(filters)
        return jsonify(
            {
                "ok": True,
                "stats": GetCustomerPulseMetricsQuery()(
                    CustomerPulseMetricsQueryDTO(
                        days=_stats_days(request.args),
                        owner_userids=list(read_scope.get("allowed_owner_userids") or []),
                        access_context=dict(read_scope.get("tenant_context") or {}),
                    )
                ),
            }
        )
    except CustomerPulseAccessDenied as exc:
        return _access_error_json(exc)


def admin_customer_pulse_card_api(card_id: int):
    try:
        assert_customer_pulse_any_permission(
            {CUSTOMER_PULSE_PERMISSION_VIEW_INBOX, CUSTOMER_PULSE_PERMISSION_VIEW_WIDGET},
            access_context=_customer_pulse_access_context(),
            message="当前角色没有查看 Customer Pulse 卡片详情的权限。",
            code="card_view_forbidden",
        )
        if not _pulse_feature_enabled(_customer_pulse_access_context()):
            return _feature_disabled_json()
        _card, access_scope = _card_access_scope(card_id, require_operator=False)
        payload = GetCustomerPulseCardQuery()(
            CustomerPulseCardQueryDTO(
                card_id=card_id,
                access_context=dict(access_scope.get("tenant_context") or {}),
            )
        )
        return jsonify({"ok": True, **payload})
    except CustomerPulseAccessDenied as exc:
        return _access_error_json(exc)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc), "code": "feature_disabled"}), 403
    except LookupError:
        return jsonify({"ok": False, "error": "card not found"}), 404


def admin_customer_pulse_card_evidence_api(card_id: int):
    try:
        access_context = _customer_pulse_access_context()
        assert_customer_pulse_any_permission(
            {CUSTOMER_PULSE_PERMISSION_VIEW_INBOX, CUSTOMER_PULSE_PERMISSION_VIEW_WIDGET},
            access_context=access_context,
            message="当前角色没有查看 Customer Pulse 卡片详情的权限。",
            code="card_view_forbidden",
        )
        if not _pulse_feature_enabled(access_context):
            return _feature_disabled_json()
        _card, access_scope = _card_access_scope(card_id, require_operator=False)
        assert_customer_pulse_evidence_view(access_scope.get("tenant_context"))
        payload = GetCustomerPulseCardEvidenceQuery()(
            CustomerPulseCardEvidenceQueryDTO(
                card_id=card_id,
                access_context=dict(access_scope.get("tenant_context") or {}),
                event_source="admin_customer_pulse_evidence",
            )
        )
        _audit_customer_pulse_operation(
            operator=_normalized_text(access_scope.get("operator")) or _operator({}),
            action_type="view_card_evidence",
            target_type=CUSTOMER_PULSE_AUDIT_TARGET_EVIDENCE,
            target_id=str(card_id),
            tenant_context=access_scope.get("tenant_context"),
            before={
                "tenant_key": _normalized_text(access_scope.get("tenant_key")),
                "owner_userid": _normalized_text((_card or {}).get("owner_userid")),
            },
            after={
                "result": "ok",
                "evidence_count": len(payload.get("evidence") or []),
                "inaccessible_ref_count": len(payload.get("inaccessible_refs") or []),
            },
        )
        _record_customer_pulse_security_metric(
            event_type="evidence_viewed",
            event_source="admin_customer_pulse_evidence",
            tenant_context=access_scope.get("tenant_context"),
            operator=_normalized_text(access_scope.get("operator")) or _operator({}),
            action_type="view_card_evidence",
            target_id=str(card_id),
            payload={
                "evidence_count": len(payload.get("evidence") or []),
                "inaccessible_ref_count": len(payload.get("inaccessible_refs") or []),
            },
        )
        return jsonify({"ok": True, **payload})
    except CustomerPulseAccessDenied as exc:
        return _access_error_json(exc)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc), "code": "feature_disabled"}), 403
    except LookupError:
        return jsonify({"ok": False, "error": "card not found"}), 404


def admin_customer_pulse_refresh_api():
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return jsonify({"ok": False, "error": action_token_error}), 400
    payload = _request_payload()
    try:
        scope = _resolve_operator_scope(_inbox_filters(payload))
        if not _pulse_feature_enabled(scope.get("tenant_context")):
            return _feature_disabled_json()
        result = RefreshCustomerPulseCardsCommand()(
            RefreshCustomerPulseCardsCommandDTO(
                operator=_normalized_text(scope.get("operator")) or _operator(payload),
                allowed_owner_userids=list(scope.get("allowed_owner_userids") or []),
                access_context=dict(scope.get("tenant_context") or {}),
            )
        )
        _audit_customer_pulse_operation(
            operator=_normalized_text(scope.get("operator")) or _operator(payload),
            action_type="refresh_cards",
            target_type=CUSTOMER_PULSE_AUDIT_TARGET_ACTION,
            target_id="inbox",
            tenant_context=scope.get("tenant_context"),
            before={"filters": _inbox_filters(payload), "tenant_key": _normalized_text(scope.get("tenant_key"))},
            after={
                "processed_count": int(result.get("processed_count") or 0),
                "created_count": int(result.get("created_count") or 0),
                "updated_count": int(result.get("updated_count") or 0),
            },
        )
        return jsonify({"ok": True, "result": result})
    except CustomerPulseAccessDenied as exc:
        return _access_error_json(exc)


def admin_customer_pulse_card_preview_api(card_id: int):
    payload = _request_payload()
    try:
        _card, access_scope = _card_access_scope(card_id, require_operator=False)
        if not _pulse_feature_enabled(access_scope.get("tenant_context")):
            return _feature_disabled_json()
        preview = PreviewCustomerActionCommand()(
            PreviewCustomerActionCommandDTO(
                card_id=card_id,
                action_type=_normalized_text(payload.get("action_type")),
                action_payload=payload,
                track_click=_truthy(payload.get("track_click")),
                metric_source=_normalized_text(payload.get("metric_source")),
                operator=_normalized_text(access_scope.get("operator")) or _operator(payload),
                access_context=dict(access_scope.get("tenant_context") or {}),
            )
        )
        return jsonify({"ok": True, "preview": preview})
    except CustomerPulseAccessDenied as exc:
        return _access_error_json(exc)
    except LookupError:
        return jsonify({"ok": False, "error": "card not found"}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def admin_customer_pulse_card_execute_api(card_id: int):
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return jsonify({"ok": False, "error": action_token_error}), 400
    payload = _request_payload()
    try:
        card, access_scope = _card_access_scope(card_id, require_operator=False)
        if not _pulse_feature_enabled(access_scope.get("tenant_context")):
            return _feature_disabled_json()
        result = ExecuteCustomerActionCommand()(
            ExecuteCustomerActionCommandDTO(
                card_id=card_id,
                action_type=_normalized_text(payload.get("action_type")),
                action_payload=payload,
                operator=_normalized_text(access_scope.get("operator")) or _operator(payload),
                access_context=dict(access_scope.get("tenant_context") or {}),
            )
        )
        _audit_customer_pulse_operation(
            operator=_normalized_text(access_scope.get("operator")) or _operator(payload),
            action_type="execute_card_action",
            target_type=CUSTOMER_PULSE_AUDIT_TARGET_ACTION,
            target_id=str(card_id),
            tenant_context=access_scope.get("tenant_context"),
            before={
                "tenant_key": _normalized_text(access_scope.get("tenant_key")),
                "owner_userid": _normalized_text(card.get("owner_userid")),
                "action_type": _normalized_text(payload.get("action_type")),
            },
            after={
                "execution_id": int((result.get("execution") or {}).get("id") or 0),
                "execution_status": _normalized_text((result.get("execution") or {}).get("execution_status")),
            },
        )
        return jsonify({"ok": True, **result})
    except CustomerPulseAccessDenied as exc:
        return _access_error_json(exc)
    except LookupError:
        return jsonify({"ok": False, "error": "card not found"}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception:
        return jsonify({"ok": False, "error": "当前无法执行行动卡"}), 500


def admin_customer_pulse_card_feedback_api(card_id: int):
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return jsonify({"ok": False, "error": action_token_error}), 400
    payload = _request_payload()
    try:
        access_context = _customer_pulse_access_context()
        assert_customer_pulse_feedback_permission(access_context)
        card, access_scope = _card_access_scope(card_id, require_operator=False)
        if not _pulse_feature_enabled(access_scope.get("tenant_context")):
            return _feature_disabled_json()
        result = SubmitCustomerPulseFeedbackCommand()(
            SubmitCustomerPulseFeedbackCommandDTO(
                card_id=card_id,
                feedback_type=_normalized_text(payload.get("feedback_type")),
                feedback_payload=payload,
                operator=_normalized_text(access_scope.get("operator")) or _operator(payload),
                access_context=dict(access_scope.get("tenant_context") or {}),
            )
        )
        _audit_customer_pulse_operation(
            operator=_normalized_text(access_scope.get("operator")) or _operator(payload),
            action_type="submit_card_feedback",
            target_type=CUSTOMER_PULSE_AUDIT_TARGET_ACTION,
            target_id=str(card_id),
            tenant_context=access_scope.get("tenant_context"),
            before={
                "tenant_key": _normalized_text(access_scope.get("tenant_key")),
                "owner_userid": _normalized_text(card.get("owner_userid")),
            },
            after={"feedback_type": _normalized_text(payload.get("feedback_type"))},
        )
        return jsonify({"ok": True, **result})
    except CustomerPulseAccessDenied as exc:
        return _access_error_json(exc)
    except LookupError:
        return jsonify({"ok": False, "error": "card not found"}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception:
        return jsonify({"ok": False, "error": "当前无法记录反馈"}), 500


def admin_customer_pulse_execution_undo_api(execution_id: int):
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return jsonify({"ok": False, "error": action_token_error}), 400
    payload = _request_payload()
    try:
        _execution, card, access_scope = _execution_access_scope(execution_id, require_operator=False)
        if not _pulse_feature_enabled(access_scope.get("tenant_context")):
            return _feature_disabled_json()
        result = UndoCustomerPulseCardActionCommand()(
            UndoCustomerPulseCardActionCommandDTO(
                execution_id=execution_id,
                operator=_normalized_text(access_scope.get("operator")) or _operator(payload),
                access_context=dict(access_scope.get("tenant_context") or {}),
            )
        )
        _audit_customer_pulse_operation(
            operator=_normalized_text(access_scope.get("operator")) or _operator(payload),
            action_type="undo_execution",
            target_type=CUSTOMER_PULSE_AUDIT_TARGET_ACTION,
            target_id=str(execution_id),
            tenant_context=access_scope.get("tenant_context"),
            before={
                "tenant_key": _normalized_text(access_scope.get("tenant_key")),
                "owner_userid": _normalized_text(card.get("owner_userid")),
            },
            after={"execution_status": _normalized_text((result.get("execution") or {}).get("execution_status"))},
        )
        return jsonify({"ok": True, **result})
    except CustomerPulseAccessDenied as exc:
        return _access_error_json(exc)
    except LookupError:
        return jsonify({"ok": False, "error": "execution not found"}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception:
        return jsonify({"ok": False, "error": "当前无法撤销该动作"}), 500


def internal_customer_pulse_inbox_api():
    auth_failure = require_internal_api_token()
    if auth_failure is not None:
        return auth_failure
    limit = request.args.get("limit", "50")
    filters = _inbox_filters(request.args)
    try:
        resolved_limit = max(1, min(int(limit), 200))
    except ValueError:
        return jsonify({"ok": False, "error": "limit must be integer"}), 400
    try:
        assert_customer_pulse_inbox_view(_customer_pulse_access_context())
        if not _pulse_feature_enabled(_customer_pulse_access_context()):
            return _feature_disabled_json()
        read_scope = _resolve_read_scope(filters)
        return jsonify(
            {
                "ok": True,
                "inbox": GetCustomerPulseInboxQuery()(
                    CustomerPulseInboxQueryDTO(
                        filters={
                            "limit": resolved_limit,
                            "owner_userid": _normalized_text(read_scope.get("owner_userid_filter")),
                            "external_userid": _normalized_text(filters.get("external_userid")),
                            "operator": _normalized_text(read_scope.get("operator")),
                            "scope": _normalized_text(filters.get("scope")) or "all",
                            "stage": _normalized_text(filters.get("stage")),
                            "risk": _normalized_text(filters.get("risk")),
                            "overdue_only": bool(filters.get("overdue_only")),
                            "draft_only": bool(filters.get("draft_only")),
                            "high_priority_only": bool(filters.get("high_priority_only")),
                            "search": _normalized_text(filters.get("search")),
                            "track_metrics": False,
                            "tenant_key": _normalized_text(read_scope.get("tenant_key")),
                            "allowed_owner_userids": read_scope.get("allowed_owner_userids") or [],
                        },
                        access_context=dict(read_scope.get("tenant_context") or {}),
                    )
                ),
            }
        )
    except CustomerPulseAccessDenied as exc:
        return _access_error_json(exc)


def internal_customer_pulse_stats_api():
    auth_failure = require_internal_api_token()
    if auth_failure is not None:
        return auth_failure
    filters = _inbox_filters(request.args)
    try:
        assert_customer_pulse_inbox_view(_customer_pulse_access_context())
        if not _pulse_feature_enabled(_customer_pulse_access_context()):
            return _feature_disabled_json()
        read_scope = _resolve_read_scope(filters)
        return jsonify(
            {
                "ok": True,
                "stats": GetCustomerPulseMetricsQuery()(
                    CustomerPulseMetricsQueryDTO(
                        days=_stats_days(request.args),
                        owner_userids=list(read_scope.get("allowed_owner_userids") or []),
                        access_context=dict(read_scope.get("tenant_context") or {}),
                    )
                ),
            }
        )
    except CustomerPulseAccessDenied as exc:
        return _access_error_json(exc)


def internal_customer_pulse_customer_api(external_userid: str):
    auth_failure = require_internal_api_token()
    if auth_failure is not None:
        return auth_failure
    try:
        assert_customer_pulse_any_permission(
            {CUSTOMER_PULSE_PERMISSION_VIEW_INBOX, CUSTOMER_PULSE_PERMISSION_VIEW_WIDGET},
            access_context=_customer_pulse_access_context(),
            message="当前角色没有查看 Customer Pulse 客户详情的权限。",
            code="customer_pulse_detail_forbidden",
        )
        if not _pulse_feature_enabled(_customer_pulse_access_context()):
            return _feature_disabled_json()
        read_scope = _resolve_read_scope({"owner_userid": ""})
        payload = GetCustomerPulseCustomerDetailQuery()(
            CustomerPulseCustomerDetailQueryDTO(
                external_userid=external_userid,
                tenant_key=_normalized_text(read_scope.get("tenant_key")),
                allowed_owner_userids=list(read_scope.get("allowed_owner_userids") or []),
                track_metrics=False,
                access_context=dict(read_scope.get("tenant_context") or {}),
            )
        )
    except CustomerPulseAccessDenied as exc:
        return _access_error_json(exc)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except LookupError:
        return jsonify({"ok": False, "error": "customer not found"}), 404
    return jsonify({"ok": True, **payload})


def internal_customer_pulse_recompute_api():
    auth_failure = require_internal_api_token()
    if auth_failure is not None:
        return auth_failure
    payload = _request_payload()
    raw_external_userids = payload.get("external_userids") or payload.get("external_userid") or []
    if isinstance(raw_external_userids, list):
        external_userids = [str(item or "").strip() for item in raw_external_userids if str(item or "").strip()]
    elif raw_external_userids:
        external_userids = [str(raw_external_userids).strip()]
    else:
        external_userids = []
    if not external_userids:
        return jsonify({"ok": False, "error": "external_userid is required"}), 400
    force_sync = str(payload.get("force_sync") or "").strip().lower() in {"1", "true", "yes", "on"}
    try:
        job_scope = assert_customer_pulse_internal_job_access(_customer_pulse_access_context())
        if not _pulse_feature_enabled(job_scope.get("tenant_context")):
            return _feature_disabled_json()
    except CustomerPulseAccessDenied as exc:
        return _access_error_json(exc)
    if force_sync:
        result = RefreshCustomerPulseCardsCommand()(
            RefreshCustomerPulseCardsCommandDTO(
                external_userids=external_userids,
                operator=_normalized_text(job_scope.get("operator")) or _operator(payload) or "internal_api",
                allowed_owner_userids=list(job_scope.get("allowed_owner_userids") or []),
                access_context=dict(job_scope.get("tenant_context") or {}),
            )
        )
        _audit_customer_pulse_operation(
            operator=_normalized_text(job_scope.get("operator")) or "internal_api",
            action_type="force_refresh_cards",
            target_type=CUSTOMER_PULSE_AUDIT_TARGET_JOB,
            target_id="recompute",
            tenant_context=job_scope.get("tenant_context"),
            before={"external_userids": external_userids, "tenant_key": _normalized_text(job_scope.get("tenant_key"))},
            after={"processed_count": int(result.get("processed_count") or 0)},
        )
        return jsonify({"ok": True, "result": result})
    jobs = [
        EnqueueCustomerPulseRecomputeCommand()(
            EnqueueCustomerPulseRecomputeCommandDTO(
                external_userid=external_userid,
                owner_userid=_normalized_text(payload.get("owner_userid")),
                delay_seconds=int(payload.get("delay_seconds") or 0),
                operator=_normalized_text(job_scope.get("operator")) or _operator(payload) or "internal_api",
                trigger_source=_normalized_text(payload.get("trigger_source")),
                trigger_ref_type=_normalized_text(payload.get("trigger_ref_type")),
                trigger_ref_id=_normalized_text(payload.get("trigger_ref_id")),
                access_context=dict(job_scope.get("tenant_context") or {}),
            )
        )
        for external_userid in external_userids
    ]
    _audit_customer_pulse_operation(
        operator=_normalized_text(job_scope.get("operator")) or "internal_api",
        action_type="enqueue_recompute",
        target_type=CUSTOMER_PULSE_AUDIT_TARGET_JOB,
        target_id="recompute",
        tenant_context=job_scope.get("tenant_context"),
        before={"external_userids": external_userids, "tenant_key": _normalized_text(job_scope.get("tenant_key"))},
        after={"job_count": len(jobs)},
    )
    return jsonify({"ok": True, "jobs": jobs})


def internal_customer_pulse_run_due_api():
    auth_failure = require_internal_api_token()
    if auth_failure is not None:
        return auth_failure
    payload = _request_payload()
    try:
        limit = max(1, min(int(payload.get("limit") or request.values.get("limit") or 20), 200))
        rescan_limit = max(1, min(int(payload.get("rescan_limit") or request.values.get("rescan_limit") or 20), 200))
    except ValueError:
        return jsonify({"ok": False, "error": "limit and rescan_limit must be integers"}), 400
    try:
        job_scope = assert_customer_pulse_internal_job_access(_customer_pulse_access_context())
        if not _pulse_feature_enabled(job_scope.get("tenant_context")):
            return _feature_disabled_json()
        result = RunDueCustomerPulseSnapshotJobCommand()(
            RunDueCustomerPulseSnapshotJobCommandDTO(
                limit=limit,
                rescan_limit=rescan_limit,
                operator=_normalized_text(job_scope.get("operator")) or _operator(payload) or "internal_api",
                allowed_owner_userids=list(job_scope.get("allowed_owner_userids") or []),
                access_context=dict(job_scope.get("tenant_context") or {}),
            )
        )
        _audit_customer_pulse_operation(
            operator=_normalized_text(job_scope.get("operator")) or "internal_api",
            action_type="run_due_jobs",
            target_type=CUSTOMER_PULSE_AUDIT_TARGET_JOB,
            target_id="run_due",
            tenant_context=job_scope.get("tenant_context"),
            before={
                "limit": limit,
                "rescan_limit": rescan_limit,
                "tenant_key": _normalized_text(job_scope.get("tenant_key")),
            },
            after={
                "queue_success_count": int(((result.get("queue") or {}).get("success_count") or 0)),
                "refresh_processed_count": int(((result.get("refresh") or {}).get("processed_count") or 0)),
            },
        )
        return jsonify({"ok": True, "result": result})
    except CustomerPulseAccessDenied as exc:
        return _access_error_json(exc)


def register_routes(bp):
    bp.route("/admin/customer-pulse", methods=["GET"])(admin_customer_pulse_inbox)
    bp.route("/admin/customer-pulse/actions/refresh", methods=["POST"])(admin_customer_pulse_refresh_action)
    bp.route("/admin/customer-pulse/cards/<int:card_id>/actions/execute", methods=["POST"])(
        admin_customer_pulse_card_execute_action
    )
    bp.route("/admin/customer-pulse/cards/<int:card_id>/feedback", methods=["POST"])(
        admin_customer_pulse_card_feedback_action
    )
    bp.route("/api/admin/customer-pulse", methods=["GET"])(admin_customer_pulse_api)
    bp.route("/api/admin/customer-pulse/stats", methods=["GET"])(admin_customer_pulse_stats_api)
    bp.route("/api/admin/customer-pulse/cards/<int:card_id>", methods=["GET"])(admin_customer_pulse_card_api)
    bp.route("/api/admin/customer-pulse/cards/<int:card_id>/evidence", methods=["GET"])(
        admin_customer_pulse_card_evidence_api
    )
    bp.route("/api/admin/customer-pulse/actions/refresh", methods=["POST"])(admin_customer_pulse_refresh_api)
    bp.route("/api/admin/customer-pulse/cards/<int:card_id>/actions/preview", methods=["POST"])(
        admin_customer_pulse_card_preview_api
    )
    bp.route("/api/admin/customer-pulse/cards/<int:card_id>/actions/execute", methods=["POST"])(
        admin_customer_pulse_card_execute_api
    )
    bp.route("/api/admin/customer-pulse/cards/<int:card_id>/feedback", methods=["POST"])(
        admin_customer_pulse_card_feedback_api
    )
    bp.route("/api/admin/customer-pulse/executions/<int:execution_id>/undo", methods=["POST"])(
        admin_customer_pulse_execution_undo_api
    )
    bp.route("/api/internal/customer-pulse/inbox", methods=["GET"])(internal_customer_pulse_inbox_api)
    bp.route("/api/internal/customer-pulse/stats", methods=["GET"])(internal_customer_pulse_stats_api)
    bp.route("/api/internal/customer-pulse/customers/<external_userid>", methods=["GET"])(internal_customer_pulse_customer_api)
    bp.route("/api/internal/customer-pulse/recompute", methods=["POST"])(internal_customer_pulse_recompute_api)
    bp.route("/api/internal/customer-pulse/run-due", methods=["POST"])(internal_customer_pulse_run_due_api)
