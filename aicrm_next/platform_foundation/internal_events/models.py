from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from aicrm_next.platform_foundation.command_bus.models import CommandContext

DEFAULT_TENANT_ID = "aicrm"

InternalEventConsumerRunStatus = Literal[
    "pending",
    "running",
    "succeeded",
    "failed_retryable",
    "failed_terminal",
    "blocked",
    "skipped",
]
InternalEventConsumerAttemptStatus = Literal[
    "succeeded",
    "failed_retryable",
    "failed_terminal",
    "blocked",
    "skipped",
]
InternalEventConsumerType = Literal["projection", "orchestration", "external_effect_planner", "diagnostic"]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def public_datetime(value: Any) -> str:
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value or "").strip()
        if not text:
            return ""
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return text
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class InternalEventCreateRequest:
    event_type: str
    aggregate_type: str
    aggregate_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    payload_summary: dict[str, Any] = field(default_factory=dict)
    context: CommandContext = field(default_factory=CommandContext)
    event_version: int = 1
    subject_type: str = ""
    subject_id: str = ""
    idempotency_key: str = ""
    source_module: str = ""
    source_command_id: str = ""
    correlation_id: str = ""
    occurred_at: datetime | None = None
    tenant_id: str = DEFAULT_TENANT_ID


@dataclass(frozen=True)
class InternalEvent:
    id: int = 0
    tenant_id: str = DEFAULT_TENANT_ID
    event_id: str = field(default_factory=lambda: "iev_" + uuid4().hex)
    event_type: str = ""
    event_version: int = 1
    aggregate_type: str = ""
    aggregate_id: str = ""
    subject_type: str = ""
    subject_id: str = ""
    idempotency_key: str = ""
    actor_id: str = ""
    actor_type: str = "system"
    source_module: str = ""
    source_route: str = ""
    source_command_id: str = ""
    trace_id: str = ""
    request_id: str = ""
    correlation_id: str = ""
    occurred_at: str = ""
    payload_json: dict[str, Any] = field(default_factory=dict)
    payload_summary_json: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class InternalEventConsumerRun:
    id: int = 0
    tenant_id: str = DEFAULT_TENANT_ID
    event_id: str = ""
    consumer_name: str = ""
    consumer_type: str = "projection"
    status: InternalEventConsumerRunStatus = "pending"
    attempt_count: int = 0
    max_attempts: int = 5
    next_retry_at: str = ""
    locked_at: str = ""
    locked_by: str = ""
    last_attempt_id: str = ""
    last_error_code: str = ""
    last_error_message: str = ""
    result_summary_json: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    finished_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class InternalEventConsumerAttempt:
    id: int = 0
    attempt_id: str = field(default_factory=lambda: "iea_" + uuid4().hex)
    consumer_run_id: int = 0
    consumer_name: str = ""
    status: InternalEventConsumerAttemptStatus = "skipped"
    request_summary_json: dict[str, Any] = field(default_factory=dict)
    response_summary_json: dict[str, Any] = field(default_factory=dict)
    error_code: str = ""
    error_message: str = ""
    started_at: str = ""
    completed_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class InternalEventConsumerResult:
    status: InternalEventConsumerAttemptStatus
    request_summary: dict[str, Any] = field(default_factory=dict)
    response_summary: dict[str, Any] = field(default_factory=dict)
    result_summary: dict[str, Any] = field(default_factory=dict)
    error_code: str = ""
    error_message: str = ""
    retry_after_seconds: int | None = None

    @property
    def ok(self) -> bool:
        return self.status == "succeeded"
