from __future__ import annotations

import pytest

from wecom_ability_service import create_app
from wecom_ability_service.db import init_db
from wecom_ability_service.observability import RequestContextFilter
from wecom_ability_service.routes import _dispatch_background_task


@pytest.fixture()
def app(tmp_path):
    db_path = tmp_path / "background-job.sqlite3"
    private_key_path = tmp_path / "wecom_private_key.pem"
    sdk_lib_path = tmp_path / "libWeWorkFinanceSdk_C.so"
    private_key_path.write_text("fake-key", encoding="utf-8")
    sdk_lib_path.write_text("fake-so", encoding="utf-8")

    app = create_app(
        {
            "TESTING": True,
            "CALLBACK_ASYNC_ENABLED": False,
            "DATABASE_PATH": str(db_path),
            "WECOM_CORP_ID": "ww-test",
            "WECOM_CONTACT_SECRET": "contact-secret-test",
            "WECOM_SECRET": "secret-test",
            "WECOM_AGENT_ID": "1000002",
            "WECOM_ARCHIVE_SECRET": "archive-secret",
            "WECOM_API_BASE": "http://fake-wecom.local",
            "WECOM_PRIVATE_KEY_PATH": str(private_key_path),
            "WECOM_SDK_LIB_PATH": str(sdk_lib_path),
        }
    )
    with app.app_context():
        init_db()
    yield app


def test_background_task_logs_include_job_id(app, caplog):
    caplog.handler.addFilter(RequestContextFilter())

    with app.app_context(), caplog.at_level("INFO", logger="callback"):
        _dispatch_background_task("sample_task", lambda: None)

    started = next(record for record in caplog.records if "background task started" in record.getMessage())
    finished = next(record for record in caplog.records if "background task finished" in record.getMessage())

    assert started.job_id
    assert finished.job_id == started.job_id
    assert started.task_name == "sample_task"
    assert finished.task_name == "sample_task"
    assert "job_id=" in started.getMessage()
    assert "task_name=sample_task" in started.getMessage()


def test_http_triggered_background_task_logs_include_parent_request_id(app, caplog):
    caplog.handler.addFilter(RequestContextFilter())

    with app.test_request_context("/health", headers={"X-Request-Id": "parent-request-001"}):
        app.preprocess_request()
        with caplog.at_level("INFO", logger="callback"):
            _dispatch_background_task("http_task", lambda: None)

    started = next(record for record in caplog.records if "background task started" in record.getMessage())
    finished = next(record for record in caplog.records if "background task finished" in record.getMessage())

    assert started.parent_request_id == "parent-request-001"
    assert finished.parent_request_id == "parent-request-001"
    assert "parent_request_id=parent-request-001" in started.getMessage()
    assert "parent_request_id=parent-request-001" in finished.getMessage()
