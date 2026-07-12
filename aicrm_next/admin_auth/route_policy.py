from __future__ import annotations

import hashlib
import hmac
import json
import os
from collections import defaultdict, deque
from threading import RLock
from time import monotonic
from typing import Any
from urllib.parse import parse_qs

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool

from aicrm_next.shared.route_policy import RoutePolicy, RoutePolicyIndex, match_route_policy
from aicrm_next.shared.internal_service_tokens import validate_internal_service_token
from aicrm_next.shared.runtime import production_environment
from aicrm_next.shared.signed_context import load_sidebar_owner_context_token

from .capabilities import session_can, viewer_only
from .guards import admin_auth_enforcement_enabled, admin_auth_required_response, admin_page_auth_redirect, current_admin_session
from .session_state import validate_admin_session_state
from .service import CSRF_COOKIE, csrf_token_from_session, normalize_text, route_headers


SIDEBAR_OWNER_TOKEN_HEADER = "x-aicrm-sidebar-owner-token"
CSRF_HEADER = "x-csrf-token"
ROUTE_POLICY_ENFORCEMENT_ENV = "AICRM_ROUTE_POLICY_ENFORCED"
RATE_LIMIT_PROFILES: dict[str, tuple[int, int]] = {
    "auth_strict": (20, 60),
    "authenticated": (600, 60),
    "callback_burst": (600, 60),
    "health": (600, 60),
    "integration": (300, 60),
    "internal": (600, 60),
    "public_standard": (120, 60),
    "public_strict": (30, 60),
}


class RouteRateLimiter:
    def __init__(self) -> None:
        self._events: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = RLock()

    def allow(self, *, profile: str, principal: str, route_key: str, now: float | None = None) -> bool:
        limit, window = RATE_LIMIT_PROFILES[profile]
        timestamp = monotonic() if now is None else float(now)
        key = (principal, route_key)
        with self._lock:
            events = self._events[key]
            cutoff = timestamp - window
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= limit:
                return False
            events.append(timestamp)
            return True


RATE_LIMITER = RouteRateLimiter()


def route_policy_enforcement_enabled() -> bool:
    explicit = normalize_text(os.getenv(ROUTE_POLICY_ENFORCEMENT_ENV)).lower()
    if explicit in {"1", "true", "yes", "on"}:
        return True
    if explicit in {"0", "false", "no", "off"}:
        return not _route_policy_disable_override_allowed()
    if _pytest_auth_bypass_enabled():
        return False
    return production_environment()


def _route_policy_disable_override_allowed() -> bool:
    if normalize_text(os.getenv("PYTEST_CURRENT_TEST")):
        return True
    if normalize_text(os.getenv("AICRM_NEXT_ENV")).lower() == "test":
        return True
    return not production_environment()


def _pytest_auth_bypass_enabled() -> bool:
    if not normalize_text(os.getenv("PYTEST_CURRENT_TEST")):
        return False
    admin_auth = normalize_text(os.getenv("AICRM_ADMIN_AUTH_ENFORCED")).lower()
    return admin_auth in {"0", "false", "no", "off"}


async def route_policy_required_response(
    request: Request,
    *,
    app: FastAPI,
    index: RoutePolicyIndex,
) -> Response | None:
    matched = match_route_policy(app, request.scope, index)
    if matched.static or matched.builtin:
        return None
    if matched.route is None:
        return admin_auth_required_response(request)
    enforcement_enabled = route_policy_enforcement_enabled()
    policy = matched.policy
    if policy is None:
        if enforcement_enabled or admin_auth_enforcement_enabled():
            return _error("route_policy_missing", status_code=403)
        return None

    request.state.route_policy = policy
    _set_pii_principal(request, actor_type="anonymous", actor_id="anonymous", policy_scope=policy.access_scope)
    if enforcement_enabled and not _rate_limit_allows(request, policy):
        return _error("route_rate_limited", status_code=429)

    if policy.auth_scheme == "admin_session":
        return await _enforce_admin_session(request, policy)
    if policy.auth_scheme == "internal_bearer" and enforcement_enabled:
        return _enforce_internal_bearer(request, policy)
    if policy.auth_scheme == "scoped_bearer" and enforcement_enabled:
        return _enforce_scoped_bearer_presence(request)
    if policy.auth_scheme == "sidebar_signed_context" and enforcement_enabled:
        return await _enforce_sidebar_context(request)
    return None


async def _enforce_admin_session(request: Request, policy: RoutePolicy) -> Response | None:
    if not (admin_auth_enforcement_enabled() or route_policy_enforcement_enabled()):
        return None
    session = current_admin_session(request)
    if session is None:
        if str(request.url.path).startswith(("/admin", "/setup")):
            return admin_page_auth_redirect(request)
        return _error("admin_auth_required", status_code=401)
    _set_pii_principal(
        request,
        actor_type="admin_session",
        actor_id=normalize_text(session.get("admin_user_id") or session.get("username")) or "admin_session",
        policy_scope=policy.access_scope,
    )
    session_state = await run_in_threadpool(validate_admin_session_state, session)
    if not session_state.ok:
        return _error(session_state.error or "admin_session_revoked", status_code=401)
    request.state.admin_session = session
    if policy.is_write and viewer_only(session):
        return _error("admin_capability_required", status_code=403, capability=policy.capability)
    if policy.capability not in {"public", "health_read"} and not session_can(session, policy.capability):
        return _error("admin_capability_required", status_code=403, capability=policy.capability)
    if policy.csrf:
        csrf_error = await _csrf_error(request, session)
        if csrf_error:
            return csrf_error
    return None


def _enforce_internal_bearer(request: Request, policy: RoutePolicy) -> Response | None:
    try:
        result = validate_internal_service_token(policy.token_purpose, _bearer_token(request))
    except ValueError:
        return _error("internal_token_purpose_invalid", status_code=503)
    if not result.ok:
        status_code = 503 if result.error == "internal_token_not_configured" else 401
        return _error(result.error, status_code=status_code)
    request.state.service_account = result.service_account
    _set_pii_principal(request, actor_type="internal_service", actor_id=result.service_account)
    return None


def _enforce_scoped_bearer_presence(request: Request) -> Response | None:
    provided = _bearer_token(request) or normalize_text(request.query_params.get("token"))
    if not provided:
        return _error("scoped_token_required", status_code=401)
    request.state.service_account = "scoped_integration"
    _set_pii_principal(request, actor_type="scoped_service", actor_id="scoped_integration")
    return None


async def _enforce_sidebar_context(request: Request) -> Response | None:
    token = (
        normalize_text(request.headers.get(SIDEBAR_OWNER_TOKEN_HEADER))
        or normalize_text(request.query_params.get("sidebar_owner_token"))
        or normalize_text(request.query_params.get("owner_token"))
    )
    result = load_sidebar_owner_context_token(token)
    if not result.get("ok"):
        return _error("sidebar_context_required", status_code=401)
    context = dict(result.get("context") or {})
    owner_userid = normalize_text(context.get("owner_userid") or context.get("viewer_userid"))
    if not owner_userid:
        return _error("sidebar_context_required", status_code=401)
    claimed_values = [
        normalize_text(request.query_params.get(key))
        for key in ("owner_userid", "current_userid", "bind_by_userid", "viewer_userid")
    ]
    content_type = normalize_text(request.headers.get("content-type")).lower()
    if content_type.startswith("application/json"):
        try:
            body = json.loads((await request.body()).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            body = {}
        if isinstance(body, dict):
            claimed_values.extend(
                normalize_text(body.get(key))
                for key in ("owner_userid", "current_userid", "bind_by_userid", "viewer_userid", "actor_id")
            )
    if any(value and not hmac.compare_digest(value, owner_userid) for value in claimed_values):
        return _error("sidebar_owner_scope_forbidden", status_code=403)
    request.state.sidebar_context = context
    request.state.sidebar_owner_userid = owner_userid
    _set_pii_principal(request, actor_type="sidebar_owner", actor_id=owner_userid, policy_scope="owner")
    return None


def _set_pii_principal(
    request: Request,
    *,
    actor_type: str,
    actor_id: str,
    policy_scope: str = "",
) -> None:
    request.state.pii_actor_type = normalize_text(actor_type) or "anonymous"
    request.state.pii_actor_id = normalize_text(actor_id) or "anonymous"
    if policy_scope:
        request.state.pii_policy_scope = normalize_text(policy_scope)


async def _csrf_error(request: Request, session: dict[str, Any]) -> JSONResponse | None:
    expected = csrf_token_from_session(session)
    cookie_token = normalize_text(request.cookies.get(CSRF_COOKIE))
    request_token = normalize_text(request.headers.get(CSRF_HEADER))
    if not request_token:
        content_type = normalize_text(request.headers.get("content-type")).lower()
        if content_type.startswith("application/x-www-form-urlencoded"):
            body = (await request.body()).decode("utf-8", errors="ignore")
            values = parse_qs(body, keep_blank_values=True).get("csrf_token") or []
            request_token = normalize_text(values[-1] if values else "")
        elif content_type.startswith("multipart/form-data"):
            request_token = _multipart_form_value(
                await request.body(),
                content_type=content_type,
                field_name="csrf_token",
            )
    if expected and cookie_token and request_token:
        if hmac.compare_digest(expected, cookie_token) and hmac.compare_digest(expected, request_token):
            return None
    return _error("admin_csrf_required", status_code=403)


def _multipart_form_value(body: bytes, *, content_type: str, field_name: str) -> str:
    boundary_marker = "boundary="
    if boundary_marker not in content_type:
        return ""
    boundary = content_type.split(boundary_marker, 1)[1].split(";", 1)[0].strip().strip('"')
    if not boundary:
        return ""
    delimiter = f"--{boundary}".encode("utf-8")
    expected_name = f'name="{field_name}"'.encode("utf-8")
    for part in body.split(delimiter):
        headers, separator, content = part.partition(b"\r\n\r\n")
        if not separator or expected_name not in headers:
            continue
        value = content.split(b"\r\n", 1)[0]
        return normalize_text(value.decode("utf-8", errors="ignore"))
    return ""


def _bearer_token(request: Request) -> str:
    authorization = normalize_text(request.headers.get("authorization"))
    return normalize_text(authorization[7:]) if authorization.startswith("Bearer ") else ""


def _rate_limit_allows(request: Request, policy: RoutePolicy) -> bool:
    principal = _rate_limit_principal(request, policy)
    return RATE_LIMITER.allow(profile=policy.rate_limit, principal=principal, route_key=policy.key)


def _rate_limit_principal(request: Request, policy: RoutePolicy) -> str:
    if policy.auth_scheme == "admin_session":
        session = current_admin_session(request)
        if session:
            subject = normalize_text(session.get("admin_user_id") or session.get("username"))
            session_id = normalize_text(session.get("sid"))
            if subject:
                return f"admin:{subject}:{session_id[:16]}"
    if policy.auth_scheme in {"internal_bearer", "scoped_bearer"}:
        token = _bearer_token(request) or normalize_text(request.query_params.get("token"))
        if token:
            return f"bearer:{hashlib.sha256(token.encode('utf-8')).hexdigest()[:24]}"
    if policy.auth_scheme == "sidebar_signed_context":
        token = normalize_text(request.headers.get(SIDEBAR_OWNER_TOKEN_HEADER))
        if token:
            return f"sidebar:{hashlib.sha256(token.encode('utf-8')).hexdigest()[:24]}"
    forwarded = normalize_text(request.headers.get("x-forwarded-for")).split(",", 1)[0].strip()
    real_ip = normalize_text(request.headers.get("x-real-ip"))
    client_host = normalize_text(getattr(request.client, "host", ""))
    return f"ip:{(forwarded or real_ip or client_host or 'unknown')[:128]}"


def _error(error: str, *, status_code: int, capability: str = "") -> JSONResponse:
    payload: dict[str, Any] = {
        "ok": False,
        "error": error,
        "route_owner": "ai_crm_next",
        "real_external_call_executed": False,
    }
    if capability:
        payload["required_capability"] = capability
    return JSONResponse(payload, status_code=status_code, headers=route_headers())
