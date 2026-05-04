from __future__ import annotations

from typing import Any

from . import repo


def log_external_contact_event(
    *,
    corp_id: str,
    event_type: str,
    change_type: str,
    external_userid: str,
    user_id: str,
    event_time: int,
    event_key: str,
    payload_xml: str,
    payload_json: dict[str, Any],
) -> dict[str, Any]:
    existing = repo.get_external_contact_event_log_by_key(event_key)
    if existing:
        repo.touch_external_contact_event_log(int(existing["id"]))
        return {
            "id": int(existing["id"]),
            "process_status": existing.get("process_status", ""),
            "retry_count": int(existing.get("retry_count") or 0),
            "is_duplicate": True,
        }
    row = repo.insert_external_contact_event_log(
        corp_id=corp_id,
        event_type=event_type,
        change_type=change_type,
        external_userid=external_userid,
        user_id=user_id,
        event_time=event_time,
        event_key=event_key,
        payload_xml=payload_xml,
        payload_json=payload_json,
    )
    return {
        "id": int(row["id"]),
        "process_status": row.get("process_status", "pending"),
        "retry_count": int(row.get("retry_count") or 0),
        "is_duplicate": False,
    }


def mark_external_contact_event_processing(event_log_id: int) -> dict[str, Any] | None:
    row = repo.mark_external_contact_event_processing(event_log_id)
    return dict(row) if row else None


def get_external_contact_event_log(event_log_id: int) -> dict[str, Any] | None:
    row = repo.get_external_contact_event_log(event_log_id)
    return dict(row) if row else None


def finish_external_contact_event_log(
    event_log_id: int,
    *,
    status: str,
    error_message: str = "",
    increment_retry: bool = False,
) -> None:
    repo.finish_external_contact_event_log(
        event_log_id,
        status=status,
        error_message=error_message,
        increment_retry=increment_retry,
    )


def get_recent_external_contact_event_logs(limit: int = 20) -> list[dict[str, Any]]:
    return [dict(row) for row in repo.get_recent_external_contact_event_logs(limit=limit)]


def count_pending_events() -> dict[str, Any]:
    return repo.count_pending_events()


def count_failed_events_since(since_timestamp: str) -> int:
    return repo.count_failed_events_since(since_timestamp)


def list_stale_pending_events(*, age_seconds: int = 120, limit: int = 50) -> list[dict[str, Any]]:
    return repo.list_stale_pending_events(age_seconds=age_seconds, limit=limit)


def mark_event_dead_letter(event_log_id: int, *, error_message: str = "") -> None:
    repo.mark_event_dead_letter(event_log_id, error_message=error_message)
