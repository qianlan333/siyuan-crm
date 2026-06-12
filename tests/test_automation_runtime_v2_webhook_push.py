from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from aicrm_next.automation_runtime_v2.api import verify_webhook_signature

from tests.automation_runtime_v2_test_helpers import seed_program, seed_task


def test_webhook_push_event_payload_enters_renderer(next_client, next_pg_schema):
    program_id = seed_program("runtime_v2_webhook")
    seed_task(program_id, trigger_type="webhook_push", content_mode="agent", agent_config={"agent_code": "missing", "fallback_content": "fallback", "webhook_key": "demo"})
    assert verify_webhook_signature("demo", {"signature": "ok"}, "ok") is True

    response = next_client.post(
        "/api/automation-runtime/v2/webhooks/demo",
        headers={"X-AICRM-Signature": "ok"},
        json={"signature": "ok", "external_event_id": "evt-1", "program_id": program_id, "external_userid": "wm_webhook", "variables": {"x": 1}},
    )
    assert response.status_code == 200
    payload = response.json()["runtime_v2"]
    assert payload["counts"]["enqueued"] == 1
    assert payload["plans"][0]["status"] == "enqueued"
