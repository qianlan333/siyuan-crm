from __future__ import annotations

from .connection import get_db_backend


def is_postgres() -> bool:
    return get_db_backend() == "postgres"


def is_sqlite() -> bool:
    return get_db_backend() == "sqlite"


def cast_text(expr: str) -> str:
    """SQL fragment for casting a column / expression to text.

    Postgres needs an explicit ``::text`` for timestamp / numeric columns when
    they participate in COALESCE with strings; SQLite is dynamically typed and
    needs no cast.
    """
    if is_postgres():
        return f"{expr}::text"
    return expr


def coalesce_text(*exprs: str, default: str = "''") -> str:
    """COALESCE wrapper that auto-casts each expression to text on Postgres."""
    casted = ", ".join(cast_text(e) for e in exprs)
    if default is None:
        return f"COALESCE({casted})"
    return f"COALESCE({casted}, {default})"


def nonempty(col: str) -> str:
    """SQL predicate for ``col`` being non-NULL and non-empty.

    Both backends accept ``col <> ''`` after a NULL-guard, so the fragment is
    portable; centralising it avoids inconsistent variants across repos.
    """
    return f"{col} IS NOT NULL AND {col} <> ''"


def upsert_clause(*, conflict_cols: list[str], update_cols: list[str]) -> str:
    """Render an ``ON CONFLICT ... DO UPDATE`` tail.

    Both Postgres and recent SQLite share this exact syntax, so this helper
    is mostly here so callers stop typing it by hand and so we have one place
    to swap dialects if SQLite < 3.24 needs to be supported again.
    """
    conflict = ", ".join(conflict_cols)
    assignments = ", ".join(f"{col} = EXCLUDED.{col}" for col in update_cols)
    return f"ON CONFLICT ({conflict}) DO UPDATE SET {assignments}"
