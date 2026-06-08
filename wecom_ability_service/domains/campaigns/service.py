"""Campaign 服务 — 创建草稿、互斥分配、提交审阅、人工启动。

互斥分配是这个文件的灵魂：``allocate_campaign_members`` 把所有 Segment 命中
的 member 按 ``priority`` 排序，第一次见到的 member 才落到 ``campaign_members``，
重复命中的全部丢弃 — UNIQUE(campaign_id, member_id) 兜底保证。

整个 Campaign 的生命周期：

    propose_campaign (Agent)
        ├─ 创建 campaigns 行 (review_status=pending_review, run_status=draft)
        ├─ 创建 campaign_segments 行（带 priority）
        ├─ 创建 campaign_steps 行（每个 segment 自己的节奏）
        └─ allocate_campaign_members（互斥分配候选）

    submit_campaign_for_review (Agent)
        └─ 把 metadata 整理好，CRM 后台开始能看到这个 Campaign

    start_campaign (CRM 后台 + 人工 token)
        ├─ run_status = active
        ├─ 给每个 campaign_member 计算 next_due_at（基于 anchor_mode）
        └─ Cron 接管，按 due 推送
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from ...db import get_db
from ..segments.service import get_segment, increment_usage
from ..segments.sql_sandbox import fetch_member_rows
from .payload_helpers import normalize_int_list, normalize_str_list, parse_step_payload
from .time_helpers import DEFAULT_SEND_TIME as _DEFAULT_SEND_TIME
from .time_helpers import DEFAULT_TIMEZONE as _DEFAULT_TIMEZONE
from .time_helpers import campaign_step_due_iso


logger = logging.getLogger(__name__)


_VALID_ANCHOR_MODES = ("campaign_start_date", "member_joined_at")
_EDITABLE_REVIEW_STATUSES = ("draft", "pending_review")
_EDITABLE_RUN_STATUSES = ("draft", "paused")


def _now_iso() -> str:
    # 同 scheduler._now_iso —— 必须 timezone-aware，否则 PG TIMESTAMPTZ 解读错位
    return datetime.now(timezone.utc).isoformat()


def _new_campaign_code() -> str:
    return f"camp-{uuid.uuid4().hex[:12]}"


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        loaded = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _find_active_member_conflicts(*, campaign_id: int, limit: int = 10) -> dict[str, Any]:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        SELECT COUNT(*) AS conflict_count
        FROM campaign_members cm
        JOIN campaign_members other_cm
          ON other_cm.external_contact_id = cm.external_contact_id
         AND other_cm.campaign_id <> cm.campaign_id
         AND other_cm.status IN ('pending', 'running')
        JOIN campaigns other_c
          ON other_c.id = other_cm.campaign_id
         AND other_c.run_status = 'active'
        WHERE cm.campaign_id = ?
          AND cm.status = 'pending'
          AND cm.external_contact_id <> ''
        """,
        (int(campaign_id),),
    )
    count_row = cur.fetchone()
    total = int(count_row["conflict_count"] or 0) if count_row else 0
    if not total:
        return {"count": 0, "examples": []}
    cur.execute(
        """
        SELECT cm.external_contact_id,
               other_c.id AS campaign_id,
               other_c.campaign_code,
               other_c.display_name
        FROM campaign_members cm
        JOIN campaign_members other_cm
          ON other_cm.external_contact_id = cm.external_contact_id
         AND other_cm.campaign_id <> cm.campaign_id
         AND other_cm.status IN ('pending', 'running')
        JOIN campaigns other_c
          ON other_c.id = other_cm.campaign_id
         AND other_c.run_status = 'active'
        WHERE cm.campaign_id = ?
          AND cm.status = 'pending'
          AND cm.external_contact_id <> ''
        ORDER BY other_c.started_at DESC, other_c.id DESC, cm.id ASC
        LIMIT ?
        """,
        (int(campaign_id), int(limit)),
    )
    return {"count": total, "examples": [dict(row) for row in (cur.fetchall() or [])]}


def _compute_first_step_due_iso(
    *,
    anchor_date: str,
    day_offset: int,
    send_time: str,
    step_timezone: str,
) -> str:
    """算 D+day_offset @ send_time 在 step.timezone 下的 tz-aware ISO。

    必须输出带时区后缀的 ISO（如 ``2026-05-09T08:00:00+08:00``），否则 PG
    TIMESTAMPTZ 字段会按 server timezone（Asia/Shanghai）解读 naive 字符串，
    跨 UTC↔本地的写入会错位 8 小时，cron 立即扫到一个"已过期"的 due。
    """
    return campaign_step_due_iso(
        anchor_date=anchor_date,
        day_offset=day_offset,
        send_time=send_time,
        step_timezone=step_timezone,
    )


def _ensure_campaign_editable(camp: dict[str, Any]) -> None:
    review_status = camp.get("review_status")
    if review_status not in _EDITABLE_REVIEW_STATUSES:
        raise PermissionError(f"campaign review_status={review_status} not editable")
    run_status = camp.get("run_status")
    if run_status not in _EDITABLE_RUN_STATUSES:
        raise PermissionError(f"campaign run_status={run_status} not editable")


def _table_columns(table_name: str) -> set[str]:
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = ?
            """,
            (table_name,),
        )
        columns = {str(row["column_name"]) for row in (cur.fetchall() or [])}
        if columns:
            return columns
    except Exception:
        try:
            if hasattr(db, "rollback"):
                db.rollback()
        except Exception:
            pass
    return set()


def _insert_campaign_member(
    *,
    cur: Any,
    campaign_member_columns: set[str],
    campaign_id: int,
    campaign_segment_id: int,
    segment_id: int,
    member_id: int,
    external_contact_id: str,
    trace_id: str,
) -> None:
    columns = [
        "campaign_id",
        "campaign_segment_id",
        "segment_id",
        "member_id",
        "external_contact_id",
        "status",
    ]
    values: list[Any] = [
        int(campaign_id),
        int(campaign_segment_id),
        int(segment_id),
        int(member_id),
        external_contact_id,
        "pending",
    ]
    if "current_step_index" in campaign_member_columns:
        columns.append("current_step_index")
        values.append(-1)
    if "trace_id" in campaign_member_columns:
        columns.append("trace_id")
        values.append(trace_id)
    placeholders = ", ".join("?" for _ in values)
    cur.execute(
        f"INSERT INTO campaign_members ({', '.join(columns)}) VALUES ({placeholders})",
        tuple(values),
    )


# ---------- 创建 / 编辑 -----------------------------------------------------

def create_campaign_draft(
    *,
    campaign_code: str = "",
    display_name: str,
    intent: str,
    anchor_mode: str = "campaign_start_date",
    anchor_date: str = "",
    owner_userid: str = "",
    operator: str = "",
    session_id: str = "",
    trace_id: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if anchor_mode not in _VALID_ANCHOR_MODES:
        raise ValueError(f"invalid anchor_mode: {anchor_mode}")
    code = (campaign_code or "").strip() or _new_campaign_code()
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT id FROM campaigns WHERE campaign_code = ?", (code,))
    if cur.fetchone():
        raise ValueError(f"campaign_code already exists: {code}")
    effective_anchor = (anchor_date or "").strip()
    if not effective_anchor and anchor_mode == "campaign_start_date":
        effective_anchor = datetime.now(timezone.utc).date().isoformat()
    cur.execute(
        """
        INSERT INTO campaigns
            (campaign_code, display_name, intent, anchor_mode, anchor_date,
             review_status, run_status, created_by_agent, created_by_session,
             trace_id, owner_userid, metadata_json)
        VALUES (?, ?, ?, ?, ?, 'draft', 'draft', ?, ?, ?, ?, ?)
        """,
        (
            code,
            (display_name or "").strip() or code,
            (intent or "").strip(),
            anchor_mode,
            effective_anchor,
            (operator or "")[:100],
            (session_id or "")[:100],
            (trace_id or "")[:100],
            (owner_userid or "")[:100],
            json.dumps(metadata or {}, ensure_ascii=False),
        ),
    )
    db.commit()
    return get_campaign(campaign_id=int(cur.lastrowid or 0)) or {}


def add_segment_to_campaign(
    *,
    campaign_id: int,
    segment_code: str = "",
    segment_id: int | None = None,
    priority: int = 100,
    label: str = "",
) -> dict[str, Any]:
    seg = get_segment(segment_code=segment_code, segment_id=segment_id)
    if not seg:
        raise LookupError("segment not found")
    if str(seg.get("status") or "") != "active":
        raise ValueError(f"segment not active: {seg.get('segment_code')}")
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "SELECT id FROM campaign_segments WHERE campaign_id = ? AND segment_id = ?",
        (int(campaign_id), int(seg["id"])),
    )
    existing = cur.fetchone()
    if existing:
        return {"id": int(existing["id"]), "status": "exists"}
    cur.execute(
        """
        INSERT INTO campaign_segments
            (campaign_id, segment_id, segment_code, priority, label)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            int(campaign_id),
            int(seg["id"]),
            str(seg["segment_code"]),
            int(priority),
            (label or "")[:200],
        ),
    )
    db.commit()
    increment_usage(segment_id=int(seg["id"]))
    return {"id": int(cur.lastrowid or 0), "segment_id": int(seg["id"])}


def add_step_to_campaign(
    *,
    campaign_id: int,
    campaign_segment_id: int,
    step_index: int,
    day_offset: int,
    content_text: str = "",
    content_payload: dict[str, Any] | None = None,
    send_time: str = _DEFAULT_SEND_TIME,
    timezone: str = "Asia/Shanghai",
    stop_on_reply: bool = True,
    skip_if_recently_touched_days: int = 0,
    agent_run_id: str = "",
) -> dict[str, Any]:
    db = get_db()
    cur = db.cursor()
    # PG-only upsert; keep this explicit and avoid legacy replace semantics.
    cur.execute(
        """
        INSERT INTO campaign_steps
            (campaign_id, campaign_segment_id, step_index, day_offset, send_time,
             timezone, content_text, content_payload_json, stop_on_reply,
             skip_if_recently_touched_days, agent_run_id, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (campaign_segment_id, step_index) DO UPDATE SET
            campaign_id = excluded.campaign_id,
            day_offset = excluded.day_offset,
            send_time = excluded.send_time,
            timezone = excluded.timezone,
            content_text = excluded.content_text,
            content_payload_json = excluded.content_payload_json,
            stop_on_reply = excluded.stop_on_reply,
            skip_if_recently_touched_days = excluded.skip_if_recently_touched_days,
            agent_run_id = excluded.agent_run_id,
            updated_at = excluded.updated_at
        """,
        (
            int(campaign_id),
            int(campaign_segment_id),
            int(step_index),
            int(day_offset),
            (send_time or _DEFAULT_SEND_TIME),
            (timezone or "Asia/Shanghai"),
            (content_text or "")[:4000],
            json.dumps(content_payload or {}, ensure_ascii=False),
            bool(stop_on_reply),
            int(skip_if_recently_touched_days or 0),
            (agent_run_id or "")[:100],
            _now_iso(),
        ),
    )
    db.commit()
    return {"campaign_segment_id": int(campaign_segment_id), "step_index": int(step_index)}


# ---------- 互斥分配 — 灵魂 ------------------------------------------------

def allocate_campaign_members(
    *,
    campaign_id: int,
) -> dict[str, Any]:
    """对 Campaign 下所有 segment 跑一遍 SQL，按 priority 互斥分配 member。

    保证：
    - 高优先级 segment 先扫，扫到的 member 就锁在那个 segment 上
    - 低优先级 segment 即使扫到同一个 member，UNIQUE 约束会拒绝插入
    - 整个分配在一个事务里完成（避免并发竞争）
    """
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "SELECT trace_id, anchor_mode, anchor_date FROM campaigns WHERE id = ?",
        (int(campaign_id),),
    )
    camp_row = cur.fetchone()
    if not camp_row:
        raise LookupError("campaign not found")
    trace_id = str(camp_row["trace_id"] or "")

    cur.execute(
        """
        SELECT cs.id AS campaign_segment_id, cs.segment_id, cs.priority,
               s.segment_code, s.sql_query, s.sql_params_json, s.status
        FROM campaign_segments cs
        JOIN segments s ON s.id = cs.segment_id
        WHERE cs.campaign_id = ?
        ORDER BY cs.priority DESC, cs.id ASC
        """,
        (int(campaign_id),),
    )
    seg_rows = cur.fetchall() or []
    if not seg_rows:
        return {"campaign_id": campaign_id, "allocated": 0, "skipped_collisions": 0}

    allocated = 0
    collision = 0
    per_segment: dict[int, dict[str, int]] = {}
    seen_member_ids: set[int] = set()
    allocation_errors: list[dict[str, Any]] = []
    campaign_member_columns = _table_columns("campaign_members")

    for s in seg_rows:
        if str(s["status"] or "") != "active":
            continue
        seg_id = int(s["segment_id"])
        cs_id = int(s["campaign_segment_id"])
        params = _json_object(s["sql_params_json"])
        try:
            member_rows = fetch_member_rows(sql=str(s["sql_query"] or ""), params=params)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("segment %s sql failed during allocation: %s", s["segment_code"], exc)
            continue
        bucket = per_segment.setdefault(cs_id, {"matched": 0, "allocated": 0, "skipped": 0})
        bucket["matched"] += len(member_rows)
        for mr_in in member_rows:
            mid = mr_in["member_id"]
            sql_ext = mr_in.get("external_contact_id", "")
            if mid in seen_member_ids:
                collision += 1
                bucket["skipped"] += 1
                continue
            # 优先用 segment SQL 自带的 external_contact_id (允许 user_ops_pool_current 等表
            # 直接输出 ext_id), 没带才 fallback 到 automation_member.id 反查 (兼容老 segment).
            external = sql_ext
            if not external:
                cur.execute(
                    "SELECT external_contact_id FROM automation_member WHERE id = ?",
                    (int(mid),),
                )
                mr = cur.fetchone()
                external = str(mr["external_contact_id"] or "") if mr else ""
            try:
                sp_name = f"_campaign_member_alloc_{cs_id}_{int(mid)}"
                cur.execute(f"SAVEPOINT {sp_name}")
                _insert_campaign_member(
                    cur=cur,
                    campaign_member_columns=campaign_member_columns,
                    campaign_id=int(campaign_id),
                    campaign_segment_id=cs_id,
                    segment_id=seg_id,
                    member_id=int(mid),
                    external_contact_id=external,
                    trace_id=trace_id,
                )
                cur.execute(f"RELEASE SAVEPOINT {sp_name}")
                seen_member_ids.add(mid)
                allocated += 1
                bucket["allocated"] += 1
            except Exception as exc:
                try:
                    cur.execute(f"ROLLBACK TO SAVEPOINT {sp_name}")
                    cur.execute(f"RELEASE SAVEPOINT {sp_name}")
                except Exception:
                    pass
                logger.debug("allocate skip mid=%s reason=%s", mid, exc)
                collision += 1
                bucket["skipped"] += 1
                if len(allocation_errors) < 10:
                    allocation_errors.append(
                        {
                            "member_id": int(mid),
                            "campaign_segment_id": cs_id,
                            "reason": str(exc),
                        }
                    )
    db.commit()
    return {
        "campaign_id": campaign_id,
        "allocated": allocated,
        "skipped_collisions": collision,
        "per_segment": per_segment,
        "errors": allocation_errors,
        "trace_id": trace_id,
    }


# ---------- 状态机 ----------------------------------------------------------

def submit_campaign_for_review(*, campaign_id: int, operator: str = "") -> dict[str, Any]:
    """Agent 端把方案打磨好，提交 CRM 端审阅 — review_status: draft → pending_review。"""
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "UPDATE campaigns SET review_status = 'pending_review', updated_at = ? "
        "WHERE id = ? AND review_status IN ('draft','pending_review')",
        (_now_iso(), int(campaign_id)),
    )
    db.commit()
    if not cur.rowcount:
        raise RuntimeError("campaign not in submittable state")
    logger.info("campaign %s submitted for review by %s", campaign_id, operator)
    return get_campaign(campaign_id=campaign_id) or {}


def start_campaign(
    *,
    campaign_id: int,
    human_approver: str,
    approval_token_value: str,
) -> dict[str, Any]:
    """CRM 后台 + 人工 token → Campaign 真正启动，调度器接管。"""
    from ..cloud_orchestrator import approval_token

    if not approval_token_value:
        raise PermissionError("approval_token is required")
    camp = get_campaign(campaign_id=campaign_id)
    if not camp:
        raise LookupError("campaign not found")
    if camp.get("run_status") in ("active", "paused", "finished"):
        return camp
    conflicts = _find_active_member_conflicts(campaign_id=campaign_id)
    if conflicts["count"]:
        sample = ", ".join(
            f"{item.get('external_contact_id')}->{item.get('campaign_code')}"
            for item in conflicts["examples"][:5]
        )
        raise PermissionError(
            f"campaign has {conflicts['count']} member(s) already pending/running "
            f"in active campaigns; examples: {sample}; pause or finish the existing "
            "campaign before starting this one"
        )
    token_check = approval_token.consume_token(
        token=approval_token_value,
        plan_id=str(camp["campaign_code"]),
        consumer=human_approver,
        scope="start_campaign",
    )
    if not token_check.get("ok"):
        raise PermissionError(f"approval_token rejected: {token_check.get('reason')}")
    db = get_db()
    cur = db.cursor()
    started_at = _now_iso()
    cur.execute(
        """
        UPDATE campaigns SET
            review_status = 'approved', run_status = 'active',
            approved_by = ?, approved_at = ?, started_at = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            str(human_approver)[:100],
            started_at,
            started_at,
            started_at,
            int(campaign_id),
        ),
    )
    # 给所有 campaign_member 计算 anchor_date + 第一步 next_due_at
    anchor_mode = str(camp.get("anchor_mode") or "campaign_start_date")
    if anchor_mode == "campaign_start_date":
        anchor_date = str(camp.get("anchor_date") or "") or datetime.now(timezone.utc).date().isoformat()
        cur.execute(
            "UPDATE campaign_members SET anchor_date = ?, joined_at = ? WHERE campaign_id = ?",
            (anchor_date, started_at, int(campaign_id)),
        )
    else:
        # member_joined_at — anchor_date 取 joined_at 当天的 UTC 日期，避免跨时区错位
        cur.execute(
            "UPDATE campaign_members SET anchor_date = "
            "TO_CHAR(joined_at AT TIME ZONE 'UTC', 'YYYY-MM-DD') "
            "WHERE campaign_id = ?",
            (int(campaign_id),),
        )
    # 第一步 due 时间 = anchor_date + day_offset @ send_time
    cur.execute(
        """
        SELECT cm.id AS cm_id, cm.campaign_segment_id, cm.anchor_date
        FROM campaign_members cm
        WHERE cm.campaign_id = ? AND cm.status = 'pending'
        """,
        (int(campaign_id),),
    )
    member_rows = cur.fetchall() or []
    for mr in member_rows:
        cur.execute(
            """
            SELECT day_offset, send_time, timezone
            FROM campaign_steps
            WHERE campaign_segment_id = ?
            ORDER BY step_index ASC LIMIT 1
            """,
            (int(mr["campaign_segment_id"]),),
        )
        step_row = cur.fetchone()
        if not step_row:
            continue
        due_iso = _compute_first_step_due_iso(
            anchor_date=str(mr["anchor_date"] or ""),
            day_offset=int(step_row["day_offset"] or 0),
            send_time=str(step_row["send_time"] or _DEFAULT_SEND_TIME),
            step_timezone=str(step_row["timezone"] or _DEFAULT_TIMEZONE),
        )
        cur.execute(
            "UPDATE campaign_members SET next_due_at = ?, current_step_index = -1 WHERE id = ?",
            (due_iso, int(mr["cm_id"])),
        )
    db.commit()
    try:
        from .scheduler import ensure_campaign_scheduled_jobs

        ensure_campaign_scheduled_jobs(campaign_id=int(campaign_id))
    except Exception as exc:  # pragma: no cover - scheduling fallback remains run-due
        logger.warning("campaign %s schedule sync failed after start: %s", campaign_id, exc)
    logger.info("campaign %s started by %s", campaign_id, human_approver)
    return get_campaign(campaign_id=campaign_id) or {}


def pause_campaign(*, campaign_id: int, reason: str = "") -> dict[str, Any]:
    db = get_db()
    cur = db.cursor()
    now = _now_iso()
    cur.execute(
        "UPDATE campaigns SET run_status = 'paused', paused_at = ?, paused_reason = ?, updated_at = ? "
        "WHERE id = ? AND run_status = 'active'",
        (now, str(reason)[:200], now, int(campaign_id)),
    )
    if cur.rowcount:
        # Campaign jobs are keyed as "{campaign_id}:{campaign_segment_id}:{step_index}"
        # (and older jobs as "{campaign_id}:{step_index}").  Pausing must stop
        # already scheduled queue entries too; otherwise the worker can still
        # send from broadcast_jobs after the campaign is paused.
        cur.execute(
            """
            UPDATE broadcast_jobs
            SET status = 'cancelled',
                cancelled_by = ?,
                cancelled_at = CURRENT_TIMESTAMP,
                cancel_reason = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE source_type = 'campaign'
              AND source_id LIKE ?
              AND status IN ('queued', 'waiting_approval')
            """,
            (
                "campaign_pause",
                (str(reason) or "campaign paused")[:1000],
                f"{int(campaign_id)}:%",
            ),
        )
        logger.info(
            "campaign %s paused; cancelled %s open broadcast job(s)",
            campaign_id,
            int(cur.rowcount or 0),
        )
    db.commit()
    return get_campaign(campaign_id=campaign_id) or {}


def resume_campaign(*, campaign_id: int) -> dict[str, Any]:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "UPDATE campaigns SET run_status = 'active', paused_at = '', paused_reason = '', updated_at = ? "
        "WHERE id = ? AND run_status = 'paused'",
        (_now_iso(), int(campaign_id)),
    )
    db.commit()
    return get_campaign(campaign_id=campaign_id) or {}


def reject_campaign(*, campaign_id: int, reason: str = "") -> bool:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "UPDATE campaigns SET review_status = 'rejected', run_status = 'cancelled', "
        "paused_reason = ?, updated_at = ? WHERE id = ?",
        (str(reason)[:200], _now_iso(), int(campaign_id)),
    )
    db.commit()
    return (cur.rowcount or 0) > 0


def delete_campaign(*, campaign_id: int) -> dict[str, Any]:
    """硬删 campaign 及其全部子表行（campaign_segments / campaign_steps /
    campaign_members）+ broadcast_jobs 中由该 campaign 派生出的待发批次。

    安全闸：只允许删 ``run_status in (draft, paused, cancelled, finished)``。
    active 不能删——队列里可能正在跑，删了会让 worker 拿到悬空 source_id。

    cloud_broadcast_plans.campaign_id 是兼容字段，置 NULL 即可，不删 plan。
    """
    camp = get_campaign(campaign_id=campaign_id)
    if not camp:
        raise LookupError("campaign not found")
    run_status = str(camp.get("run_status") or "")
    if run_status == "active":
        raise PermissionError(
            f"campaign run_status={run_status} 正在运行，不能删除；请先暂停或撤销"
        )

    db = get_db()
    cur = db.cursor()
    cid = int(campaign_id)
    # broadcast_jobs.source_id 是 "{campaign_id}:{campaign_segment_id}:{step_index}"
    # 形式（见 scheduler.py）。旧队列里可能还有 "{campaign_id}:{step_index}"，
    # 两者都用 LIKE '{cid}:%' 精确匹配；不能用 source_id = str(cid)。
    cur.execute(
        "DELETE FROM broadcast_jobs WHERE source_type = 'campaign' AND source_id LIKE ?",
        (f"{cid}:%",),
    )
    jobs_deleted = int(cur.rowcount or 0)
    cur.execute("DELETE FROM campaign_members WHERE campaign_id = ?", (cid,))
    members_deleted = int(cur.rowcount or 0)
    cur.execute("DELETE FROM campaign_steps WHERE campaign_id = ?", (cid,))
    steps_deleted = int(cur.rowcount or 0)
    cur.execute("DELETE FROM campaign_segments WHERE campaign_id = ?", (cid,))
    segments_deleted = int(cur.rowcount or 0)
    # cloud_broadcast_plans 留住 plan 本身（审计要），只解关联
    cur.execute(
        "UPDATE cloud_broadcast_plans SET campaign_id = NULL WHERE campaign_id = ?",
        (cid,),
    )
    plans_unlinked = int(cur.rowcount or 0)
    cur.execute("DELETE FROM campaigns WHERE id = ?", (cid,))
    deleted = (cur.rowcount or 0) > 0
    db.commit()
    return {
        "ok": deleted,
        "deleted_id": cid,
        "deleted_campaign_code": str(camp.get("campaign_code") or ""),
        "rows_cleared": {
            "campaign_segments": segments_deleted,
            "campaign_steps": steps_deleted,
            "campaign_members": members_deleted,
            "broadcast_jobs": jobs_deleted,
            "cloud_broadcast_plans_unlinked": plans_unlinked,
        },
    }


def finish_campaign(*, campaign_id: int) -> dict[str, Any]:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "UPDATE campaigns SET run_status = 'finished', finished_at = ?, updated_at = ? WHERE id = ?",
        (_now_iso(), _now_iso(), int(campaign_id)),
    )
    db.commit()
    return get_campaign(campaign_id=campaign_id) or {}


# ---------- 查询 ------------------------------------------------------------

def get_campaign(*, campaign_code: str = "", campaign_id: int | None = None) -> dict[str, Any] | None:
    db = get_db()
    cur = db.cursor()
    if campaign_id is not None:
        cur.execute("SELECT * FROM campaigns WHERE id = ?", (int(campaign_id),))
    elif campaign_code:
        cur.execute("SELECT * FROM campaigns WHERE campaign_code = ?", (str(campaign_code),))
    else:
        return None
    row = cur.fetchone()
    if not row:
        return None
    d = dict(row)
    try:
        d["metadata"] = json.loads(d.get("metadata_json") or "{}")
    except (TypeError, ValueError):
        d["metadata"] = {}
    try:
        d["stats"] = json.loads(d.get("stats_json") or "{}")
    except (TypeError, ValueError):
        d["stats"] = {}
    return d


def list_campaigns(
    *,
    review_status: str = "",
    run_status: str = "",
    limit: int = 500,
    offset: int = 0,
    group_code: str = "",
) -> list[dict[str, Any]]:
    db = get_db()
    cur = db.cursor()
    where = ["1=1"]
    args: list[Any] = []
    if review_status:
        where.append("review_status = ?")
        args.append(review_status)
    if run_status:
        where.append("run_status = ?")
        args.append(run_status)
    if group_code:
        where.append("CAST(c.metadata_json AS TEXT) LIKE ?")
        args.append(f'%"{group_code}"%')
    args.extend([max(1, min(int(limit or 500), 5000)), max(0, int(offset or 0))])
    cur.execute(
        f"""
        SELECT c.id, c.campaign_code, c.display_name, c.intent, c.anchor_mode, c.anchor_date,
               c.review_status, c.run_status, c.created_by_agent,
               c.owner_userid, c.started_at, c.finished_at,
               c.created_at, c.updated_at, c.metadata_json,
               (SELECT COUNT(*) FROM campaign_segments cs WHERE cs.campaign_id = c.id) AS segment_count,
               (SELECT COUNT(*) FROM campaign_members cm WHERE cm.campaign_id = c.id) AS member_count
        FROM campaigns c WHERE {' AND '.join(where)}
        ORDER BY c.id DESC LIMIT ? OFFSET ?
        """,
        tuple(args),
    )
    rows: list[dict[str, Any]] = []
    for r in (cur.fetchall() or []):
        d = dict(r)
        # 解 metadata_json 拿 group_code / group_label, 让前端按 group 折叠
        raw_meta = d.get("metadata_json") or "{}"
        if isinstance(raw_meta, dict):
            meta = raw_meta
        else:
            try:
                meta = json.loads(str(raw_meta) or "{}")
            except (TypeError, ValueError):
                meta = {}
        d["group_code"] = str(meta.get("group_code") or "")
        d["group_label"] = str(meta.get("group_label") or "")
        if group_code and d["group_code"] != group_code:
            continue
        rows.append(d)
    return rows


def update_campaign_step(
    *,
    campaign_id: int,
    step_index: int,
    content_text: str | None = None,
    send_time: str | None = None,
    day_offset: int | None = None,
    stop_on_reply: bool | None = None,
    image_library_ids: list[int] | None = None,
    image_media_ids: list[str] | None = None,
    miniprogram_library_ids: list[int] | None = None,
    attachment_library_ids: list[int] | None = None,
) -> dict[str, Any]:
    """编辑单个 step。只有 review_status in (draft, pending_review) 且 run_status in (draft, paused) 时才允许，
    避免运行中改文案造成混乱。

    图片配置存进 ``content_payload_json``：
    - ``image_library_ids``（推荐）：图片素材库 id 列表，scheduler 发送时调
      ``image_library.resolve_image_media_id`` 自动换出有效 media_id
    - ``image_media_ids``（老格式）：直接是企微 media_id 列表，仅兼容老数据。
      新版 UI 不再产生此字段。

    两种格式可共存，scheduler 顺序拼接。"""
    camp = get_campaign(campaign_id=campaign_id)
    if not camp:
        raise LookupError("campaign not found")
    _ensure_campaign_editable(camp)

    db = get_db()
    cur = db.cursor()
    cur.execute(
        "SELECT id, content_payload_json FROM campaign_steps "
        "WHERE campaign_id = ? AND step_index = ?",
        (int(campaign_id), int(step_index)),
    )
    existing = cur.fetchone()
    if not existing:
        raise LookupError(f"step {step_index} not found in campaign {campaign_id}")

    # PG jsonb is already a dict; legacy JSON text is still accepted defensively.
    payload = parse_step_payload(dict(existing).get("content_payload_json"))

    sets: list[str] = []
    args: list[Any] = []
    if content_text is not None:
        sets.append("content_text = ?")
        args.append(str(content_text)[:4000])
    if send_time is not None:
        sets.append("send_time = ?")
        args.append(str(send_time) or _DEFAULT_SEND_TIME)
    if day_offset is not None:
        sets.append("day_offset = ?")
        args.append(int(day_offset))
    if stop_on_reply is not None:
        sets.append("stop_on_reply = ?")
        args.append(bool(stop_on_reply))
    payload_dirty = False
    if image_library_ids is not None:
        payload["image_library_ids"] = normalize_int_list(image_library_ids, limit=9)
        payload_dirty = True
    if image_media_ids is not None:
        payload["image_media_ids"] = normalize_str_list(image_media_ids, limit=9)  # 老格式兼容
        payload_dirty = True
    if miniprogram_library_ids is not None:
        payload["miniprogram_library_ids"] = normalize_int_list(miniprogram_library_ids)
        payload_dirty = True
    if attachment_library_ids is not None:
        payload["attachment_library_ids"] = normalize_int_list(attachment_library_ids, limit=9)
        payload_dirty = True
    if payload_dirty:
        sets.append("content_payload_json = ?")
        args.append(json.dumps(payload, ensure_ascii=False))

    if not sets:
        return {"updated": False, "reason": "no_fields"}

    sets.append("updated_at = ?")
    args.append(_now_iso())
    args.extend([int(campaign_id), int(step_index)])
    cur.execute(
        f"UPDATE campaign_steps SET {', '.join(sets)} "
        "WHERE campaign_id = ? AND step_index = ?",
        tuple(args),
    )
    db.commit()
    return {"updated": True, "rowcount": int(cur.rowcount or 0)}


def delete_campaign_step(*, campaign_id: int, step_index: int) -> dict[str, Any]:
    """删除单个 step。仅 draft 态可删，且不能删完最后一条（campaign 没节奏无法启动）。"""
    camp = get_campaign(campaign_id=campaign_id)
    if not camp:
        raise LookupError("campaign not found")
    _ensure_campaign_editable(camp)
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "SELECT COUNT(*) AS cnt FROM campaign_steps WHERE campaign_id = ?",
        (int(campaign_id),),
    )
    count_row = cur.fetchone() or {}
    step_count = int(count_row.get("cnt") if isinstance(count_row, dict) else count_row[0] or 0)
    cur.execute(
        "SELECT id FROM campaign_steps WHERE campaign_id = ? AND step_index = ? LIMIT 1",
        (int(campaign_id), int(step_index)),
    )
    if not cur.fetchone():
        raise LookupError(f"step {step_index} not found in campaign {campaign_id}")
    if step_count <= 1:
        raise PermissionError("cannot delete last campaign step")
    cur.execute(
        "DELETE FROM campaign_steps WHERE campaign_id = ? AND step_index = ?",
        (int(campaign_id), int(step_index)),
    )
    db.commit()
    return {"deleted": True, "rowcount": int(cur.rowcount or 0)}


def append_campaign_step(
    *,
    campaign_id: int,
    campaign_segment_id: int,
    day_offset: int = 0,
    send_time: str = _DEFAULT_SEND_TIME,
    content_text: str = "",
    stop_on_reply: bool = True,
) -> dict[str, Any]:
    """在某 segment 末尾追加一个新 step；自动算下一个 step_index。仅 draft 态可加。"""
    camp = get_campaign(campaign_id=campaign_id)
    if not camp:
        raise LookupError("campaign not found")
    _ensure_campaign_editable(camp)
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "SELECT COALESCE(MAX(step_index), -1) AS max_idx FROM campaign_steps "
        "WHERE campaign_segment_id = ?",
        (int(campaign_segment_id),),
    )
    row = cur.fetchone() or {}
    next_idx = int(row.get("max_idx") if isinstance(row, dict) else (row[0] if row else -1)) + 1
    return add_step_to_campaign(
        campaign_id=campaign_id,
        campaign_segment_id=campaign_segment_id,
        step_index=next_idx,
        day_offset=int(day_offset),
        send_time=send_time,
        content_text=content_text,
        stop_on_reply=stop_on_reply,
    )


def list_campaign_members(
    *,
    campaign_id: int,
    status: str = "",
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """返回 Campaign 命中的成员列表 + 状态分布。每条带 external_userid，前端可链到 ``/admin/customers/<external_userid>``。"""
    db = get_db()
    cur = db.cursor()
    where = ["cm.campaign_id = ?"]
    args: list[Any] = [int(campaign_id)]
    if status:
        where.append("cm.status = ?")
        args.append(str(status))
    cur.execute(
        f"SELECT COUNT(*) AS c FROM campaign_members cm WHERE {' AND '.join(where)}",
        tuple(args),
    )
    total_row = cur.fetchone() or {}
    total = int(total_row.get("c") if isinstance(total_row, dict) else (total_row[0] if total_row else 0))
    args2 = list(args) + [int(limit), int(offset)]
    cur.execute(
        f"""
        SELECT cm.id, cm.member_id, cm.external_contact_id, cm.status, cm.stop_reason,
               cm.current_step_index, cm.next_due_at, cm.last_step_sent_at,
               cm.last_error_text, cm.retry_count, cm.anchor_date, cm.joined_at,
               cs.label AS segment_label, cs.priority AS segment_priority,
               s.display_name AS segment_name, s.segment_code,
               am.phone, am.current_pool, am.current_audience_code,
               am.profile_segment_key, am.behavior_tier_key
        FROM campaign_members cm
        JOIN campaign_segments cs ON cs.id = cm.campaign_segment_id
        JOIN segments s ON s.id = cs.segment_id
        LEFT JOIN automation_member am ON am.id = cm.member_id
        WHERE {' AND '.join(where)}
        ORDER BY cm.id DESC LIMIT ? OFFSET ?
        """,
        tuple(args2),
    )
    rows = [dict(r) for r in (cur.fetchall() or [])]
    return {"total": total, "rows": rows, "limit": int(limit), "offset": int(offset)}


def assemble_campaign_overview(*, campaign_id: int) -> dict[str, Any]:
    """聚合一个 Campaign 的全部信息：定义 + 分层 + 节奏 + 成员统计。给审阅页用。"""
    camp = get_campaign(campaign_id=campaign_id)
    if not camp:
        return {}
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        SELECT cs.id AS campaign_segment_id, cs.segment_id, cs.segment_code,
               cs.priority, cs.label,
               s.display_name AS segment_name, s.cached_headcount,
               (SELECT COUNT(*) FROM campaign_members cm
                  WHERE cm.campaign_segment_id = cs.id) AS allocated_count
        FROM campaign_segments cs
        JOIN segments s ON s.id = cs.segment_id
        WHERE cs.campaign_id = ?
        ORDER BY cs.priority DESC, cs.id ASC
        """,
        (int(campaign_id),),
    )
    segments = []
    for row in cur.fetchall() or []:
        cs_id = int(row["campaign_segment_id"])
        cur.execute(
            """
            SELECT step_index, day_offset, send_time, content_text, stop_on_reply,
                   skip_if_recently_touched_days, content_payload_json
            FROM campaign_steps
            WHERE campaign_segment_id = ?
            ORDER BY step_index ASC
            """,
            (cs_id,),
        )
        steps = []
        for r in (cur.fetchall() or []):
            sd = dict(r)
            sd["content_payload_json"] = parse_step_payload(sd.get("content_payload_json"))
            steps.append(sd)
        d = dict(row)
        d["steps"] = steps
        segments.append(d)
    cur.execute(
        """
        SELECT status, COUNT(*) AS c
        FROM campaign_members
        WHERE campaign_id = ?
        GROUP BY status
        """,
        (int(campaign_id),),
    )
    member_status = {str(r["status"] or "unknown"): int(r["c"] or 0) for r in (cur.fetchall() or [])}
    return {
        "campaign": camp,
        "segments": segments,
        "member_status_counts": member_status,
        "total_members": sum(member_status.values()),
    }


# ---------- 一站式 ---------------------------------------------------------

def propose_campaign(
    *,
    display_name: str,
    intent: str,
    segments: list[dict[str, Any]],
    anchor_mode: str = "campaign_start_date",
    anchor_date: str = "",
    owner_userid: str = "",
    operator: str = "",
    session_id: str = "",
    trace_id: str = "",
    auto_allocate: bool = True,
    group_code: str = "",
    group_label: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Agent 一次调用搞定整个 Campaign 草稿。

    ``segments`` 形如：
    [
      {
        "segment_code": "silent_30d_no_inbound",
        "priority": 200,
        "label": "沉默-重点",
        "steps": [
          {"step_index":0, "day_offset":0, "send_time":"09:00", "content_text":"..."},
          {"step_index":1, "day_offset":3, "send_time":"09:00", "content_text":"..."},
        ]
      },
      ...
    ]

    会按 priority 降序去做互斥分配（高优先级先抢人）。
    """
    if not segments:
        raise ValueError("at least one segment is required")
    # group_code / group_label 落进 metadata_json, 让 admin list 接口按 group
    # 折叠展示多 campaign (典型场景: 同一份名单按 owner_userid 拆 N 个 campaign,
    # 业务上仍是 1 个推送计划, 见技能 md §3.5 拆 Campaign 模式)
    merged_metadata: dict[str, Any] = dict(metadata or {})
    if group_code:
        merged_metadata["group_code"] = str(group_code)
    if group_label:
        merged_metadata["group_label"] = str(group_label)
    camp = create_campaign_draft(
        display_name=display_name,
        intent=intent,
        anchor_mode=anchor_mode,
        anchor_date=anchor_date,
        owner_userid=owner_userid,
        operator=operator,
        session_id=session_id,
        trace_id=trace_id,
        metadata=merged_metadata or None,
    )
    camp_id = int(camp["id"])
    for seg_spec in segments:
        added = add_segment_to_campaign(
            campaign_id=camp_id,
            segment_code=str(seg_spec.get("segment_code") or ""),
            priority=int(seg_spec.get("priority") or 100),
            label=str(seg_spec.get("label") or ""),
        )
        cs_id = int(added["id"])
        for step in (seg_spec.get("steps") or []):
            add_step_to_campaign(
                campaign_id=camp_id,
                campaign_segment_id=cs_id,
                step_index=int(step.get("step_index") or 0),
                day_offset=int(step.get("day_offset") or 0),
                send_time=str(step.get("send_time") or _DEFAULT_SEND_TIME),
                timezone=str(step.get("timezone") or "Asia/Shanghai"),
                content_text=str(step.get("content_text") or ""),
                stop_on_reply=bool(step.get("stop_on_reply", True)),
                skip_if_recently_touched_days=int(step.get("skip_if_recently_touched_days") or 0),
                agent_run_id=str(step.get("agent_run_id") or ""),
            )
    allocation = {}
    if auto_allocate:
        allocation = allocate_campaign_members(campaign_id=camp_id)
    overview = assemble_campaign_overview(campaign_id=camp_id)
    overview["allocation"] = allocation
    return overview


__all__ = [
    "add_segment_to_campaign",
    "add_step_to_campaign",
    "allocate_campaign_members",
    "assemble_campaign_overview",
    "create_campaign_draft",
    "finish_campaign",
    "get_campaign",
    "append_campaign_step",
    "delete_campaign_step",
    "list_campaign_members",
    "list_campaigns",
    "update_campaign_step",
    "pause_campaign",
    "propose_campaign",
    "reject_campaign",
    "resume_campaign",
    "start_campaign",
    "submit_campaign_for_review",
]
