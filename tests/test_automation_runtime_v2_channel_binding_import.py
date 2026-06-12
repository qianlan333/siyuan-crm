from __future__ import annotations

import inspect

from tests.automation_runtime_v2_test_helpers import count, db, seed_channel, seed_contact, seed_program, seed_task


def _counts_for_program(program_id: int) -> dict[str, int]:
    conn = db()
    return {
        "events": int(conn.execute("SELECT COUNT(*) AS count FROM automation_event_v2 WHERE program_id = ?", (program_id,)).fetchone()["count"]),
        "memberships": int(conn.execute("SELECT COUNT(*) AS count FROM automation_membership_v2 WHERE program_id = ?", (program_id,)).fetchone()["count"]),
        "stage_entries": int(conn.execute("SELECT COUNT(*) AS count FROM automation_stage_entry_v2 WHERE program_id = ?", (program_id,)).fetchone()["count"]),
        "task_plans": int(conn.execute("SELECT COUNT(*) AS count FROM automation_task_plan_v2 WHERE program_id = ?", (program_id,)).fetchone()["count"]),
        "broadcast_jobs": int(
            conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM broadcast_jobs bj
                JOIN automation_task_plan_v2 tp ON (bj.content_payload->>'task_plan_id') = tp.id::text
                WHERE bj.source_type = 'automation_runtime_v2'
                  AND tp.program_id = ?
                """,
                (program_id,),
            ).fetchone()["count"]
        ),
    }


def test_channel_binding_http_imports_history_without_legacy_domain(next_pg_schema, next_client):
    from aicrm_next.automation_engine import channels_api

    source = inspect.getsource(channels_api.bind_channels_to_program_resource)
    assert "wecom_ability_service" not in source

    program_id = seed_program("runtime_v2_http_binding")
    channel_id = seed_channel("runtime_v2_http_binding_channel")
    seed_task(program_id, trigger_type="audience_entered", target_stage="operating", content_text="hello")
    contact_ids = [
        seed_contact(channel_id, f"wm_http_binding_{idx}", first_at="2026-01-01 08:00:00+00")
        for idx in range(3)
    ]

    response = next_client.post(
        f"/api/admin/automation-conversion/programs/{program_id}/channel-bindings",
        json={
            "channel_ids": [channel_id],
            "binding_status": "active",
            "auto_enter_pool": True,
            "initial_audience_code": "pending_questionnaire",
            "max_import_count": 10,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["ok"] is True
    assert payload["history_imported"] is True
    assert payload["requires_batch_import"] is False
    assert payload["generated_event_count"] == 3
    assert payload["generated_membership_count"] == 3
    assert payload["generated_stage_entry_count"] == 3
    assert payload["generated_task_plan_count"] == 3
    assert payload["generated_broadcast_job_count"] == 3
    assert len(payload["bindings"]) == 1

    counts = _counts_for_program(program_id)
    assert counts == {"events": 3, "memberships": 3, "stage_entries": 3, "task_plans": 3, "broadcast_jobs": 3}

    event = db().execute(
        """
        SELECT occurred_at, raw_occurred_at
        FROM automation_event_v2
        WHERE source_type = 'binding_import'
          AND source_id = ?
        LIMIT 1
        """,
        (f"{program_id}:{payload['bindings'][0]['id']}:{contact_ids[0]}",),
    ).fetchone()
    assert str(event["raw_occurred_at"]).startswith("2026-01-01 08:00:00")
    assert str(event["occurred_at"]) != str(event["raw_occurred_at"])

    again = next_client.post(
        f"/api/admin/automation-conversion/programs/{program_id}/channel-bindings",
        json={"channel_ids": [channel_id], "max_import_count": 10},
    )

    assert again.status_code == 201
    again_payload = again.json()
    assert again_payload["history_imported"] is True
    assert again_payload["generated_event_count"] == 0
    assert again_payload["skipped_existing_count"] == 3
    assert _counts_for_program(program_id) == counts
    assert count("broadcast_jobs") == 3


def test_channel_binding_http_large_protection_blocks_partial_runtime_writes(next_pg_schema, next_client):
    program_id = seed_program("runtime_v2_http_binding_guard")
    channel_id = seed_channel("runtime_v2_http_binding_guard_channel")
    seed_task(program_id, trigger_type="audience_entered", target_stage="operating", content_text="hello")
    for idx in range(3):
        seed_contact(channel_id, f"wm_http_guard_{idx}")

    response = next_client.post(
        f"/api/admin/automation-conversion/programs/{program_id}/channel-bindings",
        json={"channel_ids": [channel_id], "max_import_count": 2},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["requires_batch_import"] is True
    assert payload["history_imported"] is False
    assert payload["total_contact_count"] == 3
    assert payload["max_import_count"] == 2
    assert payload["import_continue_token"]
    assert _counts_for_program(program_id) == {"events": 0, "memberships": 0, "stage_entries": 0, "task_plans": 0, "broadcast_jobs": 0}

    confirmed = next_client.post(
        f"/api/admin/automation-conversion/programs/{program_id}/channel-bindings",
        json={"channel_ids": [channel_id], "max_import_count": 2, "confirm_large_import": True},
    )

    assert confirmed.status_code == 201
    assert confirmed.json()["history_imported"] is True
    assert confirmed.json()["generated_event_count"] == 3
    assert _counts_for_program(program_id)["events"] == 3
