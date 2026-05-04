from __future__ import annotations

import json
from typing import Any, Mapping, TypedDict, cast

from flask import current_app, g, has_request_context, request

from ...infra.settings import get_setting
from ..routing_config import get_owner_role

CUSTOMER_PULSE_DEFAULT_TENANT_KEY = "aicrm"
CUSTOMER_PULSE_TENANT_MODE_KEY = "CUSTOMER_PULSE_TENANT_MODE"
CUSTOMER_PULSE_EXTERNAL_ENFORCE_REQUEST_SCOPED_KEY = "CUSTOMER_PULSE_EXTERNAL_ENFORCE_REQUEST_SCOPED"
CUSTOMER_PULSE_TENANT_POLICY_KEY = "CUSTOMER_PULSE_TENANT_ACCESS_POLICY_JSON"
CUSTOMER_PULSE_LEGACY_INTERNAL_MODE = "legacy_internal"
CUSTOMER_PULSE_REQUEST_SCOPED_MODE = "request_scoped"
CUSTOMER_PULSE_TENANT_HEADER_NAMES = ("X-Tenant-Key", "X-Customer-Pulse-Tenant")
CUSTOMER_PULSE_ACTOR_USERID_HEADER = "X-Admin-Userid"
CUSTOMER_PULSE_ACTOR_ROLE_HEADER = "X-Admin-Role"
CUSTOMER_PULSE_DEFAULT_VIEWER_ROLES = {"sales", "delivery", "ops", "admin"}
CUSTOMER_PULSE_DEFAULT_OPERATOR_ROLES = {"sales", "delivery", "ops", "admin"}
CUSTOMER_PULSE_DEFAULT_INTERNAL_ROLES = {"ops", "admin"}
CUSTOMER_PULSE_PRIVILEGED_ROLES = {"ops", "admin"}
CUSTOMER_PULSE_PERMISSION_PAGE_VISIBLE = "page_visible"
CUSTOMER_PULSE_PERMISSION_VIEW_INBOX = "inbox_view"
CUSTOMER_PULSE_PERMISSION_VIEW_WIDGET = "widget_view"
CUSTOMER_PULSE_PERMISSION_VIEW_EVIDENCE = "evidence_view"
CUSTOMER_PULSE_PERMISSION_GENERATE_REPLY_DRAFT = "generate_reply_draft"
CUSTOMER_PULSE_PERMISSION_CREATE_FOLLOWUP_TASK = "create_followup_task"
CUSTOMER_PULSE_PERMISSION_UPDATE_FOLLOWUP_SEGMENT = "update_followup_segment"
CUSTOMER_PULSE_PERMISSION_UPDATE_TAGS = "update_tags"
CUSTOMER_PULSE_PERMISSION_SET_FOLLOWUP_REMINDER = "set_followup_reminder"
CUSTOMER_PULSE_PERMISSION_SUBMIT_FEEDBACK = "submit_feedback"
CUSTOMER_PULSE_ACTION_PERMISSION_MAP = {
    "generate_reply_draft": CUSTOMER_PULSE_PERMISSION_GENERATE_REPLY_DRAFT,
    "create_followup_task": CUSTOMER_PULSE_PERMISSION_CREATE_FOLLOWUP_TASK,
    "update_followup_segment": CUSTOMER_PULSE_PERMISSION_UPDATE_FOLLOWUP_SEGMENT,
    "update_tags": CUSTOMER_PULSE_PERMISSION_UPDATE_TAGS,
    "set_followup_reminder": CUSTOMER_PULSE_PERMISSION_SET_FOLLOWUP_REMINDER,
}
CUSTOMER_PULSE_VIEW_PERMISSIONS = {
    CUSTOMER_PULSE_PERMISSION_PAGE_VISIBLE,
    CUSTOMER_PULSE_PERMISSION_VIEW_INBOX,
    CUSTOMER_PULSE_PERMISSION_VIEW_WIDGET,
}
CUSTOMER_PULSE_ALL_PERMISSIONS = frozenset(
    {
        *CUSTOMER_PULSE_VIEW_PERMISSIONS,
        CUSTOMER_PULSE_PERMISSION_VIEW_EVIDENCE,
        CUSTOMER_PULSE_PERMISSION_SUBMIT_FEEDBACK,
        *CUSTOMER_PULSE_ACTION_PERMISSION_MAP.values(),
    }
)


class CustomerPulseTenantContext(TypedDict, total=False):
    mode: str
    auth_mode: str
    valid: bool
    legacy_mode: bool
    tenant_key: str
    user_id: str
    role: str
    source: str
    tenant_source: str
    user_source: str
    role_source: str
    actor_userid: str
    actor_role: str
    operator: str
    policy: dict[str, Any]
    allowed_owner_userids: list[str]
    member_userids: list[str]
    viewer_roles: list[str]
    operator_roles: list[str]
    internal_roles: list[str]
    permissions_by_role: dict[str, list[str]]
    permissions_by_userid: dict[str, list[str]]
    granted_permissions: list[str]
    can_view_all: bool
    error_code: str
    error_message: str
    http_status: int


class CustomerPulseAccessDenied(PermissionError):
    def __init__(self, message: str, *, code: str = "customer_pulse_access_denied", http_status: int = 403):
        super().__init__(message)
        self.code = code
        self.http_status = int(http_status)


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _normalized_csv_set(value: Any) -> set[str]:
    if isinstance(value, (list, tuple, set)):
        return {_normalized_text(item) for item in value if _normalized_text(item)}
    return {
        _normalized_text(item)
        for item in _normalized_text(value).replace("|", ",").split(",")
        if _normalized_text(item)
    }


def _normalized_permission_set(value: Any) -> set[str]:
    raw_permissions = _normalized_csv_set(value)
    if "all" in raw_permissions or "*" in raw_permissions:
        return set(CUSTOMER_PULSE_ALL_PERMISSIONS)
    return {item for item in raw_permissions if item in CUSTOMER_PULSE_ALL_PERMISSIONS}


def _normalized_permission_map(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, list[str]] = {}
    for actor_key, permission_values in value.items():
        normalized_actor_key = _normalized_text(actor_key).lower()
        if not normalized_actor_key:
            continue
        normalized[normalized_actor_key] = sorted(_normalized_permission_set(permission_values))
    return normalized


def _json_loads(value: Any, *, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    text = _normalized_text(value)
    if not text:
        return default
    try:
        return json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _config_value(key: str, default: Any = "") -> Any:
    stored = get_setting(key)
    if stored not in (None, ""):
        return stored
    return current_app.config.get(key, default)


def customer_pulse_tenant_mode() -> str:
    normalized = _normalized_text(_config_value(CUSTOMER_PULSE_TENANT_MODE_KEY, CUSTOMER_PULSE_LEGACY_INTERNAL_MODE)).lower()
    if normalized not in {CUSTOMER_PULSE_LEGACY_INTERNAL_MODE, CUSTOMER_PULSE_REQUEST_SCOPED_MODE}:
        return CUSTOMER_PULSE_LEGACY_INTERNAL_MODE
    return normalized


def customer_pulse_external_request_scoped_enforced() -> bool:
    normalized = _normalized_text(_config_value(CUSTOMER_PULSE_EXTERNAL_ENFORCE_REQUEST_SCOPED_KEY, "")).lower()
    return normalized in {"1", "true", "yes", "y", "on"}


def customer_pulse_is_request_scoped_mode() -> bool:
    return customer_pulse_tenant_mode() == CUSTOMER_PULSE_REQUEST_SCOPED_MODE


def customer_pulse_default_tenant_key() -> str:
    return CUSTOMER_PULSE_DEFAULT_TENANT_KEY


def customer_pulse_scoped_key(*, tenant_key: str, base_key: str) -> str:
    normalized_tenant_key = _normalized_text(tenant_key) or CUSTOMER_PULSE_DEFAULT_TENANT_KEY
    normalized_base_key = _normalized_text(base_key)
    if not normalized_base_key:
        return ""
    if normalized_tenant_key == CUSTOMER_PULSE_DEFAULT_TENANT_KEY:
        return normalized_base_key
    return f"{normalized_tenant_key}:{normalized_base_key}"


def _tenant_policy_map() -> dict[str, dict[str, Any]]:
    raw = _json_loads(_config_value(CUSTOMER_PULSE_TENANT_POLICY_KEY, "{}"), default={})
    if not isinstance(raw, dict):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for tenant_key, value in raw.items():
        normalized_tenant_key = _normalized_text(tenant_key)
        if not normalized_tenant_key or not isinstance(value, dict):
            continue
        owner_userids = _normalized_csv_set(value.get("owner_userids") or value.get("ownerUserids"))
        member_userids = _normalized_csv_set(value.get("member_userids") or value.get("memberUserids")) or set(owner_userids)
        viewer_roles = _normalized_csv_set(value.get("viewer_roles") or value.get("viewerRoles")) or set(CUSTOMER_PULSE_DEFAULT_VIEWER_ROLES)
        operator_roles = _normalized_csv_set(value.get("operator_roles") or value.get("operatorRoles")) or set(CUSTOMER_PULSE_DEFAULT_OPERATOR_ROLES)
        internal_roles = _normalized_csv_set(value.get("internal_roles") or value.get("internalRoles")) or set(CUSTOMER_PULSE_DEFAULT_INTERNAL_ROLES)
        permissions_by_role = _normalized_permission_map(value.get("permissions_by_role") or value.get("permissionsByRole"))
        permissions_by_userid = _normalized_permission_map(value.get("permissions_by_userid") or value.get("permissionsByUserid") or value.get("permissionsByUserId"))
        result[normalized_tenant_key] = {
            "tenant_key": normalized_tenant_key,
            "owner_userids": sorted(owner_userids),
            "member_userids": sorted(member_userids),
            "viewer_roles": sorted(viewer_roles),
            "operator_roles": sorted(operator_roles),
            "internal_roles": sorted(internal_roles),
            "permissions_by_role": permissions_by_role,
            "permissions_by_userid": permissions_by_userid,
            "notes": _normalized_text(value.get("notes")),
        }
    return result


def _default_permissions_for_context(context: Mapping[str, Any] | None) -> set[str]:
    normalized_context = dict(context or {})
    if normalized_context.get("legacy_mode"):
        return set(CUSTOMER_PULSE_ALL_PERMISSIONS)
    actor_role = _normalized_text(normalized_context.get("actor_role") or normalized_context.get("role")).lower()
    viewer_roles = {_normalized_text(item).lower() for item in normalized_context.get("viewer_roles", []) if _normalized_text(item)}
    operator_roles = {_normalized_text(item).lower() for item in normalized_context.get("operator_roles", []) if _normalized_text(item)}
    permissions: set[str] = set()
    if actor_role in viewer_roles:
        permissions.update(CUSTOMER_PULSE_VIEW_PERMISSIONS)
        permissions.add(CUSTOMER_PULSE_PERMISSION_VIEW_EVIDENCE)
    if actor_role in operator_roles:
        permissions.update(CUSTOMER_PULSE_ACTION_PERMISSION_MAP.values())
        permissions.add(CUSTOMER_PULSE_PERMISSION_SUBMIT_FEEDBACK)
        permissions.update(CUSTOMER_PULSE_VIEW_PERMISSIONS)
        permissions.add(CUSTOMER_PULSE_PERMISSION_VIEW_EVIDENCE)
    return permissions


def customer_pulse_effective_permissions(access_context: Mapping[str, Any] | None = None) -> set[str]:
    context = dict(access_context or current_customer_pulse_request_access_context())
    if not context:
        return set()
    if context.get("legacy_mode"):
        return set(CUSTOMER_PULSE_ALL_PERMISSIONS)
    if not bool(context.get("valid", False)):
        return set()
    actor_role = _normalized_text(context.get("actor_role") or context.get("role")).lower()
    actor_userid = _normalized_text(context.get("actor_userid") or context.get("user_id")).lower()
    permissions_by_userid = _normalized_permission_map(context.get("permissions_by_userid"))
    permissions_by_role = _normalized_permission_map(context.get("permissions_by_role"))
    if actor_userid and actor_userid in permissions_by_userid:
        return set(_normalized_permission_set(permissions_by_userid.get(actor_userid)))
    if actor_role and actor_role in permissions_by_role:
        return set(_normalized_permission_set(permissions_by_role.get(actor_role)))
    granted_permissions = _normalized_permission_set(context.get("granted_permissions"))
    if granted_permissions:
        return granted_permissions
    return _default_permissions_for_context(context)


def customer_pulse_permission_summary(access_context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    permissions = customer_pulse_effective_permissions(access_context)
    action_permissions = {
        action_type: permission_key in permissions
        for action_type, permission_key in CUSTOMER_PULSE_ACTION_PERMISSION_MAP.items()
    }
    return {
        "page_visible": CUSTOMER_PULSE_PERMISSION_PAGE_VISIBLE in permissions,
        "inbox_view": CUSTOMER_PULSE_PERMISSION_VIEW_INBOX in permissions,
        "widget_view": CUSTOMER_PULSE_PERMISSION_VIEW_WIDGET in permissions,
        "evidence_view": CUSTOMER_PULSE_PERMISSION_VIEW_EVIDENCE in permissions,
        "submit_feedback": CUSTOMER_PULSE_PERMISSION_SUBMIT_FEEDBACK in permissions,
        "action_permissions": action_permissions,
        "allowed_action_types": [action_type for action_type, allowed in action_permissions.items() if allowed],
        "can_execute_any": any(action_permissions.values()),
    }


def customer_pulse_has_permission(permission: str, *, access_context: Mapping[str, Any] | None = None) -> bool:
    return _normalized_text(permission) in customer_pulse_effective_permissions(access_context)


def customer_pulse_has_any_permission(
    permissions: list[str] | tuple[str, ...] | set[str],
    *,
    access_context: Mapping[str, Any] | None = None,
) -> bool:
    effective_permissions = customer_pulse_effective_permissions(access_context)
    return any(_normalized_text(permission) in effective_permissions for permission in permissions)


def customer_pulse_action_permission(action_type: Any) -> str:
    return CUSTOMER_PULSE_ACTION_PERMISSION_MAP.get(_normalized_text(action_type), "")


def _request_value(*keys: str) -> str:
    if not has_request_context():
        return ""
    json_payload = request.get_json(silent=True) or {}
    for key in keys:
        normalized_key = _normalized_text(key)
        if not normalized_key:
            continue
        header_value = _normalized_text(request.headers.get(normalized_key))
        if header_value:
            return header_value
        value = _normalized_text(request.values.get(normalized_key))
        if value:
            return value
        if isinstance(json_payload, dict):
            json_value = _normalized_text(json_payload.get(normalized_key))
            if json_value:
                return json_value
    return ""


def _request_candidates(*keys: str) -> list[tuple[str, str]]:
    if not has_request_context():
        return []
    json_payload = request.get_json(silent=True) or {}
    candidates: list[tuple[str, str]] = []
    for key in keys:
        normalized_key = _normalized_text(key)
        if not normalized_key:
            continue
        header_value = _normalized_text(request.headers.get(normalized_key))
        if header_value:
            candidates.append((f"header:{normalized_key.lower()}", header_value))
        value = _normalized_text(request.values.get(normalized_key))
        if value:
            candidates.append((f"param:{normalized_key}", value))
        if isinstance(json_payload, dict):
            json_value = _normalized_text(json_payload.get(normalized_key))
            if json_value:
                candidates.append((f"json:{normalized_key}", json_value))
    return candidates


def _resolve_request_value(*keys: str) -> tuple[str, str, str]:
    candidates = _request_candidates(*keys)
    if not candidates:
        return "", "", ""
    unique_values = {value for _, value in candidates if value}
    if len(unique_values) > 1:
        return "", "", "request_value_conflict"
    source, value = candidates[0]
    return value, source, ""


def build_customer_pulse_legacy_tenant_context(
    *,
    operator: str = "system",
    user_id: str = "",
    role: str = "",
    source: str = "legacy_internal",
) -> CustomerPulseTenantContext:
    normalized_user_id = _normalized_text(user_id)
    normalized_role = _normalized_text(role)
    normalized_operator = _normalized_text(operator) or normalized_user_id or "system"
    return {
        "mode": CUSTOMER_PULSE_LEGACY_INTERNAL_MODE,
        "auth_mode": CUSTOMER_PULSE_LEGACY_INTERNAL_MODE,
        "valid": True,
        "legacy_mode": True,
        "tenant_key": CUSTOMER_PULSE_DEFAULT_TENANT_KEY,
        "user_id": normalized_user_id,
        "role": normalized_role,
        "source": _normalized_text(source) or "legacy_internal",
        "tenant_source": "legacy_internal",
        "user_source": _normalized_text(source) or "legacy_internal",
        "role_source": _normalized_text(source) or "legacy_internal",
        "actor_userid": normalized_user_id,
        "actor_role": normalized_role,
        "operator": normalized_operator,
        "policy": {},
        "allowed_owner_userids": [],
        "member_userids": [],
        "viewer_roles": sorted(CUSTOMER_PULSE_DEFAULT_VIEWER_ROLES),
        "operator_roles": sorted(CUSTOMER_PULSE_DEFAULT_OPERATOR_ROLES),
        "internal_roles": sorted(CUSTOMER_PULSE_DEFAULT_INTERNAL_ROLES),
        "permissions_by_role": {},
        "permissions_by_userid": {},
        "granted_permissions": sorted(CUSTOMER_PULSE_ALL_PERMISSIONS),
        "can_view_all": True,
        "error_code": "",
        "error_message": "",
        "http_status": 200,
    }


def customer_pulse_tenant_context_summary(tenant_context: Mapping[str, Any] | None) -> dict[str, Any]:
    context = dict(tenant_context or {})
    return {
        "tenant_key": _normalized_text(context.get("tenant_key")) or CUSTOMER_PULSE_DEFAULT_TENANT_KEY,
        "user_id": _normalized_text(context.get("user_id") or context.get("actor_userid")),
        "role": _normalized_text(context.get("role") or context.get("actor_role")),
        "source": _normalized_text(context.get("source")) or "unknown",
        "auth_mode": _normalized_text(context.get("auth_mode")) or CUSTOMER_PULSE_LEGACY_INTERNAL_MODE,
        "valid": bool(context.get("valid", True)),
        "legacy_mode": bool(context.get("legacy_mode")),
        "permissions": customer_pulse_permission_summary(context),
    }


def customer_pulse_context_tenant_key(
    tenant_context: Mapping[str, Any] | None,
    *,
    require_valid: bool = True,
) -> str:
    context = dict(tenant_context or {})
    if require_valid and not bool(context.get("valid", False)):
        raise CustomerPulseAccessDenied(
            _normalized_text(context.get("error_message")) or "Customer Pulse tenant context 无效。",
            code=_normalized_text(context.get("error_code")) or "tenant_context_required",
            http_status=int(context.get("http_status") or 403),
        )
    return _normalized_text(context.get("tenant_key")) or CUSTOMER_PULSE_DEFAULT_TENANT_KEY


def resolve_customer_pulse_request_access_context() -> CustomerPulseTenantContext:
    mode = customer_pulse_tenant_mode()
    external_request_scoped_required = customer_pulse_external_request_scoped_enforced()
    if external_request_scoped_required and mode != CUSTOMER_PULSE_REQUEST_SCOPED_MODE:
        return {
            "mode": mode,
            "auth_mode": mode,
            "valid": False,
            "legacy_mode": False,
            "tenant_key": CUSTOMER_PULSE_DEFAULT_TENANT_KEY,
            "user_id": "",
            "role": "",
            "source": "external_request_scoped_guard",
            "tenant_source": "",
            "user_source": "",
            "role_source": "",
            "actor_userid": "",
            "actor_role": "",
            "operator": "system",
            "policy": {},
            "allowed_owner_userids": [],
            "member_userids": [],
            "viewer_roles": sorted(CUSTOMER_PULSE_DEFAULT_VIEWER_ROLES),
            "operator_roles": sorted(CUSTOMER_PULSE_DEFAULT_OPERATOR_ROLES),
            "internal_roles": sorted(CUSTOMER_PULSE_DEFAULT_INTERNAL_ROLES),
            "permissions_by_role": {},
            "permissions_by_userid": {},
            "granted_permissions": [],
            "can_view_all": False,
            "error_code": "tenant_mode_misconfigured",
            "error_message": "当前部署环境强制 Customer Pulse 使用 request-scoped tenant mode，禁止继续使用 legacy_internal。",
            "http_status": 503,
        }
    if not has_request_context():
        if mode == CUSTOMER_PULSE_LEGACY_INTERNAL_MODE:
            return build_customer_pulse_legacy_tenant_context(operator="system", source="legacy_internal_no_request")
        return {
            "mode": mode,
            "auth_mode": CUSTOMER_PULSE_REQUEST_SCOPED_MODE,
            "valid": False,
            "legacy_mode": False,
            "tenant_key": CUSTOMER_PULSE_DEFAULT_TENANT_KEY,
            "user_id": "",
            "role": "",
            "source": "missing_request_context",
            "tenant_source": "",
            "user_source": "",
            "role_source": "",
            "actor_userid": "",
            "actor_role": "",
            "operator": "system",
            "policy": {},
            "allowed_owner_userids": [],
            "member_userids": [],
            "viewer_roles": sorted(CUSTOMER_PULSE_DEFAULT_VIEWER_ROLES),
            "operator_roles": sorted(CUSTOMER_PULSE_DEFAULT_OPERATOR_ROLES),
            "internal_roles": sorted(CUSTOMER_PULSE_DEFAULT_INTERNAL_ROLES),
            "permissions_by_role": {},
            "permissions_by_userid": {},
            "granted_permissions": [],
            "can_view_all": False,
            "error_code": "tenant_context_required",
            "error_message": "当前环境要求显式 tenant context，后台未注入请求级租户信息。",
            "http_status": 403,
        }

    tenant_key, tenant_source, tenant_conflict = _resolve_request_value(*CUSTOMER_PULSE_TENANT_HEADER_NAMES, "tenant_key")
    actor_userid, user_source, _user_conflict = _resolve_request_value(
        CUSTOMER_PULSE_ACTOR_USERID_HEADER,
        "admin_userid",
        "actor_userid",
    )
    operator, operator_source, _operator_conflict = _resolve_request_value(
        "X-Admin-Operator",
        "operator",
        CUSTOMER_PULSE_ACTOR_USERID_HEADER,
        "admin_userid",
    )
    explicit_role, role_source, role_conflict = _resolve_request_value(CUSTOMER_PULSE_ACTOR_ROLE_HEADER, "admin_role", "actor_role")
    owner_role = get_owner_role(actor_userid) if actor_userid else None
    actor_role = _normalized_text((owner_role or {}).get("role")) or explicit_role.lower()
    policy = _tenant_policy_map().get(_normalized_text(tenant_key), {})
    allowed_owner_userids = sorted({_normalized_text(item) for item in policy.get("owner_userids", []) if _normalized_text(item)})
    member_userids = sorted({_normalized_text(item) for item in policy.get("member_userids", []) if _normalized_text(item)})
    viewer_roles = {_normalized_text(item) for item in policy.get("viewer_roles", []) if _normalized_text(item)}
    operator_roles = {_normalized_text(item) for item in policy.get("operator_roles", []) if _normalized_text(item)}
    internal_roles = {_normalized_text(item) for item in policy.get("internal_roles", []) if _normalized_text(item)}
    permissions_by_role = _normalized_permission_map(policy.get("permissions_by_role"))
    permissions_by_userid = _normalized_permission_map(policy.get("permissions_by_userid"))
    error_code = ""
    error_message = ""
    http_status = 200
    valid = True

    if mode == CUSTOMER_PULSE_REQUEST_SCOPED_MODE:
        if tenant_conflict:
            valid = False
            error_code = "tenant_context_conflict"
            error_message = "请求中的 tenant_key 存在冲突，请确保 header、query、body 只传同一个 tenant。"
            http_status = 400
        elif role_conflict:
            valid = False
            error_code = "actor_role_conflict"
            error_message = "请求中的 admin role 存在冲突，请确保 header、query、body 只传同一个角色。"
            http_status = 400
        elif not _normalized_text(tenant_key):
            valid = False
            error_code = "tenant_context_required"
            error_message = "当前环境要求 request-scoped tenant context，缺少 tenant_key。"
            http_status = 403
        elif not policy:
            valid = False
            error_code = "tenant_invalid"
            error_message = "当前 tenant 不存在或未配置 Customer Pulse 访问策略。"
            http_status = 403
        elif not actor_userid:
            valid = False
            error_code = "actor_required"
            error_message = "当前环境要求显式 actor_userid，缺少后台操作者身份。"
            http_status = 403
        elif not actor_role:
            valid = False
            error_code = "actor_role_required"
            error_message = "当前环境无法识别后台角色，拒绝访问 Customer Pulse。"
            http_status = 403
        elif member_userids and actor_userid not in member_userids:
            valid = False
            error_code = "actor_outside_tenant"
            error_message = "当前操作者不在 tenant 允许名单内，拒绝访问 Customer Pulse。"
            http_status = 403
        elif not allowed_owner_userids:
            valid = False
            error_code = "tenant_owner_scope_missing"
            error_message = "当前 tenant 没有配置 owner scope，拒绝访问 Customer Pulse。"
            http_status = 403

    base_context: CustomerPulseTenantContext = {
        "mode": mode,
        "auth_mode": CUSTOMER_PULSE_LEGACY_INTERNAL_MODE if mode == CUSTOMER_PULSE_LEGACY_INTERNAL_MODE else CUSTOMER_PULSE_REQUEST_SCOPED_MODE,
        "valid": valid,
        "legacy_mode": mode == CUSTOMER_PULSE_LEGACY_INTERNAL_MODE,
        "tenant_key": _normalized_text(tenant_key) or CUSTOMER_PULSE_DEFAULT_TENANT_KEY,
        "user_id": _normalized_text(actor_userid),
        "role": _normalized_text(actor_role),
        "source": "legacy_internal" if mode == CUSTOMER_PULSE_LEGACY_INTERNAL_MODE else "request_context",
        "tenant_source": _normalized_text(tenant_source),
        "user_source": _normalized_text(user_source),
        "role_source": _normalized_text(role_source),
        "actor_userid": _normalized_text(actor_userid),
        "actor_role": _normalized_text(actor_role),
        "operator": _normalized_text(operator) or _normalized_text(actor_userid) or "crm_console",
        "policy": policy,
        "allowed_owner_userids": allowed_owner_userids,
        "member_userids": member_userids,
        "viewer_roles": sorted(viewer_roles or CUSTOMER_PULSE_DEFAULT_VIEWER_ROLES),
        "operator_roles": sorted(operator_roles or CUSTOMER_PULSE_DEFAULT_OPERATOR_ROLES),
        "internal_roles": sorted(internal_roles or CUSTOMER_PULSE_DEFAULT_INTERNAL_ROLES),
        "permissions_by_role": permissions_by_role,
        "permissions_by_userid": permissions_by_userid,
        "granted_permissions": [],
        "can_view_all": _normalized_text(actor_role) in CUSTOMER_PULSE_PRIVILEGED_ROLES,
        "error_code": error_code,
        "error_message": error_message,
        "http_status": http_status,
    }
    base_context["granted_permissions"] = sorted(customer_pulse_effective_permissions(base_context))
    return base_context


def current_customer_pulse_request_access_context() -> CustomerPulseTenantContext:
    if has_request_context():
        cached = getattr(g, "customer_pulse_access_context", None)
        if isinstance(cached, dict):
            return cast(CustomerPulseTenantContext, cached)
        resolved = resolve_customer_pulse_request_access_context()
        g.customer_pulse_access_context = resolved
        return resolved
    return resolve_customer_pulse_request_access_context()


def bind_customer_pulse_request_context() -> None:
    if has_request_context():
        g.customer_pulse_access_context = resolve_customer_pulse_request_access_context()


def customer_pulse_template_access_payload(access_context: Mapping[str, Any] | None) -> dict[str, Any]:
    context = dict(access_context or {})
    return {
        "mode": _normalized_text(context.get("mode")) or CUSTOMER_PULSE_LEGACY_INTERNAL_MODE,
        "auth_mode": _normalized_text(context.get("auth_mode")) or CUSTOMER_PULSE_LEGACY_INTERNAL_MODE,
        "tenant_key": _normalized_text(context.get("tenant_key")) or CUSTOMER_PULSE_DEFAULT_TENANT_KEY,
        "actor_userid": _normalized_text(context.get("actor_userid") or context.get("user_id")),
        "actor_role": _normalized_text(context.get("actor_role") or context.get("role")),
        "source": _normalized_text(context.get("source")),
        "valid": bool(context.get("valid", True)),
        "can_view_all": bool(context.get("can_view_all")),
        "permissions": customer_pulse_permission_summary(context),
    }


def assert_customer_pulse_request_context(
    access_context: Mapping[str, Any] | None = None,
) -> CustomerPulseTenantContext:
    context = dict(access_context or current_customer_pulse_request_access_context())
    if context.get("legacy_mode"):
        return cast(CustomerPulseTenantContext, context)
    if bool(context.get("valid")):
        return cast(CustomerPulseTenantContext, context)
    raise CustomerPulseAccessDenied(
        _normalized_text(context.get("error_message")) or "Customer Pulse 当前不可访问。",
        code=_normalized_text(context.get("error_code")) or "customer_pulse_access_denied",
        http_status=int(context.get("http_status") or 403),
    )


def assert_customer_pulse_permission(
    permission: str,
    *,
    access_context: Mapping[str, Any] | None = None,
    message: str,
    code: str,
    http_status: int = 403,
) -> CustomerPulseTenantContext:
    context = assert_customer_pulse_request_context(access_context)
    if context.get("legacy_mode"):
        return context
    if _normalized_text(permission) in customer_pulse_effective_permissions(context):
        return context
    raise CustomerPulseAccessDenied(message, code=code, http_status=http_status)


def assert_customer_pulse_any_permission(
    permissions: list[str] | tuple[str, ...] | set[str],
    *,
    access_context: Mapping[str, Any] | None = None,
    message: str,
    code: str,
    http_status: int = 403,
) -> CustomerPulseTenantContext:
    context = assert_customer_pulse_request_context(access_context)
    if context.get("legacy_mode"):
        return context
    if customer_pulse_has_any_permission(permissions, access_context=context):
        return context
    raise CustomerPulseAccessDenied(message, code=code, http_status=http_status)


def assert_customer_pulse_page_visible(access_context: Mapping[str, Any] | None = None) -> CustomerPulseTenantContext:
    return assert_customer_pulse_permission(
        CUSTOMER_PULSE_PERMISSION_PAGE_VISIBLE,
        access_context=access_context,
        message="当前角色没有查看 AI推进 页面入口的权限。",
        code="page_permission_forbidden",
    )


def assert_customer_pulse_inbox_view(access_context: Mapping[str, Any] | None = None) -> CustomerPulseTenantContext:
    return assert_customer_pulse_permission(
        CUSTOMER_PULSE_PERMISSION_VIEW_INBOX,
        access_context=access_context,
        message="当前角色没有查看 Customer Pulse 收件箱的权限。",
        code="inbox_view_forbidden",
    )


def assert_customer_pulse_widget_view(access_context: Mapping[str, Any] | None = None) -> CustomerPulseTenantContext:
    return assert_customer_pulse_permission(
        CUSTOMER_PULSE_PERMISSION_VIEW_WIDGET,
        access_context=access_context,
        message="当前角色没有查看客户详情 AI 下一步组件的权限。",
        code="widget_view_forbidden",
    )


def assert_customer_pulse_evidence_view(access_context: Mapping[str, Any] | None = None) -> CustomerPulseTenantContext:
    return assert_customer_pulse_permission(
        CUSTOMER_PULSE_PERMISSION_VIEW_EVIDENCE,
        access_context=access_context,
        message="当前角色没有查看原始证据的权限。",
        code="evidence_view_forbidden",
    )


def assert_customer_pulse_feedback_permission(access_context: Mapping[str, Any] | None = None) -> CustomerPulseTenantContext:
    return assert_customer_pulse_permission(
        CUSTOMER_PULSE_PERMISSION_SUBMIT_FEEDBACK,
        access_context=access_context,
        message="当前角色没有提交 Customer Pulse 反馈的权限。",
        code="feedback_permission_forbidden",
    )


def assert_customer_pulse_action_permission(
    action_type: Any,
    *,
    access_context: Mapping[str, Any] | None = None,
) -> CustomerPulseTenantContext:
    permission_key = customer_pulse_action_permission(action_type)
    if not permission_key:
        raise CustomerPulseAccessDenied("当前动作未注册到 Customer Pulse 权限矩阵。", code="action_permission_unmapped", http_status=403)
    return assert_customer_pulse_permission(
        permission_key,
        access_context=access_context,
        message="当前角色没有执行该 Customer Pulse 动作的权限。",
        code="action_permission_denied",
    )


def resolve_customer_pulse_read_scope(
    *,
    requested_owner_userid: str = "",
    access_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    context = assert_customer_pulse_request_context(access_context)
    tenant_key = _normalized_text(context.get("tenant_key")) or CUSTOMER_PULSE_DEFAULT_TENANT_KEY
    normalized_requested_owner_userid = _normalized_text(requested_owner_userid)
    if context.get("legacy_mode"):
        return {
            "tenant_key": tenant_key,
            "owner_userid_filter": normalized_requested_owner_userid,
            "allowed_owner_userids": [],
            "actor_userid": _normalized_text(context.get("actor_userid") or context.get("user_id")),
            "actor_role": _normalized_text(context.get("actor_role") or context.get("role")),
            "operator": _normalized_text(context.get("operator")) or "crm_console",
            "can_view_all": True,
            "tenant_context": context,
        }
    viewer_roles = {_normalized_text(item) for item in context.get("viewer_roles", []) if _normalized_text(item)}
    actor_role = _normalized_text(context.get("actor_role"))
    actor_userid = _normalized_text(context.get("actor_userid"))
    if actor_role not in viewer_roles:
        raise CustomerPulseAccessDenied("当前角色没有查看 Customer Pulse 的权限。", code="viewer_role_forbidden", http_status=403)
    allowed_owner_userids = [_normalized_text(item) for item in context.get("allowed_owner_userids", []) if _normalized_text(item)]
    if bool(context.get("can_view_all")):
        if normalized_requested_owner_userid and normalized_requested_owner_userid not in allowed_owner_userids:
            raise CustomerPulseAccessDenied("请求的 owner scope 不在当前 tenant 范围内。", code="owner_scope_forbidden", http_status=403)
        return {
            "tenant_key": tenant_key,
            "owner_userid_filter": normalized_requested_owner_userid,
            "allowed_owner_userids": allowed_owner_userids,
            "actor_userid": actor_userid,
            "actor_role": actor_role,
            "operator": _normalized_text(context.get("operator")) or actor_userid or "crm_console",
            "can_view_all": True,
            "tenant_context": context,
        }
    if actor_userid not in allowed_owner_userids:
        raise CustomerPulseAccessDenied("当前操作者不在 tenant owner scope 内。", code="actor_owner_scope_forbidden", http_status=403)
    if normalized_requested_owner_userid and normalized_requested_owner_userid != actor_userid:
        raise CustomerPulseAccessDenied("当前角色只能查看自己的客户。", code="owner_scope_forbidden", http_status=403)
    return {
        "tenant_key": tenant_key,
        "owner_userid_filter": actor_userid,
        "allowed_owner_userids": [actor_userid],
        "actor_userid": actor_userid,
        "actor_role": actor_role,
        "operator": _normalized_text(context.get("operator")) or actor_userid or "crm_console",
        "can_view_all": False,
        "tenant_context": context,
    }


def assert_customer_pulse_target_owner_access(
    target_owner_userid: str,
    *,
    require_operator: bool,
    access_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    context = assert_customer_pulse_request_context(access_context)
    if context.get("legacy_mode"):
        return {
            "tenant_key": _normalized_text(context.get("tenant_key")) or CUSTOMER_PULSE_DEFAULT_TENANT_KEY,
            "operator": _normalized_text(context.get("operator")) or "crm_console",
            "actor_userid": _normalized_text(context.get("actor_userid") or context.get("user_id")),
            "actor_role": _normalized_text(context.get("actor_role") or context.get("role")),
            "tenant_context": context,
        }
    normalized_target_owner_userid = _normalized_text(target_owner_userid)
    if not normalized_target_owner_userid:
        raise CustomerPulseAccessDenied("当前客户缺少 owner_userid，拒绝继续访问。", code="missing_owner_userid", http_status=403)
    allowed_owner_userids = {_normalized_text(item) for item in context.get("allowed_owner_userids", []) if _normalized_text(item)}
    if normalized_target_owner_userid not in allowed_owner_userids:
        raise CustomerPulseAccessDenied("目标客户不在当前 tenant owner scope 内。", code="cross_tenant_owner_scope", http_status=403)
    actor_role = _normalized_text(context.get("actor_role"))
    actor_userid = _normalized_text(context.get("actor_userid"))
    role_allowlist = (
        {_normalized_text(item) for item in context.get("operator_roles", []) if _normalized_text(item)}
        if require_operator
        else {_normalized_text(item) for item in context.get("viewer_roles", []) if _normalized_text(item)}
    )
    if actor_role not in role_allowlist:
        raise CustomerPulseAccessDenied("当前角色没有执行 Customer Pulse 动作的权限。", code="operator_role_forbidden", http_status=403)
    if not bool(context.get("can_view_all")) and actor_userid != normalized_target_owner_userid:
        raise CustomerPulseAccessDenied("当前角色不能操作其他负责人的客户。", code="owner_scope_forbidden", http_status=403)
    return {
        "tenant_key": _normalized_text(context.get("tenant_key")) or CUSTOMER_PULSE_DEFAULT_TENANT_KEY,
        "operator": _normalized_text(context.get("operator")) or actor_userid or "crm_console",
        "actor_userid": actor_userid,
        "actor_role": actor_role,
        "tenant_context": context,
    }


def assert_customer_pulse_internal_job_access(access_context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    context = assert_customer_pulse_request_context(access_context)
    if context.get("legacy_mode"):
        return {
            "tenant_key": _normalized_text(context.get("tenant_key")) or CUSTOMER_PULSE_DEFAULT_TENANT_KEY,
            "operator": _normalized_text(context.get("operator")) or "internal_api",
            "allowed_owner_userids": [],
            "tenant_context": context,
        }
    actor_role = _normalized_text(context.get("actor_role"))
    internal_roles = {_normalized_text(item) for item in context.get("internal_roles", []) if _normalized_text(item)}
    if actor_role not in internal_roles:
        raise CustomerPulseAccessDenied("当前角色没有触发 Customer Pulse 内部作业的权限。", code="internal_role_forbidden", http_status=403)
    return {
        "tenant_key": _normalized_text(context.get("tenant_key")) or CUSTOMER_PULSE_DEFAULT_TENANT_KEY,
        "operator": _normalized_text(context.get("operator")) or _normalized_text(context.get("actor_userid")) or "internal_api",
        "allowed_owner_userids": [
            _normalized_text(item) for item in context.get("allowed_owner_userids", []) if _normalized_text(item)
        ],
        "tenant_context": context,
    }
