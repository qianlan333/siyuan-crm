from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class TimelineItemDTO:
    event_id: str = ""
    event_type: str = ""
    type: str = ""
    event_time: str = ""
    occurred_at: str = ""
    title: str = ""
    summary: str = ""
    source_table: str = ""
    source_id: str = ""
    operator_userid: str = ""
    external_userid: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["type"] = data["type"] or data["event_type"]
        effective_payload = data["payload"] or data["metadata"]
        data["payload"] = effective_payload
        data["metadata"] = effective_payload
        return data


@dataclass
class TimelineDTO:
    external_userid: str = ""
    items: list[TimelineItemDTO] = field(default_factory=list)
    count: int = 0
    limit: int = 50
    offset: int = 0
    filters: dict[str, str] = field(default_factory=dict)
    total: int = 0

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["items"] = [item.to_dict() for item in self.items]
        return payload
