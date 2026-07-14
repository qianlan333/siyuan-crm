from __future__ import annotations

import json

from scripts.diagnose_external_orders_blockers import classify_evidence


EXPECTED_CONSUMERS = [
    "order_projection_consumer",
    "service_period_entitlement_consumer",
    "webhook_order_paid_consumer",
    "customer_business_summary_consumer",
    "dnd_policy_consumer",
    "ai_assist_notify_consumer",
]


def _fixture(*, status: str = "pending", attempt_count: int = 0, config: dict | None = None) -> dict:
    return {
        "order_id": "156",
        "source": {"type": "fixture"},
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
                "status": status,
                "attempt_count": attempt_count,
                "last_error_code": "",
                "last_error_message": "",
                "next_retry_at": "",
            }
            for name in EXPECTED_CONSUMERS
        ],
        "payment_succeeded_consumer_run_due_config": {
            "token_configured": True,
            "auto_execute_enabled": True,
            "allowlist_required": True,
            "allowed_event_types": ["payment.succeeded"],
            "allowed_consumers": EXPECTED_CONSUMERS,
            "allowed_event_consumers": [f"payment.succeeded:{name}" for name in EXPECTED_CONSUMERS],
            **(config or {}),
        },
        "external_effect_linkage": {
            "jobs": [{"id": 96, "status": "succeeded", "execution_mode": "execute"}],
            "attempts": [{"id": 97, "status": "succeeded", "adapter_mode": "execute"}],
            "push_center_status": "sent",
        },
        "order_customer_channel_linkage": {
            "order_id": "156",
            "provider": "wechat_pay",
            "source": "h5_checkout",
            "external_userid_present": True,
            "raw_external_userid": "wm_raw_should_not_appear",
            "mobile": "13800000000",
            "openid": "openid_should_not_appear",
            "unionid": "unionid_should_not_appear",
            "order_no": "full_order_no_should_not_appear",
            "customer_list_index_rows": 1,
            "customer_detail_snapshot_rows": 1,
            "channel_contact_rows": 1,
            "channel_ids_present": 1,
            "projection_source_found": True,
        },
    }


def _run_due(payload: dict) -> dict:
    return classify_evidence(payload)["payment_succeeded_consumer_run_due"]


def test_pending_consumers_are_ready_for_operator_preview_when_gates_are_present() -> None:
    run_due = _run_due(_fixture())

    assert run_due["classification"] == "run_due_ready_for_operator_preview"
    assert run_due["run_due_eligible"] is True
    assert run_due["preview_route_available"] is True
    assert run_due["can_execute_in_operator_window"] is True
    assert run_due["recommended_execution_mode"] == "operator_preview_first_then_batch_size_one_single_consumer_execute_after_approval"
    assert run_due["real_external_call_risk"] == "none_from_internal_event_worker; webhook_order_paid_consumer may create_or_reuse external_effect_job only"
    assert run_due["production_write_risk"] == "execute_writes_consumer_run_attempts_and_may_enqueue_external_effect_job"


def test_missing_token_blocks_run_due_preview() -> None:
    run_due = _run_due(_fixture(config={"token_configured": False}))

    assert run_due["classification"] == "run_due_blocked_by_token"
    assert run_due["token_gate_status"] == "missing_internal_token_config"
    assert run_due["blocking_reason"] == "missing_internal_token_config"
    assert run_due["can_execute_in_operator_window"] is False


def test_auto_execute_disabled_blocks_run_due_execute_path() -> None:
    run_due = _run_due(_fixture(config={"auto_execute_enabled": False}))

    assert run_due["classification"] == "run_due_blocked_by_auto_execute_config"
    assert run_due["blocking_reason"] == "auto_execute_disabled_for_run_due_execute"
    assert run_due["recommended_execution_mode"] == "fix_gate_or_collect_operator_approval_before_any_execute"


def test_missing_allowlist_blocks_run_due_execute_path() -> None:
    run_due = _run_due(
        _fixture(
            config={
                "allowed_event_types": [],
                "allowed_consumers": [],
                "allowed_event_consumers": [],
                "allowlist_missing": True,
            }
        )
    )

    assert run_due["classification"] == "run_due_blocked_by_allowlist"
    assert run_due["allowlist_status"] == "missing_or_incomplete"
    assert run_due["blocking_reason"] == "event_or_consumer_allowlist_missing"


def test_already_succeeded_consumers_do_not_need_run_due() -> None:
    run_due = _run_due(_fixture(status="succeeded", attempt_count=1))

    assert run_due["classification"] == "consumer_already_succeeded"
    assert run_due["operator_action_required"] is False
    assert run_due["recommended_execution_mode"] == "no_execute_recollect_external_orders_evidence"


def test_failed_retryable_consumers_are_retryable_operator_work() -> None:
    run_due = _run_due(_fixture(status="failed_retryable", attempt_count=1))

    assert run_due["classification"] == "consumer_failed_retryable"
    assert run_due["can_execute_in_operator_window"] is True
    assert run_due["blocking_reason"] == "retryable_consumer_failure"


def test_explicitly_skippable_pending_consumers_are_classified_for_operator_skip() -> None:
    payload = _fixture()
    payload["consumer_runs"] = []
    for consumer_name in EXPECTED_CONSUMERS:
        is_optional = consumer_name in {"customer_business_summary_consumer", "dnd_policy_consumer", "ai_assist_notify_consumer"}
        payload["consumer_runs"].append(
            {
                "consumer_name": consumer_name,
                "status": "pending" if is_optional else "succeeded",
                "attempt_count": 0 if is_optional else 1,
                "last_error_code": "",
                "last_error_message": "",
            }
        )
    payload["explicitly_skippable_consumers"] = [
        "customer_business_summary_consumer",
        "dnd_policy_consumer",
        "ai_assist_notify_consumer",
    ]

    run_due = _run_due(payload)

    assert run_due["classification"] == "consumer_explicitly_skippable"
    assert run_due["recommended_execution_mode"] == "operator_preview_then_manual_skip_with_approved_reason_if_non_applicable"


def test_non_applicable_event_type_is_not_run_due_work() -> None:
    payload = _fixture()
    payload["internal_event"]["event_type"] = "questionnaire.submitted"

    run_due = _run_due(payload)

    assert run_due["classification"] == "consumer_non_applicable"
    assert run_due["operator_action_required"] is False


def test_consumer_run_due_diagnostics_redact_sensitive_values() -> None:
    payload = classify_evidence(_fixture(config={"token_configured": True}))
    dumped = json.dumps(payload, ensure_ascii=False)

    assert "wm_raw_should_not_appear" not in dumped
    assert "13800000000" not in dumped
    assert "openid_should_not_appear" not in dumped
    assert "unionid_should_not_appear" not in dumped
    assert "full_order_no_should_not_appear" not in dumped
    assert "iev_demo_should_be_redacted_dff3" not in dumped
    assert "required_token_or_gate" in dumped
    assert "OAuth automation-worker access token" in dumped
    assert "AUTOMATION_INTERNAL_API_TOKEN" not in dumped
