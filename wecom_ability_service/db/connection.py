from __future__ import annotations

from datetime import datetime, timezone

from flask import current_app, g

import psycopg
from psycopg.rows import dict_row


def _strip_tz(value):
    """Strip timezone info from PG datetime values, normalising to UTC first.

    psycopg 3 returns ``datetime`` with tzinfo set to the PG server timezone
    (e.g. ``Asia/Shanghai``).  Old SQLite code expects naive datetimes in UTC.
    We convert to UTC **before** stripping so the naive result is always UTC,
    regardless of the server's ``timezone`` setting.
    """
    if isinstance(value, datetime) and value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _dict_row_strip_tz(cursor):
    """Row factory: ``dict_row`` + strip timezone from all datetime values."""
    base_factory = dict_row(cursor)

    def row_maker(values):
        row = base_factory(values)
        return {k: _strip_tz(v) for k, v in row.items()}

    return row_maker


def get_db_backend() -> str:
    """历史接口，2026-05 砍 SQLite 后总返回 ``"postgres"``。

    保留函数为了不动 50+ 处 caller。新代码不需要再调用。
    """
    return "postgres"


def _translate_sql(sql: str) -> str:
    return sql.replace("?", "%s")


class PostgresCursor:
    """SQLite-cursor-shaped adapter so code written with ``cur = db.cursor()``
    + ``cur.execute(? params)`` + ``cur.fetchone() / fetchall() / lastrowid``
    works against psycopg without rewriting.

    - ``?`` → ``%s`` 自动翻译
    - ``lastrowid`` 通过 ``SELECT lastval()`` 兜底（INSERT 之后自增列）
    - ``rowcount`` 直接转发
    """

    def __init__(self, conn):
        self._conn = conn
        self._cursor = conn.cursor(row_factory=_dict_row_strip_tz)
        self._last_was_insert = False
        self.lastrowid = None

    def execute(self, sql, params=None):
        sql_text = sql if isinstance(sql, str) else str(sql)
        translated = _translate_sql(sql_text)
        # ★ params 为空时**不要**传给 psycopg —— 否则它会做 placeholder
        # 解析，把 SQL 里的字面 %（如 LIKE '%abc%'）误认成 placeholder
        # 触发 "got '%3'" 之类错误。
        if params is None or (hasattr(params, "__len__") and len(params) == 0):
            self._cursor.execute(translated)
        elif isinstance(params, dict):
            self._cursor.execute(translated, params)
        else:
            self._cursor.execute(translated, tuple(params))
        upper_head = translated.lstrip().upper()[:6]
        self._last_was_insert = upper_head == "INSERT"
        self.lastrowid = None
        # 只有在真插入了行（rowcount > 0）时才尝试拿 lastval()。``INSERT ...
        # SELECT WHERE NOT EXISTS`` 这种 conditional INSERT 可能 insert 0 行，
        # 那 ``SELECT lastval()`` 会抛 ``object "..." is not yet defined``，
        # 把 cursor 状态打 abort，后续 SQL 全炸。用 SAVEPOINT 保护以防万一。
        if self._last_was_insert and self._cursor.rowcount and self._cursor.rowcount > 0:
            sp_cursor = self._conn.cursor()
            try:
                sp_cursor.execute("SAVEPOINT _pg_lastval_probe")
                try:
                    sp_cursor.execute("SELECT lastval()")
                    row = sp_cursor.fetchone()
                    if row:
                        self.lastrowid = int(row[0])
                    sp_cursor.execute("RELEASE SAVEPOINT _pg_lastval_probe")
                except Exception:
                    self.lastrowid = None
                    try:
                        sp_cursor.execute("ROLLBACK TO SAVEPOINT _pg_lastval_probe")
                        sp_cursor.execute("RELEASE SAVEPOINT _pg_lastval_probe")
                    except Exception:
                        pass
            except Exception:
                self.lastrowid = None
            finally:
                sp_cursor.close()
        return self

    def executemany(self, sql, seq):
        translated = _translate_sql(sql if isinstance(sql, str) else str(sql))
        self._cursor.executemany(translated, list(seq))
        return self

    def executescript(self, script: str) -> None:
        statements = [s.strip() for s in script.split(";") if s.strip()]
        for s in statements:
            self._cursor.execute(s)

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchmany(self, n=None):
        if n is None:
            return self._cursor.fetchmany()
        return self._cursor.fetchmany(int(n))

    def fetchall(self):
        return self._cursor.fetchall()

    @property
    def rowcount(self):
        return self._cursor.rowcount

    @property
    def description(self):
        return self._cursor.description

    def close(self):
        try:
            self._cursor.close()
        except Exception:
            pass


class PostgresConnection:
    def __init__(self, conn):
        self._conn = conn

    def cursor(self):
        return PostgresCursor(self._conn)

    def execute(self, sql: str, params: tuple | list | None = None):
        # 走 PostgresCursor wrapper 让 INSERT 后 ``cursor.lastrowid`` 能拿到自增 id
        # （raw psycopg cursor 没有 lastrowid 属性，老 sqlite-shaped 代码会 AttributeError）。
        wrapper = PostgresCursor(self._conn)
        wrapper.execute(sql, params)
        return wrapper

    def executemany(self, sql: str, seq_of_params: list[tuple] | list[list]):
        cursor = self._conn.cursor(row_factory=_dict_row_strip_tz)
        cursor.executemany(_translate_sql(sql), seq_of_params)
        return cursor

    def executescript(self, script: str) -> None:
        cursor = self._conn.cursor()
        statements = [statement.strip() for statement in script.split(";") if statement.strip()]
        for statement in statements:
            cursor.execute(statement)
        cursor.close()

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()


def _connect_postgres():
    database_url = str(current_app.config.get("DATABASE_URL", "") or "").strip()
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is required. SQLite has been removed (2026-05). "
            "Run a local Postgres (e.g. `docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=test postgres:16`) "
            "and set DATABASE_URL=postgresql://...."
        )
    conn = psycopg.connect(database_url, autocommit=False)
    return PostgresConnection(conn)


def get_db():
    if "db" not in g:
        g.db = _connect_postgres()
    return g.db


def close_db(_: object | None = None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()
