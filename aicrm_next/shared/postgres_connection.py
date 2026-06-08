from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from flask import current_app, g, has_app_context

from aicrm_next.shared.runtime import raw_database_url


def _strip_tz(value: Any) -> Any:
    if isinstance(value, datetime) and value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _translate_sql(sql: str) -> str:
    return sql.replace("?", "%s")


class PostgresCursor:
    def __init__(self, conn: Any) -> None:
        import psycopg
        from psycopg.rows import dict_row

        base_factory = dict_row

        def row_factory(cursor: Any) -> Any:
            maker = base_factory(cursor)

            def row_maker(values: Any) -> dict[str, Any]:
                row = maker(values)
                return {key: _strip_tz(value) for key, value in row.items()}

            return row_maker

        self._conn = conn
        self._cursor = conn.cursor(row_factory=row_factory)
        self.lastrowid: int | None = None

    def execute(self, sql: str, params: tuple[Any, ...] | list[Any] | dict[str, Any] | None = None) -> "PostgresCursor":
        translated = _translate_sql(str(sql))
        if params is None or (hasattr(params, "__len__") and len(params) == 0):
            self._cursor.execute(translated)
        elif isinstance(params, dict):
            self._cursor.execute(translated, params)
        else:
            self._cursor.execute(translated, tuple(params))
        self.lastrowid = None
        if translated.lstrip().upper().startswith("INSERT") and self._cursor.rowcount and self._cursor.rowcount > 0:
            probe = self._conn.cursor()
            try:
                probe.execute("SAVEPOINT _next_lastval_probe")
                try:
                    probe.execute("SELECT lastval()")
                    row = probe.fetchone()
                    self.lastrowid = int(row[0]) if row else None
                    probe.execute("RELEASE SAVEPOINT _next_lastval_probe")
                except Exception:
                    self.lastrowid = None
                    probe.execute("ROLLBACK TO SAVEPOINT _next_lastval_probe")
                    probe.execute("RELEASE SAVEPOINT _next_lastval_probe")
            finally:
                probe.close()
        return self

    def executemany(self, sql: str, seq: list[tuple[Any, ...]] | list[list[Any]]) -> "PostgresCursor":
        self._cursor.executemany(_translate_sql(str(sql)), list(seq))
        return self

    def fetchone(self) -> dict[str, Any] | None:
        return self._cursor.fetchone()

    def fetchall(self) -> list[dict[str, Any]]:
        return self._cursor.fetchall()

    @property
    def rowcount(self) -> int:
        return int(self._cursor.rowcount)

    @property
    def description(self) -> Any:
        return self._cursor.description

    def close(self) -> None:
        self._cursor.close()


class PostgresConnection:
    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def cursor(self) -> PostgresCursor:
        return PostgresCursor(self._conn)

    def execute(self, sql: str, params: tuple[Any, ...] | list[Any] | dict[str, Any] | None = None) -> PostgresCursor:
        return self.cursor().execute(sql, params)

    def executemany(self, sql: str, seq: list[tuple[Any, ...]] | list[list[Any]]) -> Any:
        cursor = self._conn.cursor()
        cursor.executemany(_translate_sql(str(sql)), list(seq))
        return cursor

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()


def _database_url() -> str:
    if has_app_context():
        configured = str(current_app.config.get("DATABASE_URL", "") or "").strip()
        if configured:
            return configured
    return raw_database_url()


def _connect() -> PostgresConnection:
    import psycopg

    database_url = _database_url()
    if not database_url:
        raise RuntimeError("DATABASE_URL is required for Next automation admission runtime")
    return PostgresConnection(psycopg.connect(database_url, autocommit=False))


def get_db() -> PostgresConnection:
    if has_app_context():
        if "next_db" not in g:
            g.next_db = _connect()
        return g.next_db
    return _connect()
