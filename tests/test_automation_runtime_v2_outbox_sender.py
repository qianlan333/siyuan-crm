from __future__ import annotations

import json

from aicrm_next.automation_runtime_v2 import process_event_payload
from aicrm_next.automation_runtime_v2.domain import AutomationEventInput
from aicrm_next.automation_runtime_v2.outbox import enqueue

from tests.automation_runtime_v2_test_helpers import db, seed_program, seed_task


def test_runtime_v2_outbox_uses_task_config_sender(next_pg_schema):
    program_id = seed_program("runtime_v2_sender_payload")
    seed_task(
        program_id,
        trigger_type="on_event",
        content_text="【RuntimeV2真实链路测试】case=sender_payload sender=HuangYouCan",
        agent_config={"trigger_event_type": "questionnaire_submitted", "sender_userid": "HuangYouCan"},
    )

    process_event_payload(
        AutomationEventInput(
            event_type="questionnaire_submitted",
            source_type="questionnaire",
            source_id="sender-payload-submission",
            program_id=program_id,
            external_userid="external-test-target",
            payload_json={"answers": {"need": "runtime v2"}},
        )
    )

    job = db().execute("SELECT * FROM broadcast_jobs WHERE source_type = 'automation_runtime_v2' ORDER BY id DESC LIMIT 1").fetchone()
    payload = job["content_payload"] if isinstance(job["content_payload"], dict) else json.loads(job["content_payload"])
    metadata = job["metadata_json"] if isinstance(job["metadata_json"], dict) else json.loads(job["metadata_json"])
    assert payload["sender_userid"] == "HuangYouCan"
    assert payload["owner_userid"] == "HuangYouCan"
    assert payload["target_external_userids"] == ["external-test-target"]
    assert job["target_external_userids"] == ["external-test-target"]
    assert metadata["sender_resolution"]["source"] == "task_config"


def test_runtime_v2_outbox_does_not_enqueue_without_sender(next_pg_schema):
    conn = db()
    program_id = seed_program("runtime_v2_sender_missing")
    task_id = seed_task(program_id, trigger_type="on_event", content_text="hello")
    membership = conn.execute(
        """
        INSERT INTO automation_membership_v2 (program_id, external_userid, joined_at)
        VALUES (?, 'wm_sender_missing', CURRENT_TIMESTAMP)
        RETURNING id
        """,
        (program_id,),
    ).fetchone()
    plan = conn.execute(
        """
        INSERT INTO automation_task_plan_v2 (
            program_id, task_id, membership_id, trigger_type, status, rendered_content_json
        )
        VALUES (?, ?, ?, 'on_event', 'rendered', ?::jsonb)
        RETURNING id
        """,
        (program_id, task_id, int(membership["id"]), json.dumps({"type": "fixed_message", "content_text": "hello"})),
    ).fetchone()
    conn.commit()

    result = enqueue(int(plan["id"]), operator_id="")

    assert result["status"] == "failed"
    assert result["reason"] == "sender_userid_missing"
    assert result["plan"]["status"] == "failed"
    assert result["plan"]["skip_reason"] == "sender_userid_missing"
    assert result["plan"]["broadcast_job_id"] is None
    count = conn.execute("SELECT COUNT(*) AS count FROM broadcast_jobs WHERE source_type = 'automation_runtime_v2'").fetchone()["count"]
    assert int(count) == 0
