from __future__ import annotations

from typing import Any


def parse_timeline_filters(args: Any) -> dict[str, Any]:
    raw_limit = str(args.get("limit", "50") or "50").strip() or "50"
    raw_offset = str(args.get("offset", "0") or "0").strip() or "0"
    raw_event_type = str(args.get("event_type", "") or "").strip()

    try:
        limit = int(raw_limit)
    except ValueError as exc:
        raise ValueError("limit must be an integer") from exc
    try:
        offset = int(raw_offset)
    except ValueError as exc:
        raise ValueError("offset must be an integer") from exc

    if limit < 1:
        raise ValueError("limit must be >= 1")
    if offset < 0:
        raise ValueError("offset must be >= 0")

    return {
        "event_type": raw_event_type,
        "limit": raw_limit,
        "offset": raw_offset,
        "normalized_limit": min(limit, 100),
        "normalized_offset": offset,
    }
