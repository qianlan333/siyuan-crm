from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal
from uuid import uuid4

from .command_bus.models import utcnow_iso

ExternalCallAttemptStatus = Literal["success", "failed", "blocked"]
_SENSITIVE_KEYS = {"token", "secret", "password", "authorization", "access_token", "refresh_token"}


def scrub_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key, value in payload.items():
        if key.lower() in _SENSITIVE_KEYS:
            summary[key] = "[redacted]"
        elif isinstance(value, (str, int, float, bool)) or value is None:
            summary[key] = value
        else:
            summary[key] = type(value).__name__
    return summary


@dataclass(frozen=True)
class ExternalCallAttempt:
    external_call_attempt_id: str = field(default_factory=lambda: uuid4().hex)
    adapter_name: str = ""
    adapter_mode: str = "none"
    operation: str = ""
    request_id: str = ""
    trace_id: str = ""
    side_effect_plan_id: str = ""
    status: ExternalCallAttemptStatus = "success"
    request_summary: dict[str, Any] = field(default_factory=dict)
    response_summary: dict[str, Any] = field(default_factory=dict)
    error_code: str = ""
    error_message: str = ""
    created_at: str = field(default_factory=utcnow_iso)
    completed_at: str = field(default_factory=utcnow_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class InMemoryExternalCallAttemptRepository:
    def __init__(self) -> None:
        self._attempts: list[ExternalCallAttempt] = []

    def record_attempt(self, **kwargs: Any) -> ExternalCallAttempt:
        if "request_summary" in kwargs:
            kwargs["request_summary"] = scrub_summary(dict(kwargs["request_summary"] or {}))
        if "response_summary" in kwargs:
            kwargs["response_summary"] = scrub_summary(dict(kwargs["response_summary"] or {}))
        attempt = ExternalCallAttempt(**kwargs)
        self._attempts.append(attempt)
        return attempt

    def list_attempts(self) -> list[ExternalCallAttempt]:
        return list(self._attempts)
