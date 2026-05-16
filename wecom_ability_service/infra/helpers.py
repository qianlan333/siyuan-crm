from __future__ import annotations

from datetime import datetime
from typing import Any


def db_bool(value: bool) -> bool:
    """传给 PG BOOLEAN 字段的值。

    历史上调用方需要自己处理跨库布尔值；2026-05 统一 PG 后这里固定返回 Python bool。
    """
    return bool(value)


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
