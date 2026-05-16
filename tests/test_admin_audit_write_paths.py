from __future__ import annotations

from flask import Flask


def test_admin_auth_directory_sync_uses_unified_audit(monkeypatch):
    from wecom_ability_service.domains import admin_audit
    from wecom_ability_service.domains.admin_auth import service as admin_auth_service

    calls: list[dict[str, object]] = []

    class FakeDirectoryClient:
        corp_id = "ww-test"

        def list_department_users(self, department_id: int = 1, fetch_child: int = 1):
            return {
                "userlist": [
                    {
                        "userid": "sales.one",
                        "name": "Sales One",
                        "department": [1],
                        "position": "Advisor",
                        "status": 1,
                    },
                    {},
                ]
            }

    monkeypatch.setattr(admin_auth_service, "_directory_root_department_id", lambda: 1)
    monkeypatch.setattr(
        admin_auth_service.WeComClient,
        "from_contact_app",
        staticmethod(lambda: FakeDirectoryClient()),
    )
    monkeypatch.setattr(
        admin_auth_service.repo,
        "upsert_admin_wecom_directory_members",
        lambda **kwargs: len(kwargs["members"]),
    )
    monkeypatch.setattr(admin_audit, "record_audit", lambda **kwargs: calls.append(kwargs))

    result = admin_auth_service.sync_admin_wecom_directory_members(operator="ops")

    assert result["synced_count"] == 1
    assert result["skipped_count"] == 1
    assert calls == [
        {
            "operator": "ops",
            "action_type": "sync_admin_wecom_directory",
            "target_type": "admin_wecom_directory_members",
            "target_id": "ww-test",
            "before": {"department_id": 1},
            "after": {
                "synced_count": 1,
                "skipped_count": 1,
                "department_id": 1,
                "corp_id": "ww-test",
            },
        }
    ]


def test_admin_auth_audit_helper_normalizes_blank_operator(monkeypatch):
    from wecom_ability_service.domains import admin_audit
    from wecom_ability_service.domains.admin_auth import service as admin_auth_service

    calls: list[dict[str, object]] = []
    monkeypatch.setattr(admin_audit, "record_audit", lambda **kwargs: calls.append(kwargs))

    admin_auth_service._record_audit(
        operator="",
        action_type="create_admin_user",
        target_type="admin_user",
        target_id="root.admin",
        after={"ok": True},
    )

    assert calls == [
        {
            "operator": "crm_console",
            "action_type": "create_admin_user",
            "target_type": "admin_user",
            "target_id": "root.admin",
            "before": {},
            "after": {"ok": True},
        }
    ]


def test_sunset_access_uses_unified_audit(monkeypatch):
    from wecom_ability_service.domains import admin_audit
    from wecom_ability_service.http import internal_auth

    app = Flask(__name__)
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(internal_auth, "current_admin_session_user", lambda: {"id": 1})
    monkeypatch.setattr(internal_auth, "current_admin_operator", lambda: "root.admin")
    monkeypatch.setattr(admin_audit, "record_audit", lambda **kwargs: calls.append(kwargs))

    with app.test_request_context(
        "/admin/audit",
        headers={"X-Forwarded-For": "203.0.113.9", "User-Agent": "pytest"},
    ):
        internal_auth._record_sunset_access("/admin/audit")

    assert calls == [
        {
            "operator": "root.admin",
            "action_type": "sunset_route_access",
            "target_type": "sunset_route",
            "target_id": "/admin/audit",
            "before": {
                "path": "/admin/audit",
                "method": "GET",
                "operator": "root.admin",
            },
            "after": {
                "referrer": "",
                "remote_addr": "203.0.113.9",
                "user_agent": "pytest",
            },
        }
    ]
