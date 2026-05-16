"""跨 program / 跨渠道的频次预算（防反复骚扰中枢）。

设计目标：
- 唯一执行点：`check_member_budget()` 在 `_build_pool_send_plan` 的 eligible 过滤里调
- 滑窗算法：不存全量历史，只查 ``WHERE consumed_at > now() - window_seconds``
- 一个 member 受多 budget 约束，全部通过才放行；任何一条不过 → 跳过原因 ``budget_exceeded``
- 写入 ``automation_frequency_consumption``：发送成功后记录，trace_id 串联三端

预算定义在 ``automation_frequency_budget`` 表（运营可在 admin console 配置）：
- ``scope=global``：全局对所有 member 生效
- ``scope=channel``：按渠道（``scope_key='wecom_private'``）
- ``scope=program``：按 program_code
- ``scope=pool``：按 pool_key

设计上故意做成"读多写少 + 索引扫描"，避免在高并发群发时拖慢主流程。
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any, Iterable, Sequence

from ...db import get_db
from ...db.helpers import fetchall_dicts, fetchone_dict, placeholders


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BudgetVerdict:
    """单个 budget 的检查结果。"""

    budget_id: int
    budget_code: str
    allowed: bool
    used: int
    cap: int
    window_seconds: int
    skip_reason: str = ""


@dataclass(frozen=True)
class MemberBudgetCheck:
    """一个 member 在所有相关 budget 上的合并结果。"""

    allowed: bool
    skip_reason: str
    verdicts: list[BudgetVerdict]


# 没有内置默认预算 —— 全部通过 admin 手动加。
# 框架 (check_member_budget / list_active_budgets / record_consumption) 仍保留，
# 任何运营在 admin 加的 budget 都会按既有逻辑生效。
_DEFAULT_BUDGETS: tuple[dict[str, Any], ...] = ()


# 历史曾经默认开启、现在退役的预算 code。
# 启动时自动把这些行 disable（保留行 + 历史 consumption 引用完整性，不删除），
# 这样生产 DB 已经 INSERT 过的旧记录不需要运营手工 UPDATE 也能立刻失效。
_RETIRED_BUDGET_CODES: tuple[str, ...] = (
    "ai_initiated_per_member_weekly",
    "global_per_member_weekly",
    "global_per_member_daily",
)


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def ensure_default_budgets() -> None:
    """启动期把默认预算写进库（已存在则不覆盖运营修改的值）。

    同时把 ``_RETIRED_BUDGET_CODES`` 里的历史预算自动 disable —— 仅当 DB 里
    现存且 enabled 时才 UPDATE，避免覆盖运营手动重新开启的状态。

    自带 rollback 防护：调用前如果事务已 abort（PG），先 rollback 清干净。
    """
    db = get_db()
    try:
        if hasattr(db, "rollback"):
            db.rollback()
    except Exception:  # pragma: no cover - defensive
        pass
    cursor = db.cursor()
    for spec in _DEFAULT_BUDGETS:
        try:
            row = fetchone_dict(
                db,
                "SELECT id FROM automation_frequency_budget WHERE budget_code = ?",
                (spec["budget_code"],),
            )
            if row:
                continue
            cursor.execute(
                """
                INSERT INTO automation_frequency_budget
                    (budget_code, scope, scope_key, window_seconds, max_count,
                     description, enabled)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    spec["budget_code"],
                    spec["scope"],
                    spec["scope_key"],
                    spec["window_seconds"],
                    spec["max_count"],
                    spec["description"],
                    True,
                ),
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("ensure_budget failed code=%s err=%s", spec["budget_code"], exc)
            try:
                if hasattr(db, "rollback"):
                    db.rollback()
            except Exception:
                pass
            cursor = db.cursor()  # rollback 后重建 cursor
    for retired_code in _RETIRED_BUDGET_CODES:
        try:
            cursor.execute(
                "UPDATE automation_frequency_budget SET enabled = ? "
                "WHERE budget_code = ? AND enabled",
                (False, retired_code),
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("retire_budget failed code=%s err=%s", retired_code, exc)
            try:
                if hasattr(db, "rollback"):
                    db.rollback()
            except Exception:
                pass
            cursor = db.cursor()
    db.commit()


def list_active_budgets(
    *,
    channels: Iterable[str] = (),
    program_codes: Iterable[str] = (),
    pool_keys: Iterable[str] = (),
) -> list[dict[str, Any]]:
    """挑出对当前发送场景生效的 budget。

    返回 enabled=1 的 budget，按 scope 过滤：
    - global 永远生效
    - channel/program/pool 在调用方提供的 scope_key 集合里时生效
    """
    rows = fetchall_dicts(
        get_db(),
        """
        SELECT id, budget_code, scope, scope_key, window_seconds, max_count, description
        FROM automation_frequency_budget
        WHERE enabled
        ORDER BY id ASC
        """,
    )
    channel_set = {str(c) for c in channels if c}
    program_set = {str(p) for p in program_codes if p}
    pool_set = {str(k) for k in pool_keys if k}
    out: list[dict[str, Any]] = []
    for row in rows:
        scope = (row["scope"] or "").lower()
        scope_key = row["scope_key"] or ""
        if scope == "global":
            out.append(row)
        elif scope == "channel" and (not scope_key or scope_key in channel_set):
            out.append(row)
        elif scope == "program" and scope_key in program_set:
            out.append(row)
        elif scope == "pool" and scope_key in pool_set:
            out.append(row)
    return out


def _count_consumption(
    *,
    budget_id: int,
    member_id: int | None,
    external_contact_id: str,
    window_seconds: int,
    exclude_source_kind: str = "",
    exclude_source_ids: Sequence[str] = (),
) -> int:
    db = get_db()

    cutoff_iso = (_utc_now_naive() - timedelta(seconds=int(window_seconds))).isoformat()

    # 同 campaign 续推排除：不计入同来源的历史消耗
    exclude_clause = ""
    exclude_params: tuple = ()
    if exclude_source_kind and exclude_source_ids:
        exclude_clause = f" AND NOT (source_kind = ? AND source_id IN ({placeholders(exclude_source_ids)}))"
        exclude_params = (exclude_source_kind, *exclude_source_ids)

    if member_id and int(member_id) > 0:
        row = fetchone_dict(
            db,
            f"""
            SELECT COUNT(*) AS c FROM automation_frequency_consumption
            WHERE budget_id = ?
              AND member_id = ?
              AND consumed_at >= ?{exclude_clause}
            """,
            (int(budget_id), int(member_id), cutoff_iso, *exclude_params),
        )
        if row:
            return int(row["c"] or 0)
    if external_contact_id:
        row = fetchone_dict(
            db,
            f"""
            SELECT COUNT(*) AS c FROM automation_frequency_consumption
            WHERE budget_id = ?
              AND external_contact_id = ?
              AND consumed_at >= ?{exclude_clause}
            """,
            (int(budget_id), external_contact_id, cutoff_iso, *exclude_params),
        )
        if row:
            return int(row["c"] or 0)
    return 0


def check_member_budget(
    *,
    member_id: int | None,
    external_contact_id: str = "",
    channels: Iterable[str] = ("wecom_private",),
    program_codes: Iterable[str] = (),
    pool_keys: Iterable[str] = (),
    exclude_source_kind: str = "",
    exclude_source_ids: Sequence[str] = (),
) -> MemberBudgetCheck:
    """合并检查一个 member 是否被任何相关 budget 拒绝。

    返回结构里带每条 budget 的明细，便于 UI 展示"为什么被跳过"。

    ``exclude_source_kind`` / ``exclude_source_ids`` — 排除特定来源的消耗记录，
    用于同一 campaign 续推时不重复消耗 daily budget。
    """
    budgets = list_active_budgets(
        channels=channels,
        program_codes=program_codes,
        pool_keys=pool_keys,
    )
    verdicts: list[BudgetVerdict] = []
    blocked_reason = ""
    for b in budgets:
        used = _count_consumption(
            budget_id=int(b["id"]),
            member_id=member_id,
            external_contact_id=external_contact_id,
            window_seconds=int(b["window_seconds"]),
            exclude_source_kind=exclude_source_kind,
            exclude_source_ids=exclude_source_ids,
        )
        cap = int(b["max_count"])
        allowed = used < cap
        reason = "" if allowed else f"budget_exceeded:{b['budget_code']}"
        verdicts.append(
            BudgetVerdict(
                budget_id=int(b["id"]),
                budget_code=str(b["budget_code"]),
                allowed=allowed,
                used=used,
                cap=cap,
                window_seconds=int(b["window_seconds"]),
                skip_reason=reason,
            )
        )
        if not allowed and not blocked_reason:
            blocked_reason = reason
    return MemberBudgetCheck(
        allowed=not blocked_reason,
        skip_reason=blocked_reason,
        verdicts=verdicts,
    )


def record_consumption(
    *,
    member_id: int | None,
    external_contact_id: str,
    channels: Iterable[str] = ("wecom_private",),
    program_codes: Iterable[str] = (),
    pool_keys: Iterable[str] = (),
    source_kind: str = "",
    source_id: str = "",
    trace_id: str = "",
) -> int:
    """发送成功后记录消耗，所有相关 budget 各加一条。返回写入条数。"""
    budgets = list_active_budgets(
        channels=channels,
        program_codes=program_codes,
        pool_keys=pool_keys,
    )
    if not budgets:
        return 0
    db = get_db()
    cur = db.cursor()
    written = 0
    for b in budgets:
        cur.execute(
            """
            INSERT INTO automation_frequency_consumption
                (budget_id, member_id, external_contact_id, source_kind, source_id, trace_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                int(b["id"]),
                int(member_id) if member_id else None,
                str(external_contact_id or ""),
                str(source_kind or ""),
                str(source_id or ""),
                str(trace_id or ""),
            ),
        )
        written += 1
    db.commit()
    return written


def cleanup_expired_consumption(*, batch_size: int = 5000) -> int:
    """清理任何 budget 都不会再用到的旧消耗记录。

    一条记录对哪个 budget 还有效，取决于该 budget 的 window_seconds；只要超过
    所有 enabled budget 中最大的 window，就可以删。这里取一个保守的 90 天硬上限。
    """
    cutoff_iso = (_utc_now_naive() - timedelta(days=90)).isoformat()
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        DELETE FROM automation_frequency_consumption
        WHERE id IN (
            SELECT id FROM automation_frequency_consumption
            WHERE consumed_at < ?
            ORDER BY id ASC
            LIMIT ?
        )
        """,
        (cutoff_iso, int(batch_size)),
    )
    deleted = cur.rowcount or 0
    db.commit()
    return deleted


def annotate_eligible_items_with_budget(
    *,
    eligible_items: list[dict[str, Any]],
    pool_keys: Iterable[str] = (),
    program_codes: Iterable[str] = ("signup_conversion_v1",),
    channels: Iterable[str] = ("wecom_private",),
    skipped_by_reason: dict[str, int] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int], list[dict[str, Any]]]:
    """对 _build_pool_send_plan 的 eligible_items 做频次预算筛查。

    Returns:
        (allowed_items, updated_skipped_by_reason, budget_skip_details)
        budget_skip_details: 每个被跳过 member 的预算明细（用于 UI 解释）
    """
    if skipped_by_reason is None:
        skipped_by_reason = {}
    if not eligible_items:
        return eligible_items, skipped_by_reason, []
    started = time.monotonic()
    allowed: list[dict[str, Any]] = []
    skip_details: list[dict[str, Any]] = []
    for item in eligible_items:
        result = check_member_budget(
            member_id=int(item.get("automation_member_id") or 0) or None,
            external_contact_id=str(item.get("external_userid") or ""),
            channels=channels,
            program_codes=program_codes,
            pool_keys=pool_keys,
        )
        if result.allowed:
            allowed.append(item)
            continue
        skipped_by_reason["budget_exceeded"] = (
            skipped_by_reason.get("budget_exceeded", 0) + 1
        )
        skip_details.append(
            {
                "external_userid": str(item.get("external_userid") or ""),
                "skip_reason": result.skip_reason,
                "verdicts": [v.__dict__ for v in result.verdicts],
            }
        )
    elapsed_ms = int((time.monotonic() - started) * 1000)
    if elapsed_ms > 500:
        logger.warning(
            "frequency_budget filter slow: %d items in %d ms", len(eligible_items), elapsed_ms
        )
    return allowed, skipped_by_reason, skip_details
