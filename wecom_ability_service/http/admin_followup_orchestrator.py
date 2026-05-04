from __future__ import annotations

from typing import Any, Mapping

from flask import jsonify, request, url_for

from ..application.ai_assist import (
    AssignFollowupMissionCommand,
    AssignFollowupMissionCommandDTO,
    ExecuteFollowupMissionItemActionCommand,
    ExecuteFollowupMissionItemActionCommandDTO,
    FollowupCandidatesQueryDTO,
    FollowupCustomerQueryDTO,
    FollowupFeatureGateQueryDTO,
    FollowupMissionBoardQueryDTO,
    FollowupMissionDetailQueryDTO,
    FollowupMyMissionsQueryDTO,
    GetFollowupMissionBoardQuery,
    GetFollowupMissionDetailQuery,
    GetFollowupOrchestratorCustomerQuery,
    GetFollowupOrchestratorFeatureGateQuery,
    ListFollowupCandidatesQuery,
    ListFollowupMyMissionsQuery,
    PreviewFollowupMissionItemActionCommand,
    PreviewFollowupMissionItemActionCommandDTO,
    SyncFollowupMissionsCommand,
    SyncFollowupMissionsCommandDTO,
    UndoFollowupMissionItemActionCommand,
    UndoFollowupMissionItemActionCommandDTO,
)
from ..domains.admin_config import repo as admin_config_repo
from ..domains.customer_pulse.access import (
    CustomerPulseAccessDenied,
    assert_customer_pulse_inbox_view,
    assert_customer_pulse_page_visible,
    assert_customer_pulse_request_context,
    current_customer_pulse_request_access_context,
    customer_pulse_template_access_payload,
    customer_pulse_tenant_context_summary,
)
from ..domains.followup_orchestrator import FOLLOWUP_ORCHESTRATOR_MISSION_ACTIONS
from .admin_console import _breadcrumb_items, _render_admin_template
from .internal_auth import ensure_admin_console_action_token, require_internal_api_token, validate_admin_console_action_token


def _normalized_text(value: object) -> str:
    return str(value or "").strip()


def _request_payload() -> dict[str, Any]:
    json_payload = request.get_json(silent=True) or {}
    if request.method == "POST" and request.form:
        return {**json_payload, **request.form.to_dict(flat=True)}
    return json_payload or request.args.to_dict(flat=True)


def _access_context() -> Mapping[str, object]:
    return current_customer_pulse_request_access_context()


def _feature_gate_result(access_context: Mapping[str, object] | None = None) -> dict[str, object]:
    return GetFollowupOrchestratorFeatureGateQuery()(
        FollowupFeatureGateQueryDTO(access_context=dict(access_context or _access_context()))
    )


def _feature_gate(access_context: Mapping[str, object] | None = None) -> dict[str, object]:
    feature_gate = (_feature_gate_result(access_context) or {}).get("feature_gate")
    return dict(feature_gate) if isinstance(feature_gate, Mapping) else {}


def _followup_enabled(access_context: Mapping[str, object] | None = None) -> bool:
    return bool((_feature_gate_result(access_context) or {}).get("enabled"))


def _operator(source: dict | None = None) -> str:
    access_context = _access_context()
    payload = dict(source or {})
    return (
        _normalized_text(payload.get("operator"))
        or _normalized_text(access_context.get("operator"))
        or _normalized_text(request.headers.get("X-Admin-Operator"))
        or "crm_console"
    )


def _normalized_action_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    extra_payload = payload.get("extra_payload")
    return dict(extra_payload) if isinstance(extra_payload, dict) else dict(payload)


def _audit_followup_orchestrator_operation(
    *,
    operator: str,
    action_type: str,
    target_type: str,
    target_id: str,
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    tenant_context = customer_pulse_tenant_context_summary(_access_context())
    actor = {
        "actor_userid": _normalized_text(tenant_context.get("actor_userid")),
        "actor_role": _normalized_text(tenant_context.get("actor_role")),
        "operator": _normalized_text(operator),
        "auth_mode": _normalized_text(tenant_context.get("auth_mode")),
    }
    admin_config_repo.insert_admin_operation_log(
        operator=_normalized_text(operator) or "crm_console",
        action_type=_normalized_text(action_type),
        target_type=_normalized_text(target_type),
        target_id=_normalized_text(target_id),
        before_json={**dict(before or {}), "tenant_context": tenant_context, "actor": actor},
        after_json={**dict(after or {}), "tenant_context": tenant_context, "actor": actor},
    )


def _feature_disabled_json():
    gate = _feature_gate()
    return jsonify({"ok": False, "error": "当前租户或角色未启用团队编排", "code": "feature_disabled", "feature_gate": gate}), 403


def _feature_disabled_page(*, page_notice: str = "", page_error: str = ""):
    return _render_admin_template(
        "placeholder.html",
        active_nav="followup_orchestrator",
        page_title="团队编排",
        page_summary="当前租户或角色尚未进入 Team Follow-up Orchestrator 灰度范围。",
        breadcrumbs=_breadcrumb_items(("客户管理后台", url_for("api.admin_console_home")), ("团队编排", None)),
        actions=[{"label": "返回工作台", "href": url_for("api.admin_console_home"), "variant": "secondary"}],
        state_title="功能未启用",
        state_body="请先开启 ai_followup_orchestrator，并确保 ai_customer_pulse 已可用。",
        state_items=[
            "团队编排器依赖 customer_pulse action cards 作为输入。",
            "MVP 复用现有 tenant / RBAC / 审计链路，不额外引入第二套鉴权。",
        ],
        page_notice=page_notice,
        page_error=page_error,
    )


def _render_access_denied_page(exc: CustomerPulseAccessDenied):
    return _render_admin_template(
        "placeholder.html",
        active_nav="followup_orchestrator",
        page_title="团队编排",
        page_summary="当前租户或角色没有访问 Team Follow-up Orchestrator 的权限。",
        breadcrumbs=_breadcrumb_items(("客户管理后台", url_for("api.admin_console_home")), ("团队编排", None)),
        actions=[{"label": "返回工作台", "href": url_for("api.admin_console_home"), "variant": "secondary"}],
        state_title="无权访问",
        state_body=str(exc),
        state_items=[
            "当前阶段直接复用 customer_pulse 的 tenant context 与页面权限。",
            "缺少 tenant、跨租户或无页面权限时，一律 deny by default。",
        ],
        page_error=str(exc),
    ), int(exc.http_status)


def _filters(source: Mapping[str, object]) -> dict[str, str]:
    return {
        "scope": _normalized_text(source.get("scope") or "team") or "team",
        "owner_userid": _normalized_text(source.get("owner_userid")),
        "external_userid": _normalized_text(source.get("external_userid")),
        "actor_userid": _normalized_text(source.get("actor_userid") or request.headers.get("X-Admin-Userid")),
        "limit": _normalized_text(source.get("limit") or "50") or "50",
    }


def _resolved_limit(source: Mapping[str, object]) -> int:
    raw_limit = _normalized_text(source.get("limit") or "50") or "50"
    try:
        return max(1, min(int(raw_limit), 200))
    except ValueError as exc:
        raise ValueError("limit must be integer") from exc


def _resolved_actor_userid(source: Mapping[str, object]) -> str:
    access_context = _access_context()
    return (
        _normalized_text(source.get("actor_userid"))
        or _normalized_text(access_context.get("actor_userid"))
        or _normalized_text(access_context.get("user_id"))
        or _normalized_text(request.headers.get("X-Admin-Userid"))
    )


def _mission_action_result(
    *,
    mission_key: str,
    action_type: str,
    payload: dict | None = None,
):
    normalized_action_type = _normalized_text(action_type)
    if normalized_action_type not in FOLLOWUP_ORCHESTRATOR_MISSION_ACTIONS:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "unsupported action_type",
                    "supported_action_types": list(FOLLOWUP_ORCHESTRATOR_MISSION_ACTIONS),
                }
            ),
            400,
        )
    body = dict(payload or {})
    access_context = _access_context()
    result = AssignFollowupMissionCommand()(
        AssignFollowupMissionCommandDTO(
            mission_key=_normalized_text(mission_key),
            action_type=normalized_action_type,
            actor_userid=_resolved_actor_userid(body),
            actor_role=_normalized_text(access_context.get("actor_role") or access_context.get("role") or body.get("actor_role")),
            operator=_operator(body),
            access_context=dict(access_context),
            mission_item_key=_normalized_text(body.get("mission_item_key")),
            note=_normalized_text(body.get("note")),
        )
    )
    return jsonify(
        {
            "ok": True,
            "mission_key": _normalized_text(mission_key),
            "action_type": normalized_action_type,
            "result": result,
        }
    )


def _render_followup_orchestrator_page(*, page_notice: str = "", page_error: str = ""):
    access_context = _access_context()
    try:
        assert_customer_pulse_request_context(access_context)
        assert_customer_pulse_page_visible(access_context)
        assert_customer_pulse_inbox_view(access_context)
    except CustomerPulseAccessDenied as exc:
        return _render_access_denied_page(exc)
    if not _followup_enabled(access_context):
        return _feature_disabled_page(page_notice=page_notice, page_error=page_error)
    filters = _filters(request.args)
    payload = ListFollowupCandidatesQuery()(
        FollowupCandidatesQueryDTO(
            scope=filters["scope"],
            owner_userid=filters["owner_userid"],
            external_userid=filters["external_userid"],
            access_context=dict(access_context),
        )
    )
    return _render_admin_template(
        "followup_orchestrator.html",
        active_nav="followup_orchestrator",
        page_title="团队编排",
        page_summary="把个人 action card 升级为团队级任务包、波次、接力和转派建议；最终执行仍复用既有 Customer Pulse 动作链路。",
        breadcrumbs=_breadcrumb_items(("客户管理后台", url_for("api.admin_console_home")), ("团队编排", None)),
        orchestrator_payload=payload,
        orchestrator_access=customer_pulse_template_access_payload(access_context),
        admin_action_token=ensure_admin_console_action_token(),
        page_notice=page_notice,
        page_error=page_error,
    )


def admin_followup_orchestrator():
    return _render_followup_orchestrator_page()


def api_admin_followup_orchestrator():
    access_context = _access_context()
    try:
        assert_customer_pulse_request_context(access_context)
        assert_customer_pulse_page_visible(access_context)
        assert_customer_pulse_inbox_view(access_context)
    except CustomerPulseAccessDenied as exc:
        return jsonify({"ok": False, "error": str(exc), "code": exc.code}), int(exc.http_status)
    if not _followup_enabled(access_context):
        return _feature_disabled_json()
    filters = _filters(request.args)
    try:
        if filters["scope"] == "mine":
            payload = ListFollowupMyMissionsQuery()(
                FollowupMyMissionsQueryDTO(
                    actor_userid=_resolved_actor_userid(filters),
                    limit=_resolved_limit(filters),
                    auto_sync=True,
                    access_context=dict(access_context),
                )
            )
        elif filters["owner_userid"] or filters["external_userid"] or filters["scope"] not in {"", "team"}:
            payload = ListFollowupCandidatesQuery()(
                FollowupCandidatesQueryDTO(
                    scope=filters["scope"],
                    owner_userid=filters["owner_userid"],
                    external_userid=filters["external_userid"],
                    limit=_resolved_limit(filters),
                    auto_sync=True,
                    access_context=dict(access_context),
                )
            )
        else:
            payload = GetFollowupMissionBoardQuery()(
                FollowupMissionBoardQueryDTO(
                    limit=_resolved_limit(filters),
                    auto_sync=True,
                    access_context=dict(access_context),
                )
            )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "orchestrator": payload})


def api_admin_followup_orchestrator_customer(external_userid: str):
    access_context = _access_context()
    try:
        assert_customer_pulse_request_context(access_context)
        assert_customer_pulse_page_visible(access_context)
        assert_customer_pulse_inbox_view(access_context)
    except CustomerPulseAccessDenied as exc:
        return jsonify({"ok": False, "error": str(exc), "code": exc.code}), int(exc.http_status)
    if not _followup_enabled(access_context):
        return _feature_disabled_json()
    payload = GetFollowupOrchestratorCustomerQuery()(
        FollowupCustomerQueryDTO(
            external_userid=_normalized_text(external_userid),
            access_context=dict(access_context),
        )
    )
    return jsonify({"ok": True, "customer_orchestrator": payload})


def api_admin_followup_orchestrator_mission_detail(mission_key: str):
    access_context = _access_context()
    try:
        assert_customer_pulse_request_context(access_context)
        assert_customer_pulse_page_visible(access_context)
        assert_customer_pulse_inbox_view(access_context)
    except CustomerPulseAccessDenied as exc:
        return jsonify({"ok": False, "error": str(exc), "code": exc.code}), int(exc.http_status)
    if not _followup_enabled(access_context):
        return _feature_disabled_json()
    try:
        payload = GetFollowupMissionDetailQuery()(
            FollowupMissionDetailQueryDTO(
                mission_key=_normalized_text(mission_key),
                access_context=dict(access_context),
            )
        )
    except CustomerPulseAccessDenied as exc:
        return jsonify({"ok": False, "error": str(exc), "code": exc.code}), int(exc.http_status)
    except LookupError:
        return jsonify({"ok": False, "error": "mission not found"}), 404
    return jsonify({"ok": True, "mission": payload})


def api_admin_followup_orchestrator_mission_action(mission_key: str, action_type: str):
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return jsonify({"ok": False, "error": action_token_error}), 400
    access_context = _access_context()
    try:
        assert_customer_pulse_request_context(access_context)
        assert_customer_pulse_page_visible(access_context)
        assert_customer_pulse_inbox_view(access_context)
    except CustomerPulseAccessDenied as exc:
        return jsonify({"ok": False, "error": str(exc), "code": exc.code}), int(exc.http_status)
    if not _followup_enabled(access_context):
        return _feature_disabled_json()
    payload = _request_payload()
    operator = _operator(payload)
    normalized_action_type = _normalized_text(action_type)
    try:
        response = _mission_action_result(
            mission_key=_normalized_text(mission_key),
            action_type=normalized_action_type,
            payload=payload,
        )
        _audit_followup_orchestrator_operation(
            operator=operator,
            action_type=f"followup_orchestrator_{normalized_action_type}",
            target_type="followup_orchestrator_mission",
            target_id=_normalized_text(mission_key),
            before={"request_fields": sorted(str(key) for key in payload.keys()), "path": request.path},
            after={"result": "updated"},
        )
        return response
    except CustomerPulseAccessDenied as exc:
        _audit_followup_orchestrator_operation(
            operator=operator,
            action_type=f"followup_orchestrator_{normalized_action_type}",
            target_type="followup_orchestrator_mission",
            target_id=_normalized_text(mission_key),
            before={"request_fields": sorted(str(key) for key in payload.keys()), "path": request.path},
            after={"result": "denied", "error": str(exc), "code": exc.code},
        )
        return jsonify({"ok": False, "error": str(exc), "code": exc.code}), int(exc.http_status)
    except LookupError:
        return jsonify({"ok": False, "error": "mission not found"}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def api_admin_followup_orchestrator_mission_item_preview(mission_key: str, mission_item_key: str):
    access_context = _access_context()
    try:
        assert_customer_pulse_request_context(access_context)
        assert_customer_pulse_page_visible(access_context)
        assert_customer_pulse_inbox_view(access_context)
    except CustomerPulseAccessDenied as exc:
        return jsonify({"ok": False, "error": str(exc), "code": exc.code}), int(exc.http_status)
    if not _followup_enabled(access_context):
        return _feature_disabled_json()
    payload = _request_payload()
    try:
        result = PreviewFollowupMissionItemActionCommand()(
            PreviewFollowupMissionItemActionCommandDTO(
                mission_key=_normalized_text(mission_key),
                mission_item_key=_normalized_text(mission_item_key),
                action_type=_normalized_text(payload.get("action_type")),
                actor_userid=_resolved_actor_userid(payload),
                operator=_operator(payload),
                access_context=dict(access_context),
            )
        )
        return jsonify({"ok": True, "preview": result})
    except CustomerPulseAccessDenied as exc:
        return jsonify({"ok": False, "error": str(exc), "code": exc.code}), int(exc.http_status)
    except LookupError:
        return jsonify({"ok": False, "error": "mission item not found"}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def api_admin_followup_orchestrator_mission_item_execute(mission_key: str, mission_item_key: str):
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return jsonify({"ok": False, "error": action_token_error}), 400
    access_context = _access_context()
    try:
        assert_customer_pulse_request_context(access_context)
        assert_customer_pulse_page_visible(access_context)
        assert_customer_pulse_inbox_view(access_context)
    except CustomerPulseAccessDenied as exc:
        return jsonify({"ok": False, "error": str(exc), "code": exc.code}), int(exc.http_status)
    if not _followup_enabled(access_context):
        return _feature_disabled_json()
    payload = _request_payload()
    operator = _operator(payload)
    try:
        result = ExecuteFollowupMissionItemActionCommand()(
            ExecuteFollowupMissionItemActionCommandDTO(
                mission_key=_normalized_text(mission_key),
                mission_item_key=_normalized_text(mission_item_key),
                action_type=_normalized_text(payload.get("action_type")),
                actor_userid=_resolved_actor_userid(payload),
                actor_role=_normalized_text(access_context.get("actor_role") or access_context.get("role") or payload.get("actor_role")),
                operator=operator,
                note=_normalized_text(payload.get("note")),
                action_payload=_normalized_action_payload(payload),
                access_context=dict(access_context),
            )
        )
        _audit_followup_orchestrator_operation(
            operator=operator,
            action_type=f"followup_orchestrator_execute_{_normalized_text(payload.get('action_type'))}",
            target_type="followup_orchestrator_mission_item",
            target_id=_normalized_text(mission_item_key),
            before={"request_fields": sorted(str(key) for key in payload.keys()), "path": request.path},
            after={"result": "updated", "mission_key": _normalized_text(mission_key)},
        )
        return jsonify({"ok": True, "result": result})
    except CustomerPulseAccessDenied as exc:
        _audit_followup_orchestrator_operation(
            operator=operator,
            action_type=f"followup_orchestrator_execute_{_normalized_text(payload.get('action_type'))}",
            target_type="followup_orchestrator_mission_item",
            target_id=_normalized_text(mission_item_key),
            before={"request_fields": sorted(str(key) for key in payload.keys()), "path": request.path},
            after={"result": "denied", "error": str(exc), "code": exc.code},
        )
        return jsonify({"ok": False, "error": str(exc), "code": exc.code}), int(exc.http_status)
    except LookupError:
        return jsonify({"ok": False, "error": "mission item not found"}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def api_admin_followup_orchestrator_mission_item_undo(mission_key: str, mission_item_key: str):
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return jsonify({"ok": False, "error": action_token_error}), 400
    access_context = _access_context()
    try:
        assert_customer_pulse_request_context(access_context)
        assert_customer_pulse_page_visible(access_context)
        assert_customer_pulse_inbox_view(access_context)
    except CustomerPulseAccessDenied as exc:
        return jsonify({"ok": False, "error": str(exc), "code": exc.code}), int(exc.http_status)
    if not _followup_enabled(access_context):
        return _feature_disabled_json()
    payload = _request_payload()
    operator = _operator(payload)
    try:
        result = UndoFollowupMissionItemActionCommand()(
            UndoFollowupMissionItemActionCommandDTO(
                mission_key=_normalized_text(mission_key),
                mission_item_key=_normalized_text(mission_item_key),
                execution_id=int(payload.get("execution_id") or 0),
                actor_userid=_resolved_actor_userid(payload),
                actor_role=_normalized_text(access_context.get("actor_role") or access_context.get("role") or payload.get("actor_role")),
                operator=operator,
                access_context=dict(access_context),
            )
        )
        _audit_followup_orchestrator_operation(
            operator=operator,
            action_type="followup_orchestrator_undo_executor",
            target_type="followup_orchestrator_mission_item",
            target_id=_normalized_text(mission_item_key),
            before={"request_fields": sorted(str(key) for key in payload.keys()), "path": request.path},
            after={"result": "updated", "mission_key": _normalized_text(mission_key)},
        )
        return jsonify({"ok": True, "result": result})
    except CustomerPulseAccessDenied as exc:
        return jsonify({"ok": False, "error": str(exc), "code": exc.code}), int(exc.http_status)
    except LookupError:
        return jsonify({"ok": False, "error": "mission item not found"}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def internal_followup_orchestrator_team_board_api():
    auth_failure = require_internal_api_token()
    if auth_failure is not None:
        return auth_failure
    access_context = _access_context()
    try:
        assert_customer_pulse_request_context(access_context)
        assert_customer_pulse_inbox_view(access_context)
        if not _followup_enabled(access_context):
            return _feature_disabled_json()
        payload = GetFollowupMissionBoardQuery()(
            FollowupMissionBoardQueryDTO(
                limit=_resolved_limit(request.args),
                auto_sync=True,
                access_context=dict(access_context),
            )
        )
        return jsonify({"ok": True, "team_board": payload})
    except CustomerPulseAccessDenied as exc:
        return jsonify({"ok": False, "error": str(exc), "code": exc.code}), int(exc.http_status)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def internal_followup_orchestrator_my_missions_api():
    auth_failure = require_internal_api_token()
    if auth_failure is not None:
        return auth_failure
    access_context = _access_context()
    try:
        assert_customer_pulse_request_context(access_context)
        assert_customer_pulse_inbox_view(access_context)
        if not _followup_enabled(access_context):
            return _feature_disabled_json()
        filters = _filters(request.args)
        payload = ListFollowupMyMissionsQuery()(
            FollowupMyMissionsQueryDTO(
                actor_userid=_resolved_actor_userid(filters),
                limit=_resolved_limit(filters),
                auto_sync=True,
                access_context=dict(access_context),
            )
        )
        return jsonify({"ok": True, "my_missions": payload})
    except CustomerPulseAccessDenied as exc:
        return jsonify({"ok": False, "error": str(exc), "code": exc.code}), int(exc.http_status)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def internal_followup_orchestrator_mission_detail_api(mission_key: str):
    auth_failure = require_internal_api_token()
    if auth_failure is not None:
        return auth_failure
    access_context = _access_context()
    try:
        assert_customer_pulse_request_context(access_context)
        assert_customer_pulse_inbox_view(access_context)
        if not _followup_enabled(access_context):
            return _feature_disabled_json()
        payload = GetFollowupMissionDetailQuery()(
            FollowupMissionDetailQueryDTO(
                mission_key=_normalized_text(mission_key),
                access_context=dict(access_context),
            )
        )
        return jsonify({"ok": True, "mission": payload})
    except CustomerPulseAccessDenied as exc:
        return jsonify({"ok": False, "error": str(exc), "code": exc.code}), int(exc.http_status)
    except LookupError:
        return jsonify({"ok": False, "error": "mission not found"}), 404


def internal_followup_orchestrator_mission_action_api(mission_key: str, action_type: str):
    auth_failure = require_internal_api_token()
    if auth_failure is not None:
        return auth_failure
    access_context = _access_context()
    payload = _request_payload()
    operator = _operator(payload)
    try:
        assert_customer_pulse_request_context(access_context)
        assert_customer_pulse_inbox_view(access_context)
        if not _followup_enabled(access_context):
            return _feature_disabled_json()
        response = _mission_action_result(
            mission_key=_normalized_text(mission_key),
            action_type=_normalized_text(action_type),
            payload=payload,
        )
        _audit_followup_orchestrator_operation(
            operator=operator,
            action_type=f"followup_orchestrator_{_normalized_text(action_type)}",
            target_type="followup_orchestrator_mission",
            target_id=_normalized_text(mission_key),
            before={"request_fields": sorted(str(key) for key in payload.keys()), "path": request.path},
            after={"result": "updated"},
        )
        return response
    except CustomerPulseAccessDenied as exc:
        _audit_followup_orchestrator_operation(
            operator=operator,
            action_type=f"followup_orchestrator_{_normalized_text(action_type)}",
            target_type="followup_orchestrator_mission",
            target_id=_normalized_text(mission_key),
            before={"request_fields": sorted(str(key) for key in payload.keys()), "path": request.path},
            after={"result": "denied", "error": str(exc), "code": exc.code},
        )
        return jsonify({"ok": False, "error": str(exc), "code": exc.code}), int(exc.http_status)
    except LookupError:
        return jsonify({"ok": False, "error": "mission not found"}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def internal_followup_orchestrator_mission_item_preview_api(mission_key: str, mission_item_key: str):
    auth_failure = require_internal_api_token()
    if auth_failure is not None:
        return auth_failure
    access_context = _access_context()
    try:
        assert_customer_pulse_request_context(access_context)
        assert_customer_pulse_inbox_view(access_context)
        if not _followup_enabled(access_context):
            return _feature_disabled_json()
        payload = _request_payload()
        result = PreviewFollowupMissionItemActionCommand()(
            PreviewFollowupMissionItemActionCommandDTO(
                mission_key=_normalized_text(mission_key),
                mission_item_key=_normalized_text(mission_item_key),
                action_type=_normalized_text(payload.get("action_type")),
                actor_userid=_resolved_actor_userid(payload),
                operator=_operator(payload),
                access_context=dict(access_context),
            )
        )
        return jsonify({"ok": True, "preview": result})
    except CustomerPulseAccessDenied as exc:
        return jsonify({"ok": False, "error": str(exc), "code": exc.code}), int(exc.http_status)
    except LookupError:
        return jsonify({"ok": False, "error": "mission item not found"}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def internal_followup_orchestrator_mission_item_execute_api(mission_key: str, mission_item_key: str):
    auth_failure = require_internal_api_token()
    if auth_failure is not None:
        return auth_failure
    access_context = _access_context()
    payload = _request_payload()
    operator = _operator(payload)
    try:
        assert_customer_pulse_request_context(access_context)
        assert_customer_pulse_inbox_view(access_context)
        if not _followup_enabled(access_context):
            return _feature_disabled_json()
        result = ExecuteFollowupMissionItemActionCommand()(
            ExecuteFollowupMissionItemActionCommandDTO(
                mission_key=_normalized_text(mission_key),
                mission_item_key=_normalized_text(mission_item_key),
                action_type=_normalized_text(payload.get("action_type")),
                actor_userid=_resolved_actor_userid(payload),
                actor_role=_normalized_text(access_context.get("actor_role") or access_context.get("role") or payload.get("actor_role")),
                operator=operator,
                note=_normalized_text(payload.get("note")),
                action_payload=_normalized_action_payload(payload),
                access_context=dict(access_context),
            )
        )
        _audit_followup_orchestrator_operation(
            operator=operator,
            action_type=f"followup_orchestrator_execute_{_normalized_text(payload.get('action_type'))}",
            target_type="followup_orchestrator_mission_item",
            target_id=_normalized_text(mission_item_key),
            before={"request_fields": sorted(str(key) for key in payload.keys()), "path": request.path},
            after={"result": "updated", "mission_key": _normalized_text(mission_key)},
        )
        return jsonify({"ok": True, "result": result})
    except CustomerPulseAccessDenied as exc:
        _audit_followup_orchestrator_operation(
            operator=operator,
            action_type=f"followup_orchestrator_execute_{_normalized_text(payload.get('action_type'))}",
            target_type="followup_orchestrator_mission_item",
            target_id=_normalized_text(mission_item_key),
            before={"request_fields": sorted(str(key) for key in payload.keys()), "path": request.path},
            after={"result": "denied", "error": str(exc), "code": exc.code},
        )
        return jsonify({"ok": False, "error": str(exc), "code": exc.code}), int(exc.http_status)
    except LookupError:
        return jsonify({"ok": False, "error": "mission item not found"}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def internal_followup_orchestrator_mission_item_undo_api(mission_key: str, mission_item_key: str):
    auth_failure = require_internal_api_token()
    if auth_failure is not None:
        return auth_failure
    access_context = _access_context()
    payload = _request_payload()
    operator = _operator(payload)
    try:
        assert_customer_pulse_request_context(access_context)
        assert_customer_pulse_inbox_view(access_context)
        if not _followup_enabled(access_context):
            return _feature_disabled_json()
        result = UndoFollowupMissionItemActionCommand()(
            UndoFollowupMissionItemActionCommandDTO(
                mission_key=_normalized_text(mission_key),
                mission_item_key=_normalized_text(mission_item_key),
                execution_id=int(payload.get("execution_id") or 0),
                actor_userid=_resolved_actor_userid(payload),
                actor_role=_normalized_text(access_context.get("actor_role") or access_context.get("role") or payload.get("actor_role")),
                operator=operator,
                access_context=dict(access_context),
            )
        )
        _audit_followup_orchestrator_operation(
            operator=operator,
            action_type="followup_orchestrator_undo_executor",
            target_type="followup_orchestrator_mission_item",
            target_id=_normalized_text(mission_item_key),
            before={"request_fields": sorted(str(key) for key in payload.keys()), "path": request.path},
            after={"result": "updated", "mission_key": _normalized_text(mission_key)},
        )
        return jsonify({"ok": True, "result": result})
    except CustomerPulseAccessDenied as exc:
        return jsonify({"ok": False, "error": str(exc), "code": exc.code}), int(exc.http_status)
    except LookupError:
        return jsonify({"ok": False, "error": "mission item not found"}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def internal_followup_orchestrator_sync_api():
    auth_failure = require_internal_api_token()
    if auth_failure is not None:
        return auth_failure
    access_context = _access_context()
    try:
        assert_customer_pulse_request_context(access_context)
        assert_customer_pulse_inbox_view(access_context)
        if not _followup_enabled(access_context):
            return _feature_disabled_json()
        filters = _filters(_request_payload())
        payload = SyncFollowupMissionsCommand()(
            SyncFollowupMissionsCommandDTO(
                scope=filters["scope"],
                owner_userid=filters["owner_userid"],
                external_userid=filters["external_userid"],
                limit=_resolved_limit(filters),
                access_context=dict(access_context),
            )
        )
        return jsonify({"ok": True, "sync": payload})
    except CustomerPulseAccessDenied as exc:
        return jsonify({"ok": False, "error": str(exc), "code": exc.code}), int(exc.http_status)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def register_routes(bp):
    bp.route("/admin/followup-orchestrator", methods=["GET"])(admin_followup_orchestrator)
    bp.route("/api/admin/followup-orchestrator", methods=["GET"])(api_admin_followup_orchestrator)
    bp.route("/api/admin/followup-orchestrator/customers/<external_userid>", methods=["GET"])(api_admin_followup_orchestrator_customer)
    bp.route("/api/admin/followup-orchestrator/missions/<mission_key>", methods=["GET"])(api_admin_followup_orchestrator_mission_detail)
    bp.route("/api/admin/followup-orchestrator/missions/<mission_key>/actions/<action_type>", methods=["POST"])(api_admin_followup_orchestrator_mission_action)
    bp.route("/api/admin/followup-orchestrator/missions/<mission_key>/items/<mission_item_key>/actions/preview", methods=["POST"])(api_admin_followup_orchestrator_mission_item_preview)
    bp.route("/api/admin/followup-orchestrator/missions/<mission_key>/items/<mission_item_key>/actions/execute", methods=["POST"])(api_admin_followup_orchestrator_mission_item_execute)
    bp.route("/api/admin/followup-orchestrator/missions/<mission_key>/items/<mission_item_key>/actions/undo", methods=["POST"])(api_admin_followup_orchestrator_mission_item_undo)
    bp.route("/api/internal/followup-orchestrator/team-board", methods=["GET"])(internal_followup_orchestrator_team_board_api)
    bp.route("/api/internal/followup-orchestrator/my-missions", methods=["GET"])(internal_followup_orchestrator_my_missions_api)
    bp.route("/api/internal/followup-orchestrator/missions/<mission_key>", methods=["GET"])(internal_followup_orchestrator_mission_detail_api)
    bp.route("/api/internal/followup-orchestrator/missions/<mission_key>/actions/<action_type>", methods=["POST"])(internal_followup_orchestrator_mission_action_api)
    bp.route("/api/internal/followup-orchestrator/missions/<mission_key>/items/<mission_item_key>/actions/preview", methods=["POST"])(internal_followup_orchestrator_mission_item_preview_api)
    bp.route("/api/internal/followup-orchestrator/missions/<mission_key>/items/<mission_item_key>/actions/execute", methods=["POST"])(internal_followup_orchestrator_mission_item_execute_api)
    bp.route("/api/internal/followup-orchestrator/missions/<mission_key>/items/<mission_item_key>/actions/undo", methods=["POST"])(internal_followup_orchestrator_mission_item_undo_api)
    bp.route("/api/internal/followup-orchestrator/sync", methods=["POST"])(internal_followup_orchestrator_sync_api)
