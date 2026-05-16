"""互动聚合视图查询服务 — Cloud 端"读"用户互动历史的统一入口。

直接读视图 ``automation_member_interaction_stats``（迁移 0004 创建），
该视图把 ``automation_touch_delivery_log`` / ``automation_ai_push_log`` /
``automation_member`` 在成员维度聚合，避免 Cloud Agent 跨多表查询带来的
N+1 + 大 prompt 问题。

补充信息（回复率 / 沉默天数 / 最近一次有效互动）由本服务计算后回填。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from ...db import get_db


logger = logging.getLogger(__name__)


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def query_member_interaction_stats(
    *,
    external_contact_ids: Iterable[str] = (),
    member_ids: Iterable[int] = (),
    lookback_days: int = 30,
) -> list[dict[str, Any]]:
    """对一批成员返回互动聚合，单批最多 500 条。

    Returns:
        [{
            "member_id": int, "external_contact_id": str, "phone": str,
            "current_pool": str, "current_audience_code": str,
            "profile_segment_key": str, "behavior_tier_key": str,
            "outbound_count_total": int, "outbound_count_7d": int,
            "outbound_count_30d": int,
            "last_outbound_at": str, "last_inbound_at": str,
            "reply_count_30d": int, "reply_rate_30d": float,
            "silent_days": int|None,
            "ai_cooldown_active": bool, "ai_push_count_30d": int,
        }, ...]
    """
    external_list = [str(x).strip() for x in external_contact_ids if str(x).strip()]
    member_list = [int(x) for x in member_ids if str(x).strip()]
    if not external_list and not member_list:
        return []
    external_list = external_list[:500]
    member_list = member_list[:500]
    db = get_db()
    cur = db.cursor()
    rows: list[dict[str, Any]] = []
    if external_list:
        placeholders = ",".join(["?"] * len(external_list))
        cur.execute(
            f"""
            SELECT * FROM automation_member_interaction_stats
            WHERE external_contact_id IN ({placeholders})
            """,
            tuple(external_list),
        )
        rows.extend(dict(r) for r in (cur.fetchall() or []))
    if member_list:
        placeholders = ",".join(["?"] * len(member_list))
        cur.execute(
            f"""
            SELECT * FROM automation_member_interaction_stats
            WHERE member_id IN ({placeholders})
            """,
            tuple(member_list),
        )
        seen_ids = {int(r["member_id"]) for r in rows}
        for r in cur.fetchall() or []:
            d = dict(r)
            if int(d["member_id"]) not in seen_ids:
                rows.append(d)
    # 回填回复数 / 沉默天数 / cooldown active
    now = _utc_now_naive()
    cutoff_iso = (now - timedelta(days=int(lookback_days))).isoformat()
    out: list[dict[str, Any]] = []
    for row in rows:
        member_id = int(row.get("member_id") or 0)
        last_inbound_at = ""
        reply_count = 0
        if member_id:
            cur.execute(
                """
                SELECT MAX(last_inbound_at) AS last_in
                FROM automation_reply_monitor_queue WHERE member_id = ?
                """,
                (member_id,),
            )
            r2 = cur.fetchone()
            last_inbound_at = str(r2["last_in"] or "") if r2 else ""
            cur.execute(
                """
                SELECT COUNT(*) AS c
                FROM automation_reply_monitor_queue
                WHERE member_id = ? AND last_inbound_at >= ?
                """,
                (member_id, cutoff_iso),
            )
            r3 = cur.fetchone()
            reply_count = int(r3["c"] or 0) if r3 else 0
        outbound_30d = int(row.get("outbound_count_30d") or 0)
        reply_rate = (reply_count / outbound_30d) if outbound_30d > 0 else 0.0
        last_out_dt = _parse_iso(str(row.get("last_outbound_at") or ""))
        last_in_dt = _parse_iso(last_inbound_at)
        silent_days: int | None = None
        if last_out_dt:
            base = last_in_dt if (last_in_dt and last_in_dt > last_out_dt) else last_out_dt
            delta = now - base
            silent_days = max(0, delta.days)
        cooldown_until_dt = _parse_iso(str(row.get("ai_cooldown_until") or ""))
        cooldown_active = bool(cooldown_until_dt and cooldown_until_dt > now)
        out.append(
            {
                "member_id": member_id,
                "external_contact_id": str(row.get("external_contact_id") or ""),
                "phone": str(row.get("phone") or ""),
                "current_pool": str(row.get("current_pool") or ""),
                "current_audience_code": str(row.get("current_audience_code") or ""),
                "profile_segment_key": str(row.get("profile_segment_key") or ""),
                "behavior_tier_key": str(row.get("behavior_tier_key") or ""),
                "outbound_count_total": int(row.get("outbound_count_total") or 0),
                "outbound_count_7d": int(row.get("outbound_count_7d") or 0),
                "outbound_count_30d": outbound_30d,
                "last_outbound_at": str(row.get("last_outbound_at") or ""),
                "last_inbound_at": last_inbound_at,
                "reply_count_30d": reply_count,
                "reply_rate_30d": round(reply_rate, 4),
                "silent_days": silent_days,
                "ai_cooldown_active": cooldown_active,
                "ai_cooldown_until": str(row.get("ai_cooldown_until") or ""),
                "ai_push_count_30d": int(row.get("ai_push_count_30d") or 0),
                "last_ai_push_at": str(row.get("last_ai_push_log_at") or row.get("last_ai_push_at") or ""),
            }
        )
    return out


def aggregate_population_stats(items: list[dict[str, Any]]) -> dict[str, Any]:
    """对一批 member 的 stats 做总体汇总，给 Cloud 端做"人群解读"。

    返回的字段 Cloud Agent 直接拿来生成"why_selected"解释 / 给话术 AI 发工单的人群摘要。
    """
    if not items:
        return {
            "total": 0,
            "outbound_count_30d_avg": 0,
            "reply_rate_30d_avg": 0.0,
            "silent_distribution": {"<=7": 0, "8-14": 0, "15-30": 0, ">30": 0, "unknown": 0},
            "pool_distribution": {},
            "profile_segment_distribution": {},
            "behavior_tier_distribution": {},
            "cooldown_active_count": 0,
        }
    total = len(items)
    outbound_sum = sum(int(i.get("outbound_count_30d") or 0) for i in items)
    reply_rate_sum = sum(float(i.get("reply_rate_30d") or 0.0) for i in items)
    silent_buckets = {"<=7": 0, "8-14": 0, "15-30": 0, ">30": 0, "unknown": 0}
    pool_dist: dict[str, int] = {}
    profile_dist: dict[str, int] = {}
    behavior_dist: dict[str, int] = {}
    cooldown_count = 0
    for it in items:
        days = it.get("silent_days")
        if days is None:
            silent_buckets["unknown"] += 1
        elif days <= 7:
            silent_buckets["<=7"] += 1
        elif days <= 14:
            silent_buckets["8-14"] += 1
        elif days <= 30:
            silent_buckets["15-30"] += 1
        else:
            silent_buckets[">30"] += 1
        pool_dist[str(it.get("current_pool") or "unknown")] = pool_dist.get(str(it.get("current_pool") or "unknown"), 0) + 1
        ps = str(it.get("profile_segment_key") or "unknown")
        profile_dist[ps] = profile_dist.get(ps, 0) + 1
        bh = str(it.get("behavior_tier_key") or "unknown")
        behavior_dist[bh] = behavior_dist.get(bh, 0) + 1
        if it.get("ai_cooldown_active"):
            cooldown_count += 1
    return {
        "total": total,
        "outbound_count_30d_avg": round(outbound_sum / total, 2),
        "reply_rate_30d_avg": round(reply_rate_sum / total, 4),
        "silent_distribution": silent_buckets,
        "pool_distribution": pool_dist,
        "profile_segment_distribution": profile_dist,
        "behavior_tier_distribution": behavior_dist,
        "cooldown_active_count": cooldown_count,
    }


def query_recent_touch_outcomes(
    *,
    plan_id: str = "",
    trace_id: str = "",
    send_record_id: int | None = None,
    lookback_hours: int = 72,
) -> dict[str, Any]:
    """T+24 / T+72 跟进：群发后多少人收到、多少人回复、多少人转化。

    优先级：plan_id（cloud_broadcast_plans）> trace_id > send_record_id。
    """
    db = get_db()
    cur = db.cursor()
    sent_count = 0
    skip_count = 0
    delivered_count = 0
    reply_items: list[dict[str, Any]] = []

    target_record_id: int | None = None
    target_trace_id = (trace_id or "").strip()
    if plan_id:
        cur.execute(
            "SELECT trace_id, commit_send_record_id FROM cloud_broadcast_plans WHERE plan_id = ?",
            (str(plan_id),),
        )
        row = cur.fetchone()
        if row:
            target_trace_id = target_trace_id or str(row["trace_id"] or "")
            target_record_id = int(row["commit_send_record_id"] or 0) or None
    if send_record_id is not None:
        target_record_id = int(send_record_id)

    if target_trace_id:
        cur.execute(
            """
            SELECT status, COUNT(*) AS c
            FROM automation_touch_delivery_log
            WHERE trace_id = ?
            GROUP BY status
            """,
            (target_trace_id,),
        )
        for row in cur.fetchall() or []:
            status = (row["status"] or "").lower()
            count = int(row["c"] or 0)
            if status == "sent":
                sent_count += count
                delivered_count += count
            elif status == "skipped":
                skip_count += count

    if target_record_id:
        cur.execute(
            """
            SELECT eligible_count, sent_count, skipped_count
            FROM user_ops_send_records WHERE id = ?
            """,
            (int(target_record_id),),
        )
        row = cur.fetchone()
        if row:
            sent_count = int(row["sent_count"] or sent_count)
            skip_count = int(row["skipped_count"] or skip_count)

    cutoff_iso = (_utc_now_naive() - timedelta(hours=int(lookback_hours))).isoformat()
    if target_trace_id:
        cur.execute(
            """
            SELECT q.member_id, q.last_inbound_at, m.external_contact_id
            FROM automation_reply_monitor_queue q
            JOIN automation_member m ON m.id = q.member_id
            WHERE q.last_inbound_at >= ?
            AND EXISTS (
                SELECT 1 FROM automation_touch_delivery_log d
                WHERE d.member_id = q.member_id
                  AND d.trace_id = ?
                  AND d.status = 'sent'
            )
            """,
            (cutoff_iso, target_trace_id),
        )
        for row in cur.fetchall() or []:
            reply_items.append(
                {
                    "external_contact_id": str(row["external_contact_id"] or ""),
                    "replied_at": str(row["last_inbound_at"] or ""),
                }
            )
    return {
        "plan_id": plan_id,
        "trace_id": target_trace_id,
        "send_record_id": target_record_id,
        "sent": sent_count,
        "delivered": delivered_count,
        "skipped": skip_count,
        "reply_count": len(reply_items),
        "replies": reply_items[:50],
        "reply_rate": round(len(reply_items) / sent_count, 4) if sent_count else 0.0,
        "lookback_hours": int(lookback_hours),
    }


def scan_silent_for_revival(
    *,
    silent_days_min: int = 14,
    silent_days_max: int = 60,
    pool_keys: Iterable[str] = ("active_focus", "inactive_focus"),
    limit: int = 100,
) -> list[dict[str, Any]]:
    """扫描沉默池候选 — 给 Cloud Agent 决定是否激活。

    - 最近一次 outbound 在 [silent_days_min, silent_days_max] 区间
    - 之后无 inbound（即真沉默）
    - 不在 cooldown
    - 在指定 pool 集合内
    """
    db = get_db()
    cur = db.cursor()
    pool_list = [str(p) for p in pool_keys if p]
    if not pool_list:
        pool_list = ["active_focus", "inactive_focus"]
    placeholders = ",".join(["?"] * len(pool_list))
    cur.execute(
        f"""
        SELECT
            m.id AS member_id,
            m.external_contact_id,
            m.phone,
            m.current_pool,
            m.profile_segment_key,
            m.behavior_tier_key,
            m.ai_cooldown_until,
            (SELECT MAX(sent_at) FROM automation_touch_delivery_log d
                WHERE d.member_id = m.id AND d.status = 'sent') AS last_outbound_at,
            (SELECT MAX(last_inbound_at) FROM automation_reply_monitor_queue q
                WHERE q.member_id = m.id) AS last_inbound_at
        FROM automation_member m
        WHERE m.current_pool IN ({placeholders})
        ORDER BY m.id ASC
        LIMIT ?
        """,
        (*pool_list, int(limit) * 4),
    )
    raw = cur.fetchall() or []
    out: list[dict[str, Any]] = []
    now = _utc_now_naive()
    for row in raw:
        last_out = _parse_iso(str(row["last_outbound_at"] or ""))
        last_in = _parse_iso(str(row["last_inbound_at"] or ""))
        if not last_out:
            continue
        if last_in and last_in > last_out:
            continue
        days_since = (now - last_out).days
        if days_since < silent_days_min or days_since > silent_days_max:
            continue
        cooldown = _parse_iso(str(row["ai_cooldown_until"] or ""))
        if cooldown and cooldown > now:
            continue
        out.append(
            {
                "member_id": int(row["member_id"]),
                "external_contact_id": str(row["external_contact_id"] or ""),
                "phone": str(row["phone"] or ""),
                "current_pool": str(row["current_pool"] or ""),
                "profile_segment_key": str(row["profile_segment_key"] or ""),
                "behavior_tier_key": str(row["behavior_tier_key"] or ""),
                "last_outbound_at": str(row["last_outbound_at"] or ""),
                "silent_days": days_since,
            }
        )
        if len(out) >= int(limit):
            break
    return out


def query_segment_dimensions() -> dict[str, Any]:
    """返回当前可用的筛选维度元数据 — Cloud Agent 决策前的"快速识图"。"""
    db = get_db()
    cur = db.cursor()
    pool_keys = []
    cur.execute(
        "SELECT DISTINCT current_pool FROM automation_member WHERE current_pool <> '' ORDER BY current_pool"
    )
    pool_keys = [str(row["current_pool"]) for row in (cur.fetchall() or [])]

    cur.execute(
        "SELECT DISTINCT profile_segment_key FROM automation_member WHERE profile_segment_key <> '' ORDER BY profile_segment_key"
    )
    profile_keys = [str(row["profile_segment_key"]) for row in (cur.fetchall() or [])]

    cur.execute(
        "SELECT DISTINCT behavior_tier_key FROM automation_member WHERE behavior_tier_key <> '' ORDER BY behavior_tier_key"
    )
    behavior_keys = [str(row["behavior_tier_key"]) for row in (cur.fetchall() or [])]

    cur.execute(
        "SELECT DISTINCT current_audience_code FROM automation_member WHERE current_audience_code <> '' ORDER BY current_audience_code"
    )
    audience_codes = [str(row["current_audience_code"]) for row in (cur.fetchall() or [])]

    return {
        "pool_keys": pool_keys,
        "profile_segment_keys": profile_keys,
        "behavior_tier_keys": behavior_keys,
        "audience_codes": audience_codes,
    }


__all__ = [
    "query_member_interaction_stats",
    "aggregate_population_stats",
    "query_recent_touch_outcomes",
    "scan_silent_for_revival",
    "query_segment_dimensions",
]
