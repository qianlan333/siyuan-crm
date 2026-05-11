from __future__ import annotations

import pytest

from wecom_ability_service.observability import RequestContextFilter
from wecom_ability_service.routes import _dispatch_background_task


@pytest.fixture()
def app(tmp_path):
    from tests.conftest import build_pg_test_app

    with build_pg_test_app(tmp_path, CALLBACK_ASYNC_ENABLED=False) as app:
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
