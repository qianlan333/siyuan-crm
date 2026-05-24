from __future__ import annotations

from wecom_ability_service.db import get_db
from wecom_ability_service.domains.automation_conversion.channel_binding_service import upsert_channel_contact

from automation_channel_admission_helpers import (
    admin_action_token,
    create_channel,
    create_program,
    login_admin,
    save_audience_entry_rule,
    table_count,
)


def test_channel_center_api_success_invalid_ids_status_and_action_token(app, client, monkeypatch):
    login_admin(client, app, monkeypatch)
    token = admin_action_token(client)
    with app.app_context():
        program_id = create_program()
        save_audience_entry_rule(
            program_id,
            {
                "order_review": {"enabled": False},
                "questionnaire_review": {"enabled": False},
                "conversion_review": {"enabled": False},
            },
        )

    missing_token = client.post(
        "/api/admin/channels",
        json={"channel_code": "api_missing_token", "channel_name": "missing token"},
    )
    assert missing_token.status_code == 400
    assert missing_token.get_json()["reason"] == "admin_action_token_required"

    created = client.post(
        "/api/admin/channels",
        json={
            "admin_action_token": token,
            "channel_code": "api_channel",
            "channel_name": "API 渠道",
            "scene_value": "scene_api_channel",
            "status": "active",
        },
    )
    assert created.status_code == 201
    channel = created.get_json()["channel"]
    channel_id = int(channel["id"])

    channel_list = client.get("/api/admin/channels")
    assert channel_list.status_code == 200
    assert any(int(item["id"]) == channel_id for item in channel_list.get_json()["channels"])

    with app.app_context():
        upsert_channel_contact(
            channel_id=channel_id,
            external_contact_id="wm_api_contact",
            owner_staff_id="sales_01",
            entered_at="2026-05-23 10:00:00",
        )
        get_db().commit()

    contacts = client.get(f"/api/admin/channels/{channel_id}/contacts")
    assert contacts.status_code == 200
    assert contacts.get_json()["contacts"][0]["external_contact_id"] == "wm_api_contact"
    assert client.get("/api/admin/channels/999999/contacts").status_code == 404

    invalid_binding = client.post(
        f"/api/admin/automation-conversion/programs/{program_id}/channel-bindings",
        json={"admin_action_token": token, "channel_ids": [999999]},
    )
    assert invalid_binding.status_code == 404
    assert invalid_binding.get_json()["reason"] == "channel_not_found"

    bound = client.post(
        f"/api/admin/automation-conversion/programs/{program_id}/channel-bindings",
        json={"admin_action_token": token, "channel_ids": [channel_id]},
    )
    assert bound.status_code == 201
    binding = bound.get_json()["bindings"][0]
    binding_id = int(binding["id"])
    assert bound.get_json()["history_imported"] is False

    channel_bindings = client.get(f"/api/admin/channels/{channel_id}/bindings")
    assert channel_bindings.status_code == 200
    assert channel_bindings.get_json()["bindings"][0]["binding_status"] == "active"

    paused = client.patch(
        f"/api/admin/automation-conversion/programs/{program_id}/channel-bindings/{binding_id}",
        json={"admin_action_token": token, "binding_status": "paused"},
    )
    assert paused.status_code == 200
    assert paused.get_json()["binding"]["binding_status"] == "paused"

    archived = client.delete(
        f"/api/admin/automation-conversion/programs/{program_id}/channel-bindings/{binding_id}",
        json={"admin_action_token": token},
    )
    assert archived.status_code == 200
    assert archived.get_json()["binding"]["binding_status"] == "archived"
    assert archived.get_json()["channel_deleted"] is False

    import_without_active_binding = client.post(
        f"/api/admin/automation-conversion/programs/{program_id}/channel-bindings/import",
        json={"admin_action_token": token, "channel_id": channel_id, "dry_run": True},
    )
    assert import_without_active_binding.status_code == 400
    assert import_without_active_binding.get_json()["reason"] == "active_binding_required"


def test_channel_binding_import_api_dry_run_and_attempt_logs(app, client, monkeypatch):
    login_admin(client, app, monkeypatch)
    token = admin_action_token(client)
    with app.app_context():
        program_id = create_program()
        channel = create_channel("api_import_channel")
        channel_id = int(channel["id"])
        save_audience_entry_rule(
            program_id,
            {
                "order_review": {"enabled": False},
                "questionnaire_review": {"enabled": False},
                "conversion_review": {"enabled": False},
            },
        )
        upsert_channel_contact(
            channel_id=channel_id,
            external_contact_id="wm_api_import",
            owner_staff_id="sales_01",
            entered_at="2026-05-22 09:00:00",
        )
        get_db().commit()

    bound = client.post(
        f"/api/admin/automation-conversion/programs/{program_id}/channel-bindings",
        json={"admin_action_token": token, "channel_ids": [channel_id]},
    )
    assert bound.status_code == 201

    dry_run = client.post(
        f"/api/admin/automation-conversion/programs/{program_id}/channel-bindings/import",
        json={"admin_action_token": token, "channel_id": channel_id, "dry_run": True},
    )
    assert dry_run.status_code == 200
    assert dry_run.get_json()["dry_run"] is True
    assert dry_run.get_json()["planned_count"] == 1
    with app.app_context():
        assert table_count("automation_program_member") == 0

    imported = client.post(
        f"/api/admin/automation-conversion/programs/{program_id}/channel-bindings/import",
        json={"admin_action_token": token, "channel_id": channel_id},
    )
    assert imported.status_code == 200
    assert imported.get_json()["imported_count"] == 1

    attempts = client.get(f"/api/admin/automation-conversion/programs/{program_id}/admission-attempts")
    assert attempts.status_code == 200
    payload = attempts.get_json()
    assert payload["reason"] == "admission_attempts_listed"
    assert payload["admission_attempts"][0]["trigger_type"] == "manual_import"
