from __future__ import annotations

from wecom_ability_service.db import get_db

from automation_channel_admission_helpers import create_channel


def test_runtime_diagnosis_reports_scene_resolution_and_effect_configuration(app, client):
    with app.app_context():
        channel = create_channel("runtime_diagnosis_channel")
        get_db().execute(
            """
            UPDATE automation_channel
            SET welcome_message = '欢迎加入报名渠道',
                entry_tag_id = 'tag-signup-lead',
                entry_tag_name = '报名引流品',
                owner_staff_id = 'HuangYouCan'
            WHERE id = ?
            """,
            (int(channel["id"]),),
        )
        get_db().commit()

        response = client.get(f"/api/admin/channels/runtime-diagnosis?scene_value={channel['scene_value']}")

        assert response.status_code == 200
        payload = response.get_json()
        assert payload["scene_resolve"]["match_type"] == "current_scene"
        assert payload["channel"]["id"] == int(channel["id"])
        assert payload["welcome_configured"] is True
        assert payload["entry_tag_configured"] is True
        assert payload["expected_baseline_effects"]["channel_contact"] is True


def test_runtime_diagnosis_dry_run_plans_actions_without_side_effects(app, client, monkeypatch):
    with app.app_context():
        channel = create_channel("runtime_diagnosis_dry_run")
        get_db().execute(
            """
            UPDATE automation_channel
            SET welcome_message = '欢迎加入报名渠道',
                entry_tag_id = 'tag-signup-lead',
                entry_tag_name = '报名引流品',
                owner_staff_id = 'HuangYouCan'
            WHERE id = ?
            """,
            (int(channel["id"]),),
        )
        get_db().commit()

        response = client.post(
            "/api/admin/channels/runtime-diagnosis/dry-run",
            json={
                "state": channel["scene_value"],
                "external_userid": "wm_runtime_diagnosis_dry_run",
                "follow_user_userid": "HuangYouCan",
                "welcome_code_present": True,
            },
        )

        assert response.status_code == 200
        payload = response.get_json()
        planned = payload["planned_actions"]
        assert planned["handled"] is True
        assert planned["baseline_effects"]["channel_contact"]["planned"] is True
        assert planned["welcome_message"]["reason"] == "dry_run"
        assert planned["entry_tag"]["reason"] == "dry_run"
        rows = get_db().execute(
            """
            SELECT id
            FROM automation_channel_contact
            WHERE external_contact_id = 'wm_runtime_diagnosis_dry_run'
            """
        ).fetchall()
        assert rows == []


def test_runtime_route_map_exposes_release_and_worker_fields(client):
    response = client.get("/api/system/runtime-route-map")

    assert response.status_code == 200
    payload = response.get_json()
    assert "web_release_sha" in payload
    assert "worker_release_sha" in payload
    assert "task_queue_backend" in payload
    assert "callback_async_enabled" in payload


def test_next_runtime_route_map_and_callback_facade_are_explicit():
    pytest = __import__("pytest")
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from aicrm_next.main import create_app

    client = TestClient(create_app())

    route_map = client.get("/api/system/runtime-route-map")

    assert route_map.status_code == 200
    payload = route_map.json()
    assert payload["route_owner"] == "ai_crm_next"
    assert payload["wecom_callback_routes"]["/wecom/external-contact/callback"] == "aicrm_next.channel_entry.api"
    assert payload["next_live_callback_gateway_enabled"] is True
    assert payload["legacy_callback_fallback_enabled"] is False
