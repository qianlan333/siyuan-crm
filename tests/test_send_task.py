"""SendTask v1 契约 — 字段映射 + round-trip + 校验。

不连 PG / Flask。验证：
- 必填字段缺失 / 非法 source_kind / 空 recipients → ValueError
- ``to_enqueue_kwargs()`` 产出的 dict 等价于 ``broadcast_jobs.enqueue_job`` 的关键字
- ``from_broadcast_job`` 是 ``to_enqueue_kwargs`` 的逆（含 sender_userid round-trip）
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from wecom_ability_service.application.send_task import (
    VALID_SEND_TASK_SOURCE_KINDS,
    SendTask,
)
from wecom_ability_service.domains.broadcast_jobs.repo import VALID_SOURCE_TYPES


def _minimal_task(**overrides):
    base = {
        "source_kind": "manual",
        "source_id": "src-1",
        "recipients": ["wm_a", "wm_b"],
        "content": {"fn_name": "send_text", "wecom_payload": {"content": "hi"}},
    }
    base.update(overrides)
    return SendTask(**base)


def test_valid_source_kinds_match_broadcast_jobs_repo():
    # 体检报告的关键不变量：SendTask 的 source_kind 与 broadcast_jobs 表
    # 接受的 source_type 必须始终一致 — 任何一边新增 kind 必须同步另一边。
    assert VALID_SEND_TASK_SOURCE_KINDS == VALID_SOURCE_TYPES


def test_constructor_rejects_unknown_source_kind():
    with pytest.raises(ValueError, match="source_kind"):
        _minimal_task(source_kind="bogus_kind")


def test_constructor_rejects_empty_recipients():
    with pytest.raises(ValueError, match="recipients is empty"):
        _minimal_task(recipients=[])


def test_constructor_allows_empty_recipients_for_handler_resolved_jobs():
    task = _minimal_task(
        source_kind="workflow",
        recipients=[],
        allow_empty_recipients=True,
        content={"workflow_id": 1, "node_id": 1, "pre_scheduled": True},
    )
    assert task.recipients == []
    assert task.allow_empty_recipients is True


def test_constructor_strips_recipient_whitespace_and_blanks():
    task = _minimal_task(recipients=["  wm_a  ", "", "wm_b", "   "])
    assert task.recipients == ["wm_a", "wm_b"]


def test_to_enqueue_kwargs_default_scheduled_for_is_now_utc():
    before = datetime.now(timezone.utc)
    kwargs = _minimal_task().to_enqueue_kwargs()
    after = datetime.now(timezone.utc)
    scheduled = kwargs["scheduled_for"]
    assert isinstance(scheduled, datetime)
    assert scheduled.tzinfo is not None
    assert before <= scheduled <= after


def test_to_enqueue_kwargs_field_mapping():
    task = SendTask(
        source_kind="campaign",
        source_id="42:1",
        source_table="campaign_members",
        recipients=["wm_x", "wm_y"],
        content={"step": {"step_index": 1}, "text": {"content": "hello"}},
        sender_userid="alice",
        scheduled_for="2026-05-11 09:00:00+00:00",
        priority=50,
        requires_approval=True,
        batch_key="batch-7",
        trace_id="trace-abc",
        created_by="cron-test",
        target_summary="42 人",
        content_summary="hello…",
        content_type="private_message",
    )
    kwargs = task.to_enqueue_kwargs()
    assert kwargs["source_type"] == "campaign"
    assert kwargs["source_id"] == "42:1"
    assert kwargs["source_table"] == "campaign_members"
    assert kwargs["target_external_userids"] == ["wm_x", "wm_y"]
    # sender_userid 不在 broadcast_jobs schema 里 — 经由 content_payload 携带
    assert kwargs["content_payload"]["_sender_userid"] == "alice"
    assert kwargs["content_payload"]["text"] == {"content": "hello"}
    assert kwargs["scheduled_for"] == "2026-05-11 09:00:00+00:00"
    assert kwargs["priority"] == 50
    assert kwargs["requires_approval"] is True
    assert kwargs["allow_empty_targets"] is False
    assert kwargs["batch_key"] == "batch-7"
    assert kwargs["trace_id"] == "trace-abc"
    assert kwargs["created_by"] == "cron-test"
    assert kwargs["target_summary"] == "42 人"
    assert kwargs["content_summary"] == "hello…"
    assert kwargs["content_type"] == "private_message"


def test_to_enqueue_kwargs_omits_sender_userid_when_blank():
    kwargs = _minimal_task().to_enqueue_kwargs()
    assert "_sender_userid" not in kwargs["content_payload"]


def test_to_enqueue_kwargs_maps_empty_recipient_override():
    task = SendTask(
        source_kind="workflow",
        source_id="pre-scheduled-workflow-1",
        source_table="automation_workflow_executions",
        recipients=[],
        content={"workflow_id": 1, "node_id": 1, "pre_scheduled": True},
        allow_empty_recipients=True,
        target_summary="workflow node=1",
        content_type="private_message",
    )

    kwargs = task.to_enqueue_kwargs()

    assert kwargs["target_external_userids"] == []
    assert kwargs["allow_empty_targets"] is True


def test_round_trip_from_broadcast_job_preserves_fields():
    original = SendTask(
        source_kind="sop",
        source_id="batch-9",
        source_table="automation_sop_batches",
        recipients=["wm_p", "wm_q"],
        content={"batch_id": 9, "day_index": 2},
        sender_userid="sop_runner",
        scheduled_for="2026-05-11 09:30:00+00:00",
        priority=80,
        requires_approval=False,
        batch_key="",
        trace_id="trace-sop-9",
        created_by="cron-sop",
        target_summary="2 人",
        content_summary="day 2 推送",
        content_type="private_message",
    )
    # 模拟 broadcast_jobs 行：to_enqueue_kwargs → enqueue_job → DB → fetch_job_by_id
    enqueue_kwargs = original.to_enqueue_kwargs()
    fake_row = {
        "source_type": enqueue_kwargs["source_type"],
        "source_id": enqueue_kwargs["source_id"],
        "source_table": enqueue_kwargs["source_table"],
        "scheduled_for": enqueue_kwargs["scheduled_for"],
        "priority": enqueue_kwargs["priority"],
        "batch_key": enqueue_kwargs["batch_key"],
        "requires_approval": enqueue_kwargs["requires_approval"],
        "target_external_userids": enqueue_kwargs["target_external_userids"],
        "target_summary": enqueue_kwargs["target_summary"],
        "content_type": enqueue_kwargs["content_type"],
        "content_payload": enqueue_kwargs["content_payload"],
        "content_summary": enqueue_kwargs["content_summary"],
        "trace_id": enqueue_kwargs["trace_id"],
        "created_by": enqueue_kwargs["created_by"],
    }
    revived = SendTask.from_broadcast_job(fake_row)
    assert revived == original


def test_from_broadcast_job_allows_empty_target_rows():
    row = {
        "source_type": "workflow",
        "source_id": "pre-scheduled-workflow-1",
        "source_table": "automation_workflow_executions",
        "target_external_userids": [],
        "content_payload": {"workflow_id": 1, "node_id": 1, "pre_scheduled": True},
    }
    task = SendTask.from_broadcast_job(row)
    assert task.recipients == []
    assert task.allow_empty_recipients is True


def test_from_broadcast_job_handles_missing_fields():
    # broadcast_jobs.fetch_job_by_id 永远返回完整列；这里防御性测试缺字段也不崩
    minimal_row = {
        "source_type": "manual",
        "source_id": "x",
        "target_external_userids": ["wm_a"],
        "content_payload": {},
    }
    task = SendTask.from_broadcast_job(minimal_row)
    assert task.source_kind == "manual"
    assert task.recipients == ["wm_a"]
    assert task.sender_userid == ""
    assert task.priority == 100
    assert task.requires_approval is False
