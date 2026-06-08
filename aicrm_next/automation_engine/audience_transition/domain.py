from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AudienceTransitionEvent:
    member_id: int
    external_userid: str
    program_id: int
    source_channel_id: int
    audience_entry_id: int
    audience_code: str
    entry_reason: str
    entry_source: str
    operator_id: str
    occurred_at: str = ""

    def is_complete(self) -> bool:
        return self.member_id > 0 and self.audience_entry_id > 0 and bool(self.audience_code)


def base_realtime_result(event: AudienceTransitionEvent | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "audience_entry_id": int(event.audience_entry_id) if event else 0,
        "audience_code": event.audience_code if event else "",
        "entry_reason": event.entry_reason if event else "",
        "realtime_operation_tasks_ran": 0,
        "realtime_operation_tasks_enqueued_count": 0,
        "realtime_operation_tasks_results": [],
        "realtime_operation_tasks_error": "",
        "realtime_operation_tasks_reason": "",
    }
    return payload
