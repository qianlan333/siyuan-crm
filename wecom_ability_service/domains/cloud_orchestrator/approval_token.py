"""Approval Token — UI 签发的"一次性 commit 许可"。

写操作 `commit_broadcast_plan` 必须带 token，token 绑定 plan_id + operator + 5min TTL，
在 ``cloud_approval_tokens`` 表里走"签发 → 校验 → 消费"状态机。

设计上对外只暴露 token_hash，明文 token 不入库（只在签发时返回给前端）。
"""
from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from ...db import get_db, get_db_backend


logger = logging.getLogger(__name__)


_DEFAULT_TTL_SECONDS = 300  # 5 分钟


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8", errors="ignore")).hexdigest()


def issue_token(
    *,
    plan_id: str,
    operator: str,
    scope: str = "commit_broadcast_plan",
    ttl_seconds: int = _DEFAULT_TTL_SECONDS,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """签发一次性 token；返回明文 token（只此一次）。"""
    if not plan_id:
        raise ValueError("plan_id is required")
    if not operator:
        raise ValueError("operator is required")
    plain = secrets.token_urlsafe(32)
    token_hash = _hash_token(plain)
    # 用 timezone-aware ISO 字符串写入。PG TIMESTAMPTZ 对 naive 字符串会按 server timezone
    # 解读（中国 server 默认 Asia/Shanghai），把 ``utcnow()+5min`` 倒推 8 小时存为"6 小时前"，
    # token 一签发就立刻过期。带 ``+00:00`` 后 PG 按 UTC 写入；SQLite 字符串比较也不受影响。
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=int(ttl_seconds))).isoformat()
    db = get_db()
    cur = db.cursor()
    import json as _json

    cur.execute(
        """
        INSERT INTO cloud_approval_tokens
            (token_hash, plan_id, operator, scope, expires_at, metadata_json)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            token_hash,
            str(plan_id),
            str(operator),
            str(scope),
            expires_at,
            _json.dumps(metadata or {}, ensure_ascii=False),
        ),
    )
    db.commit()
    return {
        "token": plain,
        "plan_id": plan_id,
        "operator": operator,
        "scope": scope,
        "expires_at": expires_at,
    }


def consume_token(
    *,
    token: str,
    plan_id: str,
    consumer: str = "",
    scope: str = "commit_broadcast_plan",
) -> dict[str, Any]:
    """校验并消费 token。

    Returns: {"ok": bool, "reason": str, "operator": str}
    """
    if not token:
        return {"ok": False, "reason": "missing_token", "operator": ""}
    token_hash = _hash_token(token)
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        SELECT id, plan_id, operator, scope, expires_at, consumed_at
        FROM cloud_approval_tokens WHERE token_hash = ? LIMIT 1
        """,
        (token_hash,),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "reason": "token_not_found", "operator": ""}
    if str(row["plan_id"] or "") != str(plan_id):
        return {"ok": False, "reason": "plan_mismatch", "operator": str(row["operator"] or "")}
    if str(row["scope"] or "") != str(scope):
        return {"ok": False, "reason": "scope_mismatch", "operator": str(row["operator"] or "")}
    if row["consumed_at"]:
        return {"ok": False, "reason": "already_consumed", "operator": str(row["operator"] or "")}
    raw_expires = row["expires_at"]
    if raw_expires:
        # PG 返回 datetime（可能 aware 也可能 naive），SQLite 返回字符串
        if isinstance(raw_expires, datetime):
            exp = raw_expires
        else:
            try:
                exp = datetime.fromisoformat(str(raw_expires))
            except ValueError:
                exp = None
        if exp is not None:
            # 统一 utc-aware 后比较，避免 PG TIMESTAMPTZ vs naive utcnow 抛 TypeError
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > exp:
                return {"ok": False, "reason": "expired", "operator": str(row["operator"] or "")}
    cur.execute(
        """
        UPDATE cloud_approval_tokens
        SET consumed_at = CURRENT_TIMESTAMP, consumed_by = ?
        WHERE id = ? AND consumed_at IS NULL
        """,
        (str(consumer or ""), int(row["id"])),
    )
    db.commit()
    if cur.rowcount and cur.rowcount > 0:
        return {"ok": True, "reason": "consumed", "operator": str(row["operator"] or "")}
    return {"ok": False, "reason": "race_already_consumed", "operator": str(row["operator"] or "")}


__all__ = ["issue_token", "consume_token"]
