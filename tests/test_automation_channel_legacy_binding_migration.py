from __future__ import annotations

from wecom_ability_service.db import get_db
from wecom_ability_service.domains.automation_conversion.channel_binding_service import (
    ensure_legacy_program_channel_bindings,
)
from wecom_ability_service.domains.automation_conversion.customer_acquisition_service import handle_customer_acquisition_event
from wecom_ability_service.domains.automation_conversion.member_state_service import handle_channel_enter_from_callback

from automation_channel_admission_helpers import (
    admin_action_token,
    create_channel,
    create_program,
    disabled_entry_rule,
    fetch_program_member,
    login_admin,
    save_audience_entry_rule,
    set_callback_now,
    table_count,
)


def _binding_rows(channel_id: int | None = None) -> list[dict]:
    sql = "SELECT * FROM automation_program_channel_binding"
    params: list[int] = []
    if channel_id:
        sql += " WHERE channel_id = ?"
        params.append(int(channel_id))
    sql += " ORDER BY id ASC"
    return [dict(row) for row in get_db().execute(sql, tuple(params)).fetchall()]


def _insert_legacy_wca_link(*, program_id: int, channel_id: int, link_id: str = "legacy-link-001") -> dict:
    row = get_db().execute(
        """
        INSERT INTO wecom_customer_acquisition_links (
            corp_id, automation_channel_id, program_id, workflow_id, initial_audience_code,
            link_id, link_name, link_url, customer_channel, final_url, skip_verify,
            range_user_list, range_department_list, priority_option, status,
            created_at, updated_at
        )
        VALUES (
            'ww-test', ?, ?, NULL, 'pending_questionnaire',
            ?, ?, 'https://work.weixin.qq.com/ca/legacy',
            'wca_legacy_channel', CAST(? AS TEXT),
            FALSE, '[]'::jsonb, '[]'::jsonb, '{}'::jsonb, 'active',
            '2026-05-20 09:00:00', '2026-05-20 09:00:00'
        )
        RETURNING *
        """,
        (
            int(channel_id),
            int(program_id),
            link_id,
            link_id,
            "https://work.weixin.qq.com/ca/legacy?customer_channel=wca_legacy_channel",
        ),
    ).fetchone()
    get_db().commit()
    return dict(row)


def test_legacy_automation_channel_program_id_creates_binding_without_recreating_channel(app):
    with app.app_context():
        program_id = create_program("legacy_channel_p1")
        channel = create_channel("legacy_channel_ch1", program_id=program_id)
        channel_id = int(channel["id"])
        before_count = table_count("automation_channel")

        report = ensure_legacy_program_channel_bindings()

        rows = _binding_rows(channel_id)
        assert report["created_binding_count"] == 1
        assert len(rows) == 1
        assert int(rows[0]["program_id"]) == program_id
        assert int(rows[0]["channel_id"]) == channel_id
        assert table_count("automation_channel") == before_count
        stored_channel = dict(get_db().execute("SELECT * FROM automation_channel WHERE id = ?", (channel_id,)).fetchone())
        assert stored_channel["id"] == channel_id
        assert stored_channel["channel_code"] == channel["channel_code"]
        assert stored_channel["scene_value"] == channel["scene_value"]
        assert stored_channel["qr_url"] == channel["qr_url"]


def test_legacy_wecom_customer_acquisition_program_id_creates_binding_without_recreating_link(app):
    with app.app_context():
        program_id = create_program("legacy_wca_p1")
        channel = create_channel("legacy_wca_ch2")
        channel_id = int(channel["id"])
        link = _insert_legacy_wca_link(program_id=program_id, channel_id=channel_id)
        before_channel_count = table_count("automation_channel")
        before_link_count = table_count("wecom_customer_acquisition_links")

        report = ensure_legacy_program_channel_bindings()

        rows = _binding_rows(channel_id)
        assert report["created_binding_count"] == 1
        assert len(rows) == 1
        assert int(rows[0]["program_id"]) == program_id
        assert int(rows[0]["channel_id"]) == channel_id
        stored_link = dict(get_db().execute("SELECT * FROM wecom_customer_acquisition_links WHERE id = ?", (int(link["id"]),)).fetchone())
        assert stored_link["final_url"] == link["final_url"]
        assert stored_link["customer_channel"] == link["customer_channel"]
        assert stored_link["link_id"] == link["link_id"]
        assert table_count("automation_channel") == before_channel_count
        assert table_count("wecom_customer_acquisition_links") == before_link_count


def test_legacy_binding_migration_is_idempotent(app):
    with app.app_context():
        program_id = create_program("legacy_idempotent_p1")
        channel = create_channel("legacy_idempotent_ch", program_id=program_id)

        first = ensure_legacy_program_channel_bindings()
        second = ensure_legacy_program_channel_bindings()

        assert first["created_binding_count"] == 1
        assert second["created_binding_count"] == 0
        assert second["skipped_existing_count"] >= 1
        assert len(_binding_rows(int(channel["id"]))) == 1


def test_legacy_binding_migration_reports_conflict_and_prefers_channel_program_id(app):
    with app.app_context():
        p1 = create_program("legacy_conflict_p1")
        p2 = create_program("legacy_conflict_p2")
        channel = create_channel("legacy_conflict_ch", program_id=p1)
        _insert_legacy_wca_link(program_id=p2, channel_id=int(channel["id"]), link_id="legacy-conflict-link")

        report = ensure_legacy_program_channel_bindings()

        rows = _binding_rows(int(channel["id"]))
        assert report["created_binding_count"] == 1
        assert report["conflict_count"] == 1
        assert int(rows[0]["program_id"]) == p1
        assert rows[0]["binding_status"] == "active"
        assert report["conflicts"][0]["candidate_program_ids"] == [p1, p2]
        assert report["conflicts"][0]["chosen_program_id"] == p1
        assert report["conflicts"][0]["reason"] == "automation_channel.program_id takes precedence"


def test_legacy_channels_show_on_each_program_entry_page_and_are_excluded_from_other_candidates(app, client, monkeypatch):
    login_admin(client, app, monkeypatch)
    with app.app_context():
        p1 = create_program("legacy_page_p1")
        p2 = create_program("legacy_page_p2")
        ch1 = create_channel("legacy_page_ch1", program_id=p1)
        ch2 = create_channel("legacy_page_ch2", program_id=p2)
        before_count = table_count("automation_channel")

    p1_html = client.get(f"/admin/automation-conversion/programs/{p1}/entry-channels").get_data(as_text=True)
    p2_html = client.get(f"/admin/automation-conversion/programs/{p2}/entry-channels").get_data(as_text=True)

    assert "legacy_page_ch1" in p1_html
    assert "legacy_page_ch2" in p2_html
    assert f'data-bind-candidate data-channel-id="{int(ch1["id"])}"' not in p2_html
    assert f'data-bind-candidate data-channel-id="{int(ch2["id"])}"' not in p1_html
    with app.app_context():
        assert table_count("automation_channel") == before_count


def test_legacy_program_channel_scan_enters_original_program_without_new_qrcode(app, monkeypatch):
    with app.app_context():
        program_id = create_program("legacy_scan_p1")
        channel = create_channel("legacy_scan_ch", program_id=program_id)
        save_audience_entry_rule(program_id, disabled_entry_rule())
        before_count = table_count("automation_channel")

        set_callback_now(monkeypatch, "2026-05-23 10:00:00")
        result = handle_channel_enter_from_callback(
            external_contact_id="wm_legacy_scan_001",
            payload_json={"state": channel["scene_value"]},
            channel=channel,
            follow_user_userid="sales_01",
        )

        assert result["mode"] == "program_admission"
        assert result["admission_results"][0]["admission_status"] == "accepted"
        member = fetch_program_member("wm_legacy_scan_001", program_id)
        assert member is not None
        assert int(member["program_id"]) == program_id
        assert table_count("automation_channel") == before_count


def test_legacy_wecom_customer_acquisition_callback_enters_original_program_without_regenerating_link(app):
    with app.app_context():
        program_id = create_program("legacy_wca_callback_p1")
        channel = create_channel("legacy_wca_callback_ch")
        save_audience_entry_rule(program_id, disabled_entry_rule())
        link = _insert_legacy_wca_link(program_id=program_id, channel_id=int(channel["id"]), link_id="legacy-callback-link")
        before_final_url = link["final_url"]

        result = handle_customer_acquisition_event(
            corp_id="ww-test",
            event_data={
                "Event": "customer_acquisition",
                "LinkId": "legacy-callback-link",
                "State": "wca_legacy_channel",
                "ExternalUserID": "wm_legacy_wca_001",
                "UserID": "sales_01",
            },
        )

        assert result["mode"] == "program_admission"
        member = fetch_program_member("wm_legacy_wca_001", program_id)
        assert member is not None
        assert int(member["program_id"]) == program_id
        stored_link = dict(get_db().execute("SELECT final_url FROM wecom_customer_acquisition_links WHERE id = ?", (int(link["id"]),)).fetchone())
        assert stored_link["final_url"] == before_final_url


def test_available_for_program_api_excludes_legacy_migrated_active_channel(app, client, monkeypatch):
    login_admin(client, app, monkeypatch)
    token = admin_action_token(client)
    with app.app_context():
        p1 = create_program("legacy_available_p1")
        p2 = create_program("legacy_available_p2")
        channel = create_channel("legacy_available_ch", program_id=p1)

    response = client.get(f"/api/admin/channels?available_for_program_id={p2}")
    assert response.status_code == 200
    ids = {int(item["id"]) for item in response.get_json()["channels"]}
    assert int(channel["id"]) not in ids
    assert token


def test_unbinding_legacy_channel_archives_binding_keeps_channel_and_allows_rebinding(app, client, monkeypatch):
    login_admin(client, app, monkeypatch)
    token = admin_action_token(client)
    with app.app_context():
        p1 = create_program("legacy_unbind_p1")
        p2 = create_program("legacy_unbind_p2")
        channel = create_channel("legacy_unbind_ch", program_id=p1)
        get_db().execute("UPDATE automation_channel SET qr_url = 'https://example.test/legacy-qr.png' WHERE id = ?", (int(channel["id"]),))
        save_audience_entry_rule(p1, disabled_entry_rule())
        ensure_legacy_program_channel_bindings()
        binding = _binding_rows(int(channel["id"]))[0]
        set_callback_now(monkeypatch, "2026-05-23 10:00:00")
        handle_channel_enter_from_callback(
            external_contact_id="wm_legacy_unbind_001",
            payload_json={"state": channel["scene_value"]},
            channel=channel,
            follow_user_userid="sales_01",
        )
        get_db().commit()

    deleted = client.delete(
        f"/api/admin/automation-conversion/programs/{p1}/channel-bindings/{int(binding['id'])}",
        json={"admin_action_token": token},
    )
    assert deleted.status_code == 200
    payload = deleted.get_json()
    assert payload["binding"]["binding_status"] == "archived"
    assert payload["channel_deleted"] is False
    assert payload["exited_member_count"] == 1
    with app.app_context():
        stored_channel = dict(get_db().execute("SELECT * FROM automation_channel WHERE id = ?", (int(channel["id"]),)).fetchone())
        assert stored_channel["qr_url"] == "https://example.test/legacy-qr.png"
        assert table_count("automation_channel", "id = ?", (int(channel["id"]),)) == 1

    rebound = client.post(
        f"/api/admin/automation-conversion/programs/{p2}/channel-bindings",
        json={"admin_action_token": token, "channel_ids": [int(channel["id"])]},
    )
    assert rebound.status_code == 201
    assert rebound.get_json()["bindings"][0]["program_id"] == p2
