from __future__ import annotations

from scripts.ops import check_wecom_callback_ingestion_evidence as ingestion


def test_ingestion_evidence_extracts_idempotency_key_from_pressure_payload() -> None:
    payload = {
        "sample_validation": {
            "ok": True,
            "idempotency_key": "ww-test|change_external_contact|add_external_contact|wm-a|sales-a|1782530000|welcome-a|scene-a",
        }
    }

    assert (
        ingestion.extract_idempotency_key_from_pressure_evidence(payload)
        == "ww-test|change_external_contact|add_external_contact|wm-a|sales-a|1782530000|welcome-a|scene-a"
    )


def test_ingestion_evidence_accepts_recent_webhook_inbox_row() -> None:
    payload = ingestion.evaluate_ingestion_row(
        {
            "id": 42,
            "tenant_id": "aicrm",
            "provider": "wecom",
            "event_family": "external_contact",
            "corp_id": "ww-test",
            "event_type": "change_external_contact",
            "change_type": "add_external_contact",
            "external_event_id": "idem-1",
            "idempotency_key": "idem-1",
            "status": "received",
            "attempt_count": 0,
            "duplicate_count": 1,
            "received_at": "2026-06-27T10:00:00+00:00",
            "last_seen_at": "2026-06-27T10:00:01+00:00",
            "finished_at": None,
            "age_seconds": 12,
        },
        idempotency_key="idem-1",
        max_age_seconds=600,
    )

    assert payload["ok"] is True
    assert payload["webhook_inbox_row"]["found"] is True
    assert payload["webhook_inbox_row"]["status"] == "received"
    assert payload["webhook_inbox_row"]["duplicate_count"] == 1


def test_ingestion_evidence_rejects_missing_or_old_row() -> None:
    missing = ingestion.evaluate_ingestion_row(None, idempotency_key="idem-1", max_age_seconds=600)
    assert missing["ok"] is False
    assert missing["webhook_inbox_row"]["found"] is False

    old = ingestion.evaluate_ingestion_row(
        {
            "provider": "wecom",
            "event_family": "external_contact",
            "idempotency_key": "idem-1",
            "status": "succeeded",
            "age_seconds": 601,
        },
        idempotency_key="idem-1",
        max_age_seconds=600,
    )

    assert old["ok"] is False
    assert any("exceeds 600 seconds" in violation for violation in old["violations"])
