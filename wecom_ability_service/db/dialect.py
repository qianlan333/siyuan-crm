"""SQL dialect helpers.

历史上项目同时支持 PostgreSQL（生产）+ SQLite（部分老测试），导致大量 backend
分支代码 + 11 个跨库兼容 bug。2026-05 决策砍掉 SQLite，统一 PG。

保留的 helpers 只负责生成 PG SQL fragment：
- ``cast_text(expr)`` 加 ``::timestamp::text``
- ``coalesce_text(...)`` 按 PG 写法 cast
- ``nonempty(col)`` 改用 ``IS NOT NULL``（PG TIMESTAMPTZ 不能跟 '' 比）
- ``upsert_clause(...)`` 生成 PG 的 ON CONFLICT 子句
"""
from __future__ import annotations


def cast_text(expr: str) -> str:
    """SQL fragment for casting an expression to text on PG.

    Uses ``::timestamp::text`` instead of ``::text`` so that TIMESTAMPTZ
    values are rendered **without** the timezone offset (``+08``) — matching
    the naive-datetime convention the rest of the codebase expects.
    """
    return f"({expr})::timestamp::text"


def coalesce_text(*exprs: str, default: str = "''") -> str:
    """COALESCE wrapper with explicit ``::text`` cast for each expression."""
    casted = ", ".join(cast_text(e) for e in exprs)
    if default is None:
        return f"COALESCE({casted})"
    return f"COALESCE({casted}, {default})"


def nonempty(col: str) -> str:
    """``col`` is non-NULL (PG TIMESTAMPTZ 不能跟 '' 比，统一用 IS NOT NULL)."""
    return f"{col} IS NOT NULL"


def upsert_clause(*, conflict_cols: list[str], update_cols: list[str]) -> str:
    """``ON CONFLICT ... DO UPDATE`` tail."""
    conflict = ", ".join(conflict_cols)
    assignments = ", ".join(f"{col} = EXCLUDED.{col}" for col in update_cols)
    return f"ON CONFLICT ({conflict}) DO UPDATE SET {assignments}"
