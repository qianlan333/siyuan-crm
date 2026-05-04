from __future__ import annotations


def _sqlite_table_columns(db, table_name: str) -> set[str]:
    return {row["name"] for row in db.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _sqlite_table_sql(db, table_name: str) -> str:
    row = db.execute(
        """
        SELECT sql
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        (table_name,),
    ).fetchone()
    return str((row or {}).get("sql") or "")


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
