from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aicrm_next.admin_config.repository import AdminConfigRepository

from .capabilities import normalize_roles, session_roles
from .service import normalize_text


@dataclass(frozen=True)
class SessionStateResult:
    ok: bool
    error: str = ""
    admin_user: dict[str, Any] | None = None
    roles: tuple[str, ...] = ()


def validate_admin_session_state(
    session: dict[str, Any],
    *,
    repository: AdminConfigRepository | None = None,
) -> SessionStateResult:
    login_type = normalize_text(session.get("login_type"))
    if login_type != "wecom_sso":
        return SessionStateResult(ok=True, roles=session_roles(session))

    try:
        admin_user_id = int(session.get("admin_user_id") or 0)
        session_version = int(session.get("session_version") or 0)
    except (TypeError, ValueError):
        return SessionStateResult(ok=False, error="admin_session_revoked")
    if admin_user_id <= 0 or session_version <= 0:
        return SessionStateResult(ok=False, error="admin_session_revoked")

    try:
        repo = repository or AdminConfigRepository()
        admin_user = repo.get_admin_user(admin_user_id)
        if not admin_user:
            return SessionStateResult(ok=False, error="admin_session_revoked")
        if not _enabled(admin_user.get("is_active")) or not _enabled(admin_user.get("login_enabled")):
            return SessionStateResult(ok=False, error="admin_session_revoked")
        if int(admin_user.get("session_version") or 0) != session_version:
            return SessionStateResult(ok=False, error="admin_session_revoked")
        current_roles = normalize_roles(
            row.get("role_code")
            for row in repo.list_admin_user_roles([admin_user_id])
            if int(row.get("admin_user_id") or 0) == admin_user_id
        )
        if normalize_text(admin_user.get("admin_level")) == "super_admin":
            current_roles = ("super_admin",)
        if current_roles != session_roles(session):
            return SessionStateResult(ok=False, error="admin_session_revoked")
        return SessionStateResult(ok=True, admin_user=admin_user, roles=current_roles)
    except Exception:
        return SessionStateResult(ok=False, error="admin_session_state_unavailable")


def _enabled(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return normalize_text(value).lower() in {"1", "true", "yes", "on"}
