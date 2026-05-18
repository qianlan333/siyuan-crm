"""Cloud 端审计日志 + trace_id 生成。

每次 Cloud Agent 调用 MCP tool 都写一条 ``cloud_agent_audit_log``，commit 类
操作额外保存 ``full_payload_json``（prompt + arguments + decision）。
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator

from ...db import get_db


logger = logging.getLogger(__name__)


def new_trace_id(prefix: str = "tr") -> str:
    """跨三端的统一 trace id。Cloud 发起一次操作就生成一个，全程透传。"""
    return f"{prefix}-{uuid.uuid4().hex}"


def new_session_id() -> str:
    return f"sess-{uuid.uuid4().hex}"


def _hash_args(arguments: dict[str, Any]) -> str:
    try:
        normalized = json.dumps(arguments, sort_keys=True, ensure_ascii=False)
    except TypeError:
        normalized = str(arguments)
    return hashlib.sha256(normalized.encode("utf-8", errors="ignore")).hexdigest()[:16]


def _summarize_result(result: Any, limit: int = 240) -> str:
    if result is None:
        return ""
    if isinstance(result, str):
        return result[:limit]
    try:
        s = json.dumps(result, ensure_ascii=False)
    except (TypeError, ValueError):
        s = str(result)
    if len(s) > limit:
        return s[:limit] + "...(truncated)"
    return s


def write_audit(
    *,
    session_id: str,
    trace_id: str,
    operator: str,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
    result: Any = None,
    latency_ms: int = 0,
    status: str = "success",
    error_message: str = "",
    requires_token: bool = False,
    token_verified: bool = False,
    full_payload: dict[str, Any] | None = None,
) -> int:
    """写一条 audit；返回新行 id。"""
    args = arguments or {}
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        INSERT INTO cloud_agent_audit_log
            (session_id, trace_id, operator, tool_name, arguments_hash,
             arguments_json, result_summary, latency_ms, status, error_message,
             requires_token, token_verified, full_payload_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(session_id or ""),
            str(trace_id or ""),
            str(operator or ""),
            str(tool_name or ""),
            _hash_args(args),
            json.dumps(args, ensure_ascii=False)[:8000],
            _summarize_result(result),
            int(latency_ms),
            str(status or "success"),
            str(error_message or "")[:500],
            bool(requires_token),
            bool(token_verified),
            (
                json.dumps(full_payload, ensure_ascii=False)[:32000]
                if isinstance(full_payload, dict)
                else "{}"
            ),
        ),
    )
    db.commit()
    return int(cur.lastrowid or 0)


@contextmanager
def audited_tool_call(
    *,
    session_id: str,
    trace_id: str,
    operator: str,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
    requires_token: bool = False,
    token_verified: bool = False,
    full_payload: dict[str, Any] | None = None,
) -> Iterator[dict[str, Any]]:
    """上下文管理器：自动测时、自动写 audit。

    用法：

        with audited_tool_call(...) as ctx:
            ctx["result"] = do_something()
    """
    state: dict[str, Any] = {"result": None, "error": None}
    started = time.monotonic()
    try:
        yield state
    except Exception as exc:
        state["error"] = exc
        write_audit(
            session_id=session_id,
            trace_id=trace_id,
            operator=operator,
            tool_name=tool_name,
            arguments=arguments,
            result=None,
            latency_ms=int((time.monotonic() - started) * 1000),
            status="error",
            error_message=str(exc)[:500],
            requires_token=requires_token,
            token_verified=token_verified,
            full_payload=full_payload,
        )
        raise
    else:
        write_audit(
            session_id=session_id,
            trace_id=trace_id,
            operator=operator,
            tool_name=tool_name,
            arguments=arguments,
            result=state.get("result"),
            latency_ms=int((time.monotonic() - started) * 1000),
            status="success",
            requires_token=requires_token,
            token_verified=token_verified,
            full_payload=full_payload,
        )


def list_recent_audit(
    *,
    session_id: str = "",
    trace_id: str = "",
    limit: int = 50,
) -> list[dict[str, Any]]:
    db = get_db()
    cur = db.cursor()
    if session_id:
        cur.execute(
            """
            SELECT id, session_id, trace_id, tool_name, status, latency_ms,
                   error_message, result_summary, created_at
            FROM cloud_agent_audit_log
            WHERE session_id = ?
            ORDER BY id DESC LIMIT ?
            """,
            (str(session_id), int(limit)),
        )
    elif trace_id:
        cur.execute(
            """
            SELECT id, session_id, trace_id, tool_name, status, latency_ms,
                   error_message, result_summary, created_at
            FROM cloud_agent_audit_log
            WHERE trace_id = ?
            ORDER BY id DESC LIMIT ?
            """,
            (str(trace_id), int(limit)),
        )
    else:
        cur.execute(
            """
            SELECT id, session_id, trace_id, tool_name, status, latency_ms,
                   error_message, result_summary, created_at
            FROM cloud_agent_audit_log
            ORDER BY id DESC LIMIT ?
            """,
            (int(limit),),
        )
    return [dict(row) for row in (cur.fetchall() or [])]


def build_observability_payload() -> dict[str, Any]:
    """Build Cloud Orchestrator observability counters for the admin/API surfaces."""

    cutoff_7d = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    cutoff_1d = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()

    db = get_db()
    cur = db.cursor()
    funnel: dict[str, int] = {}
    cur.execute(
        """
        SELECT status, COUNT(*) AS c FROM cloud_broadcast_plans
        WHERE created_at >= ?
        GROUP BY status
        """,
        (cutoff_7d,),
    )
    for row in cur.fetchall() or []:
        funnel[str(row["status"] or "unknown")] = int(row["c"] or 0)

    audit_status: dict[str, int] = {}
    cur.execute(
        """
        SELECT status, COUNT(*) AS c FROM cloud_agent_audit_log
        WHERE created_at >= ?
        GROUP BY status
        """,
        (cutoff_1d,),
    )
    for row in cur.fetchall() or []:
        audit_status[str(row["status"] or "unknown")] = int(row["c"] or 0)

    cur.execute(
        """
        SELECT tool_name, COUNT(*) AS c, AVG(latency_ms) AS avg_ms,
               SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) AS err_count
        FROM cloud_agent_audit_log
        WHERE created_at >= ?
        GROUP BY tool_name
        ORDER BY c DESC LIMIT 20
        """,
        (cutoff_1d,),
    )
    tool_stats = [
        {
            "tool": str(row["tool_name"] or ""),
            "count": int(row["c"] or 0),
            "avg_latency_ms": int(row["avg_ms"] or 0),
            "error_count": int(row["err_count"] or 0),
        }
        for row in cur.fetchall() or []
    ]

    cur.execute(
        """
        SELECT id, status, latency_ms, tool_name, error_message, trace_id, created_at
        FROM cloud_agent_audit_log
        WHERE status = 'error'
        ORDER BY id DESC LIMIT 10
        """
    )
    recent_errors = [dict(row) for row in (cur.fetchall() or [])]

    return {
        "plan_funnel_7d": funnel,
        "audit_status_1d": audit_status,
        "tool_stats_1d": tool_stats,
        "recent_errors": recent_errors,
    }


__all__ = [
    "new_trace_id",
    "new_session_id",
    "write_audit",
    "audited_tool_call",
    "list_recent_audit",
    "build_observability_payload",
]
