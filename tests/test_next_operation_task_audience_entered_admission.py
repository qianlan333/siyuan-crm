from __future__ import annotations

import argparse
import json

import pytest

from wecom_ability_service.db import get_db
from aicrm_next.automation_engine.automation_program_admission import admit_channel_contact_to_program
from aicrm_next.automation_engine.automation_program_admission import (
    run_audience_entered_operation_tasks,
)
from wecom_ability_service.domains.automation_conversion.channel_binding_service import bind_channels_to_program
from wecom_ability_service.domains.automation_conversion import operation_task_repo
from wecom_ability_service.domains.automation_conversion.operation_task_replay_service import (
    replay_audience_entered_operation_task,
)
from wecom_ability_service.domains.automation_conversion.projection_repair_service import (
    repair_automation_member_projection,
)
from wecom_ability_service.domains.automation_conversion.questionnaire_bridge_service import (
    sync_questionnaire_submission_audience_transition,
)
from wecom_ability_service.domains.questionnaire.service import submit_questionnaire

from aicrm_next.automation_engine.programs import create_automation_program_operation_task
from automation_channel_admission_helpers import (
    create_channel,
    create_choice_questionnaire,
    create_program,
    disabled_entry_rule,
    save_audience_entry_rule,
    table_count,
)


T1 = "2026-05-23 10:00:00"


def _bind(program_id: int, channel_id: int, payload: dict | None = None) -> int:
    return int(bind_channels_to_program(program_id, [channel_id], payload or {}, "pytest")["bindings"][0]["id"])


def _create_audience_entered_task(program_id: int, *, name: str = "Next realtime task", status: str = "active") -> dict:
    return create_automation_program_operation_task(
        program_id,
        {
            "task_name": name,
            "status": status,
            "trigger_type": "audience_entered",
            "send_time": "10:00",
            "target_stage_code": "operating",
            "target_audience_code": "operating",
            "audience_day_offset": 1,
            "behavior_filter": "none",
            "content_mode": "unified",
            "unified_content_json": {"content_text": f"{name} content"},
        },
        operator_id="pytest",
    )["task"]


def _create_scheduled_daily_task(program_id: int) -> dict:
    return create_automation_program_operation_task(
        program_id,
        {
            "task_name": "Next scheduled daily task",
            "status": "active",
            "trigger_type": "scheduled_daily",
            "send_time": "10:00",
            "target_stage_code": "operating",
            "target_audience_code": "operating",
            "audience_day_offset": 1,
            "behavior_filter": "none",
            "content_mode": "unified",
            "unified_content_json": {"content_text": "scheduled daily content"},
        },
        operator_id="pytest",
    )["task"]


def _setup_admission_case(code: str) -> tuple[int, dict, int]:
    program_id = create_program(code)
    channel = create_channel(f"{code}_channel", program_id=program_id)
    binding_id = _bind(program_id, int(channel["id"]))
    save_audience_entry_rule(program_id, disabled_entry_rule())
    return program_id, channel, binding_id


def _job_count(task_id: int, audience_entry_id: int) -> int:
    return table_count(
        "broadcast_jobs",
        "source_type = 'operation_task' AND source_table = 'automation_operation_task_execution' AND source_id = ?",
        (f"{int(task_id)}:audience_entered:{int(audience_entry_id)}",),
    )


def _execution_count(task_id: int, audience_entry_id: int) -> int:
    return table_count(
        "automation_operation_task_execution",
        "task_id = ? AND execution_id = ?",
        (int(task_id), f"actask-event-{int(task_id)}-{int(audience_entry_id)}"),
    )


def _execution_item_count(task_id: int, audience_entry_id: int) -> int:
    return table_count(
        "automation_operation_task_execution_item",
        "task_id = ? AND audience_entry_id = ?",
        (int(task_id), int(audience_entry_id)),
    )


def _current_entry(external_contact_id: str) -> dict:
    row = get_db().execute(
        """
        SELECT e.id, e.audience_code, e.entry_reason, e.entry_source, m.questionnaire_status, m.current_pool
        FROM automation_member_audience_entry e
        JOIN automation_member m ON m.id = e.member_id
        WHERE m.external_contact_id = ?
          AND e.is_current = TRUE
        ORDER BY e.id DESC
        LIMIT 1
        """,
        (external_contact_id,),
    ).fetchone()
    return dict(row or {})


def test_next_program_admission_triggers_audience_entered_operation_task(app):
    with app.app_context():
        program_id, channel, binding_id = _setup_admission_case("next_rt_admission_trigger")
        task = _create_audience_entered_task(program_id, name="Next admission realtime")

        result = admit_channel_contact_to_program(
            program_id,
            int(channel["id"]),
            binding_id,
            "wm_next_rt_admission_001",
            trigger_time=T1,
        )

        assert result["admission_status"] == "accepted"
        assert result["audience_entry_id"] > 0
        assert result["audience_code"] == "operating"
        assert result["entry_reason"] == "audience_entry_rule_passed"
        assert result["realtime_task_hook"]["ok"] is True
        assert result["realtime_operation_tasks_ran"] == 1
        assert result["realtime_operation_tasks_enqueued_count"] == 1
        assert result["realtime_operation_tasks_results"][0]["execution_id"] == f"actask-event-{task['id']}-{result['audience_entry_id']}"
        assert result["realtime_task_hook"]["side_effect_plan"]["planned"] is True
        assert result["realtime_task_hook"]["side_effect_plan"]["real_external_call_executed"] is False
        assert result["external_push_plan"]["real_external_call_executed"] is False
        assert _execution_count(task["id"], result["audience_entry_id"]) == 1
        assert _job_count(task["id"], result["audience_entry_id"]) == 1

        item = get_db().execute(
            """
            SELECT external_contact_id, status
            FROM automation_operation_task_execution_item
            WHERE execution_id = ?
            LIMIT 1
            """,
            (f"actask-event-{task['id']}-{result['audience_entry_id']}",),
        ).fetchone()
        assert item
        assert item["external_contact_id"] == "wm_next_rt_admission_001"
        assert item["status"] == "queued"


def test_next_program_admission_recheck_is_idempotent_for_audience_entered_task(app):
    with app.app_context():
        program_id, channel, binding_id = _setup_admission_case("next_rt_admission_idempotent")
        task = _create_audience_entered_task(program_id, name="Next admission idempotent")

        first = admit_channel_contact_to_program(
            program_id,
            int(channel["id"]),
            binding_id,
            "wm_next_rt_admission_002",
            trigger_time=T1,
        )
        second = admit_channel_contact_to_program(
            program_id,
            int(channel["id"]),
            binding_id,
            "wm_next_rt_admission_002",
            trigger_time=T1,
        )

        assert first["realtime_operation_tasks_enqueued_count"] == 1
        assert second["admission_status"] == "duplicate_active"
        assert second["audience_entry_id"] == first["audience_entry_id"]
        assert second["realtime_task_hook"]["ok"] is True
        assert second["realtime_operation_tasks_enqueued_count"] == 0
        assert _execution_count(task["id"], first["audience_entry_id"]) == 1
        assert _job_count(task["id"], first["audience_entry_id"]) == 1


def test_next_program_admission_uses_entry_snapshot_program_when_channel_row_points_elsewhere(app):
    with app.app_context():
        old_program_id = create_program("next_rt_channel_row_old_program")
        new_program_id = create_program("next_rt_binding_new_program")
        channel = create_channel("next_rt_shared_channel", program_id=old_program_id)
        binding_id = _bind(new_program_id, int(channel["id"]))
        save_audience_entry_rule(new_program_id, disabled_entry_rule())
        old_task = _create_audience_entered_task(old_program_id, name="Old program must not run")
        new_task = _create_audience_entered_task(new_program_id, name="New binding program runs")

        result = admit_channel_contact_to_program(
            new_program_id,
            int(channel["id"]),
            binding_id,
            "wm_next_rt_binding_program",
            trigger_time=T1,
        )

        assert result["admission_status"] == "accepted"
        assert result["audience_entry_id"] > 0
        assert result["realtime_operation_tasks_enqueued_count"] == 1
        assert result["realtime_operation_tasks_results"][0]["task_id"] == new_task["id"]
        assert _execution_count(new_task["id"], result["audience_entry_id"]) == 1
        assert _job_count(new_task["id"], result["audience_entry_id"]) == 1
        assert _execution_count(old_task["id"], result["audience_entry_id"]) == 0
        assert _job_count(old_task["id"], result["audience_entry_id"]) == 0


def test_audience_entered_behavior_layered_uses_program_member_segment_snapshot(app):
    with app.app_context():
        program_id, channel, binding_id = _setup_admission_case("next_rt_behavior_program_segment")
        admitted = admit_channel_contact_to_program(
            program_id,
            int(channel["id"]),
            binding_id,
            "wm_next_rt_behavior_program_segment",
            trigger_time=T1,
        )
        assert admitted["audience_code"] == "operating"

        get_db().execute(
            """
            UPDATE automation_program_member
            SET state_payload_json = CAST(? AS jsonb)
            WHERE program_id = ?
              AND external_contact_id = ?
            """,
            (
                json.dumps({"behavior_tier_key": "between_2_9"}),
                program_id,
                "wm_next_rt_behavior_program_segment",
            ),
        )
        get_db().commit()

        task = create_automation_program_operation_task(
            program_id,
            {
                "task_name": "Next behavior layered program segment",
                "status": "active",
                "trigger_type": "audience_entered",
                "send_time": "10:00",
                "target_stage_code": "operating",
                "target_audience_code": "operating",
                "audience_day_offset": 1,
                "behavior_filter": "between_2_9",
                "content_mode": "behavior_layered",
                "segment_contents_json": [
                    {
                        "segment_key": "between_2_9",
                        "segment_name": "消息 2-9 条",
                        "content_text": "behavior layered content",
                    }
                ],
            },
            operator_id="pytest",
        )["task"]

        result = run_audience_entered_operation_tasks(
            member_id=int(admitted["member_id"]),
            audience_code="operating",
            audience_entry_id=int(admitted["audience_entry_id"]),
            operator_id="pytest_behavior_segment",
        )

        execution_id = f"actask-event-{int(task['id'])}-{int(admitted['audience_entry_id'])}"
        assert result["ok"] is True
        assert result["ran"] == 1
        assert result["enqueued_count"] == 1
        assert _execution_count(task["id"], admitted["audience_entry_id"]) == 1
        assert _job_count(task["id"], admitted["audience_entry_id"]) == 1

        item = get_db().execute(
            """
            SELECT segment_key, rendered_content_text, status
            FROM automation_operation_task_execution_item
            WHERE execution_id = ?
            LIMIT 1
            """,
            (execution_id,),
        ).fetchone()
        assert item
        assert item["segment_key"] == "between_2_9"
        assert item["rendered_content_text"] == "behavior layered content"
        assert item["status"] == "queued"


def test_audience_entered_invalid_active_task_records_diagnostics_and_replay_requires_explicit_allow(app):
    with app.app_context():
        program_id, channel, binding_id = _setup_admission_case("next_rt_invalid_active_replay")
        admitted = admit_channel_contact_to_program(
            program_id,
            int(channel["id"]),
            binding_id,
            "wm_next_rt_invalid_active_replay",
            trigger_time=T1,
        )
        assert admitted["audience_code"] == "operating"
        get_db().execute(
            """
            UPDATE automation_program_member
            SET state_payload_json = CAST(? AS jsonb)
            WHERE program_id = ?
              AND external_contact_id = ?
            """,
            (
                json.dumps({"behavior_tier_key": "between_2_9"}),
                program_id,
                "wm_next_rt_invalid_active_replay",
            ),
        )
        get_db().commit()
        task = operation_task_repo.insert_task(
            {
                "program_id": program_id,
                "task_name": "Historical invalid behavior task",
                "status": "active",
                "trigger_type": "audience_entered",
                "send_time": "10:00",
                "target_stage_code": "operating",
                "target_audience_code": "operating",
                "audience_day_offset": 1,
                "behavior_filter": "between_2_9",
                "content_mode": "behavior_layered",
                "segment_contents_json": [],
                "created_by": "pytest",
                "updated_by": "pytest",
            }
        )
        get_db().commit()

        first = run_audience_entered_operation_tasks(
            member_id=int(admitted["member_id"]),
            audience_code="operating",
            audience_entry_id=int(admitted["audience_entry_id"]),
            operator_id="pytest_invalid_active",
        )

        execution_id = f"actask-event-{int(task['id'])}-{int(admitted['audience_entry_id'])}"
        assert first["enqueued_count"] == 0
        assert first["results"][0]["reason"] == "behavior_segment_content_missing"
        assert first["results"][0]["content_diagnostics"]["ok"] is False
        assert _execution_count(task["id"], admitted["audience_entry_id"]) == 1
        assert _execution_item_count(task["id"], admitted["audience_entry_id"]) == 0
        assert _job_count(task["id"], admitted["audience_entry_id"]) == 0
        execution = get_db().execute(
            "SELECT status, summary_json FROM automation_operation_task_execution WHERE execution_id = ?",
            (execution_id,),
        ).fetchone()
        assert execution["status"] == "failed"
        assert execution["summary_json"]["no_execution_items"] is True

        fixed = dict(task)
        fixed["segment_contents_json"] = [
            {"segment_key": "between_2_9", "segment_name": "消息 2-9 条", "content_text": "fixed behavior content"}
        ]
        operation_task_repo.update_task(int(task["id"]), fixed)
        get_db().commit()

        blocked = run_audience_entered_operation_tasks(
            member_id=int(admitted["member_id"]),
            audience_code="operating",
            audience_entry_id=int(admitted["audience_entry_id"]),
            operator_id="pytest_invalid_active_again",
        )
        assert blocked["enqueued_count"] == 0
        assert blocked["results"][0]["reason"] == "existing_execution_without_items"
        assert blocked["results"][0]["blocked_by_existing_execution"] is True

        dry_run = replay_audience_entered_operation_task(
            program_id=program_id,
            external_userid="wm_next_rt_invalid_active_replay",
            audience_entry_id=int(admitted["audience_entry_id"]),
            task_ids=[int(task["id"])],
            dry_run=True,
        )
        assert dry_run["results"][0]["can_replay"] is False
        assert dry_run["results"][0]["reason"] == "failed_empty_content_execution_blocks_replay"

        allowed_dry_run = replay_audience_entered_operation_task(
            program_id=program_id,
            external_userid="wm_next_rt_invalid_active_replay",
            audience_entry_id=int(admitted["audience_entry_id"]),
            task_ids=[int(task["id"])],
            dry_run=True,
            allow_failed_empty_execution_retry=True,
        )
        assert allowed_dry_run["results"][0]["can_replay"] is True
        assert allowed_dry_run["results"][0]["retry_of_execution_id"] == execution_id
        assert _execution_item_count(task["id"], admitted["audience_entry_id"]) == 0

        applied = replay_audience_entered_operation_task(
            program_id=program_id,
            external_userid="wm_next_rt_invalid_active_replay",
            audience_entry_id=int(admitted["audience_entry_id"]),
            task_ids=[int(task["id"])],
            dry_run=False,
            allow_failed_empty_execution_retry=True,
        )
        result = applied["results"][0]
        assert result["enqueued_count"] == 1
        assert result["created_execution_id"].startswith(f"actask-event-{int(task['id'])}-{int(admitted['audience_entry_id'])}-retry-")
        assert result["job_id"] > 0
        assert table_count(
            "broadcast_jobs",
            "source_type = 'operation_task' AND source_id = ?",
            (result["source_id"],),
        ) == 1
        assert _execution_item_count(task["id"], admitted["audience_entry_id"]) == 1


def test_admission_persists_behavior_segment_from_questionnaire_mobile_snapshot(app, monkeypatch):
    with app.app_context():
        program_id, channel, binding_id = _setup_admission_case("next_rt_behavior_snapshot_admission")
        questionnaire = create_choice_questionnaire("next_rt_behavior_snapshot_admission_q")
        external_contact_id = "wm_next_rt_behavior_snapshot"
        get_db().execute(
            """
            INSERT INTO questionnaire_submissions (
                questionnaire_id, respondent_key, external_userid, mobile_snapshot, total_score, final_tags, submitted_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(questionnaire["id"]),
                external_contact_id,
                external_contact_id,
                "13900009001",
                0,
                "[]",
                T1,
            ),
        )
        get_db().execute(
            """
            INSERT INTO questionnaire_submissions (
                questionnaire_id, respondent_key, external_userid, mobile_snapshot, total_score, final_tags, submitted_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(questionnaire["id"]),
                f"{external_contact_id}_latest_empty_mobile",
                external_contact_id,
                "",
                0,
                "[]",
                "2026-05-23 10:05:00",
            ),
        )
        get_db().commit()
        monkeypatch.setattr(
            "aicrm_next.automation_engine.automation_program_admission.get_message_activity_db_status",
            lambda: {"configured": True},
        )
        monkeypatch.setattr(
            "aicrm_next.automation_engine.automation_program_admission.query_message_activity_counts",
            lambda: [{"phone_match_key": "139_9001", "message_count": 5}],
        )

        admitted = admit_channel_contact_to_program(
            program_id,
            int(channel["id"]),
            binding_id,
            external_contact_id,
            trigger_time=T1,
        )

        assert admitted["audience_code"] == "operating"
        assert admitted["segmentation"]["behavior_tier_key"] == "between_2_9"
        assert admitted["segmentation"]["behavior_result"]["phone_source"] == "questionnaire_mobile_snapshot"

        program_member = get_db().execute(
            """
            SELECT state_payload_json
            FROM automation_program_member
            WHERE program_id = ?
              AND external_contact_id = ?
            LIMIT 1
            """,
            (program_id, external_contact_id),
        ).fetchone()
        assert program_member
        assert program_member["state_payload_json"]["behavior_tier_key"] == "between_2_9"


def test_next_program_admission_does_not_trigger_unmatched_audience_task(app):
    with app.app_context():
        program_id, channel, binding_id = _setup_admission_case("next_rt_admission_unmatched")
        task = create_automation_program_operation_task(
            program_id,
            {
                "task_name": "Next unmatched realtime",
                "status": "active",
                "trigger_type": "audience_entered",
                "send_time": "10:00",
                "target_stage_code": "operating",
                "target_audience_code": "operating",
                "audience_day_offset": 1,
                "behavior_filter": "gte_10",
                "content_mode": "unified",
                "unified_content_json": {"content_text": "unmatched content"},
            },
            operator_id="pytest",
        )["task"]

        result = admit_channel_contact_to_program(
            program_id,
            int(channel["id"]),
            binding_id,
            "wm_next_rt_admission_003",
            trigger_time=T1,
        )

        assert result["admission_status"] == "accepted"
        assert result["audience_code"] == "operating"
        assert result["realtime_task_hook"]["ok"] is True
        assert result["realtime_operation_tasks_ran"] == 0
        assert result["realtime_operation_tasks_enqueued_count"] == 0
        assert _execution_count(task["id"], result["audience_entry_id"]) == 0
        assert _job_count(task["id"], result["audience_entry_id"]) == 0


def test_next_program_admission_hook_failure_is_reported_without_breaking_admission(app, monkeypatch):
    from aicrm_next.automation_engine.audience_transition.integration_gateway import OperationTaskRealtimeTriggerGateway

    def broken_trigger(self, event):
        raise RuntimeError("realtime hook boom")

    monkeypatch.setattr(OperationTaskRealtimeTriggerGateway, "trigger", broken_trigger)

    with app.app_context():
        program_id, channel, binding_id = _setup_admission_case("next_rt_admission_hook_failure")
        _create_audience_entered_task(program_id, name="Next hook failure")

        result = admit_channel_contact_to_program(
            program_id,
            int(channel["id"]),
            binding_id,
            "wm_next_rt_admission_004",
            trigger_time=T1,
        )

        assert result["admission_status"] == "accepted"
        assert result["audience_entry_id"] > 0
        assert result["realtime_task_hook"]["ok"] is False
        assert "realtime hook boom" in result["realtime_operation_tasks_error"]
        assert table_count("automation_operation_task_execution") == 0
        assert table_count("broadcast_jobs", "source_type = 'operation_task'") == 0


def test_next_program_admission_realtime_hook_does_not_trigger_scheduled_daily_task(app):
    with app.app_context():
        program_id, channel, binding_id = _setup_admission_case("next_rt_admission_scheduled_daily_guard")
        task = _create_scheduled_daily_task(program_id)

        result = admit_channel_contact_to_program(
            program_id,
            int(channel["id"]),
            binding_id,
            "wm_next_rt_admission_005",
            trigger_time=T1,
        )

        assert result["admission_status"] == "accepted"
        assert result["realtime_task_hook"]["ok"] is True
        assert result["realtime_operation_tasks_ran"] == 0
        assert result["realtime_operation_tasks_enqueued_count"] == 0
        assert table_count("automation_operation_task_execution", "task_id = ?", (int(task["id"]),)) == 0
        assert table_count("broadcast_jobs", "source_type = 'operation_task'") == 0


def test_next_program_admission_realtime_hook_does_not_trigger_inactive_task(app):
    with app.app_context():
        program_id, channel, binding_id = _setup_admission_case("next_rt_admission_inactive_guard")
        task = _create_audience_entered_task(program_id, name="Next inactive realtime", status="paused")

        result = admit_channel_contact_to_program(
            program_id,
            int(channel["id"]),
            binding_id,
            "wm_next_rt_admission_inactive",
            trigger_time=T1,
        )

        assert result["admission_status"] == "accepted"
        assert result["realtime_task_hook"]["ok"] is True
        assert result["realtime_operation_tasks_ran"] == 0
        assert result["realtime_operation_tasks_enqueued_count"] == 0
        assert table_count("automation_operation_task_execution", "task_id = ?", (int(task["id"]),)) == 0
        assert table_count("broadcast_jobs", "source_type = 'operation_task'") == 0


def test_next_program_admission_rejects_closed_program_without_realtime_side_effects(app):
    with app.app_context():
        program_id = create_program("next_rt_closed_program_guard", status="archived")
        channel = create_channel("next_rt_closed_program_guard_channel", program_id=program_id)
        binding_id = _bind(program_id, int(channel["id"]))
        save_audience_entry_rule(program_id, disabled_entry_rule())
        task = _create_audience_entered_task(program_id, name="Closed program must not run")

        result = admit_channel_contact_to_program(
            program_id,
            int(channel["id"]),
            binding_id,
            "wm_next_rt_closed_program",
            trigger_time=T1,
        )

        assert result["admission_status"] == "rejected"
        assert result["accepted"] is False
        assert result["reason"] == "program_archived"
        assert result["source_status"] == "next_command"
        assert result["fallback_used"] is False
        assert result["real_external_call_executed"] is False
        assert result["audit"]["entry_reason"] == "program_archived"
        assert result["external_push_plan"]["planned"] is False
        assert result["external_push_plan"]["real_external_call_executed"] is False
        assert table_count("automation_program_member", "program_id = ?", (program_id,)) == 0
        assert table_count("automation_operation_task_execution", "task_id = ?", (int(task["id"]),)) == 0
        assert table_count("broadcast_jobs", "source_type = 'operation_task'") == 0


def test_questionnaire_submit_moves_pending_entry_to_operating_and_triggers_audience_entered_task(app):
    with app.app_context():
        program_id, channel, binding_id = _setup_admission_case("next_rt_questionnaire_submit")
        questionnaire = create_choice_questionnaire("next_rt_questionnaire_submit_q")
        task = _create_audience_entered_task(program_id, name="Next questionnaire realtime")
        save_audience_entry_rule(
            program_id,
            {
                "order_review": {"enabled": False},
                "questionnaire_review": {"enabled": True, "selected_questionnaire_id": questionnaire["id"]},
                "conversion_review": {"enabled": False},
            },
        )

        admitted = admit_channel_contact_to_program(
            program_id,
            int(channel["id"]),
            binding_id,
            "wm_next_rt_questionnaire_001",
            trigger_time=T1,
        )
        pending_entry = _current_entry("wm_next_rt_questionnaire_001")

        assert admitted["admission_status"] == "waiting"
        assert admitted["audience_code"] == "pending_questionnaire"
        assert admitted["entry_reason"] == "questionnaire_review_pending"
        assert admitted["realtime_operation_tasks_enqueued_count"] == 0
        assert pending_entry["audience_code"] == "pending_questionnaire"
        assert pending_entry["entry_reason"] == "questionnaire_review_pending"
        assert _job_count(task["id"], pending_entry["id"]) == 0

        submit_result = submit_questionnaire(
            questionnaire["slug"],
            {
                "external_userid": "wm_next_rt_questionnaire_001",
                "answers": {str(questionnaire["question_id"]): questionnaire["option_a_id"]},
            },
            request_meta={},
        )
        operating_entry = _current_entry("wm_next_rt_questionnaire_001")

        assert submit_result["success"] is True
        assert table_count("questionnaire_submissions", "questionnaire_id = ?", (int(questionnaire["id"]),)) == 1
        assert operating_entry["questionnaire_status"] == "submitted"
        assert operating_entry["current_pool"] == "operating"
        assert operating_entry["audience_code"] == "operating"
        assert operating_entry["entry_reason"] == "audience_entry_rule_passed"
        assert _execution_count(task["id"], operating_entry["id"]) == 1
        assert _execution_item_count(task["id"], operating_entry["id"]) == 1
        assert _job_count(task["id"], operating_entry["id"]) == 1

        job = get_db().execute(
            """
            SELECT source_type, content_payload
            FROM broadcast_jobs
            WHERE source_id = ?
            LIMIT 1
            """,
            (f"{int(task['id'])}:audience_entered:{int(operating_entry['id'])}",),
        ).fetchone()
        assert job
        assert job["source_type"] == "operation_task"
        assert job["content_payload"]["trigger_type"] == "audience_entered"

        submission = get_db().execute(
            "SELECT id FROM questionnaire_submissions WHERE questionnaire_id = ? LIMIT 1",
            (int(questionnaire["id"]),),
        ).fetchone()
        repeated = sync_questionnaire_submission_audience_transition(
            external_contact_id="wm_next_rt_questionnaire_001",
            questionnaire_id=int(questionnaire["id"]),
            submission_id=int(submission["id"]),
            operator_id="pytest_repeat",
        )
        assert repeated["ok"] is True
        assert _execution_count(task["id"], operating_entry["id"]) == 1
        assert _execution_item_count(task["id"], operating_entry["id"]) == 1
        assert _job_count(task["id"], operating_entry["id"]) == 1


def test_projection_repair_dry_run_and_apply_syncs_questionnaire_operating_state(app):
    with app.app_context():
        program_id, channel, binding_id = _setup_admission_case("next_rt_projection_repair")
        questionnaire = create_choice_questionnaire("next_rt_projection_repair_q")
        external_contact_id = "wm_next_rt_projection_repair"
        admitted = admit_channel_contact_to_program(
            program_id,
            int(channel["id"]),
            binding_id,
            external_contact_id,
            trigger_time=T1,
        )
        assert admitted["audience_code"] == "operating"
        get_db().execute(
            """
            INSERT INTO questionnaire_submissions (
                questionnaire_id, respondent_key, external_userid, mobile_snapshot, total_score, final_tags, submitted_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (int(questionnaire["id"]), external_contact_id, external_contact_id, "13900000088", 0, "[]", T1),
        )
        get_db().execute(
            """
            UPDATE automation_member
            SET questionnaire_status = 'pending',
                current_pool = 'pending_questionnaire',
                current_audience_code = 'operating'
            WHERE external_contact_id = ?
            """,
            (external_contact_id,),
        )
        get_db().execute(
            """
            UPDATE automation_program_member
            SET current_stage_code = 'pending_questionnaire',
                current_audience_code = 'pending_questionnaire'
            WHERE program_id = ?
              AND external_contact_id = ?
            """,
            (program_id, external_contact_id),
        )
        get_db().commit()

        dry_run = repair_automation_member_projection(
            external_userid=external_contact_id,
            program_id=program_id,
            dry_run=True,
        )
        assert dry_run["would_update"] is True
        assert dry_run["diff"]["member"]["questionnaire_status"]["after"] == "submitted"
        assert dry_run["diff"]["member"]["current_pool"]["after"] == "operating"

        row = get_db().execute(
            "SELECT questionnaire_status, current_pool FROM automation_member WHERE external_contact_id = ?",
            (external_contact_id,),
        ).fetchone()
        assert row["questionnaire_status"] == "pending"
        assert row["current_pool"] == "pending_questionnaire"

        applied = repair_automation_member_projection(
            external_userid=external_contact_id,
            program_id=program_id,
            dry_run=False,
            apply=True,
            operator_id="pytest_projection_repair",
        )
        assert applied["updated"] is True
        row = get_db().execute(
            "SELECT id, questionnaire_status, current_pool, current_audience_code, phone FROM automation_member WHERE external_contact_id = ?",
            (external_contact_id,),
        ).fetchone()
        assert row["questionnaire_status"] == "submitted"
        assert row["current_pool"] == "operating"
        assert row["current_audience_code"] == "operating"
        assert row["phone"] == "13900000088"
        assert table_count("automation_event", "member_id = ? AND action = ?", (int(row["id"]), "projection_repair")) == 1


def test_questionnaire_submit_bridge_reports_source_channel_missing_without_enqueue(app):
    with app.app_context():
        program_id, channel, binding_id = _setup_admission_case("next_rt_questionnaire_missing_channel")
        questionnaire = create_choice_questionnaire("next_rt_questionnaire_missing_channel_q")
        task = _create_audience_entered_task(program_id, name="Next questionnaire missing channel")
        save_audience_entry_rule(
            program_id,
            {
                "order_review": {"enabled": False},
                "questionnaire_review": {"enabled": True, "selected_questionnaire_id": questionnaire["id"]},
                "conversion_review": {"enabled": False},
            },
        )
        admit_channel_contact_to_program(
            program_id,
            int(channel["id"]),
            binding_id,
            "wm_next_rt_questionnaire_002",
            trigger_time=T1,
        )
        get_db().execute(
            "UPDATE automation_member SET source_channel_id = NULL WHERE external_contact_id = ?",
            ("wm_next_rt_questionnaire_002",),
        )
        get_db().commit()
        submit_questionnaire(
            questionnaire["slug"],
            {
                "external_userid": "wm_next_rt_questionnaire_002",
                "answers": {str(questionnaire["question_id"]): questionnaire["option_a_id"]},
            },
            request_meta={},
        )
        operating_entry = _current_entry("wm_next_rt_questionnaire_002")

        assert operating_entry["audience_code"] == "operating"
        assert operating_entry["entry_reason"] == "audience_entry_rule_passed"
        assert _execution_count(task["id"], operating_entry["id"]) == 0
        assert _execution_item_count(task["id"], operating_entry["id"]) == 0
        assert _job_count(task["id"], operating_entry["id"]) == 0

        repeated = sync_questionnaire_submission_audience_transition(
            external_contact_id="wm_next_rt_questionnaire_002",
            questionnaire_id=int(questionnaire["id"]),
            operator_id="pytest_missing_channel",
        )
        assert repeated["ok"] is True
        assert repeated["reason"] == "source_channel_missing"
        assert repeated["realtime_task_hook"]["realtime_operation_tasks_reason"] == "source_channel_missing"


def test_questionnaire_submit_bridge_reports_missing_audience_entry(app):
    with app.app_context():
        program_id, channel, binding_id = _setup_admission_case("next_rt_missing_audience_entry")
        admit_channel_contact_to_program(
            program_id,
            int(channel["id"]),
            binding_id,
            "wm_next_rt_missing_entry",
            trigger_time=T1,
        )
        member = get_db().execute(
            "SELECT id FROM automation_member WHERE external_contact_id = ? LIMIT 1",
            ("wm_next_rt_missing_entry",),
        ).fetchone()
        get_db().execute(
            "DELETE FROM automation_member_audience_entry WHERE member_id = ?",
            (int(member["id"]),),
        )
        get_db().commit()

        result = run_audience_entered_operation_tasks(
            member_id=int(member["id"]),
            audience_code="operating",
            audience_entry_id=999991,
            operator_id="pytest_missing_entry",
        )

        assert result["ok"] is True
        assert result["reason"] == "audience_entry_not_found"


def test_active_agent_operation_task_requires_agent_code_at_save_time(app):
    with app.app_context():
        program_id, _, _ = _setup_admission_case("next_rt_agent_code_guard")

        with pytest.raises(ValueError, match="agent_code"):
            create_automation_program_operation_task(
                program_id,
                {
                    "task_name": "Agent without code",
                    "status": "active",
                    "trigger_type": "audience_entered",
                    "target_stage_code": "operating",
                    "target_audience_code": "operating",
                    "content_mode": "agent",
                    "agent_config_json": {},
                },
                operator_id="pytest",
            )


def test_repair_invalid_operation_task_patches_behavior_segments_with_validation(app):
    from scripts.repair_invalid_operation_tasks import repair

    with app.app_context():
        program_id, _, _ = _setup_admission_case("next_rt_behavior_repair")
        task = operation_task_repo.insert_task(
            {
                "program_id": program_id,
                "task_name": "Behavior repair target",
                "status": "active",
                "trigger_type": "audience_entered",
                "target_stage_code": "operating",
                "target_audience_code": "operating",
                "behavior_filter": "none",
                "content_mode": "behavior_layered",
                "segment_contents_json": [],
                "created_by": "pytest",
                "updated_by": "pytest",
            }
        )
        get_db().commit()

        missing = repair(
            argparse.Namespace(
                program_id=program_id,
                task_id=[task["id"]],
                action="patch-behavior-segments",
                fallback_content="",
                segment=["lt_2=少于 2 条消息内容", "between_2_9=2 到 9 条消息内容"],
                apply=False,
                dry_run=True,
                operator_id="pytest",
            )
        )
        assert missing["results"][0]["ok"] is False
        assert "missing required behavior segments" in missing["results"][0]["reason"]

        dry_run = repair(
            argparse.Namespace(
                program_id=program_id,
                task_id=[task["id"]],
                action="patch-behavior-segments",
                fallback_content="",
                segment=["lt_2=少于 2 条消息内容", "between_2_9=2 到 9 条消息内容", "gte_10=10 条及以上消息内容"],
                apply=False,
                dry_run=True,
                operator_id="pytest",
            )
        )
        assert dry_run["results"][0]["ok"] is True
        assert dry_run["results"][0]["after"]["publishable_diagnostics"]["ok"] is True
        stored = operation_task_repo.get_task(task["id"])
        assert stored["segment_contents_json"] == []

        applied = repair(
            argparse.Namespace(
                program_id=program_id,
                task_id=[task["id"]],
                action="patch-behavior-segments",
                fallback_content="",
                segment=["lt_2=少于 2 条消息内容", "between_2_9=2 到 9 条消息内容", "gte_10=10 条及以上消息内容"],
                apply=True,
                dry_run=False,
                operator_id="pytest",
            )
        )
        assert applied["results"][0]["ok"] is True
        assert applied["results"][0]["applied_publishable_diagnostics"]["ok"] is True
        stored = operation_task_repo.get_task(task["id"])
        assert {item["segment_key"] for item in stored["segment_contents_json"]} == {"lt_2", "between_2_9", "gte_10"}


def test_replay_operation_task_script_accepts_batched_scopes():
    from scripts.replay_operation_task_audience_entered import _parse_args, _scopes

    args = _parse_args(
        [
            "--program-id",
            "1",
            "--external-userid",
            "wm_one",
            "--audience-entry-id",
            "1155",
            "--external-userid",
            "wm_two",
            "--audience-entry-id",
            "1157",
            "--task-id",
            "3",
            "--task-id",
            "22",
            "--dry-run",
        ]
    )

    assert _scopes(args) == [
        {"external_userid": "wm_one", "member_id": 0, "audience_entry_id": 1155},
        {"external_userid": "wm_two", "member_id": 0, "audience_entry_id": 1157},
    ]
