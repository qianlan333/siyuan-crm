from __future__ import annotations

import logging

import pytest

from wecom_ability_service import create_app
from wecom_ability_service.db import init_db


@pytest.fixture()
def app(tmp_path):
    db_path = tmp_path / "observability.sqlite3"
    receipts_path = tmp_path / "temporary-webhook-receiver.jsonl"
    private_key_path = tmp_path / "wecom_private_key.pem"
    sdk_lib_path = tmp_path / "libWeWorkFinanceSdk_C.so"
    private_key_path.write_text("fake-key", encoding="utf-8")
    sdk_lib_path.write_text("fake-so", encoding="utf-8")

    app = create_app(
        {
            "TESTING": True,
            "DATABASE_PATH": str(db_path),
            "WECOM_CORP_ID": "ww-test",
            "WECOM_CONTACT_SECRET": "contact-secret-test",
            "WECOM_SECRET": "secret-test",
            "WECOM_AGENT_ID": "1000002",
            "WECOM_ARCHIVE_SECRET": "archive-secret",
            "WECOM_API_BASE": "http://fake-wecom.local",
            "WECOM_PRIVATE_KEY_PATH": str(private_key_path),
            "WECOM_SDK_LIB_PATH": str(sdk_lib_path),
            "RELEASE_SHA": "release-test-sha",
            "TEMP_WEBHOOK_RECEIPTS_PATH": str(receipts_path),
        }
    )
    with app.app_context():
        init_db()
    yield app


@pytest.fixture()
def client(app):
    return app.test_client()


def test_request_id_is_generated_and_written_to_response_header(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.headers["X-Request-Id"]


def test_request_id_is_forwarded_from_request_header(client):
    response = client.get("/health", headers={"X-Request-Id": "custom-request-id-001"})

    assert response.status_code == 200
    assert response.headers["X-Request-Id"] == "custom-request-id-001"


def test_favicon_route_returns_no_content(client):
    response = client.get("/favicon.ico")

    assert response.status_code == 204


def test_temporary_webhook_receiver_stores_request_payload(client):
    response = client.post(
        "/api/tmp/webhook-receiver?source=questionnaire",
        json={"submission_id": 151, "mobile": "13800138000"},
        headers={
            "User-Agent": "pytest-webhook-client",
            "X-Request-Id": "tmp-webhook-request-001",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["stored"] is True
    assert payload["receipt"]["received_at"]

    list_response = client.get("/api/tmp/webhook-receiver/receipts")
    assert list_response.status_code == 200
    list_payload = list_response.get_json()
    assert list_payload["count"] == 1
    assert list_payload["items"][0]["query"] == {"source": "questionnaire"}
    assert list_payload["items"][0]["json"] == {"submission_id": 151, "mobile": "13800138000"}
    assert list_payload["items"][0]["headers"]["user-agent"] == "pytest-webhook-client"


def test_temporary_webhook_receiver_returns_latest_receipts_first(client):
    for index in range(3):
        response = client.post(
            "/api/tmp/webhook-receiver",
            json={"submission_id": index + 1},
            headers={"User-Agent": f"pytest-webhook-client-{index}"},
        )
        assert response.status_code == 200

    list_response = client.get("/api/tmp/webhook-receiver/receipts?limit=2")
    assert list_response.status_code == 200
    list_payload = list_response.get_json()
    assert list_payload["count"] == 2
    assert [item["json"]["submission_id"] for item in list_payload["items"]] == [3, 2]


def test_temporary_webhook_receiver_receipts_can_be_cleared(client):
    response = client.post("/api/tmp/webhook-receiver", json={"submission_id": 99})
    assert response.status_code == 200

    clear_response = client.delete("/api/tmp/webhook-receiver/receipts")
    assert clear_response.status_code == 200
    assert clear_response.get_json() == {"ok": True, "cleared": True}

    list_response = client.get("/api/tmp/webhook-receiver/receipts")
    assert list_response.status_code == 200
    list_payload = list_response.get_json()
    assert list_payload == {"ok": True, "count": 0, "items": []}


def test_log_records_expose_request_id_and_release_sha(client, app, caplog):
    with caplog.at_level(logging.INFO):
        with app.test_request_context("/health", headers={"X-Request-Id": "log-request-id-001"}):
            app.preprocess_request()
            app.logger.info("in-request-log")

    request_records = [
        record
        for record in caplog.records
        if record.getMessage() == "in-request-log"
        and getattr(record, "request_id", "") == "log-request-id-001"
        and getattr(record, "release_sha", "") == "release-test-sha"
    ]
    assert request_records

    caplog.clear()
    with app.app_context():
        with caplog.at_level(logging.INFO):
            app.logger.info("out-of-request-log")

    standalone = next(record for record in caplog.records if record.getMessage() == "out-of-request-log")
    assert standalone.request_id == ""
    assert standalone.release_sha == "release-test-sha"
