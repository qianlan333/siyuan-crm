from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator


def database_url() -> str:
    return str(os.getenv("DATABASE_URL", "") or "").strip()


def has_database_url() -> bool:
    value = database_url()
    return value.startswith(("postgres://", "postgresql://", "postgresql+psycopg://"))


@contextmanager
def connect() -> Iterator[Any]:
    import psycopg
    from psycopg.rows import dict_row

    url = database_url()
    if not url:
        raise RuntimeError("DATABASE_URL is required")
    if url.startswith("postgresql+psycopg://"):
        url = "postgresql://" + url[len("postgresql+psycopg://") :]
    conn = psycopg.connect(url, row_factory=dict_row)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
