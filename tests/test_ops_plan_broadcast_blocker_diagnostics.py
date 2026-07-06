from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.diagnose_ops_plan_broadcast_blocker import classify_evidence


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "diagnose_ops_plan_broadcast_blocker.py"
PLANNER = "broadcast_task_planner_consumer"


def _base_fixture() -> dict:
    return {
        "plan_id": "external_daily_lesson_20260617_1230_huangyoucan_v1_b11",
        "source": {"type": "fixture"},
        "approval_event": {
            "exists": True,
            "event_id": "iev_demo_should_be_redacted_fd6b",
            "event_type": "ops_plan.approved",
            "aggregate_type": "cloud_orchestrator_plan",
            "aggregate_id": "external_daily_lesson_20260617_1230_huangyoucan_v1_b11",
        },
        "consumer_runs": [
            {"consumer_name": "audit_projection_consumer", "status": "pending", "attempt_count": 0},
            {"consumer_name": "automation_schedule_refresh_consumer", "status": "pending", "attempt_count": 0},
            {"consumer_name": PLANNER, "status": "pending", "attempt_count": 0},
            {"consumer_name": "ops_plan_ai_assist_notify_consumer", "status": "pending", "attempt_count": 0},
        ],
        "ops_plan_broadcast_run_due_config": {
            "token_configured": True,
            "auto_execute_enabled": True,
            "allowed_event_types": ["ops_plan.approved"],
            "allowed_consumers": [PLANNER],
            "allowed_event_consumers": [f"ops_plan.approved:{PLANNER}"],
            "allowlist_required": True,
        },
    }


def test_pending_planner_attempt_zero_is_ready_for_operator_preview_when_gates_present() -> None:
    payload = classify_evidence(_base_fixture())

    assert payload["readonly"] is True
    assert payload["real_external_call_executed"] is False
    assert payload["production_write_executed"] is False
    assert payload["classification"] == "run_due_ready_for_operator_preview"
    assert payload["broadcast_task_planner_consumer"]["consumer_name"] == PLANNER
    assert payload["attempt_count"] == 0
    assert payload["preview_route_available"] is True
    assert payload["run_due_eligible"] is True
    assert payload["can_execute_in_operator_window"] is True
    assert payload["downstream_job_expected"] is True
    assert payload["push_center_visibility_expected"] is True


def test_missing_token_blocks_preview_and_run() -> None:
    fixture = _base_fixture()
    fixture["ops_plan_broadcast_run_due_config"]["token_configured"] = False

    payload = classify_evidence(fixture)

    assert payload["classification"] == "run_due_blocked_by_token"
    assert payload["token_gate_status"] == "missing_internal_token_config"
    assert payload["blocking_reason"] == "missing_internal_token_or_admin_action_gate"


def test_auto_execute_disabled_blocks_generic_run_due_execute() -> None:
    fixture = _base_fixture()
    fixture["ops_plan_broadcast_run_due_config"]["auto_execute_enabled"] = False

    payload = classify_evidence(fixture)

    assert payload["classification"] == "run_due_blocked_by_auto_execute_config"
    assert payload["auto_execute_enabled"] is False
    assert payload["recommended_execution_mode"] == "fix_gate_or_collect_operator_approval_before_any_execute"


def test_missing_allowlist_blocks_execute() -> None:
    fixture = _base_fixture()
    fixture["ops_plan_broadcast_run_due_config"]["allowed_event_consumers"] = ["payment.succeeded:webhook_order_paid_consumer"]

    payload = classify_evidence(fixture)

    assert payload["classification"] == "run_due_blocked_by_allowlist"
    assert payload["allowlist_missing"] is True
    assert payload["allowlist_status"] == "missing_or_incomplete"


def test_already_succeeded_is_classified_without_operator_action() -> None:
    fixture = _base_fixture()
    for row in fixture["consumer_runs"]:
        if row["consumer_name"] == PLANNER:
            row["status"] = "succeeded"
            row["attempt_count"] = 1

    payload = classify_evidence(fixture)

    assert payload["classification"] == "planner_runtime_repair_required"
    assert payload["operator_action_required"] is True
    assert payload["recommended_execution_mode"] == "manual_review_readonly_only"


def test_created_broadcast_job_is_classified_with_downstream_evidence_fields() -> None:
    fixture = _base_fixture()
    for row in fixture["consumer_runs"]:
        if row["consumer_name"] == PLANNER:
            row["status"] = "succeeded"
            row["attempt_count"] = 1
            row["result_summary_json"] = {
                "planner_result": "planner_created_broadcast_job",
                "broadcast_job_id": 42,
                "push_center_job_id": "broadcast_job:42",
                "idempotency_key": "ops_plan_approved_broadcast:demo",
                "duplicate_handling": "created",
                "downstream_status": "broadcast_job_queued",
            }
    fixture["downstream"] = {"broadcast_job_count": 1, "broadcast_job_ids": [42], "external_effect_job_count": 0}

    payload = classify_evidence(fixture)

    assert payload["classification"] == "planner_created_broadcast_job"
    assert payload["planner_result"] == "planner_created_broadcast_job"
    assert payload["broadcast_job_id"] == 42
    assert payload["push_center_job_id"] == "broadcast_job:42"
    assert payload["duplicate_handling"] == "created"
    assert payload["downstream_status"] == "broadcast_job_queued"
    assert payload["operator_action_required"] is False
    assert payload["recommended_execution_mode"] == "do_not_rerun_planner_recollect_downstream_broadcast_and_push_center_evidence"


def test_reused_broadcast_job_is_classified_idempotently() -> None:
    fixture = _base_fixture()
    for row in fixture["consumer_runs"]:
        if row["consumer_name"] == PLANNER:
            row["status"] = "succeeded"
            row["attempt_count"] = 2
            row["result_summary_json"] = {
                "planner_result": "planner_reused_broadcast_job",
                "broadcast_job_id": 42,
                "push_center_job_id": "broadcast_job:42",
                "duplicate_handling": "reused",
            }

    payload = classify_evidence(fixture)

    assert payload["classification"] == "planner_reused_broadcast_job"
    assert payload["duplicate_handling"] == "reused"


def test_skipped_missing_required_input_is_explicit() -> None:
    fixture = _base_fixture()
    for row in fixture["consumer_runs"]:
        if row["consumer_name"] == PLANNER:
            row["status"] = "skipped"
            row["attempt_count"] = 1
            row["result_summary_json"] = {
                "planner_result": "planner_skipped_missing_required_input",
                "reason": "missing_audience",
            }

    payload = classify_evidence(fixture)

    assert payload["classification"] == "planner_skipped_missing_required_input"
    assert payload["blocking_reason"] == "planner_missing_required_input"


def test_skipped_non_applicable_is_explicit() -> None:
    fixture = _base_fixture()
    for row in fixture["consumer_runs"]:
        if row["consumer_name"] == PLANNER:
            row["status"] = "skipped"
            row["attempt_count"] = 1
            row["result_summary_json"] = {
                "planner_result": "planner_skipped_non_applicable",
                "reason": "consumer_non_applicable",
            }

    payload = classify_evidence(fixture)

    assert payload["classification"] == "planner_skipped_non_applicable"


def test_legacy_campaign_event_is_reclassified_as_non_applicable() -> None:
    fixture = _base_fixture()
    fixture["approval_event"]["payload_summary_json"] = {
        "plan_type": "legacy_campaign",
        "source": "legacy_campaign",
        "target_count": 47,
    }
    for row in fixture["consumer_runs"]:
        if row["consumer_name"] == PLANNER:
            row["status"] = "skipped"
            row["attempt_count"] = 2
            row["result_summary_json"] = {
                "planner_result": "planner_skipped_non_applicable",
                "reason": "consumer_non_applicable",
                "plan_type": "legacy_campaign",
            }

    payload = classify_evidence(fixture)

    assert payload["classification"] == "legacy_event_non_applicable"
    assert payload["planner_consumer_pending_classification"] == "legacy_event_non_applicable"
    assert payload["event_plan_type"] == "legacy_campaign"
    assert payload["legacy_event_reclassification"]["classification"] == "legacy_event_non_applicable"
    assert payload["legacy_event_reclassification"]["can_judge_next_native_planner"] is False
    assert payload["next_native_evidence_target_status"] == "BLOCKED_NEXT_NATIVE_TARGET_MISSING"
    assert payload["operator_action_required"] is True
    assert payload["required_operator_action"] == "create_or_approve_next_native_test_plan"
    assert payload["recommended_execution_mode"] == "do_not_rerun_legacy_event_select_next_native_cloud_plan_target"


def test_next_native_plan_with_recipients_and_messages_is_ready_for_evidence() -> None:
    fixture = _base_fixture()
    fixture["next_native_evidence_target"] = {
        "plan_id": "cloud_plan_ready_001",
        "plan_type": "cloud_plan",
        "approval_event_exists": True,
        "recipient_projection_count": 3,
        "message_projection_count": 3,
        "planner_consumer_executable": True,
    }

    payload = classify_evidence(fixture)

    assert payload["classification"] == "run_due_ready_for_operator_preview"
    assert payload["next_native_evidence_target_status"] == "next_native_plan_ready_for_evidence"
    assert payload["can_recollect_ops_plan_e2e_now"] is True
    assert payload["next_native_target_blocking_reason"] == ""


def test_next_native_plan_missing_recipients_blocks_evidence_target() -> None:
    fixture = _base_fixture()
    fixture["next_native_evidence_target"] = {
        "plan_id": "cloud_plan_missing_recipients",
        "plan_type": "cloud_plan",
        "approval_event_exists": True,
        "recipient_projection_count": 0,
        "message_projection_count": 2,
    }

    payload = classify_evidence(fixture)

    assert payload["next_native_evidence_target_status"] == "next_native_plan_missing_recipients"
    assert payload["next_native_target_blocking_reason"] == "next_native_recipient_projection_missing"
    assert payload["can_recollect_ops_plan_e2e_now"] is False


def test_next_native_plan_missing_messages_blocks_evidence_target() -> None:
    fixture = _base_fixture()
    fixture["next_native_evidence_target"] = {
        "plan_id": "cloud_plan_missing_messages",
        "plan_type": "cloud_plan",
        "approval_event_exists": True,
        "recipient_projection_count": 2,
        "message_projection_count": 0,
    }

    payload = classify_evidence(fixture)

    assert payload["next_native_evidence_target_status"] == "next_native_plan_missing_messages"
    assert payload["next_native_target_blocking_reason"] == "next_native_message_projection_missing"
    assert payload["can_recollect_ops_plan_e2e_now"] is False


def test_failed_retryable_is_classified_for_operator_retry_preview() -> None:
    fixture = _base_fixture()
    for row in fixture["consumer_runs"]:
        if row["consumer_name"] == PLANNER:
            row["status"] = "failed"
            row["attempt_count"] = 1
            row["last_error_code"] = "planner_transient_error"

    payload = classify_evidence(fixture)

    assert payload["classification"] == "planner_failed_retryable"
    assert payload["retry_route_available"] is True
    assert payload["can_execute_in_operator_window"] is True


def test_sensitive_values_are_redacted_from_output() -> None:
    fixture = _base_fixture()
    fixture["approval_event"]["raw_external_userid"] = "wm_raw_should_not_appear"
    fixture["approval_event"]["phone"] = "13800000000"
    fixture["approval_event"]["target_list"] = ["raw_member_should_not_appear"]
    fixture["next_native_evidence_target"] = {
        "plan_id": "cloud_plan_sensitive_probe",
        "plan_type": "cloud_plan",
        "recipient_projection_count": 1,
        "message_projection_count": 1,
        "raw_external_userid": "wm_next_target_should_not_appear",
        "mobile": "13900000000",
        "raw_target_list": ["raw_target_should_not_appear"],
        "member_customer_identifier": "member_customer_should_not_appear",
    }
    fixture["ops_plan_broadcast_run_due_config"]["secret"] = "secret_should_not_appear"
    fixture["ops_plan_broadcast_run_due_config"]["Authorization"] = "Bearer token_should_not_appear"

    payload = classify_evidence(fixture)
    dumped = json.dumps(payload, ensure_ascii=False)

    assert "wm_raw_should_not_appear" not in dumped
    assert "13800000000" not in dumped
    assert "raw_member_should_not_appear" not in dumped
    assert "secret_should_not_appear" not in dumped
    assert "token_should_not_appear" not in dumped
    assert "wm_next_target_should_not_appear" not in dumped
    assert "13900000000" not in dumped
    assert "raw_target_should_not_appear" not in dumped
    assert "member_customer_should_not_appear" not in dumped
    assert "iev_demo_should_be_redacted_fd6b" not in dumped
    assert "iev_***fd6b" in dumped


def test_cli_help_runs() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Readonly triage" in result.stdout


def test_cli_can_classify_input_json_fixture(tmp_path: Path) -> None:
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(json.dumps(_base_fixture()), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--input-json", str(fixture_path), "--indent", "0"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["classification"] == "run_due_ready_for_operator_preview"
    assert payload["planner_consumer_pending_classification"] == "run_due_ready_for_operator_preview"
