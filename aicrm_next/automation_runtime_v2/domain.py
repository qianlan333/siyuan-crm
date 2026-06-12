from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


EVENT_CHANNEL_ENTERED = "channel_entered"
EVENT_QUESTIONNAIRE_SUBMITTED = "questionnaire_submitted"
EVENT_PAYMENT_SUCCEEDED = "payment_succeeded"
EVENT_WEBHOOK_RECEIVED = "webhook_received"

EVENT_TYPES = {
    EVENT_CHANNEL_ENTERED,
    EVENT_QUESTIONNAIRE_SUBMITTED,
    EVENT_PAYMENT_SUCCEEDED,
    EVENT_WEBHOOK_RECEIVED,
}

TRIGGER_ON_EVENT = "on_event"
TRIGGER_ON_ENTER_STAGE = "on_enter_stage"
TRIGGER_SCHEDULED = "scheduled"
TRIGGER_WEBHOOK_PUSH = "webhook_push"
TRIGGER_TYPES = {TRIGGER_ON_EVENT, TRIGGER_ON_ENTER_STAGE, TRIGGER_SCHEDULED, TRIGGER_WEBHOOK_PUSH}

SCHEDULE_DAILY_TIME = "daily_time"
SCHEDULE_STAGE_DAY_OFFSET = "stage_day_offset"

CONTENT_FIXED_MESSAGE = "fixed_message"
CONTENT_LAYERED_MESSAGE = "layered_message"
CONTENT_AGENT_GENERATED = "agent_generated"
CONTENT_TYPES = {CONTENT_FIXED_MESSAGE, CONTENT_LAYERED_MESSAGE, CONTENT_AGENT_GENERATED}

STAGE_PENDING_QUESTIONNAIRE = "pending_questionnaire"
STAGE_OPERATING = "operating"
STAGE_CONVERTED = "converted"
STAGE_EXITED = "exited"
STAGES = {STAGE_PENDING_QUESTIONNAIRE, STAGE_OPERATING, STAGE_CONVERTED, STAGE_EXITED}

LEGACY_TRIGGER_MAP = {
    "audience_entered": TRIGGER_ON_ENTER_STAGE,
    "scheduled_daily": TRIGGER_SCHEDULED,
}
LEGACY_CONTENT_MAP = {
    "unified": CONTENT_FIXED_MESSAGE,
    "profile_layered": CONTENT_LAYERED_MESSAGE,
    "behavior_layered": CONTENT_LAYERED_MESSAGE,
    "agent": CONTENT_AGENT_GENERATED,
}


def text(value: Any) -> str:
    return str(value or "").strip()


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return int(default)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class AutomationEventInput:
    event_type: str
    source_type: str
    source_id: str
    external_userid: str = ""
    phone: str = ""
    program_id: int | None = None
    channel_id: int | None = None
    binding_id: int | None = None
    person_id: int | None = None
    occurred_at: datetime | str | None = None
    raw_occurred_at: datetime | str | None = None
    payload_json: dict[str, Any] = field(default_factory=dict)
    idempotency_key: str = ""


@dataclass(frozen=True)
class StageTransitionResult:
    target_stage: str
    changed: bool
    entry_reason: str
    diagnostics: dict[str, Any] = field(default_factory=dict)
