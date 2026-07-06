from __future__ import annotations

from scripts.ops import check_wecom_callback_processing_evidence as processing


def _row(**overrides) -> dict:
    row = {
        "id": 42,
        "tenant_id": "aicrm",
        "provider": "wecom",
        "event_family": "external_contact",
        "event_type": "change_external_contact",
        "change_type": "del_external_contact",
        "idempotency_key": "idem-1",
        "status": "succeeded",
        "attempt_count": 0,
        "processing_summary_json": {
            "handled": False,
            "identity_sync_status": "skipped",
            "external_effect_job_ids": [],
        },
        "received_at": "2026-06-27T10:00:00+00:00",
        "started_at": "2026-06-27T10:00:01+00:00",
        "finished_at": "2026-06-27T10:00:02+00:00",
        "age_seconds": 12,
    }
    row.update(overrides)
    return row


def test_processing_evidence_accepts_succeeded_noop_canary_row() -> None:
    payload = processing.evaluate_processing_row(_row(), idempotency_key="idem-1", max_age_seconds=600)

    assert payload["ok"] is True
    assert payload["webhook_inbox_row"]["status"] == "succeeded"
    assert payload["webhook_inbox_row"]["processing_summary_json"]["identity_sync_status"] == "skipped"


def test_processing_evidence_rejects_unprocessed_row() -> None:
    payload = processing.evaluate_processing_row(
        _row(status="received", finished_at="", processing_summary_json={}),
        idempotency_key="idem-1",
        max_age_seconds=600,
    )

    assert payload["ok"] is False
    assert "status is not succeeded" in payload["violations"]
    assert "finished_at is empty" in payload["violations"]


def test_processing_evidence_rejects_succeeded_row_without_started_at() -> None:
    payload = processing.evaluate_processing_row(
        _row(started_at=""),
        idempotency_key="idem-1",
        max_age_seconds=600,
    )

    assert payload["ok"] is False
    assert "started_at is empty" in payload["violations"]


def test_processing_evidence_rejects_canary_that_triggered_business_effects() -> None:
    payload = processing.evaluate_processing_row(
        _row(
            change_type="add_external_contact",
            processing_summary_json={
                "handled": True,
                "identity_sync_status": "success",
                "external_effect_job_ids": [101],
            },
        ),
        idempotency_key="idem-1",
        max_age_seconds=600,
    )

    assert payload["ok"] is False
    assert "change_type is not the default non-entry canary type" in payload["violations"]
    assert "external_effect_job_ids is not empty" in payload["violations"]


def test_processing_evidence_can_allow_business_processing_when_explicit() -> None:
    payload = processing.evaluate_processing_row(
        _row(
            change_type="add_external_contact",
            processing_summary_json={
                "handled": True,
                "identity_sync_status": "success",
                "external_effect_job_ids": [101],
            },
        ),
        idempotency_key="idem-1",
        max_age_seconds=600,
        require_canary_noop=False,
    )

    assert payload["ok"] is True
