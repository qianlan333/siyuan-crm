from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.diagnose_external_orders_blockers import classify_evidence


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "diagnose_external_orders_blockers.py"


EXPECTED_CONSUMERS = [
    "order_projection_consumer",
    "service_period_entitlement_consumer",
    "webhook_order_paid_consumer",
    "customer_business_summary_consumer",
    "dnd_policy_consumer",
    "ai_assist_notify_consumer",
]


def _production_like_fixture() -> dict:
    return {
        "order_id": "156",
        "source": {"type": "fixture", "status": "redacted"},
        "internal_event": {
            "exists": True,
            "event_id": "iev_demo_should_be_redacted_dff3",
            "event_type": "payment.succeeded",
            "aggregate_type": "wechat_pay_order",
            "aggregate_id": "156",
        },
        "consumer_runs": [
            {
                "consumer_name": name,
                "status": "pending",
                "attempt_count": 0,
                "last_error_code": "",
                "last_error_message": "",
            }
            for name in EXPECTED_CONSUMERS
        ],
        "external_effect_linkage": {
            "jobs": [
                {"id": 96, "status": "succeeded", "execution_mode": "execute"},
                {"id": 95, "status": "succeeded", "execution_mode": "execute"},
            ],
            "attempts": [
                {"id": 97, "status": "succeeded", "adapter_mode": "execute"},
                {"id": 96, "status": "succeeded", "adapter_mode": "execute"},
            ],
            "push_center_status": "sent",
        },
        "order_customer_channel_linkage": {
            "order_id": "156",
            "provider": "wechat_pay",
            "source": "h5_checkout",
            "external_userid_present": True,
            "raw_external_userid": "wm_raw_should_not_appear",
            "phone": "13800000000",
            "customer_list_index_rows": 0,
            "customer_detail_snapshot_rows": 0,
            "channel_contact_rows": 1,
            "channel_ids_present": 1,
            "projection_source_found": True,
        },
    }


def test_production_like_evidence_classifies_pending_consumers_and_missing_customer_linkage() -> None:
    payload = classify_evidence(_production_like_fixture())
    conclusion = payload["conclusion"]

    assert payload["readonly"] is True
    assert payload["real_external_call_executed"] is False
    assert payload["production_write_executed"] is False
    assert conclusion["blocker_1_classification"] == "consumer_run_pending_due_to_config"
    assert conclusion["blocker_1_repair_decision"] == "run_due_not_executed"
    assert conclusion["blocker_1_next_pr_required"] is True
    assert conclusion["blocker_2_classification"] == "linkage_missing"
    assert conclusion["blocker_2_repair_decision"] == "backfill_required"
    assert conclusion["blocker_2_next_pr_required"] is True
    assert conclusion["operator_action_required"] is True
    assert conclusion["data_backfill_required"] is True
    assert conclusion["runtime_fix_required"] is True
    assert conclusion["can_recollect_external_orders_evidence"] is False
    assert conclusion["can_claim_external_orders_90_plus"] is False
    assert payload["external_effect_linkage"]["classification"] == "expected_not_applicable"
    assert payload["internal_event_consumer_pending_decision"]["run_due_route_available"] is True
    assert payload["internal_event_consumer_pending_decision"]["consumer_placeholder_only"] is False
    assert payload["payment_succeeded_consumer_run_due"]["classification"] == "run_due_ready_for_operator_preview"
    assert payload["payment_succeeded_consumer_run_due"]["preview_route_available"] is True
    assert payload["payment_succeeded_consumer_run_due"]["required_token_or_gate"]
    assert payload["customer_read_model_linkage_decision"]["projection_status"] == "backfill_required"
    assert payload["customer_read_model_linkage_decision"]["projection_source_found"] is True
    assert payload["customer_read_model_linkage_decision"]["projection_target_found"] is False
    assert payload["customer_read_model_linkage_decision"]["approved_backfill_runbook_required"] is True


def test_complete_evidence_allows_recollection_without_blockers() -> None:
    fixture = _production_like_fixture()
    for row in fixture["consumer_runs"]:
        row["status"] = "succeeded"
        row["attempt_count"] = 1
    fixture["order_customer_channel_linkage"]["customer_list_index_rows"] = 1

    payload = classify_evidence(fixture)
    conclusion = payload["conclusion"]

    assert conclusion["blocker_1_classification"] == "expected_not_applicable"
    assert conclusion["blocker_1_repair_decision"] == "expected_not_applicable"
    assert conclusion["blocker_2_classification"] == "expected_not_applicable"
    assert conclusion["blocker_2_repair_decision"] == "expected_not_applicable"
    assert payload["customer_read_model_linkage_decision"]["projection_status"] == "projection_fixed"
    assert conclusion["operator_action_required"] is False
    assert conclusion["can_recollect_external_orders_evidence"] is True


def test_missing_expected_consumer_is_classified_as_not_registered() -> None:
    fixture = _production_like_fixture()
    fixture["consumer_runs"] = fixture["consumer_runs"][:-1]

    payload = classify_evidence(fixture)

    assert payload["internal_event"]["classification"] == "consumer_not_registered"
    assert payload["internal_event_consumer_pending_decision"]["repair_decision"] == "runtime_repair_required"
    assert "ai_assist_notify_consumer" in payload["internal_event"]["missing_consumers"]
    assert payload["conclusion"]["runtime_fix_required"] is True


def test_missing_customer_identity_requires_identity_triage() -> None:
    fixture = _production_like_fixture()
    fixture["order_customer_channel_linkage"]["external_userid_present"] = False
    fixture["order_customer_channel_linkage"]["channel_contact_rows"] = 0
    fixture["order_customer_channel_linkage"]["channel_ids_present"] = 0

    payload = classify_evidence(fixture)

    assert payload["order_customer_channel_linkage"]["classification"] == "linkage_missing"
    assert payload["customer_read_model_linkage_decision"]["repair_decision"] == "customer_identity_missing"
    assert payload["conclusion"]["blocker_2_next_pr_required"] is True


def test_sensitive_values_are_redacted_from_output() -> None:
    payload = classify_evidence(_production_like_fixture())
    dumped = json.dumps(payload, ensure_ascii=False)

    assert "wm_raw_should_not_appear" not in dumped
    assert "13800000000" not in dumped
    assert "external_userid_present" in dumped
    assert "iev_demo_should_be_redacted_dff3" not in dumped
    assert "iev_***dff3" in dumped


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
    fixture_path.write_text(json.dumps(_production_like_fixture()), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--input-json", str(fixture_path), "--indent", "0"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["conclusion"]["blocker_1_classification"] == "consumer_run_pending_due_to_config"
    assert payload["conclusion"]["blocker_2_classification"] == "linkage_missing"
