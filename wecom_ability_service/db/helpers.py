from __future__ import annotations

from typing import Any, Iterable


def fetchone_dict(db, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    row = db.execute(sql, params).fetchone()
    return dict(row) if row else None


def fetchall_dicts(db, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in db.execute(sql, params).fetchall()]


def fetch_inserted_id(cursor) -> int:
    row = cursor.fetchone() or {}
    return int((row or {}).get("id") or 0)


def placeholders(values: Iterable[object]) -> str:
    return ",".join("?" for _ in values)


def pg_table_columns(db, table_name: str) -> set[str]:
    """Return column names for a table in the current Postgres schema."""
    rows = db.execute(
        """
        SELECT column_name AS name
        FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = ?
        """,
        (table_name,),
    ).fetchall()
    return {row["name"] for row in rows}


def _postgres_table_columns(db, table_name: str) -> set[str]:
    """Backward-compatible alias for older migration helpers."""
    return pg_table_columns(db, table_name)
