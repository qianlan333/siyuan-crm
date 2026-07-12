from __future__ import annotations

from pathlib import Path

from aicrm_next.admin_auth.session_state import validate_admin_session_state


ROOT = Path(__file__).resolve().parents[1]


class FakeAdminRepository:
    def __init__(
        self,
        *,
        active: bool = True,
        login_enabled: bool = True,
        session_version: int = 4,
        roles: tuple[str, ...] = ("viewer",),
        admin_level: str = "admin",
    ) -> None:
        self.user = {
            "id": 17,
            "is_active": active,
            "login_enabled": login_enabled,
            "session_version": session_version,
            "admin_level": admin_level,
        }
        self.roles = roles

    def get_admin_user(self, user_id: int):
        return dict(self.user) if user_id == 17 else None

    def list_admin_user_roles(self, admin_user_ids: list[int]):
        if 17 not in admin_user_ids:
            return []
        return [{"admin_user_id": 17, "role_code": role} for role in self.roles]


def _session(*roles: str, session_version: int = 4) -> dict:
    return {
        "login_type": "wecom_sso",
        "admin_user_id": 17,
        "session_version": session_version,
        "roles": list(roles),
    }


def test_current_server_side_session_version_and_roles_are_valid() -> None:
    result = validate_admin_session_state(_session("viewer"), repository=FakeAdminRepository())

    assert result.ok is True
    assert result.roles == ("viewer",)


def test_disabled_admin_invalidates_existing_session_immediately() -> None:
    result = validate_admin_session_state(
        _session("viewer"),
        repository=FakeAdminRepository(active=False),
    )

    assert result.ok is False
    assert result.error == "admin_session_revoked"


def test_login_disabled_admin_invalidates_existing_session_immediately() -> None:
    result = validate_admin_session_state(
        _session("viewer"),
        repository=FakeAdminRepository(login_enabled=False),
    )

    assert result.ok is False
    assert result.error == "admin_session_revoked"


def test_session_version_change_revokes_old_session() -> None:
    result = validate_admin_session_state(
        _session("viewer", session_version=3),
        repository=FakeAdminRepository(session_version=4),
    )

    assert result.ok is False
    assert result.error == "admin_session_revoked"


def test_role_downgrade_revokes_old_capability_snapshot() -> None:
    result = validate_admin_session_state(
        _session("automation_admin"),
        repository=FakeAdminRepository(roles=("viewer",)),
    )

    assert result.ok is False
    assert result.error == "admin_session_revoked"


def test_break_glass_session_does_not_depend_on_database_row() -> None:
    result = validate_admin_session_state(
        {"login_type": "break_glass", "roles": ["super_admin"]},
        repository=FakeAdminRepository(active=False),
    )

    assert result.ok is True
    assert result.roles == ("super_admin",)


def test_r01_migration_adds_session_revocation_and_unique_result_grant_index() -> None:
    source = (ROOT / "migrations" / "versions" / "0098_admin_session_revocation.py").read_text(encoding="utf-8")

    assert "ADD COLUMN IF NOT EXISTS session_version BIGINT NOT NULL DEFAULT 1" in source
    assert "CREATE UNIQUE INDEX IF NOT EXISTS idx_questionnaire_submissions_result_token" in source
    assert "WHERE result_token <> ''" in source
