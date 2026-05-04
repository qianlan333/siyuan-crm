from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class Customer:
    external_userid: str
    name: str = ""
    owner_userid: str = ""
    remark: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    status: str = ""
    is_bound: bool = False
    last_message_at: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TimelineEvent:
    event_id: str
    external_userid: str
    event_type: str
    occurred_at: str = ""
    summary: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class MessageBatch:
    batch_id: str
    status: str = ""
    created_at: str = ""
    ack_status: str = ""
    items: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
