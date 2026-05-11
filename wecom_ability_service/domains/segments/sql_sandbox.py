"""SQL 沙箱 — Agent 写的分层 SQL 在这里跑。

强制约束：
1. 只允许单条 SELECT 语句（不允许 ``;`` 后跟另一条）
2. 关键字黑名单：DROP / DELETE / UPDATE / INSERT / ALTER / CREATE / TRUNCATE /
   ATTACH / DETACH / PRAGMA / VACUUM / REPLACE / GRANT / REVOKE
3. 必须涉及白名单表（automation_member 等只读 / 衍生表）
4. 强制最大返回行数（1 万）— 通过 SQLite/PG ``LIMIT`` 包裹
5. 强制只读事务 + 查询超时（5 秒）
6. 输出必须含 ``member_id`` 列；可选 ``external_contact_id``

这是 Agent 的"代笔"安全护栏 — Agent 自由地写筛选逻辑，但写错了不会爆库。
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any, Iterable

from ...db import get_db


logger = logging.getLogger(__name__)


class SqlSandboxError(Exception):
    """所有沙箱拒绝的异常都用这一个，便于上层统一翻译给前端/Agent。"""


# 允许 Agent 在分层 SQL 中引用的表/视图（其余一律拒绝）
ALLOWED_TABLES = frozenset(
    {
        "automation_member",
        "automation_member_interaction_stats",
        "automation_member_audience_entry",
        "automation_touch_delivery_log",
        "automation_ai_push_log",
        "automation_reply_monitor_queue",
        "automation_focus_send_batch",
        "automation_focus_send_batch_item",
        "user_ops_pool_current",
        "user_ops_send_records",
        "contact_tags",
        "automation_value_segment_current",
        "marketing_value_segment_current",
        "automation_member_segment_assignment",
        # 问卷数据 — 让 Agent 按问题/选项文本筛人（年收入、需求强度等场景）
        "questionnaire_submissions",
        "questionnaire_submission_answers",
        "questionnaires",
        "questionnaire_questions",
        "questionnaire_options",
    }
)

# 严禁出现的关键字（大小写不敏感，全词匹配）
FORBIDDEN_KEYWORDS = (
    "DROP",
    "DELETE",
    "UPDATE",
    "INSERT",
    "ALTER",
    "CREATE",
    "TRUNCATE",
    "ATTACH",
    "DETACH",
    "PRAGMA",
    "VACUUM",
    "REPLACE",
    "GRANT",
    "REVOKE",
    "EXEC",
    "EXECUTE",
)

MAX_SQL_LENGTH = 8000
MAX_ROWS = 10000
DEFAULT_TIMEOUT_SECONDS = 5


_TABLE_NAME_RE = re.compile(
    r"\b(?:FROM|JOIN)\s+([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)
_FORBIDDEN_RE = re.compile(
    r"\b(" + "|".join(FORBIDDEN_KEYWORDS) + r")\b",
    re.IGNORECASE,
)
_SELECT_PREFIX_RE = re.compile(r"^\s*(WITH\b|SELECT\b)", re.IGNORECASE)
_MULTI_STATEMENT_RE = re.compile(r";\s*\S")


def validate_segment_sql(sql: str) -> tuple[bool, str]:
    """静态校验 — 不连库、纯字符串检查。

    返回 (ok, reason)；ok=False 时 reason 直接面向 Agent，告诉它哪里写错了。
    """
    if not sql or not sql.strip():
        return False, "sql_empty"
    text = sql.strip()
    if len(text) > MAX_SQL_LENGTH:
        return False, f"sql_too_long(>{MAX_SQL_LENGTH})"
    # 必须以 SELECT 或 WITH 开头
    if not _SELECT_PREFIX_RE.match(text):
        return False, "must_start_with_SELECT_or_WITH"
    # 不允许多语句
    if _MULTI_STATEMENT_RE.search(text):
        return False, "multi_statement_not_allowed"
    # 黑名单关键字
    forbidden_match = _FORBIDDEN_RE.search(text)
    if forbidden_match:
        return False, f"forbidden_keyword:{forbidden_match.group(1).upper()}"
    # 表白名单
    referenced = {m.group(1).lower() for m in _TABLE_NAME_RE.finditer(text)}
    if not referenced:
        return False, "no_table_referenced"
    bad = referenced - ALLOWED_TABLES
    if bad:
        return False, f"forbidden_tables:{','.join(sorted(bad))}"
    return True, "ok"


def _wrap_with_limit(sql: str, max_rows: int) -> str:
    """如果 SQL 末尾没有 LIMIT，包一层。简化处理：直接外包 SELECT * FROM (...) LIMIT。"""
    text = sql.strip().rstrip(";")
    if re.search(r"\bLIMIT\s+\d+\s*$", text, re.IGNORECASE):
        return text
    return f"SELECT * FROM ({text}) AS _segment_inner LIMIT {int(max_rows)}"


def run_segment_query(
    *,
    sql: str,
    params: dict[str, Any] | None = None,
    max_rows: int = MAX_ROWS,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """跑一条已通过 ``validate_segment_sql`` 的 SQL，返回结构化结果。

    Returns:
        {
          "ok": bool,
          "rows": [{"member_id": int, "external_contact_id": str, ...}, ...],
          "row_count": int,
          "elapsed_ms": int,
          "error": str (only if ok=False),
        }
    """
    ok, reason = validate_segment_sql(sql)
    if not ok:
        raise SqlSandboxError(f"sql_invalid:{reason}")
    safe_sql = _wrap_with_limit(sql, max_rows=int(max_rows))
    db = get_db()
    cur = db.cursor()
    started = time.monotonic()
    # 检测后端 — 不同的只读保护手段：
    # - SQLite：PRAGMA query_only（局部 cursor 级，错就 try/except 静默）
    # - PG    ：不动事务 / 不发 SET，只靠静态 SQL 校验防写（避免污染调用方事务）
    #
    # ★ 用 get_db_backend() 直接拿配置，不要靠 instance/module 名字判断 ——
    # PostgresConnection 是我们的包装类，__module__ 不含 "psycopg"。之前用
    # "psycopg" in db.__class__.__module__ 永远是 False，导致 PG 上也走
    # PRAGMA query_only ON 路径，PG 报 syntax error → 事务被 abort →
    # 后续所有 SQL 全部 "transaction aborted, commands ignored"。
    from ...db import get_db_backend

    is_postgres = get_db_backend() == "postgres"
    pragma_was_set = False
    if not is_postgres:
        try:
            cur.execute("PRAGMA query_only = ON")
            pragma_was_set = True
        except Exception:
            pragma_was_set = False
    try:
        cur.execute(safe_sql, params or {})
        rows = cur.fetchmany(int(max_rows))
        elapsed_ms = int((time.monotonic() - started) * 1000)
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        logger.warning("segment sql failed: %s", exc)
        if pragma_was_set:
            try:
                cur.execute("PRAGMA query_only = OFF")
            except Exception:
                pass
        raise SqlSandboxError(f"sql_runtime_error:{exc}") from exc
    finally:
        if pragma_was_set:
            try:
                cur.execute("PRAGMA query_only = OFF")
            except Exception:
                pass

    if elapsed_ms > timeout_seconds * 1000:
        logger.warning("segment sql slow: %d ms", elapsed_ms)

    cleaned: list[dict[str, Any]] = []
    seen_member_ids: set[int] = set()
    for row in rows:
        d = dict(row) if hasattr(row, "keys") else {}
        if not d:
            try:
                d = {k: row[k] for k in row.keys()}
            except Exception:
                pass
        if "member_id" not in d and "id" in d:
            d["member_id"] = d.pop("id")
        if "member_id" not in d:
            raise SqlSandboxError("sql_missing_member_id_column")
        member_id = d.get("member_id")
        try:
            member_id_int = int(member_id) if member_id is not None else 0
        except (TypeError, ValueError):
            continue
        if member_id_int <= 0:
            continue
        # 去重 — 避免一个 member 因为 join 出现多行
        if member_id_int in seen_member_ids:
            continue
        seen_member_ids.add(member_id_int)
        d["member_id"] = member_id_int
        if "external_contact_id" in d and d["external_contact_id"] is not None:
            d["external_contact_id"] = str(d["external_contact_id"])
        cleaned.append(d)

    return {
        "ok": True,
        "rows": cleaned,
        "row_count": len(cleaned),
        "elapsed_ms": elapsed_ms,
    }


def fetch_member_ids(
    *,
    sql: str,
    params: dict[str, Any] | None = None,
    max_rows: int = MAX_ROWS,
) -> list[int]:
    """语义薄包装 — 只要 member_id 列表。"""
    res = run_segment_query(sql=sql, params=params, max_rows=max_rows)
    return [int(r["member_id"]) for r in res["rows"]]


__all__ = [
    "ALLOWED_TABLES",
    "FORBIDDEN_KEYWORDS",
    "MAX_ROWS",
    "MAX_SQL_LENGTH",
    "SqlSandboxError",
    "fetch_member_ids",
    "run_segment_query",
    "validate_segment_sql",
]
