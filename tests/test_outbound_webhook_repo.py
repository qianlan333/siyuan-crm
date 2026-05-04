from __future__ import annotations

from wecom_ability_service.domains.outbound_webhook.repo import _serialize_delivery_row


def test_serialize_delivery_row_accepts_postgres_jsonb_payload_dict():
    row = {
        "id": 1,
        "event_type": "questionnaire_submit",
        "source_key": "submission_id",
        "source_id": "sub-1",
        "target_url": "https://hooks.local/q",
        "payload_json": {"mobile": "13800138000", "answers": ["A"]},
        "payload_summary": "summary",
        "token_configured": False,
        "status": "pending",
        "attempt_count": 0,
        "max_attempts": 3,
        "response_status_code": None,
        "response_body_summary": "",
        "last_error": "",
        "last_attempted_at": "",
        "next_retry_at": "",
        "created_at": "2026-04-06 17:00:00",
        "updated_at": "2026-04-06 17:00:00",
    }

    payload = _serialize_delivery_row(row)

    assert payload is not None
    assert payload["payload_json"] == '{"mobile":"13800138000","answers":["A"]}'
    assert payload["token_configured"] is False
