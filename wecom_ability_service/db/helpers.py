from __future__ import annotations


def _sqlite_table_columns(db, table_name: str) -> set[str]:
    """PG-only：用 information_schema 列出表的列名（前缀仍叫 _sqlite_ 是因为
    50+ 处 caller 没改名，2026-05 砍 SQLite 后语义统一走 PG）。"""
    rows = db.execute(
        """
        SELECT column_name AS name
        FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = ?
        """,
        (table_name,),
    ).fetchall()
    return {row["name"] for row in rows}


def _sqlite_table_sql(db, table_name: str) -> str:
    """PG-only：用 ``pg_get_tabledef`` 不在标准里，直接从 information_schema
    拼一个简化的列定义字符串够测试断言用了。"""
    rows = db.execute(
        """
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = ?
        ORDER BY ordinal_position
        """,
        (table_name,),
    ).fetchall()
    if not rows:
        return ""
    parts = []
    for row in rows:
        name = row["column_name"]
        dtype = row["data_type"]
        not_null = "NOT NULL" if row["is_nullable"] == "NO" else ""
        default = f"DEFAULT {row['column_default']}" if row["column_default"] else ""
        parts.append(" ".join(filter(None, [name, dtype, not_null, default])))
    return f"CREATE TABLE {table_name} ({', '.join(parts)})"


def _sqlite_normalized_conversion_pool_sql(column_name: str) -> str:
    return f"""
        CASE
            WHEN COALESCE({column_name}, '') IN ('pending_questionnaire', 'operating', 'converted', 'removed', 'no_reply', 'human_reply') THEN COALESCE({column_name}, '')
            WHEN COALESCE({column_name}, '') IN ('new_user') THEN 'pending_questionnaire'
            WHEN COALESCE({column_name}, '') IN ('inactive_normal', 'inactive_focus', 'active_normal', 'active_focus', 'silent') THEN 'operating'
            WHEN COALESCE({column_name}, '') IN ('won') THEN 'converted'
            ELSE COALESCE({column_name}, '')
        END
    """


def _sqlite_table_exists(db, table_name: str) -> bool:
    return bool(_sqlite_table_sql(db, table_name))


def _postgres_table_columns(db, table_name: str) -> set[str]:
    rows = db.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = ?
        """,
        (table_name,),
    ).fetchall()
    return {row["column_name"] for row in rows}
