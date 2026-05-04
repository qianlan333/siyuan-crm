from __future__ import annotations

from typing import Any

from ..marketing_automation import service as marketing_automation_service
from ..tasks import service as tasks_service


def list_signup_conversion_batches(*, limit: int = 20, cursor: str = "", scenario_key: str = "") -> dict[str, Any]:
    """Internal automation owner for signup-conversion batch list reads."""

    kwargs: dict[str, Any] = {
        "limit": int(limit),
        "cursor": str(cursor or ""),
    }
    if str(scenario_key or "").strip():
        kwargs["scenario_key"] = str(scenario_key or "").strip()
    return marketing_automation_service.list_signup_conversion_batches(**kwargs)


def get_signup_conversion_batch(batch_id: int, *, scenario_key: str = "") -> dict[str, Any] | None:
    """Internal automation owner for signup-conversion batch detail reads."""

    kwargs: dict[str, Any] = {}
    if str(scenario_key or "").strip():
        kwargs["scenario_key"] = str(scenario_key or "").strip()
    return marketing_automation_service.get_signup_conversion_batch(int(batch_id), **kwargs)


def record_conversion_feedback(
    *,
    feedback_type: str,
    external_userid: str = "",
    chat_id: str = "",
    actor: str = "",
    feedback_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Internal automation owner for conversion feedback writes."""

    return tasks_service.record_conversion_feedback(
        feedback_type=str(feedback_type or "").strip(),
        external_userid=str(external_userid or "").strip(),
        chat_id=str(chat_id or "").strip(),
        actor=str(actor or "").strip(),
        feedback_payload=dict(feedback_payload or {}) if feedback_payload else None,
    )


def ack_conversion_batch(
    batch_id: int,
    *,
    acked_by: str = "",
    ack_note: str = "",
    automation_key: str = "",
) -> dict[str, Any] | None:
    """Internal automation owner for signup-conversion batch ack writes."""

    kwargs: dict[str, Any] = {
        "acked_by": str(acked_by or "").strip(),
        "ack_note": str(ack_note or "").strip(),
    }
    if str(automation_key or "").strip():
        kwargs["automation_key"] = str(automation_key or "").strip()
    return marketing_automation_service.ack_conversion_batch(int(batch_id), **kwargs)


__all__ = [
    "ack_conversion_batch",
    "get_signup_conversion_batch",
    "list_signup_conversion_batches",
    "record_conversion_feedback",
]
