from __future__ import annotations

from datetime import datetime
from typing import Any

from ..db import get_db_backend


def db_bool(value: bool) -> bool | int:
    return value if get_db_backend() == "postgres" else (1 if value else 0)


def stringify_db_timestamp(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


def normalize_optional_timestamp(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, str) and "-" in value and ":" in value:
        return value
    ts = int(value)
    if ts > 10_000_000_000:
        ts = ts // 1000
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
