"""``scripts/run_broadcast_queue_worker.py`` 单测 — 调度+发送循环。

mock 掉 dispatch_wecom_task 不真发企微，只验证：
- 成功路径：claim → dispatch → mark_sent
- 失败路径：dispatch raise → mark_failed 且不抛
- 错配置：content_payload 缺 fn_name → mark_failed 不调 dispatch
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from wecom_ability_service.domains.broadcast_jobs import service as queue_service


_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import run_broadcast_queue_worker as worker  # type: ignore[import-not-found]


@pytest.fixture()
def app(tmp_path):
    from tests.conftest import build_pg_test_app

    with build_pg_test_app(tmp_path) as app:
        yield app


def _enqueue_due_job(*, content_payload=None, source_id="job-1"):
    return queue_service.enqueue_job(
        source_type="manual",
        source_id=source_id,
        source_table="manual_test",
        scheduled_for=datetime.now(timezone.utc) - timedelta(minutes=1),
        target_external_userids=["wm_a", "wm_b", "wm_c"],
        target_summary="3 人测试",
        content_type="text",
        content_payload=content_payload or {
            "fn_name": "send_text",
            "wecom_payload": {"content": "hello", "touser": "wm_a|wm_b|wm_c"},
        },
        content_summary="测试文案",
    )


def test_worker_dispatches_due_job_and_marks_sent(app, monkeypatch):
    captured: dict = {}

    def fake_dispatch(task_type, fn_name, payload, **kwargs):
        captured["task_type"] = task_type
        captured["fn_name"] = fn_name
        captured["payload"] = payload
        captured["broadcast_job_id"] = kwargs.get("broadcast_job_id")
        return {"task_id": 555, "wecom_result": {"errcode": 0}}

    monkeypatch.setattr(
        "wecom_ability_service.domains.tasks.service.dispatch_wecom_task_with_intent",
        fake_dispatch,
    )

    with app.app_context():
        job_id = _enqueue_due_job()
        summary = worker.run(batch_size=10)
        job = queue_service.get_job(job_id)

    assert summary["claimed"] == 1
    assert summary["sent_ok"] == 1
    assert summary["sent_failed"] == 0
    assert captured["fn_name"] == "send_text"
    assert captured["broadcast_job_id"] == job_id
    assert job["status"] == "sent"
    assert job["outbound_task_id"] == 555
    assert job["sent_count"] == 3


def test_worker_marks_failed_when_dispatch_raises(app, monkeypatch):
    def fake_dispatch(task_type, fn_name, payload, **kwargs):
        raise RuntimeError("wecom api 401 invalid token")

    monkeypatch.setattr(
        "wecom_ability_service.domains.tasks.service.dispatch_wecom_task_with_intent",
        fake_dispatch,
    )

    with app.app_context():
        job_id = _enqueue_due_job()
        summary = worker.run(batch_size=10)
        job = queue_service.get_job(job_id)

    assert summary["sent_ok"] == 0
    assert summary["sent_failed"] == 1
    assert job["status"] == "failed"
    assert "401" in job["last_error"]


def test_worker_marks_failed_when_payload_missing_fn_name(app, monkeypatch):
    calls: list = []

    def fake_dispatch(*args, **kwargs):
        calls.append((args, kwargs))
        return {"task_id": 1, "wecom_result": {}}

    monkeypatch.setattr(
        "wecom_ability_service.domains.tasks.service.dispatch_wecom_task_with_intent",
        fake_dispatch,
    )

    with app.app_context():
        job_id = _enqueue_due_job(content_payload={"wecom_payload": {"content": "x"}})
        summary = worker.run(batch_size=10)
        job = queue_service.get_job(job_id)

    assert calls == []
    assert summary["sent_failed"] == 1
    assert job["status"] == "failed"
    assert "fn_name" in job["last_error"]


def test_worker_routes_focus_send_to_handler(app, monkeypatch):
    """focus_send 类型的 job 走 focus_send handler 而不是通用的。"""
    captured_batch_ids: list = []

    def fake_run_focus_send_job(*, batch_id):
        captured_batch_ids.append(batch_id)
        return {"ok": True, "sent_count": 5, "failed_count": 1}

    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.focus_send_service.run_focus_send_job",
        fake_run_focus_send_job,
    )

    with app.app_context():
        job_id = queue_service.enqueue_job(
            source_type="focus_send",
            source_id="99",
            source_table="automation_focus_send_batch",
            scheduled_for=datetime.now(timezone.utc) - timedelta(minutes=1),
            target_external_userids=["wm_1", "wm_2", "wm_3", "wm_4", "wm_5"],
            target_summary="5 人",
            content_type="openclaw_push",
            content_payload={"handler": "focus_send", "batch_id": 99},
            content_summary="focus_send test",
        )
        summary = worker.run(batch_size=10)
        job = queue_service.get_job(job_id)

    assert captured_batch_ids == [99]
    assert summary["sent_ok"] == 1
    assert job["status"] == "sent"
    assert job["sent_count"] == 5


def test_worker_no_due_jobs_returns_empty_summary(app):
    with app.app_context():
        summary = worker.run(batch_size=10)
    assert summary["claimed"] == 0
    assert summary["sent_ok"] == 0
    assert summary["sent_failed"] == 0
    assert summary["results"] == []
