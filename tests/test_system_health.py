from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from wecom_ability_service import create_app
from wecom_ability_service.db import get_db, init_db


@pytest.fixture()
def app(tmp_path):
    db_path = tmp_path / "health.sqlite3"
    private_key_path = tmp_path / "wecom_private_key.pem"
    sdk_lib_path = tmp_path / "libWeWorkFinanceSdk_C.so"
    private_key_path.write_text("fake-key", encoding="utf-8")
    sdk_lib_path.write_text("fake-so", encoding="utf-8")
    application = create_app(
        {
            "TESTING": True,
            "DATABASE_PATH": str(db_path),
            "WECOM_CORP_ID": "ww-test",
            "WECOM_CONTACT_SECRET": "contact-secret",
            "WECOM_SECRET": "secret-test",
            "WECOM_AGENT_ID": "1000002",
            "WECOM_ARCHIVE_SECRET": "archive-secret",
            "WECOM_API_BASE": "http://fake-wecom.local",
            "WECOM_PRIVATE_KEY_PATH": str(private_key_path),
            "WECOM_SDK_LIB_PATH": str(sdk_lib_path),
            "WECOM_CALLBACK_TOKEN": "callback-token",
            "WECOM_CALLBACK_AES_KEY": "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
        }
    )
    with application.app_context():
        init_db()
    yield application


@pytest.fixture()
def client(app):
    return app.test_client()


def _insert_event(app, *, status="pending", retry_count=0, minutes_ago=0):
    with app.app_context():
        db = get_db()
        created = (datetime.utcnow() - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%d %H:%M:%S")
        db.execute(
            """
            INSERT INTO wecom_external_contact_event_logs
            (corp_id, event_type, change_type, external_userid, user_id, event_time,
             event_key, payload_xml, payload_json, process_status, retry_count, error_message,
             created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ww-test", "change_external_contact", "add_external_contact",
                "ext_001", "user_01", 1000000,
                f"key-{uuid.uuid4().hex}", "<xml/>", "{}",
                status, retry_count, "",
                created, created,
            ),
        )
        db.commit()


def test_system_health_returns_status(client, app):
    resp = client.get("/api/system/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert "pending_events" in data
    assert "circuit_breaker_state" in data
    assert "started_at" in data
    assert "task_queue_pending" in data


def test_system_health_counts_pending_events(client, app):
    _insert_event(app, status="pending", minutes_ago=5)
    _insert_event(app, status="pending", minutes_ago=1)
    _insert_event(app, status="success", minutes_ago=3)

    resp = client.get("/api/system/health")
    data = resp.get_json()
    assert data["pending_events"] == 2
    assert data["oldest_pending_age_seconds"] is not None
    assert data["oldest_pending_age_seconds"] >= 250


def test_system_health_counts_failed_events(client, app):
    with app.app_context():
        db = get_db()
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        for i in range(3):
            db.execute(
                """
                INSERT INTO wecom_external_contact_event_logs
                (corp_id, event_type, change_type, external_userid, user_id, event_time,
                 event_key, payload_xml, payload_json, process_status, retry_count, error_message,
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'failed', 3, 'error', ?, ?)
                """,
                ("ww-test", "change", "add", "ext", "user", 0, f"fail-{i}", "", "{}", now, now),
            )
        db.commit()

    resp = client.get("/api/system/health")
    data = resp.get_json()
    assert data["failed_events_24h"] == 3


def test_compensating_scan_requeues_stale_events(app):
    _insert_event(app, status="pending", minutes_ago=5, retry_count=0)
    _insert_event(app, status="pending", minutes_ago=5, retry_count=0)
    _insert_event(app, status="success", minutes_ago=5, retry_count=0)

    with app.app_context():
        from wecom_ability_service.http.system_health import run_compensating_scan

        with patch("wecom_ability_service.http.system_health._dispatch_background_task") as mock_dispatch:
            result = run_compensating_scan()

    assert result["scanned"] == 2
    assert result["requeued"] == 2
    assert result["dead_lettered"] == 0
    assert mock_dispatch.call_count == 2


def test_compensating_scan_dead_letters_exhausted_events(app):
    _insert_event(app, status="pending", minutes_ago=5, retry_count=5)

    with app.app_context():
        from wecom_ability_service.http.system_health import run_compensating_scan

        with patch("wecom_ability_service.http.system_health._dispatch_background_task"):
            result = run_compensating_scan()

    assert result["scanned"] == 1
    assert result["requeued"] == 0
    assert result["dead_lettered"] == 1

    with app.app_context():
        db = get_db()
        row = db.execute(
            "SELECT process_status FROM wecom_external_contact_event_logs WHERE retry_count = 5"
        ).fetchone()
        assert row["process_status"] == "dead_letter"


def test_compensating_scan_api_endpoint(client, app):
    _insert_event(app, status="pending", minutes_ago=5, retry_count=0)

    with patch("wecom_ability_service.http.system_health._dispatch_background_task"):
        resp = client.post("/api/system/compensate")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["requeued"] >= 1


def test_callbacks_repo_count_pending(app):
    _insert_event(app, status="pending", minutes_ago=10)
    _insert_event(app, status="processing", minutes_ago=3)

    with app.app_context():
        from wecom_ability_service.domains.callbacks.repo import count_pending_events
        stats = count_pending_events()

    assert stats["pending_count"] == 2
    assert stats["oldest_created_at"] is not None


def test_callbacks_repo_list_stale(app):
    _insert_event(app, status="pending", minutes_ago=5)
    _insert_event(app, status="pending", minutes_ago=0)

    with app.app_context():
        from wecom_ability_service.domains.callbacks.repo import list_stale_pending_events
        stale = list_stale_pending_events(age_seconds=120)

    assert len(stale) == 1
