from __future__ import annotations

import pytest

from aicrm_next.data_health.quality_registry import (
    data_quality_checks_by_group,
    get_data_quality_check_definition,
    list_data_quality_check_definitions,
    list_data_quality_groups,
)


EXPECTED_GROUP_COUNTS = {
    "identity": 5,
    "payment": 4,
    "questionnaire": 4,
    "delivery": 4,
    "customer_projection": 3,
}


def test_data_quality_registry_groups_all_operational_rules() -> None:
    groups = list_data_quality_groups()
    checks = list_data_quality_check_definitions()
    grouped = data_quality_checks_by_group()

    assert [group["group"] for group in groups] == list(EXPECTED_GROUP_COUNTS)
    assert {group: len(items) for group, items in grouped.items()} == EXPECTED_GROUP_COUNTS
    assert len(checks) == sum(EXPECTED_GROUP_COUNTS.values())
    assert len({check["check_id"] for check in checks}) == len(checks)


def test_data_quality_registry_contains_phase7_contract_ids() -> None:
    check_ids = {check["check_id"] for check in list_data_quality_check_definitions()}

    assert {
        "identity_pending_queue_threshold",
        "identity_conflict_count",
        "identity_unionid_duplicate",
        "identity_external_userid_multi_unionid",
        "identity_mobile_multi_active_unionid",
        "payment_paid_order_missing_identity",
        "payment_paid_order_missing_product_code",
        "payment_refund_amount_exceeds_paid",
        "payment_provider_status_inconsistent",
        "questionnaire_submission_missing_unionid",
        "questionnaire_submission_missing_answers",
        "questionnaire_answer_missing_question",
        "questionnaire_final_tags_malformed",
        "delivery_broadcast_job_blocked",
        "delivery_external_effect_retryable_failures",
        "delivery_outbound_task_failed",
        "delivery_stuck_queued_claimed",
        "customer_projection_read_model_stale",
        "customer_projection_customer_360_stale",
        "customer_projection_timeline_missing_recent_activity",
    } == check_ids


def test_data_quality_registry_is_metadata_only_until_probes_are_attached() -> None:
    checks = list_data_quality_check_definitions()

    assert {check["probe_status"] for check in checks} == {"needs_probe"}
    assert {check["severity"] for check in checks} <= {"red", "yellow"}
    for check in checks:
        assert check["title"]
        assert check["description"]
        assert check["signal"]
        assert check["threshold"]
        assert check["source_tables"]
        assert check["remediation"]


def test_data_quality_registry_keeps_identity_values_out_of_payloads() -> None:
    serialized = str(list_data_quality_check_definitions())

    for forbidden in (
        "external_userid_value",
        "openid_value",
        "mobile_normalized_value",
        "unionid_value",
        "raw_payload_json",
    ):
        assert forbidden not in serialized


def test_data_quality_registry_lookup_returns_single_definition() -> None:
    definition = get_data_quality_check_definition("delivery_stuck_queued_claimed")

    assert definition is not None
    assert definition["group"] == "delivery"
    assert definition["source_tables"] == [
        "broadcast_jobs",
        "external_effect_job",
        "outbound_tasks",
    ]
    assert get_data_quality_check_definition("not_a_quality_check") is None


@pytest.fixture()
def client(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from aicrm_next.main import create_app

    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "0")
    monkeypatch.setenv("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", "1")
    return TestClient(create_app(), raise_server_exceptions=False)


def test_data_quality_summary_api_exposes_registry_counts(client) -> None:
    response = client.get("/api/admin/data-quality/summary")

    assert response.status_code == 200
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    body = response.json()
    assert body["ok"] is True
    assert body["total_checks"] == 20
    assert body["group_counts"] == EXPECTED_GROUP_COUNTS
    assert body["probe_status_counts"] == {"needs_probe": 20, "registered": 0}
    assert body["severity_counts"]["red"] >= 1
    assert body["severity_counts"]["yellow"] >= 1


def test_data_quality_groups_and_checks_api_are_metadata_only(client) -> None:
    groups = client.get("/api/admin/data-quality/groups")
    checks = client.get("/api/admin/data-quality/checks")

    assert groups.status_code == 200
    assert {group["group"]: group["check_count"] for group in groups.json()["groups"]} == EXPECTED_GROUP_COUNTS
    assert checks.status_code == 200
    assert len(checks.json()["checks"]) == 20
    assert {check["probe_status"] for check in checks.json()["checks"]} == {"needs_probe"}
    assert "raw_payload_json" not in checks.text
    assert "external_userid_value" not in checks.text


def test_data_quality_check_detail_api_and_missing_check(client) -> None:
    detail = client.get("/api/admin/data-quality/checks/payment_paid_order_missing_identity")

    assert detail.status_code == 200
    payload = detail.json()
    assert payload["ok"] is True
    assert payload["check"]["group"] == "payment"
    assert payload["check"]["source_tables"] == [
        "wechat_pay_orders",
        "alipay_pay_orders",
        "crm_user_identity",
    ]

    missing = client.get("/api/admin/data-quality/checks/not_a_quality_check")
    assert missing.status_code == 404
    assert missing.json()["error_code"] == "data_quality_check_not_found"
