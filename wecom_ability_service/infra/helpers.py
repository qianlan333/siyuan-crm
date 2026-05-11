from __future__ import annotations

from datetime import datetime
from typing import Any


def db_bool(value: bool) -> bool:
    """传给 PG BOOLEAN 字段的值。

    历史上需要 ``bool`` (PG) / ``int`` (SQLite) 双语义，2026-05 砍 SQLite 后统一
    返回 Python bool。callers 不需要改 — 行为兼容（True/False 在 SQLite TEXT 也
    能写入，虽然现在用不上了）。
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
