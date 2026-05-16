from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ...domains.broadcast_jobs.repo import VALID_SOURCE_TYPES


VALID_SEND_TASK_SOURCE_KINDS: tuple[str, ...] = VALID_SOURCE_TYPES


@dataclass
class SendTask:
    """Canonical outbound-send task.

    v1 是 ``broadcast_jobs.enqueue_job`` 契约的纯重命名层：``source_kind``↔
    ``source_type``、``recipients``↔``target_external_userids``、``content``↔
    ``content_payload``。``to_enqueue_kwargs()`` 把字段映回 enqueue_job 的关键字。

    ``sender_userid`` 不是 broadcast_jobs schema 字段——为保留 round-trip，非空时
    会在 ``to_enqueue_kwargs`` 里塞进 ``content['_sender_userid']``，
    ``from_broadcast_job`` 反向取出。这样 broadcast_jobs DB schema 完全不动。

    ``allow_empty_recipients`` 对应 ``broadcast_jobs.enqueue_job`` 的
    ``allow_empty_targets``，用于 workflow / campaign 预排期这类"到点后 handler
    再解析收件人"的任务；普通即时发送仍然默认拒绝空收件人。
    """

    source_kind: str
    source_id: str
    recipients: list[str] = field(default_factory=list)
    content: dict[str, Any] = field(default_factory=dict)

    source_table: str = ""
    sender_userid: str = ""
    scheduled_for: Any = None
    priority: int = 100
    requires_approval: bool = False
    allow_empty_recipients: bool = False
    batch_key: str = ""
    trace_id: str = ""
    created_by: str = ""
    target_summary: str = ""
    content_summary: str = ""
    content_type: str = "text"

    def __post_init__(self) -> None:
        kind = str(self.source_kind or "").strip()
        if kind not in VALID_SEND_TASK_SOURCE_KINDS:
            raise ValueError(f"invalid source_kind: {self.source_kind!r}")
        self.source_kind = kind
        self.source_id = str(self.source_id or "")
        cleaned_recipients: list[str] = []
        for raw in self.recipients or []:
            text = str(raw or "").strip()
            if text:
                cleaned_recipients.append(text)
        self.allow_empty_recipients = bool(self.allow_empty_recipients)
        if not cleaned_recipients and not self.allow_empty_recipients:
            raise ValueError("recipients is empty")
        self.recipients = cleaned_recipients
        self.content = dict(self.content or {})
        self.priority = int(self.priority)
        self.requires_approval = bool(self.requires_approval)
        self.sender_userid = str(self.sender_userid or "").strip()
        self.trace_id = str(self.trace_id or "")
        self.created_by = str(self.created_by or "")
        self.target_summary = str(self.target_summary or "")
        self.content_summary = str(self.content_summary or "")
        self.content_type = str(self.content_type or "text")
        self.batch_key = str(self.batch_key or "")
        self.source_table = str(self.source_table or "")

    def to_enqueue_kwargs(self) -> dict[str, Any]:
        payload = dict(self.content)
        if self.sender_userid:
            payload["_sender_userid"] = self.sender_userid
        return {
            "source_type": self.source_kind,
            "source_id": self.source_id,
            "source_table": self.source_table,
            "scheduled_for": self.scheduled_for if self.scheduled_for is not None else datetime.now(timezone.utc),
            "target_external_userids": list(self.recipients),
            "target_summary": self.target_summary,
            "content_type": self.content_type,
            "content_payload": payload,
            "content_summary": self.content_summary,
            "batch_key": self.batch_key,
            "priority": self.priority,
            "requires_approval": self.requires_approval,
            "allow_empty_targets": self.allow_empty_recipients,
            "trace_id": self.trace_id,
            "created_by": self.created_by,
        }

    @classmethod
    def from_broadcast_job(cls, row: dict[str, Any]) -> "SendTask":
        content = dict(row.get("content_payload") or {})
        sender_userid = str(content.pop("_sender_userid", "") or "").strip()
        return cls(
            source_kind=str(row.get("source_type") or ""),
            source_id=str(row.get("source_id") or ""),
            recipients=list(row.get("target_external_userids") or []),
            content=content,
            source_table=str(row.get("source_table") or ""),
            sender_userid=sender_userid,
            scheduled_for=row.get("scheduled_for"),
            priority=int(row.get("priority") or 100),
            requires_approval=bool(row.get("requires_approval") or False),
            allow_empty_recipients=not bool(row.get("target_external_userids") or []),
            batch_key=str(row.get("batch_key") or ""),
            trace_id=str(row.get("trace_id") or ""),
            created_by=str(row.get("created_by") or ""),
            target_summary=str(row.get("target_summary") or ""),
            content_summary=str(row.get("content_summary") or ""),
            content_type=str(row.get("content_type") or "text"),
        )
