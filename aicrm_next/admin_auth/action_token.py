from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from fastapi import Request

from aicrm_next.shared.route_ownership import load_route_manifest
from aicrm_next.shared.route_policy import DEFAULT_ROUTE_POLICY_MANIFEST
from aicrm_next.shared.runtime import production_data_ready, production_environment, require_signing_secret

from .capabilities import session_can
from .guards import current_admin_session
from .service import normalize_text


ACTION_TOKEN_TTL_SECONDS = 10 * 60
ACTION_TOKEN_VERSION = 1
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


@dataclass(frozen=True)
class ActionTokenValidation:
    ok: bool
    error: str = ""
    claims: dict[str, Any] | None = None


@dataclass(frozen=True)
class ActionTokenRoute:
    method: str
    action: str
    target: str
    capability: str

    @property
    def key(self) -> str:
        return f"{self.method} {self.target}"


def issue_action_token(
    session: dict[str, Any],
    *,
    capability: str,
    method: str,
    action: str,
    target: str,
    now: int | None = None,
    ttl_seconds: int = ACTION_TOKEN_TTL_SECONDS,
) -> str:
    normalized_capability = normalize_text(capability)
    normalized_method = normalize_text(method).upper()
    normalized_action = normalize_text(action)
    normalized_target = _normalize_target(target)
    if not normalized_capability or not normalized_method or not normalized_action or not normalized_target:
        raise ValueError("action token binding is incomplete")
    if normalized_method in SAFE_METHODS:
        raise ValueError("action token cannot be issued for a safe method")
    if not session_can(session, normalized_capability):
        raise PermissionError(f"session lacks capability: {normalized_capability}")
    issued_at = int(time.time()) if now is None else int(now)
    ttl = max(1, min(int(ttl_seconds), ACTION_TOKEN_TTL_SECONDS))
    claims = {
        "v": ACTION_TOKEN_VERSION,
        "sub": _session_subject(session),
        "sid": session_fingerprint(session),
        "cap": normalized_capability,
        "m": normalized_method,
        "act": normalized_action,
        "tgt": normalized_target,
        "iat": issued_at,
        "exp": issued_at + ttl,
        "nonce": secrets.token_urlsafe(12),
    }
    body = _b64(json.dumps(claims, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest()
    return f"{body}.{_b64(signature)}"


def validate_action_token(
    token: str,
    session: dict[str, Any],
    *,
    capability: str,
    method: str,
    action: str,
    target: str,
    now: int | None = None,
) -> ActionTokenValidation:
    claims = _decode_claims(token)
    if claims is None:
        return ActionTokenValidation(ok=False, error="invalid")
    current_time = int(time.time()) if now is None else int(now)
    try:
        issued_at = int(claims.get("iat") or 0)
        expires_at = int(claims.get("exp") or 0)
    except (TypeError, ValueError):
        return ActionTokenValidation(ok=False, error="invalid")
    if int(claims.get("v") or 0) != ACTION_TOKEN_VERSION:
        return ActionTokenValidation(ok=False, error="invalid")
    if issued_at <= 0 or expires_at <= issued_at or expires_at - issued_at > ACTION_TOKEN_TTL_SECONDS:
        return ActionTokenValidation(ok=False, error="invalid")
    if current_time < issued_at - 30:
        return ActionTokenValidation(ok=False, error="not_yet_valid")
    if current_time > expires_at:
        return ActionTokenValidation(ok=False, error="expired")

    expected = {
        "sub": _session_subject(session),
        "sid": session_fingerprint(session),
        "cap": normalize_text(capability),
        "m": normalize_text(method).upper(),
        "act": normalize_text(action),
        "tgt": _normalize_target(target),
    }
    for key, value in expected.items():
        if not value or not hmac.compare_digest(normalize_text(claims.get(key)), value):
            return ActionTokenValidation(ok=False, error=f"binding_mismatch:{key}")
    if not session_can(session, expected["cap"]):
        return ActionTokenValidation(ok=False, error="capability_revoked")
    if not normalize_text(claims.get("nonce")):
        return ActionTokenValidation(ok=False, error="invalid")
    return ActionTokenValidation(ok=True, claims=claims)


def issue_action_token_for_route(request: Request, *, method: str, target: str) -> str:
    route = _route_by_key().get(f"{normalize_text(method).upper()} {_normalize_target(target)}")
    if route is None:
        raise ValueError(f"unsafe admin route is not registered: {method} {target}")
    session = _request_session(request)
    if session is None:
        raise PermissionError("admin session is required")
    return issue_action_token(
        session,
        capability=route.capability,
        method=route.method,
        action=route.action,
        target=route.target,
    )


def validate_action_token_for_request(request: Request, token: str) -> ActionTokenValidation:
    session = _request_session(request)
    policy = getattr(request.state, "route_policy", None)
    if session is None or policy is None:
        return ActionTokenValidation(ok=False, error="context_missing")
    method = normalize_text(request.method).upper()
    if method in SAFE_METHODS:
        return ActionTokenValidation(ok=False, error="safe_method")
    return validate_action_token(
        token,
        session,
        capability=normalize_text(policy.capability),
        method=method,
        action=normalize_text(policy.route_name),
        target=normalize_text(policy.path),
    )


def build_admin_action_token_bundle(request: Request) -> dict[str, str]:
    session = _request_session(request)
    if session is None:
        return {}
    tokens: dict[str, str] = {}
    for route in _unsafe_admin_routes():
        if not session_can(session, route.capability):
            continue
        tokens[route.key] = issue_action_token(
            session,
            capability=route.capability,
            method=route.method,
            action=route.action,
            target=route.target,
        )
    return tokens


def bound_action_tokens_required() -> bool:
    value = normalize_text(os.getenv("AICRM_ROUTE_POLICY_ENFORCED")).lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    return production_environment() or production_data_ready()


def session_fingerprint(session: dict[str, Any]) -> str:
    session_id = normalize_text(session.get("sid"))
    if session_id:
        material = f"sid:{session_id}"
    else:
        material = json.dumps(
            {
                "sub": _session_subject(session),
                "iat": int(session.get("iat") or 0),
                "csrf": normalize_text(session.get("csrf_token")),
                "version": int(session.get("session_version") or 0),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    return hmac.new(_secret(), material.encode("utf-8"), hashlib.sha256).hexdigest()


def _request_session(request: Request) -> dict[str, Any] | None:
    state_session = getattr(request.state, "admin_session", None)
    if isinstance(state_session, dict):
        return state_session
    return current_admin_session(request)


def _session_subject(session: dict[str, Any]) -> str:
    admin_user_id = normalize_text(session.get("admin_user_id"))
    if admin_user_id:
        return f"admin_user:{admin_user_id}"
    username = normalize_text(session.get("username") or session.get("wecom_userid"))
    return f"admin_username:{username}" if username else ""


@lru_cache(maxsize=1)
def _unsafe_admin_routes() -> tuple[ActionTokenRoute, ...]:
    routes: list[ActionTokenRoute] = []
    for entry in load_route_manifest(DEFAULT_ROUTE_POLICY_MANIFEST):
        if normalize_text(entry.get("auth_scheme")) != "admin_session":
            continue
        capability = normalize_text(entry.get("capability"))
        action = normalize_text(entry.get("route_name"))
        target = _normalize_target(entry.get("path"))
        for method in entry.get("methods") or ():
            normalized_method = normalize_text(method).upper()
            if normalized_method in SAFE_METHODS:
                continue
            routes.append(
                ActionTokenRoute(
                    method=normalized_method,
                    action=action,
                    target=target,
                    capability=capability,
                )
            )
    return tuple(routes)


@lru_cache(maxsize=1)
def _route_by_key() -> dict[str, ActionTokenRoute]:
    return {route.key: route for route in _unsafe_admin_routes()}


def _decode_claims(token: str) -> dict[str, Any] | None:
    value = normalize_text(token)
    if "." not in value:
        return None
    body, signature = value.rsplit(".", 1)
    try:
        supplied_signature = _unb64(signature)
    except Exception:
        return None
    expected_signature = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest()
    if not hmac.compare_digest(supplied_signature, expected_signature):
        return None
    try:
        claims = json.loads(_unb64(body).decode("utf-8"))
    except Exception:
        return None
    return claims if isinstance(claims, dict) else None


def _normalize_target(value: Any) -> str:
    target = normalize_text(value)
    if target and not target.startswith("/"):
        return f"/{target}"
    return target


def _secret() -> bytes:
    return require_signing_secret(
        "AICRM_NEXT_ACTION_TOKEN_SECRET",
        fallback_env_keys=("SECRET_KEY",),
        local_fallback="aicrm-next-dev-action-token",
    )


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode((value + "=" * (-len(value) % 4)).encode("ascii"))
